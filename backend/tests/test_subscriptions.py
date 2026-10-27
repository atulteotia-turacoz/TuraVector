"""Tools catalogue, plans, sign-up with a plan, paying, renewing and admin-managed subscriptions."""
import datetime
from types import SimpleNamespace

from sqlalchemy import select

from app.core.permissions import can
from app.models import OrgMembership, OrgSubscription, User
from app.services import payments
from app.services import subscriptions as svc

ADMIN_API = "/api/superadmin/subscriptions"


def _plan(client, admin, name, tools, price=0, **extra):
    r = client.post(f"{ADMIN_API}/plans", headers=admin, json={
        "name": name, "price": price, "tool_keys": tools, "billing_period": "monthly", "audience": "all", **extra})
    assert r.status_code == 200, r.text
    return r.json()["plan"]


def _signup(client, username, plan_id=None):
    r = client.post("/api/auth/signup", json={
        "username": username, "email": f"{username}@example.com", "first_name": "Plan", "last_name": "Tester",
        "password": "secret123", "confirm_password": "secret123", "user_type": "student", "privacy_consent": True,
        "account_type": "individual", "plan_id": plan_id})
    assert r.status_code == 200, r.text
    data = r.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def _selection(client, h):
    return client.get("/api/documents/dashboard-selection", headers=h).json()


def test_builtin_tools_listed_and_custom_tool_added(client, login_as):
    admin = login_as("admin")
    keys = [t["key"] for t in client.get(f"{ADMIN_API}/tools", headers=admin).json()["tools"]]
    assert {"content_lab", "other_documents", "ext_research_assistant", "ext_lms", "ext_turagrammar"} <= set(keys)
    r = client.post(f"{ADMIN_API}/tools", headers=admin, json={"name": "Tura Stats", "url": "https://stats.example.com",
                                                                 "features": ["Charts", " "], "icon": "bar-chart"})
    assert r.status_code == 200, r.text
    tool = r.json()["tool"]
    assert tool["key"] == "ext_tura_stats" and tool["features"] == ["Charts"]
    assert client.post(f"{ADMIN_API}/tools", headers=admin, json={"name": "No link"}).status_code == 400
    builtin = next(t for t in client.get(f"{ADMIN_API}/tools", headers=admin).json()["tools"] if t["key"] == "ext_lms")
    assert client.delete(f"{ADMIN_API}/tools/{builtin['id']}", headers=admin).status_code == 400
    # the new tool shows in Application Access too
    cards = client.get("/api/superadmin/app-access", headers=admin).json()["cards"]
    assert any(c["key"] == "ext_tura_stats" for c in cards)


def test_non_superuser_cannot_manage_plans(client, login_as):
    assert client.get(f"{ADMIN_API}/plans", headers=login_as("teacher1")).status_code == 403


def test_signup_with_free_plan_unlocks_tools(client, login_as):
    plan = _plan(client, login_as("admin"), "Free Grammar", ["ext_turagrammar"])
    ctx = client.get("/api/auth/signup-context").json()
    assert any(p["id"] == plan["id"] for p in ctx["plans"]) and ctx["tools"]
    data, h = _signup(client, "plan_free_user", plan["id"])
    assert data["subscription"]["state"] == "active" and data["payment_required"] is False
    sel = _selection(client, h)
    assert "ext_turagrammar" in [a["key"] for a in sel["apps"]]
    assert client.post("/api/documents/external-apps/ext_turagrammar/launch", headers=h).status_code == 200
    assert client.post("/api/documents/external-apps/ext_lms/launch", headers=h).status_code == 403


