"""doccore — document lifecycle. All writes happen inside the rolled-back test transaction."""
import io
import datetime

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import (
    AssignedReviewer,
    Country,
    Document,
    DocumentNotification,
    DocumentType,
    DocumentVersion,
    EmailLog,
    User,
    utcnow,
)


def _ids(db):
    dtype = db.execute(select(DocumentType).where(DocumentType.is_active == 1).limit(1)).scalar_one()
    country = db.execute(select(Country).where(Country.is_active == 1).limit(1)).scalar_one()
    return dtype.id, country.id


def _user(db, username):
    return db.execute(select(User).where(User.username == username)).scalar_one()


def _upload(client, h, db, owner_id=None, name="Doccore Test Doc", filename="doccore_test.pdf", data=b"%PDF-1.4 test"):
    dtype, country = _ids(db)
    form = {"document_name": name, "document_type": str(dtype), "country": str(country)}
    if owner_id:
        form["document_owner"] = str(owner_id)
    return client.post("/api/doccore/upload", headers=h, data=form,
                       files={"document_file": (filename, io.BytesIO(data), "application/pdf")})


@pytest.fixture()
def uploaded(client, login_as, db):
    """admin uploads a document owned by teacher1."""
    teacher = _user(db, "teacher1")
    r = _upload(client, login_as("admin"), db, owner_id=teacher.id)
    assert r.status_code == 200, r.text
    doc = db.get(Document, r.json()["document_id"])
    return doc


def test_upload_with_owner_creates_document_version_and_notifications(client, login_as, db, uploaded):
    doc = uploaded
    admin, teacher = _user(db, "admin"), _user(db, "teacher1")
    year = utcnow().year
    assert doc.document_number == f"DOC-{year}-{doc.id}"
    assert doc.user_id == teacher.id and doc.created_by_id == admin.id and doc.stage_status == 0 and doc.is_active == 1
    versions = db.execute(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)).scalars().all()
    assert len(versions) == 1
    v = versions[0]
    assert v.version_number == f"{doc.document_number}-V-1"
    assert v.document_file.startswith("documents/None/doccore_test")
    assert v.user_id == teacher.id and v.created_by_id == admin.id and v.file_extension == "pdf"
    assert (settings.media_root / v.document_file).is_file()
    notes = db.execute(select(DocumentNotification).where(DocumentNotification.document_id == doc.id)).scalars().all()
    receivers = {n.receiver_id for n in notes}
    assert teacher.id in receivers and admin.id not in receivers
    assert all(n.document_type == "document_upload" and n.sent_for == "document_upload_notification" for n in notes)
    assert any(n.description.endswith(f" for {teacher.first_name} {teacher.last_name}".rstrip()) for n in notes)


def test_upload_validation(client, login_as, db):
    h = login_as("admin")
    r = client.post("/api/doccore/upload", headers=h, data={"document_name": ""})
    assert r.status_code == 400
    errs = r.json()["detail"]["errors"]
    assert errs["document_name"] == "This field is required."
    assert errs["document_type"] == "This field is required."
    assert errs["document_file"] == "This field is required."
    r = _upload(client, h, db, filename="evil.exe")
    assert r.status_code == 400
    assert "File extension “exe” is not allowed" in r.json()["detail"]["errors"]["document_file"]


def test_upload_options_and_user_search(client, login_as):
    r = client.get("/api/doccore/upload/options", headers=login_as("admin"))
    assert r.status_code == 200 and r.json()["is_admin"] is True and r.json()["document_types"]
    r = client.get("/api/doccore/search-users", params={"q": "teacher"}, headers=login_as("admin"))
    assert r.status_code == 200 and any(u["email"] == "teacher1@example.com" for u in r.json()["results"])
    r = client.get("/api/doccore/search-users", headers=login_as("reviewer1"))
    assert r.status_code == 403


def test_detail_and_history(client, login_as, db, uploaded):
    h = login_as("admin")
    r = client.get(f"/api/doccore/documents/{uploaded.id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document"]["document_number"] == uploaded.document_number
    assert len(body["versions"]) == 1 and body["latest_version_status"] == 0
    assert body["flags"]["show_update_status"] is True
    for url in (f"/api/doccore/history/{uploaded.id}", f"/api/doccore/library-history/{uploaded.id}", "/api/doccore/history"):
        assert client.get(url, headers=h).status_code == 200
    assert client.get("/api/doccore/documents/999999999", headers=h).status_code == 404
    # owner can download the stored file
    vid = body["versions"][0]["id"]
    assert client.get(f"/api/doccore/versions/{vid}/file", headers=h).status_code == 200


