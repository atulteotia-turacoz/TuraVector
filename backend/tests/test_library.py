"""Library module tests — everything runs inside the rolled-back transaction from conftest."""
import datetime
import io
import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import (
    AssignedReviewer, Country, Document, DocumentHistory, DocumentNotification, DocumentType, DocumentVersion,
    EmailLog, ReferenceDocument, ReferenceZip, User, utcnow,
)


# --------------------------------------------------------------------------- fixtures
def _make_user(db, user_type="student", **kw) -> User:
    name = f"lib_{uuid.uuid4().hex[:10]}"
    u = User(password="!", is_superuser=0, username=name, is_staff=0, is_active=1, first_name=kw.get("first_name", "Test"),
             last_name=kw.get("last_name", "User"), email=f"{name}@example.com", user_type=user_type,
             is_manager=kw.get("is_manager", 0), timezone="UTC")
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def owner(db):
    return _make_user(db, "student", first_name="Olive", last_name="Owner")


@pytest.fixture()
def document(db, owner):
    dt = db.execute(select(DocumentType).limit(1)).scalar_one()
    country = db.execute(select(Country).limit(1)).scalar_one()
    doc = Document(document_name="Library Test Doc", document_number=f"DOC-T-{uuid.uuid4().hex[:8]}", stage_status=0,
                   is_active=1, country_id=country.id, created_by_id=owner.id, modified_by_id=owner.id,
                   user_id=owner.id, document_type_id=dt.id)
    db.add(doc)
    db.commit()
    for n in (1, 2):
        db.add(DocumentVersion(version_number=f"{doc.document_number}-V-{n}", version_count=n, file_name="a.docx",
                               file_extension="docx", file_title_name=f"a{n}.docx", document_file="documents/None/a.docx",
                               stage_status=0, created_by_id=owner.id, document_id=doc.id, modified_by_id=owner.id,
                               user_id=owner.id))
    db.commit()
    return doc


def _latest(db, doc):
    return db.execute(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                      .order_by(DocumentVersion.version_count.desc())).scalars().first()


# --------------------------------------------------------------------------- document library
def test_library_requires_auth(client):
    assert client.get("/api/library/documents").status_code == 401


def test_library_list_and_filters(client, login_as, document):
    h = login_as("admin")  # user_type manager → sees all active documents
    r = client.get("/api/library/documents", headers=h, params={"search": document.document_number})
    assert r.status_code == 200
    data = r.json()
    rows = data["documents"]
    assert [d["id"] for d in rows] == [document.id]
    row = rows[0]
    assert row["version_count"] == 2
    assert row["first_version_number"].endswith("-V-2")  # "Latest" is the newest version
    assert row["owner_user_type"] == "Student"
    assert data["stats"]["total_documents"] == 1 and data["stats"]["draft_documents"] == 1
    # status filter excludes it
    r = client.get("/api/library/documents", headers=h, params={"search": document.document_number, "status": "2"})
    assert r.json()["documents"] == []
    assert {"brands", "countries", "document_types", "therapeutic_areas"} <= set(data)


def test_library_student_sees_only_own(client, db, login_as, document, owner):
    other = _make_user(db, "student")
    # grant nothing: superuser-only permission check → students without the permission are redirected
    r = client.get("/api/library/documents", headers=login_as(other.username))
    assert r.status_code == 403
    assert r.json()["detail"] == "You do not have permission to access the document library."
    assert r.json()["redirect"] == "/content-lab-management/dashboard/"


