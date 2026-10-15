"""Core session endpoints: login, logout, current user, public client config.

Port of authentication.views.login_view / logout_view. Sessions are replaced by
JWTs; everything else (validation, rate limit, consent, LoginLog) is unchanged.
"""
import re
import time
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.permissions import get_all_roles, is_admin_like, is_manager_like, user_capabilities
from app.core.security import check_password, token_for
from app.core.utils import get_client_ip, get_user_agent, iso, user_type_code, user_type_display
from app.database import get_db
from app.models import LoginLog, User, UserConsent, utcnow

from app.core.tenancy import is_org_admin, membership_blocked, membership_of, organisation_of  # noqa: E402
from app.services import billing  # noqa: E402
from app.services.org_common import org_payload  # noqa: E402

router = APIRouter(prefix="/api/auth", tags=["auth"])

CONSENT_TEXT = "I consent to the processing of my personal data in accordance with the Privacy Policy."

# Max 5 failed attempts per IP per 15 minutes; a process-local store (cleared on backend restart).
_attempts: dict[str, tuple[int, float]] = {}
_attempts_lock = Lock()
_RATE_WINDOW = 900
_RATE_MAX = 5
# Login rate limiting is temporarily disabled; set to True to re-activate the block.
_RATE_LIMIT_ENABLED = False


def _get_attempts(ip: str) -> int:
    with _attempts_lock:
        count, expires = _attempts.get(ip, (0, 0.0))
        if expires < time.time():
            _attempts.pop(ip, None)
            return 0
        return count


def _bump_attempts(ip: str, count: int) -> None:
    with _attempts_lock:
        _attempts[ip] = (count + 1, time.time() + _RATE_WINDOW)


def _clear_attempts(ip: str) -> None:
    with _attempts_lock:
        _attempts.pop(ip, None)


def create_login_log(db: Session, request: Request, user: User | None = None, username_attempted: str = "",
                     status: str = "failed", failure_reason: str = "") -> None:
    try:
        db.add(LoginLog(
            user_id=user.id if user else None,
            username_attempted=(username_attempted or (user.username if user else ""))[:150],
            email_attempted=user.email if user else "",
            status=status,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            session_key=None,
            failure_reason=failure_reason,
            location_info={},
            device_info={},
        ))
        db.commit()
    except Exception:  # noqa: BLE001 — logging must never break login
        db.rollback()


def record_user_consent(db: Session, user: User, request: Request, consent_given: bool = True,
                        consent_type: str = "privacy_policy", consent_text: str = "",
                        consent_version: str = "1.0") -> None:
    try:
        db.add(UserConsent(
            user_id=user.id, consent_type=consent_type, consent_given=int(consent_given),
            consent_text=consent_text, consent_version=consent_version,
            ip_address=get_client_ip(request), user_agent=get_user_agent(request), is_active=1,
        ))
        db.commit()
    except IntegrityError:
        # unique (user, consent_type, consent_version): already recorded, as in Django
        db.rollback()


def serialize_me(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": f"{user.first_name} {user.last_name}".strip() or user.username,
        "phone": user.phone,
        "address": user.address,
        "timezone": user.timezone,
        "user_type": user.user_type,
        "user_type_code": user_type_code(user),
        # a workspace admin is shown as e.g. "University Admin" rather than their account type
        "user_type_display": (f"{organisation_of(db, user).kind.title()} Admin" if is_org_admin(user, db)
                              # a Turacoz user who only handles invoices (no role such as Reviewer)
                              else "Financial Manager" if (not user.is_superuser and billing.is_approver(db, user)
                                                           and not get_all_roles(db, user))
                              else user_type_display(user)),
        "user_type_new_id": user.user_type_new_id,
        "is_manager": bool(user.is_manager),
        "is_staff": bool(user.is_staff),
        "is_superuser": bool(user.is_superuser),
        "is_active": bool(user.is_active),
        "is_manager_like": is_manager_like(user),
        "is_admin_like": is_admin_like(user),
        "date_joined": iso(user.date_joined),
        "last_login": iso(user.last_login),
        "roles": [{"id": r.id, "name": r.name} for r in get_all_roles(db, user)],
        "organisation": org_payload(organisation_of(db, user), membership_of(db, user)),
        "is_org_admin": is_org_admin(user, db),
        "is_invoice_approver": billing.is_approver(db, user) if not user.is_superuser else True,
        "capabilities": user_capabilities(db, user),
    }


