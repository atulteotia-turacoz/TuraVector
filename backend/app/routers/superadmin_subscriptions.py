"""Superadmin: tools catalogue, subscription plans and workspace subscriptions.

* Tools & Services — every tool a workspace can use. Built-in tools (the TuraVector dashboards and the
  Tura applications) can be renamed, described, priced through plans, made free or switched off; new
  applications are added here with their link.
* Plans & Pricing — a plan is a set of tools at a price for a period, offered to individuals,
  universities / organisations or both. Users choose plans at sign-up and on their Plans page.
* Subscriptions — every workspace's subscriptions; a plan can be given to a workspace directly
  (offline payment, complimentary) and a subscription can be cancelled or its end date changed.
"""
import datetime
import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.core.utils import iso
from app.database import get_db
from app.models import Organisation, OrgSubscription, PlatformTool, SubscriptionPlan, SubscriptionPlanTool, User
from app.models.subscriptions import BILLING_PERIODS, PLAN_AUDIENCES
from app.services import subscriptions as svc
from app.services.external_apps import APP_BY_KEY, app_of, ensure_permissions, ensure_tools, forget_tools

router = APIRouter(prefix="/api/superadmin/subscriptions", tags=["superadmin"])
PAGE_SIZE = 25
ICONS = ("flask", "file-text", "brain", "graduation-cap", "spell-check", "book-open", "bar-chart", "search",
         "pen-tool", "message-square", "layers", "globe", "shield", "sparkles", "app-window")


def _money(value, label: str) -> Decimal:
    try:
        v = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(400, f"{label} must be a number.") from None
    if v < 0:
        raise HTTPException(400, f"{label} cannot be negative.")
    return v


def _features(lines: list[str]) -> list[str]:
    return [f.strip()[:150] for f in lines if f and f.strip()][:12]


# ------------------------------------------------------------------ tools
def _plan_counts(db: Session) -> dict[int, int]:
    return dict(db.execute(select(SubscriptionPlanTool.tool_id, func.count()).group_by(SubscriptionPlanTool.tool_id)).all())


def _tool_row(t: PlatformTool, plan_count: int = 0) -> dict:
    default = APP_BY_KEY[t.key].url if t.key in APP_BY_KEY else ""
    return {**svc.tool_payload(t), "id": t.id, "url": t.url, "launch_url": app_of(t).url if t.kind == "app" else "",
            "default_url": default,
            "is_builtin": bool(t.is_builtin), "is_active": bool(t.is_active), "sort_order": t.sort_order,
            "plan_count": plan_count, "updated_at": iso(t.updated_at)}


@router.get("/tools")
def list_tools(_=Depends(require_superuser), db: Session = Depends(get_db)):
    counts = _plan_counts(db)
    return {"tools": [_tool_row(t, counts.get(t.id, 0)) for t in ensure_tools(db)], "icons": list(ICONS)}


class ToolIn(BaseModel):
    key: str = ""
    name: str
    description: str = ""
    features: list[str] = []
    url: str = ""
    icon: str = ""
    is_free: bool = False
    is_active: bool = True
    sort_order: int = 0


def _apply_tool(db: Session, t: PlatformTool, body: ToolIn, user: User) -> None:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Tool name is required.")
    clash = db.execute(select(PlatformTool.id).where(func.lower(PlatformTool.name) == name.lower(),
                                                     PlatformTool.id != (t.id or 0))).first()
    if clash:
        raise HTTPException(400, f'A tool named "{name}" already exists.')
    if t.kind == "app":
        url = body.url.strip()
        if url and not re.match(r"^https?://", url):
            raise HTTPException(400, "The link must start with https://")
        if not url and not t.is_builtin:
            raise HTTPException(400, "Enter the application's link, starting with https://")
        t.url = url[:500]  # empty on a built-in app = the link from the server settings
    t.name, t.description, t.features = name[:150], body.description.strip()[:500], _features(body.features)
    t.icon = body.icon if body.icon in ICONS else ""
    t.is_free, t.is_active = 1 if body.is_free else 0, 1 if body.is_active else 0
    t.sort_order, t.updated_by_id = body.sort_order, user.id


