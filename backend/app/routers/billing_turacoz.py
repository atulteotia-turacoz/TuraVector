"""Invoices for Turacoz Financial Managers (and superusers): each sees the workspaces they handle."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.tenancy import unfiltered
from app.database import get_db
from app.models import BillingRequest, Invoice, Organisation, OrgBillingProfile, User
from app.services import billing, billing_pdf, billing_reminders, billing_reports
from app.services.review_reports import as_csv, as_xlsx

router = APIRouter(prefix="/api/billing", tags=["billing"])


def require_approver(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if not billing.is_approver(db, user):
        raise HTTPException(403, "Only Turacoz Financial Managers can do this.")
    return user


def _scoped(stmt, column, scope: set[int] | None):
    return stmt if scope is None else stmt.where(column.in_(scope or {-1}))


def _invoice(db: Session, invoice_id: int, user: User) -> Invoice:
    with unfiltered(db):
        inv = db.get(Invoice, invoice_id)
    if inv is None or not billing.handles(db, user, inv.organisation_id):
        raise HTTPException(404, "Invoice not found")
    return inv


def _call(fn, *args):
    try:
        return fn(*args)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None


def _finish(db: Session, user: User, mails: list) -> None:
    billing.notify_in_app(db, mails, user)
    db.commit()
    billing.send(db, mails, user)


@router.get("/invoices")
def list_invoices(status: str = "", organisation: int | None = None, user: User = Depends(require_approver),
                  db: Session = Depends(get_db)):
    scope = billing.approver_scope(db, user)
    with unfiltered(db):
        stmt = _scoped(select(Invoice), Invoice.organisation_id, scope)
        if organisation:
            stmt = stmt.where(Invoice.organisation_id == organisation)
        counts = dict(db.execute(_scoped(select(Invoice.status, func.count()), Invoice.organisation_id, scope).where(
            *([Invoice.organisation_id == organisation] if organisation else [])).group_by(Invoice.status)).all())
        rows = db.execute((stmt.where(Invoice.status == status) if status else stmt).order_by(Invoice.id.desc())).scalars().all()
        # requests not invoiced yet: monthly workspaces between runs, or a billing profile still incomplete
        waiting = db.execute(_scoped(select(Organisation, func.count(BillingRequest.id), func.min(BillingRequest.created_at))
                             .join(BillingRequest, BillingRequest.organisation_id == Organisation.id)
                             .where(BillingRequest.invoice_id.is_(None)), Organisation.id, scope).group_by(Organisation.id)).all()
        profiles = {p.organisation_id: p for p in db.execute(select(OrgBillingProfile)).scalars()}
    return {
        "invoices": [billing.invoice_row(i) for i in rows], "counts": counts,
        "waiting": [{"organisation_id": o.id, "organisation": o.name, "requests": n, "since": since.isoformat() if since else None,
                     "billing_cycle": (profiles[o.id].billing_cycle if o.id in profiles else "per_submission"),
                     "missing": billing.profile_missing(profiles.get(o.id))} for o, n, since in waiting],
        "can_approve": True,
    }


@router.get("/summary")
def summary(user: User = Depends(require_approver), db: Session = Depends(get_db)):
    """For dashboards: what is waiting, and which invoices have waited longer than the reminder threshold."""
    s = billing.settings_row(db)
    now = billing.utcnow()
    scope = billing.approver_scope(db, user)
    with unfiltered(db):
        open_ = db.execute(_scoped(select(Invoice).where(Invoice.status.in_(billing_reminders.OPEN_STAGES)),
                                   Invoice.organisation_id, scope).order_by(Invoice.status_changed_at)).scalars().all()
        unbilled = db.scalar(_scoped(select(func.count()).select_from(BillingRequest).where(BillingRequest.invoice_id.is_(None)),
                                     BillingRequest.organisation_id, scope))
    rows = []
    counts = {k: {"count": 0, "amount": 0.0, "overdue": 0} for k in billing_reminders.OPEN_STAGES}
    for inv in open_:
        late = billing_reminders.overdue_days(s, inv, now)
        c = counts[inv.status]
        c["count"] += 1
        c["amount"] += float(inv.total)
        c["overdue"] += bool(late)
        rows.append({**billing.invoice_row(inv), "waiting_days": (now - billing_reminders.since(inv)).days,
                     "overdue": bool(late), "reminders_sent": inv.reminders_sent})
    rows.sort(key=lambda r: (r["status"] != "pending_turacoz", -r["waiting_days"]))
    return {"counts": counts, "unbilled_requests": unbilled or 0, "threshold_days": s.reminder_after_days,
            "invoices": rows[:8]}


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: int, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    return billing.invoice_detail(db, _invoice(db, invoice_id, user))


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    d = billing.invoice_detail(db, _invoice(db, invoice_id, user))
    return Response(billing_pdf.invoice_pdf(d), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{d["number"]}.pdf"'})


class LineEdit(BaseModel):
    id: int
    quantity: float | str
    rate: float | str


class ApproveIn(BaseModel):
    lines: list[LineEdit] = []
    remarks: str = ""


@router.post("/invoices/{invoice_id}/approve")
def approve(invoice_id: int, body: ApproveIn, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    inv = _invoice(db, invoice_id, user)
    mails = _call(billing.turacoz_approve, db, inv, user, [e.model_dump() for e in body.lines], body.remarks)
    _finish(db, user, mails)
    return {"message": f"Invoice {inv.number} approved and sent to {inv.organisation.name}.",
            "invoice": billing.invoice_detail(db, inv)}


class ReasonIn(BaseModel):
    reason: str = ""


@router.post("/invoices/{invoice_id}/reject")
def reject(invoice_id: int, body: ReasonIn, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    inv = _invoice(db, invoice_id, user)
    mails = _call(billing.turacoz_reject, db, inv, user, body.reason)
    _finish(db, user, mails)
    return {"message": f"Invoice {inv.number} cancelled.", "invoice": billing.invoice_detail(db, inv)}


class PaidIn(BaseModel):
    reference: str = ""


@router.post("/invoices/{invoice_id}/mark-paid")
def mark_paid(invoice_id: int, body: PaidIn, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    """Record a payment received outside the gateway (e.g. bank transfer)."""
    inv = _invoice(db, invoice_id, user)
    if not body.reference.strip():
        raise HTTPException(400, "Enter the payment reference (e.g. bank transfer UTR).")
    mails = _call(billing.mark_paid, db, inv, body.reference.strip(), user, f"Recorded by {billing.name_of(user)}: {body.reference.strip()}")
    _finish(db, user, mails)
    return {"message": f"Invoice {inv.number} marked as paid.", "invoice": billing.invoice_detail(db, inv)}


class MonthIn(BaseModel):
    month: str = ""  # YYYY-MM; default: the previous month


@router.post("/organisations/{org_id}/generate")
def generate(org_id: int, body: MonthIn, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    """Invoice a workspace's waiting requests now: per-submission ones one by one, monthly ones for the month."""
    with unfiltered(db):
        org = db.get(Organisation, org_id)
    if org is None or not billing.handles(db, user, org.id):
        raise HTTPException(404, "Organisation not found")
    p = billing.profile_of(db, org.id)
    if billing.profile_missing(p):
        raise HTTPException(400, f"Complete {org.name}'s billing profile first ({', '.join(billing.profile_missing(p))}).")
    if p.billing_cycle == "monthly":
        try:
            month = datetime.date.fromisoformat(f"{body.month}-01") if body.month else datetime.datetime.now(billing.IST).date()
        except ValueError:
            raise HTTPException(400, "Choose a valid month.") from None
        inv = _call(billing.bill_month, db, org, month, user)
        created = [inv] if inv else []
    else:
        created = _call(billing.bill_waiting, db, org, user)
    if not created:
        raise HTTPException(400, "Nothing to invoice for that period.")
    mails = [m for inv in created for m in billing.invoice_created_mails(db, inv)]
    _finish(db, user, mails)
    return {"message": f"{len(created)} invoice{'s' if len(created) != 1 else ''} generated: "
                       + ", ".join(i.number for i in created), "invoices": [billing.invoice_row(i) for i in created]}


