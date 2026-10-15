"""Small helpers shared by routers (port of turadome_django/utils.py and common view helpers)."""
import datetime
import math
from typing import Any

import pytz
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User


def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "127.0.0.1"


def get_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")[:500]


def user_tz(user: User | None):
    if user is not None and getattr(user, "timezone", None):
        try:
            return pytz.timezone(user.timezone)
        except pytz.UnknownTimeZoneError:
            pass
    return pytz.timezone(settings.TIME_ZONE)


def localize_datetime(dt: datetime.datetime | None, user: User | None = None):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(user_tz(user))


def format_datetime_for_user(dt, user=None, fmt: str = "%B %d, %Y at %I:%M %p") -> str:
    local = localize_datetime(dt, user)
    return local.strftime(fmt) if local else ""


def iso(dt: datetime.datetime | datetime.date | None) -> str | None:
    """Serialise a DB datetime (naive UTC) as ISO-8601 with an explicit Z so the browser localises it."""
    if dt is None:
        return None
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return dt.isoformat()


def time_ago(dt: datetime.datetime | None) -> str:
    """Port of documents.views.get_time_ago / format_time_ago."""
    if dt is None:
        return ""
    now = datetime.datetime.utcnow()
    diff = now - dt.replace(tzinfo=None)
    seconds = diff.total_seconds()
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        m = int(seconds // 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = int(seconds // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if diff.days < 7:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    return dt.strftime("%b %d, %Y")


def full_name(user: User | None) -> str:
    if user is None:
        return ""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or user.username


def user_brief(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": full_name(user),
    }


def user_type_display(user: User) -> str:
    """User.get_user_type_display — dynamic type first, then legacy choices."""
    if user.user_type_new is not None:
        return user.user_type_new.name
    return {"student": "Student", "teacher": "Teacher", "reviewer": "Reviewer", "manager": "Manager"}.get(
        user.user_type, user.user_type
    )


def user_type_code(user: User) -> str:
    return user.user_type_new.code if user.user_type_new is not None else user.user_type


def paginate(db: Session, stmt, page: int = 1, page_size: int = 25) -> dict[str, Any]:
    """Run a select() with LIMIT/OFFSET and return {items, total, page, page_size, pages}."""
    page = max(1, page)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    items = db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().unique().all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)) if page_size else 1,
    }
