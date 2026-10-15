"""Single sign-on from TuraVector into the other Tura applications.

Research Assistant / TuraGrammar ("ticket" apps): TuraVector signs a short-lived JWT
(HS256, per-app shared secret) and opens `<APP_SSO_URL>#ticket=<jwt>`. The ticket sits in
the URL fragment, so it never reaches server logs or Referer headers. The app's /sso page
posts it to its own `POST /api/auth/sso`, which verifies it, finds or creates the user by
email and returns that app's normal login token. Claims:

    iss="turavector", aud=<app key>, sub=<TuraVector user id>, email, name, iat, exp, jti

Tura LMS (Moodle): the backend asks Moodle's auth_userkey plugin for a one-time login URL
for the user's email (the plugin creates the account if "Create user" is enabled).
"""
import datetime
import secrets

import httpx
import jwt

from app.config import settings
from app.core.utils import full_name
from app.models import User
from app.services.external_apps import ExternalApp

ISSUER = "turavector"  # TuraGrammar and Research Assistant accept "turavector" and the old "turadome"


class SSOError(Exception):
    pass


def sso_configured(app: ExternalApp) -> bool:
    if app.key == "ext_lms":
        return bool(settings.TURA_LMS_WS_TOKEN and settings.TURA_LMS_BASE_URL)
    url_setting, secret_setting = _ticket_settings(app)
    return bool(getattr(settings, url_setting) and getattr(settings, secret_setting))


def launch_url(app: ExternalApp, user: User) -> str:
    """URL that opens `app` already signed in as `user`; the plain app URL when SSO isn't set up."""
    if not sso_configured(app):
        return app.url
    if app.key == "ext_lms":
        return _moodle_login_url(user)
    url_setting, secret_setting = _ticket_settings(app)
    return f"{getattr(settings, url_setting)}#ticket={make_ticket(app.key, user, getattr(settings, secret_setting))}"


def make_ticket(audience: str, user: User, secret: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": audience,
        "sub": str(user.id),
        "email": (user.email or "").strip().lower(),
        "name": full_name(user) or user.username,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=settings.SSO_TICKET_TTL_SECONDS),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _ticket_settings(app: ExternalApp) -> tuple[str, str]:
    prefix = app.url_setting.removesuffix("_URL")  # TURAGRAMMAR_URL -> TURAGRAMMAR
    return f"{prefix}_SSO_URL", f"{prefix}_SSO_SECRET"


def _moodle_login_url(user: User) -> str:
    email = (user.email or "").strip().lower()
    params = {
        "wstoken": settings.TURA_LMS_WS_TOKEN,
        "wsfunction": "auth_userkey_request_login_url",
        "moodlewsrestformat": "json",
        "user[email]": email,
        "user[username]": email,
        "user[firstname]": user.first_name or user.username,
        "user[lastname]": user.last_name or "-",
    }
    try:
        r = httpx.post(f"{settings.TURA_LMS_BASE_URL.rstrip('/')}/webservice/rest/server.php", data=params, timeout=15)
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SSOError("Could not reach Tura LMS. Please try again.") from exc
    if not isinstance(data, dict) or not data.get("loginurl"):
        message = data.get("message") if isinstance(data, dict) else None
        raise SSOError(f"Tura LMS refused the sign-in{': ' + message if message else '.'}")
    return data["loginurl"]
