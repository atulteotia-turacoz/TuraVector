"""Office 365 / OneDrive editing endpoints — port of documents/office365_views.py.

POST /api/viewer/office365/open/{version_id}             -> {edit_url, item_id}
POST /api/viewer/office365/sync/{version_id}             {item_id} -> {success, message}
POST /api/viewer/office365/reference/open/{reference_id}
POST /api/viewer/office365/reference/sync/{reference_id}

Each is also exposed under /api/office365/... (same handlers).

Used by the viewer pages and by other modules' pages (document detail / history,
reviewer dashboard, reference library).
"""
import logging
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.files import media_path
from app.database import get_db
from app.models import User
from app.services import viewer_office365 as o365
from app.services.viewer_common import get_reference_or_404, get_version_or_404

log = logging.getLogger("turadome.viewer")

router = APIRouter(prefix="/api/viewer/office365", tags=["viewer"])
# Same endpoints under /api/office365 (integration contract used by other modules' pages)
office365_router = APIRouter(prefix="/api/office365", tags=["viewer"])


def _open(relative: str | None, remote_folder, missing: str):
    if not relative:
        return JSONResponse({"error": missing}, status_code=400)
    file_path = str(media_path(relative))
    if not os.path.isfile(file_path):
        return JSONResponse({"error": f"File not found on server: {os.path.basename(file_path)}"}, status_code=404)
    try:
        item = o365.upload_file_to_onedrive(file_path, os.path.basename(file_path), remote_folder)
        item_id = item["id"]
        return {"edit_url": o365.get_edit_url(item_id), "item_id": item_id}
    except o365.FileLockedError as exc:
        return JSONResponse({"error": str(exc), "is_locked": True}, status_code=423)
    except Exception as exc:  # noqa: BLE001
        log.exception("Office 365 open failed for %s", remote_folder)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def _sync(request: Request, relative: str | None, label: str):
    try:
        body = await request.json()
        item_id = body.get("item_id")
    except Exception:  # noqa: BLE001 — JSONDecodeError / AttributeError
        return JSONResponse({"error": "Missing item_id in request body."}, status_code=400)
    if not item_id:
        return JSONResponse({"error": "item_id is required."}, status_code=400)
    try:
        content = o365.download_file_from_onedrive(item_id)
        file_path = str(media_path(relative))
        with open(file_path, "wb") as f:
            f.write(content)
        return {"success": True, "message": "File synced back successfully."}
    except Exception as exc:  # noqa: BLE001
        log.exception("Office 365 sync failed for %s", label)
        return JSONResponse({"error": str(exc)}, status_code=500)


@office365_router.post("/open/{version_id}")
@router.post("/open/{version_id}")
def open_in_office365(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    return _open(version.document_file, version_id, "No file attached to this version.")


@office365_router.post("/sync/{version_id}")
@router.post("/sync/{version_id}")
async def sync_from_office365(version_id: int, request: Request, user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    version = get_version_or_404(db, version_id)
    return await _sync(request, version.document_file, f"version {version_id}")


@office365_router.post("/reference/open/{reference_id}")
@router.post("/reference/open/{reference_id}")
def open_reference_in_office365(reference_id: int, user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    reference = get_reference_or_404(db, reference_id)
    return _open(reference.reference_file, f"ref_{reference_id}", "No file attached to this reference.")


@office365_router.post("/reference/sync/{reference_id}")
@router.post("/reference/sync/{reference_id}")
async def sync_reference_from_office365(reference_id: int, request: Request, user: User = Depends(get_current_user),
                                        db: Session = Depends(get_db)):
    reference = get_reference_or_404(db, reference_id)
    return await _sync(request, reference.reference_file, f"reference {reference_id}")
