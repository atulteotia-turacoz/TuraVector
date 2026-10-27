"""Billing: services a member asks for → invoice → Turacoz approval → client approval → payment.

* A member of a university / organisation submits a document (or written text) and picks services from
  their workspace's rate card. That is a `BillingRequest`, priced at the rate card's rates.
* Workspaces billed per submission get an invoice for every request straight away; monthly ones get
  one invoice per calendar month (`bill_month`). A workspace whose billing profile (state, country) is
  incomplete is not invoiced until the profile is filled in — its requests wait, unbilled.
* Invoice: pending_turacoz → (Turacoz approver, may adjust quantity/rate) pending_client →
  (university admin) awaiting_payment → (gateway) paid. Turacoz may cancel (rejected); the client may
  send it back with a query (→ pending_turacoz).

State changes return the emails to send; callers commit first and then call `send(db, mails)`, because
email logging commits on its own.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import send_email_with_logging
from app.core.tenancy import active_membership, unfiltered
from app.core.utils import iso
from app.models import (
    BillingApprover, BillingRequest, BillingRequestItem, BillingSettings, Document, DocumentNotification, Invoice,
    InvoiceEvent, InvoiceLine, OrgAssignment, Organisation, OrgBillingProfile, OrgMembership, RateCardItem, RateService, User,
    utcnow,
)
from app.models.billing import BILLING_CYCLES, INVOICE_STATUSES
from app.models.rates import RATE_UNITS
from app.services import billing_tax
from app.services.billing_tax import money

log = logging.getLogger("turadome.billing")
IST = ZoneInfo("Asia/Kolkata")
CLIENT_KINDS = ("university", "organisation")


class BillingError(Exception):
    """A request that cannot be done; the message is shown to the user."""


# ---------------------------------------------------------------------------------------------- people
def name_of(u: User | None) -> str:
    if u is None:
        return "System"
    return f"{u.first_name} {u.last_name}".strip() or u.username


# Financial Managers: Turacoz users who approve invoices. A university / organisation may have its own
# (an `org_assignment` with role "finance"); every workspace without one is handled by the default
# Financial Managers (`billing_approver`). Superusers can always approve, and are emailed only when
# nobody else would be.
FINANCE = "finance"


def default_approver_ids(db: Session) -> set[int]:
    with unfiltered(db):
        return set(db.execute(select(BillingApprover.user_id)).scalars())


def orgs_with_finance(db: Session) -> set[int]:
    with unfiltered(db):
        return set(db.execute(select(OrgAssignment.organisation_id).where(OrgAssignment.role == FINANCE)).scalars())


def finance_orgs_of(db: Session, user_id: int) -> set[int]:
    with unfiltered(db):
        return set(db.execute(select(OrgAssignment.organisation_id).where(
            OrgAssignment.role == FINANCE, OrgAssignment.user_id == user_id)).scalars())


def is_approver(db: Session, user: User) -> bool:
    return bool(user.is_superuser or user.id in default_approver_ids(db) or finance_orgs_of(db, user.id))


def approver_scope(db: Session, user: User) -> set[int] | None:
    """Workspaces whose invoices this user handles; None = all of them (superusers)."""
    if user.is_superuser:
        return None
    scope = finance_orgs_of(db, user.id)
    if user.id in default_approver_ids(db):
        with unfiltered(db):
            clients = set(db.execute(select(Organisation.id).where(Organisation.kind.in_(CLIENT_KINDS))).scalars())
        scope |= clients - orgs_with_finance(db)
    return scope


def handles(db: Session, user: User, org_id: int) -> bool:
    scope = approver_scope(db, user)
    return scope is None or org_id in scope


def approvers_for(db: Session, org_id: int) -> list[User]:
    """Who approves (and is emailed about) this workspace's invoices."""
    with unfiltered(db):
        own = select(OrgAssignment.user_id).where(OrgAssignment.organisation_id == org_id, OrgAssignment.role == FINANCE)
        people = list(db.execute(select(User).where(User.is_active == 1, User.id.in_(own))).scalars())
        if not people:
            people = list(db.execute(select(User).where(User.is_active == 1, User.id.in_(select(BillingApprover.user_id))))
                          .scalars())
        if not people:
            people = list(db.execute(select(User).where(User.is_active == 1, User.is_superuser == 1)).scalars())
    return people


