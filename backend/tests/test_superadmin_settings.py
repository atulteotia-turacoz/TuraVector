"""System Settings — always against a tmp copy of .env; the real backend/.env is never touched."""
import json

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Base
from app.services import superadmin_settings as svc

API = "/api/superadmin/settings"
LOG = Base.metadata.tables["django_admin_log"]

ENV_TEMPLATE = """# ---- test env ----
DEBUG=True
SECRET_KEY=super-secret-signing-key
DB_PASSWORD=db-pass-1234

# Email
EMAIL_BACKEND=console
DEFAULT_FROM_EMAIL=noreply@turadome.com
SPRINGER_API_KEY=springer-key-abcd

# trailing comment
"""


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    real = svc.ENV_PATH
    real_before = real.read_bytes() if real.exists() else None
    path = tmp_path / ".env"
    path.write_text(ENV_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(svc, "ENV_PATH", path)
    # restore any live setting a test changes
    for key in svc.EDITABLE_KEYS:
        monkeypatch.setattr(settings, key, getattr(settings, key))
    monkeypatch.setattr(settings, "SPRINGER_API_KEY", "springer-key-abcd")
    yield path
    assert (real.read_bytes() if real.exists() else None) == real_before, "real .env was modified!"


def test_requires_superuser(client, login_as, env_file):
    h = login_as("teacher1")
    assert client.get(API, headers=h).status_code == 403
    assert client.put(API, json={"EMAIL_PORT": 25}, headers=h).status_code == 403
    assert client.post(f"{API}/SPRINGER_API_KEY/reveal", headers=h).status_code == 403


def test_list_masks_secrets_and_hides_db_password(client, login_as, env_file):
    data = client.get(API, headers=login_as("admin")).json()
    titles = [s["title"] for s in data["sections"]]
    assert titles[0] == "Application URLs" and titles[-1] == "Read-only info"
    items = {k["key"]: k for s in data["sections"] for k in s["keys"]}
    assert items["SPRINGER_API_KEY"]["value"] == "••••abcd" and items["SPRINGER_API_KEY"]["is_secret"]
    assert items["EMAIL_USE_TLS"]["type"] == "bool" and items["EMAIL_PORT"]["type"] == "int"
    assert items["EMAIL_BACKEND"]["type"] == "choice"
    assert items["DB_PASSWORD"]["value"] == "" and items["SECRET_KEY"]["value"] == ""
    assert items["DB_HOST"]["read_only"] and items["DB_HOST"]["requires_restart"]
    assert items["CORS_ORIGINS"]["requires_restart"] and items["MEDIA_ROOT"]["requires_restart"]
    onlyoffice = next(s for s in data["sections"] if s["title"] == "OnlyOffice")
    editor = next(k for k in onlyoffice["keys"] if k["key"] == "ONLYOFFICE_EDITOR_JWT_SECRET")
    assert editor["is_secret"] and not editor["read_only"] and not editor["requires_restart"]
    if settings.ONLYOFFICE_EDITOR_JWT_SECRET:
        assert settings.ONLYOFFICE_EDITOR_JWT_SECRET not in json.dumps(data)
    body = json.dumps(data)
    assert settings.SECRET_KEY not in body
    if settings.DB_PASSWORD:
        assert settings.DB_PASSWORD not in body


def test_reveal(client, login_as, env_file):
    h = login_as("admin")
    assert client.post(f"{API}/SPRINGER_API_KEY/reveal", headers=h).json()["value"] == "springer-key-abcd"
    assert client.post(f"{API}/DB_PASSWORD/reveal", headers=h).status_code == 400
    assert client.post(f"{API}/SECRET_KEY/reveal", headers=h).status_code == 400
    assert client.post(f"{API}/EMAIL_HOST/reveal", headers=h).status_code == 400
    assert client.post(f"{API}/NOPE/reveal", headers=h).status_code == 404


def test_update_rejects_unknown_readonly_and_bad_types(client, login_as, env_file):
    h = login_as("admin")
    assert client.put(API, json={"NOPE": "x"}, headers=h).status_code == 400
    assert client.put(API, json={"DB_HOST": "x"}, headers=h).status_code == 400
    assert client.put(API, json={"SECRET_KEY": "x"}, headers=h).status_code == 400
    r = client.put(API, json={"EMAIL_PORT": "not-a-number"}, headers=h)
    assert r.status_code == 400 and "EMAIL_PORT" in r.json()["detail"]["errors"]
    r = client.put(API, json={"EMAIL_BACKEND": "carrier-pigeon"}, headers=h)
    assert r.status_code == 400
    assert env_file.read_text() == ENV_TEMPLATE


def test_update_rewrites_env_applies_live_and_logs(client, login_as, env_file, db):
    h = login_as("admin")
    start = db.execute(select(func.coalesce(func.max(LOG.c.id), 0))).scalar_one()
    r = client.put(API, json={
        "EMAIL_PORT": "2525", "EMAIL_USE_TLS": False, "DEFAULT_FROM_EMAIL": "ops@turadome.com",
        "SPRINGER_API_KEY": "",            # blank secret keeps current value
        "CORS_ORIGINS": "http://a.test, http://b.test", "ELSEVIER_API_KEY": "new elsevier#key",
    }, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "SPRINGER_API_KEY" not in body["changed"]
    assert body["requires_restart"] == ["CORS_ORIGINS"]
    # live
    assert settings.EMAIL_PORT == 2525 and settings.EMAIL_USE_TLS is False
    assert settings.DEFAULT_FROM_EMAIL == "ops@turadome.com" and settings.SPRINGER_API_KEY == "springer-key-abcd"
    # file: comments and order kept, lines updated in place, new keys appended, backup written
    text = env_file.read_text()
    lines = text.splitlines()
    assert lines[0] == "# ---- test env ----" and "# trailing comment" in lines
    assert lines.index("DEFAULT_FROM_EMAIL=ops@turadome.com") == ENV_TEMPLATE.splitlines().index(
        "DEFAULT_FROM_EMAIL=noreply@turadome.com")
    assert "SPRINGER_API_KEY=springer-key-abcd" in lines
    assert "EMAIL_PORT=2525" in lines and "EMAIL_USE_TLS=False" in lines
    assert 'ELSEVIER_API_KEY="new elsevier#key"' in lines
    assert (env_file.parent / ".env.bak").read_text() == ENV_TEMPLATE
    # the file parses back to the same values
    from dotenv import dotenv_values
    parsed = dotenv_values(env_file)
    assert parsed["ELSEVIER_API_KEY"] == "new elsevier#key" and parsed["CORS_ORIGINS"] == "http://a.test, http://b.test"
    # admin log names the keys, never the values
    rows = [dict(x) for x in db.execute(select(LOG).where(LOG.c.id > start)).mappings().all()]
    assert len(rows) == 1 and rows[0]["action_flag"] == 2
    msg = json.loads(rows[0]["change_message"])
    assert set(msg[0]["changed"]["fields"]) == set(body["changed"])
    assert "new elsevier#key" not in rows[0]["change_message"] and "2525" not in rows[0]["change_message"]


def test_no_change_does_not_write(client, login_as, env_file):
    h = login_as("admin")
    r = client.put(API, json={"EMAIL_BACKEND": settings.EMAIL_BACKEND}, headers=h)
    assert r.json()["changed"] == []
    assert not (env_file.parent / ".env.bak").exists()


def test_clear_secret_with_whitespace(client, login_as, env_file):
    h = login_as("admin")
    r = client.put(API, json={"SPRINGER_API_KEY": " "}, headers=h)
    assert r.json()["changed"] == ["SPRINGER_API_KEY"]
    assert settings.SPRINGER_API_KEY == ""
    assert 'SPRINGER_API_KEY=""' in env_file.read_text().splitlines()


def test_sso_settings_editable_and_applied_live(client, login_as, env_file):
    h = login_as("admin")
    sections = {s["title"]: {k["key"]: k for k in s["keys"]} for s in client.get(API, headers=h).json()["sections"]}
    sso = sections["Tura applications — single sign-on"]
    assert sso["TURAGRAMMAR_SSO_SECRET"]["is_secret"] and sso["TURAGRAMMAR_SSO_SECRET"]["can_generate"]
    assert sso["TURA_LMS_WS_TOKEN"]["is_secret"] and not sso["TURA_LMS_WS_TOKEN"].get("can_generate")

    bad = client.put(API, json={"TURAGRAMMAR_SSO_SECRET": "short", "SSO_TICKET_TTL_SECONDS": 5000}, headers=h)
    assert bad.status_code == 400
    errors = bad.json()["detail"]["errors"]
    assert "TURAGRAMMAR_SSO_SECRET" in errors and "SSO_TICKET_TTL_SECONDS" in errors

    secret = "g" * 48
    r = client.put(API, json={"TURAGRAMMAR_SSO_URL": "https://grammar.example/sso", "TURAGRAMMAR_SSO_SECRET": secret}, headers=h)
    assert r.status_code == 200 and r.json()["requires_restart"] == []
    assert secret not in json.dumps(client.get(API, headers=h).json())
    # takes effect immediately for the dashboard-selection card
    url = client.post("/api/documents/external-apps/ext_turagrammar/launch", headers=h).json()["url"]
    assert url.startswith("https://grammar.example/sso#ticket=")
