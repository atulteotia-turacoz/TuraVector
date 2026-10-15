"""Request bodies for the projects module. Values are kept loose (Any) on purpose:
validation and error texts follow the Django forms in app/services/projects_service.py."""
from typing import Any

from pydantic import BaseModel


class AuthorRow(BaseModel):
    id: int | None = None
    name: str | None = ""
    affiliation: str | None = ""
    email: str | None = ""
    author_type: str | None = "other"
    DELETE: bool = False


class ProjectIn(BaseModel):
    project_type: Any = None
    project_type_other: Any = None
    client_type: Any = None
    client_other: Any = None
    title: Any = None
    status: Any = None
    client_poc_name: Any = None
    client_poc_email: Any = None
    has_authors: Any = False
    journal_name: Any = None
    therapeutic_area: Any = None
    therapeutic_area_other: Any = None
    sub_therapy_area: Any = None
    start_date: Any = None
    estimated_end_date: Any = None
    actual_end_date: Any = None
    description: Any = None
    research_field: Any = None
    keywords: Any = None
    priority: Any = None
    budget: Any = None
    authors: list[AuthorRow] = []


class LegacyCollaboratorIn(BaseModel):
    email: str | None = None
    role: str = "contributor"


class CollaboratorIn(BaseModel):
    user: Any = None
    role: Any = None


class TaskIn(BaseModel):
    title: Any = None
    description: Any = None
    status: Any = None
    priority: Any = None
    assigned_to: Any = None
    due_date: Any = None


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