def org_admins(db: Session, org_id: int) -> list[User]:
    with unfiltered(db):
        return list(db.execute(select(User).join(OrgMembership, OrgMembership.user_id == User.id).where(
            OrgMembership.organisation_id == org_id, OrgMembership.role == "admin",
            OrgMembership.status == "active", User.is_active == 1)).scalars())


# ---------------------------------------------------------------------------------------------- settings
def settings_row(db: Session) -> BillingSettings:
    with unfiltered(db):
        row = db.execute(select(BillingSettings).order_by(BillingSettings.id).limit(1)).scalar_one_or_none()
    if row is None:
        row = BillingSettings(company_name="Turacoz Healthcare Solutions", state="Delhi", state_code="07",
                              country="India", invoice_prefix="TC")
        db.add(row)
        db.flush()
    return row


def profile_of(db: Session, org_id: int) -> OrgBillingProfile | None:
    with unfiltered(db):
        return db.execute(select(OrgBillingProfile).where(OrgBillingProfile.organisation_id == org_id)).scalar_one_or_none()


def profile_missing(p: OrgBillingProfile | None) -> list[str]:
    """What must be filled in before invoices can be made out (tax depends on it)."""
    if p is None:
        return ["country", "state"]
    missing = [] if p.country.strip() else ["country"]
    if billing_tax.in_india(p.country) and not p.state.strip():
        missing.append("state")
    return missing


def finance_people(db: Session, org_id: int) -> dict:
    """Who handles this workspace's invoices: its own Financial Managers, or the defaults."""
    with unfiltered(db):
        own = list(db.execute(select(User).join(OrgAssignment, OrgAssignment.user_id == User.id).where(
            OrgAssignment.organisation_id == org_id, OrgAssignment.role == FINANCE)).scalars())
    people = own or approvers_for(db, org_id)
    return {"uses_default": not own, "people": [{"id": u.id, "name": name_of(u), "email": u.email} for u in people]}


def profile_payload(org: Organisation, p: OrgBillingProfile | None, db: Session | None = None) -> dict:
    return {**({"financial_managers": finance_people(db, org.id)} if db is not None else {}),
        "legal_name": p.legal_name if p else "", "address": p.address if p else "", "state": p.state if p else "",
        "state_code": p.state_code if p else "", "country": p.country if p else "India", "gstin": p.gstin if p else "",
        "billing_email": p.billing_email if p else "",
        "billing_cycle": p.billing_cycle if p else "per_submission",
        "billing_cycle_label": BILLING_CYCLES[p.billing_cycle if p else "per_submission"],
        "missing": profile_missing(p), "organisation": org.name,
        "reminder_mode": p.reminder_mode if p else "default",
        "reminder_after_days": p.reminder_after_days if p else None,
        "reminder_repeat_days": p.reminder_repeat_days if p else None,
        "reminder_max": p.reminder_max if p else None,
    }


def save_profile(db: Session, org: Organisation, user: User, data: dict, allow_cycle: bool) -> OrgBillingProfile:
    p = profile_of(db, org.id)
    if p is None:
        p = OrgBillingProfile(organisation_id=org.id)
        db.add(p)
    for key, size in (("legal_name", 200), ("address", 500), ("state", 100), ("state_code", 5),
                      ("country", 100), ("gstin", 20), ("billing_email", 200)):
        if key in data and data[key] is not None:
            setattr(p, key, str(data[key]).strip()[:size])
    if p.gstin:
        p.gstin = p.gstin.upper()
    if allow_cycle and data.get("billing_cycle"):
        if data["billing_cycle"] not in BILLING_CYCLES:
            raise BillingError("Choose Per submission or Monthly billing.")
        p.billing_cycle = data["billing_cycle"]
    if not p.country.strip():
        raise BillingError("Country is required.")
    p.updated_by_id = user.id
    db.flush()
    return p


# ---------------------------------------------------------------------------------------------- requests
def client_org(db: Session, user: User) -> Organisation | None:
    """The university / organisation a member bills to (None for individuals and the Turacoz team)."""
    m = active_membership(db, user)
    return m.organisation if m and m.organisation.kind in CLIENT_KINDS else None


