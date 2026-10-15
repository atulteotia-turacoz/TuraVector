"""Reviewer workflow from documents.views.document_review_view.

(The preview page's Send for Review / Revision / Complete buttons call the
doccore module's /api/doccore/workflow/* ports of those Django views.)

Notification rows, EmailLog rows, email texts and status transitions are
reproduced verbatim from the Django code.
"""
import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.tenancy import org_admin_ids
from app.core.email import send_email_with_logging
from app.core.utils import format_datetime_for_user
from app.models import AssignedReviewer, DocumentNotification, DocumentVersion, User, utcnow
from app.services.viewer_common import STAGE_LABELS, frontend_url, get_full_name

log = logging.getLogger("turadome.viewer")


def _notify(db: Session, receiver_id: int, sender_id: int, document_type: str, document_id: int,
            description: str, sent_for: str) -> None:
    db.add(DocumentNotification(
        receiver_id=receiver_id, sender_id=sender_id, document_type=document_type,
        document_id=document_id, description=description, sent_for=sent_for, is_seen=0,
    ))


def _active_legacy_managers(db: Session, exclude_ids: list[int]) -> list[User]:
    return list(db.execute(
        select(User).where(User.user_type.in_(["manager"]), User.is_active == 1, User.id.not_in(exclude_ids))
    ).scalars())


# ------------------------------------------------------------------ review start (first open)
def mark_review_started(db: Session, assignment: AssignedReviewer, version: DocumentVersion, user: User) -> None:
    assignment.started_at = utcnow()
    db.commit()

    document = version.document
    owner = document.user
    try:
        if owner.id != user.id:
            _notify(db, owner.id, user.id, "review_request", document.id,
                    f'Reviewer {get_full_name(user)} has started reviewing your document '
                    f'"{document.document_name}" (Version: {version.version_number})',
                    "review_started")
        for manager in _active_legacy_managers(db, [user.id, owner.id]):
            _notify(db, manager.id, user.id, "review_request", document.id,
                    f'Review of document "{document.document_name}" has been started by {get_full_name(user)}',
                    "review_started_manager")
        db.commit()
    except Exception as exc:  # noqa: BLE001 — notifications never block the review
        db.rollback()
        log.error("Error creating review start notifications: %s", exc)

    try:
        reviewer_name = get_full_name(user) or user.username
        owner_name = owner.first_name or owner.username
        due = (format_datetime_for_user(assignment.review_date, user, "%B %d, %Y")
               if assignment.review_date else "Not specified")
        subject = f"🔍 Review Started: {document.document_name}"
        message = f'''Dear {owner_name},

Good news! Your document review has been started by our reviewer.

📋 Document Details:
• Document Name: {document.document_name}
• Document Number: {document.document_number}
• Version: {version.version_number}
• Document Type: {document.document_type.name if document.document_type else 'N/A'}

👨‍💼 Reviewer Information:
• Reviewer: {reviewer_name}
• Review Started: {format_datetime_for_user(assignment.started_at, user)}
• Due Date: {due}

📊 Current Status:
• Document Status: {STAGE_LABELS.get(document.stage_status, document.stage_status)}
• Review Status: In Progress

🔗 Quick Actions:
• View Document: {frontend_url(f'/content-lab-management/preview/{version.id}/')}
• Document Details: {frontend_url(f'/content-lab-management/document/{document.id}/')}
• Mail Logs: {frontend_url('/documents/mail-logs/')}

Your document is now being actively reviewed. You will receive another notification once the review is completed with the reviewer's decision and comments.

Best regards,
TuraVector System'''
        send_email_with_logging(db, subject, message, [owner.email], "review_started",
                                from_email="noreply@turadome.com", sender_user=user, recipient_user=owner,
                                document=document, document_version=version)
    except Exception as exc:  # noqa: BLE001
        log.error("Error sending review started notification: %s", exc)


