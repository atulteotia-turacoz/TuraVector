"""Organisation workspaces: who the viewer is, and the automatic data isolation filter.

Every non-superuser belongs to exactly one organisation (`org_membership`). When a request is
authenticated, `set_viewer` stores the viewer on the SQLAlchemy session (`session.info`). A
`do_orm_execute` listener then adds criteria to every top-level ORM SELECT so that rows owned by
users of other organisations are invisible — lists, counts, `db.get()` by id and subqueries alike.

- Superusers (platform superadmins) and sessions without a viewer (login, background work,
  scripts) are not filtered.
- Relationship / column lazy-loads are not filtered, so a visible row can still show e.g. the
  name of whoever approved it.
- Global catalogues (journals, roles, permissions, user types, lookup tables) are not filtered.
- A non-superuser without a membership sees only their own rows.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import event, or_, select
from sqlalchemy.orm import ORMExecuteState, Session, object_session, with_loader_criteria

from app.models import (
    AIConversation, AnnotationActivity, AssignedReviewer, Document, DocumentAnnotation, DocumentHistory,
    DocumentSharing, DocumentVersion, DocumentVersionSharing, EmailLog, Notification, Organisation,
    OrgAssignment, OrgMembership, PlagiarismCheck, ReferenceDocument, ReferenceZip, ResearchProject, User,
    UserJournalSelection,
)

_VIEWER_KEY = "tenancy_viewer"
_BYPASS_KEY = "tenancy_bypass"


@dataclass(frozen=True)
class Viewer:
    user_id: int
    org_id: int | None
    is_superuser: bool
    # every workspace whose data the viewer may see: their own, plus — for a Turacoz (system) user —
    # the client workspaces they are assigned to as PoC or Reviewer
    org_ids: tuple[int, ...] = ()


def membership_of(db: Session, user: User) -> OrgMembership | None:
    """The user's membership (any status), cached on the instance for the request."""
    cached = user.__dict__.get("_org_membership", False)
    if cached is not False:
        return cached
    with unfiltered(db):
        m = db.execute(select(OrgMembership).where(OrgMembership.user_id == user.id)).scalar_one_or_none()
    user.__dict__["_org_membership"] = m
    return m


def active_membership(db: Session, user: User) -> OrgMembership | None:
    m = membership_of(db, user)
    if m is None or m.status != "active" or m.organisation.status != "active":
        return None
    return m


def membership_blocked(db: Session, user: User) -> str | None:
    """Why this user may not sign in because of their workspace, or None if they may."""
    if user.is_superuser:
        return None
    m = membership_of(db, user)
    if m is None:
        return None
    if m.organisation.status == "pending":
        return "Your organisation is awaiting approval. You will be able to sign in once it has been approved."
    if m.organisation.status in ("rejected", "suspended"):
        return f"Your organisation's workspace has been {m.organisation.status}. Please contact support."
    if m.status == "pending":
        return "Your request to join this organisation is awaiting approval by its administrator."
    if m.status != "active":
        return "Your request to join this organisation was not approved."
    return None


def organisation_of(db: Session, user: User) -> Organisation | None:
    m = membership_of(db, user)
    return m.organisation if m else None


def is_org_admin(user: User, db: Session | None = None) -> bool:
    """Active admin of an active university/organisation workspace (individual workspaces have no admin)."""
    db = db or object_session(user)
    if db is None or user.is_superuser:
        return False
    m = active_membership(db, user)
    return bool(m and m.role == "admin" and m.organisation.kind not in ("individual", "system"))


def is_system_user(user: User, db: Session | None = None) -> bool:
    """A member of the Turacoz team workspace."""
    db = db or object_session(user)
    m = membership_of(db, user) if db is not None else None
    return bool(m and m.organisation.kind == "system")


