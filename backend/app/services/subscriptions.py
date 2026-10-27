"""Plans and subscriptions: which tools a workspace has, subscribing to a plan and paying for it.

A subscription belongs to a workspace (an individual's personal workspace or a university /
organisation), so every active member of that workspace gets the plan's tools. Tools marked free
are available to everyone. Price, period and tools are copied from the plan when subscribing.

Who may subscribe: the owner of an individual workspace, or the administrator of a university /
organisation. Members of a university / organisation get tools through their administrator.

GST is added on top of the plan price; how it splits (CGST + SGST or IGST) depends on the workspace's
billing details. Paying for a plan issues a paid tax invoice in the Turacoz invoice series. A workspace
may cancel a plan: it keeps the tools until the end of the period it paid for.
"""
import calendar
import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import active_membership, is_org_admin, unfiltered
from app.core.utils import iso
from app.models import Invoice, InvoiceLine, Organisation, OrgSubscription, PlatformTool, SubscriptionPlan, User, utcnow
from app.models.subscriptions import BILLING_PERIODS, PERIOD_MONTHS, PLAN_AUDIENCES
from app.services import billing_tax, payments


class SubscriptionError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------- dates
def add_months(dt: datetime.datetime, months: int) -> datetime.datetime:
    month = dt.month - 1 + months
    year, month = dt.year + month // 12, month % 12 + 1
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


def period_end(start: datetime.datetime, period: str) -> datetime.datetime | None:
    months = PERIOD_MONTHS.get(period)
    return None if months is None else add_months(start, months)


def is_current(sub: OrgSubscription, at: datetime.datetime | None = None) -> bool:
    at = at or utcnow()
    return (sub.status == "active" and (sub.starts_at is None or sub.starts_at <= at)
            and (sub.ends_at is None or sub.ends_at > at))


def state_of(sub: OrgSubscription) -> str:
    """pending | active | scheduled (paid, starts after the current period) | expired | cancelled"""
    if sub.status != "active":
        return sub.status
    now = utcnow()
    if sub.ends_at is not None and sub.ends_at <= now:
        return "expired"
    if sub.starts_at is not None and sub.starts_at > now:
        return "scheduled"
    return "active"


# ---------------------------------------------------------------------------------------------- catalogue
def active_tools(db: Session) -> list[PlatformTool]:
    from app.services.external_apps import ensure_tools
    return [t for t in ensure_tools(db) if t.is_active]


def plans_for(db: Session, org: Organisation | None, include_inactive: bool = False) -> list[SubscriptionPlan]:
    """Plans a workspace may choose: individual workspaces see plans for individuals, universities /
    organisations see plans for organisations; plans for everyone are offered to both."""
    stmt = select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order, SubscriptionPlan.price, SubscriptionPlan.name)
    if not include_inactive:
        stmt = stmt.where(SubscriptionPlan.is_active == 1)
    if org is not None:
        stmt = stmt.where(SubscriptionPlan.audience.in_(("all", audience_of(org))))
    return list(db.execute(stmt).scalars())


def audience_of(org: Organisation) -> str:
    return "individual" if org.kind == "individual" else "organisation"


def plan_tool_keys(plan: SubscriptionPlan) -> list[str]:
    return [pt.tool.key for pt in sorted(plan.plan_tools, key=lambda pt: (pt.tool.sort_order, pt.tool.name))]


def tool_payload(t: PlatformTool) -> dict:
    return {"key": t.key, "name": t.name, "description": t.description, "features": list(t.features or []),
            "kind": t.kind, "icon": t.icon, "is_free": bool(t.is_free)}


