"""Shared helpers for organisation workspaces."""
import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.files import media_url
from app.models import Organisation, OrgMembership, Role, User, UserRole

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def new_join_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        if not db.execute(select(Organisation.id).where(Organisation.join_code == code)).first():
            return code


def unique_slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:200] or "workspace"
    slug, n = base, 2
    while db.execute(select(Organisation.id).where(Organisation.slug == slug)).first():
        slug, n = f"{base}-{n}", n + 1
    return slug


def org_payload(org: Organisation | None, membership: OrgMembership | None = None) -> dict | None:
    if org is None:
        return None
    return {
        "id": org.id,
        "name": org.name,
        "kind": org.kind,
        "website": org.website,
        "logo_url": media_url(org.logo) if org.logo else None,
        "status": org.status,
        "role": membership.role if membership else None,
        "membership_status": membership.status if membership else None,
    }


def add_membership(db: Session, org: Organisation, user: User, role: str = "member", status: str = "active",
                   added_by: User | None = None) -> OrgMembership:
    """Put the user in `org` (replacing an automatic membership created in the same request)."""
    db.flush()
    m = db.execute(select(OrgMembership).where(OrgMembership.user_id == user.id)).scalar_one_or_none()
    if m is None:
        m = OrgMembership(user_id=user.id)
        db.add(m)
    m.organisation_id, m.role, m.status = org.id, role, status
    m.added_by_id = added_by.id if added_by else None
    db.flush()
    user.__dict__.pop("_org_membership", None)
    return m


# account type -> the role a new workspace member starts with (gives them the matching dashboards)
DEFAULT_ROLE_BY_TYPE = {"student": "Student", "researcher": "Researcher", "teacher": "Teacher", "reviewer": "Reviewer"}


def assign_default_role(db: Session, user: User, assigned_by: User | None = None) -> None:
    """Give a newly created workspace member the role of their account type, unless they already have one."""
    name = DEFAULT_ROLE_BY_TYPE.get(user.user_type)
    if not name:
        return
    db.flush()
    if db.execute(select(UserRole.id).where(UserRole.user_id == user.id).limit(1)).first():
        return
    role = db.execute(select(Role).where(Role.name == name, Role.is_active == 1)).scalars().first()
    if role:
        db.add(UserRole(user_id=user.id, role_id=role.id, assigned_by_id=assigned_by.id if assigned_by else None))


# ---------------------------------------------------------------------------------------------- PoCs
ASSIGNMENT_LABELS = {"poc": "PoC", "reviewer": "Reviewer", "finance": "Financial Manager"}


def _person(u: User) -> dict:
    return {"user_id": u.id, "username": u.username, "email": u.email, "phone": u.phone,
            "name": f"{u.first_name} {u.last_name}".strip() or u.username}


def contacts(db: Session, org: Organisation) -> dict:
    """The workspace's own points of contact (members marked PoC) and the Turacoz team assigned to it."""
    from app.core.tenancy import unfiltered
    from app.models import OrgAssignment
    with unfiltered(db):
        pocs = db.execute(select(OrgMembership).where(
            OrgMembership.organisation_id == org.id, OrgMembership.is_poc == 1, OrgMembership.status == "active")
            .order_by(OrgMembership.role, OrgMembership.created_at)).scalars().all()
        team = db.execute(select(OrgAssignment).where(OrgAssignment.organisation_id == org.id)
                          .order_by(OrgAssignment.role, OrgAssignment.created_at)).scalars().all()
        return {
            "pocs": [{**_person(m.user), "designation": m.designation, "role": m.role} for m in pocs],
            "turacoz": [{**_person(a.user), "id": a.id, "role": a.role, "role_label": ASSIGNMENT_LABELS.get(a.role, a.role),
                         "designation": a.designation, "is_active": bool(a.user.is_active)} for a in team],
        }


def set_poc(m: OrgMembership, is_poc: bool, designation: str) -> None:
    if is_poc and m.status != "active":
        raise ValueError("Only an active member can be a point of contact.")
    m.is_poc = 1 if is_poc else 0
    m.designation = designation.strip()[:150] if is_poc else ""


def system_team(db: Session) -> Organisation | None:
    from app.core.tenancy import unfiltered
    with unfiltered(db):
        return db.execute(select(Organisation).where(Organisation.kind == "system")).scalars().first()


def assign_team_member(db: Session, org: Organisation, user: User, role: str, designation: str,
                       added_by: User | None) -> None:
    """Assign a Turacoz (system) user to a client workspace as its PoC, a Reviewer or its Financial Manager."""
    from app.core.tenancy import unfiltered
    from app.models import OrgAssignment
    if role not in ASSIGNMENT_LABELS:
        raise ValueError("Role must be PoC, Reviewer or Financial Manager.")
    if org.kind in ("system", "individual"):
        raise ValueError("Turacoz team members are assigned to universities and organisations only.")
    team = system_team(db)
    with unfiltered(db):
        m = db.execute(select(OrgMembership).where(OrgMembership.user_id == user.id)).scalar_one_or_none()
        if team is None or m is None or m.organisation_id != team.id:
            raise ValueError(f"{user.username} is not a Turacoz system user.")
        a = db.execute(select(OrgAssignment).where(OrgAssignment.organisation_id == org.id,
                                                   OrgAssignment.user_id == user.id,
                                                   OrgAssignment.role == role)).scalar_one_or_none()
        if a is None:
            a = OrgAssignment(organisation_id=org.id, user_id=user.id, role=role,
                              added_by_id=added_by.id if added_by else None)
            db.add(a)
        a.designation = designation.strip()[:150] or ASSIGNMENT_LABELS[role]
