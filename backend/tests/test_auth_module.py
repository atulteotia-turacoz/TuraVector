"""Auth module: signup, password reset, profile, timezone, help/support, notifications page,
dashboard selection, other-documents profile. All writes are rolled back by conftest."""
import datetime

from sqlalchemy import select

from app.core.security import check_password, make_password
from app.models import (
    ContactQuery, DocumentFeedback, DocumentNotification, DocumentSupport, EmailLog, LoginLog, OTPVerification,
    User, UserConsent, utcnow,
)

SIGNUP = {
    "username": "pytest_new_user", "email": "pytest_new_user@Example.COM", "first_name": "Py", "last_name": "Test",
    "password": "secret123", "confirm_password": "secret123", "user_type": "researcher", "phone": "123",
    "address": "Somewhere", "privacy_consent": True,
}


def _user(db, username):
    return db.execute(select(User).where(User.username == username)).scalar_one()


# ------------------------------------------------------------------ signup
def test_signup_context(client):
    data = client.get("/api/auth/signup-context").json()
    # only self-service account types; privileged ones (teacher/reviewer/manager) are given by an admin
    assert [t["value"] for t in data["default_user_types"]] == ["student", "researcher"]
    assert {t["code"] for t in data["user_types"]} <= {"student", "researcher"}
    assert [k["value"] for k in data["organisation_kinds"]] == ["university", "organisation"]


def test_signup_validation_messages(client):
    def err(**over):
        r = client.post("/api/auth/signup", json={**SIGNUP, **over})
        assert r.status_code == 400
        return r.json()["error"]

    assert err(first_name="") == "All required fields must be filled."
    assert err(privacy_consent=False).startswith("You must consent")
    assert err(confirm_password="other123") == "Passwords do not match."
    assert err(password="short", confirm_password="short") == "Password must be at least 8 characters long."
    assert err(username="admin") == "Username already exists."
    assert err(email="atul.teotia@turacoz.com") == "Email already registered."


def test_signup_creates_user_consent_and_log(client, db):
    r = client.post("/api/auth/signup", json=SIGNUP)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "Account created successfully! Welcome to TuraVector."
    assert body["access_token"]
    u = _user(db, "pytest_new_user")
    assert u.email == "pytest_new_user@example.com"  # domain normalised like Django
    assert u.user_type == "researcher" and u.phone == "123" and u.address == "Somewhere"
    assert u.is_active == 1 and u.is_staff == 0 and u.timezone == "UTC"
    assert check_password("secret123", u.password)
    assert db.query(UserConsent).filter(UserConsent.user_id == u.id).count() == 1
    assert db.query(LoginLog).filter(LoginLog.user_id == u.id, LoginLog.status == "success").count() == 1
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["username"] == "pytest_new_user"


# ------------------------------------------------------------------ password reset
def test_forgot_password_flow(client, db, sent_emails):
    assert client.post("/api/auth/forgot-password", json={}).json() == {"error": "Email is required"}
    r = client.post("/api/auth/forgot-password", json={"email": "nobody@nowhere.invalid"})
    assert r.status_code == 404 and r.json()["error"] == "User with this email does not exist"

    r = client.post("/api/auth/forgot-password", json={"email": "teacher1@example.com"})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "OTP sent to your email. Please check your inbox and spam folder."
    assert sent_emails[-1]["subject"] == "Password Reset OTP - TuraVector"
    otp = db.execute(select(OTPVerification).where(OTPVerification.email == "teacher1@example.com")
                     .order_by(OTPVerification.id.desc())).scalars().first()
    assert otp.otp_code in sent_emails[-1]["message"]
    log = db.execute(select(EmailLog).order_by(EmailLog.id.desc())).scalars().first()
    assert log.email_type == "password_reset" and log.status == "sent"

    bad = client.post("/api/auth/verify-otp", json={"email": "teacher1@example.com", "otp": "xxxxxx", "new_password": "n"})
    assert bad.status_code == 400 and bad.json()["error"] == "Invalid OTP"

    ok = client.post("/api/auth/verify-otp", json={"email": "teacher1@example.com", "otp": otp.otp_code, "new_password": "brandnew1"})
    assert ok.json() == {"message": "Password updated successfully"}
    db.refresh(otp)
    assert otp.is_used == 1
    assert check_password("brandnew1", _user(db, "teacher1").password)


