"""FastAPI dependencies for authentication and authorisation.

Tokens are accepted from the `Authorization: Bearer <jwt>` header, or from a
`?token=` query parameter — the latter is needed where the browser fetches a URL
directly (PDF viewer, file downloads, iframes, OnlyOffice).
"""
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.permissions import can, has_module_permission, is_admin_like, is_manager_like
from app.core.security import decode_access_token, password_fingerprint
from app.core.tenancy import membership_blocked, set_viewer
from app.database import get_db
from app.models import User


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token")


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    set_viewer(db, None)
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        return None
    if "pwd" in payload and payload["pwd"] != password_fingerprint(user.password):
        return None  # password changed since this token was issued
    if membership_blocked(db, user):
        return None  # workspace pending / suspended, or membership not approved yet
    set_viewer(db, user, _superadmin_workspace(request, db) if user.is_superuser else None)
    return user


def _superadmin_workspace(request: Request, db: Session) -> int | None:
    """Workspace chosen in the superadmin top bar: `X-Workspace` header (or `?workspace=` for links).
    Empty or "all" means the whole platform."""
    raw = request.headers.get("X-Workspace") or request.query_params.get("workspace") or ""
    if not raw.isdigit():
        return None
    from app.models import Organisation
    return int(raw) if db.get(Organisation, int(raw)) is not None else None


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Superuser access required")
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    if not (user.is_staff or user.is_superuser):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff access required")
    return user


def require_manager(user: User = Depends(get_current_user)) -> User:
    if not (is_manager_like(user) or user.is_superuser):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager access required")
    return user


def require_admin_like(user: User = Depends(get_current_user)) -> User:
    """is_staff or is_superuser or manager."""
    if not is_admin_like(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to access this page.")
    return user


def require_permission(dashboard: str, module: str, action: str) -> Callable[..., User]:
    """Dependency factory: Depends(require_permission('content_lab', 'cl_upload', 'view'))."""

    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if not has_module_permission(db, user, dashboard, module, action):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action.")
        return user

    return checker


def require_capability(name: str) -> Callable[..., User]:
    """Dependency factory using the Django helper names: Depends(require_capability('can_upload'))."""

    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if not can(db, user, name):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action.")
        return user

    return checker
