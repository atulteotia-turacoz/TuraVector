"""Hand-written parts of the Django admin port that cannot be derived from metadata.

* `STR`          — each model's `__str__` (used for object_repr, FK labels, delete summaries)
* `COMPUTED`     — ModelAdmin methods used in list_display / readonly_fields
                   (file_actions, is_valid_status, content_preview, is_expired)
* `ACTIONS`      — the custom admin actions defined in the admin.py files
* `before_save`  — model.save() overrides and ModelAdmin.save_model() hooks

Rows are plain dicts keyed by DB column (Core `select(table)` mappings). `c` is the
request context (`superadmin_core.Ctx`) giving cached access to related rows.
"""
from __future__ import annotations

import datetime
import random
import smtplib
import ssl
import string
from typing import TYPE_CHECKING, Any, Callable

import pytz
from sqlalchemy import select, update

from app.models import Base, utcnow
from app.services.superadmin_registry import MODELS

if TYPE_CHECKING:  # pragma: no cover
    from app.services.superadmin_core import Ctx


def _t(name: str):
    return Base.metadata.tables[name]


def _aware(dt: datetime.datetime | None) -> str:
    """str() of an aware UTC datetime, as Django's f-strings render model datetimes."""
    if dt is None:
        return "None"
    return str(dt.replace(tzinfo=pytz.UTC))


def _full(u: dict | None) -> str:
    """AbstractUser.get_full_name()"""
    if not u:
        return ""
    return f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip()


def _uname(u: dict | None) -> str:
    return (u or {}).get("username", "None")


def _display(c: "Ctx", label: str, field: str, value: Any) -> str:
    return c.choice_label(label, field, value)


# ---------------------------------------------------------------------------- __str__
def _str_user(c, r):
    return f"{r['first_name']} {r['last_name']} ({r['username']})"


def _str_userconsent(c, r):
    u = c.rel("authentication.UserConsent", r, "user")
    status = "Given" if r["consent_given"] else "Withdrawn"
    return f"{_uname(u)} - {_display(c, 'authentication.UserConsent', 'consent_type', r['consent_type'])} - {status}"


def _str_loginlog(c, r):
    u = c.rel("authentication.LoginLog", r, "user")
    who = u["username"] if u else r["username_attempted"]
    return f"{who} - {r['status']} at {_aware(r['login_time'])}"


def _str_auth_permission(c, r):
    ct = c.fetch("contenttypes.ContentType", r["content_type_id"])
    return f"{c.content_type_str(ct)} | {r['name']}"


def _str_documentsharing(c, r):
    L = "documents.DocumentSharing"
    u = c.rel(L, r, "user")
    if r.get("document_version_id"):
        dv = c.rel(L, r, "document_version")
        return f"{(dv or {}).get('version_number')} shared with {_full(u)} ({r['permission_level']})"
    if r.get("document_id"):
        d = c.rel(L, r, "document")
        return f"{(d or {}).get('document_name')} shared with {_full(u)} ({r['permission_level']})"
    return f"Document shared with {_full(u)} ({r['permission_level']})"


def _num(v):
    if v is None:
        return "None"
    return str(float(v)) if not isinstance(v, int) else str(v)