# ------------------------------------------------------------------ Finance dashboard
@router.get("/dashboard")
def dashboard(user: User = Depends(require_approver), db: Session = Depends(get_db)):
    """A Financial Manager's workspaces with their invoice position, and the month's numbers."""
    scope = billing.approver_scope(db, user)
    s = billing.settings_row(db)
    now = billing.utcnow()
    month_start = datetime.datetime.now(billing.IST).date().replace(day=1)
    with unfiltered(db):
        orgs = db.execute(_scoped(select(Organisation).where(Organisation.kind.in_(billing.CLIENT_KINDS),
                                                             Organisation.status == "active"), Organisation.id, scope)
                          .order_by(Organisation.name)).scalars().all()
        ids = [o.id for o in orgs] or [-1]
        invoices = db.execute(select(Invoice).where(Invoice.organisation_id.in_(ids))).scalars().all()
        unbilled = dict(db.execute(select(BillingRequest.organisation_id, func.count()).where(
            BillingRequest.organisation_id.in_(ids), BillingRequest.invoice_id.is_(None)).group_by(BillingRequest.organisation_id)).all())
        profiles = {p.organisation_id: p for p in db.execute(select(OrgBillingProfile).where(OrgBillingProfile.organisation_id.in_(ids))).scalars()}
        own = billing.finance_orgs_of(db, user.id)
    per: dict[int, dict] = {o.id: {"open": 0, "outstanding": 0.0, "overdue": 0, "to_approve": 0, "paid": 0.0, "last": None} for o in orgs}
    totals = {"to_approve": 0, "to_approve_amount": 0.0, "with_client": 0, "awaiting_payment": 0, "outstanding": 0.0,
              "paid_this_month": 0.0, "invoiced_this_month": 0.0, "overdue": 0}
    for inv in invoices:
        r = per[inv.organisation_id]
        total = float(inv.total)
        late = bool(billing_reminders.overdue_days(s, inv, now))
        if r["last"] is None or inv.created_at > r["last"]:
            r["last"] = inv.created_at
        if inv.status in billing_reminders.OPEN_STAGES:
            r["open"] += 1
            r["overdue"] += late
            totals["overdue"] += late
        if inv.status == "pending_turacoz":
            r["to_approve"] += 1
            totals["to_approve"] += 1
            totals["to_approve_amount"] += total
        elif inv.status == "pending_client":
            totals["with_client"] += 1
        if inv.status in ("pending_client", "awaiting_payment"):
            r["outstanding"] += total
            totals["outstanding"] += total
        if inv.status == "awaiting_payment":
            totals["awaiting_payment"] += 1
        if inv.status == "paid":
            r["paid"] += total
            if inv.paid_at and (inv.paid_at + datetime.timedelta(hours=5, minutes=30)).date() >= month_start:
                totals["paid_this_month"] += total
        if inv.status != "rejected" and (inv.created_at + datetime.timedelta(hours=5, minutes=30)).date() >= month_start:
            totals["invoiced_this_month"] += total
    return {
        "scope": "all" if scope is None else ("assigned" if not (user.id in billing.default_approver_ids(db)) else "default"),
        "totals": totals, "threshold_days": s.reminder_after_days,
        "organisations": [{
            "id": o.id, "name": o.name, "kind": o.kind,
            "assigned": o.id in own,  # this user is its own Financial Manager (not via the default)
            "billing_cycle": profiles[o.id].billing_cycle if o.id in profiles else "per_submission",
            "profile_missing": billing.profile_missing(profiles.get(o.id)),
            "unbilled_requests": unbilled.get(o.id, 0), **{k: v for k, v in per[o.id].items() if k != "last"},
            "last_invoice_at": billing.iso(per[o.id]["last"]),
        } for o in orgs],
    }


