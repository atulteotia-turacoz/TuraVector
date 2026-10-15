"""Shared helpers for the viewer module (document preview / review / references).

Ports of small bits of logic that the Django views and templates used inline:
`get_full_name`, the Django-template `in` operator on comma strings, the
"authorised user" checks repeated across the annotation views, serializers for
the template context, and file-location helpers.
"""
import datetime
import os
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import is_manager_like
from app.config import settings
from app.core.files import media_path, media_url
from app.core.utils import iso
from app.models import (
    Document,
    DocumentVersion,
    DocumentVersionReference,
    ReferenceDocument,
    User,
)

STAGE_LABELS = {0: "Draft", 1: "Under Review", 2: "Approved", 3: "Draft Under Revision"}
REFERENCE_TYPES = {"primary": "Primary Reference", "secondary": "Secondary Reference", "supporting": "Supporting Document"}
REFERENCE_SUBTYPES = {"journal": "Journal Article", "book": "Book", "website": "Website", "report": "Report",
                      "guideline": "Guideline"}
LEGACY_USER_TYPES = {"student": "Student", "teacher": "Teacher", "reviewer": "Reviewer", "manager": "Manager"}

# Django templates test `version.file_extension in 'pdf,doc,docx,xls,xlsx,ppt,pptx'` — a *substring* test.
WEBVIEWER_EXTENSIONS = "pdf,doc,docx,xls,xlsx,ppt,pptx"


def get_full_name(user: User | None) -> str:
    """AbstractUser.get_full_name — '' when both names are empty (callers add `or username`)."""
    if user is None:
        return ""
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


def name_or_username(user: User | None) -> str:
    if user is None:
        return ""
    return get_full_name(user) or user.username


def template_name(user: User) -> str:
    """`{% if user.first_name or user.last_name %}{{ first }} {{ last }}{% else %}{{ username }}{% endif %}`"""
    if user.first_name or user.last_name:
        return f"{user.first_name or ''} {user.last_name or ''}"
    return user.username


def in_csv(value: str | None, csv: str) -> bool:
    """Django template `{% if x in 'a,b' %}` is Python substring containment."""
    return (value or "") in csv


def is_annotation_authorized(user: User) -> bool:
    """`user_type in ['admin','manager','teacher','reviewer'] or is_manager or is_superuser`"""
    return user.user_type in ["admin", "manager", "teacher", "reviewer"] or is_manager_like(user) or bool(user.is_superuser)


def is_comment_sync_authorized(user: User) -> bool:
    """`user_type in ['manager','teacher','reviewer'] or is_manager` (comment-sync views)."""
    return user.user_type in ["manager", "teacher", "reviewer"] or is_manager_like(user)


def is_manager_or_teacher(user: User) -> bool:
    """`user_type in ['manager','teacher'] or is_manager`"""
    return user.user_type in ["manager", "teacher"] or is_manager_like(user)


def error(status: int, message: str, **extra) -> JSONResponse:
    """DRF-style `Response({'error': ...}, status=...)`."""
    return JSONResponse({"error": message, **extra}, status_code=status)


def page_denied(status: int, message: str, redirect: str, level: str = "error") -> JSONResponse:
    """Replacement for Django `messages.error(...); return redirect(...)` on page views."""
    return JSONResponse({"detail": message, "redirect": redirect, "level": level}, status_code=status)


def get_version_or_404(db: Session, version_id: int) -> DocumentVersion:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(404, "No DocumentVersion matches the given query.")
    return version


def get_reference_or_404(db: Session, reference_id: int) -> ReferenceDocument:
    reference = db.get(ReferenceDocument, reference_id)
    if reference is None:
        raise HTTPException(404, "No ReferenceDocument matches the given query.")
    return reference


def frontend_url(path: str) -> str:
    """request.build_absolute_uri(path) — links in emails point at the React app."""
    return f"{settings.FRONTEND_URL.rstrip('/')}{path}"


def file_exists(relative: str | None) -> bool:
    if not relative:
        return False
    try:
        path = media_path(relative)
    except HTTPException:
        return False
    return bool(path and path.is_file())


