"""Business logic for the library module — ports of library/views.py:

library_view, reference_library_view, reference_detail_view, delete_reference_view,
upload_reference_view, upload_reference_zip_view, reference_zip_detail_view,
delete_reference_zip_view, assign_reviewer_view, manage_reviewers_view,
toggle_reviewer_status, complete_review.
"""
import datetime
import os
from typing import Any

import pytz
from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import is_manager_like
from app.config import settings
from app.core import email as core_email
from app.core.files import media_path, reference_upload_dir, reference_zip_upload_dir, save_upload
from app.core.utils import iso
from app.models import (
    AssignedReviewer, Brand, Country, Document, DocumentHistory, DocumentNotification, DocumentType,
    DocumentVersion, ReferenceDocument, ReferenceZip, TherapeuticArea, User, utcnow,
)

# ReferenceDocument choices
REFERENCE_TYPES = [
    ("primary", "Primary Reference"),
    ("secondary", "Secondary Reference"),
    ("supporting", "Supporting Document"),
]
REFERENCE_SUBTYPES = [
    ("journal", "Journal Article"),
    ("book", "Book"),
    ("website", "Website"),
    ("report", "Report"),
    ("guideline", "Guideline"),
]
TYPE_LABELS = dict(REFERENCE_TYPES)
SUBTYPE_LABELS = dict(REFERENCE_SUBTYPES)
# Document.STAGE_CHOICES (get_stage_status_display)
STAGE_LABELS = {0: "Draft", 1: "Under Review", 2: "Approved", 3: "Draft Under Revision"}

FILE_FIELD_MAX_LENGTH = 100  # Django FileField default max_length (column is VARCHAR(100))


# --------------------------------------------------------------------------- helpers
def get_full_name(user: User | None) -> str:
    """Django AbstractUser.get_full_name — may be empty (templates then fall back to username)."""
    if user is None:
        return ""
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


def full_name_or_username(user: User | None) -> str:
    """`{{ u.get_full_name|default:u.username }}`"""
    if user is None:
        return ""
    return get_full_name(user) or user.username


def is_manager_or_teacher(user: User) -> bool:
    """`user.user_type in ['manager', 'teacher'] or user.is_manager` — used by most library views."""
    return user.user_type in ("manager", "teacher") or is_manager_like(user)


def is_superuser_or_manager(user: User) -> bool:
    """`is_superuser or user_type == 'manager' or is_manager` — manage/toggle reviewer checks."""
    return bool(user.is_superuser) or is_manager_like(user)


def django_title(value: str | None) -> str:
    """Django `|title` filter (close enough for single-word user types)."""
    return (value or "").title()


def file_size(relative: str | None) -> int | None:
    """Size on disk, or None when the file is missing (Django would raise; we degrade gracefully)."""
    try:
        path = media_path(relative)
    except Exception:  # noqa: BLE001
        return None
    if path and path.is_file():
        return path.stat().st_size
    return None


def file_exists(relative: str | None) -> bool:
    try:
        path = media_path(relative)
    except Exception:  # noqa: BLE001
        return False
    return bool(path and path.is_file())


def _fit_filename(directory: str, filename: str) -> str:
    """Django's Storage.get_available_name truncates the file root so the stored path fits max_length."""
    from app.core.files import get_valid_filename

    name = get_valid_filename(os.path.basename(filename))
    full = f"{directory.strip('/')}/{name}"
    excess = len(full) - FILE_FIELD_MAX_LENGTH
    if excess > 0:
        root, ext = os.path.splitext(name)
        # leave room for Django's `_<7 chars>` suffix that may be added on collision
        cut = excess + 8
        if cut < len(root):
            name = root[:-cut] + ext
    return name


def latest_version(db: Session, document_id: int) -> DocumentVersion | None:
    """document.versions.order_by('-version_count').first()"""
    return db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_count.desc(), DocumentVersion.id.asc()).limit(1)
    ).scalar_one_or_none()


def has_approved_version(db: Session, document_id: int) -> bool:
    return db.execute(
        select(DocumentVersion.id).where(DocumentVersion.document_id == document_id,
                                         DocumentVersion.stage_status == 2).limit(1)
    ).first() is not None


def _local_now_date() -> datetime.date:
    return datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)).date()


