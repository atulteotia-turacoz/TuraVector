"""Tests for the tools module (categories, bulk import, mail logs, SMTP, journals, analytics,
export). Everything runs inside the rolled-back test transaction; outgoing email is
stubbed by conftest, SMTP and journal HTTP calls are replaced by fakes below — nothing ever
leaves the machine.
"""
import io
import json

import openpyxl
import pytest
from sqlalchemy import select

from app.models import (
    Brand, Country, DocumentType, EmailLog, SMTPSettings,
    TherapeuticArea, User, UserJournalSelection,
)
from app.services import tools_journals, tools_smtp


# --------------------------------------------------------------------------- network guards
class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, *a, **kw):
        self.host, self.port, self.sent, self.logged_in, self.tls = host, port, [], None, False
        FakeSMTP.instances.append(self)

    def starttls(self, **kw):
        self.tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent.append((from_addr, to_addrs, msg))

    def quit(self):
        pass


class _FakeSmtplib:
    SMTP = FakeSMTP
    SMTP_SSL = FakeSMTP


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(tools_smtp, "smtplib", _FakeSmtplib)

    def blocked(*a, **kw):
        raise AssertionError("real HTTP call attempted in a test")

    monkeypatch.setattr(tools_journals.requests, "get", blocked)


def _admin(db):
    return db.query(User).filter(User.username == "admin").one()


# --------------------------------------------------------------------------- categories
@pytest.mark.parametrize("kind,model,code", [
    ("document-types", DocumentType, None),
    ("therapeutic-areas", TherapeuticArea, None),
    ("brands", Brand, "ZZTESTBR"),
    ("countries", Country, "ZZ"),
])
def test_category_crud_and_toggle(client, db, login_as, kind, model, code):
    h = login_as("admin")
    data = {"name": "Zz Test Category"}
    if code:
        data["code_name"] = code
    r = client.post(f"/api/tools/categories/{kind}", data=data, headers=h)
    assert r.status_code == 200, r.text
    assert "added successfully" in r.json()["message"]
    item_id = r.json()["item"]["id"]
    obj = db.get(model, item_id)
    assert obj.is_active == 1

    # required-field validation
    r = client.post(f"/api/tools/categories/{kind}", data={"name": "  "}, headers=h)
    assert r.status_code == 400 and "required" in r.json()["detail"]

    # edit
    upd = {"name": "Zz Test Category 2", **({"code_name": code} if code else {})}
    r = client.post(f"/api/tools/categories/{kind}/{item_id}", data=upd, headers=h)
    assert r.status_code == 200 and r.json()["message"].endswith("updated successfully")
    db.refresh(obj)
    assert obj.name == "Zz Test Category 2"

    # toggle twice
    r = client.post(f"/api/tools/categories/{kind}/{item_id}/toggle", headers=h)
    assert "deactivated successfully" in r.json()["message"]
    r = client.post(f"/api/tools/categories/{kind}/{item_id}/toggle", headers=h)
    assert "activated successfully" in r.json()["message"]

    # list contains it
    params = {"search": "Zz Test"} if kind == "countries" else {}
    lst = client.get(f"/api/tools/categories/{kind}", params=params, headers=h).json()
    assert any(i["id"] == item_id for i in lst["items"])
    assert lst["active_count"] + lst["inactive_count"] == lst["total_items"]
    assert client.get(f"/api/tools/categories/{kind}/{item_id}", headers=h).json()["item"]["name"] == "Zz Test Category 2"


def test_categories_require_admin_like(client, login_as):
    r = client.get("/api/tools/categories/brands", headers=login_as("reviewer1"))
    assert r.status_code == 403
    assert r.json()["detail"] == "You do not have permission to manage categories"


def test_country_pagination(client, login_as):
    h = login_as("admin")
    r = client.get("/api/tools/categories/countries", params={"page": "abc"}, headers=h).json()
    assert r["pagination"]["page"] == 1 and len(r["items"]) <= 10
    last = client.get("/api/tools/categories/countries", params={"page": "9999"}, headers=h).json()
    assert last["pagination"]["page"] == last["pagination"]["num_pages"]


