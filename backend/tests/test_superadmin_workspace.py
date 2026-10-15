"""Superadmin workspace switcher: workspace-level models show only the chosen workspace."""
import uuid

import pytest
from sqlalchemy import select

from app.models import Organisation, OrgMembership, Permission, User, UserPermission


@pytest.fixture()
def two_workspaces(db):
    smbt = db.execute(select(Organisation).where(Organisation.slug == "smbt")).scalar_one()
    other = Organisation(name="Scope Uni", slug=f"scope-{uuid.uuid4().hex[:8]}", kind="university", website="", logo="",
                         status="active", join_code=uuid.uuid4().hex[:8].upper())
    db.add(other)
    db.commit()
    name = f"scope_{uuid.uuid4().hex[:6]}"
    outsider = User(password="!", is_superuser=0, username=name, is_staff=0, is_active=1, first_name="Out", last_name="Sider",
                    email=f"{name}@example.com", user_type="student", is_manager=0, timezone="UTC")
    db.add(outsider)
    db.commit()
    m = db.execute(select(OrgMembership).where(OrgMembership.user_id == outsider.id)).scalar_one()
    m.organisation_id = other.id
    perm = db.execute(select(Permission).limit(1)).scalar_one()
    up = UserPermission(user_id=outsider.id, permission_id=perm.id, is_granted=1, reason="scope test")
    db.add(up)
    db.commit()
    return smbt, other, outsider, up


def _h(login_as, org):
    return {**login_as("admin"), "X-Workspace": str(org.id)}


def test_changelist_and_object_follow_the_chosen_workspace(client, login_as, two_workspaces):
    smbt, other, outsider, up = two_workspaces
    url = "/api/superadmin/models/authentication/userpermission/"
    in_other = client.get(url, headers=_h(login_as, other)).json()
    # the scope test grant + the "Content Lab visible" grant every new user gets
    assert in_other["count"] == 2 and in_other["full_count"] == 2
    in_smbt = client.get(url, headers=_h(login_as, smbt)).json()
    assert all(str(up.id) != str(r["pk"]) for r in in_smbt["rows"])
    everyone = client.get(url, headers=login_as("admin")).json()
    assert everyone["full_count"] >= in_other["full_count"] + in_smbt["full_count"]
    assert client.get(f"{url}{up.id}", headers=_h(login_as, other)).status_code == 200
    assert client.get(f"{url}{up.id}", headers=_h(login_as, smbt)).status_code == 404


def test_user_dropdowns_and_users_list_are_scoped(client, login_as, two_workspaces):
    smbt, other, outsider, _ = two_workspaces
    ac = client.get("/api/superadmin/models/authentication/userpermission/autocomplete",
                    params={"field": "user", "all": "true"}, headers=_h(login_as, smbt)).json()
    assert outsider.username not in str(ac)
    ac = client.get("/api/superadmin/models/authentication/userpermission/autocomplete",
                    params={"field": "user", "all": "true"}, headers=_h(login_as, other)).json()
    assert len(ac["results"]) == 1 and outsider.username in ac["results"][0]["label"]
    users = client.get("/api/superadmin/models/authentication/user/", headers=_h(login_as, other)).json()
    assert users["count"] == 1
    manage = client.get("/api/users/manage", headers=_h(login_as, other)).json()
    assert [u["username"] for u in manage["users"]] == [outsider.username]