def rate_card_for(db: Session, user: User) -> list[dict]:
    """The services a member may pick when submitting, at their workspace's rates."""
    org = client_org(db, user)
    if org is None:
        return []
    with unfiltered(db):
        rows = db.execute(select(RateCardItem, RateService).join(RateService, RateService.id == RateCardItem.service_id)
                          .where(RateCardItem.organisation_id == org.id, RateService.is_active == 1)
                          .order_by(RateService.sort_order, RateService.name)).all()
    return [{"service_id": s.id, "name": s.name, "description": s.description, "unit": s.unit,
             "unit_label": RATE_UNITS.get(s.unit, s.unit or ""), "rate": float(i.rate),
             "tax_percent": float(s.tax_percent), "currency": s.currency} for i, s in rows]


def parse_items(raw) -> list[dict]:
    """[{service_id, quantity}] from the upload form (JSON); quantities default to 1."""
    import json
    if raw in (None, "", "[]"):
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        items = [{"service_id": int(d["service_id"]),
                  "quantity": money(1 if d.get("quantity") in (None, "") else d["quantity"])} for d in data]
    except (ValueError, TypeError, KeyError, ArithmeticError):
        raise BillingError("The selected services could not be read. Please choose them again.") from None
    if any(i["quantity"] <= 0 for i in items):
        raise BillingError("Quantity must be more than zero.")
    if len({i["service_id"] for i in items}) != len(items):
        raise BillingError("A service was selected twice.")
    return items


def check_items(db: Session, user: User, items: list[dict]) -> tuple[Organisation, dict[int, tuple]]:
    """Validate the picks against the member's rate card before anything is saved."""
    org = client_org(db, user)
    if org is None:
        raise BillingError("Services can be requested only by members of a university or organisation.")
    with unfiltered(db):
        card = {s.id: (i, s) for i, s in db.execute(
            select(RateCardItem, RateService).join(RateService, RateService.id == RateCardItem.service_id)
            .where(RateCardItem.organisation_id == org.id, RateService.is_active == 1)).all()}
    for it in items:
        if it["service_id"] not in card:
            raise BillingError("A selected service is not on your rate card any more. Please choose again.")
    return org, card


def create_request(db: Session, user: User, items: list[dict], *, document: Document | None = None,
                   version_id: int | None = None, requirement: str = "") -> tuple[BillingRequest, list["Mail"]]:
    """Save what was asked for (at today's rate card rates) and bill it if the workspace is billed per submission."""
    org, card = check_items(db, user, items)
    req = BillingRequest(organisation_id=org.id, user_id=user.id, document_id=document.id if document else None,
                         document_version_id=version_id, requirement=(requirement or "").strip() or None)
    db.add(req)
    for it in items:
        rc, s = card[it["service_id"]]
        req.items.append(BillingRequestItem(service_id=s.id, name=s.name, unit=s.unit, sac_code=s.sac_code or "",
                                            quantity=it["quantity"], rate=rc.rate, tax_percent=s.tax_percent,
                                            tax_overseas=s.tax_overseas))
    db.flush()
    mails: list[Mail] = []
    p = profile_of(db, org.id)
    if (p is None or p.billing_cycle == "per_submission") and not profile_missing(p):
        inv = issue_invoice(db, org, [req], cycle="per_submission", actor=user)
        mails += invoice_created_mails(db, inv)
    return req, mails


def unbilled(db: Session, org_id: int, before: datetime.datetime | None = None) -> list[BillingRequest]:
    with unfiltered(db):
        stmt = select(BillingRequest).where(BillingRequest.organisation_id == org_id, BillingRequest.invoice_id.is_(None))
        if before is not None:
            stmt = stmt.where(BillingRequest.created_at < before)
        return list(db.execute(stmt.order_by(BillingRequest.id)).scalars())


# ---------------------------------------------------------------------------------------------- invoices
def financial_year(day: datetime.date) -> str:
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def next_number(db: Session) -> str:
    """{prefix}{FY}-{n:04}, e.g. TC2627-0001. The counter restarts every financial year (April)."""
    with unfiltered(db):
        s = db.execute(select(BillingSettings).order_by(BillingSettings.id).limit(1).with_for_update()).scalar_one_or_none()
    if s is None:
        s = settings_row(db)
    fy = financial_year(datetime.datetime.now(IST).date())
    if s.sequence_year != fy:
        s.sequence_year, s.sequence_next = fy, 1
    while True:
        number = f"{(s.invoice_prefix or 'TC').strip()}{fy}-{s.sequence_next:04d}"
        s.sequence_next += 1
        if db.execute(select(Invoice.id).where(Invoice.number == number)).first() is None:
            return number


