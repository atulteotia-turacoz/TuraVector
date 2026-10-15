"""Non-generic admin views: UserAdmin add/password forms, DocumentVersion "change file",
and the timezone management page.

Password validation is a port of the four AUTH_PASSWORD_VALIDATORS configured in
turadome_django/settings.py (UserAttributeSimilarity, MinimumLength(8), CommonPassword,
NumericPassword); the common-password list is Django's own file.
"""
from __future__ import annotations

import datetime
import gzip
import json
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import pytz
from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, select, update

from app.config import settings
from app.core import files as files_core
from app.core.security import make_password, make_unusable_password
from app.core.utils import iso
from app.models import Base, utcnow
from app.services import superadmin_core as core

USERNAME_RE = re.compile(r"^[\w.@+-]+\Z")
_COMMON_FILE = Path(__file__).with_name("superadmin_common_passwords.txt.gz")
USER_LABEL = "authentication.User"
VERSION_LABEL = "documents.DocumentVersion"


# =============================================================================== password validation
@lru_cache
def _common_passwords() -> frozenset[str]:
    try:
        with gzip.open(_COMMON_FILE, "rt", encoding="utf-8") as fh:
            return frozenset(x.strip() for x in fh)
    except OSError:
        return frozenset()


def _exceeds_maximum_length_ratio(password: str, max_similarity: float, value: str) -> bool:
    pwd_len = len(password)
    length_bound_similarity = max_similarity / 2 * pwd_len
    value_len = len(value)
    return pwd_len >= 10 * value_len and value_len < length_bound_similarity


def validate_password(password: str, user: dict | None) -> list[str]:
    """django.contrib.auth.password_validation.validate_password with the project's validators."""
    errors: list[str] = []
    if user:
        pw = password.lower()
        fields = core.MODELS[USER_LABEL]["fields"]
        done = False
        for attr in ("username", "first_name", "last_name", "email"):
            value = user.get(attr)
            if not value or not isinstance(value, str) or done:
                continue
            vl = value.lower()
            for part in re.split(r"\W+", vl) + [vl]:
                if _exceeds_maximum_length_ratio(pw, 0.7, part):
                    continue
                if SequenceMatcher(a=pw, b=part).quick_ratio() >= 0.7:
                    errors.append(f"The password is too similar to the {fields[attr]['verbose_name']}.")
                    done = True
                    break
    if len(password) < 8:
        errors.append("This password is too short. It must contain at least 8 characters.")
    if password.lower().strip() in _common_passwords():
        errors.append("This password is too common.")
    if password.isdigit():
        errors.append("This password is entirely numeric.")
    return errors


def _password_pair(data: dict, user: dict | None, errors: dict) -> str | None:
    """SetPasswordMixin: usable_password radio + password1/password2. Returns the hash to store."""
    usable = str(data.get("usable_password", "true")).lower() not in ("false", "0", "")
    if not usable:
        return make_unusable_password()
    p1, p2 = data.get("password1") or "", data.get("password2") or ""
    if not p1:
        errors.setdefault("password1", []).append("This field is required.")
    if not p2:
        errors.setdefault("password2", []).append("This field is required.")
    if p1 and p2 and p1 != p2:
        errors.setdefault("password2", []).append("The two password fields didn’t match.")
    if errors:
        return None
    problems = validate_password(p2, user)
    if problems:
        errors.setdefault("password2", []).extend(problems)
        return None
    return make_password(p1)


