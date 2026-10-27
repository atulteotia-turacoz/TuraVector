"""Plans & subscriptions for the user app: the plans page, subscribing, paying and renewing.

Individual users manage their own workspace's plans; a university / organisation's plans are
managed by its administrator, and its members only see what the workspace has.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import PermissionChecker
from app.core.tenancy import active_membership, unfiltered
from app.database import get_db
from app.models import Invoice, OrgSubscription, SubscriptionPlan, User
from app.services import billing, payments
from app.services.external_apps import card_visible, cards
from app.services import subscriptions as svc

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def _manageable(db: Session, user: User):
    org = svc.manageable_org(db, user)
    if org is None:
        raise HTTPException(403, "Plans for your workspace are managed by its administrator.")
    return org


def _own_sub(db: Session, org_id: int, sub_id: int) -> OrgSubscription:
    sub = db.get(OrgSubscription, sub_id)
    if sub is None or sub.organisation_id != org_id:
        raise HTTPException(404, "Subscription not found")
    return sub


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.SubscriptionError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/catalogue")
def catalogue(db: Session = Depends(get_db)):
    """Public pricing for the landing page: the active tools and every active plan."""
    try:
        tools, plans = svc.active_tools(db), svc.plans_for(db, None)
    except Exception:  # noqa: BLE001 — the landing page must load if the plans tables aren't set up
        return {"tools": [], "plans": []}
    return {"tools": [svc.tool_payload(t) for t in tools], "plans": [svc.plan_payload(p) for p in plans]}


@router.get("")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Plans the workspace can choose, the tools catalogue and the workspace's subscriptions."""
    m = None if user.is_superuser else active_membership(db, user)
    org = m.organisation if m else None
    can_manage = svc.manageable_org(db, user) is not None
    # same rules as the home page cards: plans, free tools and per-user access set by an administrator
    checker = PermissionChecker(db, user)
    entitled = {c.key for c in cards(db) if card_visible(checker, user, c)}
    names = svc.tool_names(db)
    subs = svc.org_subscriptions(db, org.id) if org is not None else []
    return {
        "workspace": {"name": org.name, "kind": org.kind} if org else None,
        "can_manage": can_manage,
        "payment_available": payments.public_config(db).get("gateway") == "razorpay",
        "trial_available": can_manage and org is not None and svc.trial_available(db, org),
        "billing_missing": billing.profile_missing(billing.profile_of(db, org.id)) if can_manage and org else [],
        "tools": [{**svc.tool_payload(t), "has_access": t.key in entitled} for t in svc.active_tools(db)],
        "plans": [svc.plan_payload(p) for p in svc.plans_for(db, org)] if org is not None and org.kind != "system" else [],
        "subscriptions": [svc.subscription_payload(s, names) for s in subs
                          if can_manage or svc.state_of(s) in ("active", "scheduled")],
    }


class SubscribeIn(BaseModel):
    plan_id: int