def file_size(relative: str | None) -> int | None:
    if not file_exists(relative):
        return None
    return os.path.getsize(media_path(relative))


def has_approved_version(db: Session, document: Document) -> bool:
    return db.execute(
        select(DocumentVersion.id).where(DocumentVersion.document_id == document.id,
                                         DocumentVersion.stage_status == 2).limit(1)
    ).first() is not None


def linked_references(db: Session, version: DocumentVersion, newest_first: bool = False) -> list[DocumentVersionReference]:
    stmt = select(DocumentVersionReference).where(
        DocumentVersionReference.document_version_id == version.id,
        DocumentVersionReference.is_active == 1,
    )
    # Model Meta ordering is ['-linked_at']
    stmt = stmt.order_by(DocumentVersionReference.linked_at.desc())
    return list(db.execute(stmt).scalars())


# ------------------------------------------------------------------ serializers
def user_out(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": get_full_name(user),
        "email": user.email,
        "user_type": user.user_type,
        "user_type_display": LEGACY_USER_TYPES.get(user.user_type, user.user_type),
        "is_manager": bool(user.is_manager),
    }


def document_out(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "document_name": document.document_name,
        "document_number": document.document_number,
        "stage_status": document.stage_status,
        "stage_status_display": STAGE_LABELS.get(document.stage_status, str(document.stage_status)),
        "document_type": document.document_type.name if document.document_type else None,
        "brand": document.brand.name if document.brand else None,
        "country": document.country.name if document.country else None,
        "user": user_out(document.user),
        "created_at": iso(document.created_at),
        "updated_at": iso(document.updated_at),
    }


def version_out(version: DocumentVersion) -> dict[str, Any]:
    rel = version.document_file or ""
    return {
        "id": version.id,
        "document_id": version.document_id,
        "version_number": version.version_number,
        "version_count": version.version_count,
        "file_name": version.file_name,
        "file_extension": version.file_extension,
        "file_title_name": version.file_title_name,
        "stage_status": version.stage_status,
        "stage_status_display": STAGE_LABELS.get(version.stage_status, str(version.stage_status)),
        "user_id": version.user_id,
        "created_at": iso(version.created_at),
        "updated_at": iso(version.updated_at),
        "has_file": bool(rel),
        "file_exists": file_exists(rel),
        "file_size": file_size(rel),
        "file_path": rel,
        # public URL (Django's version.document_file.url) — used for external viewers (Office/Google)
        "media_url": media_url(rel) if rel else None,
        # authenticated endpoint used by the WebViewer and download links
        "file_api": f"/api/viewer/versions/{version.id}/file",
    }


def reference_out(reference: ReferenceDocument, full: bool = False) -> dict[str, Any]:
    rel = reference.reference_file or ""
    out = {
        "id": reference.id,
        "reference_number": reference.reference_number,
        "document_name": reference.document_name,
        "type": reference.type,
        "type_display": REFERENCE_TYPES.get(reference.type, reference.type),
        "subtype": reference.subtype,
        "subtype_display": REFERENCE_SUBTYPES.get(reference.subtype, reference.subtype),
        "therapeutic_area": reference.therapeutic_area.name if reference.therapeutic_area else None,
        "country": reference.country.name if reference.country else None,
        "ref_year": reference.ref_year,
        "file_extension": reference.file_extension,
        "file_title_name": reference.file_title_name,
        "file_name": reference.file_name,
        "has_file": bool(rel),
        "media_url": media_url(rel) if rel else None,
        "file_api": f"/api/viewer/references/{reference.id}/file",
    }
    if full:
        out.update({
            "file_exists": file_exists(rel),
            "user_id": reference.user_id,
            "created_by": user_out(reference.created_by),
            "created_at": iso(reference.created_at),
            "updated_at": iso(reference.updated_at),
        })
    return out


def link_out(link: DocumentVersionReference) -> dict[str, Any]:
    return {
        "id": link.id,
        "reference": reference_out(link.reference),
        "linked_by": user_out(link.linked_by),
        "linked_at": iso(link.linked_at),
        "notes": link.notes,
    }


def naive_utc(dt: datetime.datetime) -> datetime.datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt
