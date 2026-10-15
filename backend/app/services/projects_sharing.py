"""Document / version sharing — port of the DocumentSharing & DocumentVersionSharing model helpers,
documents/serializers.py (sharing serializers) and documents/views_shared_documents.py.

Other modules can import the access helpers (`document_permission_level`, `version_permission_level`,
`document_can_access`, `get_user_accessible_documents` ...) instead of re-implementing them.
"""
import datetime
from typing import Any

import pytz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import has_module_permission, has_role
from app.core.utils import iso
from app.models import (
    Document,
    DocumentSharing,
    DocumentVersion,
    DocumentVersionSharing,
    Role,
    User,
    utcnow,
)

SHARING_PERMISSION_LEVELS = [("view", "View Only"), ("edit", "View and Edit"), ("admin", "Full Control")]
VERSION_SHARING_PERMISSION_LEVELS = [("view", "View Only"), ("edit", "View and Edit")]


def get_full_name(user: User | None) -> str:
    if user is None:
        return ""
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


def level_display(level: str | None) -> str:
    return dict(SHARING_PERMISSION_LEVELS).get(level, level or "")


# ------------------------------------------------------------------ DocumentSharing model methods
def sharing_is_valid(db: Session, sharing: DocumentSharing) -> bool:
    """DocumentSharing.is_valid"""
    if not sharing.is_active:
        return False
    if sharing.expires_at and utcnow() > sharing.expires_at:
        return False
    if sharing.role_required_id:
        role = db.get(Role, sharing.role_required_id)
        return bool(role) and has_role(db, sharing.user, role.name)
    return True


def sharing_has_permission(db: Session, sharing: DocumentSharing, action: str) -> bool:
    """DocumentSharing.has_permission"""
    if not sharing_is_valid(db, sharing):
        return False
    permission_map = {
        "view": ["view", "edit", "admin"],
        "edit": ["edit", "admin"],
        "delete": ["admin"],
        "share": ["admin"] if not sharing.can_share else ["view", "edit", "admin"],
        "download": ["view", "edit", "admin"] if sharing.can_download else [],
        "annotate": ["view", "edit", "admin"] if sharing.can_annotate else [],
        "delete_versions": ["admin"] if not sharing.can_delete_versions else ["edit", "admin"],
    }
    return sharing.permission_level in permission_map.get(action, [])


def _first_active_share(db: Session, user: User, *, document_id: int | None = None,
                        version_id: int | None = None) -> DocumentSharing | None:
    stmt = select(DocumentSharing).where(DocumentSharing.user_id == user.id, DocumentSharing.is_active == 1)
    if document_id is not None:
        stmt = stmt.where(DocumentSharing.document_id == document_id)
    if version_id is not None:
        stmt = stmt.where(DocumentSharing.document_version_id == version_id)
    # Meta.ordering = ['-shared_at']
    return db.execute(stmt.order_by(DocumentSharing.shared_at.desc()).limit(1)).scalar_one_or_none()


def _system_level(db: Session, user: User) -> str | None:
    if has_module_permission(db, user, "content_lab", "cl_documents", "edit_all"):
        return "edit"
    if has_module_permission(db, user, "content_lab", "cl_documents", "view_all"):
        return "view"
    return None


def document_permission_level(db: Session, document: Document, user: User) -> str | None:
    """Document.get_user_permission_level"""
    if document.user_id == user.id or user.is_superuser:
        return "admin"
    sharing = _first_active_share(db, user, document_id=document.id)
    if sharing and sharing_is_valid(db, sharing):
        return sharing.permission_level
    return _system_level(db, user)


def version_permission_level(db: Session, version: DocumentVersion, user: User) -> str | None:
    """DocumentVersion.get_user_permission_level"""
    if version.document.user_id == user.id or user.is_superuser:
        return "admin"
    sharing = _first_active_share(db, user, version_id=version.id)
    if sharing and sharing_is_valid(db, sharing):
        return sharing.permission_level
    return _system_level(db, user)


