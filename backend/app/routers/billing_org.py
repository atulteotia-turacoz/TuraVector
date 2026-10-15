"""Invoices for a university / organisation admin, and the member's own service requests.

The admin sees their workspace's invoices once Turacoz has approved them, approves them (or sends them
back with a query) and pays online. Members see only the services they asked for and how far billing got.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.tenancy import unfiltered
from app.database import get_db
from app.models import BillingRequest, Document, Invoice, OrgMembership, User
from app.routers.org_admin import require_org_admin
from app.services import billing, billing_pdf, billing_reports, payments
from app.services.review_reports import as_csv, as_xlsx

router = APIRouter(tags=["billing"])

# Turacoz is still checking an invoice in these states; the client does not see it yet
HIDDEN_FROM_CLIENT = ("pending_turacoz",)


def _invoice(db: Session, admin: OrgMembership, invoice_id: int) -> Invoice:
    with unfiltered(db):
        inv = db.get(Invoice, invoice_id)
    if inv is None or inv.organisation_id != admin.organisation_id or inv.status in HIDDEN_FROM_CLIENT:
        raise HTTPException(404, "Invoice not found")
    return inv


def _done(db: Session, inv: Invoice, user: User, mails: list, message: str) -> dict:
    billing.notify_in_app(db, mails, user)
    db.commit()
    billing.send(db, mails, user)
    return {"message": message, "invoice": billing.invoice_detail(db, inv)}


def _call(fn, *args):
    try:
        return fn(*args)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/api/org/invoices")
def list_invoices(status: str = "", admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    with unfiltered(db):
        base = select(Invoice).where(Invoice.organisation_id == admin.organisation_id, Invoice.status.not_in(HIDDEN_FROM_CLIENT))
        counts = dict(db.execute(select(Invoice.status, func.count()).where(
            Invoice.organisation_id == admin.organisation_id).group_by(Invoice.status)).all())
        rows = db.execute((base.where(Invoice.status == status) if status else base).order_by(Invoice.id.desc())).scalars().all()
        due = db.scalar(select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.organisation_id == admin.organisation_id, Invoice.status.in_(("pending_client", "awaiting_payment"))))
    return {"invoices": [billing.invoice_row(i) for i in rows],
            "counts": {k: v for k, v in counts.items() if k not in HIDDEN_FROM_CLIENT},
            "outstanding": float(due or 0)}


@router.get("/api/org/invoices/{invoice_id}")
def invoice(invoice_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    return billing.invoice_detail(db, _invoice(db, admin, invoice_id))


@router.get("/api/org/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    d = billing.invoice_detail(db, _invoice(db, admin, invoice_id))
    return Response(billing_pdf.invoice_pdf(d), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{d["number"]}.pdf"'})


class NoteIn(BaseModel):
    remarks: str = ""


@router.post("/api/org/invoices/{invoice_id}/approve")
def approve(invoice_id: int, body: NoteIn, admin: OrgMembership = Depends(require_org_admin),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = _invoice(db, admin, invoice_id)
    mails = _call(billing.client_approve, db, inv, user, body.remarks)
    return _done(db, inv, user, mails, f"Invoice {inv.number} approved. You can pay it now.")


@router.post("/api/org/invoices/{invoice_id}/query")
def query(invoice_id: int, body: NoteIn, admin: OrgMembership = Depends(require_org_admin),
          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = _invoice(db, admin, invoice_id)
    mails = _call(billing.client_query, db, inv, user, body.remarks)
    billing.notify_in_app(db, mails, user)
    db.commit()
    billing.send(db, mails, user)
    return {"message": f"Invoice {inv.number} was sent back to Turacoz with your query."}


# ------------------------------------------------------------------ payment
@router.post("/api/org/invoices/{invoice_id}/pay")
def start_payment(invoice_id: int, admin: OrgMembership = Depends(require_org_admin),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = _invoice(db, admin, invoice_id)
    if inv.status != "awaiting_payment":
        raise HTTPException(400, "Only an approved, unpaid invoice can be paid.")
    gw = payments.active(db)
    if gw is None or payments.missing_fields(gw):
        raise HTTPException(400, "Online payment has not been set up yet. Please contact Turacoz to pay this invoice.")
    if gw.code != "razorpay":
        raise HTTPException(400, f"Online payment through {payments.SPECS[gw.code].name} is not available yet.")
    try:
        order = payments.ADAPTERS[gw.code].create_order(gw, inv.total, inv.number, {"invoice": inv.number})
    except payments.PaymentError as exc:
        raise HTTPException(400, str(exc)) from None
    inv.gateway, inv.gateway_order_id = gw.code, order["order_id"]
    db.commit()
    return {**order, "name": (inv.seller or {}).get("company_name") or "Turacoz",
            "description": f"Invoice {inv.number}",
            "prefill": {"name": billing.name_of(user), "email": user.email or "", "contact": user.phone or ""}}


class VerifyIn(BaseModel):
    order_id: str
    payment_id: str
    signature: str


@router.post("/api/org/invoices/{invoice_id}/pay/verify")
def verify_payment(invoice_id: int, body: VerifyIn, admin: OrgMembership = Depends(require_org_admin),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv = _invoice(db, admin, invoice_id)
    gw = payments.get(db, inv.gateway or "razorpay")
    if not inv.gateway_order_id or body.order_id != inv.gateway_order_id or gw is None or not payments.ADAPTERS[gw.code].verify(
            gw, order_id=body.order_id, payment_id=body.payment_id, signature=body.signature):
        raise HTTPException(400, "The payment could not be verified. If money was deducted, contact Turacoz with the payment reference.")
    mails = _call(billing.mark_paid, db, inv, body.payment_id, user)
    return _done(db, inv, user, mails, f"Payment received. Invoice {inv.number} is paid.")


# ------------------------------------------------------------------ billing profile
@router.get("/api/org/billing-profile")
def billing_profile(admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    return billing.profile_payload(admin.organisation, billing.profile_of(db, admin.organisation_id))


class ProfileIn(BaseModel):
    legal_name: str = ""
    address: str = ""
    state: str = ""
    state_code: str = ""
    country: str = "India"
    gstin: str = ""
    billing_email: str = ""


@router.put("/api/org/billing-profile")
def save_billing_profile(body: ProfileIn, admin: OrgMembership = Depends(require_org_admin),
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The admin keeps their billing address and GSTIN up to date; Turacoz chooses the billing cycle."""
    org = admin.organisation
    p = _call(billing.save_profile, db, org, user, body.model_dump(), False)
    created = _call(billing.bill_waiting, db, org, user)
    mails = [m for inv in created for m in billing.invoice_created_mails(db, inv)]
    billing.notify_in_app(db, mails, user)
    db.commit()
    billing.send(db, mails, user)
    return {"message": "Billing details saved.", **billing.profile_payload(org, p)}


