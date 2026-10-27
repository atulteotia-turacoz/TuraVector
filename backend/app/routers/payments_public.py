"""Payments for the user app: which gateway checkout uses (no secrets), and the gateway webhook."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.tenancy import unfiltered
from app.database import get_db
from app.models import Invoice, User
from app.services import billing, payments, subscriptions

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/config")
def checkout_config(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return payments.public_config(db)


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Backup for the checkout callback: `payment.captured` / `order.paid` mark the invoice paid (or
    activate the plan the order was for).
    Set the webhook URL and secret in the Razorpay dashboard and under Payment Gateways."""
    body = await request.body()
    gw = payments.get(db, "razorpay")
    if gw is None or not payments.ADAPTERS["razorpay"].verify(
            gw, body=body, webhook_signature=request.headers.get("X-Razorpay-Signature", "")):
        raise HTTPException(400, "Invalid signature")
    try:
        event = json.loads(body)
        payload = event.get("payload", {})
        payment = payload.get("payment", {}).get("entity", {})
        order_id = payment.get("order_id") or payload.get("order", {}).get("entity", {}).get("id")
    except (ValueError, AttributeError):
        raise HTTPException(400, "Unreadable event") from None
    if event.get("event") not in ("payment.captured", "order.paid") or not order_id:
        return {"ok": True, "ignored": True}
    if subscriptions.paid_by_webhook(db, order_id, payment.get("id") or ""):  # a plan bought from the Plans page
        db.commit()
        return {"ok": True}
    with unfiltered(db):
        inv = db.execute(select(Invoice).where(Invoice.gateway_order_id == order_id)).scalar_one_or_none()
    if inv is None or inv.status != "awaiting_payment":
        return {"ok": True, "ignored": True}
    mails = billing.mark_paid(db, inv, payment.get("id") or order_id, None, "Confirmed by Razorpay webhook")
    billing.notify_in_app(db, mails, None)
    db.commit()
    billing.send(db, mails)
    return {"ok": True}
