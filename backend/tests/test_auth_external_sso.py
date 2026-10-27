"""Single sign-on launch URLs for the other Tura applications (dashboard-selection cards)."""
import jwt
import pytest

from app.config import settings
from app.models import User
from app.services import external_apps_sso

SECRET = "x" * 40


def _launch(client, h, key):
    return client.post(f"/api/documents/external-apps/{key}/launch", headers=h)


@pytest.fixture
def grammar_sso(monkeypatch):
    monkeypatch.setattr(settings, "TURAGRAMMAR_SSO_URL", "https://grammar.example/sso")
    monkeypatch.setattr(settings, "TURAGRAMMAR_SSO_SECRET", SECRET)


def test_without_sso_settings_opens_plain_app_url(client, login_as, monkeypatch):
    monkeypatch.setattr(settings, "TURAGRAMMAR_SSO_URL", "")
    r = _launch(client, login_as("admin"), "ext_turagrammar")
    assert r.status_code == 200 and r.json()["url"] == settings.TURAGRAMMAR_URL


def test_ticket_is_signed_for_the_app(client, login_as, db, grammar_sso):
    r = _launch(client, login_as("admin"), "ext_turagrammar")
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("https://grammar.example/sso#ticket=")
    claims = jwt.decode(url.split("#ticket=", 1)[1], SECRET, algorithms=["HS256"], audience="ext_turagrammar", issuer="turavector")
    admin = db.query(User).filter(User.username == "admin").one()
    assert claims["sub"] == str(admin.id) and claims["email"] == (admin.email or "").lower()
    assert claims["exp"] - claims["iat"] == settings.SSO_TICKET_TTL_SECONDS
    # Another app's secret/audience must not accept it
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(url.split("#ticket=", 1)[1], SECRET, algorithms=["HS256"], audience="ext_research_assistant")


def test_sso_flag_on_cards(client, login_as, grammar_sso):
    apps = {a["key"]: a for a in client.get("/api/documents/dashboard-selection", headers=login_as("admin")).json()["apps"]}
    assert apps["ext_turagrammar"]["sso"] is True


def test_hidden_card_cannot_launch(client, login_as, grammar_sso):
    assert _launch(client, login_as("teacher1"), "ext_turagrammar").status_code == 403
    assert _launch(client, login_as("admin"), "nope").status_code == 403


def test_moodle_login_url(client, login_as, monkeypatch):
    monkeypatch.setattr(settings, "TURA_LMS_WS_TOKEN", "tok")
    sent = {}

    class Resp:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    def fake_post(url, data, timeout):
        sent.update(url=url, data=data)
        return Resp({"loginurl": "https://lms.example/auth/userkey/login.php?key=abc"})

    monkeypatch.setattr(external_apps_sso.httpx, "post", fake_post)
    r = _launch(client, login_as("admin"), "ext_lms")
    assert r.status_code == 200 and r.json()["url"] == "https://lms.example/auth/userkey/login.php?key=abc"
    assert sent["url"].endswith("/webservice/rest/server.php")
    assert sent["data"]["wsfunction"] == "auth_userkey_request_login_url" and sent["data"]["wstoken"] == "tok"

    monkeypatch.setattr(external_apps_sso.httpx, "post", lambda url, data, timeout: Resp({"exception": "x", "message": "Invalid token"}))
    r = _launch(client, login_as("admin"), "ext_lms")
    assert r.status_code == 502 and "Invalid token" in r.json()["error"]


def test_turastatistics_ticket(client, login_as, monkeypatch):
    monkeypatch.setattr(settings, "TURASTATISTICS_SSO_URL", "https://statistics.example/sso")
    monkeypatch.setattr(settings, "TURASTATISTICS_SSO_SECRET", SECRET)
    r = _launch(client, login_as("admin"), "ext_turastatistics")
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("https://statistics.example/sso#ticket=")
    claims = jwt.decode(url.split("#ticket=", 1)[1], SECRET, algorithms=["HS256"], audience="ext_turastatistics", issuer="turavector")
    assert claims["email"] and claims["jti"]


def test_turaslr_ticket(client, login_as, monkeypatch):
    monkeypatch.setattr(settings, "TURASLR_SSO_URL", "https://slr.example/sso")
    monkeypatch.setattr(settings, "TURASLR_SSO_SECRET", SECRET)
    url = _launch(client, login_as("admin"), "ext_turaslr").json()["url"]
    assert url.startswith("https://slr.example/sso#ticket=")
    jwt.decode(url.split("#ticket=", 1)[1], SECRET, algorithms=["HS256"], audience="ext_turaslr", issuer="turavector")
