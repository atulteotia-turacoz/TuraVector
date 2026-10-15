"""Superadmin: organisation workspaces — approve sign-ups, create workspaces, manage logos and members."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import require_superuser
from app.core.files import delete_file
from app.core.tenancy import platform_wide_scope
from app.core.utils import iso, user_type_display
from app.database import get_db
from app.models import Document, Organisation, OrgAssignment, OrgMembership, User, utcnow
from app.services import org_accounts, review_reports
from app.services.org_common import (
    ASSIGNMENT_LABELS, add_membership, assign_default_role, assign_team_member, contacts, new_join_code, org_payload,
    set_poc, system_team, unique_slug,
)
from app.services.users_common import create_user

def _platform_wide(db: Session = Depends(get_db)):
    """Organisations is a platform page: never limited by the workspace chosen in the top bar."""
    yield from platform_wide_scope(db)


router = APIRouter(prefix="/api/superadmin/organisations", tags=["superadmin"], dependencies=[Depends(_platform_wide)])

KINDS = ("university", "organisation", "individual")
STATUSES = ("pending", "active", "rejected", "suspended")


def _org(db: Session, org_id: int) -> Organisation:
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(404, "Organisation not found")
    return org


def _row(org: Organisation, members: int, pending: int, admins: list[str]) -> dict:
    return {**org_payload(org), "slug": org.slug, "join_code": org.join_code, "members": members,
            "pending_requests": pending, "admins": admins, "created_at": iso(org.created_at),
            "approved_at": iso(org.approved_at)}


def _admin_names(db: Session, org_ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for org_id, user in db.execute(select(OrgMembership.organisation_id, User).join(User, User.id == OrgMembership.user_id)
                                   .where(OrgMembership.organisation_id.in_(org_ids), OrgMembership.role == "admin",
                                          OrgMembership.status == "active")).all():
        out.setdefault(org_id, []).append(f"{user.first_name} {user.last_name}".strip() or user.username)
    return out


@router.get("")
def list_organisations(status: str = "", kind: str = "", q: str = "", _=Depends(require_superuser),
                       db: Session = Depends(get_db)):
    stmt = select(Organisation).order_by(Organisation.status != "pending", Organisation.created_at.desc())
    if status:
        stmt = stmt.where(Organisation.status == status)
    if kind:
        stmt = stmt.where(Organisation.kind == kind)
    if q:
        stmt = stmt.where(or_(Organisation.name.ilike(f"%{q}%"), Organisation.website.ilike(f"%{q}%")))
    orgs = db.execute(stmt).scalars().all()
    ids = [o.id for o in orgs]
    counts: dict[tuple[int, str], int] = {
        (oid, st): n for oid, st, n in db.execute(
            select(OrgMembership.organisation_id, OrgMembership.status, func.count())
            .where(OrgMembership.organisation_id.in_(ids)).group_by(OrgMembership.organisation_id, OrgMembership.status)).all()}
    admins = _admin_names(db, ids)
    status_counts = dict(db.execute(select(Organisation.status, func.count()).group_by(Organisation.status)).all())
    return {
        "organisations": [_row(o, counts.get((o.id, "active"), 0), counts.get((o.id, "pending"), 0), admins.get(o.id, []))
                          for o in orgs],
        "status_counts": {s: status_counts.get(s, 0) for s in STATUSES},
    }


@router.get("/{org_id}")
def organisation_detail(org_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    ms = db.execute(select(OrgMembership).where(OrgMembership.organisation_id == org.id)
                    .order_by(OrgMembership.role, OrgMembership.status, OrgMembership.created_at.desc())).scalars().all()
    ids = [m.user_id for m in ms]
    docs = dict(db.execute(select(Document.user_id, func.count()).where(
        Document.is_active == 1, Document.user_id.in_(ids)).group_by(Document.user_id)).all())
    reviews = review_reports.per_reviewer(db, ids)
    assigned_to = _assigned_to(db, ids)
    members = [{
        "user_id": m.user_id, "username": m.user.username, "email": m.user.email,
        "name": f"{m.user.first_name} {m.user.last_name}".strip(), "user_type_display": user_type_display(m.user),
        "role": m.role, "status": m.status, "is_active": bool(m.user.is_active), "documents": docs.get(m.user_id, 0),
        "joined_at": iso(m.created_at), "is_poc": bool(m.is_poc), "designation": m.designation,
        "reviews": reviews.get(m.user_id, {}).get("totals", dict(review_reports.EMPTY)),
        "reviews_by_organisation": reviews.get(m.user_id, {}).get("by_organisation", []),
        "assigned_to": assigned_to.get(m.user_id, []),
    } for m in ms]
    active = sum(1 for m in ms if m.status == "active")
    pending = sum(1 for m in ms if m.status == "pending")
    return {"organisation": _row(org, active, pending, _admin_names(db, [org.id]).get(org.id, [])), "members": members,
            "contacts": contacts(db, org)}


def _assigned_to(db: Session, ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for uid, name, role in db.execute(select(OrgAssignment.user_id, Organisation.name, OrgAssignment.role)
                                      .join(Organisation, Organisation.id == OrgAssignment.organisation_id)
                                      .where(OrgAssignment.user_id.in_(ids)).order_by(Organisation.name)).all():
        out.setdefault(uid, []).append(f"{name} ({ASSIGNMENT_LABELS.get(role, role)})")
    return out


@router.get("/{org_id}/members/{user_id}/reviews")
def member_reviews(org_id: int, user_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    """One member's review work: where they are assigned, numbers per university and every assignment."""
    org = _org(db, org_id)
    m = db.execute(select(OrgMembership).where(OrgMembership.organisation_id == org.id,
                                               OrgMembership.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Member not found")
    u = m.user
    items = review_reports.assignments(db, [u.id])
    placements = db.execute(select(OrgAssignment).where(OrgAssignment.user_id == u.id)
                            .order_by(OrgAssignment.created_at)).scalars().all()
    return {
        "organisation": {"id": org.id, "name": org.name, "kind": org.kind},
        "member": {"user_id": u.id, "username": u.username, "email": u.email, "phone": u.phone,
                   "name": f"{u.first_name} {u.last_name}".strip() or u.username,
                   "user_type_display": user_type_display(u), "is_active": bool(u.is_active),
                   "last_login": iso(u.last_login), "date_joined": iso(u.date_joined), "role": m.role},
        "assignments": [{"id": a.id, "organisation_id": a.organisation_id, "organisation": a.organisation.name,
                         "role": a.role, "role_label": ASSIGNMENT_LABELS.get(a.role, a.role), "designation": a.designation,
                         "since": iso(a.created_at)} for a in placements],
        "totals": review_reports.tally(items),
        "by_organisation": review_reports.by_organisation(items),
        "items": items,
    }


@router.get("/{org_id}/review-report")
def review_report(org_id: int, format: str = "xlsx", _=Depends(require_superuser), db: Session = Depends(get_db)):
    """Review work of every member of the workspace, in one file (Excel: three sheets; CSV: per university)."""
    org = _org(db, org_id)
    ids = list(db.execute(select(OrgMembership.user_id).where(OrgMembership.organisation_id == org.id,
                                                              OrgMembership.status == "active")).scalars())
    tables = review_reports.report_tables(db, ids, _assigned_to(db, ids))
    stamp = utcnow().strftime("%Y-%m-%d")
    base = f"{org.slug}-review-report-{stamp}"
    if format == "csv":
        return Response(review_reports.as_csv(tables["By university"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{base}.csv"'})
    return Response(review_reports.as_xlsx(tables),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"'})


class StatusIn(BaseModel):
    status: str


@router.post("/{org_id}/status")
def set_status(org_id: int, body: StatusIn, superuser: User = Depends(require_superuser), db: Session = Depends(get_db)):
    if body.status not in STATUSES:
        raise HTTPException(400, "Invalid status.")
    org = _org(db, org_id)
    if org.status == body.status:
        return {"message": f"{org.name} is already {org.status}."}
    org.status = body.status
    if body.status == "active" and org.approved_at is None:
        org.approved_at, org.approved_by_id = utcnow(), superuser.id
    db.commit()
    org_accounts.notify_organisation_decision(db, org)
    return {"message": f"{org.name} is now {org.status}."}


@router.post("")
def create_organisation(
    name: str = Form(""), kind: str = Form("university"), website: str = Form(""), logo: UploadFile | None = File(None),
    admin_username: str = Form(""), admin_email: str = Form(""), admin_first_name: str = Form(""),
    admin_last_name: str = Form(""), admin_password: str = Form(""),
    superuser: User = Depends(require_superuser), db: Session = Depends(get_db),
):
    """Create an active workspace, optionally with a new admin account."""
    if not name.strip():
        raise HTTPException(400, "Name is required.")
    if kind not in KINDS:
        raise HTTPException(400, "Invalid type.")
    try:
        org_accounts.validate_logo(logo)
    except org_accounts.SignupError as e:
        raise HTTPException(400, str(e)) from None
    wants_admin = any([admin_username, admin_email, admin_password])
    if wants_admin:
        if not all([admin_username.strip(), admin_email.strip(), admin_first_name.strip()]) or len(admin_password) < 8:
            raise HTTPException(400, "Admin needs a username, email, first name and a password of at least 8 characters.")
        if db.execute(select(User.id).where(or_(User.username == admin_username.strip(),
                                                User.email == admin_email.strip()))).first():
            raise HTTPException(400, "A user with that username or email already exists.")
    org = Organisation(name=name.strip(), slug=unique_slug(db, name), kind=kind, website=website.strip(),
                       logo=org_accounts.save_logo(logo), status="active",
                       join_code=None if kind == "individual" else new_join_code(db),
                       created_by_id=superuser.id, approved_by_id=superuser.id, approved_at=utcnow())
    db.add(org)
    db.flush()
    if wants_admin:
        admin = create_user(db, username=admin_username.strip(), email=admin_email.strip(), password=admin_password,
                            first_name=admin_first_name.strip(), last_name=admin_last_name.strip())
        add_membership(db, org, admin, role="admin" if kind != "individual" else "member", added_by=superuser)
        assign_default_role(db, admin, assigned_by=superuser)
    db.commit()
    return {"message": f"{org.name} was created.", "id": org.id}


@router.post("/{org_id}/update")
def update_organisation(org_id: int, name: str = Form(""), kind: str = Form(""), website: str = Form(""),
                        logo: UploadFile | None = File(None), remove_logo: bool = Form(False),
                        _=Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    if not name.strip():
        raise HTTPException(400, "Name is required.")
    if kind and kind not in KINDS:
        raise HTTPException(400, "Invalid type.")
    try:
        org_accounts.validate_logo(logo)
    except org_accounts.SignupError as e:
        raise HTTPException(400, str(e)) from None
    org.name, org.website = name.strip(), website.strip()
    if kind:
        org.kind = kind
        if kind != "individual" and not org.join_code:
            org.join_code = new_join_code(db)
    if (logo is not None and logo.filename) or remove_logo:
        old = org.logo
        org.logo = org_accounts.save_logo(logo) if logo is not None and logo.filename else ""
        if old:
            delete_file(old)
    db.commit()
    return {"message": f"{org.name} was updated."}


@router.post("/{org_id}/join-code/regenerate")
def regenerate_code(org_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    org.join_code = new_join_code(db)
    db.commit()
    return {"message": "Join code regenerated.", "join_code": org.join_code}


class MemberIn(BaseModel):
    user_id: int
    role: str = "member"
    status: str = "active"


@router.post("/{org_id}/members")
def put_member(org_id: int, body: MemberIn, superuser: User = Depends(require_superuser), db: Session = Depends(get_db)):
    """Add a user to this workspace (moving them out of their current one), or change their role/status."""
    org = _org(db, org_id)
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.is_superuser:
        raise HTTPException(400, "Superadmins are not members of a workspace.")
    if body.role not in ("admin", "member") or body.status not in ("active", "pending", "rejected"):
        raise HTTPException(400, "Invalid role or status.")
    if body.role == "admin" and org.kind == "individual":
        raise HTTPException(400, "Individual workspaces have no administrator.")
    add_membership(db, org, user, role=body.role, status=body.status, added_by=superuser)
    db.commit()
    return {"message": f"{user.username} is now {'an admin' if body.role == 'admin' else 'a member'} of {org.name}."}


class PocIn(BaseModel):
    is_poc: bool
    designation: str = ""


@router.post("/{org_id}/members/{user_id}/poc")
def set_member_poc(org_id: int, user_id: int, body: PocIn, _=Depends(require_superuser), db: Session = Depends(get_db)):
    org = _org(db, org_id)
    m = db.execute(select(OrgMembership).where(OrgMembership.organisation_id == org.id,
                                               OrgMembership.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Member not found")
    try:
        set_poc(m, body.is_poc, body.designation)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    db.commit()
    return {"message": f"{m.user.username} is {'now' if body.is_poc else 'no longer'} a point of contact of {org.name}."}


class AssignmentIn(BaseModel):
    user_id: int
    role: str = "poc"
    designation: str = ""


@router.post("/{org_id}/assignments")
def add_assignment(org_id: int, body: AssignmentIn, superuser: User = Depends(require_superuser),
                   db: Session = Depends(get_db)):
    """Assign a Turacoz (system) user to this workspace as its PoC or a Reviewer."""
    org = _org(db, org_id)
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    try:
        assign_team_member(db, org, user, body.role, body.designation, superuser)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    db.commit()
    return {"message": f"{user.username} assigned to {org.name} as {ASSIGNMENT_LABELS[body.role]}."}


@router.delete("/{org_id}/assignments/{assignment_id}")
def remove_assignment(org_id: int, assignment_id: int, _=Depends(require_superuser), db: Session = Depends(get_db)):
    a = db.get(OrgAssignment, assignment_id)
    if a is None or a.organisation_id != org_id:
        raise HTTPException(404, "Assignment not found")
    name, org_name = a.user.username, a.organisation.name
    db.delete(a)
    db.commit()
    return {"message": f"{name} is no longer assigned to {org_name}."}


@router.get("/system-users/search")
def search_system_users(q: str = "", _=Depends(require_superuser), db: Session = Depends(get_db)):
    """Turacoz team members, to assign to a workspace."""
    team = system_team(db)
    if team is None:
        return {"users": []}
    stmt = select(User).join(OrgMembership, OrgMembership.user_id == User.id).where(
        OrgMembership.organisation_id == team.id, User.is_active == 1)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like), User.first_name.ilike(like),
                              User.last_name.ilike(like)))
    rows = db.execute(stmt.order_by(User.first_name, User.username).limit(30)).scalars().all()
    return {"users": [{"id": u.id, "username": u.username, "email": u.email, "name": f"{u.first_name} {u.last_name}".strip(),
                       "user_type_display": user_type_display(u)} for u in rows]}


@router.get("/users/search")
def search_users(q: str = "", _=Depends(require_superuser), db: Session = Depends(get_db)):
    """Users to add to a workspace, with the workspace they are in now."""
    stmt = select(User, Organisation.name).outerjoin(OrgMembership, OrgMembership.user_id == User.id) \
        .outerjoin(Organisation, Organisation.id == OrgMembership.organisation_id).where(User.is_superuser == 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like), User.first_name.ilike(like),
                              User.last_name.ilike(like)))
    rows = db.execute(stmt.order_by(User.username).limit(20)).all()
    return {"users": [{"id": u.id, "username": u.username, "email": u.email,
                       "name": f"{u.first_name} {u.last_name}".strip(), "organisation": org_name}
                      for u, org_name in rows]}