def test_paid_plan_waits_for_payment_then_activates(client, login_as, db, monkeypatch):
    plan = _plan(client, login_as("admin"), "LMS Pro", ["ext_lms", "other_documents"], price=499)
    data, h = _signup(client, "plan_paid_user", plan["id"])
    assert data["payment_required"] is True
    sel = _selection(client, h)
    assert sel["pending"][0]["plan_name"] == "LMS Pro" and sel["redirect"] is None
    assert "ext_lms" not in [a["key"] for a in sel["apps"]]
    # "from" is the cheapest plan with the tool (a free plan in the catalogue may already include it)
    assert any(t["key"] == "ext_lms" and t["from_price"] <= 499 for t in sel["locked_tools"])

    sub_id = data["subscription"]["id"]
    sub = db.get(OrgSubscription, sub_id)
    sub.gateway, sub.gateway_order_id = "razorpay", "order_test_1"
    db.commit()
    monkeypatch.setattr(payments, "get", lambda db, code: SimpleNamespace(code="razorpay"))
    monkeypatch.setitem(payments.ADAPTERS, "razorpay", SimpleNamespace(verify=lambda gw, **kw: kw["signature"] == "good"))
    bad = client.post(f"/api/subscriptions/{sub_id}/pay/verify", headers=h,
                      json={"order_id": "order_test_1", "payment_id": "pay_1", "signature": "bad"})
    assert bad.status_code == 400
    ok = client.post(f"/api/subscriptions/{sub_id}/pay/verify", headers=h,
                     json={"order_id": "order_test_1", "payment_id": "pay_1", "signature": "good"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["subscription"]["state"] == "active"
    db.refresh(sub)
    assert sub.payment_ref == "pay_1" and sub.ends_at is not None

    sel = _selection(client, h)
    assert "ext_lms" in [a["key"] for a in sel["apps"]] and sel["can_access_other_documents"] is True
    user = db.execute(select(User).where(User.username == "plan_paid_user")).scalar_one()
    assert can(db, user, "can_access_other_documents_dashboard") is True

    # renewing queues the next period after the current one
    r = client.post(f"/api/subscriptions/{sub_id}/renew", headers=h)
    assert r.status_code == 200 and r.json()["payment_required"] is True
    renewal = db.get(OrgSubscription, r.json()["subscription"]["id"])
    svc.activate(db, renewal, payment_ref="pay_2")
    assert renewal.starts_at == sub.ends_at


def test_trial_starts_once(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Research Trial", ["ext_research_assistant"], price=999, trial_days=7)
    data, h = _signup(client, "plan_trial_user", plan["id"])
    sub = data["subscription"]
    assert sub["is_trial"] and sub["state"] == "active" and data["payment_required"] is False
    ends = datetime.datetime.fromisoformat(sub["ends_at"]) - datetime.datetime.fromisoformat(sub["starts_at"])
    assert ends == datetime.timedelta(days=7)
    assert client.get("/api/subscriptions", headers=h).json()["trial_available"] is False
    # a second attempt at the same plan has to be paid
    r = client.post("/api/subscriptions/subscribe", headers=h, json={"plan_id": plan["id"]})
    assert r.status_code == 200 and r.json()["payment_required"] is True


def test_one_trial_per_workspace(client, login_as):
    admin = login_as("admin")
    monthly = _plan(client, admin, "Trial Monthly", ["ext_research_assistant"], price=999, trial_days=14)
    yearly = _plan(client, admin, "Trial Yearly", ["ext_research_assistant"], price=9999, trial_days=14,
                   billing_period="yearly")
    _, h = _signup(client, "plan_trial_stack")
    assert client.get("/api/subscriptions", headers=h).json()["trial_available"] is True
    first = client.post("/api/subscriptions/subscribe", headers=h, json={"plan_id": monthly["id"]}).json()
    assert first["subscription"]["is_trial"] and first["payment_required"] is False
    # another plan with the same tools doesn't start a second trial
    second = client.post("/api/subscriptions/subscribe", headers=h, json={"plan_id": yearly["id"]}).json()
    assert not second["subscription"]["is_trial"] and second["payment_required"] is True


def test_paying_during_trial_starts_after_it(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Trial Then Paid", ["ext_lms"], price=499, trial_days=7)
    data, h = _signup(client, "plan_trial_paid", plan["id"])
    trial = db.get(OrgSubscription, data["subscription"]["id"])
    r = client.post(f"/api/subscriptions/{trial.id}/renew", headers=h)
    assert r.status_code == 200 and r.json()["payment_required"] is True
    paid = db.get(OrgSubscription, r.json()["subscription"]["id"])
    svc.activate(db, paid, payment_ref="pay_trial")
    assert paid.starts_at == trial.ends_at and paid.ends_at == svc.add_months(trial.ends_at, 1)


def test_expired_trial_locks_tools_until_bought_again(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Short Trial", ["ext_lms"], price=499, trial_days=3)
    data, h = _signup(client, "plan_trial_expired", plan["id"])
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]
    trial = db.get(OrgSubscription, data["subscription"]["id"])
    trial.starts_at -= datetime.timedelta(days=5)
    trial.ends_at -= datetime.timedelta(days=5)
    db.commit()
    sel = _selection(client, h)
    assert "ext_lms" not in [a["key"] for a in sel["apps"]]
    assert any(t["key"] == "ext_lms" for t in sel["locked_tools"])
    assert client.get("/api/subscriptions", headers=h).json()["subscriptions"][0]["state"] == "expired"
    r = client.post(f"/api/subscriptions/{trial.id}/renew", headers=h)
    assert r.json()["payment_required"] is True
    again = db.get(OrgSubscription, r.json()["subscription"]["id"])
    svc.activate(db, again, payment_ref="pay_again")
    assert again.starts_at > trial.ends_at  # starts now, not back-dated to the old trial
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]


def test_admin_gives_and_cancels_a_plan(client, login_as, db):
    admin = login_as("admin")
    plan = _plan(client, admin, "Campus LMS", ["ext_lms"], price=10000, audience="organisation")
    _, h = _signup(client, "plan_admin_given")
    user = db.execute(select(User).where(User.username == "plan_admin_given")).scalar_one()
    org_id = db.execute(select(OrgMembership.organisation_id).where(OrgMembership.user_id == user.id)).scalar_one()
    # admins may give any plan, also one offered only to organisations
    end = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    r = client.post(f"{ADMIN_API}/assign", headers=admin, json={"organisation_id": org_id, "plan_id": plan["id"], "ends_at": end})
    assert r.status_code == 200, r.text
    sub_id = r.json()["subscription"]["id"]
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]
    listing = client.get(ADMIN_API, headers=admin, params={"search": "Campus LMS"}).json()
    assert listing["items"][0]["id"] == sub_id
    assert client.post(f"{ADMIN_API}/{sub_id}", headers=admin, json={"action": "cancel"}).status_code == 200
    assert "ext_lms" not in [a["key"] for a in _selection(client, h)["apps"]]


def test_hidden_card_beats_plan(client, login_as, db):
    admin = login_as("admin")
    plan = _plan(client, admin, "Grammar Free 2", ["ext_turagrammar"])
    _, h = _signup(client, "plan_hidden_user", plan["id"])
    user = db.execute(select(User).where(User.username == "plan_hidden_user")).scalar_one()
    client.post("/api/superadmin/app-access/user", headers=admin, json={"user_id": user.id, "card": "ext_turagrammar", "visible": False})
    assert "ext_turagrammar" not in [a["key"] for a in _selection(client, h)["apps"]]


def test_free_tool_for_everyone(client, login_as):
    admin = login_as("admin")
    tool = next(t for t in client.get(f"{ADMIN_API}/tools", headers=admin).json()["tools"] if t["key"] == "ext_research_assistant")
    client.put(f"{ADMIN_API}/tools/{tool['id']}", headers=admin, json={**tool, "is_free": True})
    _, h = _signup(client, "plan_freetool_user")
    assert "ext_research_assistant" in [a["key"] for a in _selection(client, h)["apps"]]


def test_org_member_cannot_buy_plans(client, login_as):
    plan = _plan(client, login_as("admin"), "Member Plan", ["ext_lms"])
    r = client.post("/api/subscriptions/subscribe", headers=login_as("teacher1"), json={"plan_id": plan["id"]})
    assert r.status_code == 403


def test_plan_with_subscribers_cannot_be_deleted(client, login_as):
    admin = login_as("admin")
    plan = _plan(client, admin, "Sticky Plan", ["ext_lms"])
    _signup(client, "plan_sticky_user", plan["id"])
    assert client.delete(f"{ADMIN_API}/plans/{plan['id']}", headers=admin).status_code == 400
    empty = _plan(client, admin, "Empty Plan", ["ext_lms"])
    assert client.delete(f"{ADMIN_API}/plans/{empty['id']}", headers=admin).status_code == 200


def test_public_catalogue_lists_active_plans(client, login_as):
    admin = login_as("admin")
    shown = _plan(client, admin, "Public Campus", ["ext_lms"], price=5000, audience="organisation")
    hidden = _plan(client, admin, "Retired Plan", ["ext_lms"], is_active=False)
    data = client.get("/api/subscriptions/catalogue").json()
    ids = [p["id"] for p in data["plans"]]
    assert shown["id"] in ids and hidden["id"] not in ids and data["tools"]


def test_plans_page_matches_home_cards(client):
    # new users get Content Review without a plan; the Plans page must not show it as locked
    _, h = _signup(client, "plan_page_access")
    tools = {t["key"]: t["has_access"] for t in client.get("/api/subscriptions", headers=h).json()["tools"]}
    sel = _selection(client, h)
    assert tools["content_lab"] is sel["can_access_content_lab"] is True
    assert tools["ext_lms"] is False


def test_builtin_app_link_can_be_changed(client, login_as, monkeypatch):
    from app.services import external_apps_sso
    monkeypatch.setattr(external_apps_sso, "sso_configured", lambda app: False)
    admin = login_as("admin")
    tool = next(t for t in client.get(f"{ADMIN_API}/tools", headers=admin).json()["tools"] if t["key"] == "ext_turagrammar")
    # an empty link falls back to the server setting
    r = client.put(f"{ADMIN_API}/tools/{tool['id']}", headers=admin, json={**tool, "url": ""})
    assert r.json()["tool"]["launch_url"] == tool["default_url"]
    assert client.put(f"{ADMIN_API}/tools/{tool['id']}", headers=admin, json={**tool, "url": "ftp://x"}).status_code == 400
    r = client.put(f"{ADMIN_API}/tools/{tool['id']}", headers=admin, json={**tool, "url": "https://grammar.example.com/"})
    assert r.status_code == 200 and r.json()["tool"]["launch_url"] == "https://grammar.example.com/"
    plan = _plan(client, admin, "Grammar Link", ["ext_turagrammar"])
    _, h = _signup(client, "plan_link_user", plan["id"])
    launch = client.post("/api/documents/external-apps/ext_turagrammar/launch", headers=h).json()
    assert "grammar.example.com" in str(launch)


def _register_org(client, username, name, plan_id=None):
    data = {"first_name": "Uni", "last_name": "Admin", "password": "secret123", "confirm_password": "secret123",
            "privacy_consent": "true", "username": username, "email": f"{username}@example.com",
            "organisation_name": name, "organisation_kind": "university"}
    if plan_id:
        data["plan_id"] = str(plan_id)
    return client.post("/api/auth/signup-organisation", data=data)


def _org_status(client, login_as, db, name, status):
    from app.models import Organisation
    org = db.execute(select(Organisation).where(Organisation.name == name)).scalar_one()
    r = client.post(f"/api/superadmin/organisations/{org.id}/status", json={"status": status}, headers=login_as("admin"))
    assert r.status_code == 200, r.text
    return org


def _org_login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "secret123", "privacy_consent": True})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_university_picks_plan_at_signup_trial_starts_on_approval(client, login_as, db):
    admin = login_as("admin")
    plan = _plan(client, admin, "Campus Trial", ["ext_lms", "content_lab"], price=50000, trial_days=30,
                 audience="organisation", billing_period="yearly")
    individual_only = _plan(client, admin, "Solo Only", ["ext_lms"], audience="individual")
    ctx = client.get("/api/auth/signup-context").json()
    assert plan["id"] in [p["id"] for p in ctx["organisation_plans"]]
    assert individual_only["id"] not in [p["id"] for p in ctx["organisation_plans"]]
    assert _register_org(client, "uni_bad_plan", "Bad Plan Uni", individual_only["id"]).status_code == 400

    r = _register_org(client, "uni_plan_admin", "Plan University", plan["id"])
    assert r.status_code == 200 and "Campus Trial" in r.json()["message"]
    listing = client.get("/api/superadmin/organisations", headers=admin, params={"q": "Plan University"}).json()
    assert listing["organisations"][0]["requested_plan"] == "Campus Trial"

    org = _org_status(client, login_as, db, "Plan University", "active")
    sub = db.execute(select(OrgSubscription).where(OrgSubscription.organisation_id == org.id)).scalar_one()
    assert sub.status == "active" and sub.is_trial and sub.source == "signup"
    assert (sub.ends_at - sub.starts_at).days == 30  # counted from approval
    h = _org_login(client, "uni_plan_admin")
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]
    assert client.get("/api/subscriptions", headers=h).json()["trial_available"] is False