STR: dict[str, Callable[["Ctx", dict], str]] = {
    "auth.Group": lambda c, r: r["name"],
    "auth.Permission": _str_auth_permission,
    "contenttypes.ContentType": lambda c, r: c.content_type_str(r),
    "authentication.UserType": lambda c, r: r["name"],
    "authentication.User": _str_user,
    "authentication.OTPVerification": lambda c, r: f"OTP for {r['email']}: {r['otp_code']}",
    "authentication.SMTPConfig": lambda c, r: f"SMTP Config: {r['host']}:{r['port']}",
    "authentication.ContactQuery": lambda c, r: f"Query from {r['name']}: {r['subject']}",
    "authentication.LoginLog": _str_loginlog,
    "authentication.UserConsent": _str_userconsent,
    "authentication.Permission": lambda c, r: (
        f"{_display(c, 'authentication.Permission', 'module', r['module'])} - "
        f"{_display(c, 'authentication.Permission', 'action', r['action'])}"),
    "authentication.Role": lambda c, r: r["name"],
    "authentication.RolePermission": lambda c, r: (
        f"{(c.rel('authentication.RolePermission', r, 'role') or {}).get('name')} - "
        f"{(c.rel('authentication.RolePermission', r, 'permission') or {}).get('name')}"),
    "authentication.UserRole": lambda c, r: (
        f"{_uname(c.rel('authentication.UserRole', r, 'user'))} - "
        f"{(c.rel('authentication.UserRole', r, 'role') or {}).get('name')}"),
    "authentication.UserPermission": lambda c, r: (
        f"{_uname(c.rel('authentication.UserPermission', r, 'user'))} - "
        f"{'Granted' if r['is_granted'] else 'Denied'}: "
        f"{(c.rel('authentication.UserPermission', r, 'permission') or {}).get('name')}"),
    "documents.DocumentType": lambda c, r: r["name"],
    "documents.Brand": lambda c, r: r["name"],
    "documents.Country": lambda c, r: r["name"],
    "documents.TherapeuticArea": lambda c, r: r["name"],
    "documents.CourseCategory": lambda c, r: r["name"],
    "documents.Project": lambda c, r: r["name"],
    "documents.EnrollUser": lambda c, r: (
        f"{_uname(c.rel('documents.EnrollUser', r, 'user'))} - "
        f"{(c.rel('documents.EnrollUser', r, 'course') or {}).get('name')} ({r['role']})"),
    "documents.Document": lambda c, r: f"{r['document_number']}: {r['document_name']}",
    "documents.DocumentVersion": lambda c, r: f"{r['version_number']}: {r['file_title_name']}",
    "documents.Feedback": lambda c, r: (
        f"Feedback from {_uname(c.rel('documents.Feedback', r, 'user'))} for "
        f"{(c.rel('documents.Feedback', r, 'project') or {}).get('name')}"),
    "documents.Support": lambda c, r: f"Support request from {_uname(c.rel('documents.Support', r, 'user'))}: {r['subject']}",
    "documents.Notification": lambda c, r: (
        f"Notification for {_uname(c.rel('documents.Notification', r, 'receiver'))}: {(r['description'] or '')[:50]}"),
    "documents.DocumentAnnotation": lambda c, r: (
        f"{r['annotation_type']} on {(c.rel('documents.DocumentAnnotation', r, 'document_version') or {}).get('file_title_name')}"
        f" by {_uname(c.rel('documents.DocumentAnnotation', r, 'user'))}"),
    "documents.AnnotationActivity": lambda c, r: (
        f"{_full(c.rel('documents.AnnotationActivity', r, 'user'))} {r['action']} {r['annotation_count']} annotation(s) on "
        f"{(c.rel('documents.AnnotationActivity', r, 'document_version') or {}).get('file_title_name')}"),
    "documents.DocumentReference": lambda c, r: (
        f"{(c.rel('documents.DocumentReference', r, 'document') or {}).get('document_number')} -> "
        f"{(c.rel('documents.DocumentReference', r, 'reference') or {}).get('reference_number')}"),
    "documents.DocumentVersionReference": lambda c, r: (
        f"{(c.rel('documents.DocumentVersionReference', r, 'document_version') or {}).get('version_number')} -> "
        f"{(c.rel('documents.DocumentVersionReference', r, 'reference') or {}).get('reference_number')}"),
    "documents.EmailLog": lambda c, r: f"{r['email_type']} to {r['recipient_email']} - {r['status']}",
    "documents.SMTPSettings": lambda c, r: f"SMTP: {r['host']}:{r['port']} ({'Active' if r['is_active'] else 'Inactive'})",
    "documents.ResearchProject": lambda c, r: r["title"],
    "documents.ResearchProjectCollaborator": lambda c, r: (
        f"{_full(c.rel('documents.ResearchProjectCollaborator', r, 'user'))} - "
        f"{(c.rel('documents.ResearchProjectCollaborator', r, 'project') or {}).get('title')} ({r['role']})"),
    "documents.ResearchProjectTask": lambda c, r: f"{(c.rel('documents.ResearchProjectTask', r, 'project') or {}).get('title')} - {r['title']}",
    "documents.ProjectAuthor": lambda c, r: (
        f"{r['name']} ({r['author_type']}) - {(c.rel('documents.ProjectAuthor', r, 'project') or {}).get('title')}"),
    "documents.ResearchProjectDocument": lambda c, r: (
        f"{(c.rel('documents.ResearchProjectDocument', r, 'project') or {}).get('title')} - {r['title']}"),
    "documents.ProjectMilestone": lambda c, r: (
        f"{(c.rel('documents.ProjectMilestone', r, 'project') or {}).get('title')} - {r['milestone_name']}"),
    "documents.Journal": lambda c, r: r["name"],
    "documents.UserJournalSelection": lambda c, r: (
        f"{_full(c.rel('documents.UserJournalSelection', r, 'user'))} - "
        f"{(c.rel('documents.UserJournalSelection', r, 'journal') or {}).get('name')}"),
    "documents.DocumentSharing": _str_documentsharing,
    "documents.DocumentVersionSharing": lambda c, r: (
        f"{(c.rel('documents.DocumentVersionSharing', r, 'document_version') or {}).get('version_number')} shared with "
        f"{_full(c.rel('documents.DocumentVersionSharing', r, 'user'))}"),
    "documents.AIConversation": lambda c, r: (
        f"{_full(c.rel('documents.AIConversation', r, 'user'))} - {r['title'] or 'Chat ' + str(r['id'])}"),
    "documents.AIMessage": lambda c, r: f"{r['role']}: {(r['content'] or '')[:50]}...",
    "documents.AIDataset": lambda c, r: (
        f"{r['original_filename']} - {c.str('documents.AIConversation', c.rel('documents.AIDataset', r, 'conversation'))}"),
    "library.ReferenceDocument": lambda c, r: f"{r['reference_number']}: {r['document_name']}",
    "library.ReferenceZip": lambda c, r: f"{r['reference_zip_number']}: {r['file_title_name']}",
    "library.AssignedReviewer": lambda c, r: (
        f"Review by {_uname(c.rel('library.AssignedReviewer', r, 'user'))} for "
        f"{(c.rel('library.AssignedReviewer', r, 'document_version') or {}).get('version_number')}"),
    "library.DocumentHistory": lambda c, r: (
        f"{(c.rel('library.DocumentHistory', r, 'document') or {}).get('document_number')}: {r['action_type']} by "
        f"{_uname(c.rel('library.DocumentHistory', r, 'user'))}"),
    "library.TemporaryPassword": lambda c, r: f"Temporary password for {_uname(c.rel('library.TemporaryPassword', r, 'user'))}",
    "plagiarism.PlagiarismCheck": lambda c, r: (
        f"{r['title']} - {_uname(c.rel('plagiarism.PlagiarismCheck', r, 'user'))} - {r['status']}"),
    "plagiarism.PlagiarismFile": lambda c, r: f"{r['original_filename']} - {r['file_type']}",
    "plagiarism.PlagiarismResult": lambda c, r: (
        f"Result for {(c.rel('plagiarism.PlagiarismResult', r, 'plagiarism_check') or {}).get('title')}"),
    "plagiarism.PlagiarismSource": lambda c, r: f"Source {r['source_number']}: {r['title']} ({_num(r['similarity_percentage'])}%)",
    "plagiarism.PlagiarismPageMatch": lambda c, r: f"Page {r['page_number']} ({_num(r['similarity_percentage'])}% similarity)",
    "plagiarism.PageSourceMatch": lambda c, r: (
        f"Page {(c.rel('plagiarism.PageSourceMatch', r, 'page_match') or {}).get('page_number')} - "
        f"{(c.rel('plagiarism.PageSourceMatch', r, 'source') or {}).get('title')} ({_num(r['similarity_percentage'])}%)"),
}