def assigned_org_ids(db: Session, user_id: int) -> list[int]:
    with unfiltered(db):
        return list(db.execute(select(OrgAssignment.organisation_id).where(OrgAssignment.user_id == user_id)
                               .distinct()).scalars())


WORKSPACE_KEY = "superadmin_workspace"  # read by services/superadmin_scope.py


def set_viewer(db: Session, user: User | None, workspace: int | None = None) -> None:
    """Who is looking. A superuser normally sees every workspace; with `workspace` (the superadmin's
    top-bar choice) they see that one workspace, exactly like its members' data is filtered."""
    db.info.pop(WORKSPACE_KEY, None)
    if user is None:
        db.info.pop(_VIEWER_KEY, None)
        return
    if user.is_superuser and workspace:
        db.info[WORKSPACE_KEY] = workspace
        db.info[_VIEWER_KEY] = Viewer(user.id, workspace, False, (workspace,))
        return
    m = membership_of(db, user)
    if m is None:
        db.info[_VIEWER_KEY] = Viewer(user.id, None, bool(user.is_superuser))
        return
    org_ids = (m.organisation_id,)
    if m.organisation.kind == "system":
        org_ids += tuple(i for i in assigned_org_ids(db, user.id) if i != m.organisation_id)
    db.info[_VIEWER_KEY] = Viewer(user.id, m.organisation_id, bool(user.is_superuser), org_ids)


def get_viewer(db: Session) -> Viewer | None:
    return db.info.get(_VIEWER_KEY)


class unfiltered:
    """`with unfiltered(db): ...` — run queries without the organisation filter."""

    def __init__(self, db: Session):
        self.db = db

    def __enter__(self):
        self.db.info[_BYPASS_KEY] = self.db.info.get(_BYPASS_KEY, 0) + 1
        return self.db

    def __exit__(self, *exc):
        self.db.info[_BYPASS_KEY] -= 1


def org_admin_ids():
    """Subquery of the ids of all workspace admins (scoped to the viewer's workspace by the filter's callers)."""
    return select(OrgMembership.user_id).where(OrgMembership.role == "admin", OrgMembership.status == "active")


# The workspace that also holds what platform superusers created themselves (documents, references,
# ZIPs…): all data that existed before workspaces were introduced lives there.
HOME_WORKSPACE_SLUG = "smbt"
_home_id: dict[str, int | None] = {}


def home_workspace_id(db: Session) -> int | None:
    if "id" not in _home_id:
        with unfiltered(db):
            _home_id["id"] = db.execute(
                select(Organisation.id).where(Organisation.slug == HOME_WORKSPACE_SLUG)).scalar_one_or_none()
    return _home_id["id"]


def owner_condition(column, viewer: Viewer, home_id: int | None):
    """`column` (a row's owner) is a member of the viewer's workspace — or, in the home workspace, a
    platform superuser."""
    cond = column.in_(org_user_ids(viewer))
    if home_id is not None and home_id in viewer.org_ids:
        cond = or_(cond, column.in_(select(User.id).where(User.is_superuser == 1)))
    return cond


def org_user_ids(viewer: Viewer):
    """Subquery of the user ids the viewer may see data of: the members of their workspace(s) and the
    Turacoz users assigned to them."""
    if not viewer.org_ids:
        return select(User.id).where(User.id == viewer.user_id)
    members = select(OrgMembership.user_id).where(OrgMembership.organisation_id.in_(viewer.org_ids))
    assigned = select(OrgAssignment.user_id).where(OrgAssignment.organisation_id.in_(viewer.org_ids))
    return members.union(assigned)


# (model, owner column name) — rows are visible when the owner is in the viewer's organisation.
_SCOPED: tuple[tuple[type, str], ...] = (
    (Document, "user_id"),
    (DocumentVersion, "user_id"),
    (ReferenceDocument, "user_id"),
    (ReferenceZip, "user_id"),
    (ResearchProject, "owner_id"),
    (DocumentSharing, "user_id"),
    (DocumentVersionSharing, "user_id"),
    (DocumentHistory, "user_id"),
    (DocumentAnnotation, "user_id"),
    (AnnotationActivity, "user_id"),
    (UserJournalSelection, "user_id"),
    (EmailLog, "recipient_user_id"),
    (PlagiarismCheck, "user_id"),
    (AIConversation, "user_id"),
    (Notification, "receiver"),
)