def _seller(s: BillingSettings) -> dict:
    return {k: getattr(s, k) for k in ("company_name", "address", "state", "state_code", "country", "gstin", "pan",
                                       "email", "phone", "bank_details", "terms")}


def _buyer(org: Organisation, p: OrgBillingProfile | None) -> dict:
    return {"name": (p.legal_name if p and p.legal_name else org.name), "address": p.address if p else "",
            "state": p.state if p else "", "state_code": p.state_code if p else "",
            "country": p.country if p else "India", "gstin": p.gstin if p else "",
            "email": p.billing_email if p else ""}


def recalculate(inv: Invoice) -> None:
    subtotal = cgst = sgst = igst = Decimal("0.00")
    for line in inv.lines:
        line.amount = money(Decimal(str(line.quantity)) * Decimal(str(line.rate)))
        line.cgst, line.sgst, line.igst = billing_tax.line_tax(line.amount, line.tax_percent, bool(line.tax_overseas), inv.tax_mode)
        subtotal += line.amount
        cgst, sgst, igst = cgst + line.cgst, sgst + line.sgst, igst + line.igst
    inv.subtotal, inv.cgst, inv.sgst, inv.igst = subtotal, cgst, sgst, igst
    inv.total = subtotal + cgst + sgst + igst


def _event(inv: Invoice, user: User | None, action: str, note: str = "") -> None:
    inv.events.append(InvoiceEvent(user_id=user.id if user else None, action=action, note=(note or "")[:1000]))
    if action not in ("adjusted", "reminder"):  # the invoice moved to a new stage: restart its reminder clock
        inv.status_changed_at, inv.reminders_sent, inv.last_reminder_at = utcnow(), 0, None


def issue_invoice(db: Session, org: Organisation, requests: list[BillingRequest], *, cycle: str, actor: User | None,
                  period: tuple[datetime.date, datetime.date] | None = None) -> Invoice:
    p = profile_of(db, org.id)
    if profile_missing(p):
        raise BillingError(f"{org.name}'s billing profile is incomplete ({', '.join(profile_missing(p))}).")
    s = settings_row(db)
    mode = billing_tax.tax_mode(s.state, s.state_code, p.state, p.state_code, p.country)
    inv = Invoice(number=next_number(db), organisation_id=org.id, cycle=cycle, status="pending_turacoz", tax_mode=mode,
                  currency="INR", seller=_seller(s), buyer=_buyer(org, p),
                  period_start=period[0] if period else None, period_end=period[1] if period else None)
    db.add(inv)
    with unfiltered(db):
        docs = {d.id: d for d in db.execute(select(Document).where(
            Document.id.in_([r.document_id for r in requests if r.document_id] or [-1]))).scalars()}
    for r in requests:
        ref = docs[r.document_id].document_number if r.document_id in docs else "Requirement"
        for it in r.items:
            inv.lines.append(InvoiceLine(
                request_item_id=it.id, description=f"{it.name} · {ref} ({name_of(r.user)})"[:400], sac_code=it.sac_code,
                unit=it.unit, quantity=it.quantity, rate=it.rate, amount=0, tax_percent=it.tax_percent,
                tax_overseas=it.tax_overseas))
        r.invoice = inv
    recalculate(inv)
    _event(inv, actor, "created", f"{len(requests)} request{'s' if len(requests) != 1 else ''}")
    db.flush()
    return inv


def bill_waiting(db: Session, org: Organisation, actor: User | None) -> list[Invoice]:
    """Invoice a per-submission workspace's waiting requests (e.g. once its billing profile is complete)."""
    p = profile_of(db, org.id)
    if profile_missing(p) or (p and p.billing_cycle != "per_submission"):
        return []
    return [issue_invoice(db, org, [r], cycle="per_submission", actor=actor) for r in unbilled(db, org.id)]


def month_bounds(month: datetime.date) -> tuple[datetime.date, datetime.date, datetime.datetime]:
    """First and last day of the month (India time) and the UTC instant the month ends."""
    first = month.replace(day=1)
    nxt = (first + datetime.timedelta(days=32)).replace(day=1)
    end_utc = datetime.datetime.combine(nxt, datetime.time(), IST).astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return first, nxt - datetime.timedelta(days=1), end_utc


