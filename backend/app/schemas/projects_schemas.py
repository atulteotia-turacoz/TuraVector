"""Request bodies for document version sharing (Content Review version collaborators)."""
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------- sharing
class VersionCollaboratorAddIn(BaseModel):
    user_id: Any = None
    permission_level: str = "view"
    role_id: Any = None
    can_share: bool = False
    can_download: bool = True
    can_annotate: bool = True
    can_delete_versions: bool = False
    notify_on_update: bool = True
    notes: str | None = ""
    expires_at: str | None = None