def test_duplicate_brand_code_reports_db_error(client, db, login_as):
    h = login_as("admin")
    client.post("/api/tools/categories/brands", data={"name": "A", "code_name": "ZZDUPE"}, headers=h)
    r = client.post("/api/tools/categories/brands", data={"name": "B", "code_name": "ZZDUPE"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"].startswith("Error adding brand:")


# --------------------------------------------------------------------------- bulk import
def test_bulk_import_csv_document_types(client, db, login_as):
    h = login_as("admin")
    csv_body = "name,is_active\nZz Bulk Type A,True\nZz Bulk Type B,False\nZz Bulk Type A,True\n"
    r = client.post("/api/tools/bulk-import/document-types",
                    files={"file": ("types.csv", csv_body.encode(), "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success_count"] == 2 and body["error_count"] == 1
    assert body["errors"] == ["Row 4: Document type 'Zz Bulk Type A' already exists"]
    assert body["messages"][0]["text"] == "Successfully imported 2 document types."
    b = db.execute(select(DocumentType).where(DocumentType.name == "Zz Bulk Type B")).scalar_one()
    assert b.is_active == 0


def test_bulk_import_xlsx_brands(client, db, login_as):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "code_name", "is_active"])
    ws.append(["Zz Brand X", "zzbx", "True"])
    ws.append(["Zz Brand Y", None, "True"])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/tools/bulk-import/brands",
                    files={"file": ("b.xlsx", buf.getvalue(), "application/vnd.ms-excel")}, headers=login_as("admin"))
    body = r.json()
    assert db.execute(select(Brand).where(Brand.code_name == "ZZBX")).scalar_one().name == "Zz Brand X"
    # an empty cell is NaN in pandas → str() gives 'nan' → Django accepted it as code 'NAN' (same here)
    assert body["success_count"] + body["error_count"] == 2, body


def test_bulk_import_validation(client, login_as):
    h = login_as("admin")
    r = client.post("/api/tools/bulk-import/countries", files={"file": ("x.txt", b"abc", "text/plain")}, headers=h)
    assert r.status_code == 400 and "not allowed" in r.json()["detail"]
    r = client.post("/api/tools/bulk-import/countries", headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "This field is required."


def test_bulk_import_countries_and_template(client, db, login_as):
    h = login_as("admin")
    r = client.post("/api/tools/bulk-import/countries",
                    files={"file": ("c.csv", b"name,code_name,is_active\nZzland,zzl,True\n", "text/csv")}, headers=h)
    assert r.json()["success_count"] == 1
    assert db.execute(select(Country).where(Country.name == "Zzland")).scalar_one().code_name == "ZZL"
    t = client.get("/api/tools/bulk-import/countries/template")
    assert t.status_code == 200 and t.text.startswith("name,code_name,is_active")
    assert 'filename="countries_template.csv"' in t.headers["content-disposition"]
    ta = client.get("/api/tools/bulk-import/therapeutic-areas/template")
    assert ta.content.startswith(b"\xef\xbb\xbf")


def test_country_upload_legacy(client, db, login_as):
    h = login_as("admin")
    existing = db.execute(select(Country).limit(1)).scalar_one()
    csv_body = f"name,code_name\nZz Upland,ZU\n{existing.name},QQ\n,\n"
    r = client.post("/api/tools/country-upload", files={"file": ("c.csv", csv_body.encode(), "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    msgs = [m["text"] for m in r.json()["messages"]]
    assert msgs[0] == "Import completed: 1 countries created, 2 errors"
    assert f'Row 3: Country with name "{existing.name}" already exists' in msgs
    # update existing
    r = client.post("/api/tools/country-upload", data={"update_existing": "on"},
                    files={"file": ("c.csv", f"name,code_name\n{existing.name},QQ\n".encode(), "text/csv")}, headers=h)
    assert r.json()["messages"][0]["text"] == "Import completed: 1 countries updated"
    db.refresh(existing)
    assert existing.code_name == "QQ"
    # missing column
    r = client.post("/api/tools/country-upload", files={"file": ("c.csv", b"name\nX\n", "text/csv")}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "Missing required columns: code_name"


# --------------------------------------------------------------------------- mail logs
def _failed_log(db, **kw):
    log = EmailLog(email_type="general", recipient_email="zz@example.com", subject="Zz subject",
                   message_content="hello", status="failed", retry_count=kw.get("retry_count", 1),
                   from_email="noreply@turadome.com", error_message="boom")
    db.add(log)
    db.flush()
    return log


def test_mail_logs_list_and_detail(client, db, login_as):
    h = login_as("admin")
    log = _failed_log(db)
    r = client.get("/api/tools/mail-logs", params={"search": "zz@example.com", "status": "failed"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert any(i["id"] == log.id for i in body["items"])
    assert body["stats"]["total"] >= body["stats"]["sent"] + body["stats"]["failed"]
    d = client.get(f"/api/tools/mail-logs/{log.id}", headers=h).json()["email_log"]
    assert d["message_content"] == "hello" and d["error_message"] == "boom" and d["can_retry"]
    api = client.get(f"/api/tools/email-log/{log.id}", headers=h).json()
    assert api["status_display"] == "Failed" and api["email_type_display"] == "General"


def test_mail_logs_permission(client, login_as):
    r = client.get("/api/tools/mail-logs", headers=login_as("reviewer1"))
    assert r.status_code == 403 and r.json()["detail"] == "You do not have permission to view mail logs"


def test_retry_email_success_deletes_old(client, db, login_as, sent_emails):
    log = _failed_log(db)
    log_id = log.id
    r = client.post(f"/api/tools/mail-logs/{log_id}/retry", headers=login_as("admin"))
    assert r.status_code == 200 and r.json() == {"message": "Email retried successfully", "status": "sent"}
    assert sent_emails and sent_emails[-1]["to"] == "zz@example.com"
    assert db.get(EmailLog, log_id) is None
    new = db.execute(select(EmailLog).where(EmailLog.recipient_email == "zz@example.com")).scalars().all()
    assert len(new) == 1 and new[0].status == "sent"


def test_retry_email_not_retryable(client, db, login_as, sent_emails):
    log = _failed_log(db, retry_count=3)
    r = client.post(f"/api/tools/mail-logs/{log.id}/retry", headers=login_as("admin"))
    assert r.status_code == 400 and "cannot be retried" in r.json()["error"]
    assert not sent_emails


# --------------------------------------------------------------------------- SMTP
def _smtp_form(**over):
    data = {"action": "create", "host": "smtp.zz-test.invalid", "port": "587", "username": "zz@test.invalid",
            "password": "secret", "use_tls": "on", "from_email": "zz@test.invalid", "from_name": "Zz",
            "display_name": "Zz", "protocol": "smtp", "mailtype": "html", "charset": "utf-8",
            "encoding": "8bit", "crlf": "\\r\\n", "newline": "\\r\\n", "status": "active", "wordwrap": "on"}
    data.update(over)
    return data


def test_smtp_crud_keeps_active_row_and_never_sends(client, db, login_as):
    h = login_as("admin")
    active_before = db.execute(select(SMTPSettings).where(SMTPSettings.is_active == 1)).scalars().all()
    # create (inactive so the real active config stays active)
    r = client.post("/api/tools/smtp-settings", data=_smtp_form(), headers=h)
    assert r.status_code == 200 and r.json()["message"] == "SMTP settings created successfully"
    new_id = r.json()["id"]
    cfg = db.get(SMTPSettings, new_id)
    assert cfg.is_active == 0 and cfg.use_tls == 1 and cfg.smtp_host == "smtp.zz-test.invalid" and cfg.smtp_port == 587
    assert [c.id for c in db.execute(select(SMTPSettings).where(SMTPSettings.is_active == 1)).scalars()] == \
        [c.id for c in active_before]

    lst = client.get("/api/tools/smtp-settings", headers=h).json()
    assert any(c["id"] == new_id for c in lst["smtp_configurations"])
    assert all("password" not in c for c in lst["smtp_configurations"])

    # edit: blank password keeps the old one
    r = client.post(f"/api/tools/smtp-settings/{new_id}", data=_smtp_form(action="update", password="", port="2525"),
                    headers=h)
    assert r.status_code == 200
    db.refresh(cfg)
    assert cfg.port == 2525 and cfg.password == "secret"

    # invalid port
    r = client.post(f"/api/tools/smtp-settings/{new_id}", data=_smtp_form(action="update", port="abc"), headers=h)
    assert r.status_code == 400 and r.json()["detail"].startswith("Failed to update SMTP settings:")

    # test connection — fake smtplib only
    r = client.post(f"/api/tools/smtp-settings/{new_id}/test", headers=h)
    assert r.json()["success"] is True
    assert r.json()["message"] == "SMTP connection test successful (no email sent)"
    assert FakeSMTP.instances and FakeSMTP.instances[-1].host == "smtp.zz-test.invalid"
    assert all(not i.sent for i in FakeSMTP.instances)
    db.refresh(cfg)
    assert cfg.is_tested == 1

    # delete
    r = client.post(f"/api/tools/smtp-settings/{new_id}/delete", headers=h)
    assert r.json()["message"] == "SMTP settings deleted successfully"
    assert db.get(SMTPSettings, new_id) is None


def test_smtp_create_active_deactivates_others(client, db, login_as):
    h = login_as("admin")
    r = client.post("/api/tools/smtp-settings", data=_smtp_form(is_active="on"), headers=h)
    new_id = r.json()["id"]
    actives = db.execute(select(SMTPSettings.id).where(SMTPSettings.is_active == 1)).scalars().all()
    assert actives == [new_id]   # rolled back after the test


def test_smtp_test_with_email_uses_fake(client, db, login_as):
    h = login_as("admin")
    new_id = client.post("/api/tools/smtp-settings", data=_smtp_form(test_email="dest@test.invalid"), headers=h).json()["id"]
    r = client.post(f"/api/tools/smtp-settings/{new_id}/test", headers=h).json()
    assert r["success"] and r["message"] == "Test email sent successfully to dest@test.invalid"
    assert FakeSMTP.instances[-1].sent[0][1] == ["dest@test.invalid"]


def test_smtp_permissions(client, login_as):
    h = login_as("reviewer1")
    assert client.get("/api/tools/smtp-settings", headers=h).status_code == 403
    assert client.post("/api/tools/smtp-settings/1/test", headers=h).json() == {"error": "Permission denied"}


# --------------------------------------------------------------------------- journals
def test_journal_search_and_save(client, db, login_as, monkeypatch):
    calls = []

    class Resp:
        def __init__(self, payload=None, content=b""):
            self._p, self.content = payload, content

        def raise_for_status(self):
            pass

        def json(self):
            return self._p

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if "springernature" in url:
            return Resp({"records": [{"publicationName": "Zz Springer Journal", "publisher": "Springer",
                                      "issn": "1111-2222", "url": "https://example.org/zz"}]})
        if "esearch" in url:
            return Resp(content=b"<eSearchResult><IdList><Id>1</Id></IdList></eSearchResult>")
        return Resp(content=b"<PubmedArticleSet><PubmedArticle><MedlineCitation><Article><Journal>"
                            b"<ISSN>3333-4444</ISSN><Title>Zz PubMed Journal</Title></Journal></Article>"
                            b"</MedlineCitation></PubmedArticle></PubmedArticleSet>")

    monkeypatch.setattr(tools_journals.requests, "get", fake_get)
    monkeypatch.setattr(tools_journals.settings, "SPRINGER_API_KEY", "test-key")
    h = login_as("admin")
    r = client.post("/api/tools/journal-search", json={"query": "zz cancer"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    names = {j["name"]: j for j in body["journals"]}
    assert names["Zz Springer Journal"]["source"] == "springer_api"
    assert names["Zz PubMed Journal"]["source"] == "pubmed_api"
    assert body["sources"]["elsevier_api_count"] > 0   # built-in Elsevier oncology catalogue
    assert len(calls) == 3

    jid = names["Zz Springer Journal"]["id"]
    r = client.post("/api/tools/save-journal", json={"journal_id": jid, "action": "save"}, headers=h)
    assert r.json() == {"message": "Journal saved successfully", "is_saved": True}
    sel = client.get("/api/tools/journal-selector", headers=h).json()
    assert any(s["journal"]["id"] == jid for s in sel["user_selections"])
    r = client.post("/api/tools/save-journal", json={"journal_id": jid, "action": "unsave"}, headers=h)
    assert r.json()["is_saved"] is False
    assert db.execute(select(UserJournalSelection).where(UserJournalSelection.journal_id == jid)).first() is None
    r = client.post("/api/tools/save-journal", json={"journal_id": jid, "action": "x"}, headers=h)
    assert r.status_code == 400


def test_journal_search_requires_query(client, login_as):
    r = client.post("/api/tools/journal-search", json={"query": " "}, headers=login_as("admin"))
    assert r.status_code == 400 and r.json()["detail"] == "Search query is required"


# --------------------------------------------------------------------------- dashboard / analytics / export
def test_other_documents_dashboard(client, login_as):
    r = client.get("/api/tools/other-documents", headers=login_as("admin"))
    assert r.status_code == 200
    assert r.json() == {"dashboard_type": "other_documents", "saved_journals_count": r.json()["saved_journals_count"]}



def test_projects_are_removed(client, login_as):
    h = login_as("admin")
    for url in ("/api/projects", "/api/projects/all-collaborators", "/api/projects/collaborators"):
        assert client.get(url, headers=h).status_code == 404, url

@pytest.mark.parametrize("period", ["7", "30", "all", "bogus"])
def test_analytics(client, login_as, period):
    r = client.get("/api/tools/analytics", params={"period": period}, headers=login_as("admin"))
    assert r.status_code == 200
    b = r.json()
    assert not any("project" in k or "collaboration" in k for k in b)
    assert len(b["monthly_uploads"]) == 6
    assert b["total_reviews"] == b["completed_reviews"] + b["pending_reviews"]
    if period == "bogus":
        assert b["period_label"] == "Last 30 days"


@pytest.mark.parametrize("export_type", ["all", "documents", "journals"])
def test_export_json_and_csv(client, login_as, export_type):
    h = login_as("admin")
    summary = client.get("/api/tools/export-data", headers=h).json()
    r = client.post("/api/tools/export-data", data={"export_type": export_type, "export_format": "json"}, headers=h)
    assert r.status_code == 200 and "turavector_export_" in r.headers["content-disposition"]
    data = json.loads(r.text)
    assert "projects" not in data and "projects_count" not in summary
    if export_type in ("all", "documents"):
        assert len(data["documents"]) == summary["documents_count"]
    r = client.post("/api/tools/export-data", data={"export_type": export_type, "export_format": "csv"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    if export_type in ("all", "documents"):
        assert "=== DOCUMENTS ===" in r.text
