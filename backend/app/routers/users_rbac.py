"""Roles & permissions.

/api/rbac/legacy/...  ⇐ library.views: roles_management_view, create_role_view, edit_role_view,
                         assign_user_role_view, get_available_users_view
/api/rbac/...         ⇐ library.permission_views (the "comprehensive" permission screens)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import PermissionChecker, get_all_roles, has_module_permission
from app.core.utils import iso, user_type_display
from app.database import get_db
from app.models import Permission, Role, RolePermission, User, UserRole
from app.schemas.users_schemas import (
    AssignPermissionIn, AssignUserRoleIn, RoleEditIn, RoleFormIn, RolesManagementActionIn,
    ToggleDashboardPermissionIn, UserRoleActionIn,
)
from app.services.users_common import (
    active_permissions_ordered, delete_role, deny, get_full_name, get_or_404, manager_or_superuser, platform_manager, module_display, msg,
    parse_local_datetime, permission_dict, permissions_by_dashboard, role_dict, role_permission_ids,
    set_role_permissions, user_row,
)

router = APIRouter(prefix="/api/rbac", tags=["rbac"])

MANAGE_USERS = "/library/manage-users/"
LEGACY_ROLES = "/library/roles/"
COMP_ROLES = "/library/permissions/roles/"
CL_DASHBOARD = "/content-lab-management/dashboard/"


def ok(message: str | None = None, level: str = "success", **data):
    return {"success": True, "message": message, "messages": [msg(level, message)] if message else [], **data}


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _users_with_role(db: Session, role_id: int, newest_first: bool = True) -> list[dict]:
    q = select(UserRole).where(UserRole.role_id == role_id)
    q = q.order_by(UserRole.assigned_at.desc()) if newest_first else q.order_by(UserRole.id)
    out = []
    for ur in db.execute(q).scalars():
        out.append({
            "id": ur.id, "user": user_row(ur.user), "assigned_at": iso(ur.assigned_at), "expires_at": iso(ur.expires_at),
            "assigned_by": get_full_name(ur.assigned_by) if ur.assigned_by else None,
        })
    return out


def _role_form_context(db: Session) -> dict:
    perms = active_permissions_ordered(db)
    return {"permissions_by_dashboard": permissions_by_dashboard(perms), "total_permissions": len(perms)}


# ====================================================================== legacy (library/views.py)
@router.get("/legacy/roles")
def legacy_roles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        deny("You do not have permission to manage roles", MANAGE_USERS)
    roles = db.execute(select(Role).where(Role.is_active == 1).order_by(Role.id)).scalars().all()
    out = []
    for r in roles:
        perms = db.execute(
            select(Permission).join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == r.id)
            .order_by(Permission.dashboard, Permission.module, Permission.action)
        ).scalars().all()
        out.append({**role_dict(r), "permission_count": len(perms), "permissions": [permission_dict(p) for p in perms[:5]]})
    return {"roles": out, **_role_form_context(db)}


@router.post("/legacy/roles")
def legacy_roles_action(body: RolesManagementActionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not platform_manager(user):
        deny("You do not have permission to manage roles", MANAGE_USERS)
    if body.action == "delete_role":
        role = get_or_404(db, Role, _int(body.role_id))
        if role.is_system_role:
            raise HTTPException(400, "System roles cannot be deleted")
        name = role.name
        delete_role(db, role)
        db.commit()
        return ok(f'Role "{name}" deleted successfully')
    return ok()


@router.get("/legacy/roles/create")
def legacy_create_role_form(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not platform_manager(user):
        deny("You do not have permission to create roles", LEGACY_ROLES)
    return _role_form_context(db)


@router.post("/legacy/roles/create")
def legacy_create_role(body: RoleFormIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not platform_manager(user):
        deny("You do not have permission to create roles", LEGACY_ROLES)
    name = body.name
    if not name:
        raise HTTPException(400, "Role name is required")
    if db.execute(select(Role.id).where(Role.name == name)).first():
        raise HTTPException(400, f'Role "{name}" already exists. Please choose a different name.')
    role = Role(name=name, description=body.description or "", is_system_role=0, is_active=1)
    db.add(role)
    db.flush()
    set_role_permissions(db, role, body.permissions, user)
    db.commit()
    return ok(f'Role "{role.name}" has been created successfully', id=role.id)


def _legacy_edit_guard(db: Session, user: User, role_id: int) -> Role:
    if not platform_manager(user):
        deny("You do not have permission to edit roles", LEGACY_ROLES)
    role = get_or_404(db, Role, role_id)
    if role.is_system_role and not user.is_superuser:
        deny("System roles can only be edited by superusers", LEGACY_ROLES)
    return role


@router.get("/legacy/roles/{role_id}")
def legacy_edit_role_form(role_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = _legacy_edit_guard(db, user, role_id)
    return {"role": role_dict(role), "current_permission_ids": role_permission_ids(db, role.id),
            "users_with_role": _users_with_role(db, role.id), **_role_form_context(db)}


@router.post("/legacy/roles/{role_id}")
def legacy_edit_role(role_id: int, body: RoleEditIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = _legacy_edit_guard(db, user, role_id)
    if body.action == "remove_user_role":
        if body.user_role_id:
            ur = db.execute(select(UserRole).where(UserRole.id == _int(body.user_role_id), UserRole.role_id == role.id)).scalar_one_or_none()
            if ur is None:
                raise HTTPException(400, "User role assignment not found")
            user_name = get_full_name(ur.user)
            db.delete(ur)
            db.commit()
            return ok(f'Role "{role.name}" has been removed from {user_name}')
        return ok()
    if not body.name:
        raise HTTPException(400, "Role name is required")
    role.name = body.name
    role.description = body.description or ""
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(400, f"Error updating role: {e.orig}")
    set_role_permissions(db, role, body.permissions, user)
    db.commit()
    return ok(f'Role "{role.name}" has been updated successfully')


@router.post("/legacy/roles/{role_id}/assign-user")
def legacy_assign_user_role(role_id: int, body: AssignUserRoleIn, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        deny("You do not have permission to assign roles", f"/library/role/{role_id}/edit/")
    role = get_or_404(db, Role, role_id)
    if not body.user_id:
        raise HTTPException(400, "Please select a user")
    target = db.get(User, _int(body.user_id))
    if target is None:
        raise HTTPException(400, "Selected user not found")
    if db.execute(select(UserRole.id).where(UserRole.user_id == target.id, UserRole.role_id == role.id)).first():
        return ok(f'User {get_full_name(target)} already has the role "{role.name}"', level="warning")
    expires = parse_local_datetime(body.expires_at) if body.expires_at else None
    db.add(UserRole(user_id=target.id, role_id=role.id, assigned_by_id=user.id, expires_at=expires))
    db.commit()
    return ok(f'Role "{role.name}" has been assigned to {get_full_name(target)}')


@router.get("/legacy/roles/{role_id}/available-users")
def legacy_available_users(role_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        raise HTTPException(403, "Permission denied")
    role = get_or_404(db, Role, role_id)
    with_role = select(UserRole.user_id).where(UserRole.role_id == role.id)
    users = db.execute(select(User).where(User.is_active == 1, User.id.not_in(with_role))
                       .order_by(User.first_name, User.last_name)).scalars().all()
    return {"users": [{"id": u.id, "name": get_full_name(u), "email": u.email, "user_type": user_type_display(u)} for u in users]}


# ====================================================================== comprehensive (permission_views.py)
def _perm(db: Session, user: User, module: str, action: str) -> bool:
    return has_module_permission(db, user, "content_lab", module, action)


@router.get("/dashboard")
def permission_management_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_permissions", "view"):
        deny("You do not have permission to access permission management.", CL_DASHBOARD)
    count = lambda stmt: db.execute(stmt).scalar_one()  # noqa: E731
    recent = db.execute(select(UserRole).order_by(UserRole.assigned_at.desc()).limit(10)).scalars().all()
    return {
        "page_title": "Permission Management Dashboard",
        "stats": {
            "total_permissions": count(select(func.count(Permission.id)).where(Permission.is_active == 1)),
            "total_roles": count(select(func.count(Role.id)).where(Role.is_active == 1)),
            "total_users": count(select(func.count(User.id)).where(User.is_active == 1)),
            "total_role_assignments": count(select(func.count(UserRole.id))),
            "content_lab_permissions": count(select(func.count(Permission.id)).where(
                Permission.dashboard == "content_lab", Permission.is_active == 1)),
            "other_documents_permissions": count(select(func.count(Permission.id)).where(
                Permission.dashboard == "other_documents", Permission.is_active == 1)),
        },
        "recent_role_assignments": [{
            "id": ur.id, "role_name": ur.role.name, "user_name": get_full_name(ur.user),
            "assigned_by": get_full_name(ur.assigned_by) if ur.assigned_by else None, "assigned_at": iso(ur.assigned_at),
        } for ur in recent],
    }


@router.get("/roles")
def comprehensive_roles(page: int = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_roles", "view"):
        deny("You do not have permission to access role management.", CL_DASHBOARD)
    roles = db.execute(select(Role).where(Role.is_active == 1).order_by(Role.name)).scalars().all()
    pc = dict(db.execute(select(RolePermission.role_id, func.count(RolePermission.id)).group_by(RolePermission.role_id)).all())
    uc = dict(db.execute(select(UserRole.role_id, func.count(UserRole.id)).group_by(UserRole.role_id)).all())
    pages = max(1, -(-len(roles) // 10))
    page = page if 1 <= page <= pages else pages
    items = roles[(page - 1) * 10: page * 10]
    return {
        "page_title": "Role Management",
        "roles": [{**role_dict(r), "permission_count": pc.get(r.id, 0), "user_count": uc.get(r.id, 0)} for r in items],
        "page": page, "pages": pages, "total": len(roles),
        "can_create": _perm(db, user, "cl_roles", "create"),
        "can_edit": _perm(db, user, "cl_roles", "edit"),
        "can_delete": _perm(db, user, "cl_roles", "delete"),
    }


@router.post("/roles")
def comprehensive_create_role(body: RoleFormIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_roles", "create"):
        deny("You do not have permission to create roles.", LEGACY_ROLES)
    name = (body.name or "").strip()
    description = (body.description or "").strip()
    if not name:
        raise HTTPException(400, "Role name is required.")
    if db.execute(select(Role.id).where(Role.name == name)).first():
        raise HTTPException(400, "Role with this name already exists.")
    try:
        role = Role(name=name, description=description, is_system_role=0, is_active=1)
        db.add(role)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error creating role: {str(e)}")
    return ok(f'Role "{name}" created successfully.', id=role.id)


@router.get("/roles/{role_id}")
def comprehensive_role_detail(role_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_roles", "view"):
        deny("You do not have permission to access role details.", LEGACY_ROLES)
    role = get_or_404(db, Role, role_id, is_active=1)
    rps = db.execute(select(RolePermission).where(RolePermission.role_id == role.id).order_by(RolePermission.id)).scalars().all()
    can_assign = _perm(db, user, "cl_roles", "assign_permissions")
    available = None
    if can_assign:
        assigned = {rp.permission_id for rp in rps}
        available = [permission_dict(p) for p in active_permissions_ordered(db) if p.id not in assigned]
    return {
        "page_title": f"Role: {role.name}",
        "role": role_dict(role),
        "permissions_by_dashboard": permissions_by_dashboard([rp.permission for rp in rps], display=False),
        "users_with_role": _users_with_role(db, role.id, newest_first=False),
        "available_permissions": available,
        "can_edit": _perm(db, user, "cl_roles", "edit"),
        "can_assign_permissions": can_assign,
    }


def _comp_edit_guard(db: Session, user: User, role_id: int) -> Role:
    if not _perm(db, user, "cl_roles", "edit"):
        deny("You do not have permission to edit roles.", LEGACY_ROLES)
    role = get_or_404(db, Role, role_id, is_active=1)
    if role.is_system_role and not user.is_superuser:
        deny("System roles can only be edited by superusers", COMP_ROLES)
    return role


@router.get("/roles/{role_id}/edit")
def comprehensive_edit_role_form(role_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = _comp_edit_guard(db, user, role_id)
    return {"page_title": f"Edit Role: {role.name}", "role": role_dict(role),
            "current_permission_ids": role_permission_ids(db, role.id),
            "users_with_role": _users_with_role(db, role.id), **_role_form_context(db)}


@router.post("/roles/{role_id}/edit")
def comprehensive_edit_role(role_id: int, body: RoleEditIn, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    role = _comp_edit_guard(db, user, role_id)
    if body.action == "remove_user_role":
        if body.user_role_id:
            ur = db.execute(select(UserRole).where(UserRole.id == _int(body.user_role_id), UserRole.role_id == role.id)).scalar_one_or_none()
            if ur is None:
                raise HTTPException(400, "User role assignment not found")
            user_name = get_full_name(ur.user)
            db.delete(ur)
            db.commit()
            return ok(f'Role "{role.name}" has been removed from {user_name}')
        return ok()
    name = (body.name or "").strip()
    description = (body.description or "").strip()
    if not name:
        raise HTTPException(400, "Role name is required.")
    if db.execute(select(Role.id).where(Role.name == name, Role.id != role.id)).first():
        raise HTTPException(400, "Role with this name already exists.")
    try:
        role.name = name
        role.description = description
        set_role_permissions(db, role, body.permissions, user)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error updating role: {str(e)}")
    return ok(f'Role "{role.name}" has been updated successfully')


@router.post("/roles/{role_id}/assign-permission")
def assign_permission_to_role(role_id: int, body: AssignPermissionIn, user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_roles", "assign_permissions"):
        raise HTTPException(403, "Permission denied")
    role = db.execute(select(Role).where(Role.id == role_id, Role.is_active == 1)).scalar_one_or_none()
    if role is None:
        raise HTTPException(404, "Role not found")
    permission = db.execute(select(Permission).where(Permission.id == _int(body.permission_id), Permission.is_active == 1)).scalar_one_or_none()
    if permission is None:
        raise HTTPException(404, "Permission not found")
    if db.execute(select(RolePermission.id).where(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)).first():
        raise HTTPException(400, "Permission already assigned to this role")
    db.add(RolePermission(role_id=role.id, permission_id=permission.id, granted_by_id=None))
    db.commit()
    return {"success": True, "message": f'Permission "{permission.name}" assigned to role "{role.name}"'}


@router.delete("/roles/{role_id}/permissions/{permission_id}")
def remove_permission_from_role(role_id: int, permission_id: int, user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_roles", "assign_permissions"):
        raise HTTPException(403, "Permission denied")
    role = db.execute(select(Role).where(Role.id == role_id, Role.is_active == 1)).scalar_one_or_none()
    if role is None:
        raise HTTPException(404, "Role not found")
    permission = db.execute(select(Permission).where(Permission.id == permission_id, Permission.is_active == 1)).scalar_one_or_none()
    if permission is None:
        raise HTTPException(404, "Permission not found")
    rp = db.execute(select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)).scalars().first()
    if rp is None:
        raise HTTPException(400, "Permission not assigned to this role")
    db.delete(rp)
    db.commit()
    return {"success": True, "message": f'Permission "{permission.name}" removed from role "{role.name}"'}


@router.get("/users/{user_id}/roles")
def user_role_management(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_users", "assign_roles"):
        deny("You do not have permission to assign roles to users.", MANAGE_USERS)
    target = get_or_404(db, User, user_id, is_active=1)
    return _user_roles_context(db, target)


def _user_roles_context(db: Session, target: User) -> dict:
    urs = db.execute(select(UserRole).where(UserRole.user_id == target.id).order_by(UserRole.id)).scalars().all()
    current = {ur.role_id for ur in urs}
    available = db.execute(select(Role).where(Role.is_active == 1).order_by(Role.id)).scalars().all()
    return {
        "page_title": f"Manage Roles: {get_full_name(target)}",
        "target_user": user_row(target),
        "user_roles": [{"id": ur.id, "role": role_dict(ur.role), "assigned_at": iso(ur.assigned_at),
                        "expires_at": iso(ur.expires_at)} for ur in urs],
        "available_roles": [role_dict(r) for r in available if r.id not in current],
    }


@router.post("/users/{user_id}/roles")
def user_role_management_action(user_id: int, body: UserRoleActionIn, user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_users", "assign_roles"):
        deny("You do not have permission to assign roles to users.", MANAGE_USERS)
    target = get_or_404(db, User, user_id, is_active=1)
    if body.action == "assign":
        role = db.execute(select(Role).where(Role.id == _int(body.role_id), Role.is_active == 1)).scalar_one_or_none()
        if role is None:
            raise HTTPException(400, "Role not found.")
        try:
            db.add(UserRole(user_id=target.id, role_id=role.id, assigned_by_id=user.id))
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            raise HTTPException(400, f"Error assigning role: {str(e)}")
        return ok(f'Role "{role.name}" assigned to {get_full_name(target)}')
    if body.action == "remove":
        ur = db.execute(select(UserRole).where(UserRole.user_id == target.id, UserRole.role_id == _int(body.role_id))).scalar_one_or_none()
        if ur is None:
            raise HTTPException(400, "User role assignment not found.")
        role_name = ur.role.name
        db.delete(ur)
        db.commit()
        return ok(f'Role "{role_name}" removed from {get_full_name(target)}')
    return ok()


@router.get("/users/{user_id}/permissions")
def user_effective_permissions(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_users", "view"):
        deny("You do not have permission to view user permissions.", MANAGE_USERS)
    target = get_or_404(db, User, user_id, is_active=1)
    urs = db.execute(select(UserRole).where(UserRole.user_id == target.id).order_by(UserRole.id)).scalars().all()
    all_perms: dict[int, Permission] = {}
    role_permissions = []
    for ur in urs:
        rps = db.execute(select(RolePermission).where(RolePermission.role_id == ur.role_id).order_by(RolePermission.id)).scalars().all()
        role_permissions.append({"role": ur.role.name, "permissions": [permission_dict(rp.permission) for rp in rps]})
        for rp in rps:
            all_perms[rp.permission.id] = rp.permission
    return {
        "page_title": f"User Permissions: {get_full_name(target)}",
        "target_user": user_row(target),
        "user_roles": [{"id": ur.id, "role": role_dict(ur.role), "assigned_at": iso(ur.assigned_at),
                        "expires_at": iso(ur.expires_at)} for ur in urs],
        "role_permissions": role_permissions,
        "permissions_by_dashboard": permissions_by_dashboard(list(all_perms.values()), display=False),
        "total_permissions": len(all_perms),
    }


@router.get("/dashboard-access")
def dashboard_permissions_management(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_permissions", "view"):
        deny("You do not have permission to manage dashboard permissions.", CL_DASHBOARD)
    cl = db.execute(select(Permission).where(Permission.dashboard == "content_lab", Permission.module == "cl_dashboard_access",
                                             Permission.action == "view").limit(1)).scalar_one_or_none()
    od = db.execute(select(Permission).where(Permission.dashboard == "other_documents", Permission.module == "od_dashboard_access",
                                             Permission.action == "view").limit(1)).scalar_one_or_none()
    users = db.execute(select(User).where(User.is_active == 1).order_by(User.first_name, User.last_name)).scalars().all()
    user_access = []
    for u in users:
        checker = PermissionChecker(db, u)
        user_access.append({
            "user": user_row(u),
            "can_access_content_lab": checker.has("content_lab", "cl_dashboard_access", "view"),
            "can_access_other_docs": checker.has("other_documents", "od_dashboard_access", "view"),
            "roles": [{"id": r.id, "name": r.name} for r in get_all_roles(db, u)],
        })
    roles = db.execute(select(Role).where(Role.is_active == 1).order_by(Role.name)).scalars().all()
    uc = dict(db.execute(select(UserRole.role_id, func.count(UserRole.id)).group_by(UserRole.role_id)).all())

    def has(role_id: int, perm: Permission | None) -> bool:
        if perm is None:
            return False
        return db.execute(select(RolePermission.id).where(RolePermission.role_id == role_id,
                                                          RolePermission.permission_id == perm.id)).first() is not None

    return {
        "page_title": "Dashboard Permissions Management",
        "user_dashboard_access": user_access,
        "role_dashboard_access": [{"role": role_dict(r), "has_content_lab": has(r.id, cl), "has_other_docs": has(r.id, od),
                                   "user_count": uc.get(r.id, 0)} for r in roles],
        "content_lab_permission": permission_dict(cl) if cl else None,
        "other_documents_permission": permission_dict(od) if od else None,
        "can_edit": _perm(db, user, "cl_permissions", "edit"),
    }


@router.post("/toggle-role-dashboard-permission")
def toggle_role_dashboard_permission(body: ToggleDashboardPermissionIn, user: User = Depends(get_current_user),
                                     db: Session = Depends(get_db)):
    if not _perm(db, user, "cl_permissions", "edit"):
        raise HTTPException(403, "Permission denied")
    role = db.execute(select(Role).where(Role.id == _int(body.role_id), Role.is_active == 1)).scalar_one_or_none()
    if role is None:
        raise HTTPException(404, "Role not found")
    permission = db.execute(select(Permission).where(Permission.id == _int(body.permission_id), Permission.is_active == 1)).scalar_one_or_none()
    if permission is None:
        raise HTTPException(404, "Permission not found")
    rp = db.execute(select(RolePermission).where(RolePermission.role_id == role.id,
                                                 RolePermission.permission_id == permission.id)).scalars().first()
    if body.action == "grant":
        if rp is None:
            db.add(RolePermission(role_id=role.id, permission_id=permission.id, granted_by_id=user.id))
            db.commit()
            message = f'Dashboard access "{module_display(permission)}" granted to role "{role.name}"'
        else:
            message = f'Role "{role.name}" already has this permission'
    elif body.action == "revoke":
        if rp is not None:
            db.delete(rp)
            db.commit()
            message = f'Dashboard access "{module_display(permission)}" revoked from role "{role.name}"'
        else:
            message = f'Role "{role.name}" does not have this permission'
    else:
        raise HTTPException(400, "Invalid action")
    return {"success": True, "message": message}
