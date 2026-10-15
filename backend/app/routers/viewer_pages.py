"""Viewer pages: the data behind each Django page view of the viewer module.

Port of documents.views: document_preview, document_preview_simple,
document_review_view (GET + POST), comments_references_view, draft_view,
reference_preview, get_file_name, link_references_view, unlink_reference_view,
document_editor and download_annotated_document, plus authenticated file
endpoints that replace Django's public /media/ links for the viewer.

Where Django did `messages.error(...); redirect(...)`, these endpoints answer
with a JSON body {detail, redirect, level} so the React page can show the
message and navigate to the same place.
"""
import mimetypes
import os

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.files import media_path
from app.core.permissions import has_module_permission, is_manager_like
from app.core.utils import iso
from app.database import get_db
from app.models import (
    AssignedReviewer,
    DocumentNotification,
    DocumentVersion,
    DocumentVersionReference,
    ReferenceDocument,
    User,
)
from app.services import viewer_review
from app.services.viewer_common import (
    document_out,
    error,
    file_exists,
    get_reference_or_404,
    get_version_or_404,
    has_approved_version,
    is_manager_or_teacher,
    link_out,
    linked_references,
    page_denied,
    reference_out,
    user_out,
    version_out,
)
from app.services.viewer_xfdf import annotated_pdfs_dir, xfdf_path

router = APIRouter(prefix="/api/viewer", tags=["viewer"])


# ------------------------------------------------------------------ files
def _serve(relative: str | None, missing_message: str, download: bool, filename: str | None = None):
    if not relative:
        raise HTTPException(404, missing_message)
    path = media_path(relative)
    if path is None or not path.is_file():
        raise HTTPException(404, f"{missing_message} The file '{os.path.basename(relative)}' is missing on the server.")
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=filename or os.path.basename(relative),
                        content_disposition_type="attachment" if download else "inline")