# ------------------------------------------------------------------ a member's own requests
@router.get("/api/billing/my-requests")
def my_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    with unfiltered(db):
        reqs = db.execute(select(BillingRequest).where(BillingRequest.user_id == user.id)
                          .order_by(BillingRequest.id.desc())).scalars().all()
        docs = {d.id: d for d in db.execute(select(Document).where(
            Document.id.in_([r.document_id for r in reqs if r.document_id] or [-1]))).scalars()}
    return {"requests": [billing.request_row(db, r, docs) for r in reqs],
            "rate_card": billing.rate_card_for(db, user)}


# ------------------------------------------------------------------ finance analytics & reports (own workspace)
@router.get("/api/org/finance/analytics")
def finance_analytics(admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    return billing_reports.analytics(db, {admin.organisation_id}, 12)


def _report(db: Session, admin: OrgMembership, date_from: str, date_to: str, status: str) -> dict:
    try:
        start, end = billing_reports.resolve_range(date_from, date_to)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None
    if status in HIDDEN_FROM_CLIENT:
        status = "none"
    data = billing_reports.report(db, {admin.organisation_id}, start, end, None, status, client=True)
    data.pop("by_organisation", None)
    return data


@router.get("/api/org/finance/reports")
def finance_reports(date_from: str = "", date_to: str = "", status: str = "",
                    admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    return _report(db, admin, date_from, date_to, status)


@router.get("/api/org/finance/reports/export")
def finance_export(format: str = "xlsx", section: str = "", date_from: str = "", date_to: str = "", status: str = "",
                   admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    data = _report(db, admin, date_from, date_to, status)
    name = f"{admin.organisation.slug}_finance_{data['period']['from']}_to_{data['period']['to']}"
    if format == "pdf":
        body, media, name = billing_reports.as_pdf(data, f"{admin.organisation.name} — finance report"), "application/pdf", name + ".pdf"
    elif format == "csv":
        if section not in billing_reports.SHEETS or section not in data:
            raise HTTPException(400, "Choose a report to download.")
        body, media, name = as_csv(next(iter(billing_reports.tables(data, section).values()))), "text/csv", f"{name}_{section}.csv"
    else:
        body, media, name = as_xlsx(billing_reports.tables(data)), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", name + ".xlsx"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
