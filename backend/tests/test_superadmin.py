"""Superadmin (Django admin replacement) — runs inside the rollback-only fixtures of conftest.py."""
import io
import json

import pytest
from sqlalchemy import func, select

from app.core.security import check_password
from app.models import Base
from app.services.superadmin_registry import MODELS, REGISTERED

API = "/api/superadmin"
LOG = Base.metadata.tables["django_admin_log"]


def _path(label: str) -> str:
    s = MODELS[label]
    return f"{API}/models/{s['app_label']}/{s['model_name']}"


def _log_rows(db, since_id: int):
    return [dict(r) for r in db.execute(select(LOG).where(LOG.c.id > since_id).order_by(LOG.c.id)).mappings().all()]


def _max_log_id(db) -> int:
    return db.execute(select(func.coalesce(func.max(LOG.c.id), 0))).scalar_one()


@pytest.fixture()
def admin_h(login_as):
    return login_as("admin")


# ---------------------------------------------------------------- access control
def test_requires_authentication(client):
    assert client.get(f"{API}/index").status_code == 401


@pytest.mark.parametrize("method,url", [
    ("get", "/index"), ("get", "/models/documents/documenttype/"), ("get", "/models/documents/documenttype/config"),
    ("post", "/models/documents/document/action"), ("get", "/timezone/stats"), ("get", "/users/1/password"),
    ("get", "/settings"),
])
def test_non_superuser_gets_403(client, login_as, method, url):
    h = login_as("teacher1")
    r = getattr(client, method)(f"{API}{url}", headers=h, **({"json": {}} if method == "post" else {}))
    assert r.status_code == 403
    assert r.json()["detail"] == "Superuser access required"


# ---------------------------------------------------------------- dashboard / config
def test_index_lists_registered_models_with_counts(client, admin_h):
    data = client.get(f"{API}/index", headers=admin_h).json()
    names = [a["name"] for a in data["apps"]]
    assert names == sorted(names, key=str.lower)
    labels = {m["label"] for a in data["apps"] for m in a["models"]}
    assert labels == set(REGISTERED)
    users = next(m for a in data["apps"] for m in a["models"] if m["label"] == "authentication.User")
    assert users["count"] > 0 and users["name"] == "Users"
    assert isinstance(data["recent_actions"], list)


def test_config_mirrors_model_admin(client, admin_h):
    cfg = client.get(f"{_path('documents.Document')}/config", headers=admin_h).json()
    assert [c["name"] for c in cfg["list_display"]] == ["document_number", "document_name", "user", "stage_status", "created_at"]
    assert cfg["list_editable"] == ["stage_status"]
    assert cfg["search_fields"] == ["document_name", "document_number"]
    assert {a["name"] for a in cfg["actions"]} == {"delete_selected", "mark_as_under_review", "mark_as_approved",
                                                  "mark_as_draft_under_revision", "mark_as_draft"}
    stage = cfg["change_form"]["fields"]["stage_status"]
    assert stage["kind"] == "choice" and [0, "Draft"] in stage["choices"]
    role = client.get(f"{_path('authentication.Role')}/config", headers=admin_h).json()
    assert role["change_form"]["inlines"][0]["label"] == "authentication.RolePermission"
    hist = client.get(f"{_path('library.DocumentHistory')}/config", headers=admin_h).json()
    assert hist["perms"] == {"add": False, "change": False, "delete": True}
    assert hist["change_form"]["view_only"] is True


def test_every_registered_model_renders(client, admin_h):
    """Read-only smoke test: config, changelist, add form, first object, delete summary, history."""
    for label in REGISTERED:
        base = _path(label)
        assert client.get(f"{base}/config", headers=admin_h).status_code == 200, label
        r = client.get(f"{base}/", headers=admin_h)
        assert r.status_code == 200, (label, r.text[:300])
        cl = r.json()
        if MODELS[label]["admin"]["perms"]["add"]:
            assert client.get(f"{base}/add", headers=admin_h).status_code == 200, label
        if cl["rows"]:
            pk = cl["rows"][0]["pk"]
            r = client.get(f"{base}/{pk}", headers=admin_h)
            assert r.status_code == 200, (label, r.text[:300])
            assert client.get(f"{base}/{pk}/history", headers=admin_h).status_code == 200, label
            if label != "authentication.User":  # user cascades are huge; covered separately
                r = client.get(f"{base}/{pk}/delete", headers=admin_h)
                assert r.status_code == 200, (label, r.text[:300])