def test_university_paid_plan_waits_for_payment_after_approval(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Campus Paid", ["ext_lms"], price=20000, audience="organisation")
    _register_org(client, "uni_paid_admin", "Paid University", plan["id"])
    org = _org_status(client, login_as, db, "Paid University", "active")
    sub = db.execute(select(OrgSubscription).where(OrgSubscription.organisation_id == org.id)).scalar_one()
    assert sub.status == "pending" and not sub.is_trial
    h = _org_login(client, "uni_paid_admin")
    sel = _selection(client, h)
    assert sel["pending"][0]["plan_name"] == "Campus Paid" and "ext_lms" not in [a["key"] for a in sel["apps"]]


def test_rejected_university_plan_is_cancelled(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Campus Rejected", ["ext_lms"], price=0, audience="organisation")
    _register_org(client, "uni_rej_admin", "Rejected University", plan["id"])
    org = _org_status(client, login_as, db, "Rejected University", "rejected")
    sub = db.execute(select(OrgSubscription).where(OrgSubscription.organisation_id == org.id)).scalar_one()
    assert sub.status == "cancelled"


# ------------------------------------------------------------------ GST, invoices, receipts and cancelling
def _details(client, h, state, code, **extra):
    r = client.put("/api/subscriptions/billing", headers=h, json={
        "legal_name": "Plan Buyer", "address": "1 Test Street", "state": state, "state_code": code, "country": "India", **extra})
    assert r.status_code == 200, r.text
    return r.json()["details"]


def _seller_state(db):
    from app.services import billing
    s = billing.settings_row(db)
    return s.state, s.state_code


def test_gst_added_on_top_and_invoice_issued_when_paid(client, login_as, db, monkeypatch):
    plan = _plan(client, login_as("admin"), "GST Plan", ["ext_lms"], price=1000, tax_percent=18, sac_code="998431")
    data, h = _signup(client, "plan_gst_user", plan["id"])
    sub_id = data["subscription"]["id"]
    assert client.get("/api/subscriptions", headers=h).json()["billing_missing"] == ["country", "state"]

    # paying needs billing details: GST depends on the state
    monkeypatch.setattr(payments, "active", lambda db: SimpleNamespace(code="razorpay", mode="test", currency="INR", public_config={}))
    monkeypatch.setattr(payments, "missing_fields", lambda gw: [])
    orders = []
    monkeypatch.setitem(payments.ADAPTERS, "razorpay", SimpleNamespace(
        create_order=lambda gw, amount, receipt, notes: orders.append(amount) or {"order_id": "order_gst", "amount": amount},
        verify=lambda gw, **kw: True))
    r = client.post(f"/api/subscriptions/{sub_id}/pay", headers=h)
    assert r.status_code == 400 and "billing details" in r.json()["detail"]

    state, code = _seller_state(db)
    _details(client, h, state, code)
    sub = client.get("/api/subscriptions", headers=h).json()["subscriptions"][0]
    assert sub["tax_amount"] == 180 and sub["total"] == 1180
    assert client.post(f"/api/subscriptions/{sub_id}/pay", headers=h).status_code == 200
    assert orders == [svc.Decimal("1180.00")]
    r = client.post(f"/api/subscriptions/{sub_id}/pay/verify", headers=h,
                    json={"order_id": "order_gst", "payment_id": "pay_gst", "signature": "ok"})
    assert r.status_code == 200, r.text

    bill = client.get("/api/subscriptions/billing", headers=h).json()
    assert len(bill["invoices"]) == 1
    row = bill["invoices"][0]
    assert row["status"] == "paid" and row["total"] == 1180 and row["tax"] == 180 and row["plan_name"] == "GST Plan"
    inv = client.get(f"/api/subscriptions/invoices/{row['id']}", headers=h).json()
    assert inv["tax_mode"] == "intra" and inv["cgst"] == 90 and inv["sgst"] == 90 and inv["igst"] == 0
    assert inv["payment_id"] == "pay_gst" and inv["buyer"]["name"] == "Plan Buyer"
    assert inv["lines"][0]["sac_code"] == "998431" and inv["lines"][0]["rate"] == 1000
    assert inv["amount_in_words"]
    # another workspace can't open it
    _, other = _signup(client, "plan_gst_other")
    assert client.get(f"/api/subscriptions/invoices/{row['id']}", headers=other).status_code == 404


def test_other_state_pays_igst(client, login_as, db):
    plan = _plan(client, login_as("admin"), "IGST Plan", ["ext_lms"], price=500)
    data, h = _signup(client, "plan_igst_user", plan["id"])
    _details(client, h, "Some Other State", "99")
    sub = db.get(OrgSubscription, data["subscription"]["id"])
    db.refresh(sub)
    assert sub.tax_mode == "inter" and sub.tax_amount == 90
    svc.activate(db, sub, payment_ref="pay_igst")
    inv = client.get(f"/api/subscriptions/invoices/{sub.invoice_id}", headers=h).json()
    assert inv["igst"] == 90 and inv["cgst"] == 0 and inv["total"] == 590


def test_admin_mark_paid_issues_invoice_but_given_plan_does_not(client, login_as, db):
    admin = login_as("admin")
    plan = _plan(client, admin, "Offline Plan", ["ext_lms"], price=300)
    data, h = _signup(client, "plan_offline_user", plan["id"])
    sub_id = data["subscription"]["id"]
    assert client.post(f"{ADMIN_API}/{sub_id}", headers=admin, json={"action": "activate", "notes": "NEFT 123"}).status_code == 200
    assert db.get(OrgSubscription, sub_id).invoice_id is not None
    user = db.execute(select(User).where(User.username == "plan_offline_user")).scalar_one()
    org_id = db.execute(select(OrgMembership.organisation_id).where(OrgMembership.user_id == user.id)).scalar_one()
    given = client.post(f"{ADMIN_API}/assign", headers=admin, json={"organisation_id": org_id, "plan_id": plan["id"]}).json()
    assert db.get(OrgSubscription, given["subscription"]["id"]).invoice_id is None
    assert len(client.get("/api/subscriptions/billing", headers=h).json()["invoices"]) == 1


def test_cancel_keeps_tools_until_period_end_and_can_be_undone(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Cancel Plan", ["ext_lms"], price=400)
    data, h = _signup(client, "plan_cancel_user", plan["id"])
    sub = db.get(OrgSubscription, data["subscription"]["id"])
    svc.activate(db, sub, payment_ref="pay_cancel")
    db.commit()
    r = client.post(f"/api/subscriptions/{sub.id}/cancel", headers=h)
    assert r.status_code == 200 and "keep its tools until" in r.json()["message"]
    payload = r.json()["subscription"]
    assert payload["state"] == "active" and payload["cancelled_at"] and payload["can_cancel"] is False
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]  # still usable until it ends
    assert client.post(f"/api/subscriptions/{sub.id}/cancel", headers=h).status_code == 400
    assert client.post(f"/api/subscriptions/{sub.id}/resume", headers=h).status_code == 200
    db.refresh(sub)
    assert sub.cancelled_at is None
    # once the period is over, a cancelled plan stops like any other
    client.post(f"/api/subscriptions/{sub.id}/cancel", headers=h)
    sub.starts_at -= datetime.timedelta(days=40)
    sub.ends_at -= datetime.timedelta(days=40)
    db.commit()
    assert "ext_lms" not in [a["key"] for a in _selection(client, h)["apps"]]


def test_cancelling_a_paid_renewal_notes_the_refund(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Renewal Plan", ["ext_lms"], price=200)
    data, h = _signup(client, "plan_refund_user", plan["id"])
    first = db.get(OrgSubscription, data["subscription"]["id"])
    svc.activate(db, first, payment_ref="pay_r1")
    renewal = db.get(OrgSubscription, client.post(f"/api/subscriptions/{first.id}/renew", headers=h).json()["subscription"]["id"])
    svc.activate(db, renewal, payment_ref="pay_r2")
    db.commit()
    assert svc.state_of(renewal) == "scheduled"
    r = client.post(f"/api/subscriptions/{renewal.id}/cancel", headers=h)
    assert r.status_code == 200 and "refund" in r.json()["message"]
    db.refresh(renewal)
    assert renewal.status == "cancelled" and "refund" in renewal.notes and "pay_r2" in renewal.notes
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]  # the first period still runs


def test_free_lifetime_plan_cancels_at_once(client, login_as, db):
    plan = _plan(client, login_as("admin"), "Free Forever", ["ext_lms"], billing_period="lifetime")
    data, h = _signup(client, "plan_free_cancel", plan["id"])
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]
    r = client.post(f"/api/subscriptions/{data['subscription']['id']}/cancel", headers=h)
    assert r.status_code == 200
    assert "ext_lms" not in [a["key"] for a in _selection(client, h)["apps"]]


def test_tools_added_to_a_plan_reach_its_subscribers(client, login_as, db):
    admin = login_as("admin")
    plan = _plan(client, admin, "Growing Plan", ["content_lab"], billing_period="lifetime")
    data, h = _signup(client, "plan_growing_user", plan["id"])
    assert "ext_lms" not in [a["key"] for a in _selection(client, h)["apps"]]
    body = {"name": "Growing Plan", "price": 0, "billing_period": "lifetime", "audience": "all",
            "tool_keys": ["other_documents", "ext_lms"]}
    r = client.put(f"{ADMIN_API}/plans/{plan['id']}", headers=admin, json=body)
    assert r.status_code == 200 and "1 subscriber got the added tools" in r.json()["message"]
    sub = db.get(OrgSubscription, data["subscription"]["id"])
    db.refresh(sub)
    # added tools arrive at once; the removed one stays with the existing subscriber
    assert sub.tool_keys == ["content_lab", "other_documents", "ext_lms"]
    assert "ext_lms" in [a["key"] for a in _selection(client, h)["apps"]]