def document_can_access(db: Session, document: Document, user: User) -> bool:
    """Document.can_user_access"""
    if document.user_id == user.id or user.is_superuser:
        return True
    sharing = _first_active_share(db, user, document_id=document.id)
    if sharing and sharing_is_valid(db, sharing):
        return True
    return has_module_permission(db, user, "content_lab", "cl_documents", "view_all")


def version_can_access(db: Session, version: DocumentVersion, user: User) -> bool:
    """DocumentVersion.can_user_access"""
    if version.document.user_id == user.id or user.is_superuser:
        return True
    sharing = _first_active_share(db, user, version_id=version.id)
    if sharing and sharing_is_valid(db, sharing):
        return True
    return has_module_permission(db, user, "content_lab", "cl_documents", "view_all")


def can_manage_version_collaborators(db: Session, version: DocumentVersion, user: User) -> bool:
    """Gate used by every views_collaborators view."""
    return (version.document.user_id == user.id or bool(user.is_superuser)
            or version_permission_level(db, version, user) == "admin")


# ------------------------------------------------------------------ views_shared_documents.py
def get_user_accessible_documents(db: Session, user: User, include_shared: bool = True):
    """Returns a select() of accessible, active documents."""
    if has_module_permission(db, user, "content_lab", "cl_documents", "view_all"):
        return select(Document).where(Document.is_active == 1)
    cond = Document.user_id == user.id
    if include_shared:
        shared_ids = [i for i in db.execute(select(DocumentSharing.document_id).where(
            DocumentSharing.user_id == user.id, DocumentSharing.is_active == 1)).scalars() if i is not None]
        if shared_ids:
            cond = or_(cond, Document.id.in_(shared_ids))
    return select(Document).where(cond, Document.is_active == 1)


def get_user_documents_by_status(db: Session, user: User, status: int, include_shared: bool = True):
    return get_user_accessible_documents(db, user, include_shared).where(Document.stage_status == status)


def get_document_statistics_for_user(db: Session, user: User, include_shared: bool = True) -> dict[str, int]:
    base = get_user_accessible_documents(db, user, include_shared)

    def count(stmt) -> int:
        return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    return {
        "total": count(base),
        "draft": count(base.where(Document.stage_status == 0)),
        "review": count(base.where(Document.stage_status == 1)),
        "approved": count(base.where(Document.stage_status == 2)),
        "revision": count(base.where(Document.stage_status == 3)),
        "shared_with_me": db.execute(select(func.count()).select_from(DocumentSharing).where(
            DocumentSharing.user_id == user.id, DocumentSharing.is_active == 1)).scalar_one() if include_shared else 0,
    }


# ------------------------------------------------------------------ serializers
def serialize_sharing(db: Session, s: DocumentSharing) -> dict[str, Any]:
    """DocumentSharingSerializer"""
    return {
        "id": s.id, "document": s.document_id, "document_version": s.document_version_id, "user": s.user_id,
        "user_display": {"id": s.user.id, "name": get_full_name(s.user), "email": s.user.email,
                         "username": s.user.username},
        "permission_level": s.permission_level, "permission_level_display": level_display(s.permission_level),
        "role_required": s.role_required_id,
        "role_display": {"id": s.role_required.id, "name": s.role_required.name} if s.role_required else None,
        "shared_by": s.shared_by_id,
        "shared_by_display": {"id": s.shared_by.id, "name": get_full_name(s.shared_by), "email": s.shared_by.email},
        "shared_at": iso(s.shared_at), "expires_at": iso(s.expires_at),
        "can_share": bool(s.can_share), "can_download": bool(s.can_download), "can_annotate": bool(s.can_annotate),
        "can_delete_versions": bool(s.can_delete_versions), "notify_on_update": bool(s.notify_on_update),
        "notes": s.notes, "is_active": bool(s.is_active), "last_accessed": iso(s.last_accessed),
        "is_valid": sharing_is_valid(db, s),
    }