# =============================================================================== UserAdmin add
def add_user(c: core.Ctx, data: dict) -> dict:
    errors: dict[str, list[str]] = {}
    username = (data.get("username") or "").strip()
    ut = core.table(USER_LABEL)
    if not username:
        errors["username"] = ["This field is required."]
    elif len(username) > 150:
        errors["username"] = [f"Ensure this value has at most 150 characters (it has {len(username)})."]
    elif not USERNAME_RE.match(username):
        errors["username"] = ["Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters."]
    elif c.db.execute(select(ut.c.id).where(func.lower(ut.c.username) == username.lower())).first():
        errors["username"] = ["A user with that username already exists."]
    encoded = _password_pair(data, {"username": username}, errors)
    if errors:
        core.raise_form_errors(core.FormErrors(errors))
    values = {**core.model_defaults(USER_LABEL), "username": username, "password": encoded}
    pk = core.write_row(c, USER_LABEL, values, None)
    if c.org_id:  # added while a workspace is chosen in the top bar: the user joins it
        m = core.Base.metadata.tables["org_membership"]
        now = core.utcnow()
        c.db.execute(m.insert().values(organisation_id=c.org_id, user_id=pk, role="member", status="active",
                                       added_by_id=c.user.id if c.user else None, created_at=now, updated_at=now))
    row = c.fetch(USER_LABEL, pk)
    rep = c.str(USER_LABEL, row)
    core.log_action(c, USER_LABEL, pk, rep, core.ADDITION, json.dumps([{"added": {}}]))
    c.db.commit()
    return {"pk": str(pk), "str": rep,
            "message": f"The user “{rep}” was added successfully. You may edit it again below."}


# =============================================================================== password change
def password_form(c: core.Ctx, pk_raw) -> dict:
    row = core.get_row(c, USER_LABEL, pk_raw)
    return {"pk": str(row["id"]), "username": row["username"], "str": c.str(USER_LABEL, row),
            "title": f"Change password: {row['username']}",
            "usable": not (row["password"] or "").startswith("!"),
            "help": core.PASSWORD_HELP}


def change_password(c: core.Ctx, pk_raw, data: dict) -> dict:
    row = core.get_row(c, USER_LABEL, pk_raw)
    errors: dict[str, list[str]] = {}
    encoded = _password_pair(data, row, errors)
    if errors:
        core.raise_form_errors(core.FormErrors(errors))
    t = core.table(USER_LABEL)
    c.db.execute(update(t).where(t.c.id == row["id"]).values(password=encoded, updated_at=utcnow()))
    core.log_action(c, USER_LABEL, row["id"], c.str(USER_LABEL, row), core.CHANGE,
                    json.dumps([{"changed": {"fields": ["password"]}}]))
    c.db.commit()
    return {"message": "Password changed successfully."}


# =============================================================================== DocumentVersion change file
ALLOWED = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"]
MAX_SIZE = 50 * 1024 * 1024


def _annotation_count(c: core.Ctx, version_id: int) -> int:
    t = Base.metadata.tables["documents_documentannotation"]
    return c.db.execute(select(func.count()).select_from(t).where(t.c.document_version_id == version_id)).scalar_one()


def change_file_form(c: core.Ctx, pk_raw) -> dict:
    v = core.get_row(c, VERSION_LABEL, pk_raw)
    upd = v["updated_at"]
    local = pytz.UTC.localize(upd).astimezone(pytz.timezone(settings.TIME_ZONE)) if upd else None
    return {
        "pk": str(v["id"]),
        "str": c.str(VERSION_LABEL, v),
        "title": f"Change File for Version: {v['version_number']}",
        "version": {
            "version_number": v["version_number"], "file_name": v["file_name"],
            "file_extension": (v["file_extension"] or "").upper(), "file_title_name": v["file_title_name"],
            "stage_status": c.choice_label(VERSION_LABEL, "stage_status", v["stage_status"]),
            "updated_at": iso(upd), "updated_at_display": local.strftime("%Y-%m-%d %H:%M:%S") if local else "",
            "document_file": v["document_file"], "url": files_core.media_url(v["document_file"]),
        },
        "annotation_count": _annotation_count(c, v["id"]),
        "allowed_extensions": ALLOWED,
        "help_text": "Upload a new file to replace the existing document version file. "
                     "Allowed formats: pdf, doc, docx, xls, xlsx, ppt, pptx",
    }


def _upload_size(up: UploadFile) -> int:
    up.file.seek(0, os.SEEK_END)
    size = up.file.tell()
    up.file.seek(0)
    return size


