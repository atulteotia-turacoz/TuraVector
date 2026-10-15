"""University / organisation admin console: members, join requests, workspace settings.

Only admins of an active university/organisation workspace; every query is limited to their
workspace explicitly (memberships) and by the tenancy filter (users, documents, references).
"""
import secrets
import string

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.files import delete_file
from app.core.security import make_password
from app.core.tenancy import active_membership, is_org_admin, unfiltered
from app.core.utils import iso, user_type_display
from app.database import get_db
from app.core.permissions import get_all_roles
from app.models import (
    AssignedReviewer, Document, DocumentVersion, LoginLog, OrgAssignment, OrgMembership, ReferenceDocument, User,
    RateCardItem, RateService, UserType, utcnow,
)
from app.models.rates import RATE_UNITS
from app.services import org_accounts, review_reports
from app.services.org_common import assign_default_role, contacts, new_join_code, org_payload, set_poc
from app.services.users_common import create_user

router = APIRouter(prefix="/api/org", tags=["organisation"])

# account types a workspace admin may give its members
MEMBER_USER_TYPES = ("student", "researcher", "teacher", "reviewer")


def require_org_admin(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> OrgMembership:
    if not is_org_admin(user, db):
        raise HTTPException(403, "Only the administrator of a university or organisation can do this.")
    return active_membership(db, user)


def _member(db: Session, admin: OrgMembership, user_id: int) -> OrgMembership:
    m = db.execute(select(OrgMembership).where(
        OrgMembership.user_id == user_id, OrgMembership.organisation_id == admin.organisation_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Member not found")
    return m


def _member_row(m: OrgMembership, docs: dict[int, int]) -> dict:
    u = m.user
    return {
        "user_id": u.id, "username": u.username, "email": u.email, "first_name": u.first_name,
        "last_name": u.last_name, "user_type": u.user_type, "user_type_display": user_type_display(u),
        "role": m.role, "status": m.status, "is_active": bool(u.is_active), "date_joined": iso(u.date_joined),
        "last_login": iso(u.last_login), "documents": docs.get(u.id, 0), "requested_at": iso(m.created_at),
        "is_poc": bool(m.is_poc), "designation": m.designation,
    }


def _random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ------------------------------------------------------------------ overview & members
@router.get("/overview")
def overview(admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    org = admin.organisation
    counts = dict(db.execute(select(OrgMembership.status, func.count()).where(
        OrgMembership.organisation_id == org.id).group_by(OrgMembership.status)).all())
    return {
        "organisation": {**org_payload(org, admin), "join_code": org.join_code},
        "members": counts.get("active", 0),
        "pending_requests": counts.get("pending", 0),
        "documents": db.scalar(select(func.count()).select_from(Document).where(Document.is_active == 1)),
        "references": db.scalar(select(func.count()).select_from(ReferenceDocument).where(ReferenceDocument.is_active == 1)),
        "member_user_types": [{"value": c, "label": c.title()} for c in MEMBER_USER_TYPES],
    }


@router.get("/members")
def members(status: str = "active", admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(OrgMembership).where(
        OrgMembership.organisation_id == admin.organisation_id, OrgMembership.status == status)
        .order_by(OrgMembership.role, OrgMembership.created_at.desc())).scalars().all()
    docs = dict(db.execute(select(Document.user_id, func.count()).where(Document.is_active == 1)
                           .group_by(Document.user_id)).all())
    return {"members": [_member_row(m, docs) for m in rows]}


STAGES = {0: "Draft", 1: "Under Review", 2: "Approved", 3: "Draft Under Revision"}


@router.get("/members/{user_id}")
def member_detail(user_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    """Everything about one member: profile, documents, references, review work and recent sign-ins."""
    m = _member(db, admin, user_id)
    u = m.user
    docs = db.execute(select(Document).where(Document.user_id == u.id, Document.is_active == 1)
                      .order_by(Document.created_at.desc())).scalars().all()
    versions = dict(db.execute(select(DocumentVersion.document_id, func.count()).where(
        DocumentVersion.document_id.in_([d.id for d in docs])).group_by(DocumentVersion.document_id)).all()) if docs else {}
    by_stage = {label: sum(1 for d in docs if d.stage_status == code) for code, label in STAGES.items()}
    refs = db.execute(select(ReferenceDocument).where(ReferenceDocument.user_id == u.id, ReferenceDocument.is_active == 1)
                      .order_by(ReferenceDocument.created_at.desc())).scalars().all()
    reviews = db.execute(select(AssignedReviewer).where(AssignedReviewer.user_id == u.id, AssignedReviewer.is_active == 1)
                         .order_by(AssignedReviewer.created_at.desc())).scalars().all()
    logins = db.execute(select(LoginLog).where(LoginLog.user_id == u.id).order_by(LoginLog.login_time.desc()).limit(10)).scalars().all()
    row = _member_row(m, {u.id: len(docs)})
    return {
        "member": {**row, "phone": u.phone, "address": u.address, "is_self": u.id == admin.user_id,
                   "roles": [r.name for r in get_all_roles(db, u)]},
        "stats": {"documents": len(docs), "by_stage": by_stage, "references": len(refs),
                  "reviews_pending": sum(1 for r in reviews if not r.is_completed),
                  "reviews_completed": sum(1 for r in reviews if r.is_completed)},
        "documents": [{"id": d.id, "number": d.document_number, "name": d.document_name,
                       "stage": STAGES.get(d.stage_status, str(d.stage_status)), "stage_status": d.stage_status,
                       "versions": versions.get(d.id, 0), "created_at": iso(d.created_at), "updated_at": iso(d.updated_at)}
                      for d in docs],
        "references": [{"id": r.id, "number": r.reference_number, "name": r.document_name, "type": r.type,
                        "created_at": iso(r.created_at)} for r in refs],
        "reviews": [{"id": r.id, "document_id": r.document_version.document_id if r.document_version else None,
                     "document": (f"{r.document_version.version_number}" if r.document_version else ""),
                     "review_date": iso(r.review_date), "completed": bool(r.is_completed),
                     "completed_at": iso(r.completed_at), "assigned_at": iso(r.created_at)} for r in reviews],
        "logins": [{"time": iso(l.login_time), "status": l.status, "ip": l.ip_address} for l in logins],
    }


class MemberIn(BaseModel):
    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    password: str = ""
    user_type: str = "student"
    role: str = "member"
    send_welcome_email: bool = True


@router.post("/members")
def add_member(body: MemberIn, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    if not all([body.username.strip(), body.email.strip(), body.first_name.strip()]):
        raise HTTPException(400, "Username, email and first name are required.")
    if body.user_type not in MEMBER_USER_TYPES or body.role not in ("admin", "member"):
        raise HTTPException(400, "Invalid account type or role.")
    if body.password and len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters long.")
    from app.core.tenancy import unfiltered
    with unfiltered(db):  # usernames/emails are unique across every workspace
        if db.execute(select(User.id).where(User.username == body.username.strip())).first():
            raise HTTPException(400, "Username already exists.")
        if db.execute(select(User.id).where(User.email == body.email.strip())).first():
            raise HTTPException(400, "Email already registered.")
    password = body.password or _random_password()
    user_type = db.execute(select(UserType).where(UserType.code == body.user_type, UserType.is_active == 1)).scalars().first()
    user = create_user(db, username=body.username.strip(), email=body.email.strip(), password=password,
                       first_name=body.first_name.strip(), last_name=body.last_name.strip(), user_type=body.user_type,
                       user_type_new_id=user_type.id if user_type else None)
    db.flush()  # joins the admin's workspace automatically (tenancy)
    m = _member(db, admin, user.id)
    m.role = body.role
    assign_default_role(db, user, assigned_by=admin.user)
    db.commit()
    org = admin.organisation
    if body.send_welcome_email:
        org_accounts._mail(db, [user], f"Your TuraVector account at {org.name}",
                           f"Hello {user.first_name},\n\nAn account was created for you in {org.name} on TuraVector.\n\n"
                           f"Username: {user.username}\nPassword: {password}\n\n"
                           f"Sign in: {org_accounts.frontend_url('/login/')}\nPlease change your password after signing in.")
    return {"message": f"{user.first_name} {user.last_name} was added to {org.name}.".replace("  ", " "),
            "user_id": user.id, "password": None if body.password else password}


@router.post("/members/{user_id}/approve")
def approve(user_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    m = _member(db, admin, user_id)
    if m.status != "pending":
        raise HTTPException(400, "This request has already been handled.")
    m.status, m.added_by_id = "active", admin.user_id
    db.commit()
    org_accounts.notify_membership_decision(db, m)
    return {"message": f"{m.user.first_name} {m.user.last_name} can now sign in."}


@router.post("/members/{user_id}/reject")
def reject(user_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    m = _member(db, admin, user_id)
    if m.status != "pending":
        raise HTTPException(400, "This request has already been handled.")
    m.status = "rejected"
    db.commit()
    org_accounts.notify_membership_decision(db, m)
    return {"message": "Request rejected."}


@router.get("/contacts")
def org_contacts(admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    """The workspace's points of contact and the Turacoz team assigned to it (read-only here)."""
    return contacts(db, admin.organisation)


class PocIn(BaseModel):
    is_poc: bool
    designation: str = ""


@router.post("/members/{user_id}/poc")
def set_member_poc(user_id: int, body: PocIn, admin: OrgMembership = Depends(require_org_admin),
                   db: Session = Depends(get_db)):
    m = _member(db, admin, user_id)
    try:
        set_poc(m, body.is_poc, body.designation)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    db.commit()
    name = f"{m.user.first_name} {m.user.last_name}".strip() or m.user.username
    return {"message": f"{name} is {'now' if body.is_poc else 'no longer'} a point of contact."}


# ------------------------------------------------------------------ our rate card (read-only)
@router.get("/rate-card")
def our_rate_card(admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    """The rates Turacoz charges this workspace. Standard rates are not shown here."""
    items = db.execute(select(RateCardItem).join(RateService, RateService.id == RateCardItem.service_id)
                       .where(RateCardItem.organisation_id == admin.organisation_id)
                       .order_by(RateService.sort_order, RateService.name)).scalars().all()
    return {"items": [{
        "id": i.id, "name": i.service.name, "description": i.service.description,
        "unit_label": RATE_UNITS.get(i.service.unit, i.service.unit or ""), "rate": float(i.rate),
        "tax_percent": float(i.service.tax_percent), "currency": i.service.currency, "notes": i.notes,
    } for i in items]}


# ------------------------------------------------------------------ reviewers of our documents
def _reviewer_rows(db: Session, org) -> tuple[list[dict], list[dict], dict[int, User]]:
    """Everyone reviewing this workspace's documents (members and Turacoz staff), with their numbers —
    counting only reviews of this workspace's documents."""
    items, people = review_reports.workspace_reviewers(db, org.id)
    with unfiltered(db):
        team = {a.user_id: a for a in db.execute(select(OrgAssignment).where(
            OrgAssignment.organisation_id == org.id, OrgAssignment.role == "reviewer")).scalars()}
        for uid in team:
            if uid not in people:
                people[uid] = db.get(User, uid)
        member_ids = set(db.execute(select(OrgMembership.user_id).where(
            OrgMembership.organisation_id == org.id)).scalars())
    by_reviewer: dict[int, list[dict]] = {}
    for i in items:
        by_reviewer.setdefault(i["reviewer_id"], []).append(i)
    rows = []
    for uid, u in people.items():
        rows.append({
            "user_id": uid, "name": f"{u.first_name} {u.last_name}".strip() or u.username, "username": u.username,
            "email": u.email, "user_type_display": user_type_display(u), "is_active": bool(u.is_active),
            "source": "member" if uid in member_ids else "turacoz",
            "assigned_to_us": uid in team, **review_reports.tally(by_reviewer.get(uid, [])),
        })
    rows.sort(key=lambda r: (-r["assigned"], r["name"].lower()))
    return rows, items, people


@router.get("/reviewers")
def reviewers(admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    rows, items, _ = _reviewer_rows(db, admin.organisation)
    return {"reviewers": rows, "totals": review_reports.tally(items)}


@router.get("/reviewers/{user_id}")
def reviewer_detail(user_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    rows, items, _ = _reviewer_rows(db, admin.organisation)
    row = next((r for r in rows if r["user_id"] == user_id), None)
    if row is None:
        raise HTTPException(404, "This person does not review your documents.")
    mine = [i for i in items if i["reviewer_id"] == user_id]
    return {"reviewer": row, "totals": review_reports.tally(mine), "items": mine}


@router.get("/review-report")
def review_report(format: str = "xlsx", admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    """Review work on this workspace's documents, every reviewer in one file."""
    org = admin.organisation
    rows, items, _ = _reviewer_rows(db, org)
    ids = [r["user_id"] for r in rows]
    labels = {r["user_id"]: [f"{org.name} ({'Member' if r['source'] == 'member' else 'Turacoz'})"] for r in rows}
    tables = review_reports.report_tables(db, ids, labels, items)
    base = f"{org.slug}-reviewers-{utcnow().strftime('%Y-%m-%d')}"
    if format == "csv":
        return Response(review_reports.as_csv(tables["Summary"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{base}.csv"'})
    return Response(review_reports.as_xlsx(tables),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"'})


class RoleIn(BaseModel):
    role: str


@router.post("/members/{user_id}/role")
def set_role(user_id: int, body: RoleIn, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    if body.role not in ("admin", "member"):
        raise HTTPException(400, "Invalid role.")
    m = _member(db, admin, user_id)
    if m.status != "active":
        raise HTTPException(400, "Only active members can be made administrators.")
    if m.role == "admin" and body.role == "member" and _admin_count(db, admin.organisation_id) <= 1:
        raise HTTPException(400, "A workspace needs at least one administrator.")
    m.role = body.role
    db.commit()
    return {"message": "Role updated."}


def _admin_count(db: Session, org_id: int) -> int:
    return db.scalar(select(func.count()).select_from(OrgMembership).where(
        OrgMembership.organisation_id == org_id, OrgMembership.role == "admin", OrgMembership.status == "active"))


@router.post("/members/{user_id}/toggle-active")
def toggle_active(user_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    if user_id == admin.user_id:
        raise HTTPException(400, "You cannot deactivate your own account.")
    m = _member(db, admin, user_id)
    m.user.is_active = 0 if m.user.is_active else 1
    db.commit()
    return {"message": "Account activated." if m.user.is_active else "Account deactivated.",
            "is_active": bool(m.user.is_active)}


@router.post("/members/{user_id}/reset-password")
def reset_password(user_id: int, admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    m = _member(db, admin, user_id)
    password = _random_password()
    m.user.password = make_password(password)
    db.commit()
    return {"message": f"New password for {m.user.username}: {password}", "password": password}


# ------------------------------------------------------------------ workspace settings
@router.post("/settings")
def update_settings(name: str = Form(""), website: str = Form(""), logo: UploadFile | None = File(None),
                    remove_logo: bool = Form(False), admin: OrgMembership = Depends(require_org_admin),
                    db: Session = Depends(get_db)):
    org = admin.organisation
    if not name.strip():
        raise HTTPException(400, "Enter the name of your university or organisation.")
    try:
        org_accounts.validate_logo(logo)
    except org_accounts.SignupError as e:
        raise HTTPException(400, str(e)) from None
    org.name, org.website = name.strip(), website.strip()
    if (logo is not None and logo.filename) or remove_logo:
        old = org.logo
        org.logo = org_accounts.save_logo(logo) if logo is not None and logo.filename else ""
        if old:
            delete_file(old)
    db.commit()
    return {"message": "Workspace updated.", "organisation": {**org_payload(org, admin), "join_code": org.join_code}}


@router.post("/join-code/regenerate")
def regenerate_join_code(admin: OrgMembership = Depends(require_org_admin), db: Session = Depends(get_db)):
    org = admin.organisation
    org.join_code = new_join_code(db)
    db.commit()
    return {"message": "A new join code was created. The old code no longer works.", "join_code": org.join_code}
