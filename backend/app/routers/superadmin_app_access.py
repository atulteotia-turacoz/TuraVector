"""Superadmin: which dashboard-selection cards each user sees.

Visibility is set **per user only** (roles are not used for cards):
- Visible → UserPermission(user, card permission, is_granted=1)
- Hidden  → UserPermission(..., is_granted=0) — an explicit deny, so a role that happens to hold the
            same permission can't reopen the dashboard through the normal permission check.
Superusers always see every card; managers always see Content Lab.
Every change is written to django_admin_log like other admin changes.
"""
import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.core.permissions import PermissionChecker
from app.core.utils import full_name
from app.database import get_db
from app.models import Permission, User, UserPermission
from app.services import superadmin_core as core
from app.services.external_apps import APPS, CARD_BY_KEY, CARDS, Card, card_permission, card_visible

router = APIRouter(prefix="/api/superadmin/app-access", tags=["superadmin"])
PAGE_SIZE = 25


def _card(key: str) -> Card:
    if key not in CARD_BY_KEY:
        raise HTTPException(404, "Unknown card")
    return CARD_BY_KEY[key]


def _cell(user: User, card: Card, checker: PermissionChecker, setting: bool | None) -> dict:
    manager_like = user.user_type == "manager" or bool(user.is_manager)
    if user.is_superuser:
        source = "superuser"
    elif card.key == "content_lab" and manager_like:
        source = "manager"
    else:
        source = "visible" if setting is True else "hidden"
    return {"visible": card_visible(checker, user, card), "source": source, "locked": source in ("superuser", "manager")}


def _cards_meta() -> list[dict]:
    urls = {a.key: a.url for a in APPS}
    return [{"key": c.key, "name": c.name, "kind": c.kind, "url": urls.get(c.key)} for c in CARDS]


def _settings(db: Session, perms: dict[str, Permission], user_ids: list[int]) -> dict[tuple[int, str], bool]:
    by_perm = {p.id: key for key, p in perms.items()}
    return {(up.user_id, by_perm[up.permission_id]): bool(up.is_granted) for up in db.execute(
        select(UserPermission).where(UserPermission.user_id.in_(user_ids or [-1]),
                                     UserPermission.permission_id.in_(list(by_perm)))).scalars()}


@router.get("")
def app_access(search: str = "", page: int = 1, db: Session = Depends(get_db), admin: User = Depends(require_superuser)):
    perms = {c.key: card_permission(db, c) for c in CARDS}
    stmt = select(User).where(User.is_active == 1)
    if search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like), User.first_name.ilike(like),
                              User.last_name.ilike(like), func.concat(User.first_name, " ", User.last_name).ilike(like)))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(1, page), pages)
    users = db.execute(stmt.order_by(User.first_name, User.last_name, User.username)
                       .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)).scalars().all()
    settings_ = _settings(db, perms, [u.id for u in users])
    items = []
    for u in users:
        checker = PermissionChecker(db, u)
        items.append({"id": u.id, "name": full_name(u), "username": u.username, "email": u.email,
                      "is_superuser": bool(u.is_superuser),
                      "cards": {c.key: _cell(u, c, checker, settings_.get((u.id, c.key))) for c in CARDS}})
    return {"cards": _cards_meta(), "users": {"items": items, "total": total, "page": page, "pages": pages}}


@router.get("/users/{user_id}")
def user_cards(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_superuser)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    perms = {c.key: card_permission(db, c) for c in CARDS}
    settings_ = _settings(db, perms, [target.id])
    checker = PermissionChecker(db, target)
    return {"user": {"id": target.id, "name": full_name(target), "is_superuser": bool(target.is_superuser)},
            "cards": [{**m, **_cell(target, CARD_BY_KEY[m["key"]], checker, settings_.get((target.id, m["key"])))}
                      for m in _cards_meta()]}


class UserCardIn(BaseModel):
    user_id: int
    card: str
    visible: bool


def _set(db: Session, admin: User, target: User, card: Card, visible: bool) -> None:
    perm = card_permission(db, card)
    up = db.execute(select(UserPermission).where(UserPermission.user_id == target.id,
                                                 UserPermission.permission_id == perm.id)).scalar_one_or_none()
    granted = 1 if visible else 0
    c = core.Ctx(db, admin)
    if up is None:
        up = UserPermission(user_id=target.id, permission_id=perm.id, is_granted=granted, granted_by_id=admin.id,
                            reason=f"Dashboard card set {'Visible' if visible else 'Hidden'} by {admin.username}")
        db.add(up)
        db.flush()
        core.log_action(c, "authentication.UserPermission", up.id, f"{target.username} - {card.name}", 1,
                        f"{card.name}: {'Visible' if visible else 'Hidden'}")
    elif up.is_granted != granted:
        up.is_granted = granted
        db.flush()
        core.log_action(c, "authentication.UserPermission", up.id, f"{target.username} - {card.name}", 2,
                        f"{card.name}: {'Visible' if visible else 'Hidden'}")


@router.post("/user")
def set_user_card(body: UserCardIn, db: Session = Depends(get_db), admin: User = Depends(require_superuser)):
    card = _card(body.card)
    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(404, "User not found")
    _set(db, admin, target, card, body.visible)
    db.commit()
    cell = _cell(target, card, PermissionChecker(db, target), body.visible)
    note = " (always visible for superusers)" if cell["source"] == "superuser" else \
        " (managers always see Content Lab)" if cell["source"] == "manager" else ""
    return {"success": True, "visible": cell["visible"],
            "message": f"{card.name}: {'visible' if cell['visible'] else 'hidden'} for {full_name(target)}{note}"}


class BulkIn(BaseModel):
    card: str
    visible: bool
    scope: Literal["all_active_users"] = "all_active_users"


@router.post("/bulk")
def set_card_for_everyone(body: BulkIn, db: Session = Depends(get_db), admin: User = Depends(require_superuser)):
    """Set one card Visible / Hidden for every active user at once."""
    card = _card(body.card)
    users = db.execute(select(User).where(User.is_active == 1)).scalars().all()
    for u in users:
        _set(db, admin, u, card, body.visible)
    db.commit()
    return {"success": True, "message": f"{card.name} set {'Visible' if body.visible else 'Hidden'} for all {len(users)} active users"}