# ---------------------------------------------------------------------------- computed columns
def _user_has_role(c: "Ctx", user_id: int, role_name: str) -> bool:
    """User.has_role(): UserRole(user, role__name, role__is_active) exists."""
    ur, role = _t("authentication_userrole"), _t("authentication_role")
    return c.db.execute(
        select(ur.c.id).join(role, role.c.id == ur.c.role_id)
        .where(ur.c.user_id == user_id, role.c.name == role_name, role.c.is_active == 1).limit(1)
    ).first() is not None


def sharing_is_valid(c: "Ctx", r: dict) -> bool:
    """DocumentSharing.is_valid()"""
    if not r["is_active"]:
        return False
    if r["expires_at"] and utcnow() > r["expires_at"]:
        return False
    if r.get("role_required_id"):
        role = c.fetch("authentication.Role", r["role_required_id"])
        return _user_has_role(c, r["user_id"], role["name"]) if role else False
    return True


def temp_password_is_expired(c: "Ctx", r: dict) -> bool:
    return r["expires_at"] is not None and utcnow() > r["expires_at"]


# (label, name) -> {label (short_description), kind, fn}
COMPUTED: dict[tuple[str, str], dict] = {
    ("documents.DocumentVersion", "file_actions"): {
        "label": "File Actions", "kind": "link",
        "fn": lambda c, r: {"text": "Change File", "route": "change_file"},
    },
    ("documents.DocumentSharing", "is_valid_status"): {
        "label": "Is Valid", "kind": "boolean", "fn": sharing_is_valid,
    },
    ("documents.AIMessage", "content_preview"): {
        "label": "Content Preview", "kind": "text",
        "fn": lambda c, r: (r["content"][:100] + "...") if len(r["content"] or "") > 100 else r["content"],
    },
    ("library.TemporaryPassword", "is_expired"): {
        "label": "Expired", "kind": "boolean", "fn": temp_password_is_expired,
    },
    ("authentication.User", "workspace"): {
        "label": "Workspace", "kind": "text", "fn": lambda c, r: user_workspace(c, r),
    },
}