class LoginIn(BaseModel):
    username: str = ""
    password: str = ""
    privacy_consent: bool = False


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    username = body.username.strip()
    password = body.password

    if len(username) > 150 or len(password) > 128:
        raise HTTPException(400, "Invalid input length.")
    if not re.match(r"^[a-zA-Z0-9@._+-]+$", username):
        raise HTTPException(400, "Invalid username format.")

    ip = get_client_ip(request)
    attempts = _get_attempts(ip)
    if _RATE_LIMIT_ENABLED and attempts >= _RATE_MAX:
        create_login_log(db, request, username_attempted=username, status="blocked",
                         failure_reason="Rate limited - too many attempts")
        raise HTTPException(429, "Too many login attempts. Please try again later.")

    if not body.privacy_consent:
        raise HTTPException(400, "You must consent to the processing of your personal data in accordance with the Privacy Policy.")

    # ModelBackend: lookup by username, check password, reject inactive users
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or not check_password(password, user.password) or not user.is_active:
        _bump_attempts(ip, attempts)
        create_login_log(db, request, username_attempted=username, status="failed", failure_reason="Invalid credentials")
        raise HTTPException(401, "Invalid username or password")

    _clear_attempts(ip)
    blocked = membership_blocked(db, user)
    if blocked:
        create_login_log(db, request, user=user, username_attempted=username, status="blocked", failure_reason=blocked[:250])
        raise HTTPException(403, blocked)
    user.last_login = utcnow()
    db.commit()
    record_user_consent(db, user, request, consent_text=CONSENT_TEXT)
    create_login_log(db, request, user=user, username_attempted=username, status="success")

    return {"access_token": token_for(user), "token_type": "bearer", "user": serialize_me(db, user)}


@router.post("/logout")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    create_login_log(db, request, user=user, username_attempted=user.username, status="logout")
    latest = db.execute(
        select(LoginLog).where(LoginLog.user_id == user.id, LoginLog.status == "success")
        .order_by(LoginLog.login_time.desc()).limit(1)
    ).scalar_one_or_none()
    if latest:
        latest.logout_time = utcnow()
        db.commit()
    return {"success": True}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return serialize_me(db, user)


config_router = APIRouter(prefix="/api", tags=["config"])


@config_router.get("/config")
def client_config():
    """Equivalent of turadome_django.context_processors.settings_context."""
    key = settings.PDFTRON_LICENSE_KEY or ""
    return {
        "PDFTRON_ENABLED": settings.PDFTRON_ENABLED,
        "PDFTRON_LICENSE_KEY": key,
        "PDFTRON_VERSION": settings.PDFTRON_VERSION,
        "PDFTRON_PATH": settings.PDFTRON_PATH,
        "PDFTRON_LICENSED": bool(key.strip()),
        "ALLOW_DOCUMENT_DOWNLOAD": settings.ALLOW_DOCUMENT_DOWNLOAD,
        "DOCUMENT_WATERMARK": settings.DOCUMENT_WATERMARK,
        "DOCUMENT_PRINT_DISABLED": settings.DOCUMENT_PRINT_DISABLED,
        "ENABLE_ONLYOFFICE_EDITOR": settings.ENABLE_ONLYOFFICE_EDITOR,
        "ONLYOFFICE_DOCUMENT_SERVER_URL": settings.ONLYOFFICE_DOCUMENT_SERVER_URL,
        "MEDIA_URL": f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{settings.MEDIA_URL}",
        "TIME_ZONE": settings.TIME_ZONE,
    }