def bill_month(db: Session, org: Organisation, month: datetime.date, actor: User | None) -> Invoice | None:
    """One invoice for everything a monthly workspace requested up to the end of `month` and not yet billed."""
    first, last, end_utc = month_bounds(month)
    reqs = unbilled(db, org.id, before=end_utc)
    if not reqs:
        return None
    return issue_invoice(db, org, reqs, cycle="monthly", actor=actor, period=(first, last))


def monthly_orgs(db: Session) -> list[Organisation]:
    with unfiltered(db):
        return list(db.execute(select(Organisation).join(OrgBillingProfile, OrgBillingProfile.organisation_id == Organisation.id)
                               .where(OrgBillingProfile.billing_cycle == "monthly", Organisation.status == "active")).scalars())


# ---------------------------------------------------------------------------------------------- approvals
def _require(inv: Invoice, *statuses: str) -> None:
    if inv.status not in statuses:
        raise BillingError(f"Invoice {inv.number} is {INVOICE_STATUSES[inv.status].lower()}; it cannot be changed now.")


def turacoz_approve(db: Session, inv: Invoice, user: User, edits: list[dict], remarks: str = "") -> list["Mail"]:
    _require(inv, "pending_turacoz")
    lines = {line.id: line for line in inv.lines}
    changes = []
    for e in edits or []:
        line = lines.get(int(e.get("id", 0)))
        if line is None:
            raise BillingError("A line on this invoice was not found.")
        qty, rate = money(e.get("quantity", line.quantity)), money(e.get("rate", line.rate))
        if qty <= 0 or rate < 0:
            raise BillingError("Quantity must be more than zero and the rate cannot be negative.")
        if qty != money(line.quantity) or rate != money(line.rate):
            changes.append(f"{line.description.split(' · ')[0]}: {_n(line.quantity)} × {_n(line.rate)} → {_n(qty)} × {_n(rate)}")
            line.quantity, line.rate = qty, rate
    recalculate(inv)
    if inv.total <= 0:
        raise BillingError("The invoice total must be more than zero.")
    inv.status, inv.turacoz_approved_by_id, inv.turacoz_approved_at = "pending_client", user.id, utcnow()
    inv.turacoz_remarks = (remarks or "").strip()[:1000]
    if changes:
        _event(inv, user, "adjusted", "; ".join(changes))
    _event(inv, user, "turacoz_approved", inv.turacoz_remarks)
    db.flush()
    return [Mail(org_admins(db, inv.organisation_id), f"Invoice {inv.number} is ready for your approval",
                 f"Turacoz has approved invoice {inv.number} for {_fmt(inv.total)}.\n\n"
                 "Please review and approve it on your TuraVector dashboard, then pay online.", "invoice_client_approval",
                 inv, extra_to=[inv.buyer.get("email")] if inv.buyer and inv.buyer.get("email") else [])]


def turacoz_reject(db: Session, inv: Invoice, user: User, reason: str) -> list["Mail"]:
    _require(inv, "pending_turacoz")
    if not (reason or "").strip():
        raise BillingError("Give a reason for cancelling the invoice.")
    inv.status, inv.turacoz_remarks = "rejected", reason.strip()[:1000]
    _event(inv, user, "cancelled", inv.turacoz_remarks)
    db.flush()
    return [Mail(org_admins(db, inv.organisation_id) + requesters(db, inv), f"Invoice {inv.number} was cancelled",
                 f"Turacoz cancelled invoice {inv.number}.\n\nReason: {inv.turacoz_remarks}", "invoice_cancelled", inv)]


def client_approve(db: Session, inv: Invoice, user: User, remarks: str = "") -> list["Mail"]:
    _require(inv, "pending_client")
    inv.status, inv.client_approved_by_id, inv.client_approved_at = "awaiting_payment", user.id, utcnow()
    inv.client_remarks = (remarks or "").strip()[:1000]
    _event(inv, user, "client_approved", inv.client_remarks)
    db.flush()
    return [Mail(approvers_for(db, inv.organisation_id), f"{inv.organisation.name} approved invoice {inv.number}",
                 f"{name_of(user)} approved invoice {inv.number} ({_fmt(inv.total)}). It is now awaiting payment.",
                 "invoice_client_approved", inv)]


