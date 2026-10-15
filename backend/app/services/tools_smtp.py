"""SMTPSettings helpers — port of documents.models.SMTPSettings.test_connection and the
create/update logic of smtp_settings_add_view / smtp_settings_edit_view.

`test_connection` talks to the configured SMTP server with smtplib exactly like Django's
EmailBackend would with the overridden EMAIL_* settings. Tests must monkeypatch
`tools_smtp.smtplib` — never call it against the real server.
"""
import datetime
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import SMTPSettings, User, utcnow


class _Form:
    """Tiny stand-in for request.POST (`get(key, default)` with Django's semantics: a missing key → default)."""

    def __init__(self, data: dict):
        self.data = data

    def get(self, key, default=None):
        return self.data[key] if key in self.data else default


def _open_connection(cfg: SMTPSettings):
    """django.core.mail.backends.smtp.EmailBackend.open() with the config's settings."""
    use_tls, use_ssl = bool(cfg.use_tls), bool(cfg.use_ssl)
    if use_tls and use_ssl:
        raise ValueError(
            "EMAIL_USE_TLS/EMAIL_USE_SSL are mutually exclusive, so only set one of those settings to True."
        )
    if use_ssl:
        conn = smtplib.SMTP_SSL(cfg.host, cfg.port, context=ssl.create_default_context(), timeout=30)
    else:
        conn = smtplib.SMTP(cfg.host, cfg.port, timeout=30)
        if use_tls:
            conn.starttls(context=ssl.create_default_context())
    if cfg.username and cfg.password:
        conn.login(cfg.username, cfg.password)
    return conn


def test_connection(db: Session, cfg: SMTPSettings) -> tuple[bool, str]:
    """SMTPSettings.test_connection(): send a test email (or just connect) and record the result."""
    try:
        if cfg.test_email:
            body = f'''This is a test email from TuraVector Document Management System.

SMTP Configuration Details:
- Host: {cfg.host}
- Port: {cfg.port}
- Username: {cfg.username}
- TLS: {bool(cfg.use_tls)}
- SSL: {bool(cfg.use_ssl)}

If you received this email, your SMTP configuration is working correctly.

Test performed at: {datetime.datetime.now(datetime.timezone.utc)}'''
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = "SMTP Configuration Test"
            msg["From"] = cfg.from_email
            msg["To"] = cfg.test_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid()
            conn = _open_connection(cfg)
            try:
                conn.sendmail(cfg.from_email, [cfg.test_email], msg.as_bytes())
            finally:
                try:
                    conn.quit()
                except Exception:  # noqa: BLE001
                    pass
            result_message = f"Test email sent successfully to {cfg.test_email}"
        else:
            conn = _open_connection(cfg)
            try:
                conn.quit()
            except Exception:  # noqa: BLE001
                pass
            result_message = "SMTP connection test successful (no email sent)"

        cfg.is_tested = 1
        cfg.last_tested = utcnow()
        cfg.test_result = result_message
        db.commit()
        return True, result_message
    except Exception as e:  # noqa: BLE001
        error_message = f"SMTP test failed: {str(e)}"
        cfg.is_tested = 0
        cfg.last_tested = utcnow()
        cfg.test_result = error_message
        db.commit()
        return False, error_message


def _int(value) -> int:
    return int(value)


def create_settings(db: Session, user: User, data: dict) -> SMTPSettings:
    """smtp_settings_add_view, action=create. Raises on invalid input (caller formats the message)."""
    POST = _Form(data)
    if POST.get('is_active') == 'on':
        db.execute(update(SMTPSettings).where(SMTPSettings.is_active == 1).values(is_active=0))
    cfg = SMTPSettings(
        host=POST.get('host'),
        port=_int(POST.get('port', 587)),
        username=POST.get('username'),
        password=POST.get('password'),
        use_tls=int(POST.get('use_tls') == 'on'),
        use_ssl=int(POST.get('use_ssl') == 'on'),
        from_email=POST.get('from_email'),
        from_name=POST.get('from_name'),
        display_name=POST.get('display_name', POST.get('from_name')),
        protocol=POST.get('protocol', 'smtp'),
        smtp_host=POST.get('smtp_host') or POST.get('host'),
        smtp_user=POST.get('smtp_user') or POST.get('username'),
        smtp_pass=POST.get('smtp_pass') or POST.get('password'),
        smtp_crypto=POST.get('smtp_crypto', 'tls'),
        smtp_port=_int(POST.get('smtp_port', 0)) if POST.get('smtp_port') else _int(POST.get('port', 587)),
        mailtype=POST.get('mailtype', 'html'),
        charset=POST.get('charset', 'utf-8'),
        encoding=POST.get('encoding', '8bit'),
        crlf=POST.get('crlf', '\\r\\n'),
        newline=POST.get('newline', '\\r\\n'),
        wordwrap=int(POST.get('wordwrap') == 'on'),
        test_email=POST.get('test_email') or None,
        is_active=int(POST.get('is_active') == 'on'),
        status=POST.get('status', 'active'),
        is_tested=0,
        last_tested=None,
        test_result=None,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(cfg)
    db.flush()
    return cfg


def update_settings(db: Session, user: User, cfg: SMTPSettings, data: dict) -> SMTPSettings:
    """smtp_settings_edit_view, action=update."""
    POST = _Form(data)
    if POST.get('is_active') == 'on':
        db.execute(update(SMTPSettings).where(SMTPSettings.is_active == 1, SMTPSettings.id != cfg.id)
                   .values(is_active=0))
    cfg.host = POST.get('host')
    cfg.port = _int(POST.get('port', 587))
    cfg.username = POST.get('username')
    password = POST.get('password')
    if password:
        cfg.password = password
    cfg.use_tls = int(POST.get('use_tls') == 'on')
    cfg.use_ssl = int(POST.get('use_ssl') == 'on')
    cfg.from_email = POST.get('from_email')
    cfg.from_name = POST.get('from_name')
    cfg.display_name = POST.get('display_name', POST.get('from_name'))
    cfg.protocol = POST.get('protocol', 'smtp')
    cfg.smtp_host = POST.get('smtp_host') or POST.get('host')
    cfg.smtp_user = POST.get('smtp_user') or POST.get('username')
    if POST.get('smtp_pass'):
        cfg.smtp_pass = POST.get('smtp_pass')
    cfg.smtp_crypto = POST.get('smtp_crypto', 'tls')
    cfg.smtp_port = _int(POST.get('smtp_port', 0)) if POST.get('smtp_port') else _int(POST.get('port', 587))
    cfg.mailtype = POST.get('mailtype', 'html')
    cfg.charset = POST.get('charset', 'utf-8')
    cfg.encoding = POST.get('encoding', '8bit')
    cfg.crlf = POST.get('crlf', '\\r\\n')
    cfg.newline = POST.get('newline', '\\r\\n')
    cfg.wordwrap = int(POST.get('wordwrap') == 'on')
    cfg.test_email = POST.get('test_email') or None
    cfg.is_active = int(POST.get('is_active') == 'on')
    cfg.status = POST.get('status', 'active')
    cfg.updated_by_id = user.id
    db.flush()
    return cfg