@router.head("/versions/{version_id}/file")
@router.get("/versions/{version_id}/file")
def version_file(version_id: int, download: bool = False, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """The document file (Django served it publicly at version.document_file.url)."""
    version = get_version_or_404(db, version_id)
    return _serve(version.document_file, "Document file not found.", download)


@router.head("/references/{reference_id}/file")
@router.get("/references/{reference_id}/file")
def reference_file(reference_id: int, download: bool = False, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    reference = get_reference_or_404(db, reference_id)
    return _serve(reference.reference_file, "Reference file not found.", download)


def _mark_notification_seen(db: Session, notification_id: str | None, user: User) -> None:
    if not notification_id:
        return
    try:
        nid = int(notification_id)
    except ValueError:
        return
    notification = db.execute(
        select(DocumentNotification).where(DocumentNotification.id == nid, DocumentNotification.receiver_id == user.id)
    ).scalar_one_or_none()
    if notification is not None:
        notification.is_seen = 1
        db.commit()


def _references_payload(db: Session, version) -> tuple[list, list]:
    links = linked_references(db, version)
    return [reference_out(link.reference) for link in links], [link_out(link) for link in links]


# ------------------------------------------------------------------ document_preview (preview_map.html)
@router.get("/versions/{version_id}/preview")
def document_preview(version_id: int, noti_id: str | None = None, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    document = version.document
    if document.user_id != user.id and not has_module_permission(db, user, "content_lab", "cl_documents", "view"):
        return page_denied(403, "You do not have permission to view this document", "/content-lab-management/library/")
    _mark_notification_seen(db, noti_id, user)
    references, links = _references_payload(db, version)
    return {"version": version_out(version), "document": document_out(document),
            "references": references, "linked_refs": links}


# ------------------------------------------------------------------ document_preview_simple
@router.get("/versions/{version_id}/preview-simple")
def document_preview_simple(version_id: int, noti_id: str | None = None, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    document = version.document
    if document.user_id != user.id and not is_manager_or_teacher(user):
        return page_denied(403, "You do not have permission to view this document", "/content-lab-management/dashboard/")
    _mark_notification_seen(db, noti_id, user)
    return {"version": version_out(version), "document": document_out(document),
            "debug_info": {"file_path": version.document_file or None,
                           "file_exists": file_exists(version.document_file)}}


# ------------------------------------------------------------------ document_review_view (review.html)
def _review_assignment(db: Session, version, user: User) -> AssignedReviewer | None:
    return db.execute(
        select(AssignedReviewer).where(AssignedReviewer.user_id == user.id,
                                       AssignedReviewer.document_version_id == version.id,
                                       AssignedReviewer.is_active == 1)
        .order_by(AssignedReviewer.id).limit(1).with_for_update()
    ).scalar_one_or_none()


def _review_entry(db: Session, version_id: str | None, user: User):
    """Shared start of GET and POST: id check, assignment check, first-open side effects."""
    if not version_id:
        return None, None, page_denied(400, "No document version specified.", "/content-lab-management/dashboard/")
    try:
        vid = int(version_id)
    except ValueError:
        raise HTTPException(404, "No DocumentVersion matches the given query.")
    version = get_version_or_404(db, vid)
    assignment = _review_assignment(db, version, user)
    if assignment is None and not user.is_superuser:
        return None, None, page_denied(403, "You are not assigned to review this document.",
                                       "/content-lab-management/reviewer-dashboard/")
    if assignment is not None and not assignment.started_at:
        viewer_review.mark_review_started(db, assignment, version, user)
    else:
        db.commit()  # release the row lock
    return version, assignment, None


def _review_context(db: Session, version, assignment):
    previous = db.execute(
        select(AssignedReviewer).where(AssignedReviewer.document_version_id == version.id,
                                       AssignedReviewer.is_completed == 1,
                                       AssignedReviewer.remarks.is_not(None), AssignedReviewer.remarks != "")
        .order_by(AssignedReviewer.updated_at.desc())
    ).scalars().all()
    references, links = _references_payload(db, version)
    return {
        "version": version_out(version),
        "document": document_out(version.document),
        "assignment": None if assignment is None else {
            "id": assignment.id, "started_at": iso(assignment.started_at), "review_date": iso(assignment.review_date),
            "is_completed": bool(assignment.is_completed), "remarks": assignment.remarks,
        },
        "previous_reviews": [{"id": r.id, "user": user_out(r.user), "remarks": r.remarks,
                              "updated_at": iso(r.updated_at)} for r in previous],
        "references": references,
        "linked_refs": links,
        "page_title": "Document Review",
    }


@router.get("/review")
def document_review(id: str | None = Query(None), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    version, assignment, denied = _review_entry(db, id, user)
    if denied is not None:
        return denied
    return _review_context(db, version, assignment)


@router.post("/review")
def submit_review(id: str | None = Query(None), body: dict = Body(default_factory=dict),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version, assignment, denied = _review_entry(db, id, user)
    if denied is not None:
        return denied
    comments = str(body.get("comments") or "").strip()
    decision = body.get("decision")
    if not comments:
        raise HTTPException(400, "Please enter review comments.")
    if not decision:
        raise HTTPException(400, "Please select a review decision.")
    result = viewer_review.submit_review(db, assignment, version, user, comments, str(decision))
    if result["level"] == "error":
        return JSONResponse({"detail": result["message"], "warnings": result["warnings"]}, status_code=400)
    return {"message": result["message"], "warnings": result["warnings"], "redirect": "/content-lab-management/reviewer-dashboard/"}


# ------------------------------------------------------------------ comments_references_view
@router.get("/versions/{version_id}/comments")
def comments_references(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    document = version.document
    if document.user_id != user.id and not has_module_permission(db, user, "content_lab", "cl_documents", "view"):
        return page_denied(403, "You do not have permission to view this document", "/content-lab-management/library/")
    links = linked_references(db, version)
    reviews = db.execute(
        select(AssignedReviewer).where(AssignedReviewer.document_version_id == version.id,
                                       AssignedReviewer.remarks.is_not(None), AssignedReviewer.remarks != "")
        .order_by(AssignedReviewer.created_at.desc())
    ).scalars().all()
    return {
        "version": version_out(version),
        "document": document_out(document),
        "references": [reference_out(link.reference) for link in links],
        "reviews": [{
            "id": r.id, "user": user_out(r.user), "is_completed": bool(r.is_completed),
            "completed_at": iso(r.completed_at), "started_at": iso(r.started_at), "remarks": r.remarks,
            "created_at": iso(r.created_at), "modified_by": user_out(r.modified_by),
        } for r in reviews],
    }


# ------------------------------------------------------------------ draft_view
@router.get("/versions/{version_id}/draft")
def draft(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    document = version.document
    if document.user_id != user.id and not is_manager_or_teacher(user):
        return page_denied(403, "You do not have permission to edit this document", "/content-lab-management/library/")
    references, links = _references_payload(db, version)
    # Django rendered 'documents/draft.html', which does not exist in the project (TemplateDoesNotExist).
    return {"version": version_out(version), "document": document_out(document), "references": references,
            "linked_refs": links, "template_missing": True}


# ------------------------------------------------------------------ reference_preview
@router.get("/references/{reference_id}/preview")
def reference_preview(reference_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reference = get_reference_or_404(db, reference_id)
    has_access = (
        reference.user_id == user.id
        or user.user_type in ["manager", "teacher"]
        or is_manager_like(user)
        or has_module_permission(db, user, "content_lab", "cl_reviewer_dashboard", "view")
    )
    if not has_access:
        return page_denied(403, "You do not have permission to view this reference", "/content-lab-management/reference-library/")
    return {"reference": reference_out(reference, full=True)}


@router.post("/get-file-name")
def get_file_name(body: dict = Body(default_factory=dict), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    try:
        ref_id = body.get("refId")
        if not ref_id:
            return error(400, "Reference ID is required")
        reference = db.get(ReferenceDocument, int(ref_id))
        if reference is None:
            raise HTTPException(404, "No ReferenceDocument matches the given query.")
        if reference.user_id != user.id and not is_manager_or_teacher(user):
            return error(403, "Permission denied")
        return {"file_name": reference.file_name}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        return error(500, str(exc))


# ------------------------------------------------------------------ link / unlink references
def _link_guard(db: Session, version_id: int, user: User):
    version = get_version_or_404(db, version_id)
    document = version.document
    if document.user_id != user.id and not user.is_superuser:
        return version, page_denied(403, "You do not have permission to link references to this document version.",
                                    f"/content-lab-management/document/{document.id}/history/")
    return version, None


@router.get("/versions/{version_id}/link-references")
def link_references_page(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version, denied = _link_guard(db, version_id, user)
    if denied is not None:
        return denied
    document = version.document
    stmt = select(ReferenceDocument).where(ReferenceDocument.is_active == 1)
    if not (user.user_type in ["manager", "teacher"] or is_manager_like(user) or user.is_superuser):
        stmt = stmt.where(ReferenceDocument.user_id == user.id)
    linked_ids = select(DocumentVersionReference.reference_id).where(
        DocumentVersionReference.document_version_id == version.id, DocumentVersionReference.is_active == 1)
    available = db.execute(stmt.where(ReferenceDocument.id.not_in(linked_ids))).scalars().all()
    links = linked_references(db, version)
    return {
        "document": document_out(document),
        "document_version": version_out(version),
        "available_references": [reference_out(r) for r in available],
        "linked_references": [link_out(link) for link in links],
    }


@router.post("/versions/{version_id}/link-references")
def link_references(version_id: int, body: dict = Body(default_factory=dict), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    version, denied = _link_guard(db, version_id, user)
    if denied is not None:
        return denied
    reference_ids = body.get("reference_ids") or []
    if not isinstance(reference_ids, list):
        reference_ids = [reference_ids]
    notes = body.get("notes", "") or ""
    linked_count = 0
    errors: list[str] = []
    for ref_id in reference_ids:
        try:
            reference = db.get(ReferenceDocument, int(ref_id))
            if reference is None:
                errors.append(f"Error linking reference {ref_id}: No ReferenceDocument matches the given query.")
                continue
            # get_or_create on (document_version, reference): an existing row — even an
            # inactive one — is returned untouched, exactly like Django.
            existing = db.execute(
                select(DocumentVersionReference).where(DocumentVersionReference.document_version_id == version.id,
                                                       DocumentVersionReference.reference_id == reference.id)
            ).scalar_one_or_none()
            if existing is None:
                db.add(DocumentVersionReference(document_version_id=version.id, reference_id=reference.id,
                                                linked_by_id=user.id, notes=notes, is_active=1))
                db.commit()
                linked_count += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(f"Error linking reference {ref_id}: {exc}")
    message = (f"Successfully linked {linked_count} reference(s) to the document version."
               if linked_count > 0 else None)
    return {"linked_count": linked_count, "message": message, "errors": errors,
            "redirect": f"/content-lab-management/document/{version.document_id}/history/"}


@router.post("/versions/{version_id}/unlink-reference/{reference_id}")
def unlink_reference(version_id: int, reference_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    version, denied = _link_guard(db, version_id, user)
    if denied is not None:
        return denied
    redirect = f"/content-lab-management/version/{version.id}/link-references/"
    link = db.execute(
        select(DocumentVersionReference).where(DocumentVersionReference.document_version_id == version.id,
                                               DocumentVersionReference.reference_id == reference_id,
                                               DocumentVersionReference.is_active == 1)
    ).scalar_one_or_none()
    if link is None:
        return {"level": "error", "message": "Error unlinking reference: No DocumentVersionReference matches the given query.",
                "redirect": redirect}
    link.is_active = 0
    db.commit()
    return {"level": "success", "message": "Reference unlinked successfully.", "redirect": redirect}


# ------------------------------------------------------------------ document_editor (redirect logic only)
@router.get("/editor/{version_id}")
def document_editor(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    detail = f"/content-lab-management/document/{version.document_id}/"
    if has_approved_version(db, version.document):
        return {"level": "error", "redirect": detail,
                "message": "Cannot edit document - This document has an approved version. Approved documents are locked."}
    if version.stage_status == 1 and user.user_type in ["student", "researcher"]:
        return {"level": "error", "redirect": detail, "message": "Cannot edit document - This document is under review."}
    if version.user_id != user.id and not has_module_permission(db, user, "content_lab", "cl_documents", "edit"):
        return {"level": "error", "redirect": "/content-lab-management/dashboard/",
                "message": "You do not have permission to edit this document"}
    if not settings.ENABLE_ONLYOFFICE_EDITOR:
        return {"level": "warning", "redirect": detail,
                "message": "OnlyOffice editor is not configured. Please download the file to edit."}
    return {"level": None, "message": None, "redirect": f"/content-lab-management/onlyoffice/edit/?id={version_id}"}


# ------------------------------------------------------------------ download_annotated_document
@router.get("/versions/{version_id}/download-annotated")
def download_annotated(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    document = version.document
    is_assigned_reviewer = db.execute(
        select(AssignedReviewer.id).join(DocumentVersion, AssignedReviewer.document_version_id == DocumentVersion.id)
        .where(AssignedReviewer.user_id == user.id, AssignedReviewer.is_active == 1,
               DocumentVersion.document_id == document.id).limit(1)
    ).first() is not None
    if (document.user_id != user.id
            and not has_module_permission(db, user, "content_lab", "cl_documents", "view")
            and not is_assigned_reviewer):
        return page_denied(403, "You do not have permission to download this document",
                           f"/content-lab-management/document/{document.id}/")

    if not version.document_file:
        return page_denied(400, "Error downloading document: The 'document_file' attribute has no file associated with it.",
                           f"/content-lab-management/document/{version_id}/")
    base = os.path.splitext(version.file_name)[0]
    doc_dir = os.path.dirname(str(media_path(version.document_file)))
    candidates = [
        os.path.join(annotated_pdfs_dir(), f"annotated_pdf_{user.id}_{version.id}.pdf"),
        os.path.join(annotated_pdfs_dir(), f"annotated_pdf_{version.id}.pdf"),
        os.path.join(doc_dir, f"{base}_annotated.pdf"),
    ]
    for pdf_path in candidates:
        if os.path.exists(pdf_path):
            return FileResponse(pdf_path, media_type="application/pdf", filename=f"{base}_annotated.pdf")

    if os.path.exists(xfdf_path(version.id, user.id)):
        if (version.file_extension or "").lower() == "pdf":
            message = "Annotations exist but have not been merged. Please use the Export button in preview."
        else:
            message = None
    else:
        message = "No annotations found. Downloading original document."
    # Django redirected to version.document_file.url (shown inline by the browser)
    response = _serve(version.document_file, "Document file not found.", download=False)
    if message:
        response.headers["X-Viewer-Message"] = message
    return response