def client_query(db: Session, inv: Invoice, user: User, reason: str) -> list["Mail"]:
    _require(inv, "pending_client")
    if not (reason or "").strip():
        raise BillingError("Tell Turacoz what needs to change.")
    inv.status, inv.client_remarks = "pending_turacoz", reason.strip()[:1000]
    inv.turacoz_approved_by_id = inv.turacoz_approved_at = None
    _event(inv, user, "client_query", inv.client_remarks)
    db.flush()
    return [Mail(approvers_for(db, inv.organisation_id), f"Query on invoice {inv.number} from {inv.organisation.name}",
                 f"{name_of(user)} sent invoice {inv.number} back to Turacoz:\n\n{inv.client_remarks}",
                 "invoice_client_query", inv)]


def mark_paid(db: Session, inv: Invoice, payment_id: str, user: User | None, note: str = "") -> list["Mail"]:
    if inv.status == "paid":
        return []
    _require(inv, "awaiting_payment")
    inv.status, inv.payment_id, inv.paid_at = "paid", (payment_id or "")[:100], utcnow()
    _event(inv, user, "paid", note or f"Payment {payment_id}")
    db.flush()
    return [Mail(org_admins(db, inv.organisation_id) + approvers_for(db, inv.organisation_id) + requesters(db, inv),
                 f"Payment received for invoice {inv.number}",
                 f"Payment of {_fmt(inv.total)} for invoice {inv.number} ({inv.organisation.name}) has been received."
                 f"\nPayment reference: {inv.payment_id}", "invoice_paid", inv)]


def requesters(db: Session, inv: Invoice) -> list[User]:
    return [r.user for r in inv.requests if r.user is not None]


def invoice_created_mails(db: Session, inv: Invoice) -> list["Mail"]:
    return [Mail(approvers_for(db, inv.organisation_id), f"New invoice {inv.number} for {inv.organisation.name} needs approval",
                 f"Invoice {inv.number} for {inv.organisation.name} ({_fmt(inv.total)}) was generated and is waiting "
                 "for Turacoz approval.", "invoice_created", inv)]


def _n(v) -> str:
    """2000.00 → 2000, 1.50 → 1.5"""
    return f"{Decimal(str(v)).normalize():f}"


def _fmt(v) -> str:
    return f"INR {money(v):,.2f}"


# ---------------------------------------------------------------------------------------------- notifications
@dataclass
class Mail:
    users: list[User]
    subject: str
    body: str
    email_type: str
    invoice: Invoice
    extra_to: list[str] = field(default_factory=list)


def notify_in_app(db: Session, mails: list[Mail], sender: User | None) -> None:
    """Bell notifications (added before the caller's commit). document_type "invoice" links to the invoice."""
    for m in mails:
        for u in {u.id: u for u in m.users}.values():
            db.add(DocumentNotification(receiver_id=u.id, sender_id=sender.id if sender else u.id,
                                        document_type="invoice", document_id=m.invoice.id, description=m.subject,
                                        sent_for=m.email_type, is_seen=0))


# Emails go out on a background thread (SMTP takes seconds per message); the test-suite sends inline.
SEND_IN_BACKGROUND = True


def send(db: Session, mails: list[Mail], sender: User | None = None) -> None:
    """Email everyone (after the caller has committed); a failed email never undoes the change."""
    outbox = []
    for m in mails:
        seen: set[str] = set()
        for u in m.users:
            if u.email and u.email.lower() not in seen:
                seen.add(u.email.lower())
                outbox.append((m.subject, f"Dear {name_of(u)},\n\n{m.body}\n\nTuraVector", u.email, m.email_type, u.id))
        for addr in m.extra_to:
            if addr and addr.lower() not in seen:
                seen.add(addr.lower())
                outbox.append((m.subject, f"{m.body}\n\nTuraVector", addr, m.email_type, None))
    if not outbox:
        return
    sender_id = sender.id if sender else None
    if not SEND_IN_BACKGROUND:
        _deliver_all(db, outbox, sender_id)
        return
    import threading
    from app.database import SessionLocal

    def run():
        session = SessionLocal()
        try:
            _deliver_all(session, outbox, sender_id)
        finally:
            session.close()
    threading.Thread(target=run, name="invoice-email", daemon=True).start()


def _deliver_all(db: Session, outbox: list[tuple], sender_id: int | None) -> None:
    sender = db.get(User, sender_id) if sender_id else None
    for subject, body, to, email_type, user_id in outbox:
        try:
            send_email_with_logging(db, subject, body, [to], email_type, sender_user=sender,
                                    recipient_user=db.get(User, user_id) if user_id else None)
        except Exception as exc:  # noqa: BLE001
            log.error("invoice email to %s failed: %s", to, exc)


