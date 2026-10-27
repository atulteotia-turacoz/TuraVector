"""RBAC — a direct port of the permission methods on the Django User model
(authentication/models.py). Same lookup order, same defaults:

1. superusers have every permission;
2. an active direct UserPermission decides (grant or explicit deny);
3. otherwise any active, unexpired role that holds the permission grants it;
4. otherwise deny.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import is_org_admin
from app.models import Permission, RolePermission, Role, User, UserPermission, UserRole, utcnow

# University/organisation admins hold every TuraVector permission inside their own workspace (the
# tenancy filter keeps them there) — except the platform-wide settings that only superusers manage.
_ORG_ADMIN_DASHBOARDS = ("content_lab", "other_documents")
_PLATFORM_MODULES = ("cl_roles", "cl_permissions", "cl_email", "cl_email_settings")
# The reviewer dashboard is a reviewer's own work list, not an admin tool: an admin gets it only
# through a Reviewer role like anybody else.
_NOT_FOR_ORG_ADMINS = ("cl_reviewer_dashboard",)


def org_admin_grants(user: User, dashboard: str, module: str) -> bool:
    return (dashboard in _ORG_ADMIN_DASHBOARDS and module not in _PLATFORM_MODULES
            and module not in _NOT_FOR_ORG_ADMINS and is_org_admin(user))


def _not_expired(expires_at) -> bool:
    return expires_at is None or utcnow() < expires_at


def has_module_permission(db: Session, user: User, dashboard: str, module: str, action: str) -> bool:
    if user.is_superuser:
        return True
    if org_admin_grants(user, dashboard, module):
        return True

    direct = db.execute(
        select(UserPermission)
        .join(Permission, UserPermission.permission_id == Permission.id)
        .where(
            UserPermission.user_id == user.id,
            Permission.dashboard == dashboard,
            Permission.module == module,
            Permission.action == action,
            Permission.is_active == 1,
        )
    ).scalars().all()
    for perm in direct:
        if _not_expired(perm.expires_at):
            return bool(perm.is_granted)

    user_roles = db.execute(
        select(UserRole).join(Role, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, Role.is_active == 1)
    ).scalars().all()
    for ur in user_roles:
        if not _not_expired(ur.expires_at):
            continue
        exists = db.execute(
            select(RolePermission.id)
            .join(Permission, RolePermission.permission_id == Permission.id)
            .where(
                RolePermission.role_id == ur.role_id,
                Permission.dashboard == dashboard,
                Permission.module == module,
                Permission.action == action,
                Permission.is_active == 1,
            ).limit(1)
        ).first()
        if exists:
            return True
    return False


class PermissionChecker:
    """Loads all of a user's permission data once, then answers checks in memory.

    Use this when many checks are needed in one request (e.g. building the
    capability map for the UI); results are identical to `has_module_permission`.
    """

    def __init__(self, db: Session, user: User):
        self.user = user
        self.superuser = bool(user.is_superuser)
        self.direct: dict[tuple[str, str, str], bool] = {}
        self.role_perms: set[tuple[str, str, str]] = set()
        self.org_admin = not self.superuser and is_org_admin(user, db)
        if self.superuser:
            return
        rows = db.execute(
            select(UserPermission, Permission)
            .join(Permission, UserPermission.permission_id == Permission.id)
            .where(UserPermission.user_id == user.id, Permission.is_active == 1)
        ).all()
        for up, p in rows:
            if _not_expired(up.expires_at):
                self.direct.setdefault((p.dashboard, p.module, p.action), bool(up.is_granted))
        role_rows = db.execute(
            select(UserRole.expires_at, Permission.dashboard, Permission.module, Permission.action)
            .join(Role, UserRole.role_id == Role.id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, RolePermission.permission_id == Permission.id)
            .where(UserRole.user_id == user.id, Role.is_active == 1, Permission.is_active == 1)
        ).all()
        for expires_at, d, m, a in role_rows:
            if _not_expired(expires_at):
                self.role_perms.add((d, m, a))

    def has(self, dashboard: str, module: str, action: str) -> bool:
        if self.superuser:
            return True
        if self.org_admin and org_admin_grants(self.user, dashboard, module):
            return True
        key = (dashboard, module, action)
        if key in self.direct:
            return self.direct[key]
        return key in self.role_perms


# name -> (dashboard, module, action); mirrors every can_* helper on the Django User model
CAPABILITIES: dict[str, tuple[str, str, str]] = {
    "can_access_dashboard": ("content_lab", "cl_dashboard", "view"),
    "can_access_manager_dashboard": ("content_lab", "cl_manager_dashboard", "view"),
    "can_access_reviewer_dashboard": ("content_lab", "cl_reviewer_dashboard", "view"),
    "can_upload": ("content_lab", "cl_upload", "view"),
    "can_create_upload": ("content_lab", "cl_upload", "create"),
    "can_access_library": ("content_lab", "cl_library", "view"),
    "can_create_library": ("content_lab", "cl_library", "create"),
    "can_edit_library": ("content_lab", "cl_library", "edit"),
    "can_delete_library": ("content_lab", "cl_library", "delete"),
    "can_manage_users": ("content_lab", "cl_users", "view"),
    "can_create_users": ("content_lab", "cl_users", "create"),
    "can_edit_users": ("content_lab", "cl_users", "edit"),
    "can_assign_roles": ("content_lab", "cl_users", "assign_roles"),
    "can_manage_roles": ("content_lab", "cl_roles", "view"),
    "can_create_roles": ("content_lab", "cl_roles", "create"),
    "can_edit_roles": ("content_lab", "cl_roles", "edit"),
    "can_assign_permissions": ("content_lab", "cl_roles", "assign_permissions"),
    "can_view_reports": ("content_lab", "cl_reports", "view"),
    "can_create_reports": ("content_lab", "cl_reports", "create"),
    "can_manage_email_settings": ("content_lab", "cl_email", "view"),
    "can_create_email_settings": ("content_lab", "cl_email", "create"),
    "can_edit_email_settings": ("content_lab", "cl_email", "edit"),
    "can_view_mail_logs": ("content_lab", "cl_mail_logs", "view"),
    "can_retry_emails": ("content_lab", "cl_mail_logs", "retry"),
    "can_view_documents": ("content_lab", "cl_documents", "view"),
    "can_view_all_documents": ("content_lab", "cl_documents", "view_all"),
    "can_edit_documents": ("content_lab", "cl_documents", "edit"),
    "can_edit_all_documents": ("content_lab", "cl_documents", "edit_all"),
    "can_delete_documents": ("content_lab", "cl_documents", "delete"),
    "can_delete_all_documents": ("content_lab", "cl_documents", "delete_all"),
    "can_delete_document_versions": ("content_lab", "cl_documents", "delete_version"),
    "can_delete_all_document_versions": ("content_lab", "cl_documents", "delete_version_all"),
    "can_view_document_history": ("content_lab", "cl_documents", "view_history"),
    "can_view_all_document_history": ("content_lab", "cl_documents", "view_all_history"),
    "can_create_document_versions": ("content_lab", "cl_documents", "create_version"),
    "can_upload_documents": ("content_lab", "cl_documents", "upload"),
    "can_manage_library": ("content_lab", "cl_library", "manage"),
    "can_manage_reference_zip": ("content_lab", "cl_library", "manage"),
    "can_review_documents": ("content_lab", "cl_review", "review"),
    "can_reject_documents": ("content_lab", "cl_review", "reject"),
    # NB: Django defines can_assign_reviewers twice; the later (cl_review/assign) wins.
    "can_assign_reviewers": ("content_lab", "cl_review", "assign"),
    "can_access_other_documents": ("other_documents", "od_dashboard", "view"),
    "can_search_journals": ("other_documents", "od_journals", "search"),
    "can_access_reviews": ("content_lab", "cl_review", "view"),
    "can_view_completed": ("content_lab", "cl_completed", "view"),
    "can_access_archive": ("content_lab", "cl_archive", "view"),
    "can_access_references": ("content_lab", "cl_library", "view"),
    "can_access_document_references": ("content_lab", "cl_library", "manage"),
    # template-tag filters (authentication/templatetags/permission_tags.py)
    "tag_can_manage_users": ("content_lab", "cl_manage_users", "view"),
    "tag_can_manage_email_settings": ("content_lab", "cl_email_settings", "view"),
    "tag_can_manage_permissions": ("content_lab", "cl_permissions", "view"),
}


def user_capabilities(db: Session, user: User) -> dict[str, bool]:
    checker = PermissionChecker(db, user)
    caps = {name: checker.has(*spec) for name, spec in CAPABILITIES.items()}
    # These two always pass for superusers in Django, then fall back to the permission
    for name, (tool, dashboard, module) in _DASHBOARD_CAPS.items():
        caps[name] = checker.has(dashboard, module, "view") or (
            (dashboard, module, "view") not in checker.direct and _has_tool(db, user, tool))
    return caps


# The two dashboard-access capabilities are also opened by a plan (or a free tool) that includes the
# dashboard — unless the user has an explicit per-user setting, which always decides.
_DASHBOARD_CAPS = {
    "can_access_content_lab_dashboard": ("content_lab", "content_lab", "cl_dashboard_access"),
    "can_access_other_documents_dashboard": ("other_documents", "other_documents", "od_dashboard_access"),
}


def _has_tool(db: Session, user: User, tool: str) -> bool:
    from app.services.subscriptions import has_tool
    return has_tool(db, user, tool)


def _has_direct_setting(db: Session, user: User, dashboard: str, module: str) -> bool:
    return db.execute(
        select(UserPermission.id).join(Permission, UserPermission.permission_id == Permission.id)
        .where(UserPermission.user_id == user.id, Permission.dashboard == dashboard, Permission.module == module,
               Permission.action == "view", Permission.is_active == 1).limit(1)
    ).first() is not None


def can(db: Session, user: User, capability: str) -> bool:
    """Check one named capability, e.g. can(db, user, "can_view_all_documents")."""
    if capability in _DASHBOARD_CAPS:
        tool, dashboard, module = _DASHBOARD_CAPS[capability]
        return has_module_permission(db, user, dashboard, module, "view") or (
            not _has_direct_setting(db, user, dashboard, module) and _has_tool(db, user, tool))
    return has_module_permission(db, user, *CAPABILITIES[capability])


def get_all_roles(db: Session, user: User) -> list[Role]:
    rows = db.execute(
        select(UserRole, Role).join(Role, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, Role.is_active == 1)
    ).all()
    return [role for ur, role in rows if _not_expired(ur.expires_at)]


def has_role(db: Session, user: User, role_name: str) -> bool:
    return db.execute(
        select(UserRole.id).join(Role, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, Role.name == role_name, Role.is_active == 1).limit(1)
    ).first() is not None


def get_all_permissions(db: Session, user: User) -> list[Permission]:
    perms: dict[int, Permission] = {}
    for role in get_all_roles(db, user):
        for p in db.execute(
            select(Permission).join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id, Permission.is_active == 1)
        ).scalars():
            perms[p.id] = p
    for up, p in db.execute(
        select(UserPermission, Permission).join(Permission, UserPermission.permission_id == Permission.id)
        .where(UserPermission.user_id == user.id, Permission.is_active == 1, UserPermission.is_granted == 1)
    ).all():
        if _not_expired(up.expires_at):
            perms[p.id] = p
    return list(perms.values())


def get_accessible_modules(db: Session, user: User, dashboard: str) -> list[str]:
    if user.is_superuser:
        return list(db.execute(
            select(Permission.module).where(
                Permission.dashboard == dashboard, Permission.action == "view", Permission.is_active == 1
            ).distinct()
        ).scalars())
    checker = PermissionChecker(db, user)
    modules = {m for (d, m, a) in checker.role_perms if d == dashboard and a == "view"}
    for (d, m, a), granted in checker.direct.items():
        if d == dashboard and a == "view":
            if granted:
                modules.add(m)
            else:
                modules.discard(m)
    return sorted(modules)


def is_manager_like(user: User) -> bool:
    """`user.user_type == 'manager' or user.is_manager` — used throughout the Django templates —
    or an admin of a university/organisation workspace (a manager within their workspace)."""
    return user.user_type == "manager" or bool(user.is_manager) or is_org_admin(user)


def is_admin_like(user: User) -> bool:
    """`is_staff or is_superuser or manager` — gate for Mail and Manage Categories menus."""
    return bool(user.is_staff or user.is_superuser) or is_manager_like(user)
