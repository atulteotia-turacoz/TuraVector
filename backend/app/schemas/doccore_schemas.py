"""Request bodies for the doccore module."""
from typing import Any

from pydantic import BaseModel


class WorkflowIn(BaseModel):
    """Body of send-for-review / send-for-revision / mark-complete (same keys as the Django AJAX calls)."""
    docId: Any = None
    versionId: Any = None


class StatusIn(BaseModel):
    """DocumentStatusUpdateForm / DocumentVersionStatusUpdateForm."""
    stage_status: Any = None


class EditIn(BaseModel):
    """DocumentEditForm."""
    document_name: str | None = None
    document_type: str | int | None = None
    country: str | int | None = None
    brand: str | int | None = None
    therapeutic_area: str | int | None = None