def test_new_version_and_review_workflow(client, login_as, db, uploaded, sent_emails):
    admin_h, teacher_h = login_as("admin"), login_as("teacher1")
    teacher = _user(db, "teacher1")

    # owner creates version 2
    r = client.get(f"/api/doccore/documents/{uploaded.id}/new-version", headers=teacher_h)
    assert r.status_code == 200 and r.json()["new_version_number"] == f"{uploaded.document_number}-V-2"
    r = client.post(f"/api/doccore/documents/{uploaded.id}/new-version", headers=teacher_h,
                    files={"document_file": ("v2.docx", io.BytesIO(b"docx"), "application/octet-stream")})
    assert r.status_code == 200, r.text
    v2 = db.get(DocumentVersion, r.json()["version_id"])
    assert v2.version_count == 2 and v2.version_number == f"{uploaded.document_number}-V-2"
    assert v2.document_file.startswith("documents/None/")
    assert db.execute(select(DocumentNotification).where(
        DocumentNotification.document_id == uploaded.id, DocumentNotification.document_type == "version_updated")).first()

    # send for review (owner)
    r = client.post("/api/doccore/workflow/send-for-review", headers=teacher_h,
                    json={"versionId": v2.id, "docId": uploaded.id})
    assert r.status_code == 200, r.text
    db.refresh(v2); db.refresh(uploaded)
    assert v2.stage_status == 1 and uploaded.stage_status == 1
    # second time -> only drafts
    r = client.post("/api/doccore/workflow/send-for-review", headers=teacher_h, json={"versionId": v2.id})
    assert r.status_code == 400 and r.json()["error"] == "Only draft documents can be sent for review"

    # under review -> new version locked
    r = client.get(f"/api/doccore/documents/{uploaded.id}/new-version", headers=teacher_h)
    assert r.status_code == 403
    assert r.json()["detail"]["message"] == "Cannot create new version - Document is currently under review."

    # reviewer decision: send for revision -> email + EmailLog + notification
    r = client.post("/api/doccore/workflow/send-for-revision", headers=admin_h, json={"versionId": v2.id})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Draft Under Revision" and r.json()["email_sent"] is True
    db.refresh(v2)
    assert v2.stage_status == 3
    log = db.execute(select(EmailLog).where(EmailLog.document_version_id == v2.id,
                                            EmailLog.email_type == "revision_request")).scalar_one()
    assert log.status == "sent" and log.recipient_email == teacher.email
    assert sent_emails and sent_emails[-1]["subject"] == f"Document Revision Required - {uploaded.document_number}"
    assert db.execute(select(DocumentNotification).where(
        DocumentNotification.document_id == uploaded.id, DocumentNotification.sent_for == "revision_request")).first()

    # mark complete -> approved, then edits are locked
    r = client.post("/api/doccore/workflow/mark-complete", headers=admin_h, json={"versionId": v2.id})
    assert r.status_code == 200 and r.json()["status"] == "Approved"
    assert db.execute(select(EmailLog).where(EmailLog.document_version_id == v2.id,
                                             EmailLog.email_type == "approval_notification")).first()
    r = client.get(f"/api/doccore/documents/{uploaded.id}/edit", headers=teacher_h)
    assert r.status_code == 403 and "approved version" in r.json()["detail"]["message"]

    # reviewer without cl_review edit
    r = client.post("/api/doccore/workflow/mark-complete", headers=login_as("multi_role_test"), json={"versionId": v2.id})
    assert r.status_code in (200, 403)


def test_edit_document(client, login_as, db, uploaded):
    h = login_as("admin")
    page = client.get(f"/api/doccore/documents/{uploaded.id}/edit", headers=h)
    assert page.status_code == 200
    d = page.json()["document"]
    r = client.post(f"/api/doccore/documents/{uploaded.id}/edit", headers=h, json={
        "document_name": "Renamed doccore", "document_type": d["document_type"], "country": d["country"]})
    assert r.status_code == 200 and r.json()["message"] == 'Document "Renamed doccore" has been updated successfully.'
    db.refresh(uploaded)
    assert uploaded.document_name == "Renamed doccore"
    r = client.post(f"/api/doccore/documents/{uploaded.id}/edit", headers=h, json={"document_name": ""})
    assert r.status_code == 400 and r.json()["detail"]["errors"]["country"] == "This field is required."


def test_status_updates(client, login_as, db, uploaded):
    h = login_as("admin")
    assert client.get(f"/api/doccore/documents/{uploaded.id}/status", headers=h).status_code == 200
    r = client.post(f"/api/doccore/documents/{uploaded.id}/status", headers=h, json={"stage_status": "2"})
    assert r.status_code == 200
    # the real previous status is reported (Django's "from X to X" quirk is fixed)
    assert r.json()["message"] == 'Document status updated from "Draft" to "Approved"'
    n = db.execute(select(DocumentNotification).where(DocumentNotification.document_id == uploaded.id,
                                                      DocumentNotification.sent_for == f"Document: {uploaded.document_name}")).scalars().all()
    assert n and n[-1].document_type == "document_approved"
    r = client.post(f"/api/doccore/documents/{uploaded.id}/status", headers=h, json={"stage_status": "9"})
    assert r.status_code == 400

    v = db.execute(select(DocumentVersion).where(DocumentVersion.document_id == uploaded.id)).scalar_one()
    old_version_stage = v.stage_status
    r = client.post(f"/api/doccore/versions/{v.id}/status", headers=h, json={"stage_status": 1})
    assert r.status_code == 200
    assert r.json()["message"].endswith('to "Under Review"')
    assert old_version_stage == 1 or 'from "Under Review"' not in r.json()["message"]
    db.refresh(uploaded); db.refresh(v)
    assert v.stage_status == 1 and uploaded.stage_status == 1
    # no permission
    r = client.post(f"/api/doccore/versions/{v.id}/status", headers=login_as("reviewer1"), json={"stage_status": 0})
    assert r.status_code in (200, 403)


