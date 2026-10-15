"""Workspace sign-up flows and workspace notifications.

- Individual: a personal workspace (active at once) with the user as its only member.
- University / organisation: a pending workspace with the signing-up user as its admin; a
  superadmin approves it before anyone can sign in.
- Join with code: the user asks to join an existing workspace; its admin approves the request.
"""
import logging

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import send_plain_email
from app.core.files import save_upload
from app.core.tenancy import unfiltered
from app.models import Organisation, OrgMembership, User, utcnow
from app.services.org_common import add_membership, new_join_code, unique_slug
from app.services.viewer_common import frontend_url

log = logging.getLogger("turadome.org")

# Self-chosen account types at sign-up. Privileged types (teacher, reviewer, manager) are given by
# a workspace admin or superadmin — never self-selected.
SIGNUP_USER_TYPES = (("student", "Student"), ("researcher", "Researcher"))
ORG_KINDS_FOR_SIGNUP = (("university", "University"), ("organisation", "Organisation"))
LOGO_DIR = "organisation_logos"
MAX_LOGO_BYTES = 2 * 1024 * 1024


class SignupError(ValueError):
    pass


def validate_logo(upload: UploadFile | None) -> None:
    if upload is None or not upload.filename:
        return
    data = upload.file.read(MAX_LOGO_BYTES + 1)
    upload.file.seek(0)
    if len(data) > MAX_LOGO_BYTES:
        raise SignupError("The logo must be 2 MB or smaller.")
    try:
        from PIL import Image
        import io
        Image.open(io.BytesIO(data)).verify()
    except Exception:  # noqa: BLE001
        raise SignupError("Upload the logo as a PNG or JPG image.") from None


def save_logo(upload: UploadFile | None) -> str:
    if upload is None or not upload.filename:
        return ""
    return save_upload(upload, LOGO_DIR)


def create_individual_workspace(db: Session, user: User) -> Organisation:
    name = f"{user.first_name} {user.last_name}".strip() or user.username
    org = Organisation(name=name, slug=unique_slug(db, f"{name}-{user.username}"), kind="individual", website="",
                       logo="", status="active", join_code=None, created_by_id=user.id, approved_at=utcnow())
    db.add(org)
    db.flush()
    add_membership(db, org, user, role="member", status="active")
    return org


def create_pending_organisation(db: Session, admin: User, *, name: str, kind: str, website: str,
                                logo: UploadFile | None) -> Organisation:
    org = Organisation(name=name, slug=unique_slug(db, name), kind=kind, website=website, logo=save_logo(logo),
                       status="pending", join_code=new_join_code(db), created_by_id=admin.id)
    db.add(org)
    db.flush()
    add_membership(db, org, admin, role="admin", status="active")
    return org


def find_joinable(db: Session, code: str) -> Organisation:
    code = (code or "").strip().upper()
    with unfiltered(db):
        org = db.execute(select(Organisation).where(Organisation.join_code == code)).scalar_one_or_none()
    if org is None or org.kind == "individual":
        raise SignupError("That join code is not valid. Please check it with your university or organisation.")
    if org.status != "active":
        raise SignupError("This organisation is not accepting new members yet.")
    return org


def org_admins(db: Session, org: Organisation) -> list[User]:
    with unfiltered(db):
        return list(db.execute(
            select(User).join(OrgMembership, OrgMembership.user_id == User.id).where(
                OrgMembership.organisation_id == org.id, OrgMembership.role == "admin",
                OrgMembership.status == "active", User.is_active == 1)
        ).scalars())


def superusers(db: Session) -> list[User]:
    with unfiltered(db):
        return list(db.execute(select(User).where(User.is_superuser == 1, User.is_active == 1)).scalars())


def _mail(db: Session, users: list[User], subject: str, message: str) -> None:
    to = [u.email for u in users if u.email]
    if to:
        send_plain_email(db, subject, message, to)


def notify_new_organisation(db: Session, org: Organisation, admin: User) -> None:
    _mail(db, superusers(db), f"New {org.kind} awaiting approval: {org.name}",
          f"{admin.first_name} {admin.last_name} ({admin.email}) registered the {org.kind} \"{org.name}\""
          f"{f' ({org.website})' if org.website else ''}.\n\n"
          "Review it in the superadmin console under Organisations.")


def notify_join_request(db: Session, org: Organisation, user: User) -> None:
    _mail(db, org_admins(db, org), f"New request to join {org.name}",
          f"{user.first_name} {user.last_name} ({user.email}) asked to join {org.name} on TuraVector.\n\n"
          f"Approve or reject the request: {frontend_url('/content-lab-management/organisation/members/')}")


def notify_organisation_decision(db: Session, org: Organisation) -> None:
    if org.status == "active":
        subject, body = f"{org.name} is now active on TuraVector", (
            f"Your {org.kind} workspace \"{org.name}\" has been approved. You can sign in now: {frontend_url('/login/')}\n\n"
            f"Members can join with the code {org.join_code}, or you can add them from the Organisation page.")
    else:
        subject, body = f"Update on {org.name}", f"Your {org.kind} workspace \"{org.name}\" has been {org.status}."
    _mail(db, org_admins(db, org), subject, body)


def notify_membership_decision(db: Session, membership: OrgMembership) -> None:
    user, org = membership.user, membership.organisation
    if membership.status == "active":
        body = f"Your request to join {org.name} has been approved. You can sign in now: {frontend_url('/login/')}"
    else:
        body = f"Your request to join {org.name} was not approved."
    _mail(db, [user], f"Your request to join {org.name}", body)