def test_password_hash_never_exposed(client, admin_h, db):
    from app.models import User
    admin = db.query(User).filter(User.username == "admin").one()
    data = client.get(f"{_path('authentication.User')}/{admin.id}", headers=admin_h).json()
    assert "password" not in data["values"]
    assert admin.password not in json.dumps(data)
    assert admin.password.split("$")[-1] not in json.dumps(data)


# ---------------------------------------------------------------- changelist
def test_changelist_search_filter_paginate(client, admin_h, db):
    base = _path("authentication.User")
    all_ = client.get(f"{base}/", headers=admin_h).json()
    assert all_["count"] == all_["full_count"] and all_["per_page"] == 100
    found = client.get(f"{base}/", params={"q": "admin"}, headers=admin_h).json()
    assert any(r["cells"][0]["text"] == "admin" for r in found["rows"])
    assert found["count"] < found["full_count"]
    active = client.get(f"{base}/", params={"is_active__exact": "1"}, headers=admin_h).json()
    sel = next(f for f in active["filters"] if f["path"] == "is_active")
    assert next(o for o in sel["choices"] if o["label"] == "Yes")["selected"]
    assert all(r["cells"][8]["bool"] for r in active["rows"])  # 8: after the added Workspace column
    # pagination (100 / page like Django)
    logs = _path("authentication.LoginLog")
    p1 = client.get(f"{logs}/", headers=admin_h).json()
    if p1["count"] > 100:
        assert len(p1["rows"]) == 100 and p1["pages"] >= 2
        p2 = client.get(f"{logs}/", params={"p": 2}, headers=admin_h).json()
        assert p2["page"] == 2 and {r["pk"] for r in p2["rows"]}.isdisjoint({r["pk"] for r in p1["rows"]})
    # related-field search (user__username) + choices filter + date hierarchy
    r = client.get(f"{logs}/", params={"q": "admin", "status__exact": "success"}, headers=admin_h).json()
    assert all(row["cells"][2]["text"] == "Success" for row in r["rows"])
    assert r["date_hierarchy"]["field"] == "login_time"
    # ordering: sort by username descending
    o = client.get(f"{base}/", params={"o": "-0"}, headers=admin_h).json()
    names = [row["cells"][0]["text"] for row in o["rows"]]
    assert names == sorted(names, key=str.lower, reverse=True) or o["ordering"] == [{"index": 0, "desc": True}]


def test_fk_and_date_filters(client, admin_h):
    base = _path("documents.Document")
    cl = client.get(f"{base}/", headers=admin_h).json()
    dtf = next(f for f in cl["filters"] if f["path"] == "document_type")
    opt = dtf["choices"][1]
    filtered = client.get(f"{base}/", params=opt["params"], headers=admin_h).json()
    assert filtered["count"] <= cl["count"]
    roles = client.get(f"{_path('authentication.UserRole')}/", headers=admin_h).json()
    df = next(f for f in roles["filters"] if f["path"] == "assigned_at")
    year = next(o for o in df["choices"] if o["label"] == "This year")
    assert client.get(f"{_path('authentication.UserRole')}/", params=year["params"], headers=admin_h).status_code == 200