# ---------------------------------------------------------------------------------------------- payloads
def _f(v) -> float:
    return float(v or 0)


CYCLE_LABELS = {**BILLING_CYCLES, "subscription": "Plan subscription"}  # plan payments are invoiced when paid


def invoice_row(inv: Invoice) -> dict:
    return {"id": inv.id, "number": inv.number, "organisation_id": inv.organisation_id,
            "organisation": inv.organisation.name if inv.organisation else "", "cycle": inv.cycle,
            "cycle_label": CYCLE_LABELS.get(inv.cycle, inv.cycle), "status": inv.status,
            "status_label": INVOICE_STATUSES[inv.status], "total": _f(inv.total), "currency": inv.currency,
            "period_start": iso(inv.period_start), "period_end": iso(inv.period_end),
            "created_at": iso(inv.created_at), "paid_at": iso(inv.paid_at)}


def invoice_detail(db: Session, inv: Invoice) -> dict:
    with unfiltered(db):
        users = {u.id: u for u in db.execute(select(User).where(User.id.in_(
            [e.user_id for e in inv.events if e.user_id] + [inv.turacoz_approved_by_id or 0, inv.client_approved_by_id or 0]
        ))).scalars()}
        docs = {d.id: d for d in db.execute(select(Document).where(
            Document.id.in_([r.document_id for r in inv.requests if r.document_id] or [-1]))).scalars()}
    return {
        **invoice_row(inv),
        "tax_mode": inv.tax_mode, "tax_mode_label": billing_tax.MODE_LABELS[inv.tax_mode],
        "subtotal": _f(inv.subtotal), "cgst": _f(inv.cgst), "sgst": _f(inv.sgst), "igst": _f(inv.igst),
        "amount_in_words": billing_tax.amount_in_words(inv.total),
        "seller": inv.seller or {}, "buyer": inv.buyer or {},
        "turacoz_remarks": inv.turacoz_remarks, "client_remarks": inv.client_remarks,
        "turacoz_approved_by": name_of(users.get(inv.turacoz_approved_by_id)) if inv.turacoz_approved_by_id else None,
        "turacoz_approved_at": iso(inv.turacoz_approved_at),
        "client_approved_by": name_of(users.get(inv.client_approved_by_id)) if inv.client_approved_by_id else None,
        "client_approved_at": iso(inv.client_approved_at), "payment_id": inv.payment_id,
        "lines": [{"id": line.id, "description": line.description, "sac_code": line.sac_code, "unit": line.unit,
                   "unit_label": RATE_UNITS.get(line.unit, line.unit or ""), "quantity": _f(line.quantity),
                   "rate": _f(line.rate), "amount": _f(line.amount), "tax_percent": _f(line.tax_percent),
                   "cgst": _f(line.cgst), "sgst": _f(line.sgst), "igst": _f(line.igst)} for line in inv.lines],
        "requests": [{"id": r.id, "requested_by": name_of(r.user), "created_at": iso(r.created_at),
                      "document_id": r.document_id,
                      "document": (docs[r.document_id].document_name if r.document_id in docs else None),
                      "document_number": (docs[r.document_id].document_number if r.document_id in docs else None),
                      "requirement": r.requirement or ""} for r in inv.requests],
        "events": [{"action": e.action, "note": e.note, "by": name_of(users.get(e.user_id)) if e.user_id else "System",
                    "at": iso(e.created_at)} for e in inv.events],
    }


def request_row(db: Session, r: BillingRequest, docs: dict[int, Document]) -> dict:
    """A member's own request: the services they asked for and where billing has got to (no invoice details)."""
    d = docs.get(r.document_id) if r.document_id else None
    if r.invoice is None:
        status = "Not invoiced yet"
    else:
        status = {"pending_turacoz": "Invoice being checked by Turacoz", "pending_client": "Invoice with your administrator",
                  "awaiting_payment": "Invoice approved", "paid": "Paid", "rejected": "Cancelled"}[r.invoice.status]
    return {"id": r.id, "created_at": iso(r.created_at), "document_id": r.document_id,
            "document": d.document_name if d else None, "document_number": d.document_number if d else None,
            "requirement": r.requirement or "", "status": status,
            "services": [{"name": i.name, "unit_label": RATE_UNITS.get(i.unit, i.unit or ""), "quantity": _f(i.quantity)}
                         for i in r.items]}
