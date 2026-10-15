"""Account endpoints — port of authentication/views.py (everything except login/logout,
which live in auth_core.py): signup, forgot password / OTP, test email, contact form,
profile update, change password, timezone APIs and the profile API.

Django returned `{'error': ...}` / `{'message': ...}` bodies with explicit status codes;
the same bodies and codes are returned here.
"""
import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.core.email as email_core
from app.config import settings
from app.core.deps import get_current_user, get_optional_user
from app.core.email import send_email_with_logging
from app.core.security import check_password, make_password, token_for
from app.database import get_db
from app.models import ContactQuery, OTPVerification, User, utcnow
from app.routers.auth_core import CONSENT_TEXT, create_login_log, record_user_consent, serialize_me
from app.schemas.auth_schemas import (
    ChangePasswordIn, ContactIn, EmailIn, SignupIn, TimezoneIn, UpdateProfileIn, VerifyOtpIn,
)
from app.services import auth_account as svc
from app.services import org_accounts
from app.services.org_common import add_membership, assign_default_role

log = logging.getLogger("turadome.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _err(message: str, status: int, **extra) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status)


def _get_one(db: Session, model, label: str, *conds):
    """Django `Model.objects.get(...)`: returns the row, None if missing; raises on duplicates."""
    rows = db.execute(select(model).where(*conds).limit(21)).scalars().all()
    if len(rows) > 1:
        raise RuntimeError(f"get() returned more than one {label} -- it returned {len(rows) if len(rows) < 21 else 'more than 20'}!")
    return rows[0] if rows else None


# ------------------------------------------------------------------ signup
@router.get("/signup-context")
def get_signup_context(db: Session = Depends(get_db)):
    return svc.signup_context(db)


def _validate_account(db: Session, body: SignupIn) -> JSONResponse | None:
    if not all([body.username, body.email, body.first_name, body.last_name, body.password, body.confirm_password]):
        return _err("All required fields must be filled.", 400)
    if not body.privacy_consent:
        return _err("You must consent to the processing of your personal data in accordance with the Privacy Policy.", 400)
    if body.password != body.confirm_password:
        return _err("Passwords do not match.", 400)
    if len(body.password) < 8:
        return _err("Password must be at least 8 characters long.", 400)
    if (body.user_type or "student") not in dict(org_accounts.SIGNUP_USER_TYPES):
        return _err("Invalid account type.", 400)
    if db.execute(select(User.id).where(User.username == body.username).limit(1)).first():
        return _err("Username already exists.", 400)
    if db.execute(select(User.id).where(User.email == body.email).limit(1)).first():
        return _err("Email already registered.", 400)
    return None


def _create_account(db: Session, body: SignupIn, request: Request) -> User:
    user = svc.create_user(db, username=body.username, email=body.email, first_name=body.first_name,
                           last_name=body.last_name, password=body.password, phone=body.phone or "",
                           address=body.address or "", user_type=body.user_type or "student")
    record_user_consent(db, user, request, consent_given=True, consent_type="privacy_policy",
                        consent_text=CONSENT_TEXT, consent_version="1.0")
    assign_default_role(db, user)
    return user


@router.post("/signup")
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)):
    """Individual sign-up (personal workspace, signed in at once) or a request to join a
    university/organisation with its join code (signed in once its admin approves)."""
    error = _validate_account(db, body)
    if error:
        return error
    joining = body.account_type == "join"
    try:
        org = org_accounts.find_joinable(db, body.join_code) if joining else None
    except org_accounts.SignupError as e:
        return _err(str(e), 400)

    try:
        user = _create_account(db, body, request)
        if joining:
            add_membership(db, org, user, role="member", status="pending")
        else:
            org_accounts.create_individual_workspace(db, user)
            create_login_log(db, request, user=user, username_attempted=user.username, status="success")
            user.last_login = utcnow()
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(f"Error creating account: {e}", 400)

    if joining:
        org_accounts.notify_join_request(db, org, user)
        return {"message": f"Your request to join {org.name} has been sent. You can sign in once its administrator "
                           "approves it.", "pending": True}
    return {
        "message": "Account created successfully! Welcome to TuraVector.",
        "access_token": token_for(user),
        "token_type": "bearer",
        "user": serialize_me(db, user),
    }