def _naive_local_to_utc(dt: datetime.datetime) -> datetime.datetime:
    """Django (USE_TZ=True, no active tz) treats a naive datetime as TIME_ZONE and stores UTC."""
    aware = pytz.timezone(settings.TIME_ZONE).localize(dt)
    return aware.astimezone(pytz.UTC).replace(tzinfo=None)


def _named(obj, *extra: str) -> dict | None:
    if obj is None:
        return None
    out = {"id": obj.id, "name": obj.name}
    for f in extra:
        out[f] = getattr(obj, f, None)
    return out


# --------------------------------------------------------------------------- library_view
def library_documents(db: Session, user: User, search: str, document_type: str, brand: str,
                      country: str, status: str) -> dict[str, Any]:
    stmt = select(Document).where(Document.is_active == 1)
    if not is_manager_or_teacher(user):
        stmt = stmt.where(Document.user_id == user.id)

    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Document.document_name.ilike(like), Document.document_number.ilike(like)))
    if document_type:
        stmt = stmt.where(Document.document_type_id.in_(select(DocumentType.id).where(DocumentType.name == document_type)))
    if brand:
        stmt = stmt.where(Document.brand_id.in_(select(Brand.id).where(Brand.name == brand)))
    if country:
        stmt = stmt.where(Document.country_id.in_(select(Country.id).where(Country.name == country)))
    if status:
        stmt = stmt.where(Document.stage_status == int(status))

    stmt = stmt.order_by(Document.created_at.desc()).options(
        selectinload(Document.user), selectinload(Document.created_by), selectinload(Document.modified_by),
        selectinload(Document.document_type), selectinload(Document.brand), selectinload(Document.country),
        selectinload(Document.therapeutic_area),
    )
    documents = db.execute(stmt).scalars().all()

    # versions.count and versions.first (no Meta.ordering on DocumentVersion → first() orders by pk)
    ids = [d.id for d in documents]
    version_info: dict[int, tuple[int, int]] = {}
    first_numbers: dict[int, str] = {}
    if ids:
        for doc_id, cnt, min_id in db.execute(
            # newest version (highest id) — Django showed the oldest here as "Latest"
            select(DocumentVersion.document_id, func.count(DocumentVersion.id), func.max(DocumentVersion.id))
            .where(DocumentVersion.document_id.in_(ids)).group_by(DocumentVersion.document_id)
        ).all():
            version_info[doc_id] = (cnt, min_id)
        min_ids = [v[1] for v in version_info.values()]
        if min_ids:
            for vid, vnum in db.execute(
                select(DocumentVersion.id, DocumentVersion.version_number).where(DocumentVersion.id.in_(min_ids))
            ).all():
                first_numbers[vid] = vnum

    rows = []
    stats = {"total_documents": 0, "draft_documents": 0, "review_documents": 0,
             "approved_documents": 0, "revised_documents": 0}
    for d in documents:
        cnt, min_id = version_info.get(d.id, (0, None))
        stats["total_documents"] += 1
        key = {0: "draft_documents", 1: "review_documents", 2: "approved_documents", 3: "revised_documents"}.get(d.stage_status)
        if key:
            stats[key] += 1
        rows.append({
            "id": d.id,
            "document_number": d.document_number,
            "document_name": d.document_name,
            "created_by_is_owner": d.created_by_id == d.user_id,
            "created_by_name": f"{d.created_by.first_name or ''} {d.created_by.last_name or ''}".strip() if d.created_by else "",
            "document_type": d.document_type.name if d.document_type else None,
            "brand": _named(d.brand, "code_name"),
            "country": _named(d.country, "code_name"),
            "therapeutic_area": d.therapeutic_area.name if d.therapeutic_area else None,
            "stage_status": d.stage_status,
            "version_count": cnt,
            "first_version_number": first_numbers.get(min_id) if min_id else None,
            "owner_id": d.user_id,
            "owner_name": f"{d.user.first_name or ''} {d.user.last_name or ''}".strip() if d.user else "",
            "owner_user_type": django_title(d.user.user_type) if d.user else "",
            "created_at": iso(d.created_at),
            "updated_at": iso(d.updated_at),
            "modified_by_first_name": d.modified_by.first_name if d.modified_by else None,
        })

    def active(model):
        return [{"id": o.id, "name": o.name} for o in db.execute(
            select(model).where(model.is_active == 1).order_by(model.id)).scalars()]

    return {
        "documents": rows,
        "brands": active(Brand),
        "countries": active(Country),
        "document_types": active(DocumentType),
        "therapeutic_areas": active(TherapeuticArea),
        "stats": stats,
    }


