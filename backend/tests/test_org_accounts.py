"""Workspace sign-up, the university admin console and the superadmin organisations API."""
import io

from PIL import Image
from sqlalchemy import select

from app.models import Organisation, OrgMembership, User

BASE = {"first_name": "Asha", "last_name": "Rao", "password": "secret123", "confirm_password": "secret123",
        "privacy_consent": True}


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "navy").save(buf, "PNG")
    return buf.getvalue()


def _signup(client, username, **extra):
    return client.post("/api/auth/signup", json={**BASE, "username": username, "email": f"{username}@example.com", **extra})


def _login(client, username):
    return client.post("/api/auth/login", json={"username": username, "password": "secret123", "privacy_consent": True})


def _membership(db, username) -> OrgMembership:
    user = db.execute(select(User).where(User.username == username)).scalar_one()
    return db.execute(select(OrgMembership).where(OrgMembership.user_id == user.id)).scalar_one()


def _register_university(client, username="uniadmin_t", name="Test University"):
    return client.post("/api/auth/signup-organisation", data={
        **{k: str(v) for k, v in BASE.items()}, "username": username, "email": f"{username}@example.com",
        "organisation_name": name, "organisation_kind": "university", "website": "https://test.example.edu",
    }, files={"logo": ("logo.png", io.BytesIO(_png()), "image/png")})


def _approve(client, login_as, db, name="Test University") -> Organisation:
    org = db.execute(select(Organisation).where(Organisation.name == name)).scalar_one()
    r = client.post(f"/api/superadmin/organisations/{org.id}/status", json={"status": "active"}, headers=login_as("admin"))
    assert r.status_code == 200, r.text
    db.refresh(org)
    return org


# ------------------------------------------------------------------ sign-up
def test_individual_signup_gets_a_personal_workspace(client, db):
    r = _signup(client, "solo_t", user_type="researcher")
    assert r.status_code == 200, r.text
    me = r.json()["user"]
    assert me["organisation"]["kind"] == "individual" and me["organisation"]["name"] == "Asha Rao"
    assert me["is_org_admin"] is False and me["is_manager_like"] is False
    m = _membership(db, "solo_t")
    assert m.role == "member" and m.status == "active"


def test_signup_cannot_choose_a_privileged_type(client):
    for t in ("manager", "teacher", "reviewer"):
        r = _signup(client, f"sneaky_{t}", user_type=t)
        assert r.status_code == 400 and r.json()["error"] == "Invalid account type."


def test_university_signup_waits_for_approval(client, db, login_as, sent_emails):
    r = _register_university(client)
    assert r.status_code == 200, r.text
    assert r.json()["pending"] is True and "access_token" not in r.json()
    org = db.execute(select(Organisation).where(Organisation.name == "Test University")).scalar_one()
    assert org.status == "pending" and org.kind == "university" and org.logo.startswith("organisation_logos/")
    assert org.join_code and _membership(db, "uniadmin_t").role == "admin"
    assert any("awaiting approval" in e["subject"] for e in sent_emails)  # superadmins are told

    blocked = _login(client, "uniadmin_t")
    assert blocked.status_code == 403 and "awaiting approval" in blocked.json()["detail"]

    _approve(client, login_as, db)
    ok = _login(client, "uniadmin_t")
    assert ok.status_code == 200, ok.text
    me = ok.json()["user"]
    assert me["is_org_admin"] is True and me["organisation"]["name"] == "Test University"
    assert me["user_type_display"] == "University Admin" and me["organisation"]["logo_url"]


def test_university_signup_validation(client):
    r = client.post("/api/auth/signup-organisation", data={**{k: str(v) for k, v in BASE.items()}, "username": "x_t",
                                                           "email": "x_t@example.com", "organisation_name": ""})
    assert r.status_code == 400 and "name of your university" in r.json()["error"]
    r = client.post("/api/auth/signup-organisation", data={
        **{k: str(v) for k, v in BASE.items()}, "username": "x_t", "email": "x_t@example.com", "organisation_name": "U",
    }, files={"logo": ("logo.png", io.BytesIO(b"not an image"), "image/png")})
    assert r.status_code == 400 and r.json()["error"] == "Upload the logo as a PNG or JPG image."