def plan_payload(p: SubscriptionPlan) -> dict:
    tools = [pt.tool for pt in sorted(p.plan_tools, key=lambda pt: (pt.tool.sort_order, pt.tool.name))]
    return {"id": p.id, "name": p.name, "description": p.description, "price": float(p.price), "currency": p.currency,
            "tax_percent": float(p.tax_percent or 0), "sac_code": p.sac_code or "",
            "billing_period": p.billing_period, "billing_period_label": BILLING_PERIODS.get(p.billing_period, p.billing_period),
            "trial_days": p.trial_days, "audience": p.audience, "audience_label": PLAN_AUDIENCES.get(p.audience, p.audience),
            "is_featured": bool(p.is_featured), "is_active": bool(p.is_active), "sort_order": p.sort_order,
            "tools": [{"key": t.key, "name": t.name, "is_active": bool(t.is_active)} for t in tools]}


def subscription_payload(s: OrgSubscription, tool_names: dict[str, str] | None = None) -> dict:
    keys = list(s.tool_keys or [])
    return {"id": s.id, "organisation_id": s.organisation_id, "plan_id": s.plan_id, "plan_name": s.plan_name,
            "tools": [{"key": k, "name": (tool_names or {}).get(k, k)} for k in keys],
            "price": float(s.price), "currency": s.currency, "billing_period": s.billing_period,
            "billing_period_label": BILLING_PERIODS.get(s.billing_period, s.billing_period),
            "status": s.status, "state": state_of(s), "is_trial": bool(s.is_trial), "source": s.source,
            "starts_at": iso(s.starts_at), "ends_at": iso(s.ends_at), "paid_at": iso(s.paid_at),
            "payment_ref": s.payment_ref, "gateway": s.gateway, "notes": s.notes, "created_at": iso(s.created_at),
            "tax_percent": float(s.tax_percent or 0), "tax_amount": float(s.tax_amount or 0),
            "total": float(Decimal(s.price) + Decimal(s.tax_amount or 0)), "invoice_id": s.invoice_id,
            "cancelled_at": iso(s.cancelled_at), "can_cancel": can_cancel(s)}


def tool_names(db: Session) -> dict[str, str]:
    from app.services.external_apps import ensure_tools
    return {t.key: t.name for t in ensure_tools(db)}


# ---------------------------------------------------------------------------------------------- entitlements
def org_subscriptions(db: Session, org_id: int) -> list[OrgSubscription]:
    with unfiltered(db):
        return list(db.execute(select(OrgSubscription).where(OrgSubscription.organisation_id == org_id)
                               .order_by(OrgSubscription.created_at.desc(), OrgSubscription.id.desc())).scalars())


def entitled_tool_keys(db: Session, user: User) -> set[str]:
    """Tools this user has through free tools and their workspace's current subscriptions."""
    tools = active_tools(db)
    active_keys = {t.key for t in tools}
    keys = {t.key for t in tools if t.is_free}
    m = active_membership(db, user)
    if m is not None:
        for s in org_subscriptions(db, m.organisation_id):
            if is_current(s):
                keys.update(k for k in (s.tool_keys or []) if k in active_keys)
    return keys


def has_tool(db: Session, user: User, key: str) -> bool:
    return key in entitled_tool_keys(db, user)


def manageable_org(db: Session, user: User) -> Organisation | None:
    """The workspace whose plans this user may buy: their own individual workspace, or the university /
    organisation they administer."""
    if user.is_superuser:
        return None
    m = active_membership(db, user)
    if m is None:
        return None
    if m.organisation.kind == "individual" or is_org_admin(user, db):
        return m.organisation
    return None


def give_added_tools(db: Session, plan: SubscriptionPlan) -> int:
    """Tools newly added to a plan reach its running and upcoming subscriptions straight away. (Tools taken
    out of a plan stay with existing subscribers until their period ends.) Returns how many changed."""
    keys = plan_tool_keys(plan)
    changed = 0
    with unfiltered(db):
        subs = db.execute(select(OrgSubscription).where(OrgSubscription.plan_id == plan.id,
                                                        OrgSubscription.status.in_(("active", "pending")))).scalars().all()
    for s in subs:
        if s.status == "active" and state_of(s) == "expired":
            continue
        have = list(s.tool_keys or [])
        new = [k for k in keys if k not in have]
        if new:
            s.tool_keys = have + new
            changed += 1
    db.flush()
    return changed


