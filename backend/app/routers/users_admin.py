"""User management — port of library.views: manager_dashboard_view, manage_users_view, create_user_view,
view_user_profile, edit_user_view, toggle_user_status, delete_user_view, change_user_password_view,
view_user_password, user_permissions_view, bulk_import_users_view, download_user_template_view and
the (effective) user-type views.

Django flashed `messages` and redirected; here every write returns `{success, message, messages:[{level,text}]}`
and every refusal is an HTTP error whose detail carries the same message (plus the Django redirect target).
"""
import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.deps import get_current_user
from app.core.email import send_email_with_logging
from app.core import email as core_email
from app.core.permissions import can, is_manager_like
from app.core.security import make_password
from app.core.utils import iso, user_type_display
from app.database import get_db
from app.models import (
    Document, Permission, Role, TemporaryPassword, User, UserPermission, UserRole, UserType, utcnow,
)
from app.schemas.users_schemas import (
    ChangePasswordIn, CreateUserIn, EditUserIn, UserPermissionActionIn, UserTypeIn,
)
from app.services import users_dashboard, users_import
from app.services.users_common import (
    LEGACY_USER_TYPES, active_permissions_ordered, create_user, deny, document_counts, get_full_name, get_or_404,
    manager_only, manager_or_superuser, msg, permission_str, platform_manager, permissions_by_dashboard, role_dict, user_permissions_list,
    user_roles_list, user_row, user_type_dict, user_type_user_counts,
)

from app.core.tenancy import place_new_users_in  # noqa: E402
from app.services.superadmin_scope import workspace_of  # noqa: E402
from app.models import Organisation, OrgMembership  # noqa: E402

router = APIRouter(prefix="/api/users", tags=["users"])

MANAGER_DASHBOARD = "/content-lab-management/dashboard/"
MANAGE_USERS = "/library/manage-users/"
USER_TYPES = "/library/user-types/"
HOME = "/content-lab-management/dashboard/"


def ok(message: str | None = None, *extra_msgs: dict, **data):
    messages = ([msg("success", message)] if message else []) + list(extra_msgs)
    return {"success": True, "message": message, "messages": messages, **data}