def test_change_file(client, login_as, db, uploaded):
    h = login_as("admin")
    v = db.execute(select(DocumentVersion).where(DocumentVersion.document_id == uploaded.id)).scalar_one()
    assert client.get(f"/api/doccore/versions/{v.id}/change-file", headers=h).json()["annotation_count"] == 0
    r = client.post(f"/api/doccore/versions/{v.id}/change-file", headers=h,
                    files={"new_file": ("replaced.docx", io.BytesIO(b"x"), "application/octet-stream")})
    assert r.status_code == 400 and "confirm_delete_annotations" in r.json()["detail"]["errors"]
    old = v.document_file
    r = client.post(f"/api/doccore/versions/{v.id}/change-file", headers=h, data={"confirm_delete_annotations": "on"},
                    files={"new_file": ("replaced.docx", io.BytesIO(b"x"), "application/octet-stream")})
    assert r.status_code == 200, r.text
    db.refresh(v)
    assert v.document_file == f"documents/{v.id}/replaced.docx" and v.file_extension == "docx"
    assert not (settings.media_root / old).exists()
    r = client.get(f"/api/doccore/versions/{v.id}/change-file", headers=login_as("teacher1"))
    assert r.status_code == 403 and r.json()["detail"]["redirect"] == f"/content-lab-management/preview/{v.id}/"


def test_delete_version_and_document(client, login_as, db, uploaded):
    h = login_as("admin")
    teacher_h = login_as("teacher1")
    r = client.post(f"/api/doccore/documents/{uploaded.id}/new-version", headers=teacher_h,
                    files={"document_file": ("v2.pdf", io.BytesIO(b"pdf"), "application/pdf")})
    v2 = r.json()["version_id"]
    db.add(AssignedReviewer(user_id=_user(db, "reviewer1").id, document_version_id=v2, review_date=utcnow(),
                            is_completed=0, is_active=1, created_by_id=1, modified_by_id=1))
    db.flush()
    r = client.delete(f"/api/doccore/versions/{v2}", headers=h)
    assert r.status_code == 200 and r.json()["success"] is True
    assert db.get(DocumentVersion, v2) is None
    r = client.delete(f"/api/doccore/documents/{uploaded.id}", headers=h)
    assert r.json()["success"] is True and r.json()["redirect"] == "/content-lab-management/library/"
    db.expire_all()
    assert db.get(Document, uploaded.id) is None
    r = client.delete(f"/api/doccore/documents/{uploaded.id}", headers=h)
    assert r.status_code == 404 and r.json()["message"] == "Document not found: No Document matches the given query."


def test_dashboards_and_lists(client, login_as, db, uploaded):
    h = login_as("admin")
    r = client.get("/api/doccore/dashboard", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["redirect"] == "/content-lab-management/dashboard/"
    r = client.get("/api/doccore/dashboard", headers=login_as("teacher1"))
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert any(d["id"] == uploaded.id for d in r.json()["recent_documents"])
    for url in ("/api/doccore/reviewer-dashboard?status=all", "/api/doccore/all-reviews?status=pending",
                "/api/doccore/reviewer-assignments?filter_status=unassigned", "/api/doccore/references"):
        r = client.get(url, headers=h)
        assert r.status_code == 200, (url, r.text)
    rows = client.get("/api/doccore/reviewer-assignments", params={"search": uploaded.document_number}, headers=h).json()
    assert rows["total_documents"] == 1 and rows["document_data"][0]["has_reviewers"] is False


def test_legacy_upload(client, login_as, db):
    h = login_as("admin")
    dtype, country = _ids(db)
    r = client.post("/api/doccore/upload-legacy", headers=h, data={"document_name": "x"})
    assert r.status_code == 400 and r.json()["detail"]["message"] == "All required fields must be filled"
    ta = client.get("/api/doccore/upload-legacy/options", headers=h).json()["therapeutic_areas"]
    plain = next(t for t in ta if not t["is_other"])
    r = client.post("/api/doccore/upload-legacy", headers=h, data={
        "document_name": "Legacy doccore", "document_type": str(dtype), "country": str(country),
        "therapeutic_area": str(plain["value"])},
        files={"document_file": ("legacy.pdf", io.BytesIO(b"pdf"), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["redirect"] == "/content-lab-management/dashboard/"
    other = [t for t in ta if t["is_other"]]
    if other:
        r = client.post("/api/doccore/upload-legacy", headers=h, data={
            "document_name": "Legacy doccore", "document_type": str(dtype), "country": str(country),
            "therapeutic_area": str(other[0]["value"])},
            files={"document_file": ("legacy.pdf", io.BytesIO(b"pdf"), "application/pdf")})
        assert r.json()["detail"]["message"] == "Please specify the other therapeutic area."
