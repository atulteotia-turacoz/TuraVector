"""Projects module tests — run inside the rolled-back transaction from conftest."""
import io
import json

import pytest
from sqlalchemy import select

from app.models import (
    DocumentNotification,
    DocumentSharing,
    DocumentVersion,
    DocumentVersionSharing,
    ProjectAuthor,
    ProjectMilestone,
    ResearchProject,
    ResearchProjectCollaborator,
    ResearchProjectDocument,
    ResearchProjectTask,
    User,
)

BASE = {
    "project_type": "manuscript", "client_type": "internal", "title": "Pytest Project",
    "status": "planning", "therapeutic_area": "oncology", "priority": "medium",
    "description": "A test project about things", "keywords": "alpha, beta, ,gamma",
}


def _user(db, username):
    return db.execute(select(User).where(User.username == username)).scalar_one()


def _create(client, h, **extra):
    r = client.post("/api/projects", json={**BASE, **extra}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- CRUD + authors
def test_create_project_with_authors(client, login_as, db):
    h = login_as("teacher1")
    r = client.post("/api/projects", json={**BASE, "status": "active", "has_authors": True, "authors": [
        {"name": "Ann Author", "affiliation": "Uni", "email": "ann@example.com", "author_type": "corresponding"},
        {"name": "", "affiliation": "", "email": "", "author_type": "other"},  # untouched extra form
    ]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["message"] == 'Project "Pytest Project" created successfully!'
    pid = r.json()["id"]
    p = db.get(ResearchProject, pid)
    assert p.status == "planning"  # forced on create
    assert p.owner_id == _user(db, "teacher1").id
    authors = db.execute(select(ProjectAuthor).where(ProjectAuthor.project_id == pid)).scalars().all()
    assert [a.email for a in authors] == ["ann@example.com"]

    d = client.get(f"/api/projects/{pid}", headers=h).json()
    assert d["keywords_list"] == ["alpha", "beta", "gamma"]
    assert d["is_owner"] and d["progress_percentage"] == 0
    assert d["authors"][0]["author_type"] == "corresponding"

    lst = client.get("/api/projects", params={"search": "Pytest"}, headers=h).json()
    assert any(i["id"] == pid for i in lst["items"])
    assert lst["start_index"] == 1


def test_invalid_author_formset_is_silently_skipped(client, login_as, db):
    h = login_as("teacher1")
    pid = _create(client, h, has_authors=True, authors=[{"name": "No Email", "affiliation": "X", "email": "bad"}])
    p = db.get(ResearchProject, pid)
    assert p is not None
    assert db.execute(select(ProjectAuthor).where(ProjectAuthor.project_id == pid)).first() is None


def test_project_validation_messages(client, login_as):
    h = login_as("teacher1")
    r = client.post("/api/projects", json={**BASE, "title": "", "project_type": "other",
                                           "client_poc_email": "nope", "budget": "123456789.123"}, headers=h)
    assert r.status_code == 400
    d = r.json()["detail"]
    assert d["message"] == "Please correct the errors in the form."
    assert d["errors"]["title"] == ["This field is required."]
    assert d["errors"]["client_poc_email"] == ["Enter a valid email address."]
    assert "budget" in d["errors"]
    assert d["non_field_errors"] == ["Please specify the project type when 'Other' is selected."]


def test_edit_and_delete_project_owner_only(client, login_as, db):
    owner = login_as("teacher1")
    pid = _create(client, owner, has_authors=True,
                  authors=[{"name": "A", "affiliation": "U", "email": "a@example.com", "author_type": "other"}])
    author = db.execute(select(ProjectAuthor).where(ProjectAuthor.project_id == pid)).scalar_one()

    other = login_as("reviewer1")
    r = client.put(f"/api/projects/{pid}", json=BASE, headers=other)
    assert r.status_code == 403 and r.json()["detail"] == "Only the project owner can edit this project."
    assert client.get(f"/api/projects/{pid}", headers=other).json()["detail"] == \
        "You do not have permission to view this project."

    form = client.get(f"/api/projects/{pid}/edit", headers=owner).json()
    assert form["authors"][0]["id"] == author.id
    r = client.put(f"/api/projects/{pid}", json={**BASE, "title": "Renamed", "status": "on_hold", "has_authors": True,
                                                 "actual_end_date": "2025-02-03", "authors": [
                                                     {"id": author.id, "DELETE": True},
                                                     {"name": "B", "affiliation": "U2", "email": "b@example.com"}]},
                   headers=owner)
    assert r.status_code == 200, r.text
    db.expire_all()
    p = db.get(ResearchProject, pid)
    assert p.title == "Renamed" and p.status == "on_hold" and str(p.actual_end_date) == "2025-02-03"
    assert [a.email for a in db.execute(select(ProjectAuthor).where(ProjectAuthor.project_id == pid)).scalars()] == \
        ["b@example.com"]

    assert client.delete(f"/api/projects/{pid}", headers=other).status_code == 403
    info = client.get(f"/api/projects/{pid}/delete", headers=owner).json()
    assert info["status_display"] == "On Hold"
    r = client.delete(f"/api/projects/{pid}", headers=owner)
    assert r.json()["message"] == 'Project "Renamed" has been deleted successfully.'
    db.expire_all()
    assert db.get(ResearchProject, pid) is None
    assert db.execute(select(ProjectAuthor).where(ProjectAuthor.project_id == pid)).first() is None


# ---------------------------------------------------------------- timeline
def test_timeline_defaults_and_save(client, login_as, db):
    h = login_as("teacher1")
    pid = _create(client, h)
    t = client.get(f"/api/projects/{pid}/timeline", headers=h).json()
    names = [m["milestone_name"] for m in t["milestones"]]
    assert names[0] == "Kick off call" and names[-1] == "Final submitted draft" and len(names) == 10
    assert t["can_edit"] is True

    ms = t["milestones"]
    rows = [{**m} for m in ms]
    rows[0].update(start_date="2025-01-01", end_date="2025-01-11", status="completed", responsible_person_name="Ann")
    rows[1]["DELETE"] = True
    rows.append({"id": None, "order": 11, "milestone_name": "Extra", "status": "not_started"})
    files = {"attachment-10": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    r = client.post(f"/api/projects/{pid}/timeline", data={"milestones": json.dumps(rows)}, files=files, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Project timeline updated successfully!"
    db.expire_all()
    stored = db.execute(select(ProjectMilestone).where(ProjectMilestone.project_id == pid)
                        .order_by(ProjectMilestone.order)).scalars().all()
    assert len(stored) == 10
    assert stored[0].tat_days == 10 and stored[0].status == "completed"
    extra = stored[-1]
    assert extra.milestone_name == "Extra" and extra.attachment.startswith("milestones/notes")
    assert client.get(f"/api/projects/milestones/{extra.id}/attachment", headers=h).content == b"hello"

    # validation: end before start, duplicate order with an existing row
    bad = [{**m} for m in client.get(f"/api/projects/{pid}/timeline", headers=h).json()["milestones"]]
    bad[0].update(start_date="2025-02-10", end_date="2025-02-01")
    bad.append({"order": 3, "milestone_name": "Dup", "status": "not_started"})
    r = client.post(f"/api/projects/{pid}/timeline", data={"milestones": json.dumps(bad)}, headers=h)
    assert r.status_code == 400
    msg = r.json()["detail"]
    assert msg.startswith("Timeline errors: Form 0:") and "End date must be after start date." in msg
    assert "Project milestone with this Project and Order already exists." in msg


def test_timeline_collaborator_cannot_edit(client, login_as, db):
    owner = login_as("teacher1")
    pid = _create(client, owner)
    db.add(ResearchProjectCollaborator(project_id=pid, user_id=_user(db, "reviewer1").id, role="researcher",
                                       is_active=1))
    db.commit()
    collab = login_as("reviewer1")
    t = client.get(f"/api/projects/{pid}/timeline", headers=collab).json()
    assert t["can_edit"] is False
    r = client.post(f"/api/projects/{pid}/timeline", data={"milestones": "[]"}, headers=collab)
    assert r.status_code == 403 and r.json()["detail"] == "Only the project owner can edit the timeline."


# ---------------------------------------------------------------- collaborators
def test_collaborator_add_edit_remove(client, login_as, db):
    owner = login_as("teacher1")
    pid = _create(client, owner)
    target = _user(db, "reviewer2")
    form = client.get(f"/api/projects/{pid}/collaborators/form", headers=owner).json()
    assert any(o["value"] == target.id for o in form["users"])
    assert all(o["value"] != _user(db, "teacher1").id for o in form["users"])

    r = client.post(f"/api/projects/{pid}/collaborators", json={"user": target.id, "role": "analyst"}, headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["message"] == f"{target.first_name} {target.last_name} has been added as Analyst."
    cid = r.json()["id"]

    # owner cannot be added; duplicates rejected (not in available queryset)
    r = client.post(f"/api/projects/{pid}/collaborators", json={"user": target.id, "role": "analyst"}, headers=owner)
    assert r.status_code == 400 and "Select a valid choice" in r.json()["detail"]["errors"]["user"][0]
    r = client.post(f"/api/projects/{pid}/collaborators", json={"user": "", "role": "x"}, headers=owner)
    assert r.json()["detail"]["errors"]["user"] == ["This field is required."]

    collab_h = login_as("reviewer2")
    assert client.get(f"/api/projects/{pid}", headers=collab_h).json()["is_collaborator"] is True
    r = client.post(f"/api/projects/{pid}/collaborators", json={"user": 1, "role": "analyst"}, headers=collab_h)
    assert r.status_code == 403 and r.json()["detail"] == "Only the project owner can add collaborators."

    r = client.put(f"/api/projects/{pid}/collaborators/{cid}", json={"role": "reviewer"}, headers=owner)
    assert r.json()["message"] == f"{target.first_name} {target.last_name}'s role has been updated to Reviewer."

    pc = client.get(f"/api/projects/{pid}/collaborators", headers=collab_h).json()
    assert pc["can_manage"] is False and pc["collaborators"][0]["role"] == "reviewer"
    lst = client.get("/api/projects/collaborators", params={"role": "reviewer"}, headers=owner).json()
    assert any(c["id"] == cid and c["can_manage"] for c in lst["collaborators"])
    allc = client.get("/api/projects/all-collaborators", params={"project": str(pid)}, headers=collab_h).json()
    assert allc["total_collaborations"] == 1 and allc["total_collaborators"] == 1

    legacy = client.post(f"/api/projects/{pid}/collaborators/by-email", json={"email": target.email}, headers=owner)
    assert legacy.status_code == 400 and legacy.json()["detail"] == "User is already a collaborator"

    r = client.delete(f"/api/projects/{pid}/collaborators/{cid}", headers=owner)
    assert r.json()["message"] == f"{target.first_name} {target.last_name} has been removed from the project."
    db.expire_all()
    assert db.get(ResearchProjectCollaborator, cid) is None


# ---------------------------------------------------------------- tasks
def test_tasks_crud(client, login_as, db):
    owner = login_as("teacher1")
    pid = _create(client, owner)
    stranger = login_as("reviewer1")
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "T"}, headers=stranger)
    assert r.json()["detail"] == "You do not have permission to add tasks to this project."

    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "", "status": "todo", "priority": "medium",
                                                        "assigned_to": _user(db, "reviewer1").id}, headers=owner)
    errs = r.json()["detail"]["errors"]
    assert errs["title"] == ["This field is required."] and "assigned_to" in errs

    r = client.post(f"/api/projects/{pid}/tasks", json={
        "title": "Write intro", "status": "completed", "priority": "high",
        "assigned_to": _user(db, "teacher1").id, "due_date": "2025-03-01"}, headers=owner)
    assert r.json()["message"] == 'Task "Write intro" has been added to the project.'
    tid = r.json()["id"]
    client.post(f"/api/projects/{pid}/tasks", json={"title": "Other", "status": "todo", "priority": "low"},
                headers=owner)
    assert client.get(f"/api/projects/{pid}", headers=owner).json()["progress_percentage"] == 50

    r = client.put(f"/api/projects/{pid}/tasks/{tid}", json={"title": "Write intro v2", "status": "in_progress",
                                                             "priority": "urgent"}, headers=owner)
    assert r.json()["message"] == 'Task "Write intro v2" has been updated.'
    db.expire_all()
    t = db.get(ResearchProjectTask, tid)
    assert t.priority == "urgent" and t.assigned_to_id is None
    r = client.delete(f"/api/projects/{pid}/tasks/{tid}", headers=owner)
    assert r.json()["message"] == 'Task "Write intro v2" has been deleted.'


# ---------------------------------------------------------------- documents
def test_project_documents(client, login_as, db):
    owner = login_as("teacher1")
    pid = _create(client, owner)
    r = client.post(f"/api/projects/{pid}/upload-document", data={"title": ""}, headers=owner)
    assert r.status_code == 400 and r.json()["detail"] == "Title and file are required."
    r = client.post(f"/api/projects/{pid}/upload-document", data={"title": "Protocol", "description": "d"},
                    files={"document_file": ("protocol.pdf", io.BytesIO(b"%PDF-1"), "application/pdf")},
                    headers=owner)
    assert r.json()["message"] == 'Document "Protocol" uploaded successfully!'
    did = r.json()["id"]
    doc = db.get(ResearchProjectDocument, did)
    assert doc.file == "projects/documents/protocol.pdf"
    assert client.get(f"/api/projects/{pid}/documents/{did}/download", headers=owner).content == b"%PDF-1"

    other = login_as("reviewer1")
    assert client.delete(f"/api/projects/{pid}/documents/{did}", headers=other).status_code == 403
    r = client.delete(f"/api/projects/{pid}/documents/{did}", headers=owner)
    assert r.json()["message"] == 'Document "Protocol" deleted successfully!'


# ---------------------------------------------------------------- version sharing
@pytest.fixture()
def version(db):
    """The newest version of an SMBT document (other workspaces' documents are hidden from SMBT users)."""
    from app.models import Document, Organisation, OrgMembership
    smbt = select(Organisation.id).where(Organisation.slug == "smbt").scalar_subquery()
    v = db.execute(select(DocumentVersion).join(Document, Document.id == DocumentVersion.document_id)
                   .join(OrgMembership, OrgMembership.user_id == Document.user_id)
                   .where(OrgMembership.organisation_id == smbt)
                   .order_by(DocumentVersion.id.desc()).limit(1)).scalar_one()
    return v


def test_version_collaborators_flow(client, login_as, db, version):
    admin = login_as("admin")
    page = client.get(f"/api/sharing/versions/{version.id}/collaborators", headers=admin).json()
    owner_id = version.document.user_id
    candidate = next(u for u in page["available_users"] if u["value"] != owner_id)
    assert all(u["value"] != owner_id for u in page["available_users"])

    s = client.get("/api/sharing/search-users-version-sharing",
                   params={"q": "a", "version_id": version.id}, headers=admin).json()
    assert len(s["users"]) <= 10 and all(u["id"] != owner_id for u in s["users"])
    assert client.get("/api/sharing/search-users-version-sharing", params={"q": ""}, headers=admin).json() == \
        {"users": []}

    r = client.post(f"/api/sharing/versions/{version.id}/collaborators/add", json={
        "user_id": candidate["value"], "permission_level": "edit", "can_share": True, "notes": "pls review",
        "expires_at": ""}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] and body["collaborator"]["permission_level"] == "View and Edit"
    sid = body["collaborator"]["id"]
    row = db.get(DocumentSharing, sid)
    assert row.document_id == version.document_id and row.can_share == 1 and row.expires_at is None
    note = db.execute(select(DocumentNotification).where(DocumentNotification.receiver_id == candidate["value"],
                                                         DocumentNotification.sent_for == "document_sharing")
                      .order_by(DocumentNotification.id.desc())).scalars().first()
    assert note and note.description.endswith(f"shared version '{version.version_number}' with you")

    dup = client.post(f"/api/sharing/versions/{version.id}/collaborators/add",
                      json={"user_id": candidate["value"]}, headers=admin)
    assert dup.status_code == 400 and dup.json()["error"] == "Document version already shared with this user"

    r = client.post(f"/api/sharing/versions/{version.id}/collaborators/update/{sid}",
                    json={"permission_level": "admin", "can_download": False, "role_id": ""}, headers=admin)
    assert r.json()["message"] == "Collaborator permissions updated successfully"
    db.expire_all()
    assert db.get(DocumentSharing, sid).permission_level == "admin" and db.get(DocumentSharing, sid).can_download == 0

    r = client.post(f"/api/sharing/versions/{version.id}/collaborators/remove/{sid}", headers=admin)
    assert r.json()["success"] and r.json()["message"].startswith("Successfully removed ")
    db.expire_all()
    assert db.get(DocumentSharing, sid) is None


def test_version_collaborators_permission_denied(client, login_as, db, version):
    owner_id = version.document.user_id
    candidates = [u for u in ("reviewer1", "reviewer2", "teacher1") if _user(db, u).id != owner_id
                  and not _user(db, u).is_superuser]
    h = login_as(candidates[0])
    r = client.get(f"/api/sharing/versions/{version.id}/collaborators", headers=h)
    assert r.status_code == 403
    r = client.post(f"/api/sharing/versions/{version.id}/collaborators/add", json={"user_id": 1}, headers=h)
    assert r.status_code == 403 and r.json() == {"error": "Permission denied"}


def test_drf_sharing_endpoints(client, login_as, db, version):
    admin = login_as("admin")
    target = _user(db, "reviewer2")
    r = client.post("/api/sharing/document-version-sharing", json={
        "document_version": version.id, "user": target.id, "permission_level": "view"}, headers=admin)
    assert r.status_code == 201, r.text
    vsid = r.json()["id"]
    assert r.json()["version_display"]["version_number"] == version.version_number
    r = client.post("/api/sharing/document-version-sharing", json={
        "document_version": version.id, "user": target.id}, headers=admin)
    assert r.status_code == 400 and "unique set" in r.json()["non_field_errors"][0]
    r = client.patch(f"/api/sharing/document-version-sharing/{vsid}", json={"permission_level": "edit"}, headers=admin)
    assert r.json()["permission_level"] == "edit"
    assert client.delete(f"/api/sharing/document-version-sharing/{vsid}", headers=admin).status_code == 204
    db.expire_all()
    assert db.get(DocumentVersionSharing, vsid) is None

    r = client.post("/api/sharing/document-sharing", json={"document": version.document_id, "user": target.id,
                                                           "permission_level": "view"}, headers=admin)
    assert r.status_code == 201, r.text
    shid = r.json()["id"]
    assert r.json()["user_display"]["username"] == "reviewer2" and r.json()["is_valid"] is True
    lst = client.get("/api/sharing/document-sharing", headers=admin).json()
    assert {"count", "next", "previous", "results"} <= set(lst)
    assert any(s["id"] == shid for s in client.get("/api/sharing/document-sharing/my-shares", headers=admin).json())
    tgt_h = login_as("reviewer2")
    assert any(d["id"] == version.document_id for d in
               client.get("/api/sharing/document-sharing/shared-with-me", headers=tgt_h).json())
    acc = client.post("/api/sharing/document-sharing/check-access",
                      json={"document_id": version.document_id, "action": "download"}, headers=tgt_h).json()
    assert acc["has_access"] is True and acc["has_permission"] is True
    r = client.patch(f"/api/sharing/document-sharing/{shid}", json={"notes": "x"}, headers=tgt_h)
    assert r.status_code == 400
    assert client.delete(f"/api/sharing/document-sharing/{shid}", headers=tgt_h).status_code == 403
    assert client.delete(f"/api/sharing/document-sharing/{shid}", headers=admin).status_code == 204
