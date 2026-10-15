"""Office 365 / OneDrive editing — port of documents/office365_utils.py."""
import logging

import requests

from app.config import settings

log = logging.getLogger("turadome.viewer")

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
MICROSOFT_SCOPE = ["https://graph.microsoft.com/.default"]


class FileLockedError(Exception):
    """Raised when a file is locked (already being edited in Office 365)."""


def get_graph_access_token() -> str:
    import msal

    app = msal.ConfidentialClientApplication(
        settings.MICROSOFT_CLIENT_ID,
        authority=settings.microsoft_authority,
        client_credential=settings.MICROSOFT_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=MICROSOFT_SCOPE)
    if "access_token" in result:
        return result["access_token"]
    error_desc = result.get("error_description", result.get("error", "Unknown error"))
    log.error("Failed to acquire Graph token: %s", error_desc)
    raise Exception(f"Could not acquire Microsoft Graph token: {error_desc}")


def upload_file_to_onedrive(file_path: str, file_name: str, version_id) -> dict:
    token = get_graph_access_token()
    upn = settings.MICROSOFT_ONEDRIVE_USER_ID
    remote_path = f"/TuradomeEditing/{version_id}/{file_name}"
    url = f"{GRAPH_API_BASE}/users/{upn}/drive/root:{remote_path}:/content"
    with open(file_path, "rb") as f:
        data = f.read()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}
    resp = requests.put(url, headers=headers, data=data, timeout=120)
    if resp.status_code == 423:
        raise FileLockedError("Document is already open in Office 365. Please use the existing window or wait for it to be closed.")
    if resp.status_code not in (200, 201):
        log.error("OneDrive upload failed [%s]: %s", resp.status_code, resp.text)
        raise Exception(f"OneDrive upload failed ({resp.status_code}): {resp.text}")
    return resp.json()


def get_edit_url(item_id: str) -> str:
    token = get_graph_access_token()
    upn = settings.MICROSOFT_ONEDRIVE_USER_ID
    url = f"{GRAPH_API_BASE}/users/{upn}/drive/items/{item_id}/createLink"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json={"type": "edit", "scope": "anonymous"}, timeout=30)
    if resp.status_code not in (200, 201):
        log.warning("Could not create sharing link [%s]: %s", resp.status_code, resp.text)
        resp2 = requests.get(f"{GRAPH_API_BASE}/users/{upn}/drive/items/{item_id}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp2.raise_for_status()
        return resp2.json().get("webUrl", "")
    return resp.json().get("link", {}).get("webUrl", "")


def download_file_from_onedrive(item_id: str) -> bytes:
    token = get_graph_access_token()
    upn = settings.MICROSOFT_ONEDRIVE_USER_ID
    headers = {"Authorization": f"Bearer {token}"}
    meta = requests.get(f"{GRAPH_API_BASE}/users/{upn}/drive/items/{item_id}", headers=headers, timeout=30)
    if meta.status_code == 200:
        m = meta.json()
        log.info("Downloading file: %s, last modified: %s, size: %s bytes",
                 m.get("name"), m.get("lastModifiedDateTime"), m.get("size"))
    resp = requests.get(f"{GRAPH_API_BASE}/users/{upn}/drive/items/{item_id}/content", headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.content