def test_join_with_code_needs_admin_approval(client, db, login_as, sent_emails):
    _register_university(client)
    org = _approve(client, login_as, db)

    bad = _signup(client, "joiner_t", account_type="join", join_code="NOPE1234")
    assert bad.status_code == 400 and "not valid" in bad.json()["error"]

    r = _signup(client, "joiner_t", account_type="join", join_code=org.join_code.lower())
    assert r.status_code == 200 and r.json()["pending"] is True
    assert _membership(db, "joiner_t").status == "pending"
    assert any("request to join Test University" in e["subject"] for e in sent_emails)
    assert _login(client, "joiner_t").status_code == 403

    admin_h = {"Authorization": f"Bearer {_login(client, 'uniadmin_t').json()['access_token']}"}
    pending = client.get("/api/org/members", params={"status": "pending"}, headers=admin_h).json()["members"]
    assert [m["username"] for m in pending] == ["joiner_t"]
    joiner = db.execute(select(User).where(User.username == "joiner_t")).scalar_one()
    assert client.post(f"/api/org/members/{joiner.id}/approve", headers=admin_h).status_code == 200
    assert _login(client, "joiner_t").status_code == 200


# ------------------------------------------------------------------ university admin console
def test_org_admin_manages_members_and_settings(client, db, login_as):
    _register_university(client)
    org = _approve(client, login_as, db)
    h = {"Authorization": f"Bearer {_login(client, 'uniadmin_t').json()['access_token']}"}

    overview = client.get("/api/org/overview", headers=h).json()
    assert overview["organisation"]["join_code"] == org.join_code and overview["members"] == 1

    r = client.post("/api/org/members", headers=h, json={"username": "stud_t", "email": "stud_t@example.com",
                                                          "first_name": "Stu", "last_name": "Dent", "user_type": "student",
                                                          "send_welcome_email": False})
    assert r.status_code == 200, r.text
    password = r.json()["password"]
    m = _membership(db, "stud_t")
    assert m.organisation_id == org.id and m.role == "member" and m.status == "active"
    assert client.post("/api/auth/login", json={"username": "stud_t", "password": password,
                                                "privacy_consent": True}).status_code == 200

    stud = db.execute(select(User).where(User.username == "stud_t")).scalar_one()
    assert client.post(f"/api/org/members/{stud.id}/role", headers=h, json={"role": "admin"}).status_code == 200
    assert client.post(f"/api/org/members/{stud.id}/toggle-active", headers=h).json()["is_active"] is False

    # SMBT members are not reachable from this workspace
    smbt_user = db.execute(select(User).where(User.username == "teacher1")).scalar_one()
    assert client.post(f"/api/org/members/{smbt_user.id}/toggle-active", headers=h).status_code == 404

    s = client.post("/api/org/settings", headers=h, data={"name": "Renamed University", "website": "https://r.example"},
                    files={"logo": ("new.png", io.BytesIO(_png()), "image/png")})
    assert s.status_code == 200 and s.json()["organisation"]["name"] == "Renamed University"
    old_code = org.join_code
    assert client.post("/api/org/join-code/regenerate", headers=h).json()["join_code"] != old_code


def test_last_admin_cannot_step_down_and_members_are_not_admins(client, db, login_as):
    _register_university(client)
    _approve(client, login_as, db)
    h = {"Authorization": f"Bearer {_login(client, 'uniadmin_t').json()['access_token']}"}
    admin = db.execute(select(User).where(User.username == "uniadmin_t")).scalar_one()
    r = client.post(f"/api/org/members/{admin.id}/role", headers=h, json={"role": "member"})
    assert r.status_code == 400 and "at least one administrator" in r.json()["detail"]
    assert client.get("/api/org/overview", headers=login_as("teacher1")).status_code == 403