def test_verify_otp_expired(client, db):
    db.add(OTPVerification(email="teacher1@example.com", otp_code="999111", is_used=0,
                           expires_at=utcnow() - datetime.timedelta(minutes=1)))
    db.commit()
    r = client.post("/api/auth/verify-otp", json={"email": "teacher1@example.com", "otp": "999111", "new_password": "x"})
    assert r.status_code == 400 and r.json()["error"] == "OTP has expired"
    assert client.post("/api/auth/verify-otp", json={"email": "a"}).json()["error"] == "All fields are required"


def test_contact_form(client, db, sent_emails):
    assert client.post("/api/auth/contact", json={"name": "x"}).status_code == 400
    r = client.post("/api/auth/contact", json={"name": "N", "email": "n@e.com", "subject": "Hi", "message": "M"})
    assert r.json()["message"] == "Thank you for your message. We will get back to you soon."
    assert db.query(ContactQuery).filter(ContactQuery.email == "n@e.com").count() == 1
    assert sent_emails[-1]["subject"] == "New Contact Form Submission: Hi" and sent_emails[-1]["to"] == "admin@turadome.com"


def test_test_email(client, sent_emails):
    r = client.post("/api/auth/test-email", json={"email": "x@example.com"})
    assert r.status_code == 200 and r.json()["method"] == "advanced_email_system"
    assert sent_emails[-1]["subject"] == "TuraVector Email Test"


# ------------------------------------------------------------------ profile
def test_update_profile_keeps_missing_fields(client, db, login_as):
    h = login_as("teacher1")
    before = _user(db, "teacher1")
    addr = before.address
    r = client.post("/api/auth/update-profile", json={"first_name": "Changed", "phone": "555"}, headers=h)
    assert r.json() == {"message": "Profile updated successfully"}
    u = _user(db, "teacher1")
    assert u.first_name == "Changed" and u.phone == "555" and u.address == addr
    assert client.post("/api/auth/update-profile", json={}).status_code == 401


def test_change_password(client, db, login_as):
    u = _user(db, "teacher1")
    u.password = make_password("oldpass123", iterations=1000)
    db.commit()
    h = login_as("teacher1")
    url = "/api/auth/change-password"
    assert client.post(url, json={}, headers=h).json()["error"] == "Current password and new password are required"
    assert client.post(url, json={"current_password": "nope", "new_password": "whatever1"}, headers=h).json()["error"] == "Current password is incorrect"
    assert client.post(url, json={"current_password": "oldpass123", "new_password": "short"}, headers=h).json()["error"] == "New password must be at least 8 characters long"
    assert client.post(url, json={"current_password": "oldpass123", "new_password": "newpass123"}, headers=h).json() == {"message": "Password changed successfully"}
    assert check_password("newpass123", _user(db, "teacher1").password)


def test_profile_api(client, login_as):
    data = client.get("/api/auth/profile", headers=login_as("reviewer1")).json()
    assert data["username"] == "reviewer1" and data["date_joined"].endswith("+00:00")