# ---------------------------------------------------------------------------------------------- subscribing
def trial_available(db: Session, org: Organisation, subs: list[OrgSubscription] | None = None) -> bool:
    """Each workspace gets one free trial, on whichever plan it tries first."""
    return not any(s.is_trial for s in (subs if subs is not None else org_subscriptions(db, org.id)))


def _latest_end(db: Session, org_id: int, plan_id: int | None, exclude_id: int | None = None) -> datetime.datetime | None:
    """When the workspace's paid-up time on this plan runs out (renewals start from there)."""
    now = utcnow()
    end = None
    for s in org_subscriptions(db, org_id):
        if s.id == exclude_id or s.plan_id != plan_id or s.status != "active":
            continue
        if s.ends_at is None:
            return None  # lifetime already
        if s.ends_at > now and (end is None or s.ends_at > end):
            end = s.ends_at
    return end


def activate(db: Session, sub: OrgSubscription, *, payment_ref: str = "", ends_at: datetime.datetime | None = None,
             custom_end: bool = False) -> None:
    now = utcnow()
    start = _latest_end(db, sub.organisation_id, sub.plan_id, exclude_id=sub.id) or now
    sub.status = "active"
    sub.starts_at = start
    sub.ends_at = ends_at if custom_end else period_end(start, sub.billing_period)
    if payment_ref:
        sub.payment_ref, sub.paid_at = payment_ref, now
    db.flush()
    if payment_ref and Decimal(sub.price) > 0 and sub.invoice_id is None:
        issue_invoice(db, sub)


def subscribe(db: Session, org: Organisation, plan: SubscriptionPlan, user: User | None, source: str = "self") -> OrgSubscription:
    """Start a subscription. Free plans and the workspace's first trial are active at once; otherwise it waits
    for payment."""
    if not plan.is_active:
        raise SubscriptionError("This plan is no longer available.")
    if plan.audience not in ("all", audience_of(org)):
        raise SubscriptionError("This plan is not available for your workspace.")
    if not plan.plan_tools:
        raise SubscriptionError("This plan has no tools yet.")
    subs = org_subscriptions(db, org.id)
    can_trial = trial_available(db, org, subs)
    for s in subs:  # an unpaid earlier attempt is replaced by this one
        if s.plan_id == plan.id and s.status == "pending":
            s.status = "cancelled"
            s.notes = (s.notes + " Replaced by a new attempt.").strip()
    sub = OrgSubscription(organisation_id=org.id, plan_id=plan.id, plan_name=plan.name, tool_keys=plan_tool_keys(plan),
                          price=plan.price, currency=plan.currency, billing_period=plan.billing_period, status="pending",
                          is_trial=0, source=source, gateway="", gateway_order_id="", payment_ref="", notes="",
                          created_by_id=user.id if user else None)
    db.add(sub)
    apply_tax(db, sub, plan)
    db.flush()
    if Decimal(plan.price) <= 0:
        activate(db, sub)
    elif plan.trial_days > 0 and can_trial:
        sub.is_trial, sub.status, sub.starts_at = 1, "active", utcnow()
        sub.ends_at = sub.starts_at + datetime.timedelta(days=plan.trial_days)
        sub.notes = f"{plan.trial_days}-day free trial."
    db.flush()
    return sub


REQUESTED_NOTE = "Requested at sign-up; starts when the workspace is approved."


def request_plan(db: Session, org: Organisation, plan: SubscriptionPlan, user: User) -> OrgSubscription:
    """A university / organisation picks its plan while registering. The workspace still needs approval,
    so the plan is only recorded here; start_requested() starts it on approval."""
    if not plan.is_active or plan.audience not in ("all", audience_of(org)) or not plan.plan_tools:
        raise SubscriptionError("The selected plan is not available. Please choose another plan.")
    sub = OrgSubscription(organisation_id=org.id, plan_id=plan.id, plan_name=plan.name, tool_keys=plan_tool_keys(plan),
                          price=plan.price, currency=plan.currency, billing_period=plan.billing_period, status="pending",
                          is_trial=0, source="signup", gateway="", gateway_order_id="", payment_ref="",
                          notes=REQUESTED_NOTE, created_by_id=user.id)
    db.add(sub)
    apply_tax(db, sub, plan)
    db.flush()
    return sub