@router.post("/signup-organisation")
def signup_organisation(
    request: Request,
    organisation_name: str = Form(""),
    organisation_kind: str = Form("university"),
    website: str = Form(""),
    logo: UploadFile | None = File(None),
    username: str = Form(""), email: str = Form(""), first_name: str = Form(""), last_name: str = Form(""),
    password: str = Form(""), confirm_password: str = Form(""), phone: str = Form(""), address: str = Form(""),
    privacy_consent: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Register a university/organisation workspace; the person signing up becomes its admin.
    The workspace stays pending until a superadmin approves it."""
    body = SignupIn(username=username, email=email, first_name=first_name, last_name=last_name, password=password,
                    confirm_password=confirm_password, user_type="student", phone=phone, address=address,
                    privacy_consent=privacy_consent)
    organisation_name = organisation_name.strip()
    if not organisation_name:
        return _err("Enter the name of your university or organisation.", 400)
    if organisation_kind not in dict(org_accounts.ORG_KINDS_FOR_SIGNUP):
        return _err("Choose University or Organisation.", 400)
    error = _validate_account(db, body)
    if error:
        return error
    try:
        org_accounts.validate_logo(logo)
    except org_accounts.SignupError as e:
        return _err(str(e), 400)

    try:
        user = _create_account(db, body, request)
        org = org_accounts.create_pending_organisation(db, user, name=organisation_name, kind=organisation_kind,
                                                       website=website.strip(), logo=logo)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(f"Error creating account: {e}", 400)

    org_accounts.notify_new_organisation(db, org, user)
    return {"message": f"{org.name} has been registered. We will email you once it is approved — you can sign in "
                       "after that.", "pending": True}


# ------------------------------------------------------------------ password reset
@router.post("/forgot-password")
def forgot_password(body: EmailIn, db: Session = Depends(get_db)):
    try:
        email = body.email
        if not email:
            return _err("Email is required", 400)
        user = _get_one(db, User, "User", User.email == email)
        if user is None:
            return _err("User with this email does not exist", 404)

        otp = svc.create_otp(db, email)

        subject = 'Password Reset OTP - TuraVector'
        message = f'''
        Hello {user.first_name},

        Your OTP for password reset is: {otp.otp_code}
        This OTP will expire in 15 minutes.

        If you didn't request this, please ignore this email.

        Best regards,
        TuraVector Team
        '''
        try:
            success, email_log = send_email_with_logging(
                db, subject, message, [email], "password_reset",
                from_email=svc.OTP_FROM_EMAIL, recipient_user=user,
            )
            if not success:
                return _err("Failed to send email. Please contact administrator.", 500,
                            log_id=email_log.id if email_log else None)
        except Exception as email_error:  # noqa: BLE001
            return _err("Email service temporarily unavailable. Please try again later.", 500,
                        details=str(email_error) if settings.DEBUG else None)

        return {
            "message": "OTP sent to your email. Please check your inbox and spam folder.",
            "email": email,
            "expires_in": "15 minutes",
        }
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


@router.post("/test-email")
def test_email(body: EmailIn, db: Session = Depends(get_db)):
    try:
        to = body.email
        if not to:
            return _err("Email is required", 400)
        subject = 'TuraVector Email Test'
        message = '''
        Hello,

        This is a test email to verify that your email configuration is working correctly.

        If you received this email, the email system is functioning properly.

        Best regards,
        TuraVector Team
        '''
        try:
            success, email_log = send_email_with_logging(
                db, subject, message, [to], "test", from_email="noreply@turadome.com", recipient_user=None,
            )
            if success:
                return {"message": f"Test email sent successfully to {to}", "log_id": email_log.id,
                        "method": "advanced_email_system"}
            return _err("Failed to send test email", 500, log_id=email_log.id if email_log else None,
                        method="advanced_email_system")
        except Exception as email_error:  # noqa: BLE001
            return _err("Failed to send test email", 500, details=str(email_error), method="advanced_email_system")
    except Exception as e:  # noqa: BLE001
        return _err(str(e), 500)


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpIn, db: Session = Depends(get_db)):
    try:
        email, otp_code, new_password = body.email, body.otp, body.new_password
        if not all([email, otp_code, new_password]):
            return _err("All fields are required", 400)
        otp = _get_one(db, OTPVerification, "OTPVerification", OTPVerification.email == email,
                       OTPVerification.otp_code == otp_code, OTPVerification.is_used == 0)
        if otp is None:
            return _err("Invalid OTP", 400)
        if not svc.otp_is_valid(otp):
            return _err("OTP has expired", 400)

        user = _get_one(db, User, "User", User.email == email)
        if user is None:
            raise RuntimeError("User matching query does not exist.")
        user.password = make_password(new_password)
        db.commit()

        otp.is_used = 1
        db.commit()
        return {"message": "Password updated successfully"}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


# ------------------------------------------------------------------ contact form
@router.post("/contact")
def contact_form(body: ContactIn, db: Session = Depends(get_db)):
    try:
        name, email, subject, message = body.name, body.email, body.subject, body.message
        if not all([name, email, subject, message]):
            return _err("All fields are required", 400)

        contact_query = ContactQuery(name=name, email=email, subject=subject, message=message, is_resolved=0)
        db.add(contact_query)
        db.commit()

        admin_subject = f'New Contact Form Submission: {subject}'
        admin_message = f'''
        New contact form submission:

        Name: {name}
        Email: {email}
        Subject: {subject}
        Message: {message}

        Submitted at: {svc.aware_str(contact_query.created_at)}
        '''
        # django send_mail(..., fail_silently=False): errors propagate to the 500 handler below
        email_core.deliver(db, admin_subject, admin_message, "noreply@turadome.com", "admin@turadome.com")

        return {"message": "Thank you for your message. We will get back to you soon."}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


# ------------------------------------------------------------------ profile
@router.post("/update-profile")
def update_profile(body: UpdateProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        for field in ("first_name", "last_name", "email", "phone", "address"):
            if field in body.model_fields_set:
                setattr(user, field, getattr(body, field))
        db.commit()
        return {"message": "Profile updated successfully"}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        current_password, new_password = body.current_password, body.new_password
        if not current_password or not new_password:
            return _err("Current password and new password are required", 400)
        if not check_password(current_password, user.password):
            return _err("Current password is incorrect", 400)
        if len(new_password) < 8:
            return _err("New password must be at least 8 characters long", 400)
        user.password = make_password(new_password)
        db.commit()
        return {"message": "Password changed successfully"}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


@router.get("/profile")
def profile_api(user: User = Depends(get_current_user)):
    """profile_api_view — datetimes rendered with str() exactly as Django did."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "user_type": user.user_type or "student",
        "timezone": user.timezone,
        "is_active": bool(user.is_active),
        "date_joined": svc.aware_str(user.date_joined) if user.date_joined else None,
        "last_login": svc.aware_str(user.last_login) if user.last_login else None,
    }