# --------------------------------------------------------------------------- references
def serialize_reference(r: ReferenceDocument, detail: bool = False) -> dict[str, Any]:
    out = {
        "id": r.id,
        "reference_number": r.reference_number,
        "document_name": r.document_name,
        "type": r.type,
        "type_display": TYPE_LABELS.get(r.type, r.type),
        "subtype": r.subtype,
        "subtype_display": SUBTYPE_LABELS.get(r.subtype, r.subtype),
        "therapeutic_area": r.therapeutic_area.name if r.therapeutic_area else None,
        "ref_year": r.ref_year,
        "has_file": bool(r.reference_file),
        "user_id": r.user_id,
    }
    if detail:
        out.update({
            "country": r.country.name if r.country else None,
            "ref_number": r.ref_number,
            "file_name": r.file_name,
            "file_extension": r.file_extension,
            "file_title_name": r.file_title_name,
            "created_by": full_name_or_username(r.created_by),
            "created_at": iso(r.created_at),
            "updated_at": iso(r.updated_at),
            "owner_username": r.user.username if r.user else None,
        })
    return out


def reference_list(db: Session, user: User, search: str, type_filter: str) -> list[dict]:
    stmt = select(ReferenceDocument).where(ReferenceDocument.is_active == 1)
    if not is_manager_or_teacher(user):
        stmt = stmt.where(ReferenceDocument.user_id == user.id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(ReferenceDocument.document_name.ilike(like),
                              ReferenceDocument.reference_number.ilike(like)))
    if type_filter:
        stmt = stmt.where(ReferenceDocument.type == type_filter)
    stmt = stmt.order_by(ReferenceDocument.created_at.desc()).options(selectinload(ReferenceDocument.therapeutic_area))
    return [serialize_reference(r) for r in db.execute(stmt).scalars()]


def create_reference(db: Session, user: User, *, reference_type: str, reference_subtype: str, document_name: str,
                     country_id: str, therapeutic_area_id: str | None, ref_number: str | None,
                     ref_year: str | None, upload: UploadFile) -> ReferenceDocument:
    """ReferenceDocument.objects.create(...) followed by the REF-<year>-<id> renumbering."""
    original_name = upload.filename or ""
    file_extension = os.path.splitext(original_name)[1][1:]
    year_value = int(ref_year) if ref_year else None  # same ValueError text as Django on bad input
    # upload_to uses instance.id, which is None before the first save → references/None/<name>
    directory = reference_upload_dir(None)
    stored = save_upload(upload, directory, _fit_filename(directory, original_name))
    year = utcnow().year
    reference = ReferenceDocument(
        reference_number=f"REF-{year}-NEW",  # ReferenceDocument.save() before the id exists
        type=reference_type,
        subtype=reference_subtype,
        document_name=document_name,
        country_id=int(country_id),
        therapeutic_area_id=int(therapeutic_area_id) if therapeutic_area_id else None,
        file_name=original_name,
        file_extension=file_extension,
        file_title_name=original_name,
        reference_file=stored,
        ref_number=ref_number,
        ref_year=year_value,
        user_id=user.id,
        created_by_id=user.id,
        modified_by_id=user.id,
        is_active=1,
    )
    db.add(reference)
    db.flush()
    reference.reference_number = f"REF-{year}-{reference.id}"
    db.commit()
    return reference


# --------------------------------------------------------------------------- reference ZIPs
def zip_upload_versions(db: Session, user: User) -> list[dict]:
    docs = select(Document.id).where(Document.is_active == 1)
    if not user.is_superuser:
        docs = docs.where(Document.user_id == user.id)
    versions = db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id.in_(docs))
        .order_by(DocumentVersion.created_at.desc()).options(selectinload(DocumentVersion.document))
    ).scalars().all()
    return [{
        "id": v.id,
        "version_number": v.version_number,
        "document_name": v.document.document_name,
        "document_number": v.document.document_number,
    } for v in versions]