def user_workspace(c: "Ctx", r: dict) -> str:
    """Which university / organisation the user belongs to, or that they are Turacoz / platform staff.
    Loaded once per request for the whole page."""
    names = c._cache.get(("__user_workspaces__", None))
    if names is None:
        m, o = _t("org_membership"), _t("org_organisation")
        names = {uid: (f"{name} (system user)" if kind == "system" else name)
                 for uid, name, kind in c.db.execute(select(m.c.user_id, o.c.name, o.c.kind).join(o, o.c.id == m.c.organisation_id)).all()}
        c._cache[("__user_workspaces__", None)] = names
    if r.get("is_superuser"):
        return "Platform superadmin"
    return names.get(r["id"], "No workspace")


# Show the workspace on the users list, right after the e-mail address.
_user_list = MODELS["authentication.User"]["admin"]["list_display"]
if "workspace" not in _user_list:
    _user_list.insert(_user_list.index("email") + 1, "workspace")


# ---------------------------------------------------------------------------- save() / save_model()
def _year() -> int:
    return datetime.datetime.now(pytz.timezone("UTC")).year


def before_save(c: "Ctx", label: str, values: dict, is_add: bool, existing: dict | None) -> None:
    """Mutate the column->value dict that is about to be written (model.save + ModelAdmin.save_model)."""
    merged = {**(existing or {}), **values}
    # --- model.save() overrides
    if label == "authentication.UserType" and merged.get("code"):
        values["code"] = merged["code"].lower().replace(" ", "_")
    elif label == "authentication.OTPVerification":
        if not merged.get("otp_code"):
            values["otp_code"] = "".join(random.choices(string.digits, k=6))
        if not merged.get("expires_at"):
            values["expires_at"] = utcnow() + datetime.timedelta(minutes=15)
    elif label == "documents.Document" and not merged.get("document_number"):
        values["document_number"] = f"DOC-{_year()}-{merged.get('id') or 'NEW'}"
    elif label == "documents.DocumentVersion" and not merged.get("version_number"):
        doc = c.fetch("documents.Document", merged.get("document_id"))
        values["version_number"] = f"{(doc or {}).get('document_number')}-V-{merged.get('version_count')}"
    elif label == "library.ReferenceDocument" and not merged.get("reference_number"):
        values["reference_number"] = f"REF-{_year()}-{merged.get('id') or 'NEW'}"
    elif label == "library.ReferenceZip" and not merged.get("reference_zip_number"):
        values["reference_zip_number"] = f"REF-ZIP-{_year()}-{merged.get('id') or 'NEW'}"

    # --- ModelAdmin.save_model overrides
    uid = c.user.id
    if label == "documents.SMTPSettings":
        if is_add:
            values["created_by_id"] = uid
        values["updated_by_id"] = uid
    elif label == "documents.Journal" and is_add:
        values["created_by_id"] = uid
    elif label in ("documents.DocumentSharing", "documents.DocumentVersionSharing") and is_add:
        values["shared_by_id"] = uid
    elif label in ("documents.DocumentReference", "documents.DocumentVersionReference") and is_add:
        values["linked_by_id"] = uid


