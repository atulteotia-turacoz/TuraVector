"""Document & version sharing.

- /api/sharing/document-sharing/...          <- DocumentSharingViewSet (DRF, api/document-sharing/)
- /api/sharing/document-version-sharing/...  <- DocumentVersionSharingViewSet (api/document-version-sharing/)
- /api/sharing/versions/{id}/collaborators... <- documents/views_collaborators.py
- /api/sharing/search-users-version-sharing   <- search_users_for_version_sharing

DRF error shapes are kept ({"field": [...]}, {"non_field_errors": [...]}, {"error": ...}).
"""
import math
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.utils import iso
from app.database import get_db
from app.models import (
    Document,
    DocumentNotification,
    DocumentSharing,
    DocumentVersion,
    DocumentVersionSharing,
    Role,
    User,
    utcnow,
)
from app.schemas.projects_schemas import VersionCollaboratorAddIn
from app.services import projects_sharing as sh

router = APIRouter(prefix="/api/sharing", tags=["sharing"])

PAGE_SIZE = 25  # REST_FRAMEWORK['PAGE_SIZE']


def _drf_error(data: dict[str, Any], status_code: int = 400) -> JSONResponse:
    return JSONResponse(data, status_code=status_code)


def _not_found() -> JSONResponse:
    return JSONResponse({"detail": "Not found."}, status_code=404)


def _paginate(request: Request, db: Session, stmt, page: str | None, serialize) -> Any:
    """rest_framework.pagination.PageNumberPagination"""
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    pages = max(1, math.ceil(total / PAGE_SIZE))
    try:
        page_no = int(page) if page not in (None, "") else 1
        if page_no < 1 or page_no > pages:
            raise ValueError
    except ValueError:
        return JSONResponse({"detail": "Invalid page."}, status_code=404)
    rows = db.execute(stmt.limit(PAGE_SIZE).offset((page_no - 1) * PAGE_SIZE)).scalars().unique().all()

    def link(n: int | None) -> str | None:
        return None if n is None else str(request.url.include_query_params(page=n))

    return {"count": total, "next": link(page_no + 1 if page_no < pages else None),
            "previous": link(page_no - 1 if page_no > 1 else None), "results": [serialize(r) for r in rows]}


# ====================================================================== DocumentSharingViewSet
def _sharing_queryset(user: User):
    stmt = select(DocumentSharing)
    if user.is_superuser:
        return stmt
    owned_docs = select(Document.id).where(Document.user_id == user.id)
    return stmt.where(or_(DocumentSharing.document_id.in_(owned_docs), DocumentSharing.user_id == user.id,
                          DocumentSharing.shared_by_id == user.id))


def _get_sharing(db: Session, user: User, sharing_id: int) -> DocumentSharing | None:
    return db.execute(_sharing_queryset(user).where(DocumentSharing.id == sharing_id)).scalar_one_or_none()


