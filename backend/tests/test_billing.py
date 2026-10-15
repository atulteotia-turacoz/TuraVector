"""Billing: services on upload → invoice → Turacoz approval → client approval → payment. GST split."""
import datetime
import io
import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    BillingApprover, BillingRequest, Country, DocumentType, EmailLog, Invoice, Organisation, OrgMembership, RateCardItem,
    RateService, User,
)
from app.services import billing, billing_tax, payments
from app.services.org_common import assign_default_role
from tests.test_org_isolation import _h, _join, _org, _user


# ---------------------------------------------------------------------------------------------- tax rules
def test_tax_modes_and_split():
    assert billing_tax.tax_mode("Delhi", "07", "Delhi", "7", "India") == "intra"
    assert billing_tax.tax_mode("Delhi", "", "  new  delhi ", "", "India") == "inter"
    assert billing_tax.tax_mode("Delhi", "07", "Maharashtra", "27", "India") == "inter"
    assert billing_tax.tax_mode("Delhi", "07", "Dubai", "", "United Arab Emirates") == "overseas"
    assert billing_tax.line_tax("1000", 18, False, "intra") == (Decimal("90.00"), Decimal("90.00"), Decimal("0.00"))
    assert billing_tax.line_tax("1000", 18, False, "inter") == (0, 0, Decimal("180.00"))
    assert billing_tax.line_tax("1000", 18, False, "overseas") == (0, 0, 0)
    assert billing_tax.line_tax("1000", 18, True, "overseas") == (0, 0, Decimal("180.00"))
    assert billing_tax.line_tax("0.05", 18, False, "intra")[0] == Decimal("0.00")  # 0.0045 rounds down
    assert billing_tax.amount_in_words("11800.50") == "Rupees Eleven Thousand Eight Hundred and Fifty Paise Only"
    assert billing_tax.amount_in_words(2512345) == "Rupees Twenty Five Lakh Twelve Thousand Three Hundred Forty Five Only"
    assert billing.financial_year(datetime.date(2026, 3, 31)) == "2526"
    assert billing.financial_year(datetime.date(2026, 4, 1)) == "2627"


# ---------------------------------------------------------------------------------------------- fixtures
def _service(db, name, rate, unit="per_document", tax=18, overseas=0):
    s = RateService(name=f"{name} {datetime.datetime.now().timestamp()}", unit=unit, standard_rate=rate,
                    tax_percent=tax, tax_overseas=overseas, sac_code="998311", currency="INR", is_active=1, sort_order=0)
    db.add(s)
    db.flush()
    return s


@pytest.fixture()
def uni(db):
    """A Delhi university (per submission) with an admin, a student and a two-service rate card; an approver."""
    org = _org(db, "Billing Test University")
    admin, student = _user(db, "bt_admin"), _user(db, "bt_student", first_name="Riya")
    _join(db, org, admin, "admin")
    _join(db, org, student)
    assign_default_role(db, student)
    review, editing = _service(db, "Review", 1000), _service(db, "Editing", 2, unit="per_word")
    db.add_all([RateCardItem(organisation_id=org.id, service_id=review.id, rate=Decimal("800")),
                RateCardItem(organisation_id=org.id, service_id=editing.id, rate=Decimal("1.50"))])
    s = billing.settings_row(db)
    s.state, s.state_code, s.country = "Delhi", "07", "India"
    team = db.execute(select(Organisation).where(Organisation.kind == "system")).scalar_one()
    approver = db.execute(select(User).join(OrgMembership, OrgMembership.user_id == User.id)
                          .where(OrgMembership.organisation_id == team.id).limit(1)).scalar_one()
    db.add(BillingApprover(user_id=approver.id))
    db.commit()
    return {"org": org, "admin": admin, "student": student, "review": review, "editing": editing, "approver": approver}


def _profile(client, login_as, org, **kw):
    body = {"legal_name": "Billing Test University Trust", "address": "1 Ring Road", "state": "Delhi", "state_code": "07",
            "country": "India", "gstin": "07aaaaa0000a1z5", "billing_cycle": "per_submission", **kw}
    r = client.put(f"/api/superadmin/billing/organisations/{org.id}/profile", headers=login_as("admin"), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _submit(client, db, user, services, text=None, requirement="Please review urgently"):
    dt = db.execute(select(DocumentType).where(DocumentType.is_active == 1).limit(1)).scalar_one()
    country = db.execute(select(Country).where(Country.is_active == 1).limit(1)).scalar_one()
    form = {"document_name": "Billing paper", "document_type": str(dt.id), "country": str(country.id),
            "services": json.dumps(services), "requirement": requirement}
    if text is not None:
        form["content_html"] = text
        return client.post("/api/doccore/upload", headers=_h(user), data=form)
    return client.post("/api/doccore/upload", headers=_h(user), data=form,
                       files={"document_file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")})