# ---------------------------------------------------------------------------- admin actions
Messages = list[tuple[str, str]]  # (level, text)


def _update(c: "Ctx", table: str, pks: list, **vals) -> int:
    """QuerySet.update(): no auto_now, no save() — exactly like Django."""
    if not pks:
        return 0
    t = _t(table)
    res = c.db.execute(update(t).where(t.c.id.in_(pks)).values(**vals))
    c.db.commit()
    return res.rowcount if res.rowcount is not None and res.rowcount >= 0 else len(pks)


def _stage_actions(table: str, noun: str) -> dict:
    def make(status: int, word: str):
        def run(c: "Ctx", pks: list) -> Messages:
            n = _update(c, table, pks, stage_status=status)
            return [("info", f"{n} {noun}(s) marked as {word}.")]
        return run
    return {
        "mark_as_under_review": make(1, "Under Review"),
        "mark_as_approved": make(2, "Approved"),
        "mark_as_draft_under_revision": make(3, "Draft Under Revision"),
        "mark_as_draft": make(0, "Draft"),
    }


def retry_failed_emails(c: "Ctx", pks: list) -> Messages:
    import app.core.email as email_mod  # module attribute so tests can stub deliver()

    t = _t("documents_emaillog")
    rows = c.db.execute(select(t).where(t.c.id.in_(pks), t.c.status.in_(["failed", "error"]))).mappings().all()
    retried = 0
    for r in rows:
        if (r["retry_count"] or 0) < 3 and r["status"] in ("failed", "error"):  # can_retry()
            try:
                email_mod.deliver(c.db, r["subject"], r["message_content"], r["from_email"], r["recipient_email"])
                c.db.execute(update(t).where(t.c.id == r["id"]).values(status="sent", sent_at=utcnow(), updated_at=utcnow()))
                retried += 1
            except Exception as exc:  # noqa: BLE001 — mark_as_failed
                c.db.execute(update(t).where(t.c.id == r["id"]).values(
                    status="failed", error_message=str(exc), retry_count=(r["retry_count"] or 0) + 1, updated_at=utcnow()))
            c.db.commit()
    return [("info", f"Successfully retried {retried} emails.")]


