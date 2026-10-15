"""Shared helpers for the doccore module (document lifecycle).

Ports of small bits of Django behaviour used by documents/views.py,
documents/upload_with_owner.py and library/views.py: get_full_name(),
STAGE_CHOICES, get_object_or_404, Django messages + redirect, FileField storage
naming (incl. max_length truncation) and ORM cascade deletes.
"""
import os
import secrets
import shutil
import string
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.tenancy import org_admin_ids
from app.core.permissions import is_manager_like
from app.config import settings
from app.core.files import get_valid_filename
from app.core.utils import user_tz
from app.models import (
    AnnotationActivity,
    AssignedReviewer,
    Document,
    DocumentAnnotation,
    DocumentHistory,
    DocumentReference,
    DocumentSharing,
    DocumentVersion,
    DocumentVersionReference,
    DocumentVersionSharing,
    EmailLog,
    ReferenceZip,
    User,
)

STAGE_CHOICES: list[tuple[int, str]] = [
    (0, "Draft"),
    (1, "Under Review"),
    (2, "Approved"),
    (3, "Draft Under Revision"),
]
STAGE_DISPLAY = dict(STAGE_CHOICES)

ALLOWED_DOCUMENT_EXTENSIONS = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"]

PROJECT_STATUS_DISPLAY = {"active": "Active", "completed": "Completed", "on_hold": "On Hold"}


def gfn(user: User | None) -> str:
    """Django AbstractUser.get_full_name() — may be an empty string."""
    if user is None:
        return ""
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


def stage_display(value: int | None) -> str:
    """Model.get_stage_status_display() — unknown values are returned unchanged."""
    return STAGE_DISPLAY.get(value, value)  # type: ignore[arg-type]


def is_admin_user(user: User) -> bool:
    return bool(user.is_superuser or user.is_staff)


def is_manager_flag(user: User) -> bool:
    return is_manager_like(user)


def tz_name(user: User | None) -> str:
    """{% current_timezone %}"""
    return str(user_tz(user))


def title_case(value: str | None) -> str:
    """Django |title filter (close enough for user_type codes)."""
    return (value or "").title()


def page_redirect(message: str | None, to: str, status: int = 403, level: str = "error") -> HTTPException:
    """Equivalent of `messages.<level>(request, message); return redirect(to)` for page-data endpoints."""
    return HTTPException(status, detail={"message": message, "redirect": to, "level": level})


def get_or_404(db: Session, model, obj_id, label: str):
    obj = db.get(model, obj_id) if obj_id is not None else None
    if obj is None:
        raise HTTPException(404, f"No {label} matches the given query.")
    return obj


# ---------------------------------------------------------------- documents
def latest_version(db: Session, document_id: int) -> DocumentVersion | None:
    """Document.get_latest_version() — order by -version_count."""
    return db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_count.desc()).limit(1)
    ).scalar_one_or_none()


def latest_version_status(db: Session, document: Document) -> int:
    """Document.get_latest_version_status()"""
    lv = latest_version(db, document.id)
    return lv.stage_status if lv else document.stage_status


def has_approved_version(db: Session, document_id: int) -> bool:
    return db.execute(
        select(DocumentVersion.id).where(DocumentVersion.document_id == document_id, DocumentVersion.stage_status == 2).limit(1)
    ).first() is not None


def versions_count(db: Session, document_id: int) -> int:
    return db.execute(select(func.count(DocumentVersion.id)).where(DocumentVersion.document_id == document_id)).scalar_one()


def versions_default_order(db: Session, document_id: int) -> list[DocumentVersion]:
    """document.versions.all() — DocumentVersion has no Meta.ordering, so MySQL returns PK order."""
    return list(db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id).order_by(DocumentVersion.id)
    ).scalars())


def notifiable_teachers_managers(db: Session, exclude_id: int | None = None) -> list[User]:
    stmt = select(User).where(or_(User.user_type.in_(["teacher", "manager"]), User.id.in_(org_admin_ids())),
                              User.is_active == 1)
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return list(db.execute(stmt).scalars())


