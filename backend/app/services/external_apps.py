"""The tools catalogue: TuraVector dashboards and other Tura applications on the dashboard-selection page.

Tools live in the `platform_tool` table and are managed by the superadmin (Tools & Services), so new
applications can be added without code changes. The built-in ones are created on first use:
Content Review, Journal Selector, Research Assistant, Tura LMS, TuraGrammar, TuraStatistics and TuraSLR.

Who sees a tool's card:
- superusers see every card; managers always see Content Review; university / organisation admins see
  every TuraVector dashboard (the original rules);
- otherwise a per-user setting decides when there is one (UserPermission is_granted=1 "Visible",
  is_granted=0 "Hidden" — an explicit deny, so neither a role nor a plan can reopen the card);
- otherwise the tool is visible when it is free or the user's workspace has a current subscription
  that includes it (app/services/subscriptions.py).

Each tool has one Permission row (apps: dashboard="external_apps", module=<key>, action="view";
dashboards: the existing cl_/od_dashboard_access rows).
"""
import dataclasses
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.config import settings
from app.core.permissions import PermissionChecker, is_manager_like
from app.core.tenancy import is_org_admin
from app.models import Permission, PlatformTool, User

DASHBOARD = "external_apps"


@dataclass(frozen=True)
class ExternalApp:
    key: str
    name: str
    description: str
    features: tuple[str, ...]
    url_setting: str = ""  # built-in apps: the setting holding the default URL (and the prefix of their SSO settings)
    link: str = ""         # the link set in the admin (Tools & Services); for built-in apps it replaces the setting

    @property
    def url(self) -> str:
        return self.link or (getattr(settings, self.url_setting) if self.url_setting else "")


# Built-in applications (single sign-on is wired up for these in external_apps_sso.py).
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
    ExternalApp(
        key="ext_turastatistics", name="TuraStatistics",
        description="Run statistical analyses on research data and get results ready to report.",
        features=("Descriptive & inferential statistics", "Charts and tables", "AI-assisted interpretation"),
        url_setting="TURASTATISTICS_URL",
    ),
    ExternalApp(
        key="ext_turaslr", name="TuraSLR",
        description="AI-assisted systematic literature reviews, from protocol to PRISMA-ready report.",
        features=("Search strategy & screening", "Data extraction & risk of bias", "Meta-analysis & reports"),
        url_setting="TURASLR_URL",
    ),
)
APP_BY_KEY = {a.key: a for a in APPS}

# Built-in TuraVector dashboards: key -> (Permission.dashboard, Permission.module)
DASHBOARD_PERMISSIONS = {
    "content_lab": ("content_lab", "cl_dashboard_access"),
    "other_documents": ("other_documents", "od_dashboard_access"),
}

BUILTIN_TOOLS: tuple[dict, ...] = (
    {"key": "content_lab", "name": "Content Review", "kind": "dashboard", "icon": "flask",
     "description": "Access all existing TuraVector features for comprehensive document management and collaboration.",
     "features": ["Document Upload & Version Control", "PDF Annotation & Review", "Collaborative Editing",
                  "Reference Library Management", "User Management & Permissions", "Email Notifications & Workflow"]},
    {"key": "other_documents", "name": "Journal Selector", "kind": "dashboard", "icon": "file-text",
     "description": "Access specialized document management features for different document types and workflows.",
     "features": ["Specialized Document Types", "Custom Workflows", "Advanced Processing", "Extended Integrations",
                  "Custom Templates", "Enhanced Analytics"]},
    *({"key": a.key, "name": a.name, "kind": "app", "description": a.description, "features": list(a.features),
       "icon": {"ext_research_assistant": "brain", "ext_lms": "graduation-cap", "ext_turagrammar": "spell-check",
                "ext_turastatistics": "bar-chart", "ext_turaslr": "book-open"}[a.key]}
      for a in APPS),
)


def ensure_tools(db: Session) -> list[PlatformTool]:
    """Every tool, in display order; the built-in ones are added if missing (idempotent)."""
    cached = db.info.get("platform_tools")
    if cached is not None:
        return cached
    tools = list(db.execute(select(PlatformTool).order_by(PlatformTool.sort_order, PlatformTool.name)).scalars())
    have = {t.key for t in tools}
    added = False
    for order, spec in enumerate(BUILTIN_TOOLS):
        if spec["key"] not in have:
            t = PlatformTool(**spec, url="", is_builtin=1, is_free=0, is_active=1, sort_order=order * 10)
            db.add(t)
            tools.append(t)
            added = True
    if added:
        db.flush()
        tools.sort(key=lambda t: (t.sort_order, t.name))
    db.info["platform_tools"] = tools
    return tools


