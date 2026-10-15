"""Payment gateways: Stripe, Razorpay and CCAvenue.

The superadmin keeps each gateway's keys here (secrets encrypted at rest with a key derived from
SECRET_KEY), enables the ones that may be used and makes exactly one of them *active*: every payment
goes through the active gateway. Each gateway has an adapter with the same small interface:

* `test(gw)`            — check the keys against the provider (or their format, for CCAvenue)
* `create_order(gw, …)` — start a payment; returns what the browser needs to open checkout
* `verify(gw, …)`       — check a payment callback / webhook really came from the provider
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import parse_qsl, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PaymentGateway, User, utcnow

MODES = ("test", "live")
CURRENCIES = ("INR", "USD", "EUR", "GBP", "AED", "SGD")
TIMEOUT = 10.0


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""


@dataclass(frozen=True)
class GatewaySpec:
    code: str
    name: str
    description: str
    docs_url: str
    fields: tuple[Field, ...]
    public_key_field: str | None  # field the browser may see (e.g. Razorpay key id)


SPECS: dict[str, GatewaySpec] = {
    "razorpay": GatewaySpec(
        "razorpay", "Razorpay", "Cards, UPI, net banking and wallets for India.",
        "https://dashboard.razorpay.com/app/website-app-settings/api-keys",
        (Field("key_id", "Key ID", help="Starts with rzp_test_ or rzp_live_."),
         Field("key_secret", "Key Secret", secret=True),
         Field("webhook_secret", "Webhook Secret", secret=True, required=False,
               help="Set in Razorpay → Webhooks; used to verify payment events.")),
        "key_id"),
    "stripe": GatewaySpec(
        "stripe", "Stripe", "International cards and wallets.",
        "https://dashboard.stripe.com/apikeys",
        (Field("publishable_key", "Publishable key", help="Starts with pk_test_ or pk_live_."),
         Field("secret_key", "Secret key", secret=True, help="Starts with sk_test_ or sk_live_."),
         Field("webhook_secret", "Webhook signing secret", secret=True, required=False, help="Starts with whsec_.")),
        "publishable_key"),
    "ccavenue": GatewaySpec(
        "ccavenue", "CCAvenue", "Cards, net banking and EMI through CCAvenue.",
        "https://dashboard.ccavenue.com/",
        (Field("merchant_id", "Merchant ID"),
         Field("access_code", "Access Code"),
         Field("working_key", "Working Key", secret=True, help="32-character key from CCAvenue → Settings → API Keys.")),
        None),
}
ORDER = ("razorpay", "stripe", "ccavenue")


class PaymentError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------- secrets
def _fernet() -> Fernet:
    key = hashlib.sha256(f"payment-gateways:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def read_secrets(gw: PaymentGateway) -> dict[str, str]:
    """Decrypted secrets; {} when none are stored or they were encrypted with another SECRET_KEY."""
    if not gw.secrets:
        return {}
    try:
        return json.loads(_fernet().decrypt(gw.secrets.encode()).decode())
    except (InvalidToken, ValueError):
        return {}


def _write_secrets(gw: PaymentGateway, values: dict[str, str]) -> None:
    gw.secrets = _fernet().encrypt(json.dumps(values).encode()).decode() if values else None


def config_of(gw: PaymentGateway) -> dict[str, str]:
    """All settings of a gateway (public and secret) for the adapters."""
    return {**(gw.public_config or {}), **read_secrets(gw)}


def missing_fields(gw: PaymentGateway) -> list[str]:
    cfg = config_of(gw)
    return [f.label for f in SPECS[gw.code].fields if f.required and not (cfg.get(f.key) or "").strip()]


def _mask(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) > 8 else "••••"


# ---------------------------------------------------------------------------------------------- rows
def ensure_rows(db: Session) -> list[PaymentGateway]:
    """One row per supported gateway (created disabled), in display order."""
    rows = {g.code: g for g in db.execute(select(PaymentGateway)).scalars()}
    for code in ORDER:
        if code not in rows:
            rows[code] = PaymentGateway(code=code, name=SPECS[code].name, is_enabled=0, is_active=0, mode="test",
                                        currency="INR", public_config={}, secrets=None, last_test_message="")
            db.add(rows[code])
    db.flush()
    return [rows[c] for c in ORDER]


def get(db: Session, code: str) -> PaymentGateway:
    if code not in SPECS:
        raise PaymentError("Unknown payment gateway.")
    return next(g for g in ensure_rows(db) if g.code == code)


def active(db: Session) -> PaymentGateway | None:
    gw = db.execute(select(PaymentGateway).where(PaymentGateway.is_active == 1, PaymentGateway.is_enabled == 1)).scalars().first()
    return gw if gw and gw.code in SPECS else None


def serialize(gw: PaymentGateway) -> dict:
    spec = SPECS[gw.code]
    public, secret = gw.public_config or {}, read_secrets(gw)
    fields = []
    for f in spec.fields:
        value = secret.get(f.key, "") if f.secret else public.get(f.key, "")
        fields.append({"key": f.key, "label": f.label, "secret": f.secret, "required": f.required, "help": f.help,
                       # secrets never leave the server: only whether one is set, and its last 4 characters
                       "value": "" if f.secret else value, "is_set": bool(value),
                       "preview": _mask(value) if f.secret and value else ""})
    return {
        "code": gw.code, "name": spec.name, "description": spec.description, "docs_url": spec.docs_url,
        "is_enabled": bool(gw.is_enabled), "is_active": bool(gw.is_active), "mode": gw.mode, "currency": gw.currency,
        "fields": fields, "missing": missing_fields(gw), "secrets_unreadable": bool(gw.secrets) and not secret,
        "last_tested_at": gw.last_tested_at.isoformat() + "Z" if gw.last_tested_at else None,
        "last_test_ok": None if gw.last_test_ok is None else bool(gw.last_test_ok),
        "last_test_message": gw.last_test_message,
    }


def update(db: Session, gw: PaymentGateway, data: dict, user: User) -> None:
    """Save settings. A secret is only replaced when a new value is sent (empty = keep)."""
    if "mode" in data:
        if data["mode"] not in MODES:
            raise PaymentError("Mode must be test or live.")
        gw.mode = data["mode"]
    if "currency" in data:
        if data["currency"] not in CURRENCIES:
            raise PaymentError("Unsupported currency.")
        gw.currency = data["currency"]
    values = data.get("fields") or {}
    public, secret = dict(gw.public_config or {}), read_secrets(gw)
    for f in SPECS[gw.code].fields:
        if f.key not in values:
            continue
        v = str(values[f.key] or "").strip()
        if f.secret:
            if v:
                secret[f.key] = v
        else:
            public[f.key] = v
    _check_formats(gw.code, gw.mode, {**public, **secret})
    gw.public_config = public
    _write_secrets(gw, secret)
    gw.updated_by_id = user.id
    gw.last_test_ok, gw.last_tested_at, gw.last_test_message = None, None, ""  # keys changed: test again


def _check_formats(code: str, mode: str, cfg: dict) -> None:
    def starts(key: str, prefixes: tuple[str, ...], label: str):
        v = cfg.get(key) or ""
        if v and not v.startswith(prefixes):
            raise PaymentError(f"{label} should start with {' or '.join(prefixes)} in {mode} mode.")
    if code == "razorpay":
        starts("key_id", (f"rzp_{mode}_",), "Key ID")
    elif code == "stripe":
        starts("publishable_key", (f"pk_{mode}_",), "Publishable key")
        starts("secret_key", (f"sk_{mode}_", f"rk_{mode}_"), "Secret key")
        starts("webhook_secret", ("whsec_",), "Webhook signing secret")
    elif code == "ccavenue":
        wk = cfg.get("working_key") or ""
        if wk and len(wk) != 32:
            raise PaymentError("Working Key must be 32 characters.")


def set_enabled(db: Session, gw: PaymentGateway, enabled: bool) -> None:
    if enabled and missing_fields(gw):
        raise PaymentError(f"Add {', '.join(missing_fields(gw))} before enabling {SPECS[gw.code].name}.")
    if not enabled and gw.is_active:
        raise PaymentError(f"{SPECS[gw.code].name} is the active gateway. Make another gateway active first.")
    gw.is_enabled = 1 if enabled else 0


def make_active(db: Session, gw: PaymentGateway) -> None:
    """Exactly one active gateway: activating one deactivates the others."""
    if missing_fields(gw):
        raise PaymentError(f"Add {', '.join(missing_fields(gw))} before making {SPECS[gw.code].name} active.")
    for other in ensure_rows(db):
        other.is_active = 1 if other.id == gw.id else 0
    gw.is_enabled = 1


def public_config(db: Session) -> dict:
    """What the browser needs to start a checkout with the active gateway (no secrets)."""
    gw = active(db)
    if gw is None:
        return {"gateway": None}
    spec = SPECS[gw.code]
    if missing_fields(gw):  # chosen as active, but its keys are not filled in yet
        return {"gateway": None, "not_configured": gw.code}
    return {"gateway": gw.code, "name": spec.name, "mode": gw.mode, "currency": gw.currency,
            "public_key": (gw.public_config or {}).get(spec.public_key_field) if spec.public_key_field else None}


# ---------------------------------------------------------------------------------------------- adapters
def _minor_units(amount: Decimal | float | str) -> int:
    value = Decimal(str(amount))
    if value <= 0:
        raise PaymentError("Amount must be more than zero.")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _http_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error")
        return (err.get("description") or err.get("message")) if isinstance(err, dict) else str(err)
    except ValueError:
        return resp.text[:200]


class RazorpayAdapter:
    BASE = "https://api.razorpay.com/v1"

    @staticmethod
    def _auth(cfg):
        return (cfg["key_id"], cfg["key_secret"])

    def test(self, gw: PaymentGateway) -> tuple[bool, str]:
        cfg = config_of(gw)
        r = httpx.get(f"{self.BASE}/payments", params={"count": 1}, auth=self._auth(cfg), timeout=TIMEOUT)
        if r.status_code == 200:
            return True, f"Connected to Razorpay ({gw.mode} mode)."
        return False, f"Razorpay rejected the keys: {_http_message(r)}"

    def create_order(self, gw: PaymentGateway, amount, receipt: str, notes: dict | None = None) -> dict:
        cfg = config_of(gw)
        r = httpx.post(f"{self.BASE}/orders", auth=self._auth(cfg), timeout=TIMEOUT, json={
            "amount": _minor_units(amount), "currency": gw.currency, "receipt": receipt[:40], "notes": notes or {}})
        if r.status_code >= 400:
            raise PaymentError(f"Razorpay could not create the order: {_http_message(r)}")
        order = r.json()
        return {"gateway": "razorpay", "order_id": order["id"], "amount": order["amount"], "currency": order["currency"],
                "key_id": cfg["key_id"]}

    def verify(self, gw: PaymentGateway, *, order_id: str = "", payment_id: str = "", signature: str = "",
               body: bytes = b"", webhook_signature: str = "") -> bool:
        """Checkout callback (order|payment signed with the key secret) or webhook (body signed with the webhook secret)."""
        cfg = config_of(gw)
        if webhook_signature:
            secret = cfg.get("webhook_secret") or ""
            expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            return bool(secret) and hmac.compare_digest(expected, webhook_signature)
        expected = hmac.new(cfg["key_secret"].encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class StripeAdapter:
    BASE = "https://api.stripe.com/v1"

    def test(self, gw: PaymentGateway) -> tuple[bool, str]:
        cfg = config_of(gw)
        r = httpx.get(f"{self.BASE}/balance", headers={"Authorization": f"Bearer {cfg['secret_key']}"}, timeout=TIMEOUT)
        if r.status_code == 200:
            return True, f"Connected to Stripe ({gw.mode} mode)."
        return False, f"Stripe rejected the key: {_http_message(r)}"

    def create_order(self, gw: PaymentGateway, amount, receipt: str, notes: dict | None = None) -> dict:
        cfg = config_of(gw)
        data = {"amount": _minor_units(amount), "currency": gw.currency.lower(), "metadata[receipt]": receipt,
                "automatic_payment_methods[enabled]": "true"}
        for k, v in (notes or {}).items():
            data[f"metadata[{k}]"] = str(v)
        r = httpx.post(f"{self.BASE}/payment_intents", data=data,
                       headers={"Authorization": f"Bearer {cfg['secret_key']}"}, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise PaymentError(f"Stripe could not create the payment: {_http_message(r)}")
        intent = r.json()
        return {"gateway": "stripe", "order_id": intent["id"], "client_secret": intent["client_secret"],
                "amount": intent["amount"], "currency": intent["currency"], "publishable_key": cfg["publishable_key"]}

    def verify(self, gw: PaymentGateway, *, body: bytes = b"", webhook_signature: str = "", tolerance: int = 300, **_) -> bool:
        """Stripe-Signature header: t=<timestamp>,v1=<hmac of 't.body'>."""
        secret = config_of(gw).get("webhook_secret") or ""
        parts = dict(p.split("=", 1) for p in webhook_signature.split(",") if "=" in p)
        if not secret or "t" not in parts or "v1" not in parts:
            return False
        if abs(time.time() - int(parts["t"])) > tolerance:
            return False
        expected = hmac.new(secret.encode(), f"{parts['t']}.".encode() + body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])


class CCAvenueAdapter:
    URLS = {"test": "https://test.ccavenue.com/transaction/transaction.do?command=initiateTransaction",
            "live": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction"}
    IV = bytes(range(16))

    def _cipher(self, working_key: str):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        return Cipher(algorithms.AES(hashlib.md5(working_key.encode()).digest()), modes.CBC(self.IV))

    def encrypt(self, plain: str, working_key: str) -> str:
        from cryptography.hazmat.primitives import padding
        padder = padding.PKCS7(128).padder()
        data = padder.update(plain.encode()) + padder.finalize()
        enc = self._cipher(working_key).encryptor()
        return (enc.update(data) + enc.finalize()).hex()

    def decrypt(self, cipher_hex: str, working_key: str) -> str:
        from cryptography.hazmat.primitives import padding
        dec = self._cipher(working_key).decryptor()
        data = dec.update(bytes.fromhex(cipher_hex)) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return (unpadder.update(data) + unpadder.finalize()).decode()

    def test(self, gw: PaymentGateway) -> tuple[bool, str]:
        # CCAvenue has no key-check API; make sure the working key round-trips and the IDs look right.
        cfg = config_of(gw)
        probe = f"merchant_id={cfg['merchant_id']}&order_id=test"
        ok = self.decrypt(self.encrypt(probe, cfg["working_key"]), cfg["working_key"]) == probe
        if not cfg["merchant_id"].isdigit():
            return False, "Merchant ID should contain digits only."
        return ok, ("Keys look valid. CCAvenue confirms them only on the first real transaction."
                    if ok else "The working key could not encrypt a request.")

    def create_order(self, gw: PaymentGateway, amount, receipt: str, notes: dict | None = None,
                     redirect_url: str = "", cancel_url: str = "") -> dict:
        cfg = config_of(gw)
        params = {"merchant_id": cfg["merchant_id"], "order_id": receipt, "currency": gw.currency,
                  "amount": f"{Decimal(_minor_units(amount)) / 100:.2f}", "redirect_url": redirect_url,
                  "cancel_url": cancel_url or redirect_url, "language": "EN"}
        for i, (k, v) in enumerate((notes or {}).items(), start=1):
            if i <= 5:
                params[f"merchant_param{i}"] = f"{k}:{v}"
        return {"gateway": "ccavenue", "order_id": receipt, "form_url": self.URLS[gw.mode],
                "form": {"encRequest": self.encrypt(urlencode(params), cfg["working_key"]),
                         "access_code": cfg["access_code"]}}

    def verify(self, gw: PaymentGateway, *, enc_response: str = "", **_) -> dict | None:
        """CCAvenue posts back `encResp`; a response that decrypts with our working key is genuine."""
        try:
            return dict(parse_qsl(self.decrypt(enc_response, config_of(gw)["working_key"])))
        except (ValueError, KeyError):
            return None


ADAPTERS = {"razorpay": RazorpayAdapter(), "stripe": StripeAdapter(), "ccavenue": CCAvenueAdapter()}


def test_connection(db: Session, gw: PaymentGateway) -> tuple[bool, str]:
    if missing_fields(gw):
        ok, message = False, f"Add {', '.join(missing_fields(gw))} first."
    else:
        try:
            ok, message = ADAPTERS[gw.code].test(gw)
        except httpx.HTTPError as exc:
            ok, message = False, f"Could not reach {SPECS[gw.code].name}: {exc.__class__.__name__}"
    gw.last_tested_at, gw.last_test_ok, gw.last_test_message = utcnow(), 1 if ok else 0, message[:500]
    return ok, message
