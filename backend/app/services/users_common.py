"""Shared helpers for the "users" module (manager dashboard, user admin, RBAC screens).

Ports small pieces of Django behaviour that the views rely on:
`get_full_name`, `get_*_display` for Permission choices, `create_user`, and the
"permissions_by_dashboard" grouping used by several templates.
"""
import datetime
import unicodedata
from typing import Any

import pytz
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import is_manager_like
from app.core.security import make_password
from app.core.utils import iso, user_type_display
from app.models import (
    Document, DocumentSharing, Permission, Role, RolePermission, User, UserPermission, UserRole, UserType, utcnow,
)

# ---- authentication.models.Permission choices -------------------------------------------------
DASHBOARD_CHOICES = {
    "content_lab": "Content Lab Management",
    "other_documents": "Other Documents",
}
MODULE_CHOICES = {
    "cl_dashboard_access": "Content Lab - Dashboard Access",
    "cl_dashboard": "Content Lab - Dashboard",
    "cl_upload": "Content Lab - Upload Document",
    "cl_documents": "Content Lab - My Documents",
    "cl_review": "Content Lab - Review Documents",
    "cl_completed": "Content Lab - Completed",
    "cl_library": "Content Lab - Reference Library",
    "cl_archive": "Content Lab - Document Archive",
    "cl_manager_dashboard": "Content Lab - Manager Dashboard",
    "cl_reviewer_dashboard": "Content Lab - Reviewer Dashboard",
    "cl_manage_users": "Content Lab - Manage Users",
    "cl_users": "Content Lab - Users",
    "cl_roles": "Content Lab - Roles",
    "cl_permissions": "Content Lab - Permissions",
    "cl_reports": "Content Lab - Reports",
    "cl_email": "Content Lab - Email",
    "cl_email_settings": "Content Lab - Email Settings",
    "cl_mail_logs": "Content Lab - Mail Logs",
    "od_dashboard_access": "Other Documents - Dashboard Access",
    "od_dashboard": "Other Documents - Dashboard",
    "od_projects": "Other Documents - Projects",
    "od_journals": "Other Documents - Journal Selector",
    "od_conferences": "Other Documents - Conference Selector",
    "od_analytics": "Other Documents - Analytics",
    "od_export": "Other Documents - Export Data",
    "od_settings": "Other Documents - Settings",
}
ACTION_CHOICES = {
    "view": "View", "create": "Create", "edit": "Edit", "delete": "Delete", "export": "Export",
    "approve": "Approve", "review": "Review", "manage": "Manage",
}
LEGACY_USER_TYPES = [("student", "Student"), ("teacher", "Teacher"), ("reviewer", "Reviewer"), ("manager", "Manager")]

STAGE_LABELS = {0: "Draft", 1: "Under Review", 2: "Approved", 3: "Draft Under Revision"}


def dashboard_display(p: Permission) -> str:
    return DASHBOARD_CHOICES.get(p.dashboard, p.dashboard)


def module_display(p: Permission) -> str:
    return MODULE_CHOICES.get(p.module, p.module)


def action_display(p: Permission) -> str:
    return ACTION_CHOICES.get(p.action, p.action)


def permission_str(p: Permission) -> str:
    """Permission.__str__"""
    return f"{module_display(p)} - {action_display(p)}"


def get_full_name(user: User | None) -> str:
    """AbstractUser.get_full_name — no username fallback."""
    if user is None:
        return ""
    return f"{user.first_name} {user.last_name}".strip()


# ---- access checks used by the Django views -----------------------------------------------------
def deny(message: str, redirect: str | None = None, status: int = 403):
    """A Django `messages.error(...); return redirect(...)` becomes a 403 carrying the message and target."""
    raise HTTPException(status, {"message": message, "redirect": redirect} if redirect else message)


def manager_only(user: User) -> bool:
    """`request.user.user_type == 'manager' or request.user.is_manager`"""
    return is_manager_like(user)


def platform_manager(user: User) -> bool:
    """Superuser or a global (legacy) manager. Role and user-type definitions are platform-wide, so
    university/organisation admins — managers only inside their workspace — cannot change them."""
    return bool(user.is_superuser) or user.user_type == "manager" or bool(user.is_manager)


def manager_or_superuser(user: User) -> bool:
    return is_manager_like(user) or bool(user.is_superuser)


def get_or_404(db: Session, model, obj_id: int, **filters):
    obj = db.get(model, obj_id)
    if obj is None or any(getattr(obj, k) != v for k, v in filters.items()):
        raise HTTPException(404, "Not found")
    return obj


# ---- serialisers --------------------------------------------------------------------------------
def permission_dict(p: Permission) -> dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "dashboard": p.dashboard, "module": p.module, "action": p.action,
        "description": p.description, "is_active": bool(p.is_active),
        "dashboard_display": dashboard_display(p), "module_display": module_display(p),
        "action_display": action_display(p), "label": permission_str(p),
    }


def user_row(user: User, document_count: int | None = None) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": get_full_name(user),
        "phone": user.phone,
        "address": user.address,
        "user_type": user.user_type,
        "user_type_new_id": user.user_type_new_id,
        "user_type_display": user_type_display(user),
        "is_manager": bool(user.is_manager),
        "is_active": bool(user.is_active),
        "is_superuser": bool(user.is_superuser),
        "is_staff": bool(user.is_staff),
        "date_joined": iso(user.date_joined),
        "last_login": iso(user.last_login),
        "document_count": document_count,
    }


def role_dict(role: Role) -> dict[str, Any]:
    return {
        "id": role.id, "name": role.name, "description": role.description,
        "is_system_role": bool(role.is_system_role), "is_active": bool(role.is_active),
        "created_at": iso(role.created_at), "updated_at": iso(role.updated_at),
    }


