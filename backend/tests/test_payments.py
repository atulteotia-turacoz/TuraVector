"""Payment gateway settings (superadmin) and the gateway adapters. No request leaves the machine."""
import hashlib
import hmac
import time

import httpx
import pytest
from sqlalchemy import select

from app.models import PaymentGateway
from app.services import payments

URL = "/api/superadmin/payment-gateways"
RZP = {"key_id": "rzp_test_ABC123", "key_secret": "rzp-secret-value-123", "webhook_secret": "hook-secret-xyz"}


def _gw(data, code):
    return next(g for g in data["gateways"] if g["code"] == code)


def test_listing_razorpay_active_and_superuser_only(client, login_as):
    assert client.get(URL, headers=login_as("teacher1")).status_code == 403
    d = client.get(URL, headers=login_as("admin")).json()
    assert [g["code"] for g in d["gateways"]] == ["razorpay", "stripe", "ccavenue"]
    assert _gw(d, "razorpay")["is_active"] is True
    assert not _gw(d, "stripe")["is_active"] and not _gw(d, "ccavenue")["is_active"]


def test_secrets_are_encrypted_masked_and_kept(client, db, login_as):
    h = login_as("admin")
    bad = client.post(f"{URL}/razorpay", headers=h, json={"mode": "test", "fields": {"key_id": "rzp_live_X"}})
    assert bad.status_code == 400 and "rzp_test_" in bad.json()["detail"]

    r = client.post(f"{URL}/razorpay", headers=h, json={"mode": "test", "fields": RZP})
    assert r.status_code == 200, r.text
    assert "rzp-secret-value-123" not in r.text and "hook-secret-xyz" not in r.text
    fields = {f["key"]: f for f in _gw(r.json(), "razorpay")["fields"]}
    assert fields["key_id"]["value"] == "rzp_test_ABC123"
    assert fields["key_secret"]["value"] == "" and fields["key_secret"]["is_set"] and fields["key_secret"]["preview"] == "••••-123"

    row = db.execute(select(PaymentGateway).where(PaymentGateway.code == "razorpay")).scalar_one()
    db.refresh(row)
    assert "rzp-secret-value-123" not in (row.secrets or "")  # encrypted at rest
    # an empty secret keeps the stored one
    client.post(f"{URL}/razorpay", headers=h, json={"fields": {"key_secret": "", "key_id": "rzp_test_NEW"}})
    db.refresh(row)
    assert payments.config_of(row)["key_secret"] == "rzp-secret-value-123"
    assert payments.config_of(row)["key_id"] == "rzp_test_NEW"


def test_checkout_config_needs_complete_keys(client, login_as):
    h = login_as("admin")
    client.post(f"{URL}/razorpay", headers=h, json={"fields": {"key_id": "", "key_secret": ""}})
    # Razorpay is the active gateway, but without a Key ID checkout cannot use it yet
    assert client.get("/api/payments/config", headers=login_as("teacher1")).json() == {
        "gateway": None, "not_configured": "razorpay"}
    client.post(f"{URL}/razorpay", headers=h, json={"mode": "test", "fields": RZP})
    cfg = client.get("/api/payments/config", headers=login_as("teacher1")).json()
    assert cfg == {"gateway": "razorpay", "name": "Razorpay", "mode": "test", "currency": "INR",
                   "public_key": "rzp_test_ABC123"}
    assert client.get("/api/payments/config").status_code == 401


def test_only_one_active_and_rules(client, login_as):
    h = login_as("admin")
    r = client.post(f"{URL}/stripe/activate", headers=h)
    assert r.status_code == 400 and "Publishable key" in r.json()["detail"]
    assert client.post(f"{URL}/razorpay/enabled", headers=h, json={"enabled": False}).status_code == 400  # active one
    client.post(f"{URL}/stripe", headers=h, json={"mode": "test", "fields": {
        "publishable_key": "pk_test_1", "secret_key": "sk_test_1", "webhook_secret": "whsec_1"}})
    d = client.post(f"{URL}/stripe/activate", headers=h).json()
    assert _gw(d, "stripe")["is_active"] and _gw(d, "stripe")["is_enabled"] and not _gw(d, "razorpay")["is_active"]
    assert client.post(f"{URL}/razorpay/enabled", headers=h, json={"enabled": False}).status_code == 200