# ---------------------------------------------------------------------------------------------- flow
def test_upload_offers_rate_card_and_full_per_submission_flow(client, db, login_as, uni, sent_emails):
    _profile(client, login_as, uni["org"])
    opts = client.get("/api/doccore/upload/options", headers=_h(uni["student"])).json()
    assert {s["service_id"]: s["rate"] for s in opts["rate_card"]} == {uni["review"].id: 800, uni["editing"].id: 1.5}

    r = _submit(client, db, uni["student"], [{"service_id": uni["review"].id}, {"service_id": uni["editing"].id, "quantity": 2000}])
    assert r.status_code == 200, r.text
    assert "sent to Turacoz" in r.json()["message"]
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    assert inv.status == "pending_turacoz" and inv.tax_mode == "intra" and inv.number.startswith("TC")
    assert (inv.subtotal, inv.cgst, inv.sgst, inv.igst, inv.total) == (
        Decimal("3800.00"), Decimal("342.00"), Decimal("342.00"), Decimal("0.00"), Decimal("4484.00"))
    assert any("needs approval" in m["subject"] for m in sent_emails)

    # the client does not see it until Turacoz approves; a student never sees invoices
    assert client.get("/api/org/invoices", headers=_h(uni["admin"])).json()["invoices"] == []
    assert client.get(f"/api/org/invoices/{inv.id}", headers=_h(uni["admin"])).status_code == 404
    assert client.get("/api/billing/invoices", headers=_h(uni["student"])).status_code == 403
    assert client.post(f"/api/billing/invoices/{inv.id}/approve", headers=_h(uni["admin"]), json={}).status_code == 403

    # Turacoz approver adjusts the word count and approves
    h_app = _h(uni["approver"])
    q = client.get("/api/billing/invoices?status=pending_turacoz", headers=h_app).json()
    assert inv.id in {i["id"] for i in q["invoices"]}
    words = next(line for line in inv.lines if line.unit == "per_word")
    r = client.post(f"/api/billing/invoices/{inv.id}/approve", headers=h_app,
                    json={"lines": [{"id": words.id, "quantity": 1800, "rate": 1.5}], "remarks": "Word count checked"})
    assert r.status_code == 200, r.text
    d = r.json()["invoice"]
    assert d["status"] == "pending_client" and d["subtotal"] == 3500 and d["total"] == 4130
    assert [e["action"] for e in d["events"]] == ["created", "adjusted", "turacoz_approved"]

    # the university admin sees it, may query it, then approves
    h_adm = _h(uni["admin"])
    lst = client.get("/api/org/invoices", headers=h_adm).json()
    assert [i["number"] for i in lst["invoices"]] == [inv.number] and lst["outstanding"] == 4130
    assert client.post(f"/api/org/invoices/{inv.id}/query", headers=h_adm, json={"remarks": ""}).status_code == 400
    assert client.post(f"/api/org/invoices/{inv.id}/query", headers=h_adm, json={"remarks": "Wrong GSTIN"}).status_code == 200
    assert client.post(f"/api/billing/invoices/{inv.id}/approve", headers=h_app, json={}).status_code == 200
    r = client.post(f"/api/org/invoices/{inv.id}/approve", headers=h_adm, json={})
    assert r.status_code == 200 and r.json()["invoice"]["status"] == "awaiting_payment"
    assert client.get(f"/api/org/invoices/{inv.id}/pdf", headers=h_adm).content[:4] == b"%PDF"

    # another university's admin cannot see it
    other_admin = _user(db, "bt_other")
    _join(db, _org(db, "Elsewhere Uni"), other_admin, "admin")
    assert client.get(f"/api/org/invoices/{inv.id}", headers=_h(other_admin)).status_code == 404

    # the student sees their request's progress but not the invoice
    mine = client.get("/api/billing/my-requests", headers=_h(uni["student"])).json()["requests"]
    assert mine[0]["status"] == "Invoice approved" and len(mine[0]["services"]) == 2
    assert db.query(EmailLog).filter(EmailLog.email_type.like("invoice_%")).count() >= 3


