"""Request bodies for the auth module.

Django read these with `data.get(...)`, so every field is optional here and the
routers perform the exact Django validation (and return the same messages).
"""
from typing import Any

from pydantic import BaseModel


class SignupIn(BaseModel):
    username: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = None
    confirm_password: str | None = None
    user_type: str | None = None
    phone: str | None = None
    address: str | None = None
    privacy_consent: bool = False
    # "individual" (personal workspace) or "join" (ask to join a university/organisation by code)
    account_type: str | None = None
    join_code: str | None = None


class EmailIn(BaseModel):
    email: str | None = None


class VerifyOtpIn(BaseModel):
    email: str | None = None
    otp: str | None = None
    new_password: str | None = None


class ContactIn(BaseModel):
    name: str | None = None
    email: str | None = None
    subject: str | None = None
    message: str | None = None


class UpdateProfileIn(BaseModel):
    """Only keys actually sent are applied (Django: data.get(key, current_value))."""
    first_name: Any = None
    last_name: Any = None
    email: Any = None
    phone: Any = None
    address: Any = None


class ChangePasswordIn(BaseModel):
    current_password: str | None = None
    new_password: str | None = None


class TimezoneIn(BaseModel):
    timezone: str | None = None


class FeedbackIn(BaseModel):
    project_id: Any = None
    rating: Any = None
    feedback: Any = None


class SupportIn(BaseModel):
    subject: str | None = None
    message: str | None = None
