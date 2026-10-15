"""Manager dashboard (library.views.manager_dashboard_view) and the reports data (reports_view)."""
import datetime
import math
from dataclasses import dataclass
from typing import Any

import pytz
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.utils import iso, user_type_display
from app.models import AssignedReviewer, Document, DocumentVersion, ReferenceDocument, User, UserType, utcnow
from app.services.users_common import document_counts, user_row

STATUS_MAPPING = [  # insertion order of the Django dict matters: first substring hit wins
    ("draft", 0), ("under review", 1), ("review", 1), ("approved", 2),
    ("draft under revision", 3), ("revision", 3), ("revised", 3),
]
LEGACY_TYPE_CHOICES = {"student": "Student", "teacher": "Teacher", "reviewer": "Reviewer", "manager": "Manager"}


def latest_version_statuses(db: Session, doc_ids: list[int] | None = None) -> dict[int, int]:
    """document.versions.order_by('-version_count').first().stage_status for every document."""
    stmt = select(DocumentVersion.document_id, DocumentVersion.version_count, DocumentVersion.stage_status, DocumentVersion.id)
    if doc_ids is not None:
        if not doc_ids:
            return {}
        stmt = stmt.where(DocumentVersion.document_id.in_(doc_ids))
    best: dict[int, tuple[int, int, int]] = {}
    for doc_id, count, status, vid in db.execute(stmt).all():
        cur = best.get(doc_id)
        if cur is None or (count, vid) > (cur[0], cur[2]):
            best[doc_id] = (count, status, vid)
    return {k: v[1] for k, v in best.items()}


def manager_dashboard(db: Session, search: str, page: int | str | None) -> dict[str, Any]:
    active_doc_ids = list(db.execute(select(Document.id).where(Document.is_active == 1)).scalars())
    total_documents = len(active_doc_ids)
    total_users = db.execute(select(func.count(User.id)).where(User.is_active == 1)).scalar_one()
    pending_reviews = db.execute(select(func.count(AssignedReviewer.id)).where(AssignedReviewer.is_completed == 0)).scalar_one()

    latest = latest_version_statuses(db, active_doc_ids)
    counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for doc_id in active_doc_ids:
        if doc_id in latest and latest[doc_id] in counts:
            counts[latest[doc_id]] += 1

    stmt = select(Document).where(Document.is_active == 1)
    if search:
        search_lower = search.lower()
        status_value = None
        for text, value in STATUS_MAPPING:
            if text in search_lower:
                status_value = value
                break
        if status_value is not None:
            ids = [d for d in active_doc_ids if latest.get(d) == status_value]
            stmt = stmt.where(Document.id.in_(ids or [-1]))
        else:
            like = f"%{search}%"
            owner = select(User.id).outerjoin(UserType, User.user_type_new_id == UserType.id).where(or_(
                User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like),
                User.user_type.ilike(like), UserType.name.ilike(like),
                func.concat(User.first_name, " ", User.last_name).ilike(like),
            ))
            conds = [Document.document_number.ilike(like), Document.document_name.ilike(like), Document.user_id.in_(owner)]
            type_matches = [code for code, disp in LEGACY_TYPE_CHOICES.items() if search_lower in disp.lower()]
            if type_matches:
                conds.append(Document.user_id.in_(select(User.id).where(User.user_type.in_(type_matches))))
            stmt = stmt.where(or_(*conds))
    stmt = stmt.order_by(Document.created_at.desc())

    # Paginator(…, 10).get_page(page): invalid → 1, out of range → last
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    pages = max(1, math.ceil(total / 10))
    try:
        p = int(page) if page not in (None, "") else 1
    except (TypeError, ValueError):
        p = 1
    if p < 1 or p > pages:
        p = pages
    docs = db.execute(stmt.options(joinedload(Document.user)).limit(10).offset((p - 1) * 10)).scalars().unique().all()

    items = [{
        "id": d.id,
        "document_number": d.document_number,
        "document_name": d.document_name,
        "user_name": f"{d.user.first_name} {d.user.last_name}" if d.user else "",
        "latest_version_status": latest.get(d.id, d.stage_status),
        "created_at": iso(d.created_at),
    } for d in docs]

    return {
        "page_title": "Dashboard",
        "total_documents": total_documents,
        "total_users": total_users,
        "pending_reviews": pending_reviews,
        "draft_documents": counts[0],
        "under_review_documents": counts[1],
        "approved_documents": counts[2],
        "revision_documents": counts[3],
        "search_query": search,
        "recent_documents": {"items": items, "page": p, "pages": pages, "total": total},
    }


# ---------------------------------------------------------------- reports
PERIODS = {"7": (7, "Last 7 Days"), "30": (30, "Last 30 Days"), "90": (90, "Last 90 Days")}


def period_for(date_range: str) -> tuple[datetime.datetime, str]:
    days, name = PERIODS.get(date_range, (365, "Last Year"))
    return utcnow() - datetime.timedelta(days=days), name


@dataclass(frozen=True)
class Period:
    """The report window. Presets count "in the period" from `start`; a custom range also limits the
    lists (recent documents, top users, new users) to documents and people of those dates."""
    start: datetime.datetime
    end: datetime.datetime | None  # exclusive; None = now
    name: str
    custom: bool = False


