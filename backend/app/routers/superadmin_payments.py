"""Superadmin: payment gateway settings (Stripe, Razorpay, CCAvenue) — platform-wide."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.database import get_db
from app.models import User
from app.services import payments

router = APIRouter(prefix="/api/superadmin/payment-gateways", tags=["superadmin"])


def _gateway(db: Session, code: str):
    try:
        return payments.get(db, code)
    except payments.PaymentError as e:
        raise HTTPException(404, str(e)) from None


def _listing(db: Session) -> dict:
    rows = payments.ensure_rows(db)
    db.commit()
    return {"gateways": [payments.serialize(g) for g in rows], "modes": list(payments.MODES),
            "currencies": list(payments.CURRENCIES), "checkout": payments.public_config(db)}


@router.get("")
def list_gateways(_: User = Depends(require_superuser), db: Session = Depends(get_db)):
    return _listing(db)


class GatewayIn(BaseModel):
    mode: str | None = None
    currency: str | None = None
    fields: dict[str, str] = {}


@router.post("/{code}")
def save_gateway(code: str, body: GatewayIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    gw = _gateway(db, code)
    try:
        payments.update(db, gw, body.model_dump(exclude_none=True), user)
    except payments.PaymentError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from None
    db.commit()
    return {"message": f"{gw.name} settings saved.", **_listing(db)}


class EnabledIn(BaseModel):
    enabled: bool


@router.post("/{code}/enabled")
def set_enabled(code: str, body: EnabledIn, _: User = Depends(require_superuser), db: Session = Depends(get_db)):
    gw = _gateway(db, code)
    try:
        payments.set_enabled(db, gw, body.enabled)
    except payments.PaymentError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from None
    db.commit()
    return {"message": f"{gw.name} {'enabled' if body.enabled else 'disabled'}.", **_listing(db)}


@router.post("/{code}/activate")
def activate(code: str, _: User = Depends(require_superuser), db: Session = Depends(get_db)):
    gw = _gateway(db, code)
    try:
        payments.make_active(db, gw)
    except payments.PaymentError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from None
    db.commit()
    return {"message": f"Payments now go through {gw.name}.", **_listing(db)}


@router.post("/{code}/test")
def test(code: str, _: User = Depends(require_superuser), db: Session = Depends(get_db)):
    gw = _gateway(db, code)
    ok, message = payments.test_connection(db, gw)
    db.commit()
    return {"ok": ok, "message": message, **_listing(db)}
