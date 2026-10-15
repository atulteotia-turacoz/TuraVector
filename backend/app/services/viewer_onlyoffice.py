"""OnlyOffice integration — port of documents/onlyoffice_views.py, the legacy
documents.views.onlyoffice_callback and turadome_django/utils.generate_token.

JWT secrets — which one each Django code path *effectively* used
-----------------------------------------------------------------
* OnlyOfficeEditView (the only live editor path; documents.views.document_editor
  always redirects to it) signs the editor config with
  `turadome_django.utils.generate_token`, i.e.
  `decouple.config('ONLYOFFICE_JWT_SECRET', default='6YdcN44m5WTLvDjreLSmn8ICZv5kiWo1')`.
  The Django `.env` never defined ONLYOFFICE_JWT_SECRET, so production used the
  '6YdcN44m…' default (the secret shared with the PHP app / Document Server).
* `settings.ONLYOFFICE_JWT_SECRET` (default 'ujQ0jQ6k…', the value now stored in
  backend/.env as ONLYOFFICE_JWT_SECRET) was only read by the unreachable code
  after the redirect in document_editor — it never signed anything that reached
  the Document Server.
* Neither callback view verified any JWT (both were csrf_exempt + AllowAny and
  read the JSON body directly). The new callbacks do the same.

So the editor token here is signed with ONLYOFFICE_EDITOR_JWT_SECRET (read from
the environment / backend/.env), defaulting to the same '6YdcN44m…' value.
"""
import hashlib
import os

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthGroup, AuthenticationUserGroups, DocumentVersion, User
from app.services.viewer_common import get_full_name


def editor_jwt_secret() -> str:
    return settings.ONLYOFFICE_EDITOR_JWT_SECRET


def generate_token(payload: dict) -> str:
    """turadome_django.utils.generate_token"""
    return jwt.encode(payload, editor_jwt_secret(), algorithm="HS256")


def public_base_url() -> str:
    """Base URL the Document Server uses to reach this backend (Django: NGROK_BASE_URL)."""
    base = settings.NGROK_BASE_URL or os.environ.get("NGROK_BASE_URL", "")
    if base and base.startswith("http"):
        return base.rstrip("/")
    return settings.BACKEND_PUBLIC_URL.rstrip("/")


def document_key(version: DocumentVersion) -> str:
    """md5('v<id>_<mtime>') with mtime = updated_at (else created_at) as a UTC POSIX timestamp —
    identical to Django so the Document Server cache keys of existing documents stay valid."""
    import datetime

    stamp_src = version.updated_at or version.created_at
    stamp = stamp_src.replace(tzinfo=datetime.timezone.utc).timestamp()
    return hashlib.md5(f"v{version.id}_{str(stamp)}".encode()).hexdigest()


def _first_group_name(db: Session, user: User) -> str | None:
    row = db.execute(
        select(AuthGroup.name).join(AuthenticationUserGroups, AuthenticationUserGroups.group_id == AuthGroup.id)
        .where(AuthenticationUserGroups.user_id == user.id).order_by(AuthGroup.id).limit(1)
    ).first()
    return row[0] if row else None


def build_editor_config(db: Session, version: DocumentVersion, user: User | None) -> dict:
    """OnlyOfficeEditView.get — the config dict (with token) handed to DocsAPI.DocEditor."""
    file_name = version.file_name
    base_url = public_base_url()
    # Django: f"{base_url}{version.document_file.url}" — files are served under MEDIA_URL by this backend
    file_url = f"{base_url}{settings.MEDIA_URL}{version.document_file or ''}"
    callback_url = f"{base_url}/api/viewer/onlyoffice/callback/?version_id={version.id}"

    if user is not None:
        user_id = str(user.id)
        user_name = get_full_name(user) or user.username
        group = _first_group_name(db, user) or "Default"
    else:
        user_id, user_name, group = "anonymous", "Anonymous", "Default"

    config = {
        "document": {
            "fileType": file_name.split(".")[-1],
            "key": document_key(version),
            "title": file_name,
            "url": file_url,
        },
        "editorConfig": {
            "callbackUrl": callback_url,
            "user": {
                "id": user_id,
                "name": user_name,
                "group": group,
                "userdata": {"fileName": file_name},
            },
            "customization": {
                "forcesave": True,
                "comments": True,
                "chat": True,
                "review": {"reviewDisplay": "markup", "trackChanges": False, "hoverMode": False},
            },
            "permissions": {
                "comment": True, "download": True, "edit": True, "fillForms": True,
                "modifyContentControl": True, "modifyFilter": True, "print": True, "review": True,
                "chat": True, "commentGroups": {},
            },
        },
    }
    config["token"] = generate_token(config)
    return config


def download(url: str, timeout: int | None = 30) -> bytes:
    """GET the edited file from the Document Server (raises requests exceptions)."""
    import requests

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content
