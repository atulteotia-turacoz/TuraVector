"""System Settings: view and edit the configuration / secrets kept in backend/.env.

These values were hard-coded in the Django project's settings.py; the FastAPI app reads
them from `app.config.settings` (pydantic-settings, env_file=backend/.env).

* `ENV_PATH` is the ONLY place the .env location is defined — tests monkeypatch it.
* Updates rewrite the file atomically (previous copy kept as `.env.bak`), preserving
  comments and order, then apply the new values to the live `settings` object.
* Secrets are never returned except through the explicit reveal endpoint; DB_PASSWORD and
  SECRET_KEY are never returned at all.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from app.config import BASE_DIR, Settings, settings

ENV_PATH: Path = BASE_DIR / ".env"

MASK = "••••"

# (section title, [keys])
SECTIONS: list[tuple[str, list[str]]] = [
    ("Application URLs", ["BACKEND_PUBLIC_URL", "FRONTEND_URL", "SUPERADMIN_URL", "CORS_ORIGINS"]),
    ("Auth", ["ACCESS_TOKEN_EXPIRE_MINUTES"]),
    ("Email fallback", ["EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT", "EMAIL_USE_TLS", "EMAIL_HOST_USER",
                        "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL"]),
    ("OnlyOffice", ["ONLYOFFICE_DOCUMENT_SERVER_URL", "ONLYOFFICE_JWT_SECRET", "ONLYOFFICE_EDITOR_JWT_SECRET",
                    "ONLYOFFICE_DISABLE_JWT",
                    "ENABLE_ONLYOFFICE_EDITOR", "NGROK_BASE_URL"]),
    ("Office 365", ["MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET", "MICROSOFT_TENANT_ID", "MICROSOFT_ONEDRIVE_USER_ID"]),
    ("PDFTron", ["PDFTRON_ENABLED", "PDFTRON_LICENSE_KEY", "PDFTRON_VERSION", "PDFTRON_PATH"]),
    ("Document security", ["ALLOW_DOCUMENT_DOWNLOAD", "DOCUMENT_WATERMARK", "DOCUMENT_PRINT_DISABLED"]),
    ("Tura applications", ["TURA_RESEARCH_ASSISTANT_URL", "TURA_LMS_URL", "TURAGRAMMAR_URL", "TURASTATISTICS_URL", "TURASLR_URL"]),
    ("Tura applications — single sign-on", ["SSO_TICKET_TTL_SECONDS",
                                            "TURA_RESEARCH_ASSISTANT_SSO_URL", "TURA_RESEARCH_ASSISTANT_SSO_SECRET",
                                            "TURAGRAMMAR_SSO_URL", "TURAGRAMMAR_SSO_SECRET",
                                            "TURASTATISTICS_SSO_URL", "TURASTATISTICS_SSO_SECRET",
                                            "TURASLR_SSO_URL", "TURASLR_SSO_SECRET",
                                            "TURA_LMS_BASE_URL", "TURA_LMS_WS_TOKEN"]),
    ("Journal APIs", ["SPRINGER_API_KEY", "ELSEVIER_API_KEY", "PUBMED_API_KEY"]),
    ("Storage", ["MEDIA_ROOT", "FILE_UPLOAD_MAX_SIZE", "TIME_ZONE"]),
    ("Read-only info", ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "SECRET_KEY"]),
]

SECRET_KEYS = {"EMAIL_HOST_PASSWORD", "ONLYOFFICE_JWT_SECRET", "ONLYOFFICE_EDITOR_JWT_SECRET", "MICROSOFT_CLIENT_SECRET",
               "PDFTRON_LICENSE_KEY",
               "TURA_RESEARCH_ASSISTANT_SSO_SECRET", "TURAGRAMMAR_SSO_SECRET", "TURASTATISTICS_SSO_SECRET", "TURASLR_SSO_SECRET", "TURA_LMS_WS_TOKEN",
               "SPRINGER_API_KEY", "ELSEVIER_API_KEY", "PUBMED_API_KEY",
               "DB_PASSWORD", "SECRET_KEY"}
# Never returned, never revealed, never editable here.
HIDDEN_KEYS = {"DB_PASSWORD", "SECRET_KEY"}
READ_ONLY_KEYS = {"DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"} | HIDDEN_KEYS
# Values captured at import time: DB engine, CORS middleware, the /media static mount.
RESTART_KEYS = {"DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "SECRET_KEY", "CORS_ORIGINS", "MEDIA_ROOT"}
CHOICES = {"EMAIL_BACKEND": [["console", "Console (log only)"], ["smtp", "SMTP"]]}
# Shared secrets the admin may generate in the UI (then copy into the other app's .env).
GENERATE_KEYS = {"TURA_RESEARCH_ASSISTANT_SSO_SECRET", "TURAGRAMMAR_SSO_SECRET", "TURASTATISTICS_SSO_SECRET",
                 "TURASLR_SSO_SECRET"}
MIN_LENGTH = {k: 32 for k in GENERATE_KEYS}
INT_RANGE = {"SSO_TICKET_TTL_SECONDS": (10, 600)}

HELP = {
    "BACKEND_PUBLIC_URL": "Public base URL of this API; used to build absolute media and callback URLs.",
    "FRONTEND_URL": "Base URL of the user app; used in links inside emails.",
    "SUPERADMIN_URL": "Base URL of this admin app.",
    "CORS_ORIGINS": "Comma-separated browser origins allowed to call the API.",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "Lifetime of a login token in minutes.",
    "EMAIL_BACKEND": "Used only when no active SMTP Settings row exists. 'console' only logs messages.",
    "EMAIL_HOST": "SMTP server host for the fallback backend.",
    "EMAIL_PORT": "SMTP server port.",
    "EMAIL_USE_TLS": "Use STARTTLS with the fallback SMTP server.",
    "EMAIL_HOST_USER": "SMTP username.",
    "EMAIL_HOST_PASSWORD": "SMTP password.",
    "DEFAULT_FROM_EMAIL": "Sender address for system emails.",
    "ONLYOFFICE_DOCUMENT_SERVER_URL": "URL of the OnlyOffice Document Server.",
    "ONLYOFFICE_JWT_SECRET": "Shared JWT secret configured on the Document Server.",
    "ONLYOFFICE_EDITOR_JWT_SECRET": "Signs the OnlyOffice editor token (the value the old Django editor view used)",
    "ONLYOFFICE_DISABLE_JWT": "Disable JWT signing of editor configs and callbacks.",
    "ENABLE_ONLYOFFICE_EDITOR": "Show the OnlyOffice editor for Office documents.",
    "NGROK_BASE_URL": "Public tunnel URL the Document Server uses to reach this API (development).",
    "MICROSOFT_CLIENT_ID": "Azure app registration (application) ID.",
    "MICROSOFT_CLIENT_SECRET": "Azure app client secret.",
    "MICROSOFT_TENANT_ID": "Azure tenant (directory) ID.",
    "MICROSOFT_ONEDRIVE_USER_ID": "OneDrive user whose drive stores documents opened in Office 365.",
    "PDFTRON_ENABLED": "Use the Apryse WebViewer for PDFs.",
    "PDFTRON_LICENSE_KEY": "Apryse WebViewer licence key.",
    "PDFTRON_VERSION": "Apryse / PDFTron build version (the server SDK build, e.g. 8.10.0).",
    "PDFTRON_PATH": "Path the frontend serves the WebViewer runtime from.",
    "ALLOW_DOCUMENT_DOWNLOAD": "Allow users to download documents from the viewer.",
    "DOCUMENT_WATERMARK": "Show a watermark on viewed documents.",
    "DOCUMENT_PRINT_DISABLED": "Disable printing from the viewer.",
    "TURA_RESEARCH_ASSISTANT_URL": "Link opened by the Tura Research Assistant card on the dashboard-selection page.",
    "TURA_LMS_URL": "Link opened by the Tura LMS card on the dashboard-selection page.",
    "TURAGRAMMAR_URL": "Link opened by the TuraGrammar card on the dashboard-selection page.",
    "TURASTATISTICS_URL": "Link opened by the TuraStatistics card on the dashboard-selection page.",
    "TURASLR_URL": "Link opened by the TuraSLR card on the dashboard-selection page.",
    "SSO_TICKET_TTL_SECONDS": "How long (seconds) a single sign-on link stays valid after a card is clicked. 10–600; 60 is recommended.",
    "TURA_RESEARCH_ASSISTANT_SSO_URL": "SSO page of Tura Research Assistant, e.g. https://turaresearchassistant.turacoz.com/sso. "
                                       "Blank = the card opens the normal login page.",
    "TURA_RESEARCH_ASSISTANT_SSO_SECRET": "Shared signing secret (32+ characters). Put the same value in Research Assistant's "
                                          "backend .env as TURADOME_SSO_SECRET and restart it.",
    "TURAGRAMMAR_SSO_URL": "SSO page of TuraGrammar, e.g. https://turagrammar.turacoz.com/sso. "
                           "Blank = the card opens the normal login page.",
    "TURAGRAMMAR_SSO_SECRET": "Shared signing secret (32+ characters). Put the same value in TuraGrammar's "
                              "api/.env as TURADOME_SSO_SECRET and restart it.",
    "TURASTATISTICS_SSO_URL": "SSO page of TuraStatistics, e.g. https://statistics.turacoz.com/sso. "
                              "Blank = the card opens the normal sign-in page.",
    "TURASTATISTICS_SSO_SECRET": "Shared signing secret (32+ characters). Put the same value in TuraStatistics' "
                                 ".env.local as TURAVECTOR_SSO_SECRET and restart it.",
    "TURASLR_SSO_URL": "SSO page of TuraSLR, e.g. https://turaslr.turacoz.com/sso. "
                       "Blank = the card opens the normal sign-in page.",
    "TURASLR_SSO_SECRET": "Shared signing secret (32+ characters). Put the same value in TuraSLR's "
                          "backend/.env as TURAVECTOR_SSO_SECRET and restart it.",
    "TURA_LMS_BASE_URL": "Moodle site root, e.g. https://turalms.turacoz.com (used to call its web service).",
    "TURA_LMS_WS_TOKEN": "Moodle web-service token for the auth_userkey plugin. Blank = the LMS card opens the normal login page.",
    "SPRINGER_API_KEY": "Springer Nature metadata API key (journal selector).",
    "ELSEVIER_API_KEY": "Elsevier / Scopus API key (journal selector).",
    "PUBMED_API_KEY": "NCBI E-utilities API key.",
    "MEDIA_ROOT": "Directory holding uploaded files (shared with the original Django app).",
    "FILE_UPLOAD_MAX_SIZE": "Maximum upload size in bytes.",
    "TIME_ZONE": "Default timezone (Django TIME_ZONE).",
    "DB_HOST": "Database host.", "DB_PORT": "Database port.", "DB_NAME": "Database name.", "DB_USER": "Database user.",
    "DB_PASSWORD": "Database password (never shown).", "SECRET_KEY": "Token signing key (never shown).",
}

ALL_KEYS = [k for _, keys in SECTIONS for k in keys]
EDITABLE_KEYS = [k for k in ALL_KEYS if k not in READ_ONLY_KEYS]


def _annotation(key: str):
    return Settings.model_fields[key].annotation


def key_type(key: str) -> str:
    if key in CHOICES:
        return "choice"
    ann = _annotation(key)
    return {bool: "bool", int: "int"}.get(ann, "str")


def mask(value: Any) -> str:
    s = "" if value is None else str(value)
    if not s:
        return ""
    return MASK + (s[-4:] if len(s) > 4 else "")


def describe(key: str) -> dict:
    value = getattr(settings, key)
    is_secret = key in SECRET_KEYS
    item = {
        "key": key, "type": key_type(key), "is_secret": is_secret, "read_only": key in READ_ONLY_KEYS,
        "requires_restart": key in RESTART_KEYS, "help": HELP.get(key, ""), "is_set": value not in (None, ""),
    }
    if key in CHOICES:
        item["choices"] = CHOICES[key]
    if key in GENERATE_KEYS:
        item["can_generate"] = True
    if key in HIDDEN_KEYS:
        item["value"] = ""
    elif is_secret:
        item["value"] = mask(value)
    else:
        item["value"] = value
    return item


def list_settings() -> dict:
    return {
        "sections": [{"title": title, "keys": [describe(k) for k in keys]} for title, keys in SECTIONS],
        "env_file": ENV_PATH.name,
    }


def reveal(key: str) -> dict:
    if key not in ALL_KEYS:
        raise HTTPException(404, f"Unknown setting: {key}")
    if key in HIDDEN_KEYS or key not in SECRET_KEYS:
        raise HTTPException(400, f"{key} cannot be revealed.")
    return {"key": key, "value": getattr(settings, key) or ""}


# ------------------------------------------------------------------ .env rewriting
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def serialize(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    s = str(value)
    if s == "" or re.search(r"[\s#\"'\\$`]", s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def rewrite_env(updates: dict[str, Any], path: Path | None = None) -> None:
    """Update KEY=value lines in place (keeping comments/order), append new keys; atomic, with .env.bak."""
    path = path or ENV_PATH
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        m = _LINE_RE.match(line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            nl = "\n" if line.endswith("\n") else ""
            out.append(f"{key}={serialize(remaining.pop(key))}{nl}")
        else:
            out.append(line)
    if remaining:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        for key, value in remaining.items():
            out.append(f"{key}={serialize(value)}\n")
    text = "".join(out)
    if path.exists():
        try:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        except OSError:
            pass  # the folder may be read-only for the API user; the backup is a convenience
        mode = path.stat().st_mode & 0o777
    else:
        mode = 0o600
    try:
        fd, tmp = tempfile.mkstemp(prefix=".env.", dir=str(path.parent))
    except OSError:
        # Folder not writable (common on servers): rewrite the file in place if the file itself is writable.
        path.write_text(text, encoding="utf-8")
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def validate_updates(payload: dict[str, Any]) -> dict[str, Any]:
    unknown = [k for k in payload if k not in ALL_KEYS]
    readonly = [k for k in payload if k in READ_ONLY_KEYS]
    if unknown or readonly:
        parts = []
        if unknown:
            parts.append(f"Unknown setting(s): {', '.join(unknown)}")
        if readonly:
            parts.append(f"Read-only setting(s): {', '.join(readonly)}")
        raise HTTPException(400, ". ".join(parts) + ".")
    clean: dict[str, Any] = {}
    errors: dict[str, list[str]] = {}
    for key, raw in payload.items():
        if key in SECRET_KEYS and (raw is None or raw == ""):
            continue  # blank secret keeps the current value
        if key in SECRET_KEYS and isinstance(raw, str) and raw.strip() == "":
            clean[key] = ""  # whitespace-only = the UI's explicit "Clear" button
            continue
        if key in CHOICES:
            if raw not in [c[0] for c in CHOICES[key]]:
                errors[key] = [f"Select a valid choice. {raw} is not one of the available choices."]
                continue
        try:
            value = TypeAdapter(_annotation(key)).validate_python(raw.strip() if isinstance(raw, str) else raw)
        except ValidationError as e:
            errors[key] = [err["msg"] for err in e.errors()]
            continue
        if key_type(key) == "int" and value < 0:
            errors[key] = ["Ensure this value is greater than or equal to 0."]
            continue
        if key in INT_RANGE and not INT_RANGE[key][0] <= value <= INT_RANGE[key][1]:
            errors[key] = [f"Enter a value between {INT_RANGE[key][0]} and {INT_RANGE[key][1]}."]
            continue
        if key in MIN_LENGTH and value and len(value) < MIN_LENGTH[key]:
            errors[key] = [f"Use at least {MIN_LENGTH[key]} characters (click Generate for a strong value)."]
            continue
        clean[key] = value
    if errors:
        raise HTTPException(400, {"message": "Please correct the errors below.", "errors": errors})
    return clean


def update_settings(payload: dict[str, Any], log) -> dict:
    """Validate, persist to .env, apply live. `log(changed_keys)` writes the admin LogEntry."""
    clean = validate_updates(payload)
    changed = {k: v for k, v in clean.items() if getattr(settings, k) != v}
    if changed:
        try:
            rewrite_env(changed)
        except OSError as exc:
            import getpass
            raise HTTPException(500, f"Could not save to {ENV_PATH}: {exc.strerror or exc}. "
                                     f"The API runs as user '{getpass.getuser()}'; give that user write access "
                                     f"to this file (e.g. sudo chown {getpass.getuser()} {ENV_PATH}).") from exc
        for k, v in changed.items():
            setattr(settings, k, v)
        log(sorted(changed))
    restart = sorted(k for k in changed if k in RESTART_KEYS)
    return {
        "changed": sorted(changed),
        "requires_restart": restart,
        "message": (f"Saved {len(changed)} setting(s)." if changed else "No settings were changed."),
    }


def log_message(keys: list[str]) -> str:
    return json.dumps([{"changed": {"fields": keys}}])