def create_reference_zip(db: Session, user: User, version: DocumentVersion, upload: UploadFile) -> ReferenceZip:
    original_name = upload.filename or ""
    file_extension = os.path.splitext(original_name)[1][1:]
    directory = reference_zip_upload_dir(user.id)
    stored = save_upload(upload, directory, _fit_filename(directory, original_name))
    year = utcnow().year
    ref_zip = ReferenceZip(
        reference_zip_number=f"REF-ZIP-{year}-NEW",
        user_id=user.id,
        document_version_id=version.id,
        version_number=version.version_number,
        file_name=original_name,
        file_extension=file_extension,
        file_title_name=original_name,
        zip_file=stored,
        created_by_id=user.id,
        modified_by_id=user.id,
    )
    db.add(ref_zip)
    db.flush()
    ref_zip.reference_zip_number = f"REF-ZIP-{year}-{ref_zip.id}"
    db.commit()
    return ref_zip


def serialize_zip_detail(z: ReferenceZip) -> dict[str, Any]:
    version = z.document_version
    document = version.document
    return {
        "id": z.id,
        "reference_zip_number": z.reference_zip_number,
        "file_title_name": z.file_title_name,
        "file_extension": z.file_extension,
        "has_file": bool(z.zip_file),
        "file_size": file_size(z.zip_file) if z.zip_file else None,
        "created_at": iso(z.created_at),
        "updated_at": iso(z.updated_at),
        "created_by": full_name_or_username(z.created_by),
        "modified_by": full_name_or_username(z.modified_by),
        "owner": full_name_or_username(z.user),
        "document": {
            "id": document.id,
            "document_name": document.document_name,
            "document_number": document.document_number,
            "document_type": document.document_type.name if document.document_type else None,
            "stage_status": document.stage_status,
            "stage_status_display": STAGE_LABELS.get(document.stage_status, str(document.stage_status)),
        },
        "version": {"id": version.id, "version_number": version.version_number},
    }


# --------------------------------------------------------------------------- reviewers
def reviewer_candidates(db: Session) -> list[dict]:
    """User.objects.filter(user_type__in=['reviewer', 'teacher'], is_active=True)"""
    users = db.execute(
        select(User).where(User.user_type.in_(["reviewer", "teacher"]), User.is_active == 1).order_by(User.id)
    ).scalars().all()
    return [{
        "id": u.id,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "email": u.email,
        "user_type_title": django_title(u.user_type),
    } for u in users]