def requested_plan(db: Session, org: Organisation) -> OrgSubscription | None:
    return next((s for s in org_subscriptions(db, org.id) if s.status == "pending" and s.notes == REQUESTED_NOTE), None)


def start_requested(db: Session, org: Organisation) -> OrgSubscription | None:
    """On approval: a free plan or the workspace's trial starts now (no trial days lost while waiting);
    a paid plan stays waiting for payment, which the workspace administrator makes after signing in."""
    sub = requested_plan(db, org)
    if sub is None:
        return None
    sub.notes = "Chosen at sign-up."
    plan = sub.plan
    if plan is None or not plan.is_active:
        sub.status, sub.notes = "cancelled", "The plan chosen at sign-up is no longer available."
    elif Decimal(sub.price) <= 0:
        activate(db, sub)
    elif plan.trial_days > 0 and trial_available(db, org):
        sub.is_trial, sub.status, sub.starts_at = 1, "active", utcnow()
        sub.ends_at = sub.starts_at + datetime.timedelta(days=plan.trial_days)
        sub.notes = f"{plan.trial_days}-day free trial, chosen at sign-up."
    db.flush()
    return sub


def renew(db: Session, org: Organisation, sub: OrgSubscription, user: User) -> OrgSubscription:
    """Buy the same plan again (after a trial or to extend). Uses the plan's current price."""
    if sub.plan is None:
        raise SubscriptionError("This plan is no longer available.")
    plan = sub.plan
    if not plan.is_active:
        raise SubscriptionError("This plan is no longer available.")
    new = OrgSubscription(organisation_id=org.id, plan_id=plan.id, plan_name=plan.name, tool_keys=plan_tool_keys(plan),
                          price=plan.price, currency=plan.currency, billing_period=plan.billing_period, status="pending",
                          is_trial=0, source="self", gateway="", gateway_order_id="", payment_ref="", notes="Renewal",
                          created_by_id=user.id)
    db.add(new)
    apply_tax(db, new, plan)
    db.flush()
    if Decimal(plan.price) <= 0:
        activate(db, new)
    return new


# ---------------------------------------------------------------------------------------------- payment
def start_payment(db: Session, sub: OrgSubscription, user: User) -> dict:
    if sub.status != "pending":
        raise SubscriptionError("Only a subscription awaiting payment can be paid.")
    from app.services import billing
    if billing.profile_missing(billing.profile_of(db, sub.organisation_id)):
        raise SubscriptionError("Add your billing details (country and state) first — GST on the invoice depends on them.")
    apply_tax(db, sub, sub.plan)
    gw = payments.active(db)
    if gw is None or payments.missing_fields(gw):
        raise SubscriptionError("Online payment has not been set up yet. Please contact Turacoz to activate this plan.")
    if gw.code != "razorpay":
        raise SubscriptionError(f"Online payment through {payments.SPECS[gw.code].name} is not available yet.")
    try:
        order = payments.ADAPTERS[gw.code].create_order(gw, total_of(sub), f"SUB-{sub.id}", {"subscription": str(sub.id)})
    except payments.PaymentError as exc:
        raise SubscriptionError(str(exc)) from None
    sub.gateway, sub.gateway_order_id = gw.code, order["order_id"]
    db.flush()
    return {**order, "name": "TuraVector", "description": f"{sub.plan_name} ({BILLING_PERIODS.get(sub.billing_period, '')})",
            "prefill": {"name": billing.name_of(user), "email": user.email or "", "contact": user.phone or ""}}