def sent_for_text(document_name: str) -> str:
    """Truncation used by update_document_status / update_version_status (sent_for max 100 chars)."""
    text = f"Document: {document_name}"
    if len(text) > 100:
        max_name_length = 100 - 10 - 3
        text = f"Document: {document_name[:max_name_length] + '...'}"
    return text


def status_notification_type(stage_status: int) -> str:
    return "document_approved" if stage_status == 2 else "document_rejected" if stage_status == 3 else "review_request"


# ---------------------------------------------------------------- files
_RANDOM = string.ascii_letters + string.digits


def _rand7() -> str:
    return "".join(secrets.choice(_RANDOM) for _ in range(7))


def file_extension_error(filename: str, allowed: list[str]) -> str | None:
    """django.core.validators.FileExtensionValidator message, or None when valid."""
    ext = os.path.splitext(filename)[1][1:].lower()
    if ext not in allowed:
        return f"File extension “{ext}” is not allowed. Allowed extensions are: {', '.join(allowed)}."
    return None


def upload_size(upload: UploadFile) -> int:
    f = upload.file
    pos = f.tell()
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(pos)
    return size


def save_like_django(upload: UploadFile, directory: str, max_length: int = 100) -> str:
    """FileSystemStorage.save() as invoked by a FileField(max_length=100).

    get_valid_name + get_available_name(max_length): when the name is taken or too
    long Django appends `_<7 chars>` and truncates the file root to fit.
    """
    name = get_valid_filename(os.path.basename(upload.filename or "file"))
    rel = os.path.normpath(os.path.join(directory.strip("/"), name))
    dir_name, file_name = os.path.split(rel)
    root, ext = os.path.splitext(file_name)
    media = settings.media_root
    while (media / rel).exists() or len(rel) > max_length:
        rel = os.path.join(dir_name, f"{root}_{_rand7()}{ext}")
        truncation = len(rel) - max_length
        if truncation > 0:
            root = root[:-truncation]
            if not root:
                raise HTTPException(400, (
                    f'Storage can not find an available filename for "{rel}". Please make sure that the '
                    'corresponding file field allows sufficient "max_length".'))
            rel = os.path.join(dir_name, f"{root}_{_rand7()}{ext}")
    full = media / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    upload.file.seek(0)
    with open(full, "wb") as out:
        shutil.copyfileobj(upload.file, out)
    try:
        os.chmod(full, 0o644)
    except OSError:
        pass
    return rel


def file_size_or_none(rel: str | None) -> int | None:
    if not rel:
        return None
    try:
        p = settings.media_root / rel
        return p.stat().st_size if p.is_file() else None
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- cascades
def delete_version_cascade(db: Session, version_ids: list[int]) -> None:
    """Replicates Django's on_delete handling for DocumentVersion rows (the DB FKs are NO ACTION)."""
    if not version_ids:
        return
    db.execute(update(EmailLog).where(EmailLog.document_version_id.in_(version_ids)).values(document_version_id=None))
    for model in (AnnotationActivity, DocumentAnnotation, DocumentVersionReference, DocumentVersionSharing,
                  AssignedReviewer, ReferenceZip):
        db.execute(delete(model).where(model.document_version_id.in_(version_ids)))
    db.execute(delete(DocumentHistory).where(DocumentHistory.document_version_id.in_(version_ids)))
    db.execute(delete(DocumentSharing).where(DocumentSharing.document_version_id.in_(version_ids)))
    db.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))


def delete_document_cascade(db: Session, document_id: int) -> None:
    version_ids = list(db.execute(select(DocumentVersion.id).where(DocumentVersion.document_id == document_id)).scalars())
    delete_version_cascade(db, version_ids)
    db.execute(update(EmailLog).where(EmailLog.document_id == document_id).values(document_id=None))
    db.execute(delete(DocumentReference).where(DocumentReference.document_id == document_id))
    db.execute(delete(DocumentSharing).where(DocumentSharing.document_id == document_id))
    db.execute(delete(DocumentHistory).where(DocumentHistory.document_id == document_id))
    db.execute(delete(Document).where(Document.id == document_id))


def brief(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": gfn(user),
        "user_type": user.user_type,
        "user_type_title": title_case(user.user_type),
    }