# ------------------------------------------------------------------ timezones
@router.post("/set-timezone")
def set_timezone(body: TimezoneIn, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    try:
        tz = body.timezone
        if not tz:
            return _err("Timezone is required", 400)
        if not svc.is_valid_timezone(tz):
            return _err("Invalid timezone", 400)
        if user is not None:
            user.timezone = tz
            db.commit()
        return {"message": "Timezone updated successfully", "timezone": tz}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return _err(str(e), 500)


@router.post("/detect-timezone")
def detect_timezone(body: TimezoneIn):
    """Anonymous detection — Django kept it in the session; the client keeps it in sessionStorage."""
    tz = body.timezone
    if not tz:
        return _err("Timezone is required", 400)
    if not svc.is_valid_timezone(tz):
        return _err("Invalid timezone", 400)
    return {"message": "Timezone detected successfully", "timezone": tz}


@router.get("/timezones")
def get_timezones(all: str | None = None):  # noqa: A002 — query param name from Django
    try:
        if all == "true":
            return {"timezones": svc.all_timezones()}
        return {"timezones": svc.COMMON_TIMEZONES}
    except Exception as e:  # noqa: BLE001
        return _err(str(e), 500)


@router.get("/timezone-info")
def timezone_info():
    """Values of the {% current_timezone %} / {% timezone_offset %} tags used by timezone_selector.html."""
    return svc.active_timezone_info()


@router.get("/admin/timezone-stats")
def timezone_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_staff:
        return _err("Permission denied", 403)
    try:
        return svc.timezone_stats(db)
    except Exception as e:  # noqa: BLE001
        return _err(str(e), 500)