def test_connection_check_is_recorded(client, login_as, monkeypatch):
    h = login_as("admin")
    client.post(f"{URL}/razorpay", headers=h, json={"mode": "test", "fields": RZP})
    seen = {}

    def fake_get(url, **kw):
        seen["url"], seen["auth"] = url, kw.get("auth")
        return httpx.Response(200, json={"items": []}, request=httpx.Request("GET", url))
    monkeypatch.setattr(payments.httpx, "get", fake_get)
    d = client.post(f"{URL}/razorpay/test", headers=h).json()
    assert d["ok"] is True and "Connected to Razorpay" in d["message"]
    assert seen["url"].startswith("https://api.razorpay.com/") and seen["auth"] == ("rzp_test_ABC123", "rzp-secret-value-123")
    assert _gw(d, "razorpay")["last_test_ok"] is True

    monkeypatch.setattr(payments.httpx, "get", lambda url, **kw: httpx.Response(
        401, json={"error": {"description": "Authentication failed"}}, request=httpx.Request("GET", url)))
    d = client.post(f"{URL}/razorpay/test", headers=h).json()
    assert d["ok"] is False and "Authentication failed" in d["message"]


def _row(**cfg):
    gw = PaymentGateway(code=cfg.pop("code"), name="x", mode="test", currency="INR", public_config={}, secrets=None)
    payments._write_secrets(gw, cfg)
    return gw


def test_razorpay_signatures():
    gw = _row(code="razorpay", **RZP)
    a = payments.ADAPTERS["razorpay"]
    sig = hmac.new(b"rzp-secret-value-123", b"order_1|pay_1", hashlib.sha256).hexdigest()
    assert a.verify(gw, order_id="order_1", payment_id="pay_1", signature=sig)
    assert not a.verify(gw, order_id="order_1", payment_id="pay_2", signature=sig)
    body = b'{"event":"payment.captured"}'
    wh = hmac.new(b"hook-secret-xyz", body, hashlib.sha256).hexdigest()
    assert a.verify(gw, body=body, webhook_signature=wh) and not a.verify(gw, body=b"x", webhook_signature=wh)


def test_stripe_webhook_signature():
    gw = _row(code="stripe", publishable_key="pk_test_1", secret_key="sk_test_1", webhook_secret="whsec_abc")
    body, t = b'{"id":"evt_1"}', str(int(time.time()))
    v1 = hmac.new(b"whsec_abc", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    a = payments.ADAPTERS["stripe"]
    assert a.verify(gw, body=body, webhook_signature=f"t={t},v1={v1}")
    assert not a.verify(gw, body=body, webhook_signature=f"t={int(t) - 1000},v1={v1}")  # too old


def test_ccavenue_request_round_trip():
    key = "0123456789ABCDEF0123456789ABCDEF"
    gw = _row(code="ccavenue", working_key=key)
    gw.public_config = {"merchant_id": "123456", "access_code": "AVAB00XX"}
    a = payments.ADAPTERS["ccavenue"]
    order = a.create_order(gw, "499.5", "INV-1", redirect_url="https://example.com/back")
    assert order["form"]["access_code"] == "AVAB00XX" and order["form_url"].startswith("https://test.ccavenue.com/")
    assert a.verify(gw, enc_response=order["form"]["encRequest"])["amount"] == "499.50"
    assert a.verify(gw, enc_response="00ff") is None
    assert a.test(gw)[0] is True


def test_amount_validation():
    with pytest.raises(payments.PaymentError):
        payments._minor_units("0")
    assert payments._minor_units("10.005") == 1001
