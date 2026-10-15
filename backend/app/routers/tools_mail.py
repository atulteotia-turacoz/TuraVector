"""Mail logs and SMTP settings.

Port of documents.views.mail_logs_view, email_log_detail_view, get_email_log_details,
retry_email, smtp_settings_view (list + delete), smtp_settings_add_view,
smtp_settings_edit_view and test_smtp_api.
"""
import datetime
import math

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.core.email import can_retry, send_email_with_logging
from app.core.permissions import has_module_permission
from app.core.utils import format_datetime_for_user, iso, user_tz
from app.database import get_db
from app.models import EmailLog, SMTPSettings, User
from app.services import tools_smtp

router = APIRouter(prefix="/api/tools", tags=["tools"])

EMAIL_TYPES = [
    ('revision_request', 'Revision Request'),
    ('approval_notification', 'Approval Notification'),
    ('rejection_notification', 'Rejection Notification'),
    ('support_request', 'Support Request'),
    ('review_assignment', 'Review Assignment'),
    ('review_started', 'Review Started'),
    ('general', 'General'),
]
STATUS_CHOICES = [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('error', 'Error')]
_TYPE_DISPLAY = dict(EMAIL_TYPES)
_STATUS_DISPLAY = dict(STATUS_CHOICES)


def _user_name(u: User | None) -> str | None:
    if u is None:
        return None
    return f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username


def _log_row(e: EmailLog) -> dict:
    return {
        'id': e.id,
        'email_type': e.email_type,
        'email_type_display': _TYPE_DISPLAY.get(e.email_type, e.email_type),
        'status': e.status,
        'status_display': _STATUS_DISPLAY.get(e.status, e.status),
        'recipient_email': e.recipient_email,
        'recipient_user': _user_name(e.recipient_user),
        'sender_user': _user_name(e.sender_user),
        'from_email': e.from_email,
        'subject': e.subject,
        'document': {'document_number': e.document.document_number, 'document_name': e.document.document_name}
        if e.document else None,
        'document_version': e.document_version.version_number if e.document_version else None,
        'retry_count': e.retry_count,
        'can_retry': can_retry(e),
        'sent_at': iso(e.sent_at),
        'created_at': iso(e.created_at),
    }


def _parse_date(value: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f'“{value}” value has an invalid date format. It must be in YYYY-MM-DD format.')


