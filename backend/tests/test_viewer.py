"""Viewer module tests — run inside the rolled-back transaction with a temp MEDIA_ROOT.

Every row created here (documents, versions, annotations, AnnotationActivity,
links, notifications, email logs) disappears when the test ends; annotation /
comment files are written to the temporary MEDIA_ROOT only.
"""
import os
import uuid

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import (
    AnnotationActivity,
    AssignedReviewer,
    Document,
    DocumentAnnotation,
    DocumentNotification,
    DocumentVersion,
    DocumentVersionReference,
    EmailLog,
    ReferenceDocument,
    User,
    utcnow,
)


def _user(db, username):
    return db.query(User).filter(User.username == username).one()


@pytest.fixture()
def make_version(db):
    def _make(owner, stage=0, file_rel="documents/None/viewer_test.pdf", ext="pdf"):
        doc = Document(document_name="Viewer test doc", document_number=f"DOC-VIEWER-{uuid.uuid4().hex[:10]}",
                       stage_status=stage, is_active=1, country_id=1, document_type_id=1,
                       created_by_id=owner.id, modified_by_id=owner.id, user_id=owner.id)
        db.add(doc)
        db.flush()
        version = DocumentVersion(document_id=doc.id, version_number=f"{doc.document_number}-V-1", version_count=1,
                                  file_name=os.path.basename(file_rel or "x.pdf"), file_extension=ext,
                                  file_title_name="Viewer test", document_file=file_rel or "", stage_status=stage,
                                  user_id=owner.id, created_by_id=owner.id, modified_by_id=owner.id)
        db.add(version)
        db.flush()
        return version
    return _make


@pytest.fixture()
def make_reference(db):
    def _make(owner):
        ref = ReferenceDocument(reference_number=f"REF-VIEWER-{uuid.uuid4().hex[:10]}", type="primary",
                                subtype="journal", document_name="Viewer ref", file_name="r.pdf", file_extension="pdf",
                                file_title_name="Viewer ref", reference_file="references/None/viewer_ref.pdf",
                                is_active=1, country_id=1, user_id=owner.id, created_by_id=owner.id,
                                modified_by_id=owner.id)
        db.add(ref)
        db.flush()
        return ref
    return _make


