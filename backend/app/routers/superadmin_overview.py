"""Superadmin dashboard overview: headline numbers, activity series and system health (read-only)."""
import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import require_superuser
from app.core.utils import full_name, iso
from app.database import get_db
from app.services.superadmin_scope import workspace_of
from app.models import (
    Document, DocumentVersion, EmailLog, LoginLog, OrgMembership, ReferenceDocument, ReferenceZip,
    ResearchProject, SMTPSettings, User, utcnow,
)

router = APIRouter(prefix="/api/superadmin", tags=["superadmin"])

STAGES = {0: "Draft", 1: "Under Review", 2: "Approved", 3: "Draft Under Revision"}


def _count(db: Session, stmt) -> int:
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(require_superuser)):
    now = utcnow()
    d30 = now - datetime.timedelta(days=30)
    d14 = (now - datetime.timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)

    # ?workspace=<id> (the dashboard's workspace field): the numbers of that university/organisation —
    # documents, references… are limited by the tenancy filter; users and logins are limited here.
    workspace = workspace_of(db)
    members_only = [User.is_superuser == 0] if workspace else []
    logins_of = [LoginLog.user_id.in_(select(OrgMembership.user_id).where(OrgMembership.organisation_id == workspace))] \
        if workspace else []
    users = {
        "total": _count(db, select(User.id).where(*members_only)),
        "active": _count(db, select(User.id).where(User.is_active == 1, *members_only)),
        "superusers": _count(db, select(User.id).where(User.is_superuser == 1)),
        "staff": _count(db, select(User.id).where(User.is_staff == 1, *members_only)),
        "new_30d": _count(db, select(User.id).where(User.date_joined >= d30, *members_only)),
    }

    stage_rows = db.execute(
        select(Document.stage_status, func.count(Document.id)).where(Document.is_active == 1).group_by(Document.stage_status)
    ).all()
    documents = {
        "total": sum(c for _, c in stage_rows),
        "versions": _count(db, select(DocumentVersion.id)),
        "new_30d": _count(db, select(Document.id).where(Document.is_active == 1, Document.created_at >= d30)),
        "by_stage": [{"stage": s, "label": STAGES.get(s, str(s)), "count": c} for s, c in sorted(stage_rows)],
    }

    library = {
        "references": _count(db, select(ReferenceDocument.id).where(ReferenceDocument.is_active == 1)),
        "zips": _count(db, select(ReferenceZip.id)),
        "projects": _count(db, select(ResearchProject.id)),
    }

    email_rows = db.execute(select(EmailLog.status, func.count(EmailLog.id)).group_by(EmailLog.status)).all()
    emails = {
        "by_status": {s: c for s, c in email_rows},
        "total": sum(c for _, c in email_rows),
        "last_30d": _count(db, select(EmailLog.id).where(EmailLog.created_at >= d30)),
    }

    # Login activity — successful vs failed per day, last 14 days
    day = func.date(LoginLog.login_time)
    series_rows = db.execute(
        select(day, LoginLog.status, func.count(LoginLog.id))
        .where(LoginLog.login_time >= d14, LoginLog.status.in_(("success", "failed", "blocked")), *logins_of)
        .group_by(day, LoginLog.status)
    ).all()
    by_day: dict[str, dict[str, int]] = {}
    for d, status, c in series_rows:
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        by_day.setdefault(key, {})["success" if status == "success" else "failed"] = \
            by_day.get(key, {}).get("success" if status == "success" else "failed", 0) + c
    logins_series = []
    for i in range(14):
        key = (d14 + datetime.timedelta(days=i)).date().isoformat()
        logins_series.append({"date": key, "success": by_day.get(key, {}).get("success", 0),
                              "failed": by_day.get(key, {}).get("failed", 0)})

    recent_logins = db.execute(
        select(LoginLog).where(LoginLog.status.in_(("success", "failed", "blocked")), *logins_of)
        .order_by(LoginLog.login_time.desc()).limit(8)
    ).scalars().all()

    smtp = db.execute(select(SMTPSettings).where(SMTPSettings.is_active == 1).limit(1)).scalar_one_or_none()
    media = settings.media_root
    health = {
        "database": settings.DB_NAME,
        "media_root": str(media),
        "media_exists": media.is_dir() and any(media.iterdir()) if media.is_dir() else False,
        "smtp": f"{smtp.host}:{smtp.port}" if smtp else None,
        "email_fallback": settings.EMAIL_BACKEND,
        "pdftron_version": settings.PDFTRON_VERSION,
        "pdftron_licensed": bool((settings.PDFTRON_LICENSE_KEY or "").strip()),
        "onlyoffice_url": settings.ONLYOFFICE_DOCUMENT_SERVER_URL,
        "debug": settings.DEBUG,
    }

    return {
        "generated_at": iso(now),
        "users": users,
        "documents": documents,
        "library": library,
        "emails": emails,
        "logins": {
            "series": logins_series,
            "success_14d": sum(p["success"] for p in logins_series),
            "failed_14d": sum(p["failed"] for p in logins_series),
            "recent": [{
                "id": l.id,
                "username": l.username_attempted,
                "name": full_name(l.user) if l.user else None,
                "status": l.status,
                "ip": l.ip_address,
                "time": iso(l.login_time),
            } for l in recent_logins],
        },
        "health": health,
    }
