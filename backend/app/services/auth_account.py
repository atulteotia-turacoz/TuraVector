"""Business logic for the auth module — ports of authentication/views.py helpers
(signup, OTP password reset, timezone listing/statistics) and the Django
`timezone_tags` template tags.
"""
import datetime
import random
import string
import unicodedata

import pytz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import make_password
from app.models import OTPVerification, User, UserType, utcnow

# User.USER_TYPES (legacy static choices, used as the signup fallback list)
DEFAULT_USER_TYPES = [
    ("student", "Student"),
    ("teacher", "Teacher"),
    ("reviewer", "Reviewer"),
    ("manager", "Manager"),
]

OTP_FROM_EMAIL = "noreply@turadome.com"


def aware_str(dt: datetime.datetime | None) -> str:
    """str() of a Django aware datetime (USE_TZ=True, UTC): '2024-01-01 10:00:00.123456+00:00'."""
    if dt is None:
        return "None"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return str(dt)


# ---------------------------------------------------------------- signup
def signup_context(db: Session) -> dict:
    """get_signup_context(): active UserTypes ordered by name + the static fallback choices."""
    try:
        user_types = db.execute(
            select(UserType).where(UserType.is_active == 1).order_by(UserType.name)
        ).scalars().all()
    except Exception:  # noqa: BLE001 — Django swallowed errors here
        user_types = []
    # Only the self-service account types are offered; privileged types are given by an admin.
    from app.services.org_accounts import ORG_KINDS_FOR_SIGNUP, SIGNUP_USER_TYPES
    allowed = dict(SIGNUP_USER_TYPES)
    return {
        "user_types": [{"id": t.id, "code": t.code, "name": t.name} for t in user_types if t.code in allowed],
        "default_user_types": [{"value": k, "label": v} for k, v in SIGNUP_USER_TYPES],
        "organisation_kinds": [{"value": k, "label": v} for k, v in ORG_KINDS_FOR_SIGNUP],
    }


def normalize_email(email: str | None) -> str:
    """BaseUserManager.normalize_email — lowercase the domain part."""
    email = email or ""
    try:
        email_name, domain_part = email.strip().rsplit("@", 1)
    except ValueError:
        return email
    return email_name + "@" + domain_part.lower()


def normalize_username(username: str) -> str:
    """AbstractBaseUser.normalize_username — NFKC normalisation."""
    return unicodedata.normalize("NFKC", username) if isinstance(username, str) else username


