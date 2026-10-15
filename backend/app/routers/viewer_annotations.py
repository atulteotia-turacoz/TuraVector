"""Annotation APIs used by the PDFTron/Apryse WebViewer pages and the OnlyOffice editor.

Port of documents.views: create_annotation, get_annotations, delete_annotation,
bulk_create_annotations, get_annotations_xfdf, save_annotations_xfdf,
get_annotation_activities (+ format_time_ago), save_annotated_pdf,
get_reference_annotations, save_reference_annotations and the comment-sync
endpoints (get/save OnlyOffice comments, sync to OnlyOffice, debug, restore).

Response bodies and status codes follow the DRF views, including their habit
of turning a missing object (get_object_or_404 inside try/except) into a 500
with the error text.
"""
import datetime
import json
import os
import traceback

import pytz
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.permissions import has_module_permission
from app.core.utils import format_datetime_for_user
from app.database import get_db
from app.models import AnnotationActivity, DocumentAnnotation, DocumentVersion, ReferenceDocument, User, utcnow
from app.services import viewer_xfdf
from app.services.viewer_common import error, get_full_name, is_annotation_authorized, is_comment_sync_authorized

router = APIRouter(prefix="/api/viewer", tags=["viewer"])

XFDF_MEDIA_TYPE = "application/vnd.adobe.xfdf"


def _version(db: Session, version_id: int) -> DocumentVersion:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise LookupError("No DocumentVersion matches the given query.")
    return version


def _num(value, default):
    return default if value is None else value


