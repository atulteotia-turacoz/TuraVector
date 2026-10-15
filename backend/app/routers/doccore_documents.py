"""Upload, detail, edit, new version, history and document-reference (ZIP) pages.

Ports of documents.upload_with_owner (upload_document_with_owner_view, search_users_api),
documents.views (upload_document_view, create_new_version, document_detail, document_edit,
document_history_view, references_view) and library.views.document_history_view. The ZIP download/delete buttons on the
references page use the library module's /api/library/reference-zips/{id} endpoints.
"""
import math

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.files import media_path
from app.core.permissions import can, has_module_permission, is_manager_like
from app.core.utils import iso
from app.database import get_db
from app.models import (
    AssignedReviewer,
    Brand,
    Country,
    Document,
    DocumentSharing,
    DocumentType,
    DocumentVersion,
    ReferenceZip,
    TherapeuticArea,
    User,
    utcnow,
)
from app.schemas.doccore_schemas import EditIn
from app.services import billing
from app.services import doccore_documents as svc
from app.services.doccore_common import (
    PROJECT_STATUS_DISPLAY,
    brief,
    file_size_or_none,
    gfn,
    get_or_404,
    has_approved_version,
    is_manager_flag,
    latest_version,
    latest_version_status,
    page_redirect,
    title_case,
    tz_name,
    versions_count,
    versions_default_order,
)

router = APIRouter(prefix="/api/doccore", tags=["doccore"])


def _upload_perm(db: Session, user: User) -> None:
    if not has_module_permission(db, user, "content_lab", "cl_upload", "view"):
        raise page_redirect("You do not have permission to upload documents.", "/content-lab-management/dashboard/")


# ---------------------------------------------------------------- upload (main, with owner)
@router.get("/upload/options")
def upload_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _upload_perm(db, user)
    return {
        "is_admin": bool(user.is_superuser or user.is_staff),
        "page_title": "Upload Document",
        "document_types": svc.choices(db, DocumentType),
        "countries": svc.choices(db, Country),
        "brands": svc.choices(db, Brand),
        "therapeutic_areas": svc.choices(db, TherapeuticArea),
        "therapeutic_areas_other": [t.id for t in db.execute(select(TherapeuticArea).where(
            TherapeuticArea.is_active == 1, TherapeuticArea.name.in_(["Other", "Others"]))).scalars()],
        "rate_card": billing.rate_card_for(db, user),  # services the uploader may request (empty: none)
    }


