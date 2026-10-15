"""Organisation workspaces: data of one workspace is invisible to every other workspace."""
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models import (
    Country, Document, DocumentType, DocumentVersion, Organisation, OrgMembership, ReferenceDocument,
    ResearchProject, User,
)


def _user(db, username_prefix: str, **kw) -> User:
    name = f"{username_prefix}_{uuid.uuid4().hex[:8]}"
    u = User(password="!", is_superuser=0, username=name, is_staff=0, is_active=1, first_name=kw.get("first_name", "T"),
             last_name="User", email=f"{name}@example.com", user_type=kw.get("user_type", "student"), is_manager=0,
             timezone="UTC")
    db.add(u)
    db.commit()
    return u


def _org(db, name: str, kind: str = "university") -> Organisation:
    org = Organisation(name=name, slug=f"t-{uuid.uuid4().hex[:10]}", kind=kind, website="", logo="", status="active",
                       join_code=uuid.uuid4().hex[:8].upper())
    db.add(org)
    db.commit()
    return org


def _join(db, org, user, role="member"):
    m = db.execute(select(OrgMembership).where(OrgMembership.user_id == user.id)).scalar_one()
    m.organisation_id, m.role, m.status = org.id, role, "active"
    db.commit()
    user.__dict__.pop("_org_membership", None)


def _doc(db, owner: User, name: str) -> Document:
    dt = db.execute(select(DocumentType).limit(1)).scalar_one()
    country = db.execute(select(Country).limit(1)).scalar_one()
    doc = Document(document_name=name, document_number=f"ISO-{uuid.uuid4().hex[:8]}", stage_status=0, is_active=1,
                   country_id=country.id, created_by_id=owner.id, modified_by_id=owner.id, user_id=owner.id,
                   document_type_id=dt.id)
    db.add(doc)
    db.commit()
    db.add(DocumentVersion(version_number=f"{doc.document_number}-V-1", version_count=1, file_name="a.docx",
                           file_extension="docx", file_title_name="a.docx", document_file="documents/None/a.docx",
                           stage_status=0, created_by_id=owner.id, document_id=doc.id, modified_by_id=owner.id,
                           user_id=owner.id))
    db.commit()
    return doc