@router.get("/document-sharing")
def document_sharing_list(request: Request, page: str | None = None, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    stmt = _sharing_queryset(user).order_by(DocumentSharing.shared_at.desc())
    return _paginate(request, db, stmt, page, lambda s: sh.serialize_sharing(db, s))


def _bool_field(errors: dict[str, list[str]], data: dict[str, Any], key: str, default: bool) -> bool:
    try:
        return sh.parse_bool(data.get(key), default)
    except ValueError as exc:
        errors.setdefault(key, []).append(str(exc))
        return default


def _datetime_field(errors: dict[str, list[str]], data: dict[str, Any], key: str):
    try:
        return sh.parse_datetime_input(data.get(key))
    except ValueError:
        errors.setdefault(key, []).append(
            "Datetime has wrong format. Use one of these formats instead: YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].")
        return None


@router.post("/document-sharing", status_code=201)
def document_sharing_create(data: dict[str, Any] = Body(...), user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """CreateDocumentSharingSerializer"""
    errors: dict[str, list[str]] = {}
    document = None
    if data.get("document") not in (None, ""):
        document = db.get(Document, int(data["document"])) if str(data["document"]).isdigit() else None
        if document is None:
            errors["document"] = [f'Invalid pk "{data["document"]}" - object does not exist.']
        elif sh.document_permission_level(db, document, user) != "admin":
            sharing = db.execute(select(DocumentSharing).where(
                DocumentSharing.document_id == document.id, DocumentSharing.user_id == user.id,
                DocumentSharing.is_active == 1).order_by(DocumentSharing.shared_at.desc()).limit(1)
            ).scalar_one_or_none()
            if not sharing or not sharing.can_share:
                errors["document"] = ["You don't have permission to share this document"]
    target = None
    raw_user = data.get("user")
    if raw_user in (None, ""):
        errors["user"] = ["This field is required."]
    else:
        target = db.execute(select(User).where(User.id == int(raw_user), User.is_active == 1)).scalar_one_or_none() \
            if str(raw_user).isdigit() else None
        if target is None:
            errors["user"] = [f'Invalid pk "{raw_user}" - object does not exist.']
    level = data.get("permission_level") or "view"
    if level not in dict(sh.SHARING_PERMISSION_LEVELS):
        errors["permission_level"] = [f'"{level}" is not a valid choice.']
    role = None
    if data.get("role_required") not in (None, ""):
        role = db.get(Role, int(data["role_required"])) if str(data["role_required"]).isdigit() else None
        if role is None:
            errors["role_required"] = [f'Invalid pk "{data["role_required"]}" - object does not exist.']
    expires_at = _datetime_field(errors, data, "expires_at")
    flags = {k: _bool_field(errors, data, k, d) for k, d in (
        ("can_share", False), ("can_download", True), ("can_annotate", True), ("can_delete_versions", False),
        ("notify_on_update", True))}
    if errors:
        return _drf_error(errors)
    if document is None:
        return _drf_error({"document": ["This field is required."]})

    users_to_share = None
    if "users" in data and data["users"] is not None:
        ids = [int(i) for i in data["users"]]
        users_to_share = db.execute(select(User).where(User.id.in_(ids), User.is_active == 1)).scalars().all()
        if len(users_to_share) != len(ids):
            return _drf_error({"non_field_errors": ["Some users not found or inactive"]})
    elif db.execute(select(DocumentSharing.id).where(DocumentSharing.document_id == document.id,
                                                     DocumentSharing.user_id == target.id)).first():
        return _drf_error({"non_field_errors": [f"Document already shared with {sh.get_full_name(target)}"]})

    def make(u: User) -> DocumentSharing:
        s = DocumentSharing(document_id=document.id, user_id=u.id, permission_level=level,
                            role_required_id=role.id if role else None, shared_by_id=user.id, expires_at=expires_at,
                            notes=data.get("notes"), is_active=1,
                            **{k: 1 if v else 0 for k, v in flags.items()})
        db.add(s)
        db.flush()
        return s

    if users_to_share is not None:
        created = [make(u) for u in users_to_share if not db.execute(select(DocumentSharing.id).where(
            DocumentSharing.document_id == document.id, DocumentSharing.user_id == u.id)).first()]
        db.commit()
        if not created:
            return None
        return sh.serialize_sharing(db, created[0])
    s = make(target)
    db.commit()
    return sh.serialize_sharing(db, s)


@router.get("/document-sharing/my-shares")
def my_shares(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(DocumentSharing).where(DocumentSharing.shared_by_id == user.id,
                                                    DocumentSharing.is_active == 1)
                      .order_by(DocumentSharing.shared_at.desc())).scalars().all()
    return [sh.serialize_sharing(db, s) for s in rows]


@router.get("/document-sharing/shared-with-me")
def shared_with_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = select(DocumentSharing.document_id).where(DocumentSharing.user_id == user.id, DocumentSharing.is_active == 1)
    docs = db.execute(select(Document).where(Document.id.in_(ids), Document.is_active == 1)).scalars().all()
    return [sh.serialize_shared_document(db, d, user) for d in docs]


@router.post("/document-sharing/check-access")
def check_access(data: dict[str, Any] = Body(...), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """DocumentAccessSerializer"""
    action = data.get("action") or "view"
    if action not in ("view", "edit", "delete", "share", "download", "annotate"):
        return _drf_error({"action": [f'"{action}" is not a valid choice.']})
    if data.get("document_id") in (None, ""):
        return _drf_error({"document_id": ["This field is required."]})
    try:
        document_id = int(data["document_id"])
    except (TypeError, ValueError):
        return _drf_error({"document_id": ["A valid integer is required."]})
    document = db.get(Document, document_id)
    if document is None:
        return _drf_error({"non_field_errors": ["Document not found"]})
    target = user
    if data.get("user_id"):
        target = db.get(User, int(data["user_id"]))
        if target is None:
            return _drf_error({"non_field_errors": ["User not found"]})
    can_access = sh.document_can_access(db, document, target)
    level = sh.document_permission_level(db, document, target) if can_access else None
    has_permission = False
    if can_access and level:
        sharing = db.execute(select(DocumentSharing).where(
            DocumentSharing.document_id == document.id, DocumentSharing.user_id == target.id,
            DocumentSharing.is_active == 1).order_by(DocumentSharing.shared_at.desc()).limit(1)).scalar_one_or_none()
        if sharing:
            has_permission = sh.sharing_has_permission(db, sharing, action)
        elif document.user_id == target.id or target.is_superuser:
            has_permission = True
        else:
            action_map = {"view": ["view", "edit", "admin"], "edit": ["edit", "admin"], "delete": ["admin"],
                          "share": ["admin"], "download": ["view", "edit", "admin"],
                          "annotate": ["view", "edit", "admin"]}
            has_permission = level in action_map.get(action, [])
    return {"document_id": document.id, "document_name": document.document_name, "user_id": target.id,
            "user_name": sh.get_full_name(target), "action": action, "has_access": can_access,
            "permission_level": level, "has_permission": has_permission}


@router.get("/document-sharing/expired-shares")
def expired_shares(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_superuser:
        return _drf_error({"error": "Admin access required"}, 403)
    rows = db.execute(select(DocumentSharing).where(DocumentSharing.expires_at < utcnow(),
                                                    DocumentSharing.is_active == 1)
                      .order_by(DocumentSharing.shared_at.desc())).scalars().all()
    return [sh.serialize_sharing(db, s) for s in rows]


@router.post("/document-sharing/bulk-share")
def bulk_share(data: dict[str, Any] = Body(...), user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    document_ids = data.get("document_ids") or []
    user_ids = data.get("user_ids") or []
    level = data.get("permission_level", "view")
    notes = data.get("notes", "")
    if not document_ids or not user_ids:
        return _drf_error({"error": "Both document_ids and user_ids are required"})
    documents = db.execute(select(Document).where(Document.id.in_(document_ids))).scalars().all()
    if len(documents) != len(document_ids):
        return _drf_error({"error": "Some documents not found"})
    for doc in documents:
        if not (doc.user_id == user.id or sh.document_permission_level(db, doc, user) == "admin"):
            return _drf_error({"error": f"You don't have permission to share document {doc.document_name}"}, 403)
    users = db.execute(select(User).where(User.id.in_(user_ids), User.is_active == 1)).scalars().all()
    if len(users) != len(user_ids):
        return _drf_error({"error": "Some users not found or inactive"})
    try:
        expires_at = sh.parse_datetime_input(data.get("expires_at"))
    except ValueError as exc:
        return _drf_error({"error": str(exc)})
    created = skipped = 0
    for doc in documents:
        for u in users:
            if db.execute(select(DocumentSharing.id).where(DocumentSharing.document_id == doc.id,
                                                           DocumentSharing.user_id == u.id)).first():
                skipped += 1
                continue
            db.add(DocumentSharing(document_id=doc.id, user_id=u.id, shared_by_id=user.id, permission_level=level,
                                   expires_at=expires_at, notes=notes, can_share=0, can_download=1, can_annotate=1,
                                   can_delete_versions=0, notify_on_update=1, is_active=1))
            created += 1
    db.commit()
    return {"created": created, "skipped": skipped,
            "message": f"Successfully shared {created} documents. Skipped {skipped} existing shares."}


@router.get("/document-sharing/{sharing_id}")
def document_sharing_retrieve(sharing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_sharing(db, user, sharing_id)
    if s is None:
        return _not_found()
    return sh.serialize_sharing(db, s)


def _update_sharing(sharing_id: int, data: dict[str, Any], user: User, db: Session):
    """UpdateDocumentSharingSerializer (PUT and PATCH behave the same: every field is optional)."""
    s = _get_sharing(db, user, sharing_id)
    if s is None:
        return _not_found()
    errors: dict[str, list[str]] = {}
    if "permission_level" in data and data["permission_level"] not in dict(sh.SHARING_PERMISSION_LEVELS):
        errors["permission_level"] = [f'"{data["permission_level"]}" is not a valid choice.']
    values: dict[str, Any] = {}
    if "expires_at" in data:
        values["expires_at"] = _datetime_field(errors, data, "expires_at")
    for key in ("can_share", "can_download", "can_annotate", "can_delete_versions", "notify_on_update", "is_active"):
        if key in data:
            values[key] = 1 if _bool_field(errors, data, key, False) else 0
    if "notes" in data:
        values["notes"] = data["notes"]
    if "permission_level" in data:
        values["permission_level"] = data["permission_level"]
    if errors:
        return _drf_error(errors)
    document = s.document
    if document is None or sh.document_permission_level(db, document, user) != "admin":
        return _drf_error({"non_field_errors": ["You don't have permission to update sharing settings"]})
    for k, v in values.items():
        setattr(s, k, v)
    db.commit()
    return sh.serialize_sharing_update(s)


@router.put("/document-sharing/{sharing_id}")
def document_sharing_update(sharing_id: int, data: dict[str, Any] = Body(...), user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    return _update_sharing(sharing_id, data, user, db)


@router.patch("/document-sharing/{sharing_id}")
def document_sharing_partial_update(sharing_id: int, data: dict[str, Any] = Body(...),
                                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_sharing(sharing_id, data, user, db)


@router.delete("/document-sharing/{sharing_id}")
def document_sharing_destroy(sharing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_sharing(db, user, sharing_id)
    if s is None:
        return _not_found()
    owner_id = s.document.user_id if s.document is not None else None
    if not (user.id == owner_id or user.id == s.shared_by_id or user.is_superuser):
        return _drf_error({"error": "You don't have permission to remove this sharing"}, 403)
    db.delete(s)
    db.commit()
    return Response(status_code=204)


@router.post("/document-sharing/{sharing_id}/update-access-time")
def update_access_time(sharing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_sharing(db, user, sharing_id)
    if s is None:
        return _not_found()
    if user.id != s.user_id:
        return _drf_error({"error": "You can only update access time for your own shares"}, 403)
    s.last_accessed = utcnow()
    db.commit()
    return {"message": "Access time updated"}


# ====================================================================== DocumentVersionSharingViewSet
def _version_sharing_queryset(user: User):
    stmt = select(DocumentVersionSharing)
    if user.is_superuser:
        return stmt
    owned_versions = select(DocumentVersion.id).join(Document, DocumentVersion.document_id == Document.id).where(
        Document.user_id == user.id)
    return stmt.where(or_(DocumentVersionSharing.document_version_id.in_(owned_versions),
                          DocumentVersionSharing.user_id == user.id, DocumentVersionSharing.shared_by_id == user.id))


def _clean_version_sharing(db: Session, data: dict[str, Any], instance: DocumentVersionSharing | None,
                           partial: bool) -> tuple[dict[str, Any], dict[str, list[str]]]:
    errors: dict[str, list[str]] = {}
    values: dict[str, Any] = {}
    for key, model in (("document_version", DocumentVersion), ("user", User)):
        if key in data:
            raw = data[key]
            obj = db.get(model, int(raw)) if raw not in (None, "") and str(raw).isdigit() else None
            if raw in (None, ""):
                errors[key] = ["This field may not be null."]
            elif obj is None:
                errors[key] = [f'Invalid pk "{raw}" - object does not exist.']
            else:
                values[f"{key}_id"] = obj.id
        elif not partial:
            errors[key] = ["This field is required."]
    if "permission_level" in data:
        if data["permission_level"] not in dict(sh.VERSION_SHARING_PERMISSION_LEVELS):
            errors["permission_level"] = [f'"{data["permission_level"]}" is not a valid choice.']
        else:
            values["permission_level"] = data["permission_level"]
    if "expires_at" in data:
        values["expires_at"] = _datetime_field(errors, data, "expires_at")
    for key in ("can_download", "can_annotate", "is_active"):
        if key in data:
            values[key] = 1 if _bool_field(errors, data, key, True) else 0
    if "notes" in data:
        values["notes"] = data["notes"]
    if not errors:
        version_id = values.get("document_version_id", instance.document_version_id if instance else None)
        user_id = values.get("user_id", instance.user_id if instance else None)
        clash = db.execute(select(DocumentVersionSharing.id).where(
            DocumentVersionSharing.document_version_id == version_id, DocumentVersionSharing.user_id == user_id,
            DocumentVersionSharing.id != (instance.id if instance else -1))).first()
        if clash:
            errors["non_field_errors"] = ["The fields document_version, user must make a unique set."]
    return values, errors


@router.get("/document-version-sharing")
def version_sharing_list(request: Request, page: str | None = None, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    stmt = _version_sharing_queryset(user).order_by(DocumentVersionSharing.shared_at.desc())
    return _paginate(request, db, stmt, page, sh.serialize_version_sharing)


@router.post("/document-version-sharing", status_code=201)
def version_sharing_create(data: dict[str, Any] = Body(...), user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    values, errors = _clean_version_sharing(db, data, None, partial=False)
    if errors:
        return _drf_error(errors)
    version = db.get(DocumentVersion, values["document_version_id"])
    document = version.document
    if not (document.user_id == user.id or sh.document_permission_level(db, document, user) == "admin"):
        return _drf_error({"error": "You don't have permission to share this document version"}, 403)
    s = DocumentVersionSharing(shared_by_id=user.id, permission_level="view", can_download=1, can_annotate=1,
                               is_active=1)
    for k, v in values.items():
        setattr(s, k, v)
    db.add(s)
    db.commit()
    return sh.serialize_version_sharing(s)


def _get_version_sharing(db: Session, user: User, sharing_id: int) -> DocumentVersionSharing | None:
    return db.execute(_version_sharing_queryset(user).where(DocumentVersionSharing.id == sharing_id)
                      ).scalar_one_or_none()


@router.get("/document-version-sharing/{sharing_id}")
def version_sharing_retrieve(sharing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_version_sharing(db, user, sharing_id)
    return _not_found() if s is None else sh.serialize_version_sharing(s)


def _version_sharing_update(sharing_id: int, data: dict[str, Any], partial: bool, user: User, db: Session):
    s = _get_version_sharing(db, user, sharing_id)
    if s is None:
        return _not_found()
    values, errors = _clean_version_sharing(db, data, s, partial=partial)
    if errors:
        return _drf_error(errors)
    for k, v in values.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return sh.serialize_version_sharing(s)


@router.put("/document-version-sharing/{sharing_id}")
def version_sharing_update(sharing_id: int, data: dict[str, Any] = Body(...), user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    return _version_sharing_update(sharing_id, data, False, user, db)


@router.patch("/document-version-sharing/{sharing_id}")
def version_sharing_partial_update(sharing_id: int, data: dict[str, Any] = Body(...),
                                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _version_sharing_update(sharing_id, data, True, user, db)


@router.delete("/document-version-sharing/{sharing_id}")
def version_sharing_destroy(sharing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get_version_sharing(db, user, sharing_id)
    if s is None:
        return _not_found()
    db.delete(s)
    db.commit()
    return Response(status_code=204)


# ====================================================================== views_collaborators.py
STAGE_LABELS = {0: "Draft", 1: "Under Review", 2: "Approved", 3: "Needs Revision"}


def _get_version_or_404(db: Session, version_id: int) -> DocumentVersion:
    v = db.get(DocumentVersion, version_id)
    if v is None:
        raise HTTPException(404, "No DocumentVersion matches the given query.")
    return v


def _version_collaborator_payload(s: DocumentSharing) -> dict[str, Any]:
    return {
        "id": s.id, "user": {"id": s.user.id, "full_name": sh.get_full_name(s.user), "email": s.user.email},
        "shared_by": {"id": s.shared_by.id, "full_name": sh.get_full_name(s.shared_by)},
        "shared_at": iso(s.shared_at), "expires_at": iso(s.expires_at),
        "permission_level": s.permission_level, "permission_level_display": sh.level_display(s.permission_level),
        "role_required": {"id": s.role_required.id, "name": s.role_required.name} if s.role_required else None,
        "can_share": bool(s.can_share), "can_download": bool(s.can_download), "can_annotate": bool(s.can_annotate),
        "can_delete_versions": bool(s.can_delete_versions), "notify_on_update": bool(s.notify_on_update),
        "notes": s.notes,
    }


@router.get("/versions/{version_id}/collaborators")
def version_collaborators(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """version_collaborators_view"""
    version = _get_version_or_404(db, version_id)
    document = version.document
    if not sh.can_manage_version_collaborators(db, version, user):
        # Django redirected to the document detail page with this message
        return JSONResponse({"detail": "You do not have permission to manage collaborators for this document version",
                             "document_id": document.id}, status_code=403)
    collaborators = db.execute(select(DocumentSharing).where(DocumentSharing.document_version_id == version.id,
                                                             DocumentSharing.is_active == 1)
                               .order_by(DocumentSharing.shared_at.desc())).scalars().all()
    shared_ids = [c.user_id for c in collaborators]
    available = db.execute(select(User).where(User.is_active == 1, User.id.not_in(shared_ids or [-1]),
                                              User.id != document.user_id)
                           .order_by(User.first_name, User.last_name)).scalars().all()
    roles = db.execute(select(Role).where(Role.is_active == 1).order_by(Role.name)).scalars().all()
    return {
        "version": {"id": version.id, "version_number": version.version_number,
                    "file_title_name": version.file_title_name, "stage_status": version.stage_status,
                    "stage_label": STAGE_LABELS.get(version.stage_status)},
        "document": {"id": document.id, "document_name": document.document_name,
                     "document_number": document.document_number},
        "collaborators": [_version_collaborator_payload(c) for c in collaborators],
        "available_users": [{"value": u.id, "label": f"{sh.get_full_name(u)} ({u.email})"} for u in available],
        "available_roles": [{"value": r.id, "label": r.name} for r in roles],
        "permission_levels": [{"value": v, "label": label} for v, label in sh.SHARING_PERMISSION_LEVELS],
    }


@router.post("/versions/{version_id}/collaborators/add")
def add_version_collaborator(version_id: int, body: VersionCollaboratorAddIn, user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """add_version_collaborator"""
    version = _get_version_or_404(db, version_id)
    document = version.document
    if not sh.can_manage_version_collaborators(db, version, user):
        return JSONResponse({"error": "Permission denied"}, status_code=403)
    try:
        target = None
        if body.user_id not in (None, "") and str(body.user_id).isdigit():
            target = db.execute(select(User).where(User.id == int(body.user_id), User.is_active == 1)
                                ).scalar_one_or_none()
        if target is None:
            return JSONResponse({"error": "No User matches the given query."}, status_code=400)
        if db.execute(select(DocumentSharing.id).where(DocumentSharing.document_version_id == version.id,
                                                       DocumentSharing.user_id == target.id)).first():
            return JSONResponse({"error": "Document version already shared with this user"}, status_code=400)
        role = None
        if body.role_id:
            role = db.execute(select(Role).where(Role.id == int(body.role_id), Role.is_active == 1)
                              ).scalar_one_or_none() if str(body.role_id).isdigit() else None
            if role is None:
                return JSONResponse({"error": "No Role matches the given query."}, status_code=400)
        sharing = DocumentSharing(
            document_id=document.id, document_version_id=version.id, user_id=target.id,
            permission_level=body.permission_level, role_required_id=role.id if role else None, shared_by_id=user.id,
            can_share=int(body.can_share), can_download=int(body.can_download), can_annotate=int(body.can_annotate),
            can_delete_versions=int(body.can_delete_versions), notify_on_update=int(body.notify_on_update),
            notes=body.notes, expires_at=sh.parse_datetime_input(body.expires_at), is_active=1,
        )
        db.add(sharing)
        db.flush()
        if body.notify_on_update:
            db.add(DocumentNotification(
                document_type="document_shared", document_id=document.id,
                description=f"{sh.get_full_name(user)} shared version '{version.version_number}' with you",
                receiver_id=target.id, sender_id=user.id, sent_for="document_sharing", is_seen=0,
            ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 — Django returned str(e) with 400
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {
        "success": True,
        "message": f"Successfully shared document version with {sh.get_full_name(target)}",
        "collaborator": {"id": sharing.id, "user_name": sh.get_full_name(target), "user_email": target.email,
                         "permission_level": sh.level_display(sharing.permission_level),
                         "shared_at": sharing.shared_at.strftime("%Y-%m-%d %H:%M")},
    }


def _get_version_sharing_row(db: Session, version: DocumentVersion, sharing_id: int) -> DocumentSharing:
    s = db.get(DocumentSharing, sharing_id)
    if s is None or s.document_version_id != version.id:
        raise HTTPException(404, "No DocumentSharing matches the given query.")
    return s


@router.post("/versions/{version_id}/collaborators/update/{sharing_id}")
def update_version_collaborator(version_id: int, sharing_id: int, data: dict[str, Any] | None = Body(None),
                                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """update_version_collaborator"""
    data = data or {}
    version = _get_version_or_404(db, version_id)
    sharing = _get_version_sharing_row(db, version, sharing_id)
    if not sh.can_manage_version_collaborators(db, version, user):
        return JSONResponse({"error": "Permission denied"}, status_code=403)
    try:
        sharing.permission_level = data.get("permission_level", sharing.permission_level)
        for key in ("can_share", "can_download", "can_annotate", "can_delete_versions", "notify_on_update"):
            if key in data:
                setattr(sharing, key, 1 if data[key] else 0)
        if "expires_at" in data:
            sharing.expires_at = sh.parse_datetime_input(data["expires_at"])
        if "role_id" in data:
            if data["role_id"]:
                role = db.get(Role, int(data["role_id"])) if str(data["role_id"]).isdigit() else None
                if role is None:
                    return JSONResponse({"error": "No Role matches the given query."}, status_code=400)
                sharing.role_required_id = role.id
            else:
                sharing.role_required_id = None
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"success": True, "message": "Collaborator permissions updated successfully"}


@router.post("/versions/{version_id}/collaborators/remove/{sharing_id}")
def remove_version_collaborator(version_id: int, sharing_id: int, user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    """remove_version_collaborator"""
    version = _get_version_or_404(db, version_id)
    sharing = _get_version_sharing_row(db, version, sharing_id)
    if not sh.can_manage_version_collaborators(db, version, user):
        return JSONResponse({"error": "Permission denied"}, status_code=403)
    name = sh.get_full_name(sharing.user)
    db.delete(sharing)
    db.commit()
    return {"success": True, "message": f"Successfully removed {name} from collaborators"}


@router.get("/search-users-version-sharing")
def search_users_for_version_sharing(q: str = "", version_id: str = "", user: User = Depends(get_current_user),
                                     db: Session = Depends(get_db)):
    """search_users_for_version_sharing"""
    if not q or not version_id:
        return {"users": []}
    try:
        vid = int(version_id)
    except ValueError:
        raise HTTPException(404, "No DocumentVersion matches the given query.")
    version = _get_version_or_404(db, vid)
    document = version.document
    if not sh.can_manage_version_collaborators(db, version, user):
        return {"users": []}
    shared_ids = select(DocumentSharing.user_id).where(DocumentSharing.document_version_id == version.id)
    like = f"%{q}%"
    users = db.execute(select(User).where(
        or_(User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like), User.username.ilike(like)),
        User.is_active == 1, User.id.not_in(shared_ids), User.id != document.user_id).limit(10)).scalars().all()
    return {"users": [{"id": u.id, "name": sh.get_full_name(u), "email": u.email, "username": u.username}
                      for u in users]}