@router.get("/organisations/{org_id}/profile")
def org_profile(org_id: int, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    with unfiltered(db):
        org = db.get(Organisation, org_id)
    if org is None or not billing.handles(db, user, org.id):
        raise HTTPException(404, "Organisation not found")
    return billing.profile_payload(org, billing.profile_of(db, org.id), db)


@router.put("/organisations/{org_id}/profile")
def save_org_profile(org_id: int, body: dict, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    """A Financial Manager keeps their workspaces' billing details, cycle and reminders up to date."""
    with unfiltered(db):
        org = db.get(Organisation, org_id)
    if org is None or not billing.handles(db, user, org.id):
        raise HTTPException(404, "Organisation not found")
    try:
        p = billing.save_profile(db, org, user, body, True)
        billing_reminders.apply_profile(p, body)
        created = billing.bill_waiting(db, org, user)
    except ValueError:
        raise HTTPException(400, "Reminder days must be whole numbers.") from None
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None
    mails = [m for inv in created for m in billing.invoice_created_mails(db, inv)]
    _finish(db, user, mails)
    return {"message": "Billing details saved." + (f" {len(created)} waiting request(s) invoiced." if created else ""),
            **billing.profile_payload(org, p, db)}


# ------------------------------------------------------------------ analytics & reports
@router.get("/analytics")
def analytics(months: int = 12, user: User = Depends(require_approver), db: Session = Depends(get_db)):
    return billing_reports.analytics(db, billing.approver_scope(db, user), max(3, min(months, 24)))


def _report(db: Session, user: User, date_from: str, date_to: str, organisation: int | None, status: str) -> dict:
    scope = billing.approver_scope(db, user)
    if organisation and not billing.handles(db, user, organisation):
        raise HTTPException(404, "Organisation not found")
    try:
        start, end = billing_reports.resolve_range(date_from, date_to)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None
    return billing_reports.report(db, scope, start, end, organisation, status)


@router.get("/reports")
def reports(date_from: str = "", date_to: str = "", organisation: int | None = None, status: str = "",
            user: User = Depends(require_approver), db: Session = Depends(get_db)):
    data = _report(db, user, date_from, date_to, organisation, status)
    with unfiltered(db):
        scope = billing.approver_scope(db, user)
        orgs = db.execute(_scoped(select(Organisation).where(Organisation.kind.in_(billing.CLIENT_KINDS)), Organisation.id, scope)
                          .order_by(Organisation.name)).scalars().all()
    return {**data, "organisations": [{"id": o.id, "name": o.name} for o in orgs]}


@router.get("/reports/export")
def export_report(format: str = "xlsx", section: str = "", date_from: str = "", date_to: str = "",
                  organisation: int | None = None, status: str = "", user: User = Depends(require_approver),
                  db: Session = Depends(get_db)):
    """Excel (every report as a sheet), PDF, or one report as CSV (`section`)."""
    data = _report(db, user, date_from, date_to, organisation, status)
    name = f"turavector_finance_{data['period']['from']}_to_{data['period']['to']}"
    if format == "pdf":
        body, media = billing_reports.as_pdf(data, "TuraVector finance report"), "application/pdf"
        name += ".pdf"
    elif format == "csv":
        if section not in billing_reports.SHEETS:
            raise HTTPException(400, "Choose a report to download.")
        body, media = as_csv(next(iter(billing_reports.tables(data, section).values()))), "text/csv"
        name = f"{name}_{section}.csv"
    else:
        body, media = as_xlsx(billing_reports.tables(data)), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        name += ".xlsx"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