def test_org_admin_cannot_change_platform_roles_or_user_types(client, db, login_as):
    _register_university(client)
    _approve(client, login_as, db)
    h = {"Authorization": f"Bearer {_login(client, 'uniadmin_t').json()['access_token']}"}
    assert client.post("/api/users/user-types", headers=h, json={"name": "Hacker", "code": "hacker"}).status_code == 403
    assert client.post("/api/rbac/legacy/roles/create", headers=h, json={"name": "Boss"}).status_code == 403


# ------------------------------------------------------------------ superadmin
def test_superadmin_creates_workspace_and_moves_members(client, db, login_as):
    h = login_as("admin")
    r = client.post("/api/superadmin/organisations", headers=h, data={
        "name": "College X", "kind": "organisation", "admin_username": "collegex_admin",
        "admin_email": "cx@example.com", "admin_first_name": "Cee", "admin_password": "secret123"})
    assert r.status_code == 200, r.text
    org_id = r.json()["id"]
    assert _membership(db, "collegex_admin").role == "admin"

    listed = client.get("/api/superadmin/organisations", headers=h, params={"q": "College X"}).json()
    assert listed["organisations"][0]["admins"] == ["Cee"]

    teacher = db.execute(select(User).where(User.username == "teacher1")).scalar_one()
    found = client.get("/api/superadmin/organisations/users/search", headers=h, params={"q": "teacher1"}).json()
    assert found["users"][0]["organisation"] == "SMBT"
    assert client.post(f"/api/superadmin/organisations/{org_id}/members", headers=h,
                       json={"user_id": teacher.id, "role": "admin"}).status_code == 200
    assert _membership(db, "teacher1").organisation_id == org_id
    detail = client.get(f"/api/superadmin/organisations/{org_id}", headers=h).json()
    assert {m["username"] for m in detail["members"]} == {"collegex_admin", "teacher1"}

    assert client.get("/api/superadmin/organisations", headers=login_as("teacher1")).status_code == 403