def test_payment_with_razorpay(client, db, login_as, uni, monkeypatch):
    _profile(client, login_as, uni["org"])
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    client.post(f"/api/billing/invoices/{inv.id}/approve", headers=_h(uni["approver"]), json={})
    client.post(f"/api/org/invoices/{inv.id}/approve", headers=_h(uni["admin"]), json={})

    gw = payments.get(db, "razorpay")
    monkeypatch.setattr(payments, "active", lambda db: gw)
    monkeypatch.setattr(payments, "missing_fields", lambda gw: [])
    rz = payments.ADAPTERS["razorpay"]
    monkeypatch.setattr(rz, "create_order", lambda gw, amount, receipt, notes=None: {
        "gateway": "razorpay", "order_id": "order_T1", "amount": int(amount * 100), "currency": "INR", "key_id": "rzp_test_x"})
    monkeypatch.setattr(rz, "verify", lambda gw, **kw: kw.get("signature") == "good")
    h = _h(uni["admin"])
    order = client.post(f"/api/org/invoices/{inv.id}/pay", headers=h).json()
    assert order["order_id"] == "order_T1" and order["amount"] == 94400
    bad = client.post(f"/api/org/invoices/{inv.id}/pay/verify", headers=h,
                      json={"order_id": "order_T1", "payment_id": "pay_1", "signature": "forged"})
    assert bad.status_code == 400
    ok = client.post(f"/api/org/invoices/{inv.id}/pay/verify", headers=h,
                     json={"order_id": "order_T1", "payment_id": "pay_1", "signature": "good"})
    assert ok.status_code == 200 and ok.json()["invoice"]["status"] == "paid"


def test_payment_not_configured(client, db, login_as, uni, monkeypatch):
    _profile(client, login_as, uni["org"])
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    client.post(f"/api/billing/invoices/{inv.id}/approve", headers=_h(uni["approver"]), json={})
    client.post(f"/api/org/invoices/{inv.id}/approve", headers=_h(uni["admin"]), json={})
    monkeypatch.setattr(payments, "active", lambda db: None)
    r = client.post(f"/api/org/invoices/{inv.id}/pay", headers=_h(uni["admin"]))
    assert r.status_code == 400 and "not been set up" in r.json()["detail"]
    r = client.post(f"/api/billing/invoices/{inv.id}/mark-paid", headers=_h(uni["approver"]), json={"reference": "UTR123"})
    assert r.json()["invoice"]["status"] == "paid"


def test_waits_for_billing_profile_then_invoices(client, db, login_as, uni):
    r = _submit(client, db, uni["student"], [{"service_id": uni["review"].id}], text="<p><b>My</b> requirement text</p>")
    assert r.status_code == 200, r.text
    assert db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).first() is None
    q = client.get("/api/billing/invoices", headers=_h(uni["approver"])).json()
    w = next(x for x in q["waiting"] if x["organisation_id"] == uni["org"].id)
    assert w["requests"] == 1 and w["missing"] == ["country", "state"]
    saved = _profile(client, login_as, uni["org"], state="Maharashtra", state_code="27")
    assert saved["missing"] == []
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    assert inv.tax_mode == "inter" and inv.igst == Decimal("144.00") and inv.cgst == 0


def test_monthly_billing_and_overseas(client, db, login_as, uni):
    _profile(client, login_as, uni["org"], billing_cycle="monthly", country="United Arab Emirates", state="Dubai", state_code="")
    taxed = _service(db, "Abroad taxed", 500, overseas=1)
    db.add(RateCardItem(organisation_id=uni["org"].id, service_id=taxed.id, rate=Decimal("500")))
    db.commit()
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    _submit(client, db, uni["student"], [{"service_id": taxed.id, "quantity": 2}])
    assert db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).first() is None
    r = client.post(f"/api/billing/organisations/{uni['org'].id}/generate", headers=_h(uni["approver"]), json={})
    assert r.status_code == 200, r.text
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    assert inv.cycle == "monthly" and len(inv.lines) == 2 and inv.tax_mode == "overseas"
    assert inv.subtotal == Decimal("1800.00") and inv.igst == Decimal("180.00")  # only the overseas-taxed service
    assert not db.execute(select(BillingRequest).where(BillingRequest.organisation_id == uni["org"].id,
                                                       BillingRequest.invoice_id.is_(None))).first()
    again = client.post(f"/api/billing/organisations/{uni['org'].id}/generate", headers=_h(uni["approver"]), json={})
    assert again.status_code == 400