@router.get('/mail-logs')
def mail_logs(email_type: str = '', status: str = '', search: str = '', date_from: str = '', date_to: str = '',
              page: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_module_permission(db, user, 'content_lab', 'cl_mail_logs', 'view'):
        raise HTTPException(403, 'You do not have permission to view mail logs')

    stmt = select(EmailLog).options(
        joinedload(EmailLog.recipient_user), joinedload(EmailLog.sender_user),
        joinedload(EmailLog.document), joinedload(EmailLog.document_version),
    )
    if email_type:
        stmt = stmt.where(EmailLog.email_type == email_type)
    if status:
        stmt = stmt.where(EmailLog.status == status)
    if search:
        like = f'%{search}%'
        stmt = stmt.outerjoin(User, EmailLog.recipient_user_id == User.id).where(or_(
            EmailLog.recipient_email.ilike(like), EmailLog.subject.ilike(like), User.username.ilike(like)))
    # created_at__date uses the project time zone (USE_TZ) — compare on the UTC range of that local day
    if date_from:
        stmt = stmt.where(EmailLog.created_at >= _local_day_start_utc(_parse_date(date_from), user))
    if date_to:
        stmt = stmt.where(EmailLog.created_at < _local_day_start_utc(_parse_date(date_to) + datetime.timedelta(days=1), user))
    stmt = stmt.order_by(EmailLog.created_at.desc())

    # Paginator(…, 25).get_page(page): invalid → 1, out of range → last
    per_page = 25
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    num_pages = max(1, math.ceil(total / per_page))
    try:
        number = int(page) if page else 1
    except ValueError:
        number = 1
    if number < 1 or number > num_pages:
        number = num_pages
    rows = db.execute(stmt.limit(per_page).offset((number - 1) * per_page)).unique().scalars().all()

    count = lambda *conds: db.execute(select(func.count(EmailLog.id)).where(*conds)).scalar_one()  # noqa: E731
    return {
        'page_title': 'Email Logs',
        'items': [_log_row(e) for e in rows],
        'total': total,
        'page': number,
        'pages': num_pages,
        'email_types': [{'value': v, 'label': lbl} for v, lbl in EMAIL_TYPES],
        'status_choices': [{'value': v, 'label': lbl} for v, lbl in STATUS_CHOICES],
        'filters': {'email_type': email_type, 'status': status, 'search': search,
                    'date_from': date_from, 'date_to': date_to},
        'stats': {
            'total': count(),
            'sent': count(EmailLog.status == 'sent'),
            'failed': count(EmailLog.status == 'failed'),
            'pending': count(EmailLog.status == 'pending'),
        },
    }


def _local_day_start_utc(day: datetime.date, user: User) -> datetime.datetime:
    import pytz
    tz = user_tz(user)  # TimezoneMiddleware activated the user's zone
    local = tz.localize(datetime.datetime.combine(day, datetime.time.min))
    return local.astimezone(pytz.UTC).replace(tzinfo=None)


def _detail(e: EmailLog) -> dict:
    d = _log_row(e)
    d['message_content'] = e.message_content
    d['error_message'] = e.error_message
    return d


@router.get('/mail-logs/{email_log_id}')
def email_log_detail(email_log_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """email_log_detail_view"""
    if not has_module_permission(db, user, 'content_lab', 'cl_mail_logs', 'view'):
        raise HTTPException(403, 'You do not have permission to view email details')
    e = db.get(EmailLog, email_log_id)
    if e is None:
        raise HTTPException(404, 'Not found')
    return {'page_title': 'Email Details', 'email_log': _detail(e)}


@router.get('/email-log/{email_log_id}')
def get_email_log_details(email_log_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """get_email_log_details (DRF API; IsAuthenticated only) — same payload as Django."""
    e = db.get(EmailLog, email_log_id)
    if e is None:
        raise HTTPException(404, 'Not found.')
    fmt = '%b %d, %Y %H:%M:%S'
    data = {
        'id': e.id,
        'email_type': e.email_type,
        'email_type_display': _TYPE_DISPLAY.get(e.email_type, e.email_type),
        'status': e.status,
        'status_display': _STATUS_DISPLAY.get(e.status, e.status),
        'recipient_email': e.recipient_email,
        'from_email': e.from_email,
        'subject': e.subject,
        'message_content': e.message_content,
        'error_message': e.error_message,
        'retry_count': e.retry_count,
        'created_at': format_datetime_for_user(e.created_at, user, fmt),
        'sent_at': format_datetime_for_user(e.sent_at, user, fmt) if e.sent_at else None,
    }
    if e.recipient_user:
        data['recipient_user'] = _user_name(e.recipient_user)
    if e.sender_user:
        data['sender_user'] = _user_name(e.sender_user)
    if e.document:
        data['document'] = {'document_number': e.document.document_number, 'document_name': e.document.document_name}
        if e.document_version:
            data['document_version'] = e.document_version.version_number
    return data


@router.post('/mail-logs/{email_log_id}/retry')
def retry_email(email_log_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_module_permission(db, user, 'content_lab', 'cl_mail_logs', 'edit'):
        return JSONResponse({'error': 'Permission denied'}, status_code=403)
    email_log = db.get(EmailLog, email_log_id)
    if email_log is None:
        raise HTTPException(404, 'Not found')
    try:
        if not can_retry(email_log):
            return JSONResponse({'error': 'Email cannot be retried (max attempts reached or already sent)'},
                                status_code=400)
        success, updated_log = send_email_with_logging(
            db,
            subject=email_log.subject,
            message=email_log.message_content,
            from_email=email_log.from_email,
            recipient_list=[email_log.recipient_email],
            email_type=email_log.email_type,
            sender_user=email_log.sender_user,
            recipient_user=email_log.recipient_user,
            document=email_log.document,
            document_version=email_log.document_version,
        )
        if success:
            # Delete the old failed entry to avoid duplicates
            db.delete(email_log)
            db.commit()
            return {'message': 'Email retried successfully', 'status': 'sent'}
        return JSONResponse({'message': 'Email retry failed', 'error': updated_log.error_message}, status_code=500)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return JSONResponse({'error': str(e)}, status_code=500)


# ====================================================================== SMTP settings
def _smtp_row(c: SMTPSettings, include_secret: bool = False) -> dict:
    d = {
        'id': c.id, 'host': c.host, 'port': c.port, 'username': c.username,
        'use_tls': bool(c.use_tls), 'use_ssl': bool(c.use_ssl),
        'from_email': c.from_email, 'from_name': c.from_name, 'display_name': c.display_name,
        'protocol': c.protocol, 'smtp_host': c.smtp_host, 'smtp_user': c.smtp_user,
        'smtp_crypto': c.smtp_crypto, 'smtp_port': c.smtp_port, 'mailtype': c.mailtype,
        'charset': c.charset, 'encoding': c.encoding, 'crlf': c.crlf, 'newline': c.newline,
        'wordwrap': bool(c.wordwrap), 'test_email': c.test_email, 'is_active': bool(c.is_active),
        'status': c.status, 'is_tested': bool(c.is_tested), 'last_tested': iso(c.last_tested),
        'test_result': c.test_result, 'created_at': iso(c.created_at), 'updated_at': iso(c.updated_at),
    }
    if include_secret:
        # Django pre-filled the stored password; we only say whether one is set.
        # Submitting the form with the field blank keeps the current password.
        d['has_password'] = bool(c.password)
    return d


def _require(db: Session, user: User, action: str, message: str) -> None:
    if not has_module_permission(db, user, 'content_lab', 'cl_email_settings', action):
        raise HTTPException(403, message)


@router.get('/smtp-settings')
def smtp_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require(db, user, 'view', 'You do not have permission to view SMTP settings')
    configs = db.execute(select(SMTPSettings).order_by(SMTPSettings.created_at.desc())).scalars().all()
    active = next((c for c in configs if c.is_active), None)
    return {
        'page_title': 'SMTP Settings',
        'smtp_configurations': [_smtp_row(c) for c in configs],
        'active_config': _smtp_row(active) if active else None,
    }


@router.post('/smtp-settings/{smtp_id}/delete')
def smtp_settings_delete(smtp_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """smtp_settings_view POST action=delete"""
    _require(db, user, 'view', 'You do not have permission to view SMTP settings')
    cfg = db.get(SMTPSettings, smtp_id)
    if cfg is None:
        raise HTTPException(400, 'Failed to delete SMTP settings: No SMTPSettings matches the given query.')
    try:
        db.delete(cfg)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f'Failed to delete SMTP settings: {str(e)}')
    return {'message': 'SMTP settings deleted successfully'}


async def _form_dict(request: Request) -> dict:
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}


@router.post('/smtp-settings')
async def smtp_settings_add(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require(db, user, 'create', 'You do not have permission to access this page.')
    data = await _form_dict(request)
    if data.get('action') != 'create':
        return {'message': None}
    try:
        cfg = tools_smtp.create_settings(db, user, data)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f'Failed to create SMTP settings: {_err(e)}')
    return {'message': 'SMTP settings created successfully', 'id': cfg.id}


@router.get('/smtp-settings/{smtp_id}')
def smtp_settings_get(smtp_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require(db, user, 'edit', 'You do not have permission to access this page.')
    cfg = db.get(SMTPSettings, smtp_id)
    if cfg is None:
        raise HTTPException(404, 'Not found')
    return {'page_title': 'Edit SMTP Configuration', 'smtp_config': _smtp_row(cfg, include_secret=True)}


@router.post('/smtp-settings/{smtp_id}')
async def smtp_settings_edit(smtp_id: int, request: Request, user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    _require(db, user, 'edit', 'You do not have permission to access this page.')
    cfg = db.get(SMTPSettings, smtp_id)
    if cfg is None:
        raise HTTPException(404, 'Not found')
    data = await _form_dict(request)
    if data.get('action') != 'update':
        return {'message': None}
    try:
        tools_smtp.update_settings(db, user, cfg, data)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f'Failed to update SMTP settings: {_err(e)}')
    return {'message': 'SMTP settings updated successfully'}


@router.post('/smtp-settings/{smtp_id}/test')
def test_smtp(smtp_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not has_module_permission(db, user, 'content_lab', 'cl_email_settings', 'edit'):
        return JSONResponse({'error': 'Permission denied'}, status_code=403)
    cfg = db.get(SMTPSettings, smtp_id)
    if cfg is None:
        return JSONResponse({'error': 'No SMTPSettings matches the given query.'}, status_code=500)
    try:
        success, message = tools_smtp.test_connection(db, cfg)
        return {
            'success': success,
            'message': message,
            'tested_at': format_datetime_for_user(cfg.last_tested, user) if cfg.last_tested else None,
        }
    except Exception as e:  # noqa: BLE001
        return JSONResponse({'error': str(e)}, status_code=500)


def _err(e: Exception) -> str:
    orig = getattr(e, 'orig', None)
    return str(orig) if orig is not None else str(e)
