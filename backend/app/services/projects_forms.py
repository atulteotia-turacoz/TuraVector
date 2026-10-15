"""Django-form-equivalent field cleaning for the projects module.

Error texts are Django's built-in messages so the UI shows exactly what the
original forms showed.
"""
import datetime
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

REQUIRED = "This field is required."
INVALID_DATE = "Enter a valid date."
INVALID_EMAIL = "Enter a valid email address."
INVALID_INT = "Enter a whole number."
INVALID_NUMBER = "Enter a number."

# django.core.validators.EmailValidator (simplified but equivalent for real addresses)
_EMAIL_RE = re.compile(
    r"^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"
    r"@((?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z0-9-]{2,63}(?<!-)|\[[0-9a-f:.]+\])$",
    re.IGNORECASE,
)


class FormErrors:
    """Collects field errors like a bound Django form."""

    def __init__(self) -> None:
        self.errors: dict[str, list[str]] = {}
        self.non_field: list[str] = []

    def add(self, field: str | None, message: str) -> None:
        if field is None:
            self.non_field.append(message)
        else:
            self.errors.setdefault(field, []).append(message)

    def __bool__(self) -> bool:
        return bool(self.errors or self.non_field)

    def as_detail(self, message: str) -> dict[str, Any]:
        return {"message": message, "errors": self.errors, "non_field_errors": self.non_field}

    def raise_if_any(self, message: str, status_code: int = 400) -> None:
        if self:
            raise HTTPException(status_code, detail=self.as_detail(message))


def _s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "on" if value else ""
    return str(value)


def clean_char(errs: FormErrors, field: str, value: Any, *, max_length: int, required: bool = False,
               null: bool = False, strip: bool = True) -> str | None:
    """forms.CharField: strips, required check, max_length; empty -> None when the model field is null=True."""
    text = _s(value)
    if strip:
        text = text.strip()
    if not text:
        if required:
            errs.add(field, REQUIRED)
        return None if null else ""
    if len(text) > max_length:
        errs.add(field, f"Ensure this value has at most {max_length} characters (it has {len(text)}).")
    return text


def clean_email(errs: FormErrors, field: str, value: Any, *, required: bool = False, null: bool = False) -> str | None:
    text = _s(value).strip()
    if not text:
        if required:
            errs.add(field, REQUIRED)
        return None if null else ""
    if len(text) > 254:
        errs.add(field, f"Ensure this value has at most 254 characters (it has {len(text)}).")
    if not _EMAIL_RE.match(text):
        errs.add(field, INVALID_EMAIL)
    return text


def clean_choice(errs: FormErrors, field: str, value: Any, choices: list[tuple[str, str]], *,
                 required: bool = True) -> str | None:
    text = _s(value).strip()
    if not text:
        if required:
            errs.add(field, REQUIRED)
        return None
    if text not in {c[0] for c in choices}:
        errs.add(field, f"Select a valid choice. {text} is not one of the available choices.")
    return text


def parse_date_value(value: Any) -> datetime.date | None:
    """Django DATE_INPUT_FORMATS (default list)."""
    if isinstance(value, datetime.date):
        return value
    text = _s(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%b %d, %Y", "%d %b %Y", "%d %b, %Y",
                "%B %d %Y", "%B %d, %Y", "%d %B %Y", "%d %B, %Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(text)


def clean_date(errs: FormErrors, field: str, value: Any, *, required: bool = False) -> datetime.date | None:
    text = _s(value).strip()
    if not text:
        if required:
            errs.add(field, REQUIRED)
        return None
    try:
        return parse_date_value(text)
    except ValueError:
        errs.add(field, INVALID_DATE)
        return None


def clean_bool(value: Any) -> bool:
    """forms.BooleanField / CheckboxInput: 'false', '0', '' and missing are False."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() not in ("", "false", "0", "off", "none")


def clean_decimal(errs: FormErrors, field: str, value: Any, *, max_digits: int, decimal_places: int) -> Decimal | None:
    text = _s(value).strip()
    if not text:
        return None
    try:
        num = Decimal(text)
    except InvalidOperation:
        errs.add(field, INVALID_NUMBER)
        return None
    if not num.is_finite():
        errs.add(field, INVALID_NUMBER)
        return None
    sign, digit_tuple, exponent = num.as_tuple()
    if exponent >= 0:
        digits = len(digit_tuple) + exponent
        decimals = 0
    else:
        if abs(exponent) > len(digit_tuple):
            digits = decimals = abs(exponent)
        else:
            digits = len(digit_tuple)
            decimals = abs(exponent)
    whole_digits = digits - decimals
    if digits > max_digits:
        errs.add(field, f"Ensure that there are no more than {max_digits} digits in total.")
    elif decimals > decimal_places:
        errs.add(field, f"Ensure that there are no more than {decimal_places} decimal places.")
    elif whole_digits > max_digits - decimal_places:
        errs.add(field, f"Ensure that there are no more than {max_digits - decimal_places} digits before the decimal point.")
    return num


def clean_positive_int(errs: FormErrors, field: str, value: Any, *, required: bool = True) -> int | None:
    text = _s(value).strip()
    if not text:
        if required:
            errs.add(field, REQUIRED)
        return None
    try:
        num = int(Decimal(text)) if re.fullmatch(r"[-+]?\d+(\.0*)?", text) else int(text)
    except (ValueError, InvalidOperation):
        errs.add(field, INVALID_INT)
        return None
    if num < 0:
        errs.add(field, "Ensure this value is greater than or equal to 0.")
    if num > 4294967295:
        errs.add(field, "Ensure this value is less than or equal to 4294967295.")
    return num