def _write_media(rel: str, data: bytes = b"%PDF-1.4 test") -> None:
    path = os.path.join(settings.MEDIA_ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# ------------------------------------------------------------------ files
def test_file_endpoint_404_when_missing_and_serves_when_present(client, db, login_as, make_version):
    owner = _user(db, "testuser")
    version = make_version(owner)
    h = login_as("testuser")
    r = client.get(f"/api/viewer/versions/{version.id}/file", headers=h)
    assert r.status_code == 404
    assert "missing on the server" in r.json()["detail"]
    assert client.get(f"/api/viewer/versions/{version.id}/file").status_code == 401

    _write_media(version.document_file)
    r = client.get(f"/api/viewer/versions/{version.id}/file", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert r.headers["content-type"] == "application/pdf"
    assert client.head(f"/api/viewer/versions/{version.id}/file", headers=h).status_code == 200
    # token in the query string works too (WebViewer / downloads)
    token = h["Authorization"].split()[1]
    r = client.get(f"/api/viewer/versions/{version.id}/file?download=1&token={token}")
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment")

    assert client.get("/api/viewer/versions/999999999/file", headers=h).status_code == 404


def test_reference_file_404(client, db, login_as, make_reference):
    ref = make_reference(_user(db, "testuser"))
    r = client.get(f"/api/viewer/references/{ref.id}/file", headers=login_as("testuser"))
    assert r.status_code == 404


# ------------------------------------------------------------------ preview permissions
def test_preview_permissions_and_notification(client, db, login_as, make_version):
    owner = _user(db, "testuser")
    version = make_version(owner)
    note = DocumentNotification(receiver_id=owner.id, sender_id=1, document_type="review_request",
                                document_id=version.document_id, description="x", sent_for="review", is_seen=0)
    db.add(note)
    db.flush()

    r = client.get(f"/api/viewer/versions/{version.id}/preview?noti_id={note.id}", headers=login_as("testuser"))
    assert r.status_code == 200
    body = r.json()
    assert body["version"]["id"] == version.id and body["document"]["id"] == version.document_id
    assert body["version"]["file_exists"] is False
    db.refresh(note)
    assert note.is_seen == 1

    # another student without cl_documents/view is bounced to the library, as in Django
    r = client.get(f"/api/viewer/versions/{version.id}/preview", headers=login_as("atul_kumar"))
    assert r.status_code == 403
    assert r.json() == {"detail": "You do not have permission to view this document", "redirect": "/content-lab-management/library/",
                        "level": "error"}
    assert client.get(f"/api/viewer/versions/{version.id}/preview", headers=login_as("admin")).status_code == 200


# ------------------------------------------------------------------ DocumentAnnotation CRUD
def test_annotation_crud(client, db, login_as, make_version):
    owner = _user(db, "testuser")
    version = make_version(owner)
    h = login_as("testuser")

    r = client.post(f"/api/viewer/annotations/{version.id}/create", headers=h,
                    json={"type": "highlight", "content": "Note A", "page": 2, "x": 10.5, "y": 20, "width": 5})
    assert r.status_code == 201
    ann_id = r.json()["id"]
    row = db.get(DocumentAnnotation, ann_id)
    assert row.annotation_type == "highlight" and row.page_number == 2 and row.color == "#FFFF00"

    listed = client.get(f"/api/viewer/annotations/{version.id}", headers=h).json()["annotations"]
    assert listed[0]["id"] == ann_id and listed[0]["x"] == 10.5 and listed[0]["content"] == "Note A"

    # a different student is neither owner nor authorised
    other = login_as("atul_kumar")
    assert client.post(f"/api/viewer/annotations/{version.id}/create", headers=other, json={}).json() == \
        {"error": "Permission denied"}
    assert client.delete(f"/api/viewer/annotations/{ann_id}/delete", headers=other).status_code == 403
    # reviewers are authorised
    assert client.get(f"/api/viewer/annotations/{version.id}", headers=login_as("reviewer1")).status_code == 200

    r = client.delete(f"/api/viewer/annotations/{ann_id}/delete", headers=h)
    assert r.json() == {"message": "Annotation deleted successfully"}
    assert db.get(DocumentAnnotation, ann_id) is None
    # Django turned the 404 inside try/except into a 500
    assert client.delete(f"/api/viewer/annotations/{ann_id}/delete", headers=h).status_code == 500


def test_bulk_create_replaces_only_own_annotations(client, db, login_as, make_version):
    owner = _user(db, "testuser")
    version = make_version(owner)
    teacher = _user(db, "teacher1")
    db.add(DocumentAnnotation(document_version_id=version.id, user_id=teacher.id, annotation_type="note",
                              content="teacher", page_number=1, x_position=0, y_position=0, width=0, height=0,
                              color="#FFFF00"))
    db.flush()
    h = login_as("testuser")
    assert client.post(f"/api/viewer/annotations/{version.id}/bulk-create", headers=h,
                       json={"annotations": []}).status_code == 400
    for n in (3, 2):
        r = client.post(f"/api/viewer/annotations/{version.id}/bulk-create", headers=h,
                        json={"annotations": [{"content": f"c{i}"} for i in range(n)]})
        assert r.status_code == 201 and r.json()["count"] == n
    count = lambda uid: db.scalar(select(func.count()).select_from(DocumentAnnotation).where(  # noqa: E731
        DocumentAnnotation.document_version_id == version.id, DocumentAnnotation.user_id == uid))
    assert count(owner.id) == 2 and count(teacher.id) == 1


# ------------------------------------------------------------------ XFDF save / load + AnnotationActivity
XFDF_ONE = ('<?xml version="1.0" encoding="UTF-8" ?><xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve">'
            '<annots><square page="0" rect="1,2,3,4" name="a1" title="Test User"><contents>hi</contents></square>'
            '</annots></xfdf>')


def _activities(db, version_id):
    return db.execute(select(AnnotationActivity).where(AnnotationActivity.document_version_id == version_id)
                      .order_by(AnnotationActivity.id)).scalars().all()


def test_save_xfdf_writes_file_and_logs_activity_like_django(client, db, login_as, make_version):
    total_before = db.scalar(select(func.count()).select_from(AnnotationActivity))
    owner = _user(db, "testuser")
    version = make_version(owner, stage=1)  # saving is allowed even while under review
    h = login_as("testuser")

    r = client.post(f"/api/viewer/annotations/{version.id}/save-xfdf", headers=h, json={"xfdfData": XFDF_ONE})
    assert r.status_code == 200
    assert r.json() == {"message": "XFDF annotations saved successfully",
                        "file": f"annotations_{version.id}_{owner.id}.xfdf", "annotations_count": len(XFDF_ONE)}
    path = os.path.join(settings.MEDIA_ROOT, "annotations", f"annotations_{version.id}_{owner.id}.xfdf")
    assert open(path, encoding="utf-8").read() == XFDF_ONE

    acts = _activities(db, version.id)
    # Django counted occurrences of '<annot' (so '<annots>' counts, '<square' does not)
    assert [(a.action, a.annotation_count, a.description) for a in acts] == [("modified", 1, "1 annotation")]

    # a second save within 30 s does not add a row, only refreshes the description
    two = XFDF_ONE.replace("<annots>", "<annots><annots/>")
    client.post(f"/api/viewer/annotations/{version.id}/save-xfdf", headers=h, json={"xfdfData": two})
    acts = _activities(db, version.id)
    assert len(acts) == 1 and acts[0].description == "2 annotations" and acts[0].annotation_count == 1

    # clearing logs a separate 'deleted' activity and writes the empty XFDF skeleton
    client.post(f"/api/viewer/annotations/{version.id}/save-xfdf", headers=h, json={"xfdfData": ""})
    acts = _activities(db, version.id)
    assert [(a.action, a.description, a.annotation_count) for a in acts][-1] == ("deleted", "Annotations cleared", 0)
    assert "<xfdf" in open(path, encoding="utf-8").read()

    activities = client.get(f"/api/viewer/annotations/{version.id}/activities", headers=h).json()["activities"]
    assert activities[0]["user"] == (f"{owner.first_name} {owner.last_name}".strip() or owner.username)
    assert {a["action"] for a in activities} == {"modified", "deleted"}
    assert activities[0]["relative_time"] == "Just now"
    assert client.get(f"/api/viewer/annotations/{version.id}/activities",
                      headers=login_as("atul_kumar")).status_code == 403

    # only our own rows were added; existing production activity rows are untouched
    assert db.scalar(select(func.count()).select_from(AnnotationActivity)) == total_before + 2


def test_get_xfdf_merging_and_reviewer_remarks(client, db, login_as, make_version):
    owner = _user(db, "testuser")
    teacher = _user(db, "teacher1")
    version = make_version(owner)
    client.post(f"/api/viewer/annotations/{version.id}/save-xfdf", headers=login_as("testuser"),
                json={"xfdfData": XFDF_ONE})
    client.post(f"/api/viewer/annotations/{version.id}/save-xfdf", headers=login_as("teacher1"),
                json={"xfdfData": XFDF_ONE.replace('name="a1"', 'name="t1"')})
    db.add(AssignedReviewer(user_id=_user(db, "reviewer1").id, document_version_id=version.id, review_date=utcnow(),
                            remarks="Please fix section 2", is_completed=1, is_active=1,
                            created_by_id=1, modified_by_id=1))
    db.flush()

    # privileged user: all files merged, author names appended, no reviewer sticky notes
    r = client.get(f"/api/viewer/annotations/{version.id}/xfdf", headers=login_as("admin"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.adobe.xfdf")
    assert 'name="a1"' in r.text and 'name="t1"' in r.text
    assert "Please fix section 2" not in r.text

    # student owner: >1 files -> collaborative merge + reviewer remarks as sticky notes
    r = client.get(f"/api/viewer/annotations/{version.id}/xfdf", headers=login_as("testuser"))
    assert 'name="t1"' in r.text and "Please fix section 2" in r.text and "Reviewer Comment" in r.text

    # unknown version -> empty XFDF with 200, like Django
    r = client.get("/api/viewer/annotations/999999999/xfdf", headers=login_as("testuser"))
    assert r.status_code == 200 and r.text.startswith("<?xml")


# ------------------------------------------------------------------ OnlyOffice comment sync
def test_onlyoffice_comment_sync_roundtrip(client, db, login_as, make_version):
    owner = _user(db, "testuser")
    version = make_version(owner)
    teacher_h = login_as("teacher1")
    teacher = _user(db, "teacher1")
    comments = [{"text": "From editor", "author": "T", "page": 0, "x": 100, "y": 100, "date": "2025"}]

    r = client.post(f"/api/viewer/comments/{version.id}/onlyoffice/save", headers=teacher_h, json={"comments": comments})
    assert r.json() == {"message": "OnlyOffice comments saved and synced to PDFTron", "comments_count": 1}
    assert client.get(f"/api/viewer/comments/{version.id}/onlyoffice", headers=teacher_h).json()["comments"] == comments
    for uid in (teacher.id, owner.id):  # synced into both the commenter's and the owner's XFDF
        text = open(os.path.join(settings.MEDIA_ROOT, "annotations", f"annotations_{version.id}_{uid}.xfdf")).read()
        assert "onlyoffice_comment_0" in text and "From editor" in text

    # sync-to-onlyoffice skips OnlyOffice-originated annotations
    assert client.post(f"/api/viewer/comments/{version.id}/sync-to-onlyoffice", headers=teacher_h).json() == {"comments": []}
    debug = client.get(f"/api/viewer/comments/{version.id}/debug", headers=teacher_h).json()
    assert debug["onlyoffice_count"] == 1 and debug["file_paths"]["xfdf_exists"] is True

    r = client.post(f"/api/viewer/comments/{version.id}/restore", headers=teacher_h)
    assert r.status_code == 200
    text = open(os.path.join(settings.MEDIA_ROOT, "annotations", f"annotations_{version.id}_{teacher.id}.xfdf")).read()
    assert "onlyoffice_comment_0" not in text

    # students other than the owner are refused; owners under review cannot save comments
    assert client.get(f"/api/viewer/comments/{version.id}/onlyoffice", headers=login_as("atul_kumar")).status_code == 403
    version.stage_status = 1
    db.flush()
    r = client.post(f"/api/viewer/comments/{version.id}/onlyoffice/save", headers=login_as("testuser"),
                    json={"comments": []})
    assert r.status_code == 403 and r.json()["error"] == "Cannot save comments - Document is under review"


# ------------------------------------------------------------------ reference linking
def test_link_and_unlink_references(client, db, login_as, make_version, make_reference):
    owner = _user(db, "testuser")
    version = make_version(owner)
    ref = make_reference(owner)
    h = login_as("testuser")

    page = client.get(f"/api/viewer/versions/{version.id}/link-references", headers=h).json()
    assert ref.id in [r["id"] for r in page["available_references"]] and page["linked_references"] == []

    r = client.post(f"/api/viewer/versions/{version.id}/link-references", headers=h,
                    json={"reference_ids": [ref.id, 999999999], "notes": "why"})
    body = r.json()
    assert body["linked_count"] == 1
    assert body["message"] == "Successfully linked 1 reference(s) to the document version."
    assert body["errors"] == ["Error linking reference 999999999: No ReferenceDocument matches the given query."]
    assert body["redirect"] == f"/content-lab-management/document/{version.document_id}/history/"
    link = db.execute(select(DocumentVersionReference).where(
        DocumentVersionReference.document_version_id == version.id)).scalar_one()
    assert link.is_active == 1 and link.notes == "why" and link.linked_by_id == owner.id

    page = client.get(f"/api/viewer/versions/{version.id}/link-references", headers=h).json()
    assert ref.id not in [r["id"] for r in page["available_references"]]
    assert page["linked_references"][0]["reference"]["id"] == ref.id
    preview = client.get(f"/api/viewer/versions/{version.id}/preview", headers=h).json()
    assert [r["id"] for r in preview["references"]] == [ref.id]

    # linking again creates nothing
    assert client.post(f"/api/viewer/versions/{version.id}/link-references", headers=h,
                       json={"reference_ids": [ref.id]}).json()["linked_count"] == 0

    r = client.post(f"/api/viewer/versions/{version.id}/unlink-reference/{ref.id}", headers=h)
    assert r.json()["message"] == "Reference unlinked successfully."
    db.refresh(link)
    assert link.is_active == 0
    r = client.post(f"/api/viewer/versions/{version.id}/unlink-reference/{ref.id}", headers=h)
    assert r.json()["level"] == "error"

    # Django get_or_create: re-linking an unlinked reference leaves the inactive row as it is
    assert client.post(f"/api/viewer/versions/{version.id}/link-references", headers=h,
                       json={"reference_ids": [ref.id]}).json()["linked_count"] == 0
    db.refresh(link)
    assert link.is_active == 0

    # only the document owner or a superuser may manage links
    other = login_as("teacher1")
    assert client.get(f"/api/viewer/versions/{version.id}/link-references", headers=other).status_code == 403
    assert client.post(f"/api/viewer/versions/{version.id}/unlink-reference/{ref.id}", headers=other).status_code == 403
    assert client.get(f"/api/viewer/versions/{version.id}/link-references", headers=login_as("admin")).status_code == 200


def test_reference_preview_permissions(client, db, login_as, make_reference):
    ref = make_reference(_user(db, "testuser"))
    assert client.get(f"/api/viewer/references/{ref.id}/preview", headers=login_as("testuser")).status_code == 200
    assert client.get(f"/api/viewer/references/{ref.id}/preview", headers=login_as("teacher1")).status_code == 200
    r = client.get(f"/api/viewer/references/{ref.id}/preview", headers=login_as("atul_kumar"))
    assert r.status_code == 403 and r.json()["redirect"] == "/content-lab-management/reference-library/"
    r = client.post("/api/viewer/get-file-name", headers=login_as("testuser"), json={"refId": ref.id})
    assert r.json() == {"file_name": "r.pdf"}


# ------------------------------------------------------------------ review page
def test_review_start_and_submit(client, db, login_as, make_version, sent_emails):
    owner = _user(db, "testuser")
    reviewer = _user(db, "reviewer1")
    version = make_version(owner, stage=1)
    assignment = AssignedReviewer(user_id=reviewer.id, document_version_id=version.id, review_date=utcnow(),
                                  is_completed=0, is_active=1, created_by_id=1, modified_by_id=1)
    db.add(assignment)
    db.flush()
    h = login_as("reviewer1")

    assert client.get("/api/viewer/review", headers=h).json()["redirect"] == "/content-lab-management/dashboard/"
    r = client.get(f"/api/viewer/review?id={version.id}", headers=login_as("teacher1"))
    assert r.status_code == 403 and r.json()["detail"] == "You are not assigned to review this document."

    r = client.get(f"/api/viewer/review?id={version.id}", headers=h)
    assert r.status_code == 200
    db.refresh(assignment)
    assert assignment.started_at is not None
    started = db.execute(select(DocumentNotification).where(
        DocumentNotification.document_id == version.document_id,
        DocumentNotification.sent_for == "review_started")).scalars().all()
    assert len(started) == 1 and started[0].receiver_id == owner.id
    logs = db.execute(select(EmailLog).where(EmailLog.document_version_id == version.id)).scalars().all()
    assert [l.email_type for l in logs] == ["review_started"]
    # second open does not repeat the side effects
    client.get(f"/api/viewer/review?id={version.id}", headers=h)
    assert db.scalar(select(func.count()).select_from(EmailLog).where(EmailLog.document_version_id == version.id)) == 1

    r = client.post(f"/api/viewer/review?id={version.id}", headers=h, json={"comments": "  ", "decision": "approved"})
    assert r.status_code == 400 and r.json()["detail"] == "Please enter review comments."
    r = client.post(f"/api/viewer/review?id={version.id}", headers=h, json={"comments": "ok"})
    assert r.json()["detail"] == "Please select a review decision."

    r = client.post(f"/api/viewer/review?id={version.id}", headers=h, json={"comments": "Looks good", "decision": "approved"})
    assert r.status_code == 200
    assert r.json()["message"] == "Review submitted successfully. Document has been approved."
    db.refresh(assignment)
    db.refresh(version)
    assert assignment.is_completed == 1 and assignment.remarks == "Looks good" and assignment.modified_by_id == reviewer.id
    assert version.stage_status == 2 and version.document.stage_status == 2
    types = [l.email_type for l in db.execute(select(EmailLog).where(EmailLog.document_version_id == version.id)
                                               .order_by(EmailLog.id)).scalars()]
    assert types[:2] == ["review_started", "approval_notification"] and set(types[2:]) == {"general"}
    assert any(e["subject"].startswith("✅ Document Approved") for e in sent_emails)


# ------------------------------------------------------------------ editor + OnlyOffice
def test_editor_redirect_rules(client, db, login_as, make_version, monkeypatch):
    owner = _user(db, "testuser")
    version = make_version(owner, stage=1)
    h = login_as("testuser")
    r = client.get(f"/api/viewer/editor/{version.id}", headers=h).json()
    assert r["message"] == "Cannot edit document - This document is under review."
    version.stage_status = 0
    db.flush()
    monkeypatch.setattr(settings, "ENABLE_ONLYOFFICE_EDITOR", False)
    assert client.get(f"/api/viewer/editor/{version.id}", headers=h).json()["level"] == "warning"
    monkeypatch.setattr(settings, "ENABLE_ONLYOFFICE_EDITOR", True)
    assert client.get(f"/api/viewer/editor/{version.id}", headers=h).json()["redirect"] == \
        f"/content-lab-management/onlyoffice/edit/?id={version.id}"
    version.stage_status = 2
    db.flush()
    assert "approved version" in client.get(f"/api/viewer/editor/{version.id}", headers=h).json()["message"]


def test_onlyoffice_config_and_unauthenticated_callbacks(client, db, login_as, make_version):
    import jwt as pyjwt

    owner = _user(db, "testuser")
    version = make_version(owner, file_rel="documents/None/viewer_test.docx", ext="docx")
    r = client.get(f"/api/viewer/onlyoffice/edit-config?id={version.id}", headers=login_as("testuser"))
    cfg = r.json()["config"]
    assert cfg["document"]["fileType"] == "docx"
    assert cfg["editorConfig"]["callbackUrl"].endswith(f"/api/viewer/onlyoffice/callback/?version_id={version.id}")
    claims = pyjwt.decode(cfg["token"], "6YdcN44m5WTLvDjreLSmn8ICZv5kiWo1", algorithms=["HS256"])
    assert claims["document"]["key"] == cfg["document"]["key"]
    assert client.get("/api/viewer/onlyoffice/edit-config").status_code == 400
    # like Django, the edit view works without login
    assert client.get(f"/api/viewer/onlyoffice/edit-config?id={version.id}").json()["config"]["editorConfig"]["user"]["id"] == "anonymous"

    assert client.get("/api/viewer/onlyoffice/callback/").json() == {"error": 0, "message": "Callback endpoint ready"}
    assert client.post("/api/viewer/onlyoffice/callback/", json={"status": 1}).json() == \
        {"error": 1, "message": "No version_id provided"}
    assert client.post(f"/api/viewer/onlyoffice/callback/?version_id={version.id}", json={"status": 1}).json() == {"error": 0}
    assert client.post(f"/api/viewer/onlyoffice/callback/?version_id={version.id}", content=b"nope").json() == \
        {"error": 1, "message": "Invalid JSON"}
    assert client.post(f"/api/viewer/onlyoffice/callback/{version.id}/", json={"status": 4}).json() == {"error": 0}


def test_office365_open_missing_file(client, db, login_as, make_version):
    version = make_version(_user(db, "testuser"))
    for prefix in ("/api/viewer/office365", "/api/office365"):
        r = client.post(f"{prefix}/open/{version.id}", headers=login_as("testuser"))
        assert r.status_code == 404 and "File not found" in r.json()["error"]
    r = client.post(f"/api/office365/sync/{version.id}", headers=login_as("testuser"), json={})
    assert r.status_code == 400 and r.json() == {"error": "item_id is required."}