def verify_payment(db: Session, sub: OrgSubscription, order_id: str, payment_id: str, signature: str) -> None:
    gw = payments.get(db, sub.gateway or "razorpay")
    if (not sub.gateway_order_id or order_id != sub.gateway_order_id or gw is None
            or not payments.ADAPTERS[gw.code].verify(gw, order_id=order_id, payment_id=payment_id, signature=signature)):
        raise SubscriptionError("The payment could not be verified. If money was deducted, contact Turacoz with the payment reference.")
    if sub.status == "pending":
        activate(db, sub, payment_ref=payment_id)


def paid_by_webhook(db: Session, order_id: str, payment_id: str) -> bool:
    """Razorpay webhook backup: activate the subscription this order belongs to. True if one was found."""
    with unfiltered(db):
        sub = db.execute(select(OrgSubscription).where(OrgSubscription.gateway_order_id == order_id)).scalar_one_or_none()
    if sub is None:
        return False
    if sub.status == "pending":
        activate(db, sub, payment_ref=payment_id or order_id)
        sub.notes = (sub.notes + " Confirmed by Razorpay webhook.").strip()
    return True


# ---------------------------------------------------------------------------------------------- GST and invoices
def total_of(sub: OrgSubscription) -> Decimal:
    return Decimal(sub.price) + Decimal(sub.tax_amount or 0)


def apply_tax(db: Session, sub: OrgSubscription, plan: SubscriptionPlan | None) -> None:
    """Work out the GST on top of the price from the workspace's billing details (re-done just before paying,
    so details filled in after subscribing count)."""
    from app.services import billing
    if plan is not None:
        sub.tax_percent = plan.tax_percent or 0
    s = billing.settings_row(db)
    p = billing.profile_of(db, sub.organisation_id)
    buyer = billing._buyer(sub.organisation or db.get(Organisation, sub.organisation_id), p)
    sub.tax_mode = billing_tax.tax_mode(s.state, s.state_code, buyer["state"], buyer["state_code"], buyer["country"])
    cgst, sgst, igst = billing_tax.line_tax(sub.price, sub.tax_percent, False, sub.tax_mode)
    sub.tax_amount = cgst + sgst + igst


def issue_invoice(db: Session, sub: OrgSubscription, actor: User | None = None) -> Invoice:
    """The paid tax invoice for a plan payment, numbered in the Turacoz invoice series."""
    from app.services import billing
    org = sub.organisation or db.get(Organisation, sub.organisation_id)
    s = billing.settings_row(db)
    period = BILLING_PERIODS.get(sub.billing_period, sub.billing_period)
    span = (f" · {sub.starts_at:%d %b %Y} – {sub.ends_at:%d %b %Y}" if sub.starts_at and sub.ends_at else "")
    inv = Invoice(number=billing.next_number(db), organisation_id=org.id, cycle="subscription", status="paid",
                  tax_mode=sub.tax_mode or "inter", currency=sub.currency, seller=billing._seller(s),
                  buyer=billing._buyer(org, billing.profile_of(db, org.id)),
                  period_start=sub.starts_at.date() if sub.starts_at else None,
                  period_end=sub.ends_at.date() if sub.ends_at else None,
                  gateway=sub.gateway or "", gateway_order_id="", payment_id=sub.payment_ref[:100],
                  paid_at=sub.paid_at or utcnow())
    db.add(inv)
    inv.lines.append(InvoiceLine(description=f"{sub.plan_name} plan ({period}){span}"[:400],
                                 sac_code=(sub.plan.sac_code if sub.plan else "") or "", unit="", quantity=1,
                                 rate=sub.price, amount=0, tax_percent=sub.tax_percent or 0, tax_overseas=0))
    billing.recalculate(inv)
    billing._event(inv, actor, "paid", f"Plan payment {sub.payment_ref}".strip())
    db.flush()
    sub.invoice_id = inv.id
    db.flush()
    return inv


