"""Endpoints used by the app shell on every page: sidebar quick stats and the notification bell.

Ports of library.views.quick_stats_api, documents.views.get_notifications_api and
documents.views.mark_notification_read.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import is_admin_like
from app.core.utils import full_name, iso, time_ago
from app.database import get_db
from app.models import Document, DocumentNotification, ReferenceDocument, ReferenceZip, User

router = APIRouter(prefix="/api", tags=["shell"])


@router.get("/library/quick-stats")
def quick_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    def count(stmt):
        return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    docs = select(Document.id).where(Document.is_active == 1)
    refs = select(ReferenceDocument.id).where(ReferenceDocument.is_active == 1)
    zips = select(ReferenceZip.id)
    if not is_admin_like(user):
        docs = docs.where(Document.user_id == user.id)
        refs = refs.where(ReferenceDocument.user_id == user.id)
        zips = zips.where(ReferenceZip.user_id == user.id)
    return {"success": True, "data": {
        "total_documents": count(docs),
        "total_references": count(refs),
        "zip_references": count(zips),
    }}


def serialize_notification(n: DocumentNotification) -> dict:
    return {
        "id": n.id,
        "type": n.document_type,
        "description": n.description,
        "document_id": n.document_id,
        "sender": full_name(n.sender) if n.sender else "System",
        "is_seen": bool(n.is_seen),
        "created_at": iso(n.created_at),
        "time_ago": time_ago(n.created_at),
    }


@router.get("/notifications/recent")
def recent_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.execute(
        select(DocumentNotification).where(DocumentNotification.receiver_id == user.id)
        .order_by(DocumentNotification.created_at.desc()).limit(20)
    ).scalars().all()
    unread = db.execute(
        select(func.count(DocumentNotification.id))
        .where(DocumentNotification.receiver_id == user.id, DocumentNotification.is_seen == 0)
    ).scalar_one()
    return {"notifications": [serialize_notification(n) for n in items], "unread_count": unread}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(DocumentNotification, notification_id)
    if not n or n.receiver_id != user.id:
        raise HTTPException(404, "Notification not found")
    n.is_seen = 1
    db.commit()
    return {"success": True}
