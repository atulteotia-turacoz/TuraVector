"""Request bodies for the users module. Fields mirror the Django form POST names."""
from pydantic import BaseModel


class CreateUserIn(BaseModel):
    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    user_type: str = ""          # UserType id
    phone: str = ""
    address: str = ""
    password: str = ""
    confirm_password: str = ""
    is_manager: bool = False
    role: str = ""               # Role id (optional)
    organisation: str = ""       # workspace id — required when a superadmin creates the user


class EditUserIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    username: str | None = None
    phone: str | None = None
    address: str | None = None
    user_type: str = ""
    is_manager: bool = False
    is_active: bool = False


class ChangePasswordIn(BaseModel):
    new_password: str = ""
    confirm_password: str = ""
    send_email: bool = False
    force_change: bool = False


class UserPermissionActionIn(BaseModel):
    action: str = ""
    role_id: str | None = None
    permission_id: str | None = None
    reason: str = ""


class UserTypeIn(BaseModel):
    name: str = ""
    code: str = ""
    description: str = ""
    is_active: bool = False


class RoleFormIn(BaseModel):
    name: str | None = None
    description: str = ""
    permissions: list[str] = []


class RoleEditIn(BaseModel):
    action: str | None = None
    user_role_id: str | None = None
    name: str | None = None
    description: str = ""
    permissions: list[str] = []


class RolesManagementActionIn(BaseModel):
    action: str = ""
    role_id: str | None = None


class AssignUserRoleIn(BaseModel):
    user_id: str | None = None
    expires_at: str | None = None


class AssignPermissionIn(BaseModel):
    permission_id: int | str | None = None


class UserRoleActionIn(BaseModel):
    action: str = ""
    role_id: str | None = None


class ToggleDashboardPermissionIn(BaseModel):
    role_id: int | str | None = None
    permission_id: int | str | None = None
    action: str | None = None