# ---------------------------------------------------------------- CRUD + LogEntry
def test_create_update_delete_category_writes_admin_log(client, admin_h, db):
    base = _path("documents.DocumentType")
    start = _max_log_id(db)
    # validation
    bad = client.post(f"{base}/add", json={"data": {"name": ""}}, headers=admin_h)
    assert bad.status_code == 400 and bad.json()["detail"]["errors"]["name"] == ["This field is required."]
    r = client.post(f"{base}/add", json={"data": {"name": "Superadmin Test Type", "is_active": True}}, headers=admin_h)
    assert r.status_code == 200, r.text
    pk = r.json()["pk"]
    assert r.json()["message"] == "The document type “Superadmin Test Type” was added successfully."
    r = client.post(f"{base}/{pk}", json={"data": {"name": "Superadmin Test Type 2", "is_active": False}, "then": "continue"},
                    headers=admin_h)
    assert r.status_code == 200, r.text
    assert r.json()["message"].endswith("You may edit it again below.")
    # unchanged save still logs "No fields changed."
    client.post(f"{base}/{pk}", json={"data": {"name": "Superadmin Test Type 2", "is_active": False}}, headers=admin_h)
    hist = client.get(f"{base}/{pk}/history", headers=admin_h).json()["entries"]
    assert [e["change_message"] for e in hist] == ["Added.", "Changed Name and Is active.", "No fields changed."]
    summary = client.get(f"{base}/{pk}/delete", headers=admin_h).json()
    assert summary["summary"]["counts"] == [{"model": "Document types", "count": 1}]
    r = client.delete(f"{base}/{pk}", headers=admin_h)
    assert r.json()["message"] == "The document type “Superadmin Test Type 2” was deleted successfully."
    assert client.get(f"{base}/{pk}", headers=admin_h).status_code == 404
    rows = _log_rows(db, start)
    assert [r["action_flag"] for r in rows] == [1, 2, 2, 3]
    assert json.loads(rows[0]["change_message"]) == [{"added": {}}]
    assert json.loads(rows[1]["change_message"]) == [{"changed": {"fields": ["Name", "Is active"]}}]
    assert rows[2]["change_message"] == "[]" and rows[3]["change_message"] == ""
    assert {r["object_id"] for r in rows} == {pk}
    assert rows[3]["object_repr"] == "Superadmin Test Type 2"
    ct = Base.metadata.tables["django_content_type"]
    assert db.execute(select(ct.c.model).where(ct.c.id == rows[0]["content_type_id"])).scalar_one() == "documenttype"
    recent = client.get(f"{API}/index", headers=admin_h).json()["recent_actions"]
    assert recent[0]["is_deletion"] and recent[0]["object_repr"] == "Superadmin Test Type 2"


def test_unique_validation(client, admin_h, db):
    base = _path("documents.Country")
    existing = client.get(f"{base}/", headers=admin_h).json()["rows"]
    if not existing:
        pytest.skip("no countries")
    name = client.get(f"{base}/{existing[0]['pk']}", headers=admin_h).json()["values"]["name"]
    r = client.post(f"{base}/add", json={"data": {"name": name, "code_name": "ZZ", "is_active": True}}, headers=admin_h)
    assert r.status_code == 400
    assert r.json()["detail"]["errors"]["name"] == ["Country with this Name already exists."]


def test_role_inline_add_and_delete(client, admin_h, db):
    base = _path("authentication.Role")
    perms = client.get(f"{base}/autocomplete", params={"field": "authentication.RolePermission:permission", "all": True},
                       headers=admin_h).json()["results"]
    assert perms
    start = _max_log_id(db)
    r = client.post(f"{base}/add", json={"data": {"name": "SA test role", "is_active": True},
                                         "inlines": {"authentication.RolePermission": [{"values": {"permission": perms[0]["value"]}}]}},
                    headers=admin_h)
    assert r.status_code == 200, r.text
    pk = r.json()["pk"]
    obj = client.get(f"{base}/{pk}", headers=admin_h).json()
    rows = obj["inlines"][0]["rows"]
    assert len(rows) == 1 and rows[0]["values"]["permission"]["value"] == perms[0]["value"]
    msg = json.loads(_log_rows(db, start)[0]["change_message"])
    assert msg[0] == {"added": {}} and msg[1]["added"]["name"] == "role permission"
    r = client.post(f"{base}/{pk}", json={"data": {"name": "SA test role", "is_active": True},
                                          "inlines": {"authentication.RolePermission": [{"pk": rows[0]["pk"], "DELETE": True}]}},
                    headers=admin_h)
    assert r.status_code == 200, r.text
    assert client.get(f"{base}/{pk}", headers=admin_h).json()["inlines"][0]["rows"] == []


# ---------------------------------------------------------------- users
def test_user_add_and_password_change(client, admin_h, db):
    from app.models import User
    base = _path("authentication.User")
    r = client.post(f"{base}/add", json={"data": {"username": "sa_new_user", "password1": "x", "password2": "y"}},
                    headers=admin_h)
    assert r.status_code == 400
    assert r.json()["detail"]["errors"]["password2"] == ["The two password fields didn’t match."]
    r = client.post(f"{base}/add", json={"data": {"username": "sa_new_user", "password1": "12345678", "password2": "12345678"}},
                    headers=admin_h)
    errs = r.json()["detail"]["errors"]["password2"]
    assert "This password is too common." in errs and "This password is entirely numeric." in errs
    r = client.post(f"{base}/add", json={"data": {"username": "sa_new_user", "password1": "Plum-Kettle-93",
                                                  "password2": "Plum-Kettle-93"}}, headers=admin_h)
    assert r.status_code == 200, r.text
    pk = r.json()["pk"]
    user = db.query(User).filter(User.id == int(pk)).one()
    assert check_password("Plum-Kettle-93", user.password)

    start = _max_log_id(db)
    r = client.post(f"{API}/users/{pk}/password", json={"password1": "Velvet-Harbor-41", "password2": "Velvet-Harbor-41"},
                    headers=admin_h)
    assert r.status_code == 200 and r.json()["message"] == "Password changed successfully."
    db.expire_all()
    user = db.query(User).filter(User.id == int(pk)).one()
    assert user.password.startswith("pbkdf2_sha256$")
    assert check_password("Velvet-Harbor-41", user.password) and not check_password("Plum-Kettle-93", user.password)
    log = _log_rows(db, start)
    assert json.loads(log[-1]["change_message"]) == [{"changed": {"fields": ["password"]}}]
    # user edit form: password summary instead of the hash
    data = client.get(f"{base}/{pk}", headers=admin_h).json()
    assert data["display"]["password"]["usable"] is True