def test_platform_models_stay_global_and_index_marks_scope(client, login_as, two_workspaces):
    smbt, other, *_ = two_workspaces
    roles_all = client.get("/api/superadmin/models/authentication/role/", headers=login_as("admin")).json()["count"]
    roles_other = client.get("/api/superadmin/models/authentication/role/", headers=_h(login_as, other)).json()["count"]
    assert roles_all == roles_other > 0
    logs_all = client.get("/api/superadmin/models/authentication/loginlog/", headers=login_as("admin")).json()["count"]
    logs_other = client.get("/api/superadmin/models/authentication/loginlog/", headers=_h(login_as, other)).json()["count"]
    assert logs_all == logs_other  # login logs are a platform audit trail
    models = {m["label"]: m for a in client.get("/api/superadmin/index", headers=_h(login_as, other)).json()["apps"]
              for m in a["models"]}
    assert models["authentication.UserPermission"]["scope"] == "workspace"
    assert models["authentication.UserPermission"]["count"] == 2
    assert models["authentication.Role"]["scope"] == "platform"
    assert models["authentication.LoginLog"]["scope"] == "platform"


def test_superadmin_add_user_joins_the_chosen_workspace(client, db, login_as, two_workspaces):
    _, other, *_ = two_workspaces
    r = client.post("/api/superadmin/models/authentication/user/add", headers=_h(login_as, other),
                    json={"username": "scope_added_t", "password1": "Zx9!long-pass", "password2": "Zx9!long-pass"})
    assert r.status_code == 200, r.text
    u = db.execute(select(User).where(User.username == "scope_added_t")).scalar_one()
    assert db.execute(select(OrgMembership.organisation_id).where(OrgMembership.user_id == u.id)).scalar_one() == other.id


def test_workspace_header_is_ignored_for_non_superusers(client, login_as, two_workspaces):
    _, other, outsider, _ = two_workspaces
    h = {**login_as("teacher1"), "X-Workspace": str(other.id)}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["organisation"]["name"] == "SMBT"
    assert client.get(f"/api/users/{outsider.id}/profile", headers=h).status_code in (403, 404)


def test_organisations_page_is_platform_wide(client, login_as, two_workspaces):
    smbt, other, outsider, _ = two_workspaces
    h = _h(login_as, smbt)
    names = {o["name"] for o in client.get("/api/superadmin/organisations", headers=h).json()["organisations"]}
    assert {"SMBT", "Scope Uni"} <= names
    detail = client.get(f"/api/superadmin/organisations/{other.id}", headers=h).json()
    assert [m["username"] for m in detail["members"]] == [outsider.username]


def test_superuser_rows_show_in_smbt_only(client, login_as, db, two_workspaces):
    smbt, other, *_ = two_workspaces
    from app.models import Document
    admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
    owned = db.execute(select(Document.id).where(Document.user_id == admin.id)).scalars().all()
    if not owned:
        pytest.skip("no superuser documents in this database")
    url = "/api/superadmin/models/documents/document/"
    assert client.get(f"{url}{owned[0]}", headers=_h(login_as, smbt)).status_code == 200
    assert client.get(f"{url}{owned[0]}", headers=_h(login_as, other)).status_code == 404
    users = client.get("/api/superadmin/models/authentication/user/", headers=_h(login_as, smbt)).json()
    assert all("admin" != r.get("str") for r in users["rows"])


def test_dashboard_overview_for_one_workspace(client, db, login_as, two_workspaces):
    smbt, other, outsider, _ = two_workspaces
    h = login_as("admin")
    everything = client.get("/api/superadmin/overview", headers=h).json()
    only_other = client.get("/api/superadmin/overview", headers=h, params={"workspace": other.id}).json()
    assert only_other["users"]["total"] == 1 and everything["users"]["total"] > 1
    assert only_other["documents"]["total"] == 0
    in_smbt = client.get("/api/superadmin/overview", headers=h, params={"workspace": smbt.id}).json()
    # superuser uploads count as SMBT's; other workspaces (e.g. test universities) hold the rest
    from sqlalchemy import func, select
    from app.models import Document, OrgMembership
    others = db.scalar(select(func.count()).select_from(Document).join(OrgMembership, OrgMembership.user_id == Document.user_id)
                       .where(Document.is_active == 1, OrgMembership.organisation_id != smbt.id))
    assert in_smbt["documents"]["total"] == everything["documents"]["total"] - others
