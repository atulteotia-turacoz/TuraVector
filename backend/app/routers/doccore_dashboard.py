"""Content Review dashboard, reviewer dashboard, all reviews and reviewer assignments overview.

Ports of documents.views: content_lab_dashboard_view + home_view, reviewer_dashboard_view,
all_reviews_view, reviewer_assignments_overview.
"""
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import can, has_module_permission, is_manager_like
from app.core.utils import iso
from app.database import get_db
from app.models import AssignedReviewer, Document, DocumentSharing, DocumentType, DocumentVersion, User, utcnow
from app.services.doccore_common import (
    STAGE_CHOICES,
    brief,
    gfn,
    has_approved_version,
    latest_version,
    page_redirect,
    versions_count,
)

router = APIRouter(prefix="/api/doccore", tags=["doccore"])


def _django_page(page_param: str | None, num_pages: int) -> int:
    """Paginator.get_page(): non-integers -> 1, out of range -> last page."""
    try:
        n = int(page_param) if page_param not in (None, "") else 1
    except (TypeError, ValueError):
        return 1
    if n < 1 or n > num_pages:
        return num_pages  # EmptyPage -> last page
    return n


def _doc_row(d: Document) -> dict:
    return {
        "id": d.id,
        "document_number": d.document_number,
        "document_name": d.document_name,
        "stage_status": d.stage_status,
        "created_at": iso(d.created_at),
    }


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(page: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """content_lab_dashboard_view -> home_view (also serves home/, list/, user-home/, teacher-home/, manager-dashboard/)."""
    if not can(db, user, "can_access_content_lab_dashboard"):
        raise page_redirect("You do not have permission to access the Content Review dashboard.",
                            "/home")

    can_dashboard = can(db, user, "can_access_dashboard")
    can_manager = can(db, user, "can_access_manager_dashboard")
    can_review_view = has_module_permission(db, user, "content_lab", "cl_review", "view")
    if not can_dashboard and not can_manager and not can_review_view:
        raise page_redirect("You do not have permission to access the dashboard.", "/profile/")

    if can_manager:
        # home_view builds the manager context and then redirects to library:manager_dashboard
        raise page_redirect(None, "/content-lab-management/dashboard/", status=403)

    own_ids = set(db.execute(select(Document.id).where(Document.user_id == user.id, Document.is_active == 1)).scalars())
    shared_ids = set(db.execute(
        select(DocumentSharing.document_id).where(
            DocumentSharing.user_id == user.id, DocumentSharing.is_active == 1,
            DocumentSharing.document_version_id.is_not(None)).distinct()
    ).scalars())
    accessible = [i for i in own_ids | shared_ids if i is not None]

    def count(status: int | None = None) -> int:
        if not accessible:
            return 0
        stmt = select(func.count(Document.id)).where(Document.id.in_(accessible), Document.is_active == 1)
        if status is not None:
            stmt = stmt.where(Document.stage_status == status)
        return db.execute(stmt).scalar_one()

    stats = {
        "total_documents": count(),
        "draft_documents": count(0),
        "review_documents": count(1),
        "approved_documents": count(2),
        "revision_documents": count(3),
        "document_types_count": db.execute(select(func.count(DocumentType.id)).where(DocumentType.is_active == 1)).scalar_one(),
    }

    # own_documents | shared_documents, distinct, newest first, 10 per page
    cond = Document.user_id == user.id
    if shared_ids - {None}:
        cond = or_(cond, Document.id.in_(list(shared_ids - {None})))
    base = select(Document).where(cond, Document.is_active == 1)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    num_pages = max(1, math.ceil(total / 10))
    current = _django_page(page, num_pages)
    docs = db.execute(base.order_by(Document.created_at.desc()).limit(10).offset((current - 1) * 10)).scalars().all()

    return {
        "template": "teacher" if can_review_view else "user",
        **stats,
        "recent_documents": [_doc_row(d) for d in docs],
        "page": current,
        "num_pages": num_pages,
    }


# ---------------------------------------------------------------- reviewer dashboard
def _today():
    return utcnow().date()


def _is_overdue(a: AssignedReviewer) -> bool:
    return bool(a.review_date and a.review_date.date() < _today() and not a.is_completed)


def _review_status(a: AssignedReviewer) -> str:
    if a.is_completed:
        return "completed"
    if _is_overdue(a):
        return "overdue"
    return "in_review" if (a.remarks and a.remarks.strip()) else "pending"


def _filter_status(rows: list[AssignedReviewer], status_filter: str) -> list[AssignedReviewer]:
    if status_filter == "pending":
        return [a for a in rows if not a.is_completed and not a.remarks]
    if status_filter == "in_review":
        return [a for a in rows if not a.is_completed and a.remarks is not None and a.remarks != ""]
    if status_filter == "completed":
        return [a for a in rows if a.is_completed]
    if status_filter == "overdue":
        return [a for a in rows if not a.is_completed and a.review_date and a.review_date.date() < _today()]
    return rows


def _assignment_row(a: AssignedReviewer) -> dict:
    v = a.document_version
    d = v.document
    return {
        "id": a.id,
        "status": _review_status(a),
        "is_overdue": _is_overdue(a),
        "is_completed": bool(a.is_completed),
        "is_active": bool(a.is_active),
        "has_remarks": bool(a.remarks),
        "review_date": iso(a.review_date),
        "started_at": iso(a.started_at),
        "completed_at": iso(a.completed_at),
        "created_at": iso(a.created_at),
        "reviewer": brief(a.user),
        "created_by": brief(a.created_by),
        "version": {"id": v.id, "version_number": v.version_number},
        "document": {
            "id": d.id,
            "document_name": d.document_name,
            "document_number": d.document_number,
            "stage_status": d.stage_status,
            "document_type": d.document_type.name if d.document_type else None,
            "owner": brief(d.user),
        },
    }


def _assignments_query(user_scope: int | None, active_only: bool):
    stmt = (select(AssignedReviewer)
            .join(DocumentVersion, AssignedReviewer.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Document.is_active == 1))
    if active_only:
        stmt = stmt.where(AssignedReviewer.is_active == 1)
    if user_scope is not None:
        stmt = stmt.where(AssignedReviewer.user_id == user_scope)
    return stmt


@router.get("/reviewer-dashboard")
def reviewer_dashboard(status: str = "all", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can(db, user, "can_access_reviewer_dashboard"):
        raise page_redirect("You do not have permission to access the reviewer dashboard.", "/content-lab-management/dashboard/")

    is_admin_view = bool(user.is_superuser or user.user_type == "admin" or user.is_staff)
    stmt = _assignments_query(None if is_admin_view else user.id, active_only=True).order_by(AssignedReviewer.created_at.desc())
    all_rows = list(db.execute(stmt).scalars())

    pending = len(_filter_status(all_rows, "pending"))
    completed = len(_filter_status(all_rows, "completed"))
    in_review = len(_filter_status(all_rows, "in_review"))
    overdue = len(_filter_status(all_rows, "overdue"))

    if status in ("pending", "in_review", "completed", "overdue"):
        rows = _filter_status(all_rows, status)
    else:
        rows = all_rows

    return {
        "is_admin_view": is_admin_view,
        "user_full_name": gfn(user),
        "current_filter": status,
        "total_assignments": len(all_rows),
        "pending_reviews": pending,
        "completed_reviews": completed,
        "overdue_reviews": overdue,
        "in_review_count": in_review,
        "assigned_documents": [_assignment_row(a) for a in rows],
    }


@router.get("/all-reviews")
def all_reviews(status: str = "all", q: str = "", page: str | None = None,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can(db, user, "can_access_reviewer_dashboard") and not user.is_superuser:
        raise page_redirect("You do not have permission to access reviews.", "/content-lab-management/dashboard/")

    if user.is_superuser:
        stmt = _assignments_query(None, active_only=False)
    else:
        stmt = _assignments_query(user.id, active_only=True)

    if q:
        like = f"%{q}%"
        stmt = stmt.join(User, AssignedReviewer.user_id == User.id).where(or_(
            Document.document_name.ilike(like), Document.document_number.ilike(like),
            User.username.ilike(like), User.first_name.ilike(like), User.last_name.ilike(like),
        ))
    rows = list(db.execute(stmt.order_by(AssignedReviewer.created_at.desc())).scalars())
    if status in ("pending", "in_review", "completed", "overdue"):
        rows = _filter_status(rows, status)

    per_page = 20
    total = len(rows)
    num_pages = max(1, math.ceil(total / per_page))
    current = _django_page(page, num_pages)
    start = (current - 1) * per_page
    items = rows[start:start + per_page]
    return {
        "reviews": [_assignment_row(a) for a in items],
        "total_reviews": total,
        "status_filter": status,
        "search_query": q,
        "is_admin": bool(user.is_superuser),
        "page": current,
        "num_pages": num_pages,
        "start_index": start + 1 if total else 0,
        "end_index": start + len(items),
    }


# ---------------------------------------------------------------- reviewer assignments overview
@router.get("/reviewer-assignments")
def reviewer_assignments_overview(filter_status: str = "all", document_status: str = "all", search: str = "",
                                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (user.is_superuser or user.is_staff or user.user_type in ("manager", "teacher") or is_manager_like(user)
            or has_module_permission(db, user, "content_lab", "cl_documents", "view")):
        raise page_redirect("You do not have permission to view reviewer assignments", "/content-lab-management/dashboard/")

    stmt = select(Document).join(User, Document.user_id == User.id).where(Document.is_active == 1)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Document.document_name.ilike(like), Document.document_number.ilike(like),
                              User.first_name.ilike(like), User.last_name.ilike(like)))
    if document_status != "all":
        try:
            stmt = stmt.where(Document.stage_status == int(document_status))
        except ValueError:
            raise HTTPException(400, f"invalid literal for int() with base 10: '{document_status}'")

    document_data = []
    for doc in db.execute(stmt.order_by(Document.id)).scalars():
        lv = latest_version(db, doc.id)
        assignments = list(db.execute(
            select(AssignedReviewer).join(DocumentVersion, AssignedReviewer.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id == doc.id, AssignedReviewer.is_active == 1)
            .order_by(AssignedReviewer.id)
        ).scalars())
        active = [a for a in assignments if a.completed_at is None]
        has_reviewers = bool(active)
        if filter_status == "assigned" and not has_reviewers:
            continue
        if filter_status == "unassigned" and has_reviewers:
            continue
        vcount = versions_count(db, doc.id)
        document_data.append({
            "document": {
                "id": doc.id,
                "document_number": doc.document_number,
                "document_name": doc.document_name,
                "stage_status": doc.stage_status,
                "owner": brief(doc.user),
                "has_versions": vcount > 0,
                "has_approved_version": has_approved_version(db, doc.id),
            },
            "latest_version": {"id": lv.id, "version_number": lv.version_number} if lv else None,
            "has_reviewers": has_reviewers,
            "active_reviewers": [{
                "id": a.id,
                "reviewer": brief(a.user),
                # template renders assignment.assigned_at, a field AssignedReviewer does not have -> blank
                "assigned_at": None,
                "started_at": iso(a.started_at),
            } for a in active],
            "total_reviewers": len(assignments),
            "completed_reviews": sum(1 for a in assignments if a.completed_at is not None),
        })

    total = len(document_data)
    with_reviewers = sum(1 for d in document_data if d["has_reviewers"])
    return {
        "page_title": "Reviewer Assignments Overview",
        "document_data": document_data,
        "filter_status": filter_status,
        "filter_document_status": document_status,
        "search_query": search,
        "total_documents": total,
        "documents_with_reviewers": with_reviewers,
        "documents_without_reviewers": total - with_reviewers,
        "documents_needing_reviewers": sum(1 for d in document_data
                                           if d["document"]["stage_status"] == 1 and not d["has_reviewers"]),
        "stage_choices": [{"value": v, "label": l} for v, l in STAGE_CHOICES],
    }
