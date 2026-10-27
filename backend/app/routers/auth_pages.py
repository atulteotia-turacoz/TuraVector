"""Page-context and form endpoints for pages owned by the auth module that Django
served from documents/views.py: dashboard selection, notifications page, help &
support (+ support request), feedback, and the Other Documents profile page.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.email import send_email_with_logging
from app.core.utils import iso
from app.database import get_db
from app.core.permissions import PermissionChecker
from app.services import subscriptions
from app.services.external_apps import Card, app_of, card_visible, tool_by_key, visible_apps
from app.services.external_apps_sso import SSOError, launch_url, sso_configured
from app.models import (
    Document, DocumentFeedback, DocumentNotification, DocumentSupport, DocumentVersion, User,
)
from app.schemas.auth_schemas import FeedbackIn, SupportIn
from app.services.auth_account import aware_str

router = APIRouter(prefix="/api/documents", tags=["auth-pages"])

NOTIFICATION_TYPES = {
    "document_upload": "Document Upload",
    "review_request": "Review Request",
    "document_approved": "Document Approved",
    "document_rejected": "Document Rejected",
    "version_updated": "Version Updated",
    "invoice": "Invoice",
}


def _get_full_name(u: User | None) -> str:
    """Django AbstractUser.get_full_name()."""
    return f"{u.first_name} {u.last_name}".strip() if u is not None else ""


def _err(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


# ------------------------------------------------------------------ dashboard selection
@router.get("/dashboard-selection")
def dashboard_selection(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """dashboard_selection_view. `redirect` tells the client where Django would have redirected.
    Also lists the tools the user doesn't have yet (with the plans that include them) and the
    workspace's subscriptions, so the page can offer upgrades."""
    # Cards are set per user, by plan or free — see app/services/external_apps.py
    checker = PermissionChecker(db, user)
    content_lab, other_documents = tool_by_key(db, "content_lab"), tool_by_key(db, "other_documents")
    can_access_content_lab = bool(content_lab and content_lab.is_active) and card_visible(
        checker, user, Card("content_lab", "", "dashboard", "content_lab", "cl_dashboard_access"))
    can_access_other_documents = bool(other_documents and other_documents.is_active) and card_visible(
        checker, user, Card("other_documents", "", "dashboard", "other_documents", "od_dashboard_access"))

    apps = visible_apps(db, user)
    for a in apps:
        a["sso"] = sso_configured(app_of(tool_by_key(db, a["key"])))
    store = subscriptions.store_summary(db, user, {"content_lab": can_access_content_lab,
                                                   "other_documents": can_access_other_documents,
                                                   **{a["key"]: True for a in apps}})
    dashboards = {t.key: subscriptions.tool_payload(t) for t in (content_lab, other_documents) if t is not None}
    result = {
        "can_access_content_lab": can_access_content_lab,
        "can_access_other_documents": can_access_other_documents,
        "dashboards": dashboards,
        "apps": apps,
        **store,
        "redirect": None,
        "error": None,
    }
    # With application cards, tools to unlock or a payment to finish the page always shows.
    if apps or store["locked_tools"] or store["pending"]:
        return result
    if not can_access_content_lab and not can_access_other_documents:
        result["redirect"] = "/profile/"
        result["error"] = "You do not have permission to access any dashboard. Please contact your administrator."
    elif can_access_content_lab and not can_access_other_documents:
        result["redirect"] = "/content-lab-management/dashboard/"
    elif can_access_other_documents and not can_access_content_lab:
        result["redirect"] = "/journal-selector/dashboard/"
    return result


@router.post("/external-apps/{key}/launch")
def launch_external_app(key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """URL that opens another application already signed in (single sign-on when it's set up).
    Only for users who can see that app's card on the dashboard-selection page."""
    tool = tool_by_key(db, key)
    if tool is None or key not in {a["key"] for a in visible_apps(db, user)}:
        return _err("You do not have access to this application.", 403)
    try:
        return {"url": launch_url(app_of(tool), user)}
    except SSOError as exc:
        return _err(str(exc), 502)


# ------------------------------------------------------------------ notifications page
@router.get("/notifications")
def notifications_page(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """notifications_view: counts unread, then marks every notification seen.

    Django's queryset was evaluated by the template *after* the update, so every
    row is rendered as seen; the same happens here.
    """
    unread_count = db.execute(
        select(func.count(DocumentNotification.id))
        .where(DocumentNotification.receiver_id == user.id, DocumentNotification.is_seen == 0)
    ).scalar_one()
    db.execute(
        update(DocumentNotification)
        .where(DocumentNotification.receiver_id == user.id, DocumentNotification.is_seen == 0)
        .values(is_seen=1)
    )
    db.commit()
    rows = db.execute(
        select(DocumentNotification).where(DocumentNotification.receiver_id == user.id)
        .order_by(DocumentNotification.created_at.desc())
    ).scalars().all()
    return {
        "unread_count": unread_count,
        "total": len(rows),
        "notifications": [{
            "id": n.id,
            "document_type": n.document_type,
            "document_type_display": NOTIFICATION_TYPES.get(n.document_type, n.document_type),
            "description": n.description,
            "document_id": n.document_id,
            "sender": _get_full_name(n.sender) or "System",
            "sent_for": n.sent_for,
            "is_seen": bool(n.is_seen),
            "created_at": iso(n.created_at),
        } for n in rows],
    }


# ------------------------------------------------------------------ help & support
def _serialize_support(s: DocumentSupport) -> dict:
    return {
        "id": s.id,
        "subject": s.subject,
        "message": s.message,
        "is_resolved": bool(s.is_resolved),
        "created_at": iso(s.created_at),
    }


@router.get("/help-support")
def help_support(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(DocumentSupport).where(DocumentSupport.user_id == user.id).order_by(DocumentSupport.created_at.desc())
    ).scalars().all()
    return {"support_requests": [_serialize_support(s) for s in rows]}


@router.post("/support")
def submit_support_request(body: SupportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        subject, message = body.subject, body.message
        if not all([subject, message]):
            return _err("All fields are required", 400)

        support = DocumentSupport(user_id=user.id, subject=subject, message=message, is_resolved=0)
        db.add(support)
        db.commit()

        admin_subject = f'Support Request: {subject}'
        admin_message = f'''
        New support request from {user.first_name} {user.last_name}:

        Subject: {subject}
        Message: {message}

        User Email: {user.email}
        Submitted at: {aware_str(support.created_at)}
        '''
        send_email_with_logging(
            db, admin_subject, admin_message, ["atul.teotia@turacoz.com"], "support_request",
            from_email="noreply@turadome.com", sender_user=user, recipient_user=None,
        )
        return {"message": "Support request submitted successfully"}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


@router.post("/feedback")
def submit_feedback(body: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        project_id, rating, feedback_text = body.project_id, body.rating, body.feedback
        if not all([project_id, rating, feedback_text]):
            return _err("All fields are required", 400)
        db.add(DocumentFeedback(user_id=user.id, project_id=project_id, rating=int(rating), feedback_text=feedback_text))
        db.commit()
        return {"message": "Feedback submitted successfully"}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


# ------------------------------------------------------------------ other documents profile
@router.get("/other-documents/profile")
def other_documents_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    def count(stmt) -> int:
        return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    documents = select(Document.id).where(Document.user_id == user.id)
    versions = select(DocumentVersion.id).join(Document, DocumentVersion.document_id == Document.id).where(Document.user_id == user.id)

    return {
        "total_documents": count(documents),
        "total_versions": count(versions),
    }
