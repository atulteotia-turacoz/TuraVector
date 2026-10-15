"""Superadmin: rate cards.

* The standard rate card is the list of services (`rate_service`), each with its standard rate.
* A university / organisation has its own, separate rate card: services picked from the standard
  list, each at that workspace's own rate (`rate_card_item`). A service that is not on the standard
  list is added there first.
"""
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.core.utils import iso
from app.database import get_db
from app.models import Organisation, RateCardItem, RateService, User
from app.models.rates import RATE_UNITS

router = APIRouter(prefix="/api/superadmin/rates", tags=["superadmin"])


def _money(value, label: str, max_value: Decimal | None = None) -> Decimal:
    try:
        v = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(400, f"{label} must be a number.") from None
    if v < 0 or (max_value is not None and v > max_value):
        raise HTTPException(400, f"{label} must be between 0 and {max_value}." if max_value else f"{label} cannot be negative.")
    return v


def _service_row(s: RateService, used_by: int = 0) -> dict:
    return {"id": s.id, "name": s.name, "description": s.description, "unit": s.unit, "sac_code": s.sac_code,
            "tax_overseas": bool(s.tax_overseas),
            "unit_label": RATE_UNITS.get(s.unit, s.unit or ""), "standard_rate": float(s.standard_rate),
            "tax_percent": float(s.tax_percent), "currency": s.currency, "is_active": bool(s.is_active),
            "sort_order": s.sort_order, "used_by": used_by, "updated_at": iso(s.updated_at)}


# ------------------------------------------------------------------ standard rate card
@router.get("/services")
def list_services(_=Depends(require_superuser), db: Session = Depends(get_db)):
    used = dict(db.execute(select(RateCardItem.service_id, func.count(func.distinct(RateCardItem.organisation_id)))
                           .group_by(RateCardItem.service_id)).all())
    services = db.execute(select(RateService).order_by(RateService.sort_order, RateService.name)).scalars().all()
    return {"services": [_service_row(s, used.get(s.id, 0)) for s in services],
            "units": [{"value": k, "label": v} for k, v in RATE_UNITS.items()]}


class ServiceIn(BaseModel):
    name: str
    description: str = ""
    unit: str = ""  # optional: "" = no unit
    standard_rate: float | str = 0
    tax_percent: float | str = 18
    sac_code: str = ""
    tax_overseas: bool = False
    is_active: bool = True
    sort_order: int = 0


def _apply(db: Session, s: RateService, body: ServiceIn, user: User) -> None:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Service name is required.")
    if body.unit and body.unit not in RATE_UNITS:
        raise HTTPException(400, "Choose a valid unit.")
    clash = db.execute(select(RateService.id).where(func.lower(RateService.name) == name.lower(),
                                                    RateService.id != (s.id or 0))).first()
    if clash:
        raise HTTPException(400, f'A service named "{name}" already exists.')
    s.name, s.description, s.unit = name[:150], body.description.strip()[:500], body.unit
    s.standard_rate = _money(body.standard_rate, "Standard rate")
    s.tax_percent = _money(body.tax_percent, "Tax", Decimal("100"))
    s.sac_code, s.tax_overseas = body.sac_code.strip()[:20], 1 if body.tax_overseas else 0
    s.is_active, s.sort_order, s.updated_by_id = 1 if body.is_active else 0, body.sort_order, user.id


