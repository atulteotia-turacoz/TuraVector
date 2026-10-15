"""Business logic for uploading documents and versions (ports of upload_document_with_owner_view,
upload_document_view and create_new_version)."""
import os
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.files import document_upload_dir
from app.models import (
    Brand,
    Country,
    Document,
    DocumentNotification,
    DocumentType,
    DocumentVersion,
    TherapeuticArea,
    User,
    utcnow,
)
from app.services.doccore_common import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    file_extension_error,
    gfn,
    notifiable_teachers_managers,
    save_like_django,
    upload_size,
)

REQUIRED = "This field is required."
INVALID_CHOICE = "Select a valid choice. That choice is not one of the available choices."


def form_errors(errors: dict[str, str]) -> HTTPException:
    return HTTPException(400, detail={"message": "Please correct the errors below.", "errors": errors})


def choices(db: Session, model, lower: bool = True) -> list[dict[str, Any]]:
    order = func.lower(model.name) if lower else model.name
    return [{"value": o.id, "label": o.name} for o in db.execute(
        select(model).where(model.is_active == 1).order_by(order)).scalars()]


def clean_model_choice(db: Session, model, raw: str | None, required: bool, errors: dict, field: str,
                       active_only: bool = True):
    """forms.ModelChoiceField.clean()"""
    if raw is None or str(raw).strip() == "":
        if required:
            errors[field] = REQUIRED
        return None
    try:
        pk = int(str(raw).strip())
    except ValueError:
        errors[field] = INVALID_CHOICE
        return None
    obj = db.get(model, pk)
    if obj is None or (active_only and not obj.is_active):
        errors[field] = INVALID_CHOICE
        return None
    return obj


def clean_char(raw: str | None, required: bool, max_length: int, errors: dict, field: str) -> str:
    value = (raw or "").strip()
    if not value:
        if required:
            errors[field] = REQUIRED
        return ""
    if len(value) > max_length:
        errors[field] = f"Ensure this value has at most {max_length} characters (it has {len(value)})."
    return value


def clean_document_file(upload: UploadFile | None, errors: dict, field: str = "document_file",
                        allowed: list[str] = ALLOWED_DOCUMENT_EXTENSIONS) -> UploadFile | None:
    if upload is None or not upload.filename:
        errors[field] = REQUIRED
        return None
    if upload_size(upload) == 0:
        errors[field] = "The submitted file is empty."
        return None
    msg = file_extension_error(upload.filename, allowed)
    if msg:
        errors[field] = msg
        return None
    return upload


def create_document(db: Session, *, owner: User, uploader: User, document_type_id: int, document_name: str,
                    country_id: int, brand_id: int | None, therapeutic_area_id: int | None,
                    project_id: int | None = None) -> Document:
    """Document.save() fills document_number with DOC-<year>-NEW on insert, the views then set DOC-<year>-<id>."""
    year = utcnow().year
    document = Document(
        user_id=owner.id, document_type_id=document_type_id, document_name=document_name,
        country_id=country_id, brand_id=brand_id, therapeutic_area_id=therapeutic_area_id,
        course_id=None, project_id=project_id, stage_status=0, is_active=1,
        created_by_id=uploader.id, modified_by_id=uploader.id,
        document_number=f"DOC-{year}-NEW",
    )
    db.add(document)
    db.flush()
    document.document_number = f"DOC-{year}-{document.id}"
    db.flush()
    return document


def create_version(db: Session, *, document: Document, upload: UploadFile, version_count: int,
                   version_user: User, creator: User) -> DocumentVersion:
    """DocumentVersion.objects.create(document_file=uploaded_file, ...) — the file is stored before the
    instance has an id, so it lands in documents/None/ exactly like the Django app."""
    name = upload.filename or "file"
    rel = save_like_django(upload, document_upload_dir(None))
    version = DocumentVersion(
        document_id=document.id,
        version_count=version_count,
        version_number=f"{document.document_number}-V-{version_count}",
        file_name=name,
        file_extension=os.path.splitext(name)[1][1:],
        file_title_name=name,
        document_file=rel,
        stage_status=0,
        new_stage_status=None,
        user_id=version_user.id,
        created_by_id=creator.id,
        modified_by_id=creator.id,
    )
    db.add(version)
    db.flush()
    return version


