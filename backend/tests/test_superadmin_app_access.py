"""Dashboard-selection cards are set per user (Visible / Hidden); roles never decide them."""
from app.models import RolePermission, User, UserRole
from app.services.external_apps import card_by_key, card_permission


def _cards(client, h):
    d = client.get("/api/documents/dashboard-selection", headers=h).json()
    return {"content_lab": d["can_access_content_lab"], "other_documents": d["can_access_other_documents"],
            **{a["key"]: True for a in d["apps"]}}


def _set(client, h, user_id, card, visible):
    return client.post("/api/superadmin/app-access/user", headers=h, json={"user_id": user_id, "card": card, "visible": visible})


def test_requires_superuser(client, login_as):
    assert client.get("/api/superadmin/app-access", headers=login_as("teacher1")).status_code == 403
    assert _set(client, login_as("teacher1"), 1, "ext_lms", True).status_code == 403


def test_superuser_sees_all_cards(client, login_as):
    assert set(_cards(client, login_as("admin"))) >= {"content_lab", "other_documents", "ext_research_assistant", "ext_lms", "ext_turagrammar"}


def test_visible_and_hidden_per_user(client, login_as, db):
    admin, teacher = login_as("admin"), login_as("teacher1")
    t = db.query(User).filter(User.username == "teacher1").one()
    assert "ext_lms" not in _cards(client, teacher)
    r = _set(client, admin, t.id, "ext_lms", True)
    assert r.status_code == 200 and r.json()["visible"] is True
    assert "ext_lms" in _cards(client, teacher)
    _set(client, admin, t.id, "ext_lms", False)
    assert "ext_lms" not in _cards(client, teacher)
    card = next(c for c in client.get(f"/api/superadmin/app-access/users/{t.id}", headers=admin).json()["cards"] if c["key"] == "ext_lms")
    assert card["visible"] is False and card["source"] == "hidden"


def test_roles_do_not_decide_cards(client, login_as, db):
    """Granting a card's permission to the user's role must not show the card."""
    t = db.query(User).filter(User.username == "teacher1").one()
    role_id = db.query(UserRole).filter(UserRole.user_id == t.id).first().role_id
    db.add(RolePermission(role_id=role_id, permission_id=card_permission(db, card_by_key(db, "ext_turagrammar")).id))
    db.commit()
    assert "ext_turagrammar" not in _cards(client, login_as("teacher1"))


def test_hidden_content_lab_blocks_dashboard_even_with_role(client, login_as, db):
    admin = login_as("admin")
    u = db.query(User).filter(User.username == "teacher1").one()
    _set(client, admin, u.id, "content_lab", False)
    assert _cards(client, login_as("teacher1"))["content_lab"] is False
    _set(client, admin, u.id, "content_lab", True)
    assert _cards(client, login_as("teacher1"))["content_lab"] is True


def test_bulk_and_unknown(client, login_as):
    admin = login_as("admin")
    assert client.post("/api/superadmin/app-access/bulk", headers=admin, json={"card": "ext_lms", "visible": True}).status_code == 200
    assert _set(client, admin, 1, "nope", True).status_code == 404


def test_new_user_starts_with_content_lab_visible(client, login_as, db):
    from app.core.security import make_password
    from app.models import utcnow
    u = User(username="cardtest_newuser", email="cardtest_newuser@example.com", password=make_password("x"), first_name="Card",
             last_name="Test", is_superuser=0, is_staff=0, is_active=1, user_type="student", is_manager=0, timezone="UTC", date_joined=utcnow())
    db.add(u); db.commit()
    cards = {c["key"]: c for c in client.get(f"/api/superadmin/app-access/users/{u.id}", headers=login_as("admin")).json()["cards"]}
    assert cards["content_lab"]["visible"] is True and cards["ext_lms"]["visible"] is False
