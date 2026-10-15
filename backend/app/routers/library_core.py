"""Library module API — port of library/views.py (document library, reference library,
reference uploads (single + ZIP), reviewer assignment / management / completion).

Django views that answered with `messages.error(...)` + `redirect(...)` answer here with
`{"detail": <message>, "redirect": <SPA path>}` and the matching HTTP status; the frontend
shows the message as a toast and navigates to `redirect`.
"""
import logging
import mimetypes

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.files import media_path
from app.core.permissions import can, has_module_permission
from app.core.utils import iso
from app.database import get_db
from app.models import (
    AssignedReviewer, Brand, Country, Document, DocumentVersion, ReferenceDocument, ReferenceZip,
    TherapeuticArea, User,
)
from app.schemas.library_schemas import AssignReviewerIn, CompleteReviewIn
from app.services import library_service as svc

log = logging.getLogger("turadome.library")

router = APIRouter(prefix="/api/library", tags=["library"])

# SPA equivalents of the Django redirect targets
HOME = "/content-lab-management/dashboard/"                       # documents:home
CONTENT_LAB = "/content-lab-management/dashboard/"         # documents:content_lab_dashboard
LIBRARY = "/content-lab-management/library/"                           # library:library
REFERENCE_LIBRARY = "/content-lab-management/reference-library/"      # library:reference_library
UPLOAD_REFERENCE = "/content-lab-management/reference-library/upload/"
UPLOAD_ZIP = "/content-lab-management/reference-library/upload-zip/"  # library:upload_reference_zip
DOC_REFERENCES = "/content-lab-management/references/"       # documents:references


def document_detail_path(document_id: int) -> str:
    return f"/content-lab-management/document/{document_id}/"


def deny(message: str, redirect: str | None = None, status: int = 403) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message, "redirect": redirect})


def ok(message: str, redirect: str | None = None, **extra) -> dict:
    return {"success": True, "message": message, "redirect": redirect, **extra}