def notify(db: Session, *, receiver_id: int, sender_id: int, document_type: str, document_id: int,
           description: str, sent_for: str) -> None:
    db.add(DocumentNotification(
        receiver_id=receiver_id, sender_id=sender_id, document_type=document_type, document_id=document_id,
        description=description, sent_for=sent_for, is_seen=0,
    ))


def upload_with_owner(db: Session, uploader: User, *, document_owner: str | None, document_name: str | None,
                      document_type: str | None, country: str | None, brand: str | None,
                      therapeutic_area: str | None, document_file: UploadFile | None,
                      content_html: str | None = None, services: str | None = None,
                      requirement: str | None = None) -> dict:
    from app.services import billing
    from app.services.text_document import html_to_docx, plain_text
    errors: dict[str, str] = {}
    name = clean_char(document_name, True, 500, errors, "document_name")
    dtype = clean_model_choice(db, DocumentType, document_type, True, errors, "document_type")
    ctry = clean_model_choice(db, Country, country, True, errors, "country")
    brnd = clean_model_choice(db, Brand, brand, False, errors, "brand")
    ta = clean_model_choice(db, TherapeuticArea, therapeutic_area, False, errors, "therapeutic_area")
    owner_sel = clean_model_choice(db, User, document_owner, False, errors, "document_owner")
    written = content_html is not None and not (document_file is not None and document_file.filename)
    if written:  # text written in the editor instead of a file
        if not plain_text(content_html):
            errors["content_html"] = "Write something, or upload a file instead."
            upload = None
        else:
            upload = html_to_docx(content_html, name or "document")
    else:
        upload = clean_document_file(document_file, errors)
    is_admin = bool(uploader.is_superuser or uploader.is_staff)
    owner = owner_sel if (owner_sel and is_admin) else uploader
    picks: list[dict] = []
    try:
        picks = billing.parse_items(services)
        if picks:
            billing.check_items(db, owner, picks)
    except billing.BillingError as exc:
        errors["services"] = str(exc)
    if errors:
        raise form_errors(errors)

    mails: list = []
    try:
        document = create_document(db, owner=owner, uploader=uploader, document_type_id=dtype.id,
                                   document_name=name, country_id=ctry.id,
                                   brand_id=brnd.id if brnd else None,
                                   therapeutic_area_id=ta.id if ta else None)
        version = create_version(db, document=document, upload=upload, version_count=1, version_user=owner,
                                 creator=uploader)
        if picks:
            _, mails = billing.create_request(db, owner, picks, document=document, version_id=version.id,
                                              requirement=requirement or "")
            billing.notify_in_app(db, mails, owner)

        try:
            receivers = {u.id: u for u in notifiable_teachers_managers(db, exclude_id=uploader.id)}
            if owner.id != uploader.id and owner.is_active:
                receivers[owner.id] = owner
            desc = f'Document "{document.document_name}" uploaded by {gfn(uploader)}'
            if owner.id != uploader.id:
                desc += f" for {gfn(owner)}"
            for rid in receivers:
                notify(db, receiver_id=rid, sender_id=uploader.id, document_type="document_upload",
                       document_id=document.id, description=desc, sent_for="document_upload_notification")
            db.flush()
        except Exception:  # noqa: BLE001 — Django only printed notification errors
            pass
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except billing.BillingError as exc:
        db.rollback()
        raise form_errors({"services": str(exc)})
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error uploading document: {exc}")
    billing.send(db, mails, owner)

    if owner.id != uploader.id:
        msg = f"Document uploaded successfully for {gfn(owner)} with number: {document.document_number}"
    else:
        msg = f"Document uploaded successfully with number: {document.document_number}"
    if picks:
        msg += f" Your request for {len(picks)} service{'s' if len(picks) != 1 else ''} has been sent to Turacoz."
    return {"message": msg, "redirect": f"/content-lab-management/document/{document.id}/", "document_id": document.id}


