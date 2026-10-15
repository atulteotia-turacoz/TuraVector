"""File storage that behaves like Django's FileSystemStorage.

DB columns hold paths relative to MEDIA_ROOT (e.g. `documents/12/report.docx`),
exactly as Django's FileField did, so existing rows and files stay valid.
"""
import os
import re
import secrets
import shutil
import string
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

_RANDOM_CHARS = string.ascii_letters + string.digits


def get_valid_filename(name: str) -> str:
    """django.utils.text.get_valid_filename"""
    s = str(name).strip().replace(" ", "_")
    s = re.sub(r"(?u)[^-\w.]", "", s)
    if s in {"", ".", ".."}:
        raise HTTPException(400, f"Could not derive file name from '{name}'")
    return s


def media_path(relative: str | None) -> Path | None:
    if not relative:
        return None
    root = settings.media_root.resolve()
    full = (root / relative).resolve()
    if root not in full.parents and full != root:
        raise HTTPException(400, "Invalid file path")
    return full


def media_url(relative: str | None) -> str | None:
    """Public URL served by the /media mount (same scheme as Django's MEDIA_URL)."""
    if not relative:
        return None
    return f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{settings.MEDIA_URL}{relative}"


def _available_name(relative: str) -> str:
    """Django appends `_<7 random chars>` before the extension when a name is taken."""
    full = settings.media_root / relative
    if not full.exists():
        return relative
    directory, filename = os.path.split(relative)
    stem, ext = os.path.splitext(filename)
    while True:
        candidate = os.path.join(directory, f"{stem}_{''.join(secrets.choice(_RANDOM_CHARS) for _ in range(7))}{ext}")
        if not (settings.media_root / candidate).exists():
            return candidate


def save_upload(upload: UploadFile, directory: str, filename: str | None = None) -> str:
    """Save an UploadFile under MEDIA_ROOT/<directory>/ and return the relative path for the DB."""
    name = get_valid_filename(os.path.basename(filename or upload.filename or "file"))
    relative = _available_name(os.path.join(directory.strip("/"), name))
    full = settings.media_root / relative
    full.parent.mkdir(parents=True, exist_ok=True)
    upload.file.seek(0)
    with open(full, "wb") as out:
        shutil.copyfileobj(upload.file, out)
    os.chmod(full, 0o644)
    return relative


def save_bytes(data: bytes, directory: str, filename: str) -> str:
    relative = _available_name(os.path.join(directory.strip("/"), get_valid_filename(filename)))
    full = settings.media_root / relative
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    os.chmod(full, 0o644)
    return relative


def delete_file(relative: str | None) -> None:
    path = media_path(relative)
    if path and path.is_file():
        path.unlink()


# upload_to equivalents from the Django models
def document_upload_dir(document_version_id) -> str:
    # documents.models.document_upload_path uses the *version* instance id, which is
    # None before the first save — Django therefore wrote to documents/None/.
    return f"documents/{document_version_id}"


def reference_upload_dir(reference_id) -> str:
    return f"references/{reference_id}"


def reference_zip_upload_dir(user_id) -> str:
    return f"references_zip/{user_id or 'unknown'}"
