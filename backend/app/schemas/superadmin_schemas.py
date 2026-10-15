"""Request bodies for the superadmin API."""
from typing import Any

from pydantic import BaseModel, Field


class ActionIn(BaseModel):
    action: str = ""
    ids: list[str] = Field(default_factory=list)
    select_across: bool = False
    # current changelist query (search / filters) — used when select_across is true
    params: dict[str, str] = Field(default_factory=dict)
    # delete_selected: False → return the confirmation summary, True → delete
    post: bool = False


class ListEditRow(BaseModel):
    pk: str
    values: dict[str, Any] = Field(default_factory=dict)


class ListEditIn(BaseModel):
    rows: list[ListEditRow] = Field(default_factory=list)


class PasswordIn(BaseModel):
    usable_password: str | bool = "true"
    password1: str = ""
    password2: str = ""


class UserAddIn(BaseModel):
    username: str = ""
    usable_password: str | bool = "true"
    password1: str = ""
    password2: str = ""