def _h(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture()
def world(db):
    """SMBT: admin + member with a document. Other Uni: admin + member with a document and a reference."""
    smbt = db.execute(select(Organisation).where(Organisation.slug == "smbt")).scalar_one()
    other = _org(db, "Other University")
    a_admin, a_member = _user(db, "smbtadmin"), _user(db, "smbtmember")
    b_admin, b_member = _user(db, "otheradmin"), _user(db, "othermember", first_name="Bobby")
    _join(db, smbt, a_admin, "admin")
    _join(db, other, b_admin, "admin")
    _join(db, other, b_member)
    doc_a, doc_b = _doc(db, a_member, "SMBT Secret Doc"), _doc(db, b_member, "Other Uni Doc")
    country = db.execute(select(Country).limit(1)).scalar_one()
    ref_b = ReferenceDocument(document_name="Other Ref", reference_number=f"REF-{uuid.uuid4().hex[:6]}",
                              type="primary", subtype="journal", reference_file="references/x.pdf",
                              file_name="x.pdf", file_extension="pdf", file_title_name="x.pdf", is_active=1,
                              country_id=country.id,
                              user_id=b_member.id, created_by_id=b_member.id, modified_by_id=b_member.id)
    db.add(ref_b)
    db.commit()
    db.info["fresh_identity_map_per_request"] = True
    return dict(smbt=smbt, other=other, a_admin=a_admin, a_member=a_member, b_admin=b_admin, b_member=b_member,
                doc_a=doc_a, doc_b=doc_b, ref_b=ref_b)


def _texts(resp) -> str:
    return json.dumps(resp.json())


def test_org_admin_is_manager_within_workspace(client, world):
    me = client.get("/api/auth/me", headers=_h(world["b_admin"])).json()
    assert me["is_org_admin"] is True and me["is_manager_like"] is True
    assert me["organisation"]["name"] == "Other University" and me["organisation"]["role"] == "admin"
    assert me["capabilities"]["can_view_all_documents"] is True
    member = client.get("/api/auth/me", headers=_h(world["b_member"])).json()
    assert member["is_org_admin"] is False and member["organisation"]["role"] == "member"


def test_document_detail_and_files_are_isolated(client, db, world):
    h = _h(world["b_admin"])
    assert client.get(f"/api/doccore/documents/{world['doc_b'].id}", headers=h).status_code == 200
    assert client.get(f"/api/doccore/documents/{world['doc_a'].id}", headers=h).status_code in (403, 404)
    va = db.execute(select(DocumentVersion).where(DocumentVersion.document_id == world["doc_a"].id)).scalar_one()
    for url in (f"/api/doccore/versions/{va.id}/file", f"/api/viewer/versions/{va.id}/file",
                f"/api/viewer/versions/{va.id}/preview", f"/api/doccore/history/{world['doc_a'].id}"):
        assert client.get(url, headers=h).status_code in (403, 404), url


def test_lists_dashboards_and_reports_are_isolated(client, world):
    h = _h(world["b_admin"])
    for url in ("/api/library/documents", "/api/users/manager-dashboard", "/api/users/manager-dashboard/insights",
                "/api/users/reports", "/api/tools/analytics", "/api/users/manage", "/api/library/quick-stats",
                "/api/doccore/reviewer-assignments", "/api/projects/all-collaborators"):
        r = client.get(url, headers=h)
        assert r.status_code == 200, (url, r.text)
        body = _texts(r)
        assert "SMBT Secret Doc" not in body and world["a_member"].username not in body, url
    assert "Other Uni Doc" in _texts(client.get("/api/library/documents", headers=h))
    assert world["b_member"].username in _texts(client.get("/api/users/manage", headers=h))


def test_user_pickers_and_profiles_are_isolated(client, world):
    h = _h(world["b_admin"])
    found = client.get("/api/doccore/search-users", params={"q": "smbtmember"}, headers=h)
    assert world["a_member"].username not in _texts(found)
    assert client.get(f"/api/users/{world['a_member'].id}/profile", headers=h).status_code in (403, 404)
    assert client.get(f"/api/users/{world['b_member'].id}/profile", headers=h).status_code == 200


def test_references_are_isolated(client, world):
    ref = world["ref_b"]
    assert client.get(f"/api/library/references/{ref.id}", headers=_h(world["b_admin"])).status_code == 200
    assert client.get(f"/api/library/references/{ref.id}", headers=_h(world["a_admin"])).status_code in (403, 404)
    assert "Other Ref" not in _texts(client.get("/api/library/references", headers=_h(world["a_admin"])))


def test_projects_are_isolated(client, db, world):
    p = ResearchProject(title="Other Project", description="", owner_id=world["b_member"].id, status="planning",
                        priority="medium", research_field="", keywords="", is_active=1, client_type="internal",
                        has_authors=0, project_type="research", therapeutic_area="")
    db.add(p)
    db.commit()
    assert client.get(f"/api/projects/{p.id}", headers=_h(world["a_admin"])).status_code in (403, 404)


def test_superuser_sees_every_workspace(client, world, login_as):
    h = login_as("admin")
    assert client.get(f"/api/doccore/documents/{world['doc_a'].id}", headers=h).status_code == 200
    assert client.get(f"/api/doccore/documents/{world['doc_b'].id}", headers=h).status_code == 200


def test_individual_workspace_sees_only_itself(client, db, world):
    solo = _user(db, "solo")
    _join(db, _org(db, "Solo", kind="individual"), solo)
    me = client.get("/api/auth/me", headers=_h(solo)).json()
    assert me["is_org_admin"] is False and me["organisation"]["kind"] == "individual"
    h = _h(solo)
    assert client.get(f"/api/doccore/documents/{world['doc_b'].id}", headers=h).status_code in (403, 404)
    assert world["b_member"].username not in _texts(client.get("/api/doccore/search-users", params={"q": "o"}, headers=h))


def test_inactive_workspace_blocks_sign_in(client, db, world):
    db.get(Organisation, world["other"].id).status = "suspended"
    db.commit()
    assert client.get("/api/auth/me", headers=_h(world["b_member"])).status_code == 401


def test_superuser_uploads_belong_to_smbt(client, db, world):
    admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
    doc = _doc(db, admin, "Uploaded By Superadmin")
    assert client.get(f"/api/doccore/documents/{doc.id}", headers=_h(world["a_admin"])).status_code == 200
    assert client.get(f"/api/doccore/documents/{doc.id}", headers=_h(world["b_admin"])).status_code in (403, 404)
    assert "Uploaded By Superadmin" in _texts(client.get("/api/library/documents", headers=_h(world["a_admin"])))
    # superusers themselves are still not SMBT members
    users = _texts(client.get("/api/users/manage", headers=_h(world["a_admin"])))
    assert '"username": "admin"' not in users


def test_org_admin_has_no_reviewer_dashboard_unless_a_reviewer(client, world):
    caps = client.get("/api/auth/me", headers=_h(world["b_admin"])).json()["capabilities"]
    assert caps["can_access_manager_dashboard"] is True and caps["can_access_reviewer_dashboard"] is False


def test_member_detail_page(client, world):
    h = _h(world["b_admin"])
    r = client.get(f"/api/org/members/{world['b_member'].id}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["member"]["username"] == world["b_member"].username and d["member"]["role"] == "member"
    assert d["stats"]["documents"] == 1 and [x["name"] for x in d["documents"]] == ["Other Uni Doc"]
    assert d["stats"]["references"] == 1 and d["references"][0]["name"] == "Other Ref"
    # members of another workspace stay out of reach
    assert client.get(f"/api/org/members/{world['a_member'].id}", headers=h).status_code == 404
    assert client.get(f"/api/org/members/{world['b_member'].id}", headers=_h(world["b_member"])).status_code == 403
