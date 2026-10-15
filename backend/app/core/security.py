"""Password hashing compatible with Django, plus JWT access tokens.

Existing users keep their passwords: Django stores `pbkdf2_sha256$<iter>$<salt>$<b64hash>`,
and we verify and create hashes in exactly that format, so the old Django app and the
new FastAPI app can share the same user table.
"""
import base64
import datetime
import hashlib
import hmac
import secrets
import string

import jwt

from app.config import settings

DJANGO_PBKDF2_ITERATIONS = 870000  # Django 5.2 default
_SALT_CHARS = string.ascii_letters + string.digits
UNUSABLE_PASSWORD_PREFIX = "!"


def _pbkdf2(password: str, salt: str, iterations: int, digest) -> str:
    dk = hashlib.pbkdf2_hmac(digest().name, password.encode(), salt.encode(), iterations)
    return base64.b64encode(dk).decode("ascii").strip()


def make_password(password: str, salt: str | None = None, iterations: int = DJANGO_PBKDF2_ITERATIONS) -> str:
    salt = salt or "".join(secrets.choice(_SALT_CHARS) for _ in range(22))
    return f"pbkdf2_sha256${iterations}${salt}${_pbkdf2(password, salt, iterations, hashlib.sha256)}"


def make_unusable_password() -> str:
    return UNUSABLE_PASSWORD_PREFIX + "".join(secrets.choice(_SALT_CHARS) for _ in range(40))


def check_password(password: str, encoded: str | None) -> bool:
    if not password or not encoded or encoded.startswith(UNUSABLE_PASSWORD_PREFIX):
        return False
    try:
        algorithm, rest = encoded.split("$", 1)
    except ValueError:
        return False
    if algorithm in ("pbkdf2_sha256", "pbkdf2_sha1"):
        iterations, salt, _hash = rest.split("$", 2)
        digest = hashlib.sha256 if algorithm == "pbkdf2_sha256" else hashlib.sha1
        candidate = f"{algorithm}${iterations}${salt}${_pbkdf2(password, salt, int(iterations), digest)}"
        return hmac.compare_digest(candidate.encode(), encoded.encode())
    if algorithm == "md5":
        salt, _hash = rest.split("$", 1)
        return hmac.compare_digest(hashlib.md5((salt + password).encode()).hexdigest(), _hash)
    if algorithm == "sha1":
        salt, _hash = rest.split("$", 1)
        return hmac.compare_digest(hashlib.sha1((salt + password).encode()).hexdigest(), _hash)
    return False


def has_usable_password(encoded: str | None) -> bool:
    return bool(encoded) and not encoded.startswith(UNUSABLE_PASSWORD_PREFIX)


def create_access_token(user_id: int, extra: dict | None = None, expires_minutes: int | None = None) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + datetime.timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(8),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def password_fingerprint(encoded_password: str | None) -> str:
    """Short digest of the stored hash. Changing the password changes it, which invalidates
    older tokens — the JWT equivalent of Django's session auth hash (update_session_auth_hash)."""
    return hmac.new(settings.SECRET_KEY.encode(), (encoded_password or "").encode(), hashlib.sha256).hexdigest()[:16]


def token_for(user) -> str:
    """Access token bound to the user's current password."""
    return create_access_token(user.id, {"pwd": password_fingerprint(user.password)})


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
