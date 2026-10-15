"""Review workflow, status updates, file replacement and deletion.

Ports of documents.views: send_for_review, send_for_revision, mark_complete,
update_document_status, update_version_status, change_version_file_view and
library.views: delete_document_view, delete_document_version_view.
"""
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.email import send_email_with_logging
from app.core.files import document_upload_dir, media_path
from app.core.permissions import can, has_module_permission
from app.core.utils import format_datetime_for_user, iso
from app.database import get_db
from app.models import Document, DocumentAnnotation, DocumentVersion, User, utcnow
from app.services.doccore_common import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    STAGE_CHOICES,
    STAGE_DISPLAY,
    delete_document_cascade,
    delete_version_cascade,
    file_extension_error,
    gfn,
    get_or_404,
    notifiable_teachers_managers,
    page_redirect,
    save_like_django,
    sent_for_text,
    stage_display,
    status_notification_type,
    upload_size,
)
from app.schemas.doccore_schemas import StatusIn, WorkflowIn
from app.services.doccore_documents import notify

log = logging.getLogger("turadome.doccore")

router = APIRouter(prefix="/api/doccore", tags=["doccore"])


def _frontend(path: str) -> str:
    """request.build_absolute_uri(path) — links in emails point at the React app."""
    return f"{settings.FRONTEND_URL.rstrip('/')}{path}"


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _version_lookup(db: Session, version_id: Any) -> DocumentVersion | None:
    try:
        return db.get(DocumentVersion, int(version_id))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- send for review