# ------------------------------------------------------------------ review submit (POST)
def submit_review(db: Session, assignment: AssignedReviewer | None, version: DocumentVersion, user: User,
                  comments: str, decision: str) -> dict:
    """Returns {'level': 'success'|'error', 'message': str, 'warnings': [...]} like Django `messages`."""
    warnings: list[str] = []
    document = version.document
    owner = document.user
    try:
        if assignment is not None:
            assignment.remarks = comments
            assignment.is_completed = 1
            assignment.completed_at = utcnow()
            assignment.modified_by_id = user.id
            db.commit()

        try:
            notification_type = "document_approved" if decision == "approved" else "document_rejected"
            action = "approved" if decision == "approved" else "rejected"
            if owner.id != user.id:
                _notify(db, owner.id, user.id, notification_type, document.id,
                        f'Your document "{document.document_name}" has been {action} by reviewer '
                        f'{get_full_name(user)}. Comments: {comments[:100]}{"..." if len(comments) > 100 else ""}',
                        f"review_completed_{action}")
            for manager in _active_legacy_managers(db, [user.id, owner.id]):
                _notify(db, manager.id, user.id, notification_type, document.id,
                        f'Document "{document.document_name}" has been {action} by reviewer {get_full_name(user)}',
                        f"review_completed_{action}_manager")
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.error("Error creating review completion notifications: %s", exc)

        reviewer_name = get_full_name(user) or user.username
        owner_name = owner.first_name or owner.username
        preview_link = frontend_url(f"/content-lab-management/preview/{version.id}/")

        status_message = subject = message = email_type = None
        if decision == "approved":
            version.stage_status = 2
            db.commit()
            document.stage_status = 2
            status_message, email_type = "approved", "approval_notification"
            subject = f"✅ Document Approved: {document.document_name}"
            message = f'''Dear {owner_name},

Great news! Your document has been APPROVED by the reviewer.

📄 Document Details:
• Document: {document.document_name}
• Version: {version.version_number}
• Document Number: {document.document_number}
• Reviewed by: {reviewer_name}
• Status: ✅ APPROVED

💬 Reviewer Comments:
{comments}

🎉 Congratulations! Your document has met all requirements and is now approved.

📋 Next Steps:
• Your document is now ready for final use
• You can download the approved version from the system
• View the document with reviewer annotations at: {preview_link}

Best regards,
TuraVector Review Team'''
        elif decision == "revision":
            document.stage_status = 3
            status_message, email_type = "requires revision", "revision_request"
            subject = f"📝 Revision Required: {document.document_name}"
            message = f'''Dear {owner_name},

Your document has been reviewed and requires revision before approval.

📄 Document Details:
• Document: {document.document_name}
• Version: {version.version_number}
• Document Number: {document.document_number}
• Reviewed by: {reviewer_name}
• Status: 📝 REVISION REQUIRED

💬 Reviewer Comments & Required Changes:
{comments}

📋 Next Steps:
1. Review the feedback provided by the reviewer
2. Make the necessary changes to your document
3. Upload a new version for re-review
4. View detailed annotations at: {preview_link}

Please address all the points mentioned in the comments before resubmitting.

Best regards,
TuraVector Review Team'''
        elif decision == "rejected":
            version.stage_status = 3
            db.commit()
            document.stage_status = 3
            status_message, email_type = "rejected", "rejection_notification"
            subject = f"❌ Document Rejected: {document.document_name}"
            message = f'''Dear {owner_name},

Unfortunately, your document has been REJECTED by the reviewer.

📄 Document Details:
• Document: {document.document_name}
• Version: {version.version_number}
• Document Number: {document.document_number}
• Reviewed by: {reviewer_name}
• Status: ❌ REJECTED

💬 Rejection Reasons:
{comments}

📋 Next Steps:
1. Carefully review all feedback provided
2. Make substantial changes to address the issues
3. Consider consulting with the reviewer before resubmission
4. Upload a completely revised version when ready
5. View detailed annotations at: {preview_link}

Important: This document requires significant changes before it can be approved.

Best regards,
TuraVector Review Team'''

        db.commit()  # version.document.save()

        if subject is None:
            # Django hit an UnboundLocalError here for an unknown decision value.
            raise ValueError("local variable 'status_message' referenced before assignment")

        send_email_with_logging(db, subject, message, [owner.email], email_type,
                                from_email="noreply@turadome.com", sender_user=user, recipient_user=owner,
                                document=document, document_version=version)

        try:
            managers = list(db.execute(
                select(User).where(
                    or_(User.user_type == "manager", User.is_manager == 1, User.is_superuser == 1,
                        User.id.in_(org_admin_ids())),
                    User.id != user.id, User.id != owner.id,
                )
            ).scalars())
            if managers:
                manager_subject = f"📋 Review Completed: {document.document_name} - {status_message.upper()}"
                manager_message = f'''Review Notification for Managers,

A document review has been completed with the following details:

📄 Document Information:
• Document: {document.document_name}
• Version: {version.version_number}
• Document Number: {document.document_number}
• Owner: {owner_name} ({owner.email})
• Reviewer: {reviewer_name} ({user.email})
• Decision: {status_message.upper()}

💬 Review Comments:
{comments}

📊 Review Summary:
• Review Date: {format_datetime_for_user(utcnow(), user)}
• Document Status: {STAGE_LABELS.get(document.stage_status, document.stage_status)}

🔗 Quick Actions:
• View Document: {preview_link}
• View Mail Logs: {frontend_url('/documents/mail-logs/')}
• Reviewer Dashboard: {frontend_url('/content-lab-management/reviewer-dashboard/')}

This is an automated notification for review tracking purposes.

Best regards,
TuraVector System'''
                for manager in managers:
                    send_email_with_logging(db, manager_subject, manager_message, [manager.email], "general",
                                            from_email="noreply@turadome.com", sender_user=user,
                                            recipient_user=manager, document=document, document_version=version)
        except Exception as exc:  # noqa: BLE001
            log.error("Error sending manager notification emails: %s", exc)

        return {"level": "success", "message": f"Review submitted successfully. Document has been {status_message}.",
                "warnings": warnings}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {"level": "error", "message": f"Error submitting review: {exc}", "warnings": warnings}