# ------------------------------------------------------------------ timezones
def test_timezones(client, db, login_as):
    common = client.get("/api/auth/timezones").json()["timezones"]
    assert common[1] == {"value": "Asia/Kolkata", "label": "India Standard Time (IST)", "offset": "+05:30"}
    assert isinstance(client.get("/api/auth/timezones?all=true").json()["timezones"], list)
    assert client.post("/api/auth/set-timezone", json={}).json()["error"] == "Timezone is required"
    assert client.post("/api/auth/set-timezone", json={"timezone": "Mars/Base"}).json()["error"] == "Invalid timezone"
    anon = client.post("/api/auth/set-timezone", json={"timezone": "Europe/Paris"})
    assert anon.json() == {"message": "Timezone updated successfully", "timezone": "Europe/Paris"}
    r = client.post("/api/auth/set-timezone", json={"timezone": "Asia/Tokyo"}, headers=login_as("teacher1"))
    assert r.status_code == 200 and _user(db, "teacher1").timezone == "Asia/Tokyo"
    assert client.post("/api/auth/detect-timezone", json={"timezone": "UTC"}).json()["message"] == "Timezone detected successfully"
    assert client.get("/api/auth/timezone-info").json() == {"current_timezone": "Asia/Kolkata", "timezone_offset": "+05:30"}


def test_timezone_stats_staff_only(client, login_as):
    assert client.get("/api/auth/admin/timezone-stats", headers=login_as("teacher1")).status_code == 403
    data = client.get("/api/auth/admin/timezone-stats", headers=login_as("admin")).json()
    assert data["total_users"] >= sum(1 for _ in data["stats"]) and data["unique_timezones"] == len(data["stats"])


# ------------------------------------------------------------------ documents-side pages
def test_dashboard_selection(client, login_as):
    data = client.get("/api/documents/dashboard-selection", headers=login_as("admin")).json()
    assert data["can_access_content_lab"] and data["can_access_other_documents"] and data["redirect"] is None
    assert client.get("/api/documents/dashboard-selection").status_code == 401


def test_notifications_page_marks_seen(client, db, login_as):
    teacher = _user(db, "teacher1")
    admin = _user(db, "admin")
    db.add(DocumentNotification(document_type="document_upload", document_id=1, description="pytest", receiver_id=teacher.id,
                                sender_id=admin.id, sent_for="x", is_seen=0))
    db.commit()
    data = client.get("/api/documents/notifications", headers=login_as("teacher1")).json()
    assert data["unread_count"] >= 1 and data["total"] == len(data["notifications"])
    assert all(n["is_seen"] for n in data["notifications"])
    assert db.query(DocumentNotification).filter(DocumentNotification.receiver_id == teacher.id,
                                                 DocumentNotification.is_seen == 0).count() == 0


def test_support_request(client, db, login_as, sent_emails):
    h = login_as("teacher1")
    assert client.post("/api/documents/support", json={"subject": "x"}, headers=h).json()["error"] == "All fields are required"
    r = client.post("/api/documents/support", json={"subject": "Help pytest", "message": "Broken"}, headers=h)
    assert r.json() == {"message": "Support request submitted successfully"}
    assert sent_emails[-1]["subject"] == "Support Request: Help pytest" and sent_emails[-1]["to"] == "atul.teotia@turacoz.com"
    reqs = client.get("/api/documents/help-support", headers=h).json()["support_requests"]
    assert reqs[0]["subject"] == "Help pytest" and reqs[0]["is_resolved"] is False
    assert db.query(DocumentSupport).filter(DocumentSupport.subject == "Help pytest").count() == 1


def test_feedback(client, db, login_as):
    h = login_as("teacher1")
    assert client.post("/api/documents/feedback", json={"project_id": 1}, headers=h).status_code == 400
    r = client.post("/api/documents/feedback", json={"project_id": 1, "rating": "4", "feedback": "pytest fb"}, headers=h)
    assert r.json() == {"message": "Feedback submitted successfully"}
    assert db.query(DocumentFeedback).filter(DocumentFeedback.feedback_text == "pytest fb").one().rating == 4


def test_other_documents_profile(client, login_as):
    data = client.get("/api/documents/other-documents/profile", headers=login_as("admin")).json()
    for k in ("owned_projects_count", "collaborated_projects_count", "total_documents", "total_versions",
              "pending_milestones", "in_progress_milestones", "completed_milestones"):
        assert isinstance(data[k], int)
    assert len(data["recent_projects"]) <= 5