def resolve_period(date_range: str, date_from: str = "", date_to: str = "", tz=None) -> Period:
    """`date_range` 7/30/90/365, or "custom" with `date_from` / `date_to` (YYYY-MM-DD, the viewer's
    local days, both inclusive)."""
    if date_range != "custom":
        start, name = period_for(date_range)
        return Period(start, None, name)
    try:
        first = datetime.date.fromisoformat(date_from)
        last = datetime.date.fromisoformat(date_to) if date_to else utcnow().date()
    except ValueError:
        raise ValueError("Choose a valid From and To date.") from None
    if last < first:
        raise ValueError("The To date must be on or after the From date.")
    tz = tz or pytz.UTC

    def utc_midnight(day: datetime.date) -> datetime.datetime:
        return tz.localize(datetime.datetime.combine(day, datetime.time())).astimezone(pytz.UTC).replace(tzinfo=None)
    name = f"{first:%d %b %Y} to {last:%d %b %Y}"  # plain ASCII: it ends up in download file names
    return Period(utc_midnight(first), utc_midnight(last + datetime.timedelta(days=1)), name, True)


def _within(column, period: "Period | None") -> list:
    if period is None or not period.custom:
        return []
    return [column >= period.start, column < period.end]


def top_users(db: Session, limit: int, period: Period | None = None) -> list[tuple[User, int]]:
    """User.objects.annotate(document_count=Count('documents', filter=active)).filter(>0).order_by('-document_count')"""
    cnt = func.count(Document.id).label("document_count")
    rows = db.execute(
        select(User, cnt).join(Document, and_(Document.user_id == User.id, Document.is_active == 1,
                                              *_within(Document.created_at, period)))
        .group_by(User.id).having(cnt > 0).order_by(cnt.desc()).limit(limit)
    ).all()
    return [(u, n) for u, n in rows]


def recent_documents(db: Session, limit: int, period: Period | None = None) -> list[Document]:
    return list(db.execute(
        select(Document).where(Document.is_active == 1, *_within(Document.created_at, period)).options(
            joinedload(Document.user), joinedload(Document.document_type), joinedload(Document.brand))
        .order_by(Document.created_at.desc()).limit(limit)
    ).scalars().unique())


def recent_users(db: Session, limit: int, period: Period | None = None) -> list[User]:
    return list(db.execute(
        select(User).where(User.is_active == 1, *_within(User.date_joined, period)).options(joinedload(User.user_type_new))
        .order_by(User.date_joined.desc()).limit(limit)
    ).scalars().unique())


def report_numbers(db: Session, start_date: datetime.datetime, end_date: datetime.datetime | None = None) -> dict[str, int]:
    def count(stmt):
        return db.execute(stmt).scalar_one()
    end = end_date or (utcnow() + datetime.timedelta(days=1))
    doc_status = lambda s: count(select(func.count(Document.id)).where(Document.stage_status == s, Document.is_active == 1))  # noqa: E731
    return {
        "total_documents": count(select(func.count(Document.id)).where(Document.is_active == 1)),
        "documents_in_period": count(select(func.count(Document.id)).where(Document.created_at >= start_date, Document.created_at < end, Document.is_active == 1)),
        "total_versions": count(select(func.count(DocumentVersion.id))),
        "versions_in_period": count(select(func.count(DocumentVersion.id)).where(DocumentVersion.created_at >= start_date, DocumentVersion.created_at < end)),
        "active_users": count(select(func.count(User.id)).where(User.is_active == 1, User.last_login >= start_date, User.last_login < end)),
        "draft_docs": doc_status(0),
        "review_docs": doc_status(1),
        "approved_docs": doc_status(2),
        "revised_docs": doc_status(3),
        "total_references": count(select(func.count(ReferenceDocument.id)).where(ReferenceDocument.is_active == 1)),
        "references_in_period": count(select(func.count(ReferenceDocument.id)).where(
            ReferenceDocument.created_at >= start_date, ReferenceDocument.created_at < end, ReferenceDocument.is_active == 1)),
    }


def reports(db: Session, date_range: str, period: Period | None = None) -> dict[str, Any]:
    period = period or resolve_period(date_range)
    docs = recent_documents(db, 10, period)
    users = recent_users(db, 10, period)
    counts = document_counts(db, [u.id for u in users])
    return {
        "page_title": "Reports & Analytics",
        "date_range": date_range,
        "period_name": period.name,
        "start_date": iso(period.start),
        "end_date": iso(period.end or utcnow()),
        **report_numbers(db, period.start, period.end),
        "recent_documents": [{
            "id": d.id, "document_name": d.document_name, "document_number": d.document_number,
            "owner": f"{d.user.first_name} {d.user.last_name}", "stage_status": d.stage_status,
            "created_at": iso(d.created_at),
        } for d in docs],
        "recent_users": [user_row(u, counts.get(u.id, 0)) for u in users],
        "top_users": [{**user_row(u), "document_count": n, "user_type_display": user_type_display(u)} for u, n in top_users(db, 10, period)],
    }