# ------------------------------------------------------------------ DocumentAnnotation CRUD
@router.post("/annotations/{version_id}/create", status_code=201)
def create_annotation(version_id: int, body: dict = Body(default_factory=dict),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version = _version(db, version_id)
        if not (version.document.user_id == user.id or is_annotation_authorized(user)):
            return error(403, "Permission denied")
        annotation = DocumentAnnotation(
            document_version_id=version.id, user_id=user.id,
            annotation_type=body.get("type", "comment"), content=body.get("content", ""),
            page_number=body.get("page", 1), x_position=body.get("x", 0), y_position=body.get("y", 0),
            width=body.get("width", 0), height=body.get("height", 0), color=body.get("color", "#FFFF00"),
        )
        db.add(annotation)
        db.commit()
        return {"id": annotation.id, "message": "Annotation created successfully"}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return error(500, str(exc))


@router.get("/annotations/{version_id}")
def get_annotations(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version = _version(db, version_id)
        if not (version.document.user_id == user.id or is_annotation_authorized(user)):
            return error(403, "Permission denied")
        rows = db.execute(
            select(DocumentAnnotation).where(DocumentAnnotation.document_version_id == version.id)
            .order_by(DocumentAnnotation.created_at.desc())
        ).scalars().all()
        return {"annotations": [{
            "id": a.id, "type": a.annotation_type, "content": a.content, "page": a.page_number,
            "x": float(a.x_position), "y": float(a.y_position), "width": float(a.width), "height": float(a.height),
            "color": a.color, "user": f"{a.user.first_name} {a.user.last_name}",
            "created_at": format_datetime_for_user(a.created_at, user),
        } for a in rows]}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


@router.delete("/annotations/{annotation_id}/delete")
def delete_annotation(annotation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        annotation = db.get(DocumentAnnotation, annotation_id)
        if annotation is None:
            raise LookupError("No DocumentAnnotation matches the given query.")
        if not (annotation.user_id == user.id or is_annotation_authorized(user)):
            return error(403, "Permission denied")
        db.delete(annotation)
        db.commit()
        return {"message": "Annotation deleted successfully"}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return error(500, str(exc))


@router.post("/annotations/{version_id}/bulk-create", status_code=201)
def bulk_create_annotations(version_id: int, body: dict = Body(default_factory=dict),
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version = _version(db, version_id)
        # Django: is_authorized_user = True — every authenticated user may bulk-create
        items = body.get("annotations", [])
        if not items:
            return error(400, "No annotations provided")
        db.execute(delete(DocumentAnnotation).where(DocumentAnnotation.document_version_id == version.id,
                                                    DocumentAnnotation.user_id == user.id))
        created = 0
        for item in items:
            db.add(DocumentAnnotation(
                document_version_id=version.id, user_id=user.id,
                annotation_type=item.get("type", "comment"), content=item.get("content", ""),
                page_number=item.get("page", 1), x_position=item.get("x", 0), y_position=item.get("y", 0),
                width=item.get("width", 0), height=item.get("height", 0), color=item.get("color", "#FFFF00"),
            ))
            created += 1
        db.commit()
        return {"message": f"Successfully created {created} annotations", "count": created}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return error(500, str(exc))


# ------------------------------------------------------------------ XFDF
@router.get("/annotations/{version_id}/xfdf")
def get_annotations_xfdf(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = db.get(DocumentVersion, version_id)
    if version is None:  # Django swallowed the 404 and returned an empty XFDF document
        return Response(viewer_xfdf.EMPTY_XFDF, media_type=XFDF_MEDIA_TYPE)
    # Django: every authenticated user may load annotations
    return Response(viewer_xfdf.build_xfdf_for_user(db, version, user), media_type=XFDF_MEDIA_TYPE)


@router.post("/annotations/{version_id}/save-xfdf")
def save_annotations_xfdf(version_id: int, body: dict = Body(default_factory=dict),
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version = _version(db, version_id)
        # Django: every authenticated user may save (even while the document is under review)
        xfdf_data = body.get("xfdfData", "") or ""
        filename = viewer_xfdf.save_user_xfdf(db, version, user, xfdf_data)
        return {"message": "XFDF annotations saved successfully", "file": filename,
                "annotations_count": len(xfdf_data)}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc), detail=traceback.format_exc())


def format_time_ago(timestamp: datetime.datetime) -> str:
    """documents.views.format_time_ago (both values naive UTC)."""
    diff = utcnow() - timestamp
    if diff.days == 0:
        if diff.seconds < 60:
            return "Just now"
        if diff.seconds < 3600:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    if diff.days == 1:
        return "Yesterday"
    if diff.days < 7:
        return f"{diff.days} days ago"
    if diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    # Django formatted older dates with format_datetime_for_user(ts, None, "%b %d, %Y"); with its
    # timezone middleware disabled that resolved to the default zone (settings.TIME_ZONE).
    return pytz.UTC.localize(timestamp).astimezone(pytz.timezone(settings.TIME_ZONE)).strftime("%b %d, %Y")


@router.get("/annotations/{version_id}/activities")
def get_annotation_activities(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version = _version(db, version_id)
        if not (version.document.user_id == user.id or is_annotation_authorized(user)):
            return error(403, "Permission denied")
        rows = db.execute(
            select(AnnotationActivity).where(AnnotationActivity.document_version_id == version.id)
            .order_by(AnnotationActivity.created_at.desc()).limit(15)
        ).scalars().all()
        return {"activities": [{
            "user": get_full_name(a.user) or a.user.username,
            "action": a.action,
            "type": a.description,
            "timestamp": format_datetime_for_user(a.created_at, user),
            "relative_time": format_time_ago(a.created_at),
        } for a in rows]}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


@router.post("/save-pdf")
async def save_annotated_pdf(request: Request, version_id: str | None = None,
                             user: User = Depends(get_current_user)):
    try:
        pdf_blob = await request.body()
        if not pdf_blob:
            return error(400, "No PDF data provided")
        if version_id:
            pdf_filename = f"annotated_pdf_{user.id}_{version_id}.pdf"
        else:
            pdf_filename = f"annotated_pdf_{user.id}_{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}.pdf"
        pdf_path = os.path.join(viewer_xfdf.annotated_pdfs_dir(), os.path.basename(pdf_filename))
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        with open(pdf_path, "wb") as f:
            f.write(pdf_blob)
        return {"message": "Annotated PDF saved successfully", "file": pdf_filename, "version_id": version_id}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


# ------------------------------------------------------------------ reference annotations (stubs in Django too)
@router.get("/references/{reference_id}/annotations")
def get_reference_annotations(reference_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        if db.get(ReferenceDocument, reference_id) is None:
            raise LookupError("No ReferenceDocument matches the given query.")
        if not has_module_permission(db, user, "reference_library", "rl_view", "view"):
            return error(403, "Permission denied")
        return {"annotations": []}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


@router.post("/references/{reference_id}/annotations/save")
def save_reference_annotations(reference_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        if db.get(ReferenceDocument, reference_id) is None:
            raise LookupError("No ReferenceDocument matches the given query.")
        if not has_module_permission(db, user, "reference_library", "rl_edit", "edit"):
            return error(403, "Permission denied")
        return {"message": "Reference annotations saved successfully"}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


# ------------------------------------------------------------------ OnlyOffice <-> PDFTron comment sync
def _sync_guard(db: Session, version_id: int, user: User):
    version = _version(db, version_id)
    if version.document.user_id != user.id and not is_comment_sync_authorized(user):
        return version, error(403, "Permission denied")
    return version, None


@router.get("/comments/{version_id}/onlyoffice")
def get_onlyoffice_comments(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version, denied = _sync_guard(db, version_id, user)
        if denied is not None:
            return denied
        path = viewer_xfdf.comments_path(version.id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return {"comments": json.load(f)}
        return {"comments": []}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


@router.post("/comments/{version_id}/onlyoffice/save")
def save_onlyoffice_comments(version_id: int, body: dict = Body(default_factory=dict),
                             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version, denied = _sync_guard(db, version_id, user)
        if denied is not None:
            return denied
        if version.stage_status == 1 and user.user_type in ["student", "researcher"]:
            return error(403, "Cannot save comments - Document is under review")
        comments_data = body.get("comments", [])
        path = viewer_xfdf.comments_path(version.id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(comments_data, f, indent=2)
        if comments_data:
            viewer_xfdf.sync_onlyoffice_to_xfdf(version_id, comments_data, user.id)
            if version.document.user_id != user.id:
                viewer_xfdf.sync_onlyoffice_to_xfdf(version_id, comments_data, version.document.user_id)
        return {"message": "OnlyOffice comments saved and synced to PDFTron", "comments_count": len(comments_data)}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


@router.post("/comments/{version_id}/sync-to-onlyoffice")
def sync_pdftron_to_onlyoffice(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version, denied = _sync_guard(db, version_id, user)
        if denied is not None:
            return denied
        path = viewer_xfdf.xfdf_path(version.id, user.id)
        comments = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                comments = viewer_xfdf.convert_xfdf_to_onlyoffice_comments(f.read())
        return {"comments": comments}
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


@router.get("/comments/{version_id}/debug")
def debug_comment_sync(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version = _version(db, version_id)
        return viewer_xfdf.debug_comment_sync_info(version.id, user.id)
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc), traceback=traceback.format_exc())


@router.post("/comments/{version_id}/restore")
def restore_original_annotations(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        version, denied = _sync_guard(db, version_id, user)
        if denied is not None:
            return denied
        path = viewer_xfdf.xfdf_path(version_id, user.id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            cleaned = viewer_xfdf.merge_xfdf_with_onlyoffice_comments(content, [])
            with open(path, "w", encoding="utf-8") as f:
                f.write(cleaned)
            return {"message": "OnlyOffice synced annotations removed, original PDFTron annotations restored"}
        from fastapi.responses import JSONResponse
        return JSONResponse({"message": "No annotation file found"}, status_code=404)
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc), traceback=traceback.format_exc())
