"""Other Tura applications offered on the dashboard-selection page.

Card visibility is set per user, never by role: each card has one Permission row
(apps: dashboard="external_apps", module=<key>, action="view"; dashboards: the existing
cl_/od_dashboard_access rows) and a user sees the card only with a UserPermission
is_granted=1 ("Visible"). is_granted=0 is an explicit "Hidden" (so a role grant can't
reopen the dashboard through the normal permission check). Superusers see every card;
managers always see Content Lab (the original dashboard-selection rule).
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PermissionChecker, is_manager_like
from app.core.tenancy import is_org_admin
from app.models import Permission, User

DASHBOARD = "external_apps"


@dataclass(frozen=True)
class ExternalApp:
    key: str
    name: str
    description: str
    features: tuple[str, ...]
    url_setting: str

    @property
    def url(self) -> str:
        return getattr(settings, self.url_setting)


APPS: tuple[ExternalApp, ...] = (
    ExternalApp(
        key="ext_research_assistant", name="Tura Research Assistant",
        description="AI-assisted research support for literature, writing and analysis.",
        features=("Literature search & summaries", "Research writing assistance", "Reference support"),
        url_setting="TURA_RESEARCH_ASSISTANT_URL",
    ),
    ExternalApp(
        key="ext_lms", name="Tura LMS",
        description="Courses, training material and learning progress in one place.",
        features=("Courses & modules", "Training material", "Progress tracking"),
        url_setting="TURA_LMS_URL",
    ),
    ExternalApp(
        key="ext_turagrammar", name="TuraGrammar",
        description="Check grammar, style and clarity of scientific writing.",
        features=("Grammar & spelling checks", "Style suggestions", "Scientific writing focus"),
        url_setting="TURAGRAMMAR_URL",
    ),
)
APP_BY_KEY = {a.key: a for a in APPS}


def ensure_permissions(db: Session) -> dict[str, Permission]:
    """Create the three Permission rows if they don't exist yet (idempotent)."""
    existing = {p.module: p for p in db.execute(
        select(Permission).where(Permission.dashboard == DASHBOARD, Permission.action == "view")
    ).scalars()}
    created = False
    for app in APPS:
        if app.key not in existing:
            perm = Permission(name=f"{app.name} - Access", dashboard=DASHBOARD, module=app.key, action="view",
                              description=f"Show the {app.name} card on the dashboard-selection page", is_active=1)
            db.add(perm)
            existing[app.key] = perm
            created = True
    if created:
        db.commit()
    return existing


def visible_apps(db: Session, user: User) -> list[dict]:
    ensure_permissions(db)
    checker = PermissionChecker(db, user)
    return [{"key": a.key, "name": a.name, "description": a.description, "features": list(a.features), "url": a.url}
            for a in APPS if user_setting_visible(checker, user, DASHBOARD, a.key)]


def user_setting_visible(checker: PermissionChecker, user: User, dashboard: str, module: str) -> bool:
    """Per-user only: superuser, or an explicit Visible (UserPermission is_granted=1). Roles are ignored."""
    if user.is_superuser:
        return True
    return checker.direct.get((dashboard, module, "view")) is True


# ---------------------------------------------------------------------------------------------
# All cards on the dashboard-selection page (TuraVector dashboards + other Tura applications),
# for the superadmin's per-user / per-role "card access" controls.
@dataclass(frozen=True)
class Card:
    key: str
    name: str
    kind: str          # "dashboard" | "app"
    dashboard: str     # Permission.dashboard
    module: str        # Permission.module


CARDS: tuple[Card, ...] = (
    Card("content_lab", "Content Lab Management", "dashboard", "content_lab", "cl_dashboard_access"),
    Card("other_documents", "Journal Selector", "dashboard", "other_documents", "od_dashboard_access"),
    *(Card(a.key, a.name, "app", DASHBOARD, a.key) for a in APPS),
)
CARD_BY_KEY = {c.key: c for c in CARDS}


def card_permission(db: Session, card: Card) -> Permission:
    """Permission row behind a card (dashboard-access rows exist already; app rows are created on demand)."""
    if card.kind == "app":
        return ensure_permissions(db)[card.key]
    perm = db.execute(select(Permission).where(
        Permission.dashboard == card.dashboard, Permission.module == card.module, Permission.action == "view")).scalar_one_or_none()
    if perm is None:  # created by setup_permissions in Django; recreate if missing
        perm = Permission(name=f"{card.name} - Dashboard Access", dashboard=card.dashboard, module=card.module, action="view",
                          description=f"Access to the {card.name} dashboard", is_active=1)
        db.add(perm)
        db.commit()
    return perm


def card_visible(checker: PermissionChecker, user: User, card: Card) -> bool:
    """Whether the card shows on dashboard-selection (per-user setting; managers always get Content Lab)."""
    if card.key == "content_lab" and is_manager_like(user):
        return True
    if card.kind == "dashboard" and is_org_admin(user):
        return True  # a university/organisation admin manages every TuraVector dashboard of the workspace
    if card.key == "content_lab":
        from sqlalchemy.orm import object_session
        from app.services import billing
        db = object_session(user)
        if db is not None and billing.is_approver(db, user):
            return True  # a Turacoz Financial Manager works in Content Lab (Finance Dashboard, Invoices)
    return user_setting_visible(checker, user, card.dashboard, card.module)


# ---------------------------------------------------------------------------------------------
# New users start with Content Lab Management visible (cards are per user, so a role can't do it).
from sqlalchemy import event, insert as _insert, select as _select  # noqa: E402

from app.models import UserPermission, utcnow  # noqa: E402


@event.listens_for(User, "after_insert")
def _new_user_sees_content_lab(mapper, connection, target) -> None:
    perm_id = connection.execute(_select(Permission.id).where(
        Permission.dashboard == "content_lab", Permission.module == "cl_dashboard_access", Permission.action == "view")).scalar()
    if perm_id is None:
        return
    connection.execute(_insert(UserPermission.__table__).values(
        user_id=target.id, permission_id=perm_id, is_granted=1, reason="Content Lab Management visible for new users",
        granted_at=utcnow(), granted_by_id=None, expires_at=None))