def forget_tools(db: Session) -> None:
    """Call after changing the catalogue so the next lookup reloads it."""
    db.info.pop("platform_tools", None)


def tool_by_key(db: Session, key: str) -> PlatformTool | None:
    return next((t for t in ensure_tools(db) if t.key == key), None)


def app_of(tool: PlatformTool) -> ExternalApp:
    """The launchable application behind an app tool (built-in apps keep their URL setting and SSO)."""
    features = tuple(tool.features or ())
    if tool.key in APP_BY_KEY:
        return dataclasses.replace(APP_BY_KEY[tool.key], name=tool.name, description=tool.description, features=features,
                                   link=tool.url or "")
    return ExternalApp(key=tool.key, name=tool.name, description=tool.description, features=features, link=tool.url)


def ensure_permissions(db: Session) -> dict[str, Permission]:
    """The Permission row of every app tool, created if missing (idempotent)."""
    existing = {p.module: p for p in db.execute(
        select(Permission).where(Permission.dashboard == DASHBOARD, Permission.action == "view")
    ).scalars()}
    created = False
    for tool in ensure_tools(db):
        if tool.kind == "app" and tool.key not in existing:
            perm = Permission(name=f"{tool.name} - Access", dashboard=DASHBOARD, module=tool.key, action="view",
                              description=f"Show the {tool.name} card on the dashboard-selection page", is_active=1)
            db.add(perm)
            existing[tool.key] = perm
            created = True
    if created:
        db.commit()
    return existing


def visible_apps(db: Session, user: User) -> list[dict]:
    ensure_permissions(db)
    checker = PermissionChecker(db, user)
    out = []
    for tool in ensure_tools(db):
        if tool.is_active and tool.kind == "app" and card_visible(checker, user, card_of(tool)):
            app = app_of(tool)
            out.append({"key": tool.key, "name": app.name, "description": app.description, "features": list(app.features),
                        "url": app.url, "icon": tool.icon})
    return out


def user_setting_visible(checker: PermissionChecker, user: User, dashboard: str, module: str) -> bool:
    """Per-user only: superuser, or an explicit Visible (UserPermission is_granted=1). Roles are ignored."""
    if user.is_superuser:
        return True
    return checker.direct.get((dashboard, module, "view")) is True


# ---------------------------------------------------------------------------------------------
# All cards on the dashboard-selection page (TuraVector dashboards + other applications),
# for the superadmin's per-user "card access" controls.
@dataclass(frozen=True)
class Card:
    key: str
    name: str
    kind: str          # "dashboard" | "app"
    dashboard: str     # Permission.dashboard
    module: str        # Permission.module


def card_of(tool: PlatformTool) -> Card:
    dashboard, module = DASHBOARD_PERMISSIONS.get(tool.key, (DASHBOARD, tool.key))
    return Card(tool.key, tool.name, tool.kind, dashboard, module)


def cards(db: Session) -> list[Card]:
    """Cards of the active tools, in display order."""
    return [card_of(t) for t in ensure_tools(db) if t.is_active]


def card_by_key(db: Session, key: str) -> Card | None:
    return next((c for c in cards(db) if c.key == key), None)


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
    """Whether the card shows on dashboard-selection (see the module docstring for the order of the rules)."""
    if card.key == "content_lab" and is_manager_like(user):
        return True
    if card.kind == "dashboard" and is_org_admin(user):
        return True  # a university/organisation admin manages every TuraVector dashboard of the workspace
    db = object_session(user)
    if card.key == "content_lab":
        from app.services import billing
        if db is not None and billing.is_approver(db, user):
            return True  # a Turacoz Financial Manager works in Content Review (Finance Dashboard, Invoices)
    if user.is_superuser:
        return True
    setting = checker.direct.get((card.dashboard, card.module, "view"))
    if setting is not None:
        return setting
    if db is None:
        return False
    from app.services.subscriptions import has_tool
    return has_tool(db, user, card.key)


# ---------------------------------------------------------------------------------------------
# New users start with Content Review visible (cards are per user, so a role can't do it).
from sqlalchemy import event, insert as _insert, select as _select  # noqa: E402

from app.models import UserPermission, utcnow  # noqa: E402


@event.listens_for(User, "after_insert")
def _new_user_sees_content_lab(mapper, connection, target) -> None:
    perm_id = connection.execute(_select(Permission.id).where(
        Permission.dashboard == "content_lab", Permission.module == "cl_dashboard_access", Permission.action == "view")).scalar()
    if perm_id is None:
        return
    connection.execute(_insert(UserPermission.__table__).values(
        user_id=target.id, permission_id=perm_id, is_granted=1, reason="Content Review visible for new users",
        granted_at=utcnow(), granted_by_id=None, expires_at=None))
