from app.models import LoginLog


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_and_shell(client, login_as):
    h = login_as("admin")
    me = client.get("/api/auth/me", headers=h).json()
    assert me["is_superuser"] and me["capabilities"]["can_access_library"]
    assert client.get("/api/library/quick-stats", headers=h).json()["success"]
    assert "unread_count" in client.get("/api/notifications/recent", headers=h).json()


def test_failed_login_is_logged_and_rolled_back(client, db):
    before = db.query(LoginLog).count()
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong", "privacy_consent": True})
    assert r.status_code == 401
    assert db.query(LoginLog).count() == before + 1   # visible inside the test transaction only


def test_password_change_invalidates_old_tokens(client, db):
    from app.core.security import make_password, token_for
    from app.models import User
    user = db.query(User).filter(User.username == "teacher1").one()
    h = {"Authorization": f"Bearer {token_for(user)}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    user.password = make_password("a-new-password")
    db.commit()  # savepoint only — rolled back after the test
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_for(user)}"}).status_code == 200