# ---------------------------------------------------------------------------------------------- cancelling
def can_cancel(sub: OrgSubscription) -> bool:
    if sub.status == "pending":
        return True
    if sub.status != "active" or sub.cancelled_at is not None:
        return False
    st = state_of(sub)
    if st == "scheduled":
        return True
    # a paid plan with no end date has nothing left to cancel; free lifetime plans can be dropped
    return st == "active" and (sub.ends_at is not None or Decimal(sub.price) <= 0 or bool(sub.is_trial))


def cancel(db: Session, sub: OrgSubscription, user: User) -> str:
    """Cancel by the workspace. Unpaid: dropped. Running: keeps its tools until its end date, no refund.
    A paid renewal that hasn't started yet: cancelled, and Turacoz refunds it."""
    if not can_cancel(sub):
        raise SubscriptionError("This plan can't be cancelled. Please contact Turacoz.")
    now = utcnow()
    when = f"{now:%d %b %Y}"
    if sub.status == "pending":
        sub.status = "cancelled"
        return f"{sub.plan_name} was cancelled."
    st = state_of(sub)
    if st == "scheduled":
        sub.status, sub.cancelled_at = "cancelled", now
        paid = f"₹{total_of(sub):,.2f}"
        sub.notes = (f"{sub.notes} Cancelled before it started on {when} by {user.username} — "
                     f"refund {paid} (payment {sub.payment_ref or '—'}).").strip()[:500]
        return f"{sub.plan_name} was cancelled before it started. Turacoz will refund {paid} to you."
    if sub.ends_at is None:
        sub.status, sub.cancelled_at, sub.ends_at = "cancelled", now, now
        sub.notes = f"{sub.notes} Cancelled on {when} by {user.username}.".strip()[:500]
        return f"{sub.plan_name} was cancelled."
    sub.cancelled_at = now
    sub.notes = f"{sub.notes} Cancelled on {when} by {user.username}; runs until it ends.".strip()[:500]
    return f"{sub.plan_name} is cancelled. You keep its tools until {sub.ends_at:%d %b %Y}."


def resume(db: Session, sub: OrgSubscription, user: User) -> str:
    """Undo a cancellation while the plan is still running."""
    if sub.status != "active" or sub.cancelled_at is None or state_of(sub) != "active":
        raise SubscriptionError("Only a cancelled plan that is still running can be kept.")
    sub.cancelled_at = None
    sub.notes = f"{sub.notes} Kept by {user.username} on {utcnow():%d %b %Y}.".strip()[:500]
    return f"{sub.plan_name} will continue."


# ---------------------------------------------------------------------------------------------- home page
def store_summary(db: Session, user: User, accessible: dict[str, bool]) -> dict:
    """For the dashboard-selection page: the workspace's plans, payments still due, and the tools the user
    doesn't have yet together with the plans that include them."""
    empty = {"can_manage_plans": False, "subscriptions": [], "pending": [], "locked_tools": []}
    m = None if user.is_superuser else active_membership(db, user)
    if m is None or m.organisation.kind == "system":
        return empty
    org = m.organisation
    names = tool_names(db)
    subs = org_subscriptions(db, org.id)
    current = [subscription_payload(s, names) for s in subs if state_of(s) in ("active", "scheduled")]
    pending = [subscription_payload(s, names) for s in subs if s.status == "pending"]
    plans = plans_for(db, org)
    locked = []
    for t in active_tools(db):
        if accessible.get(t.key):
            continue
        offers = [p for p in plans if any(pt.tool_id == t.id for pt in p.plan_tools)]
        if offers:
            cheapest = min(offers, key=lambda p: p.price)
            locked.append({**tool_payload(t), "plan_count": len(offers), "from_price": float(cheapest.price),
                           "currency": cheapest.currency,
                           "from_period": BILLING_PERIODS.get(cheapest.billing_period, cheapest.billing_period)})
    can_manage = manageable_org(db, user) is not None
    return {"can_manage_plans": can_manage, "subscriptions": current, "pending": pending if can_manage else [],
            "locked_tools": locked}