def test_invalid_services_and_numbering(client, db, login_as, uni):
    other = _service(db, "Not on card", 10)
    r = _submit(client, db, uni["student"], [{"service_id": other.id}])
    assert r.status_code == 400 and "rate card" in r.json()["detail"]["errors"]["services"]
    r = _submit(client, db, uni["student"], [{"service_id": uni["review"].id, "quantity": 0}])
    assert r.status_code == 400
    a, b = billing.next_number(db), billing.next_number(db)
    assert a != b and a[:-4] == b[:-4] and int(b[-4:]) == int(a[-4:]) + 1


def test_superadmin_settings_and_approvers(client, db, login_as, uni):
    h = login_as("admin")
    r = client.put("/api/superadmin/billing/settings", headers=h,
                   json={"company_name": "Turacoz", "state": "Delhi", "invoice_prefix": "tz-", "gstin": "07abc"})
    assert r.status_code == 200 and r.json()["invoice_prefix"] == "TZ" and r.json()["next_number"].startswith("TZ")
    lst = client.get("/api/superadmin/billing/approvers", headers=h).json()
    assert uni["approver"].id in {a["user_id"] for a in lst["approvers"]}
    r = client.post("/api/superadmin/billing/approvers", headers=h, json={"user_id": uni["student"].id})
    assert r.status_code == 400  # only Turacoz team members
    me = client.get("/api/auth/me", headers=_h(uni["approver"])).json()
    assert me.get("is_invoice_approver") is True


# ---------------------------------------------------------------------------------------------- reminders
def test_reminders_default_off_and_custom(client, db, login_as, uni, sent_emails):
    from app.services import billing_reminders
    _profile(client, login_as, uni["org"])
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    h = login_as("admin")
    r = client.put("/api/superadmin/billing/settings", headers=h, json={
        "company_name": "Turacoz", "state": "Delhi", "invoice_prefix": "TC", "reminders_enabled": True,
        "reminder_after_days": 2, "reminder_repeat_days": 1, "reminder_max": 2,
        "remind_turacoz": True, "remind_client": True, "remind_payment": True})
    assert r.status_code == 200 and r.json()["reminder_after_days"] == 2
    start = inv.status_changed_at
    day = lambda n: start + datetime.timedelta(days=n, minutes=1)  # noqa: E731

    def ours(now):
        return [n for n in billing_reminders.send_due(db, now) if n == inv.number]

    assert ours(day(1)) == []                      # not yet
    sent_emails.clear()
    assert ours(day(2)) == [inv.number]            # first reminder → Turacoz approvers
    assert any("needs approval" in m["subject"] and m["subject"].startswith("Reminder") for m in sent_emails)
    assert ours(day(2)) == []                      # not twice the same day
    assert ours(day(3)) == [inv.number]            # repeat after 1 day
    assert ours(day(9)) == []                      # max 2

    # the stage changes → the clock restarts; the client's admins are reminded
    client.post(f"/api/billing/invoices/{inv.id}/approve", headers=_h(uni["approver"]), json={})
    db.refresh(inv)
    assert inv.reminders_sent == 0
    start = inv.status_changed_at
    sent_emails.clear()
    assert ours(start + datetime.timedelta(days=2, minutes=1)) == [inv.number]
    assert any(m["to"] == uni["admin"].email and "please approve" in m["subject"] for m in sent_emails)

    # the workspace switches reminders off
    client.put(f"/api/superadmin/billing/organisations/{uni['org'].id}/profile", headers=h,
               json={"country": "India", "state": "Delhi", "reminder_mode": "off"})
    assert ours(start + datetime.timedelta(days=5)) == []
    # …or customises them (first after 10 days, up to 5)
    r = client.put(f"/api/superadmin/billing/organisations/{uni['org'].id}/profile", headers=h,
                   json={"country": "India", "state": "Delhi", "reminder_mode": "custom", "reminder_after_days": 10,
                         "reminder_repeat_days": 2, "reminder_max": 5})
    assert r.json()["reminder_mode"] == "custom"
    # one reminder went on day 2; custom repeats every 2 days → nothing on day 3, the next on day 4
    assert ours(start + datetime.timedelta(days=3)) == []
    assert ours(start + datetime.timedelta(days=4, minutes=2)) == [inv.number]
    bad = client.put(f"/api/superadmin/billing/organisations/{uni['org'].id}/profile", headers=h,
                     json={"country": "India", "reminder_mode": "custom"})
    assert bad.status_code == 400