def change_file(c: core.Ctx, pk_raw, new_file: UploadFile | None, confirm: bool) -> dict:
    """documents.admin_views.change_document_version_file (POST)."""
    v = core.get_row(c, VERSION_LABEL, pk_raw)
    errors: dict[str, list[str]] = {}
    if new_file is None or not new_file.filename:
        errors["new_file"] = ["This field is required."]
    else:
        ext = new_file.filename.rsplit(".", 1)[-1].lower() if "." in new_file.filename else ""
        if ext not in ALLOWED:
            errors["new_file"] = [f"File extension “{ext}” is not allowed. Allowed extensions are: {', '.join(ALLOWED)}."]
        elif _upload_size(new_file) > MAX_SIZE:
            errors["new_file"] = [f"File size must not exceed {MAX_SIZE // (1024 * 1024)}MB"]
    if not confirm:
        errors["confirm_delete_annotations"] = ["This field is required."]
    if errors:
        core.raise_form_errors(core.FormErrors(errors))

    messages: list[dict] = []
    old_rel = v["document_file"] or None
    try:
        ann = Base.metadata.tables["documents_documentannotation"]
        annotation_count = _annotation_count(c, v["id"])
        c.db.execute(delete(ann).where(ann.c.document_version_id == v["id"]))
        stored = files_core.save_upload(new_file, files_core.document_upload_dir(v["id"]))
        t = core.table(VERSION_LABEL)
        c.db.execute(update(t).where(t.c.id == v["id"]).values(
            document_file=stored, file_name=new_file.filename,
            file_extension=new_file.filename.split(".")[-1].lower(), modified_by_id=c.user.id, updated_at=utcnow()))
        c.db.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        c.db.rollback()
        raise HTTPException(400, f"Error replacing file: {exc}")
    if old_rel and old_rel != stored:
        try:
            p = files_core.media_path(old_rel)
            if p and p.exists():
                os.remove(p)
        except Exception as exc:  # noqa: BLE001
            messages.append({"level": "warning", "message": f"Could not delete old file: {exc}"})
    messages.append({"level": "success", "message": f"Successfully replaced file for version {v['version_number']}. "
                                                    f"Deleted {annotation_count} annotation(s)."})
    return {"messages": messages, "document_file": stored}


# =============================================================================== timezone management
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


def list_timezones(all_: bool) -> list[dict]:
    """authentication.views.get_timezones"""
    if not all_:
        return COMMON_TIMEZONES
    out = []
    now = datetime.datetime.now(pytz.UTC).replace(tzinfo=None)
    for name in pytz.all_timezones:
        try:
            offset = pytz.timezone(name).utcoffset(now)
            if offset:
                hours, remainder = divmod(int(offset.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                off = f"{hours:+03d}:{minutes:02d}"
            else:
                off = "+00:00"
            out.append({"value": name, "label": name.replace("_", " "), "offset": off})
        except Exception:  # noqa: BLE001
            continue
    out.sort(key=lambda x: x["value"])
    return out


def timezone_stats(c: core.Ctx) -> dict:
    """authentication.views.timezone_stats"""
    t = core.table(USER_LABEL)
    rows = c.db.execute(select(t.c.timezone, func.count(t.c.timezone).label("n")).group_by(t.c.timezone)
                        .order_by(func.count(t.c.timezone).desc())).all()
    total = c.db.execute(select(func.count()).select_from(t)).scalar_one()
    stats = [{"timezone": tz or "Not Set", "count": n,
              "percentage": round((n / total) * 100, 1) if total > 0 else 0} for tz, n in rows]
    return {"stats": stats, "total_users": total, "unique_timezones": len(stats)}


def timezone_overview() -> dict:
    tz = pytz.timezone(settings.TIME_ZONE)
    off = datetime.datetime.now(tz).utcoffset()
    total = int(off.total_seconds()) if off else 0
    hours, remainder = divmod(abs(total), 3600)
    minutes, _ = divmod(remainder, 60)
    return {"current_timezone": settings.TIME_ZONE, "timezone_offset": f"{'+' if total >= 0 else '-'}{hours:02d}:{minutes:02d}",
            "current_system_timezone": settings.TIME_ZONE, "django_timezone": settings.TIME_ZONE, "use_tz": True}