@router.post("/tools")
def create_tool(body: ToolIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    key = re.sub(r"[^a-z0-9]+", "_", (body.key or body.name).strip().lower()).strip("_")[:50]
    if not key:
        raise HTTPException(400, "Tool key is required.")
    key = key if key.startswith("ext_") else f"ext_{key}"
    if db.execute(select(PlatformTool.id).where(PlatformTool.key == key)).first():
        raise HTTPException(400, f'The key "{key}" is already used by another tool.')
    t = PlatformTool(key=key, kind="app", is_builtin=0)
    _apply_tool(db, t, body, user)
    db.add(t)
    db.flush()
    forget_tools(db)
    ensure_permissions(db)  # its card can also be set per user under Application Access
    db.commit()
    return {"message": f'"{t.name}" added.', "tool": _tool_row(t)}


@router.put("/tools/{tool_id}")
def update_tool(tool_id: int, body: ToolIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    t = db.get(PlatformTool, tool_id)
    if t is None:
        raise HTTPException(404, "Tool not found")
    _apply_tool(db, t, body, user)
    db.commit()
    forget_tools(db)
    return {"message": f'"{t.name}" updated.', "tool": _tool_row(t, _plan_counts(db).get(t.id, 0))}


@router.delete("/tools/{tool_id}")
def delete_tool(tool_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    t = db.get(PlatformTool, tool_id)
    if t is None:
        raise HTTPException(404, "Tool not found")
    if t.is_builtin:
        raise HTTPException(400, f'"{t.name}" is built in and can\'t be removed. Switch it off instead.')
    used = _plan_counts(db).get(t.id, 0)
    if used:
        raise HTTPException(400, f'"{t.name}" is in {used} plan(s). Remove it from them first, or switch it off.')
    name = t.name
    db.delete(t)
    db.commit()
    forget_tools(db)
    return {"message": f'"{name}" removed.'}


# ------------------------------------------------------------------ plans
def _plan_subscribers(db: Session) -> dict[int, int]:
    now = svc.utcnow()
    rows = db.execute(select(OrgSubscription.plan_id, func.count(func.distinct(OrgSubscription.organisation_id)))
                      .where(OrgSubscription.status == "active",
                             or_(OrgSubscription.ends_at.is_(None), OrgSubscription.ends_at > now))
                      .group_by(OrgSubscription.plan_id)).all()
    return {pid: n for pid, n in rows if pid is not None}


@router.get("/plans")
def list_plans(_=Depends(require_superuser), db: Session = Depends(get_db)):
    subs = _plan_subscribers(db)
    return {"plans": [{**svc.plan_payload(p), "subscribers": subs.get(p.id, 0)} for p in svc.plans_for(db, None, include_inactive=True)],
            "tools": [{"key": t.key, "name": t.name, "is_active": bool(t.is_active), "is_free": bool(t.is_free)} for t in ensure_tools(db)],
            "periods": [{"value": k, "label": v} for k, v in BILLING_PERIODS.items()],
            "audiences": [{"value": k, "label": v} for k, v in PLAN_AUDIENCES.items()]}


class PlanIn(BaseModel):
    name: str
    description: str = ""
    price: float | str = 0
    billing_period: str = "monthly"
    trial_days: int = 0
    audience: str = "all"
    tool_keys: list[str] = []
    is_featured: bool = False
    is_active: bool = True
    sort_order: int = 0
    tax_percent: float | str = 18
    sac_code: str = ""


def _apply_plan(db: Session, p: SubscriptionPlan, body: PlanIn, user: User) -> None:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Plan name is required.")
    clash = db.execute(select(SubscriptionPlan.id).where(func.lower(SubscriptionPlan.name) == name.lower(),
                                                         SubscriptionPlan.id != (p.id or 0))).first()
    if clash:
        raise HTTPException(400, f'A plan named "{name}" already exists.')
    if body.billing_period not in BILLING_PERIODS:
        raise HTTPException(400, "Choose a valid billing period.")
    if body.audience not in PLAN_AUDIENCES:
        raise HTTPException(400, "Choose who the plan is for.")
    if not 0 <= body.trial_days <= 365:
        raise HTTPException(400, "Trial days must be between 0 and 365.")
    by_key = {t.key: t for t in ensure_tools(db)}
    keys = list(dict.fromkeys(body.tool_keys))
    unknown = [k for k in keys if k not in by_key]
    if unknown:
        raise HTTPException(400, f"Unknown tool: {', '.join(unknown)}")
    if not keys:
        raise HTTPException(400, "Choose at least one tool for the plan.")
    p.name, p.description = name[:150], body.description.strip()[:500]
    p.price, p.currency, p.billing_period = _money(body.price, "Price"), "INR", body.billing_period
    p.trial_days, p.audience = body.trial_days, body.audience
    p.is_featured, p.is_active = 1 if body.is_featured else 0, 1 if body.is_active else 0
    p.sort_order, p.updated_by_id = body.sort_order, user.id
    tax = _money(body.tax_percent, "GST")
    if tax > 100:
        raise HTTPException(400, "GST must be between 0 and 100%.")
    p.tax_percent, p.sac_code = tax, body.sac_code.strip()[:20]
    current = {pt.tool.key: pt for pt in p.plan_tools}
    for k, pt in current.items():
        if k not in keys:
            p.plan_tools.remove(pt)
    for k in keys:
        if k not in current:
            p.plan_tools.append(SubscriptionPlanTool(tool_id=by_key[k].id))


@router.post("/plans")
def create_plan(body: PlanIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    p = SubscriptionPlan()
    _apply_plan(db, p, body, user)
    db.add(p)
    db.commit()
    return {"message": f'Plan "{p.name}" created.', "plan": svc.plan_payload(p)}


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, body: PlanIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    p = db.get(SubscriptionPlan, plan_id)
    if p is None:
        raise HTTPException(404, "Plan not found")
    _apply_plan(db, p, body, user)
    db.flush()
    changed = svc.give_added_tools(db, p)
    db.commit()
    extra = f" {changed} subscriber{'s' if changed != 1 else ''} got the added tools." if changed else ""
    return {"message": f'Plan "{p.name}" updated.{extra} Tools taken out stay with existing subscribers until their plan ends.',
            "plan": svc.plan_payload(p)}


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    p = db.get(SubscriptionPlan, plan_id)
    if p is None:
        raise HTTPException(404, "Plan not found")
    used = db.scalar(select(func.count()).select_from(OrgSubscription).where(OrgSubscription.plan_id == p.id))
    if used:
        raise HTTPException(400, f'"{p.name}" has {used} subscription(s). Mark it inactive instead so no one new can choose it.')
    name = p.name
    db.delete(p)
    db.commit()
    return {"message": f'Plan "{name}" deleted.'}


# ------------------------------------------------------------------ subscriptions
@router.get("")
def list_subscriptions(search: str = "", state: str = "", organisation_id: int | None = None, page: int = 1,
                       _=Depends(require_superuser), db: Session = Depends(get_db)):
    stmt = select(OrgSubscription).join(Organisation, Organisation.id == OrgSubscription.organisation_id)
    if organisation_id:
        stmt = stmt.where(OrgSubscription.organisation_id == organisation_id)
    if search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Organisation.name.ilike(like), OrgSubscription.plan_name.ilike(like),
                              OrgSubscription.payment_ref.ilike(like)))
    now = svc.utcnow()
    if state == "active":
        stmt = stmt.where(OrgSubscription.status == "active", or_(OrgSubscription.ends_at.is_(None), OrgSubscription.ends_at > now))
    elif state == "expired":
        stmt = stmt.where(OrgSubscription.status == "active", OrgSubscription.ends_at <= now)
    elif state in ("pending", "cancelled"):
        stmt = stmt.where(OrgSubscription.status == state)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    rows = db.execute(stmt.order_by(OrgSubscription.created_at.desc(), OrgSubscription.id.desc())
                      .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)).scalars().all()
    names = svc.tool_names(db)
    revenue = db.scalar(select(func.coalesce(func.sum(OrgSubscription.price + OrgSubscription.tax_amount), 0))
                        .where(OrgSubscription.paid_at.is_not(None)))
    active = db.scalar(select(func.count(func.distinct(OrgSubscription.organisation_id))).where(
        OrgSubscription.status == "active", or_(OrgSubscription.ends_at.is_(None), OrgSubscription.ends_at > now)))
    pending = db.scalar(select(func.count()).select_from(OrgSubscription).where(OrgSubscription.status == "pending"))
    return {"items": [{**svc.subscription_payload(s, names),
                       "organisation": {"id": s.organisation.id, "name": s.organisation.name, "kind": s.organisation.kind}}
                      for s in rows],
            "total": total, "page": page, "pages": pages,
            "stats": {"active_workspaces": active, "pending": pending, "revenue": float(revenue or 0)}}


class AssignIn(BaseModel):
    organisation_id: int
    plan_id: int
    ends_at: str | None = None  # ISO date; empty = the plan's normal period
    notes: str = ""


def _parse_date(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "Enter a valid end date.") from None


@router.post("/assign")
def assign_plan(body: AssignIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    """Give a workspace a plan without online payment (paid offline, complimentary, a deal)."""
    org = db.get(Organisation, body.organisation_id)
    plan = db.get(SubscriptionPlan, body.plan_id)
    if org is None or plan is None:
        raise HTTPException(404, "Workspace or plan not found")
    if org.kind == "system":
        raise HTTPException(400, "The Turacoz team workspace doesn't need a plan.")
    if not plan.plan_tools:
        raise HTTPException(400, "This plan has no tools yet.")
    ends_at = _parse_date(body.ends_at)
    sub = OrgSubscription(organisation_id=org.id, plan_id=plan.id, plan_name=plan.name, tool_keys=svc.plan_tool_keys(plan),
                          price=plan.price, currency=plan.currency, billing_period=plan.billing_period, status="pending",
                          is_trial=0, source="admin", gateway="", gateway_order_id="", payment_ref="",
                          notes=(body.notes.strip() or f"Given by {user.username}")[:500], created_by_id=user.id)
    db.add(sub)
    db.flush()
    svc.activate(db, sub, ends_at=ends_at, custom_end=ends_at is not None)
    db.commit()
    return {"message": f"{plan.name} is now active for {org.name}.", "subscription": svc.subscription_payload(sub, svc.tool_names(db))}


class UpdateSubIn(BaseModel):
    action: str  # cancel | activate | set_end
    ends_at: str | None = None
    notes: str = ""


@router.post("/{sub_id}")
def update_subscription(sub_id: int, body: UpdateSubIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    sub = db.get(OrgSubscription, sub_id)
    if sub is None:
        raise HTTPException(404, "Subscription not found")
    note = body.notes.strip()
    if body.action == "cancel":
        if sub.status == "cancelled":
            raise HTTPException(400, "This subscription is already cancelled.")
        sub.status = "cancelled"
        msg = f"{sub.plan_name} for {sub.organisation.name} was cancelled. Its tools are no longer available."
    elif body.action == "activate":
        if sub.status != "pending":
            raise HTTPException(400, "Only a subscription awaiting payment can be activated.")
        svc.activate(db, sub, payment_ref=note[:100] or f"offline-{user.username}")
        msg = f"{sub.plan_name} for {sub.organisation.name} is now active."
    elif body.action == "set_end":
        if sub.status != "active":
            raise HTTPException(400, "Only an active subscription's end date can be changed.")
        sub.ends_at = _parse_date(body.ends_at)
        msg = f"{sub.plan_name} for {sub.organisation.name} now {'ends ' + body.ends_at[:10] if sub.ends_at else 'has no end date'}."
    else:
        raise HTTPException(400, "Unknown action")
    if note:
        sub.notes = f"{sub.notes} {note}".strip()[:500]
    db.commit()
    return {"message": msg, "subscription": svc.subscription_payload(sub, svc.tool_names(db))}


@router.get("/organisations")
def organisation_options(search: str = "", _=Depends(require_superuser), db: Session = Depends(get_db)):
    """Workspaces for the "Give a plan" picker."""
    stmt = select(Organisation).where(Organisation.kind != "system", Organisation.status == "active")
    if search.strip():
        stmt = stmt.where(Organisation.name.ilike(f"%{search.strip()}%"))
    rows = db.execute(stmt.order_by(Organisation.name).limit(30)).scalars().all()
    return {"items": [{"id": o.id, "name": o.name, "kind": o.kind} for o in rows]}
