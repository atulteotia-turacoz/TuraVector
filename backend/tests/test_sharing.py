"""Document version sharing tests (Content Review version collaborators) — run inside the rolled-back transaction from conftest."""
import pytest
from sqlalchemy import select

from app.models import (
    DocumentNotification,
    DocumentSharing,
    DocumentVersion,
    DocumentVersionSharing,
    User,
)


pytestmark = pytest.mark.usefixtures("stand_ins")

def _user(db, username):
    return db.execute(select(User).where(User.username == username)).scalar_one()


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
    users = db.execute(select(User).where(User.username.in_(("reviewer1", "reviewer2", "teacher1")))).scalars().all()
    candidates = sorted(u.username for u in users if u.id != owner_id and not u.is_superuser)
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