def _criteria_options(viewer: Viewer, home_id: int | None) -> list:
    # Plain expressions (not lambdas): the values become bound parameters of the statement's cache
    # key, so one viewer's criteria can never be reused for another.
    ids = org_user_ids(viewer)
    options = [
        # same-organisation users, plus platform superadmins so their names still resolve
        with_loader_criteria(User, or_(User.id.in_(ids), User.is_superuser == 1)),
        with_loader_criteria(Organisation, Organisation.id.in_(viewer.org_ids or (-1,))),
        # a review assignment belongs to the workspace of the document under review, whoever reviews it
        with_loader_criteria(AssignedReviewer, AssignedReviewer.document_version_id.in_(
            select(DocumentVersion.id).where(owner_condition(DocumentVersion.user_id, viewer, home_id)))),
    ]
    for model, column in _SCOPED:
        options.append(with_loader_criteria(model, owner_condition(getattr(model, column), viewer, home_id)))
    return options


@event.listens_for(Session, "do_orm_execute")
def _apply_org_filter(state: ORMExecuteState) -> None:
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    session = state.session
    if session.info.get(_BYPASS_KEY):
        return
    viewer: Viewer | None = session.info.get(_VIEWER_KEY)
    if viewer is None or viewer.is_superuser:
        return
    state.statement = state.statement.options(*_criteria_options(viewer, home_workspace_id(session)))


# ---------------------------------------------------------------- automatic membership
# A user created while someone is signed in (manager "create user", bulk import, …) joins the
# creator's workspace. A superadmin has no workspace, so they choose one first with
# `place_new_users_in(db, org_id)`. Sign-up adds its memberships itself. The test-suite sets the
# same key once so that users made by fixtures join SMBT.
_NEW_USERS_KEY = "tenancy_new_users"
_TARGET_ORG_KEY = "tenancy_default_org"


def place_new_users_in(db: Session, org_id: int) -> None:
    db.info[_TARGET_ORG_KEY] = org_id


@event.listens_for(Session, "before_flush")
def _collect_new_users(session: Session, flush_context, instances) -> None:
    new = [o for o in session.new if isinstance(o, User) and not o.is_superuser]
    if new:
        session.info.setdefault(_NEW_USERS_KEY, []).extend(new)


@event.listens_for(Session, "after_flush_postexec")
def _auto_membership(session: Session, flush_context) -> None:
    new = session.info.pop(_NEW_USERS_KEY, None)
    if not new:
        return
    viewer: Viewer | None = session.info.get(_VIEWER_KEY)
    org_id = (viewer.org_id if viewer else None) or session.info.get(_TARGET_ORG_KEY)
    if not org_id:
        return
    with unfiltered(session):
        taken = set(session.execute(
            select(OrgMembership.user_id).where(OrgMembership.user_id.in_([u.id for u in new]))).scalars())
    for user in new:
        if user.id not in taken:
            session.add(OrgMembership(organisation_id=org_id, user_id=user.id, role="member", status="active",
                                      added_by_id=viewer.user_id if viewer else None))
            user.__dict__.pop("_org_membership", None)



def platform_wide_scope(db: Session):
    """Generator body for a FastAPI dependency: run the whole request without the workspace filter.
    Used by platform pages (the superadmin's Organisations) whatever workspace the top bar shows."""
    db.info[_BYPASS_KEY] = db.info.get(_BYPASS_KEY, 0) + 1
    try:
        yield
    finally:
        db.info[_BYPASS_KEY] -= 1
