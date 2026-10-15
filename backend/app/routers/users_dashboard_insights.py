"""Extra, read-only panels for the Manager Dashboard: recent uploads, monthly upload activity,
documents waiting longest in review, reviewer workload, review turnaround and top contributors. Same permission as the dashboard."""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.core.permissions import can
from app.core.utils import full_name, iso
from app.database import get_db
from app.models import AssignedReviewer, Document, DocumentVersion, User, utcnow

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/manager-dashboard/insights")
def manager_dashboard_insights(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can(db, user, "can_access_manager_dashboard"):
        raise HTTPException(403, "You do not have permission to access the manager dashboard")
    now = utcnow()

    # Recent uploads: newest versions of active documents (a version_count of 1 is a new document)
    recent = db.execute(
        select(DocumentVersion).join(Document, DocumentVersion.document_id == Document.id)
        .where(Document.is_active == 1)
        .options(joinedload(DocumentVersion.document), joinedload(DocumentVersion.created_by))
        .order_by(DocumentVersion.created_at.desc()).limit(8)
    ).scalars().unique().all()
    recent_uploads = [{
        "version_id": v.id,
        "document_id": v.document_id,
        "document_name": v.document.document_name,
        "document_number": v.document.document_number,
        "version_number": v.version_number,
        "is_new_document": v.version_count == 1,
        "file_extension": (v.file_extension or "").upper(),
        "uploaded_by": full_name(v.created_by),
        "uploaded_at": iso(v.created_at),
        "stage_status": v.stage_status,
    } for v in recent]

    # Monthly upload activity, last 12 months (new documents vs. new versions of existing ones)
    first_month = (now.replace(day=1) - datetime.timedelta(days=330)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month = func.date_format(DocumentVersion.created_at, "%Y-%m")
    rows = db.execute(
        select(month, func.count(DocumentVersion.id), func.sum(case((DocumentVersion.version_count == 1, 1), else_=0)))
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(Document.is_active == 1, DocumentVersion.created_at >= first_month)
        .group_by(month)
    ).all()
    by_month = {m: (int(total or 0), int(new or 0)) for m, total, new in rows}
    activity = []
    y, mth = first_month.year, first_month.month
    for _ in range(12):
        key = f"{y:04d}-{mth:02d}"
        total, new = by_month.get(key, (0, 0))
        activity.append({"month": key, "new_documents": new, "new_versions": total - new})
        mth += 1
        if mth > 12:
            y, mth = y + 1, 1

    # Waiting longest: active, unfinished review assignments, oldest first
    waiting_rows = db.execute(
        select(AssignedReviewer).join(DocumentVersion, AssignedReviewer.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(AssignedReviewer.is_active == 1, AssignedReviewer.is_completed == 0, Document.is_active == 1)
        .options(joinedload(AssignedReviewer.document_version).joinedload(DocumentVersion.document),
                 joinedload(AssignedReviewer.user))
        .order_by(AssignedReviewer.created_at.asc()).limit(6)
    ).scalars().unique().all()
    waiting = [{
        "assignment_id": a.id,
        "document_id": a.document_version.document_id,
        "document_name": a.document_version.document.document_name,
        "version_number": a.document_version.version_number,
        "reviewer": full_name(a.user),
        "assigned_at": iso(a.created_at),
        "due_at": iso(a.review_date),
        "days_waiting": (now - a.created_at).days,
        "overdue": a.review_date < now,
        "started": a.started_at is not None,
    } for a in waiting_rows]

    # Reviewer workload: open assignments per reviewer
    load_rows = db.execute(
        select(AssignedReviewer.user_id, func.count(AssignedReviewer.id),
               func.sum(case((AssignedReviewer.review_date < now, 1), else_=0)),
               func.sum(case((AssignedReviewer.started_at.isnot(None), 1), else_=0)))
        .where(AssignedReviewer.is_active == 1, AssignedReviewer.is_completed == 0)
        .group_by(AssignedReviewer.user_id).order_by(func.count(AssignedReviewer.id).desc()).limit(8)
    ).all()
    reviewers = {u.id: u for u in db.execute(select(User).where(User.id.in_([r[0] for r in load_rows] or [-1]))).scalars()}
    completed_30d = dict(db.execute(
        select(AssignedReviewer.user_id, func.count(AssignedReviewer.id))
        .where(AssignedReviewer.is_completed == 1, AssignedReviewer.completed_at >= now - datetime.timedelta(days=30))
        .group_by(AssignedReviewer.user_id)
    ).all())
    workload = [{
        "reviewer_id": uid,
        "reviewer": full_name(reviewers.get(uid)),
        "open": int(open_), "overdue": int(overdue or 0), "started": int(started or 0),
        "completed_30d": int(completed_30d.get(uid, 0)),
    } for uid, open_, overdue, started in load_rows]

    # Review turnaround: reviews finished in the last 90 days, and how long open ones have waited
    since = now - datetime.timedelta(days=90)
    done = db.execute(select(AssignedReviewer.created_at, AssignedReviewer.completed_at, AssignedReviewer.review_date)
                      .where(AssignedReviewer.is_active == 1, AssignedReviewer.is_completed == 1,
                             AssignedReviewer.completed_at >= since)).all()
    open_since = db.execute(select(AssignedReviewer.created_at).where(
        AssignedReviewer.is_active == 1, AssignedReviewer.is_completed == 0)).scalars().all()
    days = [max((c - a).total_seconds() / 86400, 0) for a, c, _ in done if a and c]
    on_time = sum(1 for _, c, due in done if c and due and c <= due + datetime.timedelta(days=1))
    turnaround = {
        "completed_90d": len(done),
        "avg_days": round(sum(days) / len(days), 1) if days else None,
        "on_time_pct": round(on_time * 100 / len(done)) if done else None,
        "open": len(open_since),
        "open_avg_age_days": round(sum((now - a).days for a in open_since) / len(open_since)) if open_since else None,
    }

    # Top contributors: who uploaded most new documents in the last 12 months
    top_rows = db.execute(select(Document.user_id, func.count(Document.id)).where(
        Document.is_active == 1, Document.created_at >= first_month)
        .group_by(Document.user_id).order_by(func.count(Document.id).desc()).limit(5)).all()
    uploaders = {u.id: u for u in db.execute(select(User).where(User.id.in_([r[0] for r in top_rows] or [-1]))).scalars()}
    top_contributors = [{"user_id": uid, "name": full_name(uploaders.get(uid)), "documents": int(n)} for uid, n in top_rows]

    this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month = (this_month - datetime.timedelta(days=1)).replace(day=1)
    new_docs = lambda a, b: db.execute(select(func.count(Document.id)).where(  # noqa: E731
        Document.is_active == 1, Document.created_at >= a, Document.created_at < b)).scalar_one()

    return {
        "recent_uploads": recent_uploads,
        "activity": activity,
        "waiting": waiting,
        "workload": workload,
        "turnaround": turnaround,
        "top_contributors": top_contributors,
        "new_documents_this_month": new_docs(this_month, now + datetime.timedelta(days=1)),
        "new_documents_last_month": new_docs(last_month, this_month),
    }