@router.post("/upload")
def upload_document(
    document_owner: str | None = Form(None),
    document_name: str | None = Form(None),
    document_type: str | None = Form(None),
    country: str | None = Form(None),
    brand: str | None = Form(None),
    therapeutic_area: str | None = Form(None),
    document_file: UploadFile | None = File(None),
    content_html: str | None = Form(None),  # text written in the editor instead of a file
    content_file: UploadFile | None = File(None),  # the same, sent as a file when it holds images (>1 MB)
    services: str | None = Form(None),  # JSON [{service_id, quantity}] from the uploader's rate card
    requirement: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _upload_perm(db, user)
    if content_file is not None and content_file.filename:
        raw = content_file.file.read(25 * 1024 * 1024 + 1)
        if len(raw) > 25 * 1024 * 1024:
            raise HTTPException(400, "The text is too large (over 25 MB). Use smaller images, or upload a file instead.")
        content_html = raw.decode("utf-8", errors="replace")
    return svc.upload_with_owner(db, user, document_owner=document_owner, document_name=document_name,
                                 document_type=document_type, country=country, brand=brand,
                                 therapeutic_area=therapeutic_area, document_file=document_file,
                                 content_html=content_html, services=services, requirement=requirement)


@router.get("/search-users")
def search_users(q: str = "", page: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """search_users_api (Select2 format)."""
    if not (user.is_superuser or user.is_staff):
        raise HTTPException(403, detail={"error": "Permission denied"})
    term = q.strip()
    stmt = select(User).where(User.is_active == 1)
    if term:
        like = f"%{term}%"
        stmt = stmt.where(or_(User.first_name.ilike(like), User.last_name.ilike(like),
                              User.email.ilike(like), User.username.ilike(like)))
    stmt = stmt.order_by(User.first_name, User.last_name)
    page_size = 20
    start = (max(page, 1) - 1) * page_size
    end = start + page_size
    users = db.execute(stmt.limit(page_size).offset(start)).scalars().all()
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    results = []
    for u in users:
        name = gfn(u) or u.username
        results.append({"id": u.id, "text": f"{name} - {u.email}", "name": name, "email": u.email})
    return {"results": results, "pagination": {"more": total > end}}


# ---------------------------------------------------------------- legacy upload
@router.get("/upload-legacy/options")
def upload_legacy_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _upload_perm(db, user)
    from app.models import Project
    return {
        "is_admin": bool(user.is_superuser or user.is_staff),
        "document_types": svc.choices(db, DocumentType),
        "countries": svc.choices(db, Country),
        "brands": svc.choices(db, Brand),
        "therapeutic_areas": [{"value": t.id, "label": t.name, "is_other": t.name in ("Other", "Others")}
                              for t in db.execute(select(TherapeuticArea).where(TherapeuticArea.is_active == 1)
                                                  .order_by(func.lower(TherapeuticArea.name))).scalars()],
        "projects": [{"value": p.id, "label": p.name} for p in db.execute(
            select(Project).where(Project.is_active == 1).order_by(Project.id)).scalars()],
    }


@router.post("/upload-legacy")
def upload_legacy(
    document_owner: str | None = Form(None),  # shown to admins by upload.html but ignored by the view
    document_type: str | None = Form(None),
    document_name: str | None = Form(None),
    country: str | None = Form(None),
    brand: str | None = Form(None),
    therapeutic_area: str | None = Form(None),
    therapeutic_area_other: str | None = Form(None),
    project: str | None = Form(None),
    document_file: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _upload_perm(db, user)
    return svc.upload_legacy(db, user, document_type=document_type, document_name=document_name, country=country,
                             brand=brand, therapeutic_area=therapeutic_area,
                             therapeutic_area_other=therapeutic_area_other, project=project,
                             document_file=document_file)


# ---------------------------------------------------------------- new version
def _version_document(db: Session, user: User, document_id: int) -> Document:
    if user.is_superuser or is_manager_like(user):
        return get_or_404(db, Document, document_id, "Document")
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(404, "No Document matches the given query.")
    return doc


def _version_locks(db: Session, document: Document) -> None:
    detail = f"/content-lab-management/document/{document.id}/"
    if has_approved_version(db, document.id):
        raise page_redirect("Cannot create new version - This document has an approved version. Approved documents are locked.", detail)
    lv = latest_version(db, document.id)
    if lv and lv.stage_status == 1:
        raise page_redirect("Cannot create new version - Document is currently under review.", detail)


@router.get("/documents/{document_id}/new-version")
def new_version_page(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = _version_document(db, user, document_id)
    _version_locks(db, document)
    versions = versions_default_order(db, document.id)
    newest_first = list(reversed(versions))  # first row is the latest version
    return {
        "document": {
            "id": document.id,
            "document_name": document.document_name,
            "document_number": document.document_number,
            "document_type": document.document_type.name if document.document_type else None,
            "brand": document.brand.name if document.brand else None,
            "stage_status": document.stage_status,
            "owner_name": f"{document.user.first_name} {document.user.last_name}",
        },
        "versions_count": len(versions),
        "first_version_number": newest_first[0].version_number if versions else None,
        "new_version_number": f"{document.document_number}-V-{len(versions) + 1}",
        "created_by_name": f"{user.first_name} {user.last_name}",
        "versions": [{
            "id": v.id, "version_number": v.version_number, "file_title_name": v.file_title_name,
            "stage_status": v.stage_status, "created_at": iso(v.created_at),
        } for v in newest_first],
    }


@router.post("/documents/{document_id}/new-version")
def new_version_submit(document_id: int, document_file: UploadFile | None = File(None),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = _version_document(db, user, document_id)
    _version_locks(db, document)
    return svc.create_new_version(db, user, document, document_file)


# ---------------------------------------------------------------- detail
@router.get("/documents/{document_id}")
def document_detail(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = get_or_404(db, Document, document_id, "Document")
    assignment = db.execute(
        select(AssignedReviewer).join(DocumentVersion, AssignedReviewer.document_version_id == DocumentVersion.id)
        .where(AssignedReviewer.user_id == user.id, DocumentVersion.document_id == document.id,
               AssignedReviewer.is_active == 1).order_by(AssignedReviewer.id).limit(1)
    ).scalar_one_or_none()
    is_assigned_reviewer = assignment is not None
    is_collaborator = db.execute(select(DocumentSharing.id).where(
        DocumentSharing.user_id == user.id, DocumentSharing.document_id == document.id,
        DocumentSharing.is_active == 1).limit(1)).first() is not None
    can_view = has_module_permission(db, user, "content_lab", "cl_documents", "view")
    if document.user_id != user.id and not can_view and not is_assigned_reviewer and not is_collaborator:
        raise page_redirect("You do not have permission to view this document", "/content-lab-management/reviewer-dashboard/")

    versions = list(db.execute(select(DocumentVersion).where(DocumentVersion.document_id == document.id)
                               .order_by(DocumentVersion.version_count.desc())).scalars())
    lv = versions[0] if versions else None
    lv_status = lv.stage_status if lv else document.stage_status
    approved = any(v.stage_status == 2 for v in versions)

    is_owner = document.user_id == user.id
    manager = is_manager_flag(user)
    teacher = user.user_type == "teacher"
    # template quirk: `user.user_type in 'student,researcher'` is a substring test
    student_like = (user.user_type or "") in "student,researcher"
    admin = bool(user.is_superuser or user.is_staff)
    can_delete_all_versions = can(db, user, "can_delete_all_document_versions")
    can_delete_versions = can(db, user, "can_delete_document_versions")

    def version_row(v: DocumentVersion) -> dict:
        own_version = v.user_id == user.id
        if (v.file_extension or "").lower() == "pdf" or not (manager or own_version):
            edit = "hidden"
        elif not approved and v.stage_status != 1:
            edit = "link"
        elif v.stage_status == 1 and student_like:
            edit = "locked_review"
        else:
            edit = "locked_approved"
        if can_delete_all_versions:
            delete = "any"
        elif can_delete_versions and own_version:
            delete = "draft" if v.stage_status == 0 else "locked"
        else:
            delete = "hidden"
        return {
            "id": v.id,
            "version_number": v.version_number,
            "file_title_name": v.file_title_name,
            "file_name": v.file_name,
            "file_extension": v.file_extension,
            "stage_status": v.stage_status,
            "created_at": iso(v.created_at),
            "created_by": brief(v.created_by),
            "has_file": bool(v.document_file),
            "shared_count": db.execute(select(func.count(DocumentSharing.id))
                                       .where(DocumentSharing.document_version_id == v.id)).scalar_one(),
            "edit": edit,
            "delete": delete,
        }

    project_status = None
    if document.project is not None:
        project_status = PROJECT_STATUS_DISPLAY.get(document.project.status, document.project.status)

    return {
        "document": {
            "id": document.id,
            "document_name": document.document_name,
            "document_number": document.document_number,
            "stage_status": document.stage_status,
            "document_type": document.document_type.name if document.document_type else None,
            "brand": {"name": document.brand.name, "code_name": document.brand.code_name} if document.brand else None,
            "country": {"name": document.country.name, "code_name": document.country.code_name} if document.country else None,
            "therapeutic_area": document.therapeutic_area.name if document.therapeutic_area else None,
            "course": document.course.name if document.course else None,
            "owner": brief(document.user),
            "created_by": brief(document.created_by),
            "created_by_is_owner": document.created_by_id == document.user_id,
            "modified_by": brief(document.modified_by),
            "created_at": iso(document.created_at),
            "updated_at": iso(document.updated_at),
            "days_since_created": max(0, (utcnow() - document.created_at).days),
            "project_status": project_status,
        },
        "timezone": tz_name(user),
        "latest_version": {"id": lv.id, "version_number": lv.version_number} if lv else None,
        "latest_version_status": lv_status,
        "has_approved_version": approved,
        "is_assigned_reviewer": is_assigned_reviewer,
        "reviewer_assignment_id": assignment.id if assignment else None,
        "versions": [version_row(v) for v in versions],
        "flags": {
            "is_owner": is_owner,
            "show_version_actions": is_owner or manager or teacher,
            "show_reviewer_actions": (is_owner or manager or teacher) and (manager or teacher),
            # `user.has_module_permission.content_lab...` cannot be called from a template -> only staff/superuser
            "show_update_status": admin,
            "show_edit_details": is_owner or manager,
            "edit_details_state": ("link" if (not approved and lv_status != 1)
                                   else "locked_review" if (lv_status == 1 and student_like) else "locked_approved"),
            "show_collaborators_column": bool(user.is_superuser or user.is_staff or manager),
            "can_manage_collaborators": bool(is_owner or user.is_superuser or manager),
            "upload_first_version": is_owner or manager,
        },
    }


@router.get("/versions/{version_id}/file")
def version_file(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Authenticated equivalent of the `{{ version.document_file.url }}` download link."""
    version = get_or_404(db, DocumentVersion, version_id, "DocumentVersion")
    path = media_path(version.document_file)
    if path is None or not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name)


# ---------------------------------------------------------------- edit
def _edit_checks(db: Session, user: User, document: Document) -> None:
    detail = f"/content-lab-management/document/{document.id}/"
    if (document.user_id != user.id and not has_module_permission(db, user, "content_lab", "cl_documents", "edit")
            and not is_manager_like(user)):
        raise page_redirect("You do not have permission to edit this document", detail)
    if has_approved_version(db, document.id):
        raise page_redirect("Cannot edit document - This document has an approved version. Approved documents are locked.", detail)
    if (latest_version_status(db, document) == 1 and user.user_type in ("student", "researcher")
            and document.user_id == user.id):
        raise page_redirect("Cannot edit document - This document is under review.", detail)


@router.get("/documents/{document_id}/edit")
def edit_page(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = get_or_404(db, Document, document_id, "Document")
    _edit_checks(db, user, document)
    return {
        "title": f"Edit Document: {document.document_name}",
        "document": {
            "id": document.id,
            "document_name": document.document_name,
            "document_number": document.document_number,
            "document_type": document.document_type_id,
            "country": document.country_id,
            "country_name": document.country.name if document.country else "",
            "brand": document.brand_id,
            "therapeutic_area": document.therapeutic_area_id,
            "latest_version_status": latest_version_status(db, document),
            "versions_count": versions_count(db, document.id),
            "owner_name": f"{document.user.first_name} {document.user.last_name}",
        },
        "document_types": svc.choices(db, DocumentType, lower=False),
        "countries": svc.choices(db, Country, lower=False),
        "brands": svc.choices(db, Brand, lower=False),
        "therapeutic_areas": svc.choices(db, TherapeuticArea, lower=False),
    }


@router.post("/documents/{document_id}/edit")
def edit_submit(document_id: int, body: EditIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = get_or_404(db, Document, document_id, "Document")
    _edit_checks(db, user, document)
    errors: dict[str, str] = {}
    name = svc.clean_char(body.document_name, True, 500, errors, "document_name")
    dtype = svc.clean_model_choice(db, DocumentType, body.document_type, True, errors, "document_type")
    ctry = svc.clean_model_choice(db, Country, body.country, True, errors, "country")
    brnd = svc.clean_model_choice(db, Brand, body.brand, False, errors, "brand")
    ta = svc.clean_model_choice(db, TherapeuticArea, body.therapeutic_area, False, errors, "therapeutic_area")
    if errors:
        raise svc.form_errors(errors)
    document.document_name = name
    document.document_type_id = dtype.id
    document.country_id = ctry.id
    document.brand_id = brnd.id if brnd else None
    document.therapeutic_area_id = ta.id if ta else None
    document.modified_by_id = user.id
    document.updated_at = utcnow()
    db.commit()
    return {"message": f'Document "{document.document_name}" has been updated successfully.',
            "redirect": f"/content-lab-management/document/{document.id}/"}


# ---------------------------------------------------------------- history
def _history_payload(db: Session, user: User, document: Document) -> dict:
    can_edit_all = can(db, user, "can_edit_all_documents")
    can_edit = can(db, user, "can_edit_documents")
    can_del_all = can(db, user, "can_delete_all_document_versions")
    can_del = can(db, user, "can_delete_document_versions")
    rows = []
    for v in versions_default_order(db, document.id):
        own = v.user_id == user.id
        if can_del_all:
            delete = "any"
        elif can_del and own:
            delete = "draft" if v.stage_status == 0 else "locked"
        else:
            delete = "hidden"
        rows.append({
            "id": v.id,
            "version_number": v.version_number,
            "file_title_name": v.file_title_name,
            "file_name": v.file_name,
            "stage_status": v.stage_status,
            "created_at": iso(v.created_at),
            "created_by": brief(v.created_by),
            "has_file": bool(v.document_file),
            "file_size": file_size_or_none(v.document_file),
            "can_edit": bool(can_edit_all or (can_edit and own)),
            "delete": delete,
        })
    return {
        "mode": "single",
        "page_title": "Document History",
        "timezone": tz_name(user),
        "document": {
            "id": document.id,
            "document_name": document.document_name,
            "document_number": document.document_number,
            "stage_status": document.stage_status,
            "owner_name": f"{document.user.first_name} {document.user.last_name}",
            "brand": document.brand.name if document.brand else None,
            "country": document.country.name if document.country else None,
            "created_at": iso(document.created_at),
        },
        "versions": rows,
    }


@router.get("/history")
def all_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """documents.views.document_history_view without document_id."""
    docs = db.execute(select(Document).where(Document.user_id == user.id, Document.is_active == 1)
                      .order_by(Document.id)).scalars().all()
    out = []
    for d in docs:
        first = db.execute(select(DocumentVersion.id).where(DocumentVersion.document_id == d.id)
                           .order_by(DocumentVersion.id).limit(1)).scalar_one_or_none()
        out.append({
            "id": d.id, "document_number": d.document_number, "document_name": d.document_name,
            "stage_status": d.stage_status, "versions_count": versions_count(db, d.id),
            "created_at": iso(d.created_at), "updated_at": iso(d.updated_at), "first_version_id": first,
        })
    return {"mode": "all", "page_title": "Document History", "documents": out}


@router.get("/history/{document_id}")
def document_history(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """documents.views.document_history_view(document_id) — no permission check in Django."""
    document = get_or_404(db, Document, document_id, "Document")
    return _history_payload(db, user, document)


@router.get("/library-history/{document_id}")
def library_document_history(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """library.views.document_history_view — owner, manager/teacher or is_manager only."""
    document = get_or_404(db, Document, document_id, "Document")
    if document.user_id != user.id and not (user.user_type in ("manager", "teacher") or is_manager_like(user)):
        raise page_redirect("You do not have permission to view this document history", "/content-lab-management/library/")
    return _history_payload(db, user, document)


# ---------------------------------------------------------------- document references (ZIP)
@router.get("/references")
def references(search: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_module_permission(db, user, "content_lab", "cl_library", "view"):
        raise page_redirect("You do not have permission to access document references.", "/content-lab-management/dashboard/")
    stmt = (select(ReferenceZip).join(DocumentVersion, ReferenceZip.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id).where(ReferenceZip.user_id == user.id))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(ReferenceZip.reference_zip_number.ilike(like), ReferenceZip.file_title_name.ilike(like),
                              Document.document_name.ilike(like)))
    rows = []
    for z in db.execute(stmt.order_by(ReferenceZip.id)).scalars():
        size = file_size_or_none(z.zip_file)
        rows.append({
            "id": z.id,
            "reference_zip_number": z.reference_zip_number,
            "file_title_name": z.file_title_name,
            "document_name": z.document_version.document.document_name,
            "document_number": z.document_version.document.document_number,
            "version_number": z.version_number,
            "file_size": size or None,
            "has_file": size is not None,
            "created_at": iso(z.created_at),
        })
    return {"page_title": "Document References", "search_query": search, "reference_zips": rows}


# ---------------------------------------------------------------- simple legacy pages
@router.get("/versions/{version_id}/exists")
def version_exists(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """get_object_or_404 used by complete/ and enable-editing/."""
    v = get_or_404(db, DocumentVersion, version_id, "DocumentVersion")
    return {"id": v.id, "version_number": v.version_number, "file_title_name": v.file_title_name}