# ================================================================== manager dashboard
@router.get("/manager-dashboard")
def manager_dashboard(search: str = "", page: str | None = None,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can(db, user, "can_access_manager_dashboard"):
        deny("You do not have permission to access the manager dashboard", HOME)
    return users_dashboard.manager_dashboard(db, search, page)


# ================================================================== manage users
def _managed_user(db: Session, user: User, user_id: int) -> User:
    """The user being managed. Platform superusers are out of reach for workspace admins and managers."""
    target = get_or_404(db, User, user_id)
    if target.is_superuser and not user.is_superuser:
        raise HTTPException(404, "User not found")
    return target


@router.get("/manage")
def manage_users(search: str = "", user_type: str = "", status: str = "", organisation: str = "",
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_only(user):
        deny("You do not have permission to manage users", MANAGER_DASHBOARD)
    stmt = select(User).options(joinedload(User.user_type_new))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(User.first_name.ilike(like), User.last_name.ilike(like),
                              User.email.ilike(like), User.username.ilike(like)))
    if user_type:
        stmt = stmt.where(User.user_type == user_type)
    if status == "active":
        stmt = stmt.where(User.is_active == 1)
    elif status == "inactive":
        stmt = stmt.where(User.is_active == 0)
    if user.is_superuser and not organisation:
        # the workspace chosen in the superadmin top bar ("all" = every user)
        chosen = workspace_of(db)
        organisation = str(chosen) if chosen else "all"
    # the chosen workspace also scopes the counts at the top; only superusers see superusers
    scope = [] if user.is_superuser else [User.is_superuser == 0]
    if organisation == "none":
        scope.append(~User.id.in_(select(OrgMembership.user_id)))
    elif organisation.isdigit():
        scope.append(User.id.in_(select(OrgMembership.user_id).where(OrgMembership.organisation_id == int(organisation))))
    stmt = stmt.where(*scope)
    users = db.execute(stmt.order_by(User.date_joined.desc())).scalars().unique().all()
    org_name_of = {uid: (f"{name} (system user)" if kind == "system" else name) for uid, name, kind in db.execute(
        select(OrgMembership.user_id, Organisation.name, Organisation.kind).join(
            Organisation, Organisation.id == OrgMembership.organisation_id)).all()}
    counts = document_counts(db)
    total = db.execute(select(func.count(User.id)).where(*scope)).scalar_one()
    active = db.execute(select(func.count(User.id)).where(User.is_active == 1, *scope)).scalar_one()
    type_counts = dict(db.execute(select(User.user_type, func.count(User.id)).where(*scope).group_by(User.user_type)).all())
    return {
        "page_title": "Manage Users",
        "users": [{**user_row(u, counts.get(u.id, 0)), "organisation": org_name_of.get(u.id)} for u in users],
        "search_query": search, "user_type_filter": user_type, "status_filter": status,
        "organisation_filter": organisation, "organisations": _workspace_choices(db, user, include_individual=True),
        "total_users": total, "active_users": active,
        "inactive_users": db.execute(select(func.count(User.id)).where(User.is_active == 0, *scope)).scalar_one(),
        "user_type_stats": [{"code": c, "name": n, "count": type_counts.get(c, 0)} for c, n in LEGACY_USER_TYPES],
        "user_types": [{"value": c, "label": n} for c, n in LEGACY_USER_TYPES],
    }


# ================================================================== create user
@router.get("/create-options")
def create_user_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_only(user):
        deny("You do not have permission to create users", MANAGE_USERS)
    types = db.execute(select(UserType).where(UserType.is_active == 1).order_by(UserType.name)).scalars().all()
    roles = db.execute(select(Role).where(Role.is_active == 1).order_by(Role.name)).scalars().all()
    return {"page_title": "Create New User", "user_types": [user_type_dict(t) for t in types],
            "roles": [role_dict(r) for r in roles], "organisations": _workspace_choices(db, user)}


def _workspace_choices(db: Session, user: User, include_individual: bool = False) -> list[dict] | None:
    """Workspaces a superadmin can pick (None for workspace members: they only ever see their own)."""
    if not user.is_superuser:
        return None
    stmt = select(Organisation).order_by(Organisation.name)
    if not include_individual:
        stmt = stmt.where(Organisation.status == "active", Organisation.kind != "individual")
    else:
        stmt = stmt.where(Organisation.kind != "individual")
    orgs = db.execute(stmt).scalars().all()
    return [{"id": o.id, "name": o.name, "kind": o.kind} for o in orgs]


def _chosen_workspace(db: Session, user: User, value: str | int | None) -> Organisation | None:
    """The workspace a superadmin picked for new users; workspace members always add to their own."""
    if not user.is_superuser:
        return None
    value = value or workspace_of(db)  # default: the workspace chosen in the top bar
    try:
        org = db.get(Organisation, int(value)) if value else None
    except (TypeError, ValueError):
        org = None
    if org is None or org.status != "active" or org.kind == "individual":
        raise HTTPException(400, ["Choose the workspace the new user belongs to"])
    return org


def _welcome_message(u: User) -> str:
    return f'''
                Dear {u.first_name} {u.last_name},

                Your TuraVector account has been created successfully!

                Account Details:
                Username: {u.username}
                Email: {u.email}
                User Type: {user_type_display(u)}

                You can now log in to the system using your username and the password provided by your administrator.

                Best regards,
                TuraVector Team
                '''


@router.post("/create")
def create_user_view(body: CreateUserIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_only(user):
        deny("You do not have permission to create users", MANAGE_USERS)
    username = body.username.strip()
    email = body.email.strip()
    first_name = body.first_name.strip()
    last_name = body.last_name.strip()
    user_type_id = body.user_type.strip()
    phone = body.phone.strip()
    address = body.address.strip()
    password = body.password.strip()
    confirm_password = body.confirm_password.strip()
    role_id = body.role.strip()

    errors: list[str] = []
    if not username:
        errors.append("Username is required")
    elif db.execute(select(User.id).where(User.username == username)).first():
        errors.append("Username already exists")
    if not email:
        errors.append("Email is required")
    elif db.execute(select(User.id).where(User.email == email)).first():
        errors.append("Email already exists")
    if not first_name:
        errors.append("First name is required")
    if not last_name:
        errors.append("Last name is required")

    user_type_obj = None
    if not user_type_id:
        errors.append("User type is required")
    else:
        try:
            user_type_obj = db.execute(select(UserType).where(UserType.id == int(user_type_id), UserType.is_active == 1)).scalar_one_or_none()
        except ValueError:
            user_type_obj = None
        if user_type_obj is None:
            errors.append("Invalid user type selected")
        elif user_type_obj.code == "manager" and not platform_manager(user):
            errors.append("Only a superadmin can create managers")
    if body.is_manager and not platform_manager(user):
        errors.append("Only a superadmin can create managers")

    if not password:
        errors.append("Password is required")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    if password != confirm_password:
        errors.append("Passwords do not match")

    role_obj = None
    if role_id:
        try:
            role_obj = db.execute(select(Role).where(Role.id == int(role_id), Role.is_active == 1)).scalar_one_or_none()
        except ValueError:
            role_obj = None
        if role_obj is None:
            errors.append("Invalid role selected")

    if errors:
        raise HTTPException(400, errors)
    workspace = _chosen_workspace(db, user, body.organisation)
    if workspace:
        place_new_users_in(db, workspace.id)

    try:
        new_user = create_user(
            db, username=username, email=email, password=password, first_name=first_name, last_name=last_name,
            user_type_new_id=user_type_obj.id, user_type=user_type_obj.code if user_type_obj else "student",
            phone=phone or None, address=address or None, is_manager=body.is_manager,
        )
        db.add(TemporaryPassword(user_id=new_user.id, password=password,
                                 expires_at=utcnow() + datetime.timedelta(hours=24)))
        if role_obj:
            db.add(UserRole(user_id=new_user.id, role_id=role_obj.id, assigned_by_id=user.id))
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, [f"Error creating user: {str(e)}"])

    db.refresh(new_user)
    messages = [msg("success", f'User "{new_user.first_name} {new_user.last_name}" created successfully!')]
    try:
        core_email.deliver(db, "Welcome to TuraVector - Your Account Has Been Created", _welcome_message(new_user),
                           "noreply@turadome.com", new_user.email)
        messages.append(msg("info", "Welcome email sent to the new user"))
    except Exception as e:  # noqa: BLE001
        messages.append(msg("warning", f"User created but email notification failed: {str(e)}"))
    return {"success": True, "message": messages[0]["text"], "messages": messages, "user_id": new_user.id}


# ================================================================== profile / edit / status
@router.get("/{user_id}/profile")
def view_user_profile(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        deny("You do not have permission to view user profiles", MANAGE_USERS)
    viewed = _managed_user(db, user, user_id)
    base = select(func.count(Document.id)).where(Document.user_id == viewed.id, Document.is_active == 1)
    recent = db.execute(select(Document).where(Document.user_id == viewed.id, Document.is_active == 1)
                        .order_by(Document.created_at.desc()).limit(5)).scalars().all()
    return {
        "viewed_user": user_row(viewed),
        "document_stats": {
            "total": db.execute(base).scalar_one(),
            "draft": db.execute(base.where(Document.stage_status == 0)).scalar_one(),
            "review": db.execute(base.where(Document.stage_status == 1)).scalar_one(),
            "approved": db.execute(base.where(Document.stage_status == 2)).scalar_one(),
            "recent": [{"id": d.id, "document_name": d.document_name, "stage_status": d.stage_status,
                        "created_at": iso(d.created_at)} for d in recent],
        },
        "user_roles": user_roles_list(db, viewed.id),
        "user_permissions": user_permissions_list(db, viewed.id),
    }


@router.get("/{user_id}/edit")
def edit_user_form(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        deny("You do not have permission to edit users", MANAGE_USERS)
    edited = _managed_user(db, user, user_id)
    types = db.execute(select(UserType).where(UserType.is_active == 1).order_by(UserType.name)).scalars().all()
    return {
        "edited_user": user_row(edited, document_counts(db, [edited.id]).get(edited.id, 0)),
        "user_types": [user_type_dict(t) for t in types],
    }


@router.post("/{user_id}/edit")
def edit_user(user_id: int, body: EditUserIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        deny("You do not have permission to edit users", MANAGE_USERS)
    edited = _managed_user(db, user, user_id)
    if body.first_name is not None:
        edited.first_name = body.first_name
    if body.last_name is not None:
        edited.last_name = body.last_name
    if body.email is not None:
        edited.email = body.email
    if body.username is not None:
        edited.username = body.username
    if body.phone is not None:
        edited.phone = body.phone
    if body.address is not None:
        edited.address = body.address

    if body.user_type:
        try:
            ut = db.execute(select(UserType).where(UserType.id == int(body.user_type), UserType.is_active == 1)).scalar_one_or_none()
        except ValueError:
            ut = None
        if ut is None:
            db.rollback()
            raise HTTPException(400, "Invalid user type selected")
        if ut.code == "manager" and ut.code != edited.user_type and not platform_manager(user):
            db.rollback()
            raise HTTPException(403, "Only a superadmin can make someone a manager")
        edited.user_type_new_id = ut.id
        edited.user_type = ut.code

    if int(body.is_manager) != int(edited.is_manager) and not platform_manager(user):
        db.rollback()
        raise HTTPException(403, "Only a superadmin can change the manager flag")
    edited.is_manager = int(body.is_manager)
    edited.is_active = int(body.is_active)
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error updating user: {str(e)}")
    return ok(f"User {get_full_name(edited)} updated successfully")


@router.post("/{user_id}/toggle-status")
def toggle_user_status(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        deny("You do not have permission to modify users", MANAGE_USERS)
    target = _managed_user(db, user, user_id)
    if target.id == user.id:
        raise HTTPException(400, "You cannot deactivate your own account")
    if target.is_superuser:
        raise HTTPException(400, "Admin/Superuser accounts cannot be deactivated for security reasons")
    if target.username == "admin":
        raise HTTPException(400, "The admin account cannot be deactivated")
    target.is_active = 0 if target.is_active else 1
    db.commit()
    status = "activated" if target.is_active else "deactivated"
    return ok(f"User {get_full_name(target)} has been {status}", is_active=bool(target.is_active))


@router.post("/{user_id}/delete")
def delete_user(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not manager_or_superuser(user):
        deny("You do not have permission to delete users", MANAGE_USERS)
    target = _managed_user(db, user, user_id)
    if target.id == user.id:
        raise HTTPException(400, "You cannot delete your own account")
    if target.is_superuser and not user.is_superuser:
        raise HTTPException(400, "You cannot delete superuser accounts")
    name = get_full_name(target)
    target.is_active = 0  # soft delete
    db.commit()
    return ok(f"User {name} has been deactivated")


# ================================================================== passwords
def _password_admin(user: User) -> bool:
    return bool(user.is_staff or user.is_superuser) or is_manager_like(user)


@router.get("/{user_id}/change-password")
def change_password_form(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _password_admin(user):
        deny("You do not have permission to change user passwords", MANAGE_USERS)
    target = _managed_user(db, user, user_id)
    if target.is_superuser and not user.is_superuser:
        deny("You cannot change superuser passwords", MANAGE_USERS)
    return {"page_title": f"Change Password - {get_full_name(target)}", "target_user": user_row(target)}


@router.post("/{user_id}/change-password")
def change_password(user_id: int, body: ChangePasswordIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not _password_admin(user):
        deny("You do not have permission to change user passwords", MANAGE_USERS)
    target = _managed_user(db, user, user_id)
    if target.is_superuser and not user.is_superuser:
        deny("You cannot change superuser passwords", MANAGE_USERS)

    new_password = body.new_password.strip()
    confirm_password = body.confirm_password.strip()
    errors: list[str] = []
    if not new_password:
        errors.append("New password is required")
    elif len(new_password) < 8:
        errors.append("Password must be at least 8 characters long")
    if new_password != confirm_password:
        errors.append("Passwords do not match")
    if errors:
        raise HTTPException(400, errors)

    try:
        target.password = make_password(new_password)
        db.query(TemporaryPassword).filter(TemporaryPassword.user_id == target.id).delete(synchronize_session=False)
        db.add(TemporaryPassword(user_id=target.id, password=new_password,
                                 expires_at=utcnow() + datetime.timedelta(hours=24)))
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, [f"Error changing password: {str(e)}"])

    name = get_full_name(target)
    if body.send_email and target.email:
        message = f"""
Dear {name},

Your password has been changed by an administrator.

Username: {target.username}
New Password: {new_password}

For security reasons, please log in and change your password immediately.

You can log in at: {settings.FRONTEND_URL.rstrip('/')}/auth/login/

Best regards,
TuraVector Team
"""
        sent, _ = send_email_with_logging(
            db, "Password Changed - TuraVector System", message, [target.email], "password_reset",
            from_email="noreply@turadome.com", sender_user=user, recipient_user=target,
        )
        if sent:
            return ok(f"Password changed successfully for {name} and notification email sent")
        text = "Password changed successfully but failed to send email. Check mail logs for details."
        return {"success": True, "message": text, "messages": [msg("warning", text)]}
    return ok(f"Password changed successfully for {name}")


@router.get("/{user_id}/view-password")
def view_user_password(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_superuser:
        deny("Only administrators can view user passwords", MANAGE_USERS)
    target = db.get(User, user_id)
    if target is None:
        deny("User not found", MANAGE_USERS, status=404)
    password_info = None
    error_message = None
    temp = db.execute(select(TemporaryPassword).where(TemporaryPassword.user_id == target.id)).scalar_one_or_none()
    if temp is None:
        error_message = "Password not available. Only newly created user passwords can be viewed temporarily."
    elif utcnow() > temp.expires_at:
        db.delete(temp)  # clean up expired password
        db.commit()
        error_message = "Temporary password has expired. Use Change Password to set a new one."
    else:
        password_info = {"password": temp.password, "created_at": iso(temp.created_at), "expires_at": iso(temp.expires_at)}
    return {"target_user": user_row(target), "password_info": password_info, "error_message": error_message,
            "page_title": f"View Password - {get_full_name(target)}"}


# ================================================================== legacy per-user permissions
def _require_perm_manager(user: User):
    if not manager_or_superuser(user):
        deny("You do not have permission to manage user permissions", MANAGE_USERS)


@router.get("/{user_id}/permissions")
def user_permissions_page(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_perm_manager(user)
    managed = _managed_user(db, user, user_id)
    assigned = set(db.execute(select(UserRole.role_id).where(UserRole.user_id == managed.id)).scalars())
    available = db.execute(select(Role).where(Role.is_active == 1).order_by(Role.id)).scalars().all()
    return {
        "managed_user": user_row(managed),
        "user_roles": user_roles_list(db, managed.id),
        "user_permissions": user_permissions_list(db, managed.id),
        "available_roles": [role_dict(r) for r in available if r.id not in assigned],
        "permissions_by_dashboard": permissions_by_dashboard(active_permissions_ordered(db)),
    }


@router.post("/{user_id}/permissions")
def user_permissions_action(user_id: int, body: UserPermissionActionIn, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    _require_perm_manager(user)
    managed = _managed_user(db, user, user_id)
    action = body.action
    message = None

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    if action == "assign_role":
        if body.role_id:
            role = get_or_404(db, Role, _int(body.role_id) or 0)
            exists = db.execute(select(UserRole).where(UserRole.user_id == managed.id, UserRole.role_id == role.id)).scalar_one_or_none()
            if exists is None:
                db.add(UserRole(user_id=managed.id, role_id=role.id, assigned_by_id=user.id))
            message = f'Role "{role.name}" assigned to {get_full_name(managed)}'
    elif action == "remove_role":
        db.query(UserRole).filter(UserRole.user_id == managed.id, UserRole.role_id == _int(body.role_id)).delete(synchronize_session=False)
        message = "Role removed successfully"
    elif action in ("grant_permission", "deny_permission"):
        if body.permission_id:
            permission = get_or_404(db, Permission, _int(body.permission_id) or 0)
            granted = action == "grant_permission"
            up = db.execute(select(UserPermission).where(UserPermission.user_id == managed.id,
                                                         UserPermission.permission_id == permission.id)).scalar_one_or_none()
            if up is None:
                db.add(UserPermission(user_id=managed.id, permission_id=permission.id, is_granted=int(granted),
                                      granted_by_id=user.id, reason=body.reason))
            else:
                up.is_granted = int(granted)
                up.granted_by_id = user.id
                up.reason = body.reason
            message = (f'Permission "{permission_str(permission)}" granted to {get_full_name(managed)}' if granted
                       else f'Permission "{permission_str(permission)}" denied for {get_full_name(managed)}')
    elif action == "remove_permission":
        db.query(UserPermission).filter(UserPermission.user_id == managed.id,
                                        UserPermission.permission_id == _int(body.permission_id)).delete(synchronize_session=False)
        message = "Permission override removed"
    db.commit()
    return ok(message)


# ================================================================== bulk import
@router.post("/bulk-import")
async def bulk_import_users(
    file: UploadFile | None = File(None),
    send_welcome_email: bool = Form(False),
    skip_errors: bool = Form(False),
    organisation: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not manager_only(user):
        deny("You do not have permission to import users", MANAGE_USERS)
    error = users_import.validate_file_name(file.filename if file else None)
    if error:
        raise HTTPException(400, {"field_errors": {"file": [error]}, "message": error})
    content = await file.read()
    if not content:
        error = "The submitted file is empty."
        raise HTTPException(400, {"field_errors": {"file": [error]}, "message": error})
    workspace = _chosen_workspace(db, user, organisation)
    if workspace:
        place_new_users_in(db, workspace.id)
    return users_import.import_users(db, file.filename, content, send_welcome_email, skip_errors,
                                     allow_managers=platform_manager(user), default_roles=not user.is_superuser)


@router.get("/bulk-import/template")
def download_user_template(format: str = Query("csv"), user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    if not manager_only(user):
        deny("You do not have permission to download template", MANAGE_USERS)
    content, media_type, filename = users_import.build_template(db, format)
    return Response(content, media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})


# ================================================================== user types
def _types_admin(user: User) -> bool:
    return bool(user.is_superuser) or is_manager_like(user)


def _types_editor(user: User) -> bool:
    return platform_manager(user)


@router.get("/user-types")
def manage_user_types(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _types_admin(user):
        deny("You do not have permission to manage user types.", HOME)
    counts = user_type_user_counts(db)
    types = db.execute(select(UserType).order_by(UserType.name)).scalars().all()
    return {"page_title": "Manage User Types", "user_types": [user_type_dict(t, counts.get(t.id, 0)) for t in types]}


def _validate_type(db: Session, body: UserTypeIn, exclude_id: int | None = None) -> tuple[str, str, str]:
    name, code, description = body.name.strip(), body.code.strip(), body.description.strip()
    if not name:
        raise HTTPException(400, "User type name is required.")
    if not code:
        raise HTTPException(400, "User type code is required.")
    q = select(UserType.id).where(func.lower(UserType.name) == name.lower())
    if exclude_id:
        q = q.where(UserType.id != exclude_id)
    if db.execute(q).first():
        raise HTTPException(400, "A user type with this name already exists.")
    q = select(UserType.id).where(func.lower(UserType.code) == code.lower())
    if exclude_id:
        q = q.where(UserType.id != exclude_id)
    if db.execute(q).first():
        raise HTTPException(400, "A user type with this code already exists.")
    return name, code, description


@router.post("/user-types")
def create_user_type(body: UserTypeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _types_editor(user):
        deny("You do not have permission to create user types.", USER_TYPES)
    name, code, description = _validate_type(db, body)
    try:
        ut = UserType(name=name, code=code.lower().replace(" ", "_"), description=description,
                      is_active=int(body.is_active), is_system=0)
        db.add(ut)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error creating user type: {str(e)}")
    return ok(f'User type "{name}" created successfully.', id=ut.id)


@router.get("/user-types/{user_type_id}")
def edit_user_type_form(user_type_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _types_editor(user):
        deny("You do not have permission to edit user types.", USER_TYPES)
    ut = get_or_404(db, UserType, user_type_id)
    if ut.is_system and not user.is_superuser:
        deny("System user types can only be edited by superusers.", USER_TYPES)
    return {"page_title": f"Edit User Type: {ut.name}",
            "user_type": user_type_dict(ut, user_type_user_counts(db).get(ut.id, 0))}


@router.post("/user-types/{user_type_id}")
def edit_user_type(user_type_id: int, body: UserTypeIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if not _types_editor(user):
        deny("You do not have permission to edit user types.", USER_TYPES)
    ut = get_or_404(db, UserType, user_type_id)
    if ut.is_system and not user.is_superuser:
        deny("System user types can only be edited by superusers.", USER_TYPES)
    name, code, description = _validate_type(db, body, exclude_id=ut.id)
    try:
        ut.name = name
        ut.code = code.lower().replace(" ", "_")
        ut.description = description
        ut.is_active = int(body.is_active)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Error updating user type: {str(e)}")
    return ok(f'User type "{name}" updated successfully.')


@router.post("/user-types/{user_type_id}/delete")
def delete_user_type(user_type_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _types_editor(user):
        deny("You do not have permission to delete user types.", USER_TYPES)
    ut = get_or_404(db, UserType, user_type_id)
    if ut.is_system:
        raise HTTPException(400, "System user types cannot be deleted.")
    in_use = db.execute(select(func.count(User.id)).where(User.user_type_new_id == ut.id)).scalar_one()
    if in_use > 0:
        raise HTTPException(400, f'Cannot delete user type "{ut.name}" as it is assigned to {in_use} user(s).')
    name = ut.name
    try:
        db.delete(ut)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(400, f"Error deleting user type: {str(e)}")
    return ok(f'User type "{name}" deleted successfully.')


@router.post("/user-types/{user_type_id}/toggle-status")
def toggle_user_type_status(user_type_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _types_editor(user):
        raise HTTPException(403, "You do not have permission to modify user types.")
    ut = get_or_404(db, UserType, user_type_id)
    if ut.is_system and not user.is_superuser:
        raise HTTPException(403, "System user types can only be modified by superusers.")
    try:
        ut.is_active = 0 if ut.is_active else 1
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(500, str(e))
    action = "activated" if ut.is_active else "deactivated"
    return {"success": True, "message": f'User type "{ut.name}" {action} successfully.', "is_active": bool(ut.is_active)}
