"""OnlyOffice editor config + Document Server callbacks.

* GET  /api/viewer/onlyoffice/edit-config?id=<version>  — OnlyOfficeEditView.get (no login
  required in Django either; anonymous users get id "anonymous").
* POST /api/viewer/onlyoffice/callback/?version_id=<id> — OnlyOfficeCallbackView.post
* GET  /api/viewer/onlyoffice/callback/                — OnlyOfficeCallbackView.get
* POST /api/viewer/onlyoffice/callback/<version_id>/    — legacy documents.views.onlyoffice_callback

The callbacks are called by the external Document Server, so they are
unauthenticated and, like Django, do not verify any JWT. The editor config
points the Document Server at the new callback URL automatically
(`<NGROK_BASE_URL or BACKEND_PUBLIC_URL>/api/viewer/onlyoffice/callback/?version_id=`).
"""
import json
import logging
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_optional_user
from app.core.files import document_upload_dir, media_path, save_bytes
from app.database import get_db
from app.models import DocumentVersion, User, utcnow
from app.services import viewer_onlyoffice

log = logging.getLogger("turadome.viewer")

router = APIRouter(prefix="/api/viewer/onlyoffice", tags=["viewer"])


@router.get("/edit-config")
def edit_config(id: str = "", user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    if not id:
        return JSONResponse({"detail": "Document ID is required"}, status_code=400)
    try:
        version = db.get(DocumentVersion, int(id))
    except ValueError:
        version = None
    if version is None:
        return JSONResponse({"detail": "Document not found"}, status_code=404)
    try:
        config = viewer_onlyoffice.build_editor_config(db, version, user)
    except Exception as exc:  # noqa: BLE001
        log.exception("OnlyOffice Edit Error")
        return JSONResponse({"detail": f"Internal server error: {exc}" if settings.DEBUG else "Internal server error"},
                            status_code=500)
    return {
        "config": config,
        "file_name": version.file_name,
        "document_title": version.file_title_name,
        "onlyoffice_server_url": settings.ONLYOFFICE_DOCUMENT_SERVER_URL.rstrip("/"),
        "version_id": str(version.id),
        "document_id": str(version.document_id),
        "user_name": (f"{user.first_name} {user.last_name}".strip() or user.username) if user else "",
    }


@router.get("/callback/")
def callback_ready():
    return {"error": 0, "message": "Callback endpoint ready"}


@router.post("/callback/")
async def callback(request: Request, version_id: str | None = None, db: Session = Depends(get_db)):
    """OnlyOfficeCallbackView.post — overwrite the version file in place when status is 2 or 6."""
    if not version_id:
        return {"error": 1, "message": "No version_id provided"}
    try:
        try:
            data = json.loads((await request.body()).decode("utf-8"))
        except json.JSONDecodeError:
            return {"error": 1, "message": "Invalid JSON"}
        if not data:
            return {"error": 1}
        log.info("OnlyOffice Callback - Status: %s, Key: %s", data.get("status"), data.get("key"))

        if data.get("status") in [2, 6]:
            download_url = data.get("url")
            try:
                version = db.get(DocumentVersion, int(version_id))
            except ValueError:
                version = None
            if version is None:
                return {"error": 1, "message": "Document version not found"}
            save_path = str(media_path(version.document_file))
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            try:
                content = viewer_onlyoffice.download(download_url, timeout=30)
            except Exception as exc:  # noqa: BLE001 — requests.RequestException
                log.error("OnlyOffice: Failed to download file from %s: %s", download_url, exc)
                return {"error": 3, "message": "Failed to download file"}
            try:
                with open(save_path, "wb") as f:
                    f.write(content)
            except OSError as exc:
                log.error("OnlyOffice: Failed to write file to %s: %s", save_path, exc)
                return {"error": 2, "message": "Failed to write file"}
            return {"error": 0}
        return {"error": 0}
    except Exception as exc:  # noqa: BLE001
        log.error("OnlyOffice Callback Error: %s", exc)
        return {"error": 1, "message": "Internal server error"}


@router.post("/callback/{version_id}/")
async def legacy_callback(version_id: int, request: Request, db: Session = Depends(get_db)):
    """documents.views.onlyoffice_callback — saves via the storage (new name under documents/<id>/)."""
    try:
        version = db.get(DocumentVersion, version_id)
        if version is None:
            return JSONResponse({"error": 1, "message": "No DocumentVersion matches the given query."}, status_code=500)
        data = json.loads((await request.body()).decode("utf-8"))
        if not data:
            return JSONResponse({"error": 1}, status_code=400)
        if data.get("status") in [2, 6]:
            download_url = data.get("url")
            if download_url:
                try:
                    import requests

                    response = requests.get(download_url)
                    if response.status_code == 200:
                        # FieldFile.save(file_name, ContentFile(...), save=True)
                        version.document_file = save_bytes(response.content, document_upload_dir(version.id),
                                                           version.file_name)
                        version.updated_at = utcnow()
                        db.commit()
                        return {"error": 0}
                    return JSONResponse({"error": 3, "message": "Failed to download file"}, status_code=500)
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    return JSONResponse({"error": 2, "message": f"Failed to write file: {exc}"}, status_code=500)
        return {"error": 0}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": 1, "message": str(exc)}, status_code=500)
