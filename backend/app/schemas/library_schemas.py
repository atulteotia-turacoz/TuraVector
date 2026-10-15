"""Request bodies for the library module (port of library.views POST handlers)."""
from typing import Optional

from pydantic import BaseModel


class AssignReviewerIn(BaseModel):
    """POST fields of assign_reviewer_view (all optional so the view's own messages apply)."""
    reviewer_id: Optional[str] = None
    review_date: Optional[str] = None  # 'YYYY-MM-DD'
    remarks: Optional[str] = ""


class CompleteReviewIn(BaseModel):
    """JSON body of complete_review."""
    remarks: Optional[str] = ""
    approval_status: Optional[str] = None  # 'approved' | 'rejected'