def create_user(db: Session, *, username: str, email: str, first_name: str, last_name: str, password: str,
                phone: str, address: str, user_type: str) -> User:
    """User.objects.create_user(...) followed by the extra field assignments in signup_view."""
    default_user_type = None
    try:
        default_user_type = db.execute(
            select(UserType).where(UserType.code == "student", UserType.is_active == 1).order_by(UserType.name).limit(1)
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        pass

    user = User(
        username=normalize_username(username),
        email=normalize_email(email),
        first_name=first_name,
        last_name=last_name,
        password=make_password(password),
        is_superuser=0,
        is_staff=0,
        is_active=1,
        is_manager=0,
        timezone="UTC",
        user_type=user_type,
        phone=phone,
        address=address,
        date_joined=utcnow(),
        user_type_new_id=default_user_type.id if default_user_type else None,
    )
    db.add(user)
    db.commit()
    return user


# ---------------------------------------------------------------- OTP
def create_otp(db: Session, email: str) -> OTPVerification:
    """OTPVerification.objects.create(email=email) — 6 random digits, expires in 15 minutes."""
    otp = OTPVerification(
        email=email,
        otp_code="".join(random.choices(string.digits, k=6)),
        expires_at=utcnow() + datetime.timedelta(minutes=15),
        is_used=0,
    )
    db.add(otp)
    db.commit()
    return otp


def otp_is_valid(otp: OTPVerification) -> bool:
    return not otp.is_used and utcnow() < otp.expires_at


# ---------------------------------------------------------------- timezones
COMMON_TIMEZONES = [
    {"value": "UTC", "label": "UTC (Coordinated Universal Time)", "offset": "+00:00"},
    {"value": "Asia/Kolkata", "label": "India Standard Time (IST)", "offset": "+05:30"},
    {"value": "America/New_York", "label": "Eastern Time (US & Canada)", "offset": "-05:00"},
    {"value": "America/Chicago", "label": "Central Time (US & Canada)", "offset": "-06:00"},
    {"value": "America/Denver", "label": "Mountain Time (US & Canada)", "offset": "-07:00"},
    {"value": "America/Los_Angeles", "label": "Pacific Time (US & Canada)", "offset": "-08:00"},
    {"value": "Europe/London", "label": "Greenwich Mean Time (GMT)", "offset": "+00:00"},
    {"value": "Europe/Paris", "label": "Central European Time", "offset": "+01:00"},
    {"value": "Asia/Tokyo", "label": "Japan Standard Time", "offset": "+09:00"},
    {"value": "Asia/Shanghai", "label": "China Standard Time", "offset": "+08:00"},
    {"value": "Australia/Sydney", "label": "Australian Eastern Time", "offset": "+10:00"},
    {"value": "Asia/Dubai", "label": "Gulf Standard Time", "offset": "+04:00"},
    {"value": "Asia/Singapore", "label": "Singapore Standard Time", "offset": "+08:00"},
    {"value": "Asia/Bangkok", "label": "Indochina Time", "offset": "+07:00"},
    {"value": "Asia/Karachi", "label": "Pakistan Standard Time", "offset": "+05:00"},
    {"value": "Asia/Dhaka", "label": "Bangladesh Standard Time", "offset": "+06:00"},
]


def is_valid_timezone(name: str) -> bool:
    try:
        pytz.timezone(name)
        return True
    except pytz.exceptions.UnknownTimeZoneError:
        return False


def all_timezones() -> list[dict]:
    """Literal port of the `?all=true` branch (same pytz calls, same error skipping)."""
    result = []
    for tz in pytz.all_timezones:
        try:
            tz_obj = pytz.timezone(tz)
            now = datetime.datetime.now(datetime.timezone.utc)  # django.utils.timezone.now() (aware)
            offset = tz_obj.utcoffset(now)
            if offset:
                hours, remainder = divmod(int(offset.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                offset_str = f"{hours:+03d}:{minutes:02d}"
            else:
                offset_str = "+00:00"
            result.append({"value": tz, "label": tz.replace("_", " "), "offset": offset_str})
        except Exception:  # noqa: BLE001
            continue
    result.sort(key=lambda x: x["value"])
    return result


def timezone_stats(db: Session) -> dict:
    rows = db.execute(
        select(User.timezone, func.count(User.timezone).label("count"))
        .group_by(User.timezone).order_by(func.count(User.timezone).desc())
    ).all()
    total_users = db.execute(select(func.count(User.id))).scalar_one()
    stats = []
    for tz_name, count in rows:
        stats.append({
            "timezone": tz_name or "Not Set",
            "count": count,
            "percentage": round((count / total_users) * 100, 1) if total_users > 0 else 0,
        })
    return {"stats": stats, "total_users": total_users, "unique_timezones": len(stats)}


def active_timezone_info() -> dict:
    """{% current_timezone %} / {% timezone_offset %}.

    Django's TimezoneMiddleware is disabled in settings, so the active timezone is
    always settings.TIME_ZONE when these tags render.
    """
    tz = pytz.timezone(settings.TIME_ZONE)
    offset = tz.utcoffset(utcnow())
    if offset:
        total_seconds = int(offset.total_seconds())
        hours, remainder = divmod(abs(total_seconds), 3600)
        minutes, _ = divmod(remainder, 60)
        sign = "+" if total_seconds >= 0 else "-"
        offset_str = f"{sign}{hours:02d}:{minutes:02d}"
    else:
        offset_str = "+00:00"
    return {"current_timezone": str(tz), "timezone_offset": offset_str}