def test_org_admin_cannot_create_global_managers(client, db, login_as):
    _register_university(client)
    org = _approve(client, login_as, db)
    h = {"Authorization": f"Bearer {_login(client, 'uniadmin_t').json()['access_token']}"}
    csv = ("username,email,first_name,last_name,user_type,is_manager\n"
           "imp_ok_t,imp_ok_t@example.com,Imp,Ok,Student,yes\n"
           "imp_mgr_t,imp_mgr_t@example.com,Imp,Mgr,Manager,no\n").encode()
    r = client.post("/api/users/bulk-import", headers=h, data={"skip_errors": "true"},
                    files={"file": ("users.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200, r.text
    imported = db.execute(select(User).where(User.username == "imp_ok_t")).scalar_one()
    assert imported.is_manager == 0  # the is_manager column is ignored for workspace admins
    assert _membership(db, "imp_ok_t").organisation_id == org.id  # imported users join the admin's workspace
    assert db.execute(select(User).where(User.username == "imp_mgr_t")).scalar_one_or_none() is None
    assert any("Only a superadmin can create managers" in m["text"] for m in r.json()["messages"]) or \
        "Only a superadmin" in r.text


def test_superadmin_must_choose_workspace_for_new_users(client, db, login_as):
    h = login_as("admin")
    other = client.post("/api/superadmin/organisations", headers=h, data={"name": "Workspace Y"}).json()["id"]
    opts = client.get("/api/users/create-options", headers=h).json()
    assert other in [o["id"] for o in opts["organisations"]]
    user_type = opts["user_types"][0]["id"]
    body = {"username": "sa_made_t", "email": "sa_made_t@example.com", "first_name": "Sa", "last_name": "Made",
            "user_type": str(user_type), "password": "Password1!", "confirm_password": "Password1!"}
    r = client.post("/api/users/create", headers=h, json=body)
    assert r.status_code == 400 and r.json()["detail"] == ["Choose the workspace the new user belongs to"]
    r = client.post("/api/users/create", headers=h, json={**body, "organisation": str(other)})
    assert r.status_code == 200, r.text
    assert _membership(db, "sa_made_t").organisation_id == other

    csv = b"username,email,first_name,last_name,user_type\nsa_imp_t,sa_imp_t@example.com,Sa,Imp,Student\n"
    r = client.post("/api/users/bulk-import", headers=h, data={"organisation": str(other)},
                    files={"file": ("u.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200, r.text
    assert _membership(db, "sa_imp_t").organisation_id == other


def test_new_members_get_their_role_and_admins_see_both_dashboards(client, db, login_as):
    r = _signup(client, "solo_role_t", user_type="researcher")
    me = r.json()["user"]
    assert [x["name"] for x in me["roles"]] == ["Researcher"]
    assert me["capabilities"]["can_access_other_documents"] is True

    _register_university(client)
    _approve(client, login_as, db)
    h = {"Authorization": f"Bearer {_login(client, 'uniadmin_t').json()['access_token']}"}
    sel = client.get("/api/documents/dashboard-selection", headers=h).json()
    assert sel["can_access_content_lab"] and sel["can_access_other_documents"] and sel["redirect"] is None

    client.post("/api/org/members", headers=h, json={"username": "stud_role_t", "email": "stud_role_t@example.com",
                                                     "first_name": "Stu", "user_type": "student", "password": "secret123",
                                                     "send_welcome_email": False})
    stud = client.post("/api/auth/login", json={"username": "stud_role_t", "password": "secret123",
                                                "privacy_consent": True}).json()["user"]
    assert [x["name"] for x in stud["roles"]] == ["Student"] and stud["capabilities"]["can_upload"] is True


def test_superadmin_user_list_shows_one_workspace_at_a_time(client, db, login_as):
    h = login_as("admin")
    other = client.post("/api/superadmin/organisations", headers=h, data={
        "name": "Workspace Z", "admin_username": "wsz_admin", "admin_email": "wsz@example.com",
        "admin_first_name": "Zed", "admin_password": "secret123"}).json()["id"]
    smbt = db.execute(select(Organisation.id).where(Organisation.slug == "smbt")).scalar_one()
    # the workspace chosen in the superadmin top bar decides the list
    default = client.get("/api/users/manage", headers={**h, "X-Workspace": str(smbt)}).json()
    assert default["organisation_filter"] == str(smbt)
    names = {u["username"] for u in default["users"]}
    assert "teacher1" in names and "wsz_admin" not in names and "admin" not in names
    assert {u["organisation"] for u in default["users"]} == {"SMBT"}
    only_z = client.get("/api/users/manage", headers=h, params={"organisation": str(other)}).json()
    assert [u["username"] for u in only_z["users"]] == ["wsz_admin"]
    assert client.get("/api/users/manage", headers=h).json()["organisation_filter"] == "all"
    everyone = {u["username"] for u in client.get("/api/users/manage", headers=h, params={"organisation": "all"}).json()["users"]}
    assert {"teacher1", "wsz_admin", "admin"} <= everyone


def test_username_check_and_suggestions(client):
    _signup(client, "asha.rao", user_type="researcher")
    taken = client.get("/api/auth/username-check", params={"username": "asha.rao", "first_name": "Asha", "last_name": "Rao"}).json()
    assert taken["available"] is False and "taken" in taken["message"]
    assert taken["suggestions"] and "asha.rao" not in taken["suggestions"]
    for s in taken["suggestions"]:
        assert client.get("/api/auth/username-check", params={"username": s}).json()["available"] is True
    free = client.get("/api/auth/username-check", params={"username": "brand_new_name_t"}).json()
    assert free["available"] is True and free["suggestions"] == []
    bad = client.get("/api/auth/username-check", params={"username": "no spaces!"}).json()
    assert bad["available"] is False and "letters" in bad["message"]
    # name only: suggestions before anything is typed
    assert client.get("/api/auth/username-check", params={"first_name": "Ravi", "last_name": "Kumar"}).json()["suggestions"]
    assert _signup(client, "ab", user_type="researcher").json()["error"].startswith("Username:")