def smtp_test_connection(r: dict) -> tuple[bool, str]:
    """SMTPSettings.test_connection() — Django SMTP EmailBackend semantics."""
    try:
        if r["use_ssl"]:
            server = smtplib.SMTP_SSL(r["host"], r["port"], timeout=30, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(r["host"], r["port"], timeout=30)
            if r["use_tls"]:
                server.starttls(context=ssl.create_default_context())
        try:
            if r["username"] and r["password"]:
                server.login(r["username"], r["password"])
            if r["test_email"]:
                from email.mime.text import MIMEText
                msg = MIMEText(f"""This is a test email from TuraVector Document Management System.

SMTP Configuration Details:
- Host: {r['host']}
- Port: {r['port']}
- Username: {r['username']}
- TLS: {bool(r['use_tls'])}
- SSL: {bool(r['use_ssl'])}

If you received this email, your SMTP configuration is working correctly.

Test performed at: {_aware(utcnow())}""")
                msg["Subject"] = "SMTP Configuration Test"
                msg["From"] = r["from_email"]
                msg["To"] = r["test_email"]
                server.send_message(msg)
                result = f"Test email sent successfully to {r['test_email']}"
            else:
                result = "SMTP connection test successful (no email sent)"
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
        return True, result
    except Exception as exc:  # noqa: BLE001
        return False, f"SMTP test failed: {exc}"


def test_smtp_configurations(c: "Ctx", pks: list) -> Messages:
    t = _t("documents_smtpsettings")
    tested = failed = 0
    for r in c.db.execute(select(t).where(t.c.id.in_(pks))).mappings().all():
        ok, message = smtp_test_connection(dict(r))
        c.db.execute(update(t).where(t.c.id == r["id"]).values(
            is_tested=1 if ok else 0, last_tested=utcnow(), test_result=message, updated_at=utcnow()))
        c.db.commit()
        if ok:
            tested += 1
        else:
            failed += 1
    out: Messages = []
    if tested > 0:
        out.append(("info", f"Successfully tested {tested} SMTP configurations."))
    if failed > 0:
        out.append(("warning", f"{failed} SMTP configurations failed testing."))
    return out


def extend_expiry_30_days(c: "Ctx", pks: list) -> Messages:
    t = _t("documents_documentsharing")
    extended = 0
    for r in c.db.execute(select(t).where(t.c.id.in_(pks))).mappings().all():
        new = (r["expires_at"] + datetime.timedelta(days=30)) if r["expires_at"] else utcnow() + datetime.timedelta(days=30)
        c.db.execute(update(t).where(t.c.id == r["id"]).values(expires_at=new))
        extended += 1
    c.db.commit()
    return [("info", f"{extended} share(s) extended by 30 days.")]


def delete_expired_passwords(c: "Ctx", pks: list) -> Messages:
    from sqlalchemy import delete
    t = _t("library_temporarypassword")
    cond = (t.c.id.in_(pks)) & (t.c.expires_at < utcnow())
    expired = len(c.db.execute(select(t.c.id).where(cond)).all())
    c.db.execute(delete(t).where(cond))
    c.db.commit()
    return [("info", f"{expired} expired password(s) deleted.")]


def _simple(table: str, msg: str, **vals):
    def run(c: "Ctx", pks: list) -> Messages:
        n = _update(c, table, pks, **vals)
        return [("info", msg.format(n=n))]
    return run


ACTIONS: dict[str, dict[str, Callable[["Ctx", list], Messages]]] = {
    "documents.Document": _stage_actions("documents_document", "document"),
    "documents.DocumentVersion": _stage_actions("documents_documentversion", "document version"),
    "documents.EmailLog": {"retry_failed_emails": retry_failed_emails},
    "documents.SMTPSettings": {"test_smtp_configurations": test_smtp_configurations},
    "documents.DocumentSharing": {
        "activate_shares": _simple("documents_documentsharing", "{n} share(s) activated.", is_active=1),
        "deactivate_shares": _simple("documents_documentsharing", "{n} share(s) deactivated.", is_active=0),
        "extend_expiry_30_days": extend_expiry_30_days,
    },
    "library.AssignedReviewer": {
        "mark_as_completed": _simple("library_assignedreviewer", "{n} review(s) marked as completed.", is_completed=1),
        "mark_as_active": _simple("library_assignedreviewer", "{n} review(s) marked as active.", is_active=1),
        "mark_as_inactive": _simple("library_assignedreviewer", "{n} review(s) marked as inactive.", is_active=0),
    },
    "library.TemporaryPassword": {"delete_expired_passwords": delete_expired_passwords},
}