@router.post("/subscribe")
def subscribe(body: SubscribeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _manageable(db, user)
    plan = db.get(SubscriptionPlan, body.plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    sub = _call(svc.subscribe, db, org, plan, user, "self")
    db.commit()
    return _result(db, sub)


def _result(db: Session, sub: OrgSubscription) -> dict:
    if sub.status == "active":
        msg = (f"Your {sub.plan_name} free trial has started." if sub.is_trial
               else f"{sub.plan_name} is now active.")
        return {"subscription": svc.subscription_payload(sub, svc.tool_names(db)), "payment_required": False, "message": msg}
    return {"subscription": svc.subscription_payload(sub, svc.tool_names(db)), "payment_required": True,
            "message": f"Complete the payment to activate {sub.plan_name}."}


@router.post("/{sub_id}/renew")
def renew(sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _manageable(db, user)
    sub = _own_sub(db, org.id, sub_id)
    new = _call(svc.renew, db, org, sub, user)
    db.commit()
    return _result(db, new)


@router.post("/{sub_id}/pay")
def start_payment(sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _manageable(db, user)
    order = _call(svc.start_payment, db, _own_sub(db, org.id, sub_id), user)
    db.commit()
    return order


class VerifyIn(BaseModel):
    order_id: str
    payment_id: str
    signature: str


@router.post("/{sub_id}/pay/verify")
def verify_payment(sub_id: int, body: VerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _manageable(db, user)
    sub = _own_sub(db, org.id, sub_id)
    _call(svc.verify_payment, db, sub, body.order_id, body.payment_id, body.signature)
    db.commit()
    return {"subscription": svc.subscription_payload(sub, svc.tool_names(db)),
            "message": f"Payment received. {sub.plan_name} is now active."}


@router.post("/{sub_id}/cancel")
def cancel(sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Unpaid: dropped. Running: keeps its tools until the end of the paid period (no refund).
    A paid renewal that hasn't started: cancelled and refunded by Turacoz."""
    org = _manageable(db, user)
    sub = _own_sub(db, org.id, sub_id)
    message = _call(svc.cancel, db, sub, user)
    db.commit()
    return {"message": message, "subscription": svc.subscription_payload(sub, svc.tool_names(db))}


@router.post("/{sub_id}/resume")
def resume(sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _manageable(db, user)
    sub = _own_sub(db, org.id, sub_id)
    message = _call(svc.resume, db, sub, user)
    db.commit()
    return {"message": message, "subscription": svc.subscription_payload(sub, svc.tool_names(db))}


# ------------------------------------------------------------------ billing details, invoices and receipts
def _details(org, p) -> dict:
    d = billing.profile_payload(org, p)
    return {k: d[k] for k in ("legal_name", "address", "state", "state_code", "country", "gstin", "billing_email", "missing")}


@router.get("/billing")
def billing_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The workspace's billing details (who invoices are made out to) and its plan invoices."""
    org = _manageable(db, user)
    with unfiltered(db):
        invoices = db.execute(select(Invoice).where(Invoice.organisation_id == org.id, Invoice.cycle == "subscription")
                              .order_by(Invoice.created_at.desc(), Invoice.id.desc())).scalars().all()
    plan_of = {s.invoice_id: s for s in svc.org_subscriptions(db, org.id) if s.invoice_id}
    return {
        "details": _details(org, billing.profile_of(db, org.id)),
        "invoices": [{**billing.invoice_row(inv), "subtotal": float(inv.subtotal), "tax": float(inv.cgst + inv.sgst + inv.igst),
                      "payment_id": inv.payment_id,
                      "plan_name": plan_of[inv.id].plan_name if inv.id in plan_of else (inv.lines[0].description if inv.lines else "")}
                     for inv in invoices],
    }


class BillingDetailsIn(BaseModel):
    legal_name: str = ""
    address: str = ""
    state: str = ""
    state_code: str = ""
    country: str = "India"
    gstin: str = ""
    billing_email: str = ""


@router.put("/billing")
def save_billing_details(body: BillingDetailsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _manageable(db, user)
    try:
        p = billing.save_profile(db, org, user, body.model_dump(), allow_cycle=False)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None
    if billing.profile_missing(p):
        raise HTTPException(400, "Choose your state — GST depends on it.")
    for s in svc.org_subscriptions(db, org.id):  # GST on plans still to be paid follows the new details
        if s.status == "pending":
            svc.apply_tax(db, s, s.plan)
    db.commit()
    return {"message": "Billing details saved.", "details": _details(org, p)}


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A plan invoice with everything needed to print it as a tax invoice or a payment receipt."""
    org = _manageable(db, user)
    with unfiltered(db):
        inv = db.get(Invoice, invoice_id)
    if inv is None or inv.organisation_id != org.id or inv.cycle != "subscription":
        raise HTTPException(404, "Invoice not found")
    d = billing.invoice_detail(db, inv)
    return {k: d[k] for k in ("id", "number", "status", "status_label", "currency", "period_start", "period_end",
                              "created_at", "paid_at", "payment_id", "tax_mode", "tax_mode_label", "subtotal", "cgst",
                              "sgst", "igst", "total", "amount_in_words", "seller", "buyer", "lines")} | {
        "gateway": inv.gateway}