def test_dashboard_summary_highlights_waiting(client, db, login_as, uni):
    _profile(client, login_as, uni["org"])
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    inv.status_changed_at = inv.status_changed_at - datetime.timedelta(days=10)
    db.commit()
    d = client.get("/api/billing/summary", headers=_h(uni["approver"])).json()
    row = next(r for r in d["invoices"] if r["id"] == inv.id)
    assert row["overdue"] is True and row["waiting_days"] >= 10
    assert d["counts"]["pending_turacoz"]["count"] >= 1 and d["counts"]["pending_turacoz"]["overdue"] >= 1
    assert client.get("/api/billing/summary", headers=_h(uni["admin"])).status_code == 403


def test_written_text_keeps_formatting(client, db, uni):
    import base64
    import io as _io
    from PIL import Image
    from docx import Document as Docx
    from app.models import DocumentVersion
    from app.config import settings
    buf = _io.BytesIO()
    Image.new("RGB", (30, 10), (10, 120, 200)).save(buf, "PNG")
    img = base64.b64encode(buf.getvalue()).decode()
    html = (f'<h2>Aim</h2><p style="text-align: center;"><b>Bold</b> <span style="color: rgb(255, 0, 0);">red</span></p>'
            f'<table><tr><td>a</td><td>b</td></tr></table><p><img src="data:image/png;base64,{img}"></p>')
    dt = db.execute(select(DocumentType).where(DocumentType.is_active == 1).limit(1)).scalar_one()
    country = db.execute(select(Country).where(Country.is_active == 1).limit(1)).scalar_one()
    r = client.post("/api/doccore/upload", headers=_h(uni["student"]),
                    data={"document_name": "Rich text", "document_type": str(dt.id), "country": str(country.id)},
                    files={"content_file": ("content.html", _io.BytesIO(html.encode()), "text/html")})
    assert r.status_code == 200, r.text
    v = db.execute(select(DocumentVersion).where(DocumentVersion.document_id == r.json()["document_id"])).scalar_one()
    assert v.file_extension == "docx"
    d = Docx(str(settings.media_root / v.document_file))
    assert d.paragraphs[0].style.name == "Heading 2" and len(d.tables) == 1 and len(d.inline_shapes) == 1


def test_financial_manager_per_university_and_default(client, db, login_as, uni, sent_emails):
    """A university's own Financial Manager handles its invoices; the default ones handle the rest."""
    team = db.execute(select(Organisation).where(Organisation.kind == "system")).scalar_one()
    fm = _user(db, "bt_finance", user_type="reviewer")
    _join(db, team, fm)
    h = login_as("admin")
    r = client.post(f"/api/superadmin/organisations/{uni['org'].id}/assignments", headers=h, json={"user_id": fm.id, "role": "finance"})
    assert r.status_code == 200 and "Financial Manager" in r.json()["message"]
    _profile(client, login_as, uni["org"])
    sent_emails.clear()
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id)).scalar_one()
    assert {m["to"] for m in sent_emails if "needs approval" in m["subject"]} == {fm.email}  # not the default approver

    default = _h(uni["approver"])
    assert client.get(f"/api/billing/invoices/{inv.id}", headers=default).status_code == 404
    assert inv.id not in {i["id"] for i in client.get("/api/billing/invoices?status=", headers=default).json()["invoices"]}
    own = _h(fm)
    assert client.get(f"/api/billing/invoices/{inv.id}", headers=own).status_code == 200
    dash = client.get("/api/billing/dashboard", headers=own).json()
    assert [o["id"] for o in dash["organisations"]] == [uni["org"].id] and dash["organisations"][0]["assigned"] is True
    assert dash["totals"]["to_approve"] == 1
    # a university without its own Financial Manager is the default's, not this one's
    other = _org(db, "No FM University")
    assert other.id in {o["id"] for o in client.get("/api/billing/dashboard", headers=default).json()["organisations"]}
    assert client.get(f"/api/billing/organisations/{other.id}/profile", headers=own).status_code == 404
    prof = client.get(f"/api/superadmin/billing/organisations/{uni['org'].id}/profile", headers=h).json()
    assert prof["financial_managers"]["uses_default"] is False and prof["financial_managers"]["people"][0]["id"] == fm.id
    assert client.post(f"/api/billing/invoices/{inv.id}/approve", headers=own, json={}).status_code == 200
    me = client.get("/api/auth/me", headers=own).json()
    assert me["is_invoice_approver"] is True and me["user_type_display"] == "Financial Manager"