# =========================================================================== Document library
@router.get("/documents")
def library_view(
    search: str = "", document_type: str = "", brand: str = "", country: str = "", status: str = "",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not can(db, user, "can_access_library"):
        return deny("You do not have permission to access the document library.", HOME)
    if status:
        try:
            int(status)
        except ValueError:
            raise HTTPException(400, f"Field 'stage_status' expected a number but got '{status}'.")
    data = svc.library_documents(db, user, search, document_type, brand, country, status)
    data["selected"] = {"search": search, "document_type": document_type, "brand": brand,
                        "country": country, "status": status}
    data["is_manager_or_teacher"] = svc.is_manager_or_teacher(user)
    return data


# =========================================================================== Reference library
@router.get("/references")
def reference_library_view(
    search: str = "", type: str = "", brand: str = "",  # noqa: A002 — Django GET param name
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not has_module_permission(db, user, "content_lab", "cl_library", "view"):
        return deny("You do not have permission to access the reference library.", CONTENT_LAB)
    # NB: Django also applied `brand__name=<brand>`, but ReferenceDocument has no brand field, so
    # that filter could only error; the page never sends it. It is accepted and ignored here.
    return {
        "references": svc.reference_list(db, user, search, type),
        "brands": [{"id": b.id, "name": b.name} for b in db.execute(
            select(Brand).where(Brand.is_active == 1).order_by(Brand.id)).scalars()],
        "selected": {"search": search, "type": type, "brand": brand},
        "reference_types": svc.REFERENCE_TYPES,
    }


@router.get("/references/upload-options")
def upload_reference_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_module_permission(db, user, "content_lab", "cl_library", "create"):
        return deny("You do not have permission to upload references.", REFERENCE_LIBRARY)

    def active(model):
        return [{"id": o.id, "name": o.name} for o in db.execute(
            select(model).where(model.is_active == 1).order_by(model.id)).scalars()]

    return {
        "countries": active(Country),
        "brands": active(Brand),
        "therapeutic_areas": active(TherapeuticArea),
        "reference_types": svc.REFERENCE_TYPES,
        "reference_subtypes": svc.REFERENCE_SUBTYPES,
    }


@router.post("/references/upload")
def upload_reference_view(
    reference_type: str | None = Form(None),
    reference_subtype: str | None = Form(None),
    document_name: str | None = Form(None),
    country: str | None = Form(None),
    therapeutic_area: str | None = Form(None),
    ref_number: str | None = Form(None),
    ref_year: str | None = Form(None),
    reference_file: UploadFile | None = File(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not has_module_permission(db, user, "content_lab", "cl_library", "create"):
        return deny("You do not have permission to upload references.", REFERENCE_LIBRARY)
    has_file = reference_file is not None and bool(reference_file.filename)
    if not all([reference_type, reference_subtype, document_name, country, has_file]):
        return deny("All required fields must be filled", UPLOAD_REFERENCE, status=400)
    try:
        reference = svc.create_reference(
            db, user, reference_type=reference_type, reference_subtype=reference_subtype,
            document_name=document_name, country_id=country, therapeutic_area_id=therapeutic_area or None,
            ref_number=ref_number, ref_year=ref_year, upload=reference_file,
        )
    except Exception as e:  # noqa: BLE001 — Django: messages.error(f'Error uploading reference: {e}')
        db.rollback()
        return deny(f"Error uploading reference: {getattr(e, 'orig', None) or e}", None, status=400)
    return ok(f"Reference uploaded successfully with number: {reference.reference_number}", REFERENCE_LIBRARY,
              id=reference.id, reference_number=reference.reference_number)


def _get_active_reference(db: Session, reference_id: int) -> ReferenceDocument:
    ref = db.execute(select(ReferenceDocument).where(
        ReferenceDocument.id == reference_id, ReferenceDocument.is_active == 1)).scalar_one_or_none()
    if ref is None:
        raise HTTPException(404, "No ReferenceDocument matches the given query.")
    return ref


@router.get("/references/{reference_id}")
def reference_detail_view(reference_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_module_permission(db, user, "content_lab", "cl_library", "view"):
        return deny("You do not have permission to view reference details.", REFERENCE_LIBRARY)
    reference = _get_active_reference(db, reference_id)
    if not (svc.is_manager_or_teacher(user) or reference.user_id == user.id):
        return deny("You do not have permission to view this reference.", REFERENCE_LIBRARY)
    return {"reference": svc.serialize_reference(reference, detail=True)}


def _file_response(relative: str | None, filename: str | None, download: bool) -> FileResponse:
    path = media_path(relative) if relative else None
    if not path or not path.is_file():
        raise HTTPException(404, "File not found")
    name = filename or path.name
    media_type = mimetypes.guess_type(name)[0] or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=name,
                        content_disposition_type="attachment" if download else "inline")


@router.get("/references/{reference_id}/file")
def reference_file(reference_id: int, download: bool = Query(False),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Authenticated stand-in for `reference.reference_file.url` (Django served /media/ publicly)."""
    reference = db.get(ReferenceDocument, reference_id)
    if reference is None:
        raise HTTPException(404, "No ReferenceDocument matches the given query.")
    return _file_response(reference.reference_file, reference.file_name or None, download)


@router.delete("/references/{reference_id}")
def delete_reference_view(reference_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log.info("Delete reference called for reference_id: %s, user: %s", reference_id, user.username)
    if not can(db, user, "can_delete_library"):
        log.warning("User %s does not have delete_library permission", user.username)
        return deny("You do not have permission to delete references.", REFERENCE_LIBRARY)
    reference = db.execute(select(ReferenceDocument).where(
        ReferenceDocument.id == reference_id, ReferenceDocument.is_active == 1)).scalar_one_or_none()
    if reference is None:
        return deny("Reference not found: No ReferenceDocument matches the given query.", REFERENCE_LIBRARY, 404)
    if not (svc.is_manager_or_teacher(user) or reference.user_id == user.id):
        return deny("You do not have permission to delete this reference.", REFERENCE_LIBRARY)
    try:
        number, name = reference.reference_number, reference.document_name
        reference.is_active = 0  # soft delete
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return deny(f"Error deleting reference: {e}", f"/content-lab-management/reference-library/{reference_id}/", 500)
    return ok(f'Reference "{number}" ({name}) has been deleted successfully.', REFERENCE_LIBRARY)


# =========================================================================== Reference ZIPs
@router.get("/reference-zips/upload-options")
def upload_reference_zip_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can(db, user, "can_manage_reference_zip"):
        return deny("You do not have permission to upload reference ZIP files.", DOC_REFERENCES)
    return {"versions": svc.zip_upload_versions(db, user)}


@router.post("/reference-zips/upload")
def upload_reference_zip_view(
    version_id: str | None = Form(None),
    zip_file: UploadFile | None = File(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not can(db, user, "can_manage_reference_zip"):
        return deny("You do not have permission to upload reference ZIP files.", DOC_REFERENCES)
    has_file = zip_file is not None and bool(zip_file.filename)
    if not (version_id and has_file):
        return deny("Please select a document version and ZIP file", UPLOAD_ZIP, status=400)
    try:
        version = db.get(DocumentVersion, int(version_id))
        if version is None:
            raise LookupError("No DocumentVersion matches the given query.")
        ref_zip = svc.create_reference_zip(db, user, version, zip_file)
    except Exception as e:  # noqa: BLE001 — Django: messages.error(f'Error uploading reference ZIP: {e}')
        db.rollback()
        return deny(f"Error uploading reference ZIP: {getattr(e, 'orig', None) or e}", None, status=400)
    return ok(f"Reference ZIP uploaded successfully with number: {ref_zip.reference_zip_number}",
              REFERENCE_LIBRARY, id=ref_zip.id, reference_zip_number=ref_zip.reference_zip_number)


@router.get("/reference-zips/{zip_id}")
def reference_zip_detail_view(zip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ref_zip = db.get(ReferenceZip, zip_id)
    if ref_zip is None:
        raise HTTPException(404, "No ReferenceZip matches the given query.")
    if not has_module_permission(db, user, "content_lab", "cl_library", "view"):
        return deny("You do not have permission to view reference ZIP details.", DOC_REFERENCES)
    return {"ref_zip": svc.serialize_zip_detail(ref_zip)}


@router.get("/reference-zips/{zip_id}/file")
def reference_zip_file(zip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ref_zip = db.get(ReferenceZip, zip_id)
    if ref_zip is None:
        raise HTTPException(404, "No ReferenceZip matches the given query.")
    return _file_response(ref_zip.zip_file, ref_zip.file_title_name or None, True)


@router.delete("/reference-zips/{zip_id}")
def delete_reference_zip_view(zip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log.info("Delete reference ZIP called for zip_id: %s, user: %s", zip_id, user.username)
    if not can(db, user, "can_delete_library"):
        return deny("You do not have permission to delete reference ZIP files.", DOC_REFERENCES)
    ref_zip = db.get(ReferenceZip, zip_id)
    if ref_zip is None:
        return deny("Reference ZIP not found: No ReferenceZip matches the given query.", DOC_REFERENCES, 404)
    if not (svc.is_manager_or_teacher(user) or ref_zip.user_id == user.id):
        return deny("You do not have permission to delete this reference ZIP.", DOC_REFERENCES)
    try:
        number, title = ref_zip.reference_zip_number, ref_zip.file_title_name
        db.delete(ref_zip)  # hard delete (Django did not remove the file from disk either)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return deny(f"Error deleting reference ZIP: {e}", DOC_REFERENCES, 500)
    return ok(f'Reference ZIP "{number}" ({title}) has been deleted successfully.', DOC_REFERENCES)


# =========================================================================== Reviewer assignment
def _assign_guard(db: Session, user: User, document_id: int):
    """Shared checks of assign_reviewer_view (same order as Django). Returns (document, version) or a JSONResponse."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "No Document matches the given query.")
    if svc.has_approved_version(db, document.id):
        return deny("Cannot assign reviewer - This document has an approved version. Approved documents are locked.",
                    document_detail_path(document.id))
    version = svc.latest_version(db, document.id)
    if version is None:
        return deny("No versions found for this document", LIBRARY, 404)
    if not svc.is_manager_or_teacher(user):
        return deny("You do not have permission to assign reviewers", LIBRARY)
    return document, version


@router.get("/documents/{document_id}/assign-reviewer")
def assign_reviewer_form(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    guard = _assign_guard(db, user, document_id)
    if isinstance(guard, JSONResponse):
        return guard
    document, version = guard
    return {
        "document": {
            "id": document.id,
            "document_name": document.document_name,
            "document_number": document.document_number,
            "document_type": document.document_type.name if document.document_type else None,
            "brand": document.brand.name if document.brand else None,
            "country": document.country.name if document.country else None,
            "project": document.project.name if document.project else None,
        },
        "version": {
            "id": version.id,
            "version_number": version.version_number,
            "stage_status": version.stage_status,
            "file_title_name": version.file_title_name,
            "created_at": iso(version.created_at),
            "created_by": (f"{version.created_by.first_name or ''} {version.created_by.last_name or ''}".strip()
                           if version.created_by else ""),
        },
        "reviewers": svc.reviewer_candidates(db),
        "today": svc._local_now_date().isoformat(),
        "assigned_by": f"{user.first_name or ''} {user.last_name or ''}".strip(),
    }


@router.post("/documents/{document_id}/assign-reviewer")
def assign_reviewer_view(document_id: int, body: AssignReviewerIn,
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    guard = _assign_guard(db, user, document_id)
    if isinstance(guard, JSONResponse):
        return guard
    document, version = guard
    if not (body.reviewer_id and body.review_date):
        return deny("Reviewer and review date are required", f"/content-lab-management/document/{document_id}/assign-reviewer/", 400)
    try:
        try:
            reviewer = db.get(User, int(body.reviewer_id))
        except ValueError:
            reviewer = None
        if reviewer is None:
            raise LookupError("No User matches the given query.")
        svc.assign_reviewer(db, user, version, reviewer, body.review_date, body.remarks or "")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return deny(f"Error assigning reviewer: {e}", None, 400)
    return ok(f"Reviewer {reviewer.first_name} {reviewer.last_name} assigned successfully",
              document_detail_path(document.id))


@router.get("/documents/{document_id}/manage-reviewers")
def manage_reviewers_view(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "No Document matches the given query.")
    if not svc.is_superuser_or_manager(user):
        return deny("You do not have permission to manage reviewers", document_detail_path(document_id))
    return svc.manage_reviewers_data(db, document)


@router.post("/assignments/{assignment_id}/toggle-status")
def toggle_reviewer_status(assignment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assignment = db.get(AssignedReviewer, assignment_id)
    if assignment is None:
        return JSONResponse(status_code=404, content={"error": "No AssignedReviewer matches the given query."})
    if not svc.is_superuser_or_manager(user):
        return JSONResponse(status_code=403, content={"error": "Permission denied"})
    try:
        svc.toggle_assignment(db, user, assignment)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})
    return {
        "success": True,
        "is_active": bool(assignment.is_active),
        "message": f'Reviewer assignment {"activated" if assignment.is_active else "deactivated"} successfully',
    }


@router.post("/review/{assignment_id}/complete")
def complete_review(assignment_id: int, body: CompleteReviewIn,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assignment = db.execute(select(AssignedReviewer).where(
        AssignedReviewer.id == assignment_id, AssignedReviewer.user_id == user.id)).scalar_one_or_none()
    if assignment is None:
        return JSONResponse(status_code=404, content={"error": "No AssignedReviewer matches the given query."})
    try:
        svc.complete_review(db, user, assignment, body.remarks or "", body.approval_status)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})
    return {"message": "Review completed successfully"}