@router.post("/services")
def create_service(body: ServiceIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    s = RateService(currency="INR")
    _apply(db, s, body, user)
    db.add(s)
    db.commit()
    return {"message": f'"{s.name}" added to the standard rate card.', "service": _service_row(s)}


@router.put("/services/{service_id}")
def update_service(service_id: int, body: ServiceIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    s = db.get(RateService, service_id)
    if s is None:
        raise HTTPException(404, "Service not found")
    _apply(db, s, body, user)
    db.commit()
    return {"message": f'"{s.name}" updated.', "service": _service_row(s)}


@router.delete("/services/{service_id}")
def delete_service(service_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    s = db.get(RateService, service_id)
    if s is None:
        raise HTTPException(404, "Service not found")
    used = db.scalar(select(func.count()).select_from(RateCardItem).where(RateCardItem.service_id == s.id))
    if used:
        raise HTTPException(400, f'"{s.name}" is on {used} rate card(s). Remove it from them first, or mark it inactive.')
    name = s.name
    db.delete(s)
    db.commit()
    return {"message": f'"{name}" removed from the standard rate card.'}


# ------------------------------------------------------------------ a workspace's rate card
def _org(db: Session, org_id: int) -> Organisation:
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(404, "Organisation not found")
    return org


def _card(db: Session, org: Organisation) -> dict:
    items = db.execute(select(RateCardItem).join(RateService, RateService.id == RateCardItem.service_id)
                       .where(RateCardItem.organisation_id == org.id)
                       .order_by(RateService.sort_order, RateService.name)).scalars().all()
    on_card = {i.service_id for i in items}
    available = db.execute(select(RateService).where(RateService.is_active == 1, RateService.id.not_in(on_card or {-1}))
                           .order_by(RateService.sort_order, RateService.name)).scalars().all()
    rows = []
    for i in items:
        s = i.service
        rows.append({
            "id": i.id, "service_id": s.id, "name": s.name, "description": s.description, "unit": s.unit,
            "unit_label": RATE_UNITS.get(s.unit, s.unit or ""), "currency": s.currency, "tax_percent": float(s.tax_percent),
            "standard_rate": float(s.standard_rate), "rate": float(i.rate),
            "difference": float(i.rate - s.standard_rate), "service_active": bool(s.is_active),
            "notes": i.notes, "updated_at": iso(i.updated_at),
        })
    return {"organisation": {"id": org.id, "name": org.name, "kind": org.kind}, "items": rows,
            "available": [_service_row(s) for s in available]}


@router.get("/organisations/{org_id}")
def rate_card(org_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    return _card(db, _org(db, org_id))


class AddItem(BaseModel):
    service_id: int
    rate: float | str | None = None  # default: the service's standard rate


class AddItemsIn(BaseModel):
    items: list[AddItem]


@router.post("/organisations/{org_id}/items")
def add_items(org_id: int, body: AddItemsIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    """Put standard services on the workspace's rate card (at the standard rate unless a rate is given)."""
    org = _org(db, org_id)
    if org.kind not in ("university", "organisation"):
        raise HTTPException(400, "Rate cards are for universities and organisations.")
    if not body.items:
        raise HTTPException(400, "Choose at least one service.")
    added = []
    for it in body.items:
        s = db.get(RateService, it.service_id)
        if s is None:
            raise HTTPException(400, "That service is not on the standard rate card. Add it there first.")
        if db.execute(select(RateCardItem.id).where(RateCardItem.organisation_id == org.id,
                                                    RateCardItem.service_id == s.id)).first():
            continue
        rate = s.standard_rate if it.rate in (None, "") else _money(it.rate, f"Rate for {s.name}")
        db.add(RateCardItem(organisation_id=org.id, service_id=s.id, rate=rate, notes="", updated_by_id=user.id))
        added.append(s.name)
    db.commit()
    message = f"Added {len(added)} service{'s' if len(added) != 1 else ''} to {org.name}'s rate card." if added \
        else "Those services are already on the rate card."
    return {"message": message, **_card(db, org)}


class ItemIn(BaseModel):
    rate: float | str
    notes: str = ""


@router.put("/organisations/{org_id}/items/{item_id}")
def update_item(org_id: int, item_id: int, body: ItemIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    item = db.get(RateCardItem, item_id)
    if item is None or item.organisation_id != org.id:
        raise HTTPException(404, "Rate not found")
    item.rate = _money(body.rate, "Rate")
    item.notes, item.updated_by_id = body.notes.strip()[:300], user.id
    db.commit()
    return {"message": f"{item.service.name}: rate for {org.name} updated.", **_card(db, org)}


@router.delete("/organisations/{org_id}/items/{item_id}")
def remove_item(org_id: int, item_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    item = db.get(RateCardItem, item_id)
    if item is None or item.organisation_id != org.id:
        raise HTTPException(404, "Rate not found")
    name = item.service.name
    db.delete(item)
    db.commit()
    return {"message": f"{name} removed from {org.name}'s rate card.", **_card(db, org)}