# ---------------------------------------------------------------- actions
def test_custom_action_mark_documents_approved(client, admin_h, db):
    base = _path("documents.Document")
    rows = client.get(f"{base}/", headers=admin_h).json()["rows"][:2]
    ids = [r["pk"] for r in rows]
    r = client.post(f"{base}/action", json={"action": "mark_as_approved", "ids": ids}, headers=admin_h)
    assert r.json()["messages"] == [{"level": "info", "message": f"{len(ids)} document(s) marked as Approved."}]
    docs = Base.metadata.tables["documents_document"]
    vals = {r[0] for r in db.execute(select(docs.c.stage_status).where(docs.c.id.in_([int(i) for i in ids]))).all()}
    assert vals == {2}
    r = client.post(f"{base}/action", json={"action": "mark_as_draft", "ids": []}, headers=admin_h)
    assert "Items must be selected" in r.json()["messages"][0]["message"]
    r = client.post(f"{base}/action", json={"action": "", "ids": ids}, headers=admin_h)
    assert r.json()["messages"][0]["message"] == "No action selected."


def test_assigned_reviewer_and_sharing_actions(client, admin_h):
    for label, action, word in [("library.AssignedReviewer", "mark_as_inactive", "review(s) marked as inactive."),
                                ("documents.DocumentSharing", "extend_expiry_30_days", "share(s) extended by 30 days.")]:
        rows = client.get(f"{_path(label)}/", headers=admin_h).json()["rows"][:1]
        if not rows:
            continue
        r = client.post(f"{_path(label)}/action", json={"action": action, "ids": [rows[0]["pk"]]}, headers=admin_h)
        assert r.json()["messages"][0]["message"] == f"1 {word}"


def test_retry_failed_emails_action(client, admin_h, db, sent_emails):
    from app.models import EmailLog
    log = EmailLog(email_type="general", recipient_email="x@example.com", subject="s", message_content="m",
                   from_email="noreply@turadome.com", status="failed", retry_count=0)
    db.add(log)
    db.commit()
    r = client.post(f"{_path('documents.EmailLog')}/action", json={"action": "retry_failed_emails", "ids": [str(log.id)]},
                    headers=admin_h)
    assert r.json()["messages"][0]["message"] == "Successfully retried 1 emails."
    assert sent_emails and sent_emails[0]["to"] == "x@example.com"
    db.expire_all()
    assert db.get(EmailLog, log.id).status == "sent"


def test_delete_selected_confirmation_and_cascade(client, admin_h, db):
    from app.models import Document, DocumentType, User
    admin = db.query(User).filter(User.username == "admin").one()
    country_id = db.execute(select(Base.metadata.tables["documents_country"].c.id).limit(1)).scalar_one()
    dt = DocumentType(name="SA cascade type", is_active=1)
    db.add(dt)
    db.commit()
    doc = Document(user_id=admin.id, document_type_id=dt.id, document_name="SA cascade doc", document_number="SA-CASCADE-1",
                   country_id=country_id, stage_status=0, created_by_id=admin.id, modified_by_id=admin.id, is_active=1)
    db.add(doc)
    db.commit()
    dt_id, doc_id = dt.id, doc.id
    base = _path("documents.DocumentType")
    start = _max_log_id(db)
    r = client.post(f"{base}/action", json={"action": "delete_selected", "ids": [str(dt.id)]}, headers=admin_h).json()
    assert r["confirm"] is True
    summary = r["summary"]
    root = summary["objects"][0]
    assert root["model"] == "Document type" and root["str"] == "SA cascade type"
    assert any(ch["model"] == "Document" and ch["str"] == "SA-CASCADE-1: SA cascade doc" for ch in root["children"])
    counts = {c["model"]: c["count"] for c in summary["counts"]}
    assert counts["Document types"] == 1 and counts["Documents"] == 1
    r = client.post(f"{base}/action", json={"action": "delete_selected", "ids": [str(dt.id)], "post": True},
                    headers=admin_h).json()
    assert r["messages"][0]["message"] == "Successfully deleted 1 document type."
    db.expire_all()
    assert db.get(Document, doc_id) is None and db.get(DocumentType, dt_id) is None
    assert [x["action_flag"] for x in _log_rows(db, start)] == [3]