# --------------------------------------------------------------------------- references
def test_reference_upload_list_detail_delete(client, db, login_as, tmp_path):
    h = login_as("admin")
    opts = client.get("/api/library/references/upload-options", headers=h).json()
    country_id = opts["countries"][0]["id"]
    assert ["primary", "Primary Reference"] in opts["reference_types"]

    # missing fields
    r = client.post("/api/library/references/upload", headers=h, data={"reference_type": "primary"})
    assert r.status_code == 400 and r.json()["detail"] == "All required fields must be filled"

    r = client.post("/api/library/references/upload", headers=h, data={
        "reference_type": "primary", "reference_subtype": "journal", "document_name": "My Ref",
        "country": str(country_id), "ref_number": "R1", "ref_year": "2021",
    }, files={"reference_file": ("my paper.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    ref = db.get(ReferenceDocument, body["id"])
    year = utcnow().year
    assert ref.reference_number == f"REF-{year}-{ref.id}"
    assert body["message"] == f"Reference uploaded successfully with number: {ref.reference_number}"
    assert ref.reference_file == "references/None/my_paper.pdf"
    assert ref.file_name == "my paper.pdf" and ref.file_extension == "pdf" and ref.ref_year == 2021
    assert ref.is_active == 1 and ref.user_id == ref.created_by_id == ref.modified_by_id
    assert (settings.media_root / ref.reference_file).is_file()

    # list + search + type filter
    lst = client.get("/api/library/references", headers=h, params={"search": ref.reference_number}).json()
    assert [x["id"] for x in lst["references"]] == [ref.id]
    assert lst["references"][0]["type_display"] == "Primary Reference"
    assert client.get("/api/library/references", headers=h,
                      params={"search": ref.reference_number, "type": "secondary"}).json()["references"] == []

    # detail + file
    det = client.get(f"/api/library/references/{ref.id}", headers=h).json()["reference"]
    assert det["subtype_display"] == "Journal Article" and det["ref_number"] == "R1"
    f = client.get(f"/api/library/references/{ref.id}/file", headers=h)
    assert f.status_code == 200 and f.content == b"%PDF-1.4 test"

    # bad ref_year → Django's error text
    r = client.post("/api/library/references/upload", headers=h, data={
        "reference_type": "primary", "reference_subtype": "journal", "document_name": "X",
        "country": str(country_id), "ref_year": "abc",
    }, files={"reference_file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")})
    assert r.status_code == 400 and r.json()["detail"].startswith("Error uploading reference: invalid literal")

    # soft delete
    r = client.delete(f"/api/library/references/{ref.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["message"] == f'Reference "{ref.reference_number}" (My Ref) has been deleted successfully.'
    db.refresh(ref)
    assert ref.is_active == 0
    assert client.get(f"/api/library/references/{ref.id}", headers=h).status_code == 404


def test_reference_file_missing_is_404(client, db, login_as):
    ref = db.execute(select(ReferenceDocument).limit(1)).scalar_one_or_none()
    if ref is None:
        pytest.skip("no references")
    # temp MEDIA_ROOT is empty → missing file must be a clean 404
    assert client.get(f"/api/library/references/{ref.id}/file", headers=login_as("admin")).status_code == 404


def test_reference_delete_permission(client, db, login_as):
    u = _make_user(db, "student")
    ref = db.execute(select(ReferenceDocument).where(ReferenceDocument.is_active == 1).limit(1)).scalar_one_or_none()
    if ref is None:
        pytest.skip("no references")
    r = client.delete(f"/api/library/references/{ref.id}", headers=login_as(u.username))
    assert r.status_code == 403
    assert r.json()["detail"] == "You do not have permission to delete references."
    db.refresh(ref)
    assert ref.is_active == 1


# --------------------------------------------------------------------------- reference ZIPs
def test_zip_upload_detail_delete(client, db, login_as, document):
    h = login_as("admin")
    versions = client.get("/api/library/reference-zips/upload-options", headers=h).json()["versions"]
    assert any(v["document_name"] == "Library Test Doc" for v in versions)  # superuser sees all active docs
    version = _latest(db, document)

    r = client.post("/api/library/reference-zips/upload", headers=h, data={"version_id": str(version.id)})
    assert r.status_code == 400 and r.json()["detail"] == "Please select a document version and ZIP file"

    r = client.post("/api/library/reference-zips/upload", headers=h, data={"version_id": "999999999"},
                    files={"zip_file": ("refs.zip", io.BytesIO(b"PK\x05\x06" + b"\0" * 18), "application/zip")})
    assert r.json()["detail"] == "Error uploading reference ZIP: No DocumentVersion matches the given query."

    r = client.post("/api/library/reference-zips/upload", headers=h, data={"version_id": str(version.id)},
                    files={"zip_file": ("refs.zip", io.BytesIO(b"PK\x05\x06" + b"\0" * 18), "application/zip")})
    assert r.status_code == 200, r.text
    z = db.get(ReferenceZip, r.json()["id"])
    admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
    assert z.reference_zip_number == f"REF-ZIP-{utcnow().year}-{z.id}"
    assert z.zip_file == f"references_zip/{admin.id}/refs.zip"
    assert z.version_number == version.version_number and z.file_extension == "zip"
    assert r.json()["redirect"] == "/content-lab-management/reference-library/"

    det = client.get(f"/api/library/reference-zips/{z.id}", headers=h).json()["ref_zip"]
    assert det["file_size"] == 22 and det["document"]["stage_status_display"] == "Draft"
    assert client.get(f"/api/library/reference-zips/{z.id}/file", headers=h).status_code == 200

    r = client.delete(f"/api/library/reference-zips/{z.id}", headers=h)
    assert r.status_code == 200
    assert r.json()["message"] == f'Reference ZIP "{z.reference_zip_number}" (refs.zip) has been deleted successfully.'
    assert db.get(ReferenceZip, z.id) is None


def test_zip_upload_denied(client, db, login_as):
    u = _make_user(db, "student")
    r = client.get("/api/library/reference-zips/upload-options", headers=login_as(u.username))
    assert r.status_code == 403 and r.json()["redirect"] == "/content-lab-management/references/"


# --------------------------------------------------------------------------- reviewers
def test_assign_reviewer_creates_rows(client, db, login_as, document, owner, sent_emails):
    h = login_as("teacher1")
    form = client.get(f"/api/library/documents/{document.id}/assign-reviewer", headers=h)
    assert form.status_code == 200, form.text
    data = form.json()
    assert data["version"]["version_number"].endswith("-V-2")  # latest by version_count
    assert all(x["user_type_title"] in ("Reviewer", "Teacher") for x in data["reviewers"])

    r = client.post(f"/api/library/documents/{document.id}/assign-reviewer", headers=h, json={"reviewer_id": ""})
    assert r.status_code == 400 and r.json()["detail"] == "Reviewer and review date are required"

    reviewer = db.execute(select(User).where(User.username == "reviewer1")).scalar_one()
    teacher = db.execute(select(User).where(User.username == "teacher1")).scalar_one()
    r = client.post(f"/api/library/documents/{document.id}/assign-reviewer", headers=h,
                    json={"reviewer_id": str(reviewer.id), "review_date": "2030-01-10", "remarks": "Look at p3"})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == f"Reviewer {reviewer.first_name} {reviewer.last_name} assigned successfully"
    assert r.json()["redirect"] == f"/content-lab-management/document/{document.id}/"

    version = _latest(db, document)
    a = db.execute(select(AssignedReviewer).where(AssignedReviewer.document_version_id == version.id)).scalar_one()
    assert a.user_id == reviewer.id and a.is_active == 1 and a.is_completed == 0 and a.remarks == "Look at p3"
    assert a.review_date == datetime.datetime(2030, 1, 9, 18, 30)  # midnight Asia/Kolkata stored as UTC

    notes = db.execute(select(DocumentNotification).where(DocumentNotification.document_id == document.id)).scalars().all()
    by_for = {n.sent_for: n for n in notes}
    assert by_for["reviewer_assignment"].receiver_id == reviewer.id
    assert by_for["reviewer_assignment"].document_type == "review_request"
    assert by_for["reviewer_assignment_owner"].receiver_id == owner.id
    assert by_for["reviewer_assignment"].sender_id == teacher.id

    log = db.execute(select(EmailLog).where(EmailLog.document_version_id == version.id)).scalar_one()
    assert log.email_type == "review_assignment" and log.status == "sent" and log.from_email == "noreply@turadome.com"
    assert log.subject == f"Document Review Assignment: {version.version_number}"
    assert sent_emails and sent_emails[0]["to"] == reviewer.email


def test_assign_reviewer_guards(client, db, login_as, document, owner):
    # students cannot assign
    r = client.get(f"/api/library/documents/{document.id}/assign-reviewer", headers=login_as(owner.username))
    assert r.status_code == 403 and r.json()["detail"] == "You do not have permission to assign reviewers"
    # approved version locks the document
    _latest(db, document).stage_status = 2
    db.commit()
    r = client.get(f"/api/library/documents/{document.id}/assign-reviewer", headers=login_as("teacher1"))
    assert r.status_code == 403 and r.json()["detail"].startswith("Cannot assign reviewer - This document has an approved")


def test_manage_toggle_complete(client, db, login_as, document, owner, sent_emails):
    reviewer = db.execute(select(User).where(User.username == "reviewer1")).scalar_one()
    admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
    version = _latest(db, document)
    a = AssignedReviewer(review_date=utcnow(), is_completed=0, is_active=1, created_by_id=admin.id,
                         document_version_id=version.id, modified_by_id=admin.id, user_id=reviewer.id, remarks="")
    db.add(a)
    db.commit()

    # manage page — teacher is not allowed, manager is
    r = client.get(f"/api/library/documents/{document.id}/manage-reviewers", headers=login_as("teacher1"))
    assert r.status_code == 403 and r.json()["detail"] == "You do not have permission to manage reviewers"
    data = client.get(f"/api/library/documents/{document.id}/manage-reviewers", headers=login_as("admin")).json()
    assert [x["id"] for x in data["assignments"]] == [a.id]

    # toggle
    r = client.post(f"/api/library/assignments/{a.id}/toggle-status", headers=login_as("teacher1"))
    assert r.status_code == 403 and r.json() == {"error": "Permission denied"}
    r = client.post(f"/api/library/assignments/{a.id}/toggle-status", headers=login_as("admin"))
    assert r.json() == {"success": True, "is_active": False, "message": "Reviewer assignment deactivated successfully"}
    db.refresh(a)
    assert a.is_active == 0
    log = db.execute(select(EmailLog).where(EmailLog.document_version_id == version.id)).scalar_one()
    assert log.subject == f"Review Assignment Deactivated: {version.version_number}"
    r = client.post(f"/api/library/assignments/{a.id}/toggle-status", headers=login_as("admin"))
    assert r.json()["is_active"] is True and r.json()["message"] == "Reviewer assignment activated successfully"

    # complete review — only the assigned reviewer
    r = client.post(f"/api/library/review/{a.id}/complete", headers=login_as("admin"), json={"approval_status": "approved"})
    assert r.status_code == 404
    sent_emails.clear()
    r = client.post(f"/api/library/review/{a.id}/complete", headers=login_as("reviewer1"),
                    json={"remarks": "Fine", "approval_status": "approved"})
    assert r.status_code == 200 and r.json() == {"message": "Review completed successfully"}
    db.refresh(a)
    db.refresh(version)
    assert a.is_completed == 1 and a.completed_at is not None and a.remarks == "Fine"
    assert version.stage_status == 2 and version.new_stage_status == 2 and version.modified_by_id == reviewer.id
    h = db.execute(select(DocumentHistory).where(DocumentHistory.document_version_id == version.id)).scalar_one()
    assert h.action_type == "approved"
    assert h.action_description == f"Document approved by {reviewer.first_name} {reviewer.last_name}. Remarks: Fine"
    assert sent_emails and sent_emails[0]["to"] == owner.email
    assert sent_emails[0]["subject"] == f"Document Review Completed: {version.version_number}"
