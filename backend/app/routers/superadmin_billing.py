"""Superadmin: Turacoz's billing details, the invoice approvers and each workspace's billing profile."""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.core.tenancy import is_system_user, unfiltered
from app.core.utils import iso
from app.database import get_db
from app.models import BillingApprover, OrgAssignment, Organisation, OrgMembership, User
from app.services import billing, billing_reminders

router = APIRouter(prefix="/api/superadmin/billing", tags=["superadmin"])

SETTINGS_FIELDS = {"company_name": 200, "address": 500, "state": 100, "state_code": 5, "country": 100, "gstin": 20,
                   "pan": 20, "email": 200, "phone": 50, "invoice_prefix": 10, "bank_details": 1000, "terms": 2000}


def _settings(s) -> dict:
    fy = billing.financial_year(datetime.datetime.now(billing.IST).date())
    seq = s.sequence_next if s.sequence_year == fy else 1
    return {**{k: getattr(s, k) for k in SETTINGS_FIELDS}, "next_number": f"{s.invoice_prefix}{fy}-{seq:04d}",
            **billing_reminders.settings_payload(s)}


@router.get("/settings")
def get_settings(_=Depends(require_superuser), db: Session = Depends(get_db)):
    s = billing.settings_row(db)
    db.commit()
    return _settings(s)


@router.put("/settings")
def put_settings(body: dict, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    s = billing.settings_row(db)
    for k, size in SETTINGS_FIELDS.items():
        if k in body and body[k] is not None:
            setattr(s, k, str(body[k]).strip()[:size])
    s.gstin, s.pan = s.gstin.upper(), s.pan.upper()
    s.invoice_prefix = "".join(ch for ch in s.invoice_prefix.upper() if ch.isalnum())[:6]
    if not s.company_name or not s.invoice_prefix:
        raise HTTPException(400, "Company name and invoice prefix are required.")
    if not s.state:
        raise HTTPException(400, "Your state is required — it decides between CGST + SGST and IGST.")
    try:
        billing_reminders.apply_settings(s, body)
    except (billing.BillingError, ValueError) as exc:
        raise HTTPException(400, str(exc) if isinstance(exc, billing.BillingError) else "Reminder days must be whole numbers.") from None
    s.updated_by_id = user.id
    db.commit()
    return {"message": "Billing settings saved.", **_settings(s)}


# ------------------------------------------------------------------ approvers
def _approvers(db: Session) -> list[dict]:
    with unfiltered(db):
        rows = db.execute(select(BillingApprover).order_by(BillingApprover.id)).scalars().all()
    return [{"id": a.id, "user_id": a.user_id, "name": billing.name_of(a.user), "email": a.user.email,
             "since": iso(a.created_at)} for a in rows]


@router.get("/approvers")
def list_approvers(_=Depends(require_superuser), db: Session = Depends(get_db)):
    with unfiltered(db):
        team = db.execute(select(User).join(OrgMembership, OrgMembership.user_id == User.id).join(
            Organisation, Organisation.id == OrgMembership.organisation_id).where(
            Organisation.kind == "system", User.is_active == 1).order_by(User.first_name)).scalars().all()
    current = {a["user_id"] for a in _approvers(db)}
    with unfiltered(db):
        assigned = db.execute(select(OrgAssignment, Organisation).join(Organisation, Organisation.id == OrgAssignment.organisation_id)
                              .where(OrgAssignment.role == billing.FINANCE).order_by(Organisation.name)).all()
    return {"approvers": _approvers(db),
            "assigned": [{"id": a.id, "organisation_id": o.id, "organisation": o.name, "user_id": a.user_id,
                          "name": billing.name_of(a.user), "email": a.user.email} for a, o in assigned],
            "candidates": [{"user_id": u.id, "name": billing.name_of(u), "email": u.email} for u in team if u.id not in current]}


class ApproverIn(BaseModel):
    user_id: int


@router.post("/approvers")
def add_approver(body: ApproverIn, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    with unfiltered(db):
        target = db.get(User, body.user_id)
        exists = db.execute(select(BillingApprover.id).where(BillingApprover.user_id == body.user_id)).first()
    if target is None:
        raise HTTPException(404, "User not found")
    if not is_system_user(target, db):
        raise HTTPException(400, "Only members of the Turacoz team can be Financial Managers.")
    if not exists:
        db.add(BillingApprover(user_id=target.id, added_by_id=user.id))
        db.commit()
    return {"message": f"{billing.name_of(target)} is now a default Financial Manager.", "approvers": _approvers(db)}


@router.delete("/approvers/{approver_id}")
def remove_approver(approver_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    with unfiltered(db):
        a = db.get(BillingApprover, approver_id)
    if a is None:
        raise HTTPException(404, "Approver not found")
    name = billing.name_of(a.user)
    db.delete(a)
    db.commit()
    return {"message": f"{name} is no longer a default Financial Manager.", "approvers": _approvers(db)}


# ------------------------------------------------------------------ a workspace's billing profile
def _org(db: Session, org_id: int) -> Organisation:
    with unfiltered(db):
        org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(404, "Organisation not found")
    return org


@router.get("/organisations/{org_id}/profile")
def get_profile(org_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    return billing.profile_payload(org, billing.profile_of(db, org.id), db)


@router.put("/organisations/{org_id}/profile")
def put_profile(org_id: int, body: dict, user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    if org.kind not in billing.CLIENT_KINDS:
        raise HTTPException(400, "Billing profiles are for universities and organisations.")
    try:
        p = billing.save_profile(db, org, user, body, True)
        billing_reminders.apply_profile(p, body)
        created = billing.bill_waiting(db, org, user)
    except ValueError:
        raise HTTPException(400, "Reminder days must be whole numbers.") from None
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None
    mails = [m for inv in created for m in billing.invoice_created_mails(db, inv)]
    billing.notify_in_app(db, mails, user)
    db.commit()
    billing.send(db, mails, user)
    msg = "Billing profile saved."
    if created:
        msg += f" {len(created)} waiting request{'s were' if len(created) != 1 else ' was'} invoiced."
    return {"message": msg, **billing.profile_payload(org, p, db)}


@router.post("/reminders/run")
def run_reminders(_=Depends(require_superuser), db: Session = Depends(get_db)):
    """Send the reminders that are due now (they are also checked every hour)."""
    sent = billing_reminders.send_due(db)
    return {"message": f"Sent {len(sent)} reminder{'s' if len(sent) != 1 else ''}" + (f": {', '.join(sent)}." if sent else "."),
            "sent": sent}