def test_protected_relation_blocks_delete(client, admin_h, db):
    ut = Base.metadata.tables["authentication_user"]
    used = db.execute(select(ut.c.user_type_new_id).where(ut.c.user_type_new_id.isnot(None)).limit(1)).scalar()
    if not used:
        pytest.skip("no user uses a dynamic user type")
    base = _path("authentication.UserType")
    s = client.get(f"{base}/{used}/delete", headers=admin_h).json()["summary"]
    assert s["protected"]
    r = client.delete(f"{base}/{used}", headers=admin_h)
    assert r.status_code == 400


def test_list_editable(client, admin_h, db):
    base = _path("documents.DocumentVersion")
    row = client.get(f"{base}/", headers=admin_h).json()["rows"][0]
    new = 3 if row["values"]["stage_status"] != 3 else 1
    r = client.post(f"{base}/list-edit", json={"rows": [{"pk": row["pk"], "values": {"stage_status": new}}]}, headers=admin_h)
    assert r.json()["message"] == "1 document version was changed successfully."
    hist = client.get(f"{base}/{row['pk']}/history", headers=admin_h).json()["entries"]
    assert hist[-1]["change_message"] == "Changed Stage status."


# ---------------------------------------------------------------- change file
def test_change_document_version_file(client, admin_h, db):
    from app.models import DocumentAnnotation, DocumentVersion, User
    v = db.query(DocumentVersion).first()
    u = db.query(User).filter(User.username == "admin").one()
    for i in range(2):
        db.add(DocumentAnnotation(document_version_id=v.id, user_id=u.id, annotation_type="highlight",
                                  content=f"a{i}", page_number=1, x_position=1, y_position=1, width=1, height=1,
                                  color="#FFFF00"))
    db.commit()
    url = f"{API}/documentversion/{v.id}/change-file"
    info = client.get(url, headers=admin_h).json()
    assert info["title"] == f"Change File for Version: {v.version_number}" and info["annotation_count"] >= 2
    r = client.post(url, files={"new_file": ("new.exe", io.BytesIO(b"x"))}, data={"confirm_delete_annotations": "on"},
                    headers=admin_h)
    assert r.status_code == 400 and "new_file" in r.json()["detail"]["errors"]
    r = client.post(url, files={"new_file": ("new_document.pdf", io.BytesIO(b"%PDF-1.4 new"))}, headers=admin_h)
    assert r.json()["detail"]["errors"]["confirm_delete_annotations"] == ["This field is required."]
    r = client.post(url, files={"new_file": ("new_document.pdf", io.BytesIO(b"%PDF-1.4 new"))},
                    data={"confirm_delete_annotations": "on"}, headers=admin_h)
    assert r.status_code == 200, r.text
    assert r.json()["messages"][-1]["message"].startswith(f"Successfully replaced file for version {v.version_number}.")
    db.expire_all()
    v2 = db.get(DocumentVersion, v.id)
    assert v2.file_name == "new_document.pdf" and v2.file_extension == "pdf"
    assert v2.document_file.startswith(f"documents/{v.id}/")
    assert db.query(DocumentAnnotation).filter(DocumentAnnotation.document_version_id == v.id).count() == 0


# ---------------------------------------------------------------- timezone page
def test_timezone_management(client, admin_h):
    stats = client.get(f"{API}/timezone/stats", headers=admin_h).json()
    assert stats["total_users"] > 0 and sum(s["count"] for s in stats["stats"]) <= stats["total_users"]
    assert client.get(f"{API}/timezone/timezones", params={"all": True}, headers=admin_h).json()["timezones"]
    assert client.get(f"{API}/timezone", headers=admin_h).json()["use_tz"] is True