def test_finance_analytics_and_reports(client, db, login_as, uni):
    _profile(client, login_as, uni["org"])
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}, {"service_id": uni["editing"].id, "quantity": 1000}])
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    a_inv, b_inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id).order_by(Invoice.id)).scalars().all()
    h_app, h_adm = _h(uni["approver"]), _h(uni["admin"])
    for inv in (a_inv, b_inv):
        client.post(f"/api/billing/invoices/{inv.id}/approve", headers=h_app, json={})
    client.post(f"/api/org/invoices/{a_inv.id}/approve", headers=h_adm, json={})
    client.post(f"/api/billing/invoices/{a_inv.id}/mark-paid", headers=h_app, json={"reference": "UTR1"})

    an = client.get("/api/billing/analytics", headers=h_app).json()
    org_row = next(o for o in an["by_organisation"] if o["id"] == uni["org"].id)
    assert org_row["billed"] == 2714 + 944 and org_row["received"] == 2714 and org_row["outstanding"] == 944
    assert len(an["trend"]) == 12 and an["trend"][-1]["billed"] >= 3658
    assert {s["name"] for s in an["by_service"]} >= {uni["review"].name, uni["editing"].name}
    assert an["cycle_days"]["turacoz_approval"] is not None and an["ageing"][0]["amount"] >= 944

    today = datetime.date.today().isoformat()
    rep = client.get("/api/billing/reports", headers=h_app, params={"date_from": today, "date_to": today, "organisation": uni["org"].id}).json()
    assert rep["summary"]["invoices"] == 2 and rep["summary"]["total"] == 3658 and rep["summary"]["received"] == 2714
    assert rep["summary"]["outstanding"] == 944 and len(rep["payments"]) == 1
    g = rep["gst"][0]
    assert g["tax_mode"] == "intra" and g["rate"] == 18 and g["cgst"] == g["sgst"] and g["category"] == "B2B"  # the profile has a GSTIN
    xl = client.get("/api/billing/reports/export", headers=h_app, params={"date_from": today, "date_to": today})
    assert xl.status_code == 200 and xl.content[:2] == b"PK"
    assert client.get("/api/billing/reports/export", headers=h_app, params={"format": "pdf"}).content[:4] == b"%PDF"
    csv = client.get("/api/billing/reports/export", headers=h_app, params={"format": "csv", "section": "gst"})
    assert "Taxable value" in csv.content.decode("utf-8-sig")
    assert client.get("/api/billing/reports", headers=h_app, params={"date_from": "2026-05-02", "date_to": "2026-05-01"}).status_code == 400
    assert client.get("/api/billing/analytics", headers=h_adm).status_code == 403


def test_university_finance_reports(client, db, login_as, uni):
    _profile(client, login_as, uni["org"])
    _submit(client, db, uni["student"], [{"service_id": uni["review"].id}])
    _submit(client, db, uni["student"], [{"service_id": uni["editing"].id, "quantity": 100}])
    a_inv, b_inv = db.execute(select(Invoice).where(Invoice.organisation_id == uni["org"].id).order_by(Invoice.id)).scalars().all()
    client.post(f"/api/billing/invoices/{a_inv.id}/approve", headers=_h(uni["approver"]), json={})  # b stays with Turacoz
    h = _h(uni["admin"])
    today = datetime.date.today().isoformat()
    rep = client.get("/api/org/finance/reports", headers=h, params={"date_from": today, "date_to": today}).json()
    assert [r["number"] for r in rep["register"]] == [a_inv.number]     # the one still with Turacoz is not shown
    assert "by_organisation" not in rep and rep["by_member"][0]["member"].startswith("Riya") and rep["by_member"][0]["total"] == 944
    assert rep["summary"]["outstanding"] == 944
    an = client.get("/api/org/finance/analytics", headers=h).json()
    assert an["totals"]["billed"] == 944
    xl = client.get("/api/org/finance/reports/export", headers=h, params={"date_from": today, "date_to": today})
    assert xl.status_code == 200 and xl.content[:2] == b"PK"
    assert client.get("/api/org/finance/reports/export", headers=h, params={"format": "csv", "section": "by_member"}).status_code == 200
    assert client.get("/api/org/finance/reports", headers=_h(uni["student"])).status_code == 403