def serialize_sharing_update(s: DocumentSharing) -> dict[str, Any]:
    """UpdateDocumentSharingSerializer"""
    return {
        "permission_level": s.permission_level, "expires_at": iso(s.expires_at),
        "can_share": bool(s.can_share), "can_download": bool(s.can_download), "can_annotate": bool(s.can_annotate),
        "can_delete_versions": bool(s.can_delete_versions), "notify_on_update": bool(s.notify_on_update),
        "notes": s.notes, "is_active": bool(s.is_active),
    }


def serialize_version_sharing(s: DocumentVersionSharing) -> dict[str, Any]:
    """DocumentVersionSharingSerializer"""
    v = s.document_version
    return {
        "id": s.id, "document_version": s.document_version_id,
        "version_display": {"id": v.id, "version_number": v.version_number, "file_title_name": v.file_title_name},
        "user": s.user_id,
        "user_display": {"id": s.user.id, "name": get_full_name(s.user), "email": s.user.email},
        "permission_level": s.permission_level, "shared_by": s.shared_by_id, "shared_at": iso(s.shared_at),
        "expires_at": iso(s.expires_at), "can_download": bool(s.can_download), "can_annotate": bool(s.can_annotate),
        "notes": s.notes, "is_active": bool(s.is_active), "last_accessed": iso(s.last_accessed),
    }


def serialize_shared_document(db: Session, doc: Document, user: User) -> dict[str, Any]:
    """SharedDocumentSerializer"""
    sharing = _first_active_share(db, user, document_id=doc.id)
    latest = db.execute(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                        .order_by(DocumentVersion.version_count.desc()).limit(1)).scalar_one_or_none()
    return {
        "id": doc.id, "document_name": doc.document_name, "document_number": doc.document_number,
        "document_type": doc.document_type_id,
        "document_type_name": doc.document_type.name if doc.document_type else None,
        "brand": doc.brand_id, "brand_name": doc.brand.name if doc.brand else None,
        "country": doc.country_id, "country_name": doc.country.name if doc.country else None,
        "stage_status": doc.stage_status, "user": doc.user_id, "owner_name": get_full_name(doc.user),
        "created_at": iso(doc.created_at), "updated_at": iso(doc.updated_at),
        "sharing_info": {
            "shared_by": get_full_name(sharing.shared_by), "shared_at": iso(sharing.shared_at),
            "expires_at": iso(sharing.expires_at), "can_share": bool(sharing.can_share),
            "can_download": bool(sharing.can_download),
            "can_edit": sharing.permission_level in ("edit", "admin"), "notes": sharing.notes,
        } if sharing else None,
        "access_level": document_permission_level(db, doc, user),
        "latest_version": {"id": latest.id, "version_number": latest.version_number,
                           "stage_status": latest.stage_status, "created_at": iso(latest.created_at)} if latest else None,
    }


# ------------------------------------------------------------------ input parsing
def parse_datetime_input(value: Any) -> datetime.datetime | None:
    """DateTimeField input -> naive UTC. Naive values are interpreted in settings.TIME_ZONE (Django's
    behaviour with USE_TZ=True). Raises ValueError for unparsable input."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        try:
            dt = datetime.datetime.fromisoformat(text)
        except ValueError:
            d = datetime.date.fromisoformat(text)
            dt = datetime.datetime(d.year, d.month, d.day)
    if dt.tzinfo is None:
        dt = pytz.timezone(settings.TIME_ZONE).localize(dt)
    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def parse_bool(value: Any, default: bool) -> bool:
    """DRF BooleanField"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on", "t", "y"):
        return True
    if text in ("false", "0", "no", "off", "f", "n", ""):
        return False
    raise ValueError("Must be a valid boolean.")
