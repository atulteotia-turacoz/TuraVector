"""Email sending with EmailLog bookkeeping — port of documents.views.send_email_with_logging."""
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EmailLog, SMTPSettings, utcnow

log = logging.getLogger("turadome.email")


def _mark_sent(db: Session, email_log: EmailLog) -> None:
    email_log.status = "sent"
    email_log.sent_at = utcnow()
    db.commit()


def _mark_failed(db: Session, email_log: EmailLog, error: str) -> None:
    email_log.status = "failed"
    email_log.error_message = error
    email_log.retry_count = (email_log.retry_count or 0) + 1
    db.commit()


def can_retry(email_log: EmailLog) -> bool:
    """EmailLog.can_retry — max 3 attempts."""
    return (email_log.retry_count or 0) < 3 and email_log.status in ("failed", "error")


def deliver(db: Session, subject: str, message: str, from_email: str, to: str, html: str | None = None) -> None:
    """Send one message using the active SMTPSettings row, or the .env fallback. Raises on failure."""
    if settings.EMAIL_REDIRECT_TO:  # testing: nobody but the tester receives anything
        subject, to = f"[TEST · for {to}] {subject}", settings.EMAIL_REDIRECT_TO
    smtp_config = db.execute(select(SMTPSettings).where(SMTPSettings.is_active == 1).limit(1)).scalar_one_or_none()
    msg = MIMEMultipart("alternative") if html else MIMEMultipart()
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(message, "plain"))
    if html:
        msg.attach(MIMEText(html, "html"))

    if smtp_config:
        sender_name = (getattr(smtp_config, "display_name", "") or getattr(smtp_config, "from_name", "") or "").strip()
        sender = smtp_config.from_email or from_email
        msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        server = smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=30)
        try:
            server.starttls(context=context)
            server.login(smtp_config.username, smtp_config.password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
        return

    msg["From"] = from_email
    if settings.EMAIL_BACKEND == "console":
        log.warning("[console email] To: %s | Subject: %s\n%s", to, subject, message)
        return
    server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=30)
    try:
        if settings.EMAIL_USE_TLS:
            server.starttls(context=ssl.create_default_context())
        if settings.EMAIL_HOST_USER:
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        server.send_message(msg)
    finally:
        server.quit()


def send_email_with_logging(
    db: Session,
    subject: str,
    message: str,
    recipient_list: list[str],
    email_type: str,
    from_email: str | None = None,
    sender_user=None,
    recipient_user=None,
    document=None,
    document_version=None,
    html: str | None = None,
) -> tuple[bool, EmailLog]:
    """Create an EmailLog row, send, and mark it sent/failed. Returns (success, email_log)."""
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    recipient_email = recipient_list[0] if recipient_list else ""
    email_log = EmailLog(
        email_type=email_type,
        recipient_email=recipient_email,
        recipient_user_id=getattr(recipient_user, "id", None),
        sender_user_id=getattr(sender_user, "id", None),
        subject=subject,
        message_content=message,
        document_id=getattr(document, "id", None),
        document_version_id=getattr(document_version, "id", None),
        from_email=from_email,
        status="pending",
        retry_count=0,
    )
    db.add(email_log)
    db.commit()
    try:
        deliver(db, subject, message, from_email, recipient_email, html=html)
        _mark_sent(db, email_log)
        return True, email_log
    except Exception as exc:  # noqa: BLE001 — any SMTP failure is logged, not raised
        _mark_failed(db, email_log, str(exc))
        log.error("Failed to send email to %s: %s (log %s)", recipient_email, exc, email_log.id)
        return False, email_log


def send_plain_email(db: Session, subject: str, message: str, to: list[str], from_email: str | None = None,
                     html: str | None = None) -> bool:
    """Equivalent of django.core.mail.send_mail (no EmailLog row). Returns success."""
    try:
        for addr in to:
            deliver(db, subject, message, from_email or settings.DEFAULT_FROM_EMAIL, addr, html=html)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("send_plain_email failed: %s", exc)
        return False