def upload_legacy(db: Session, user: User, *, document_type: str | None, document_name: str | None,
                  country: str | None, brand: str | None, therapeutic_area: str | None,
                  therapeutic_area_other: str | None, project: str | None,
                  document_file: UploadFile | None) -> dict:
    """documents.views.upload_document_view (POST)."""
    has_file = document_file is not None and bool(document_file.filename)
    if not all([document_type, document_name, country, therapeutic_area, has_file]):
        # redirect('upload_document') resolves to the owner-upload page
        raise HTTPException(400, detail={"message": "All required fields must be filled",
                                         "redirect": "/content-lab-management/upload/"})
    try:
        ta = db.get(TherapeuticArea, int(therapeutic_area))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"Error uploading document: Field 'id' expected a number but got {therapeutic_area!r}.") from exc
    if ta is None:
        raise HTTPException(400, detail={"message": "Invalid therapeutic area selected.", "redirect": "/content-lab-management/upload/"})
    if ta.name.lower() in ("other", "others") and not therapeutic_area_other:
        raise HTTPException(400, detail={"message": "Please specify the other therapeutic area.", "redirect": "/content-lab-management/upload/"})

    try:
        def as_int(v):
            return int(v) if v else None

        dtype_id, country_id = int(document_type), int(country)
        brand_id, project_id = as_int(brand), as_int(project)
        # Foreign keys must exist (Django raised IntegrityError from MySQL)
        for model, pk, label in ((DocumentType, dtype_id, "document_type_id"), (Country, country_id, "country_id")):
            if db.get(model, pk) is None:
                raise ValueError(f"Cannot add or update a child row: a foreign key constraint fails ({label})")
        if brand_id is not None and db.get(Brand, brand_id) is None:
            raise ValueError("Cannot add or update a child row: a foreign key constraint fails (brand_id)")

        document = create_document(db, owner=user, uploader=user, document_type_id=dtype_id,
                                   document_name=document_name, country_id=country_id, brand_id=brand_id,
                                   therapeutic_area_id=ta.id, project_id=project_id)
        create_version(db, document=document, upload=document_file, version_count=1, version_user=user, creator=user)
        try:
            for u in notifiable_teachers_managers(db, exclude_id=user.id):
                notify(db, receiver_id=u.id, sender_id=user.id, document_type="document_upload",
                       document_id=document.id,
                       description=f'New document "{document.document_name}" has been uploaded by {gfn(user)}',
                       sent_for="document_upload_notification")
            db.flush()
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error uploading document: {exc}")
    return {"message": f"Document uploaded successfully with number: {document.document_number}",
            "redirect": "/content-lab-management/dashboard/", "document_id": document.id}


def create_new_version(db: Session, user: User, document: Document, document_file: UploadFile | None) -> dict:
    """documents.views.create_new_version (POST part, after the lock checks)."""
    if document_file is None or not document_file.filename:
        raise HTTPException(400, detail={"message": "Please select a file",
                                         "redirect": f"/content-lab-management/document/{document.id}/new-version/"})
    try:
        latest = db.execute(select(DocumentVersion).where(DocumentVersion.document_id == document.id)
                            .order_by(DocumentVersion.version_count.desc()).limit(1)).scalar_one_or_none()
        new_count = (latest.version_count + 1) if latest else 1
        version = create_version(db, document=document, upload=document_file, version_count=new_count,
                                 version_user=user, creator=user)
        try:
            for u in notifiable_teachers_managers(db, exclude_id=user.id):
                notify(db, receiver_id=u.id, sender_id=user.id, document_type="version_updated",
                       document_id=document.id,
                       description=(f"New version ({version.version_number}) of document "
                                    f'"{document.document_name}" has been created by {gfn(user)}'),
                       sent_for="version_update_notification")
            db.flush()
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error creating version: {exc}")
    return {"message": f"New version created: {version.version_number}",
            "redirect": f"/content-lab-management/document/{document.id}/", "version_id": version.id}