def assign_reviewer(db: Session, assigner: User, version: DocumentVersion, reviewer: User,
                    review_date_raw: str, remarks: str) -> AssignedReviewer:
    review_date = datetime.datetime.strptime(review_date_raw, "%Y-%m-%d")
    document = version.document
    assignment = AssignedReviewer(
        user_id=reviewer.id,
        document_version_id=version.id,
        review_date=_naive_local_to_utc(review_date),
        remarks=remarks,
        is_completed=0,
        is_active=1,
        created_by_id=assigner.id,
        modified_by_id=assigner.id,
    )
    db.add(assignment)
    db.commit()

    # Notifications (failures never fail the assignment)
    try:
        db.add(DocumentNotification(
            receiver_id=reviewer.id,
            sender_id=assigner.id,
            document_type="review_request",
            document_id=document.id,
            description=(f'You have been assigned to review document "{document.document_name}" '
                         f'(Version: {version.version_number}) by {get_full_name(assigner)}'),
            sent_for="reviewer_assignment",
            is_seen=0,
        ))
        if document.user_id != assigner.id and document.user_id != reviewer.id:
            db.add(DocumentNotification(
                receiver_id=document.user_id,
                sender_id=assigner.id,
                document_type="review_request",
                document_id=document.id,
                description=(f'Your document "{document.document_name}" has been assigned to '
                             f'{get_full_name(reviewer)} for review by {get_full_name(assigner)}'),
                sent_for="reviewer_assignment_owner",
                is_seen=0,
            ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    subject = f"Document Review Assignment: {version.version_number}"
    message = f'''Dear {reviewer.first_name},

You have been assigned to review the following document:

Document: {document.document_name}
Version: {version.version_number}
Review Date: {review_date_raw}

Remarks: {remarks}

Please log in to the system to review the document.

Best regards,
TuraVector Team'''
    core_email.send_email_with_logging(
        db, subject, message, [reviewer.email], "review_assignment",
        from_email="noreply@turadome.com", sender_user=assigner, recipient_user=reviewer,
        document=document, document_version=version,
    )
    return assignment


def manage_reviewers_data(db: Session, document: Document) -> dict[str, Any]:
    assignments = db.execute(
        select(AssignedReviewer).join(DocumentVersion, AssignedReviewer.document_version_id == DocumentVersion.id)
        .where(DocumentVersion.document_id == document.id)
        .order_by(AssignedReviewer.created_at.desc())
        .options(selectinload(AssignedReviewer.user), selectinload(AssignedReviewer.document_version),
                 selectinload(AssignedReviewer.created_by))
    ).scalars().all()
    rows = []
    for a in assignments:
        u = a.user
        rows.append({
            "id": a.id,
            "reviewer_name": full_name_or_username(u),
            "reviewer_email": u.email,
            "reviewer_initials": f"{(u.first_name or '')[:1]}{(u.last_name or '')[:1]}",
            "version_id": a.document_version_id,
            "version_number": a.document_version.version_number,
            "review_date": iso(a.review_date),
            "is_completed": bool(a.is_completed),
            "is_active": bool(a.is_active),
            "assigned_by": full_name_or_username(a.created_by),
            "created_at": iso(a.created_at),
        })
    return {
        "document": {
            "id": document.id,
            "document_name": document.document_name,
            "document_number": document.document_number,
            "owner": full_name_or_username(document.user),
        },
        "has_approved_version": has_approved_version(db, document.id),
        "assignments": rows,
    }


def toggle_assignment(db: Session, actor: User, assignment: AssignedReviewer) -> AssignedReviewer:
    assignment.is_active = 0 if assignment.is_active else 1
    assignment.modified_by_id = actor.id
    db.commit()
    if not assignment.is_active:
        version = assignment.document_version
        reviewer = assignment.user
        subject = f"Review Assignment Deactivated: {version.version_number}"
        message = f'''Dear {reviewer.first_name},

Your review assignment for the following document has been deactivated:

Document: {version.document.document_name}
Version: {version.version_number}

This document is no longer visible in your reviewer dashboard.

If you have any questions, please contact your manager.

Best regards,
TuraVector Team'''
        core_email.send_email_with_logging(
            db, subject, message, [reviewer.email], "review_assignment",
            from_email="noreply@turadome.com", sender_user=actor, recipient_user=reviewer,
            document=version.document, document_version=version,
        )
    return assignment


def complete_review(db: Session, reviewer: User, assignment: AssignedReviewer, remarks: str,
                    approval_status: str | None) -> None:
    """Port of complete_review. Raises on the same conditions Django did (after committing the same rows)."""
    assignment.remarks = remarks
    assignment.is_completed = 1
    assignment.completed_at = utcnow()
    assignment.modified_by_id = reviewer.id
    db.commit()

    version = assignment.document_version
    if approval_status == "approved":
        version.stage_status = 2
        version.new_stage_status = 2
    elif approval_status == "rejected":
        version.stage_status = 3
        version.new_stage_status = 3
    version.modified_by_id = reviewer.id
    db.commit()

    action_type = "approved" if approval_status == "approved" else "rejected"
    db.add(DocumentHistory(
        document_id=version.document_id,
        document_version_id=version.id,
        action_type=action_type,
        action_description=(f"Document {action_type} by {reviewer.first_name} {reviewer.last_name}. "
                            f"Remarks: {remarks}"),
        user_id=reviewer.id,
    ))
    db.commit()

    owner = version.document.user
    subject = f"Document Review Completed: {version.version_number}"
    message = f'''
        Dear {owner.first_name},

        Your document review has been completed:

        Document: {version.document.document_name}
        Version: {version.version_number}
        Status: {approval_status.title()}
        Reviewer: {reviewer.first_name} {reviewer.last_name}

        Remarks: {remarks}

        Please log in to the system to view the details.

        Best regards,
        TuraVector Team
        '''
    # django.core.mail.send_mail (no EmailLog row; raises on failure)
    core_email.deliver(db, subject, message, "noreply@turadome.com", owner.email)