def user_type_dict(ut: UserType, user_count: int | None = None) -> dict[str, Any]:
    return {
        "id": ut.id, "name": ut.name, "code": ut.code, "description": ut.description,
        "is_active": bool(ut.is_active), "is_system": bool(ut.is_system),
        "created_at": iso(ut.created_at), "updated_at": iso(ut.updated_at), "user_count": user_count,
    }


def document_counts(db: Session, user_ids: list[int] | None = None, active_only: bool = False) -> dict[int, int]:
    """`user.documents.count()` for many users at once."""
    stmt = select(Document.user_id, func.count(Document.id)).group_by(Document.user_id)
    if active_only:
        stmt = stmt.where(Document.is_active == 1)
    if user_ids is not None:
        if not user_ids:
            return {}
        stmt = stmt.where(Document.user_id.in_(user_ids))
    return {uid: n for uid, n in db.execute(stmt).all()}


def user_type_user_counts(db: Session) -> dict[int, int]:
    """`user_type.user_set.count()`"""
    rows = db.execute(
        select(User.user_type_new_id, func.count(User.id)).where(User.user_type_new_id.is_not(None))
        .group_by(User.user_type_new_id)
    ).all()
    return {k: n for k, n in rows}


def permissions_by_dashboard(perms: list[Permission], display: bool = True) -> list[dict[str, Any]]:
    """Group permissions by dashboard → module (display names, insertion order), like the Django views."""
    grouped: dict[str, dict[str, list[dict]]] = {}
    for p in perms:
        d = dashboard_display(p) if display else p.dashboard
        m = module_display(p) if display else p.module
        grouped.setdefault(d, {}).setdefault(m, []).append(permission_dict(p))
    return [
        {"dashboard": d, "modules": [{"module": m, "permissions": ps} for m, ps in mods.items()]}
        for d, mods in grouped.items()
    ]


def active_permissions_ordered(db: Session) -> list[Permission]:
    return list(db.execute(
        select(Permission).where(Permission.is_active == 1)
        .order_by(Permission.dashboard, Permission.module, Permission.action)
    ).scalars())


def role_permission_ids(db: Session, role_id: int) -> list[int]:
    return list(db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == role_id)).scalars())


def set_role_permissions(db: Session, role: Role, permission_ids: list, granted_by: User) -> None:
    """Clear and re-add, silently skipping ids that don't exist (Permission.DoesNotExist → continue)."""
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete(synchronize_session=False)
    seen: set[int] = set()
    for raw in permission_ids:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid in seen or db.get(Permission, pid) is None:
            continue
        seen.add(pid)
        db.add(RolePermission(role_id=role.id, permission_id=pid, granted_by_id=granted_by.id))
    db.flush()


def delete_role(db: Session, role: Role) -> None:
    """role.delete() with Django's on_delete semantics (CASCADE RolePermission/UserRole, SET_NULL DocumentSharing)."""
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete(synchronize_session=False)
    db.query(UserRole).filter(UserRole.role_id == role.id).delete(synchronize_session=False)
    db.execute(update(DocumentSharing).where(DocumentSharing.role_required_id == role.id).values(role_required_id=None))
    db.delete(role)


def user_roles_list(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(UserRole, Role).join(Role, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        .order_by(UserRole.id)
    ).all()
    return [{
        "id": ur.id, "role": role_dict(r), "assigned_at": iso(ur.assigned_at), "expires_at": iso(ur.expires_at),
        "assigned_by": get_full_name(ur.assigned_by) if ur.assigned_by else None,
    } for ur, r in rows]


def user_permissions_list(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(UserPermission, Permission).join(Permission, UserPermission.permission_id == Permission.id)
        .where(UserPermission.user_id == user_id).order_by(UserPermission.id)
    ).all()
    return [{
        "id": up.id, "is_granted": bool(up.is_granted), "reason": up.reason, "granted_at": iso(up.granted_at),
        "expires_at": iso(up.expires_at), "permission": permission_dict(p),
    } for up, p in rows]


def normalize_email(email: str) -> str:
    """BaseUserManager.normalize_email — lowercase the domain part."""
    email = email or ""
    try:
        name, domain = email.strip().rsplit("@", 1)
    except ValueError:
        return email
    return f"{name}@{domain.lower()}"


def create_user(db: Session, *, username: str, email: str, password: str, first_name: str = "", last_name: str = "",
                **extra) -> User:
    """UserManager.create_user (is_staff/is_superuser False) plus model field defaults."""
    now = utcnow()
    user = User(
        username=unicodedata.normalize("NFKC", str(username)),
        email=normalize_email(str(email)),
        password=make_password(password),
        first_name=first_name,
        last_name=last_name,
        is_superuser=0,
        is_staff=0,
        is_active=1,
        date_joined=now,
        user_type=extra.pop("user_type", "student"),
        is_manager=int(bool(extra.pop("is_manager", False))),
        timezone="UTC",
        phone=extra.pop("phone", None),
        address=extra.pop("address", None),
        user_type_new_id=extra.pop("user_type_new_id", None),
    )
    db.add(user)
    db.flush()
    return user


def parse_local_datetime(value: str) -> datetime.datetime:
    """`datetime.fromisoformat(expires_at.replace('T', ' '))` — naive value interpreted in TIME_ZONE (Django
    USE_TZ makes it aware in the current timezone), stored as naive UTC."""
    dt = datetime.datetime.fromisoformat(value.replace("T", " "))
    if dt.tzinfo is None:
        dt = pytz.timezone(settings.TIME_ZONE).localize(dt)
    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def msg(level: str, text: str) -> dict[str, str]:
    return {"level": level, "text": text}
