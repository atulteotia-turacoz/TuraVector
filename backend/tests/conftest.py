"""Test harness — SAFE against the real database.

Every test runs inside one outer transaction on tura_dome_new that is ROLLED BACK
afterwards (app commits become SAVEPOINT releases), uploads go to a temp MEDIA_ROOT,
and outgoing email is stubbed. Nothing a test does survives the test.

Usage:
    def test_something(client, login_as):
        h = login_as("admin")              # Authorization header for an existing user
        r = client.get("/api/...", headers=h)
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token
from app.database import engine, get_db
from app.main import app
from app.models import Organisation, User


@pytest.fixture()
def db():
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    # users created by fixtures (no signed-in creator) join SMBT, where all existing data lives
    session.info["tenancy_default_org"] = session.execute(
        select(Organisation.id).where(Organisation.slug == "smbt")).scalar_one()
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture()
def sent_emails(monkeypatch):
    sent = []
    import app.core.email as email_mod
    monkeypatch.setattr(email_mod, "deliver", lambda db, subject, message, from_email, to, html=None: sent.append(
        {"subject": subject, "message": message, "to": to}))
    return sent


@pytest.fixture()
def client(db, tmp_path, monkeypatch, sent_emails):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    from app.services import billing
    monkeypatch.setattr(billing, "SEND_IN_BACKGROUND", False)  # a thread would write outside the test transaction
    monkeypatch.setattr(settings, "INVOICE_REMINDERS_AUTORUN", False)
    def _request_db():
        # one shared session: each request starts without a viewer and leaves none behind for the test
        db.info.pop("tenancy_viewer", None)
        if db.info.get("fresh_identity_map_per_request"):
            # behave like production's fresh per-request session: nothing loaded earlier (by the test or
            # another user's request) is served from the identity map past the organisation filter
            db.flush()
            db.expunge_all()
        try:
            yield db
        finally:
            db.info.pop("tenancy_viewer", None)
    app.dependency_overrides[get_db] = _request_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def login_as(db):
    def _login(username: str) -> dict:
        user = db.query(User).filter(User.username == username).one()
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}
    return _login
