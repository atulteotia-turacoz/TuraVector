"""System Settings — the backend/.env configuration (formerly hard-coded in Django settings.py)."""
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.database import get_db
from app.models import Base, User, utcnow
from app.services import superadmin_settings as svc

router = APIRouter(prefix="/api/superadmin/settings", tags=["superadmin"])


@router.get("")
def get_settings(user: User = Depends(require_superuser)):
    return svc.list_settings()


@router.post("/{key}/reveal")
def reveal(key: str, user: User = Depends(require_superuser)):
    return svc.reveal(key)


@router.put("")
def put_settings(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                 user: User = Depends(require_superuser)):
    def log(keys: list[str]) -> None:
        # LogEntry without a content type: names the changed keys, never their values
        db.execute(insert(Base.metadata.tables["django_admin_log"]).values(
            action_time=utcnow(), user_id=user.id, content_type_id=None, object_id=None,
            object_repr="System settings", action_flag=2, change_message=svc.log_message(keys)))
        db.commit()

    return svc.update_settings(payload, log)