@router.post("/workflow/send-for-review")
def send_for_review(body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        if not body.versionId:
            return _error(400, "Version ID is required")
        version = _version_lookup(db, body.versionId)
        if version is None:
            return _error(404, "Document version not found")
        document = version.document
        if document.user_id != user.id and not user.user_type == "student":
            return _error(403, "You do not have permission to send this document for review")
        if version.stage_status != 0:
            return _error(400, "Only draft documents can be sent for review")

        version.stage_status = 1
        version.modified_by_id = user.id
        document.stage_status = 1
        document.modified_by_id = user.id
        db.flush()
        try:
            for u in notifiable_teachers_managers(db):
                notify(db, receiver_id=u.id, sender_id=user.id, document_type="review_request", document_id=document.id,
                       description=f'Document "{document.document_name}" has been sent for review by {user.first_name} {user.last_name}',
                       sent_for="review")
            db.flush()
        except Exception as exc:  # noqa: BLE001
            log.error("Error creating notifications: %s", exc)
        db.commit()
        return {"message": "Document sent for review successfully", "status": "Under Review",
                "document_id": document.id, "version_id": version.id}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return _error(500, str(exc))


# ---------------------------------------------------------------- send for revision / mark complete
_REVISION_BODY = '''
Dear {owner},

Your document has been reviewed and requires revision.

Document Details:
- Document Name: {title}
- Document Number: {number}
- Document Type: {dtype}
- Version: {version}
- Revision Date: {date}
- Reviewed by: {reviewer}

Status: Draft Under Revision

Please review the comments and make the necessary changes to your document.

You can access your document at: {link}

Best regards,
TuraVector Document Management System
            '''

_APPROVAL_BODY = '''
Dear {owner},

Congratulations! Your document has been reviewed and approved.

Document Details:
- Document Name: {title}
- Document Number: {number}
- Document Type: {dtype}
- Version: {version}
- Approval Date: {date}
- Approved by: {reviewer}

Status: Approved

Your document is now complete and has been added to the approved documents library.

You can access your document at: {link}

Best regards,
TuraVector Document Management System
            '''


def _review_decision(db: Session, user: User, body: WorkflowIn, *, new_status: int) -> Any:
    try:
        version = _version_lookup(db, body.versionId)
        if version is None:
            # get_object_or_404 inside the try block -> Http404 caught as a generic error
            return _error(500, "No DocumentVersion matches the given query.")
        document = version.document
        if not has_module_permission(db, user, "content_lab", "cl_review", "edit"):
            return _error(403, "Permission denied")

        version.stage_status = new_status
        version.updated_at = utcnow()
        document.stage_status = new_status
        document.updated_at = utcnow()
        owner = document.user
        if owner.id != user.id:
            if new_status == 3:
                notify(db, receiver_id=owner.id, sender_id=user.id, document_type="document_rejected",
                       document_id=document.id,
                       description=f'Your document "{version.file_title_name}" has been sent for revision by {gfn(user)}',
                       sent_for="revision_request")
            else:
                notify(db, receiver_id=owner.id, sender_id=user.id, document_type="document_approved",
                       document_id=document.id,
                       description=f'Your document "{version.file_title_name}" has been approved and marked as complete by {gfn(user)}',
                       sent_for="approval_notification")
        db.commit()

        email_sent = False
        if owner.email:
            fields = dict(
                owner=gfn(owner) or owner.username,
                title=version.file_title_name,
                number=document.document_number,
                dtype=document.document_type.name,
                version=version.version_number,
                date=format_datetime_for_user(utcnow(), user),
                reviewer=gfn(user) or user.username,
                link=_frontend(f"/content-lab-management/preview/{version.id}/"),
            )
            if new_status == 3:
                subject = f"Document Revision Required - {document.document_number}"
                message, email_type = _REVISION_BODY.format(**fields), "revision_request"
            else:
                subject = f"Document Approved - {document.document_number}"
                message, email_type = _APPROVAL_BODY.format(**fields), "approval_notification"
            email_sent, _ = send_email_with_logging(
                db, subject, message, [owner.email], email_type, from_email=settings.DEFAULT_FROM_EMAIL,
                sender_user=user, recipient_user=owner, document=document, document_version=version)

        if new_status == 3:
            return {"message": "Document sent for revision successfully", "status": "Draft Under Revision",
                    "email_sent": email_sent, "notification_sent": True}
        return {"message": "Document marked as complete successfully", "status": "Approved",
                "email_sent": email_sent, "notification_sent": True}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return _error(500, str(exc))


@router.post("/workflow/send-for-revision")
def send_for_revision(body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _review_decision(db, user, body, new_status=3)


@router.post("/workflow/mark-complete")
def mark_complete(body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _review_decision(db, user, body, new_status=2)


# ---------------------------------------------------------------- status updates (admin)
def _status_perm(db: Session, user: User) -> bool:
    return bool(user.is_superuser or user.is_staff
                or has_module_permission(db, user, "content_lab", "cl_documents", "edit"))


def _clean_stage(raw: Any) -> int:
    """TypedChoiceField(coerce=int) on stage_status."""
    if raw is None or str(raw).strip() == "":
        raise HTTPException(400, detail={"message": "Please correct the errors below.",
                                         "errors": {"stage_status": "This field is required."}})
    try:
        value = int(str(raw).strip())
    except ValueError:
        value = None
    if value not in STAGE_DISPLAY:
        raise HTTPException(400, detail={"message": "Please correct the errors below.", "errors": {
            "stage_status": f"Select a valid choice. {raw} is not one of the available choices."}})
    return value


_CHOICES = [{"value": v, "label": l} for v, l in STAGE_CHOICES]


@router.get("/documents/{document_id}/status")
def document_status_page(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = get_or_404(db, Document, document_id, "Document")
    if not _status_perm(db, user):
        raise page_redirect("You do not have permission to update document status", f"/content-lab-management/document/{document.id}/")
    return {
        "page_title": "Update Document Status",
        "document": {"id": document.id, "document_number": document.document_number,
                     "document_name": document.document_name, "stage_status": document.stage_status,
                     "stage_status_display": stage_display(document.stage_status)},
        "choices": _CHOICES,
    }


@router.post("/documents/{document_id}/status")
def document_status_update(document_id: int, body: StatusIn, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    document = get_or_404(db, Document, document_id, "Document")
    detail = f"/content-lab-management/document/{document.id}/"
    if not _status_perm(db, user):
        raise page_redirect("You do not have permission to update document status", detail)
    value = _clean_stage(body.stage_status)
    # Django read the "old" status after the form had applied the new one, so its message said
    # "from X to X". We capture the real previous status first.
    old_status = stage_display(document.stage_status)
    document.stage_status = value
    document.modified_by_id = user.id
    document.updated_at = utcnow()
    new_status = stage_display(document.stage_status)
    if document.user_id != user.id:
        notify(db, receiver_id=document.user_id, sender_id=user.id,
               document_type=status_notification_type(document.stage_status), document_id=document.id,
               description=f'Document status changed from "{old_status}" to "{new_status}" by {gfn(user)}',
               sent_for=sent_for_text(document.document_name))
    db.commit()
    return {"message": f'Document status updated from "{old_status}" to "{new_status}"', "redirect": detail}


@router.get("/versions/{version_id}/status")
def version_status_page(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = get_or_404(db, DocumentVersion, version_id, "DocumentVersion")
    if not _status_perm(db, user):
        raise page_redirect("You do not have permission to update version status", f"/content-lab-management/document/{version.document_id}/")
    d = version.document
    return {
        "page_title": "Update Version Status",
        "version": {"id": version.id, "version_number": version.version_number, "stage_status": version.stage_status,
                    "stage_status_display": STAGE_DISPLAY.get(version.stage_status, "")},
        "document": {"id": d.id, "document_number": d.document_number, "document_name": d.document_name},
        "choices": _CHOICES,
    }


@router.post("/versions/{version_id}/status")
def version_status_update(version_id: int, body: StatusIn, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    version = get_or_404(db, DocumentVersion, version_id, "DocumentVersion")
    detail = f"/content-lab-management/document/{version.document_id}/"
    if not _status_perm(db, user):
        raise page_redirect("You do not have permission to update version status", detail)
    value = _clean_stage(body.stage_status)
    old_status = STAGE_DISPLAY.get(version.stage_status, "Unknown")  # real previous status
    version.stage_status = value
    version.modified_by_id = user.id
    version.updated_at = utcnow()
    new_status = STAGE_DISPLAY.get(version.stage_status, "Unknown")
    document = version.document
    if version.stage_status in (1, 2):
        document.stage_status = version.stage_status
        document.updated_at = utcnow()
    if document.user_id != user.id:
        notify(db, receiver_id=document.user_id, sender_id=user.id,
               document_type=status_notification_type(version.stage_status), document_id=document.id,
               description=f'Version {version.version_number} status changed from "{old_status}" to "{new_status}" by {gfn(user)}',
               sent_for=sent_for_text(document.document_name))
    db.commit()
    return {"message": f'Version status updated from "{old_status}" to "{new_status}"', "redirect": detail}


# ---------------------------------------------------------------- change version file (admin)
def _change_file_perm(user: User, version_id: int) -> None:
    if not (user.is_staff or user.is_superuser):
        raise page_redirect("You do not have permission to change document files.", f"/content-lab-management/preview/{version_id}/")


def _annotation_count(db: Session, version_id: int) -> int:
    return db.execute(select(func.count(DocumentAnnotation.id)).where(DocumentAnnotation.document_version_id == version_id)).scalar_one()


@router.get("/versions/{version_id}/change-file")
def change_file_page(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _change_file_perm(user, version_id)
    version = get_or_404(db, DocumentVersion, version_id, "DocumentVersion")
    return {
        "version": {
            "id": version.id, "version_number": version.version_number, "file_name": version.file_name,
            "file_extension": version.file_extension, "file_title_name": version.file_title_name,
            "stage_status_display": stage_display(version.stage_status),
            "updated_at": iso(version.updated_at),
        },
        "annotation_count": _annotation_count(db, version.id),
    }


@router.post("/versions/{version_id}/change-file")
def change_file_submit(version_id: int, new_file: UploadFile | None = File(None),
                       confirm_delete_annotations: str | None = Form(None),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _change_file_perm(user, version_id)
    version = get_or_404(db, DocumentVersion, version_id, "DocumentVersion")
    errors: dict[str, str] = {}
    if new_file is None or not new_file.filename:
        errors["new_file"] = "This field is required."
    elif upload_size(new_file) == 0:
        errors["new_file"] = "The submitted file is empty."
    else:
        msg = file_extension_error(new_file.filename, ALLOWED_DOCUMENT_EXTENSIONS)
        if msg:
            errors["new_file"] = msg
        elif upload_size(new_file) > 50 * 1024 * 1024:
            errors["new_file"] = "File size must not exceed 50MB"
    if str(confirm_delete_annotations or "").lower() in ("", "false", "0", "off"):
        errors["confirm_delete_annotations"] = "This field is required."
    if errors:
        raise HTTPException(400, detail={"message": "Please correct the errors below.", "errors": errors})

    warning = None
    try:
        old_path = media_path(version.document_file) if version.document_file else None
        count = _annotation_count(db, version.id)
        db.execute(delete(DocumentAnnotation).where(DocumentAnnotation.document_version_id == version.id))
        rel = save_like_django(new_file, document_upload_dir(version.id))
        version.document_file = rel
        version.file_name = new_file.filename
        version.file_extension = new_file.filename.split(".")[-1].lower()
        version.modified_by_id = user.id
        version.updated_at = utcnow()
        db.commit()
        if old_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception as exc:  # noqa: BLE001
                warning = f"Could not delete old file: {exc}"
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error replacing file: {exc}")
    return {
        "message": (f"Successfully replaced file for version {version.version_number}. "
                    f"Deleted {count} annotation(s)."),
        "warning": warning,
        "redirect": f"/content-lab-management/preview/{version.id}/",
    }


# ---------------------------------------------------------------- deletion (library.views)
def _result(status: int, message: str, redirect: str) -> JSONResponse:
    """JSON {message} — success 200; failures keep Django's message text with a 4xx status."""
    ok = status == 200
    return JSONResponse({"success": ok, "level": "success" if ok else "error", "message": message,
                         "redirect": redirect}, status_code=status)


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """library.views.delete_document_view (redirects to library:library)."""
    back = "/content-lab-management/library/"

    def fail(msg: str, status: int = 400) -> JSONResponse:
        return _result(status, msg, back)

    document = db.execute(select(Document).where(Document.id == document_id, Document.is_active == 1)).scalar_one_or_none()
    if document is None:
        return fail("Document not found: No Document matches the given query.", 404)
    is_owner = document.user_id == user.id
    can_delete_own = can(db, user, "can_delete_documents") and is_owner
    can_delete_all = can(db, user, "can_delete_all_documents")
    if not (can_delete_own or can_delete_all):
        return fail("You do not have permission to delete this document.", 403)
    if document.stage_status != 0 and not can_delete_all:
        stage_name = STAGE_DISPLAY.get(document.stage_status, "Unknown")
        return fail(f"Cannot delete document. Only draft documents can be deleted. Current status: {stage_name}")
    non_draft = db.execute(select(func.count(DocumentVersion.id)).where(
        DocumentVersion.document_id == document.id, DocumentVersion.stage_status != 0)).scalar_one()
    if non_draft and not can_delete_all:
        return fail(f"Cannot delete document. {non_draft} version(s) are not in draft status. "
                    "All versions must be in draft status to delete the document.")
    number, name = document.document_number, document.document_name
    version_count = db.execute(select(func.count(DocumentVersion.id)).where(DocumentVersion.document_id == document.id)).scalar_one()
    try:
        delete_document_cascade(db, document.id)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"Error deleting document: {exc}", 500)
    return _result(200, f'Document "{number}" ({name}) and all {version_count} version(s) have been deleted successfully.', back)


@router.delete("/versions/{version_id}")
def delete_version(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """library.views.delete_document_version_view (redirects to the document detail page)."""
    version = db.get(DocumentVersion, version_id)
    if version is None:
        return _result(404, "Document version not found: No DocumentVersion matches the given query.", "/content-lab-management/library/")
    document = version.document
    back = f"/content-lab-management/document/{document.id}/"

    def fail(msg: str, status: int = 400) -> JSONResponse:
        return _result(status, msg, back)

    is_owner = version.user_id == user.id or document.user_id == user.id
    can_own = can(db, user, "can_delete_document_versions") and is_owner
    can_all = can(db, user, "can_delete_all_document_versions")
    if not (can_own or can_all):
        return fail("You do not have permission to delete this document version.", 403)
    if version.stage_status != 0 and not can_all:
        stage_name = STAGE_DISPLAY.get(version.stage_status, "Unknown")
        return fail(f"Cannot delete version. Only draft versions can be deleted. Current status: {stage_name}")
    total = db.execute(select(func.count(DocumentVersion.id)).where(DocumentVersion.document_id == document.id)).scalar_one()
    if total <= 1 and not can_all:
        return fail("Cannot delete version. Document must have at least one version. "
                    "To delete the entire document, use the document delete option.")
    number, title = version.version_number, version.file_title_name
    try:
        delete_version_cascade(db, [version.id])
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"Error deleting document version: {exc}", 500)
    return _result(200, f'Document version "{number}" ({title}) has been deleted successfully.', back)
