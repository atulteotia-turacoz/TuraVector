"""Invoice reminders and the "waiting too long" highlight on dashboards.

The superadmin sets the platform rule in Billing Settings: on/off, the first reminder N days after an
invoice reaches a stage, then every M days, at most K reminders, and for which stages
(Turacoz approval → approvers; client approval and payment → the workspace's administrators).
A university / organisation may follow that rule ("default"), have no reminders ("off") or its own
days and count ("custom"). The clock restarts whenever the invoice moves to another stage.

`send_due(db)` is safe to run as often as you like (cron, the in-app hourly runner, the button).
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import unfiltered
from app.models import BillingSettings, Invoice, OrgBillingProfile, utcnow
from app.services import billing

log = logging.getLogger("turadome.billing")

OPEN_STAGES = {"pending_turacoz": "remind_turacoz", "pending_client": "remind_client", "awaiting_payment": "remind_payment"}
REMINDER_MODES = {"default": "Platform default", "off": "Off", "custom": "Custom"}


@dataclass(frozen=True)
class Rule:
    after_days: int
    repeat_days: int
    max_count: int


def rule_for(s: BillingSettings, p: OrgBillingProfile | None, status: str) -> Rule | None:
    """The reminder rule for an invoice of this workspace in this stage, or None when there are none."""
    mode = p.reminder_mode if p else "default"
    if mode == "off" or status not in OPEN_STAGES:
        return None
    if mode == "custom":
        return Rule(max(p.reminder_after_days or s.reminder_after_days, 1), max(p.reminder_repeat_days or s.reminder_repeat_days, 1),
                    max(p.reminder_max if p.reminder_max is not None else s.reminder_max, 0))
    if not s.reminders_enabled or not getattr(s, OPEN_STAGES[status]):
        return None
    return Rule(max(s.reminder_after_days, 1), max(s.reminder_repeat_days, 1), max(s.reminder_max, 0))


def since(inv: Invoice) -> datetime.datetime:
    return inv.status_changed_at or inv.created_at


def next_due(inv: Invoice, rule: Rule) -> datetime.datetime | None:
    if inv.reminders_sent >= rule.max_count:
        return None
    if inv.reminders_sent == 0 or inv.last_reminder_at is None:
        return since(inv) + datetime.timedelta(days=rule.after_days)
    return inv.last_reminder_at + datetime.timedelta(days=rule.repeat_days)


def overdue_days(s: BillingSettings, inv: Invoice, now: datetime.datetime | None = None) -> int:
    """Days past the reminder threshold the invoice has been waiting in its stage (0 = not overdue).
    Uses the platform threshold so a workspace with reminders switched off is still highlighted."""
    if inv.status not in OPEN_STAGES:
        return 0
    waited = ((now or utcnow()) - since(inv)).days
    return max(waited - max(s.reminder_after_days, 1) + 1, 0) if waited >= max(s.reminder_after_days, 1) else 0


def _mail(db: Session, inv: Invoice, n: int) -> billing.Mail:
    days = (utcnow() - since(inv)).days
    waited = f"{days} day{'s' if days != 1 else ''}"
    total = billing._fmt(inv.total)
    if inv.status == "pending_turacoz":
        return billing.Mail(billing.approvers_for(db, inv.organisation_id), f"Reminder: invoice {inv.number} for {inv.organisation.name} needs approval",
                            f"Invoice {inv.number} ({total}) has been waiting for Turacoz approval for {waited}.", "invoice_reminder", inv)
    extra = [inv.buyer["email"]] if inv.buyer and inv.buyer.get("email") else []
    if inv.status == "pending_client":
        return billing.Mail(billing.org_admins(db, inv.organisation_id), f"Reminder: please approve invoice {inv.number}",
                            f"Invoice {inv.number} ({total}) has been waiting for your approval for {waited}.\n\n"
                            "Please review it on your TuraVector dashboard.", "invoice_reminder", inv, extra_to=extra)
    return billing.Mail(billing.org_admins(db, inv.organisation_id), f"Reminder: invoice {inv.number} is due for payment",
                        f"Invoice {inv.number} ({total}) was approved {waited} ago and is awaiting payment.\n\n"
                        "You can pay it online from your TuraVector dashboard.", "invoice_reminder", inv, extra_to=extra)


def send_due(db: Session, now: datetime.datetime | None = None) -> list[str]:
    """Send every reminder that is due. Returns the invoice numbers reminded."""
    now = now or utcnow()
    with unfiltered(db):
        # one runner at a time (several workers may run the hourly loop)
        s = db.execute(select(BillingSettings).order_by(BillingSettings.id).limit(1).with_for_update()).scalar_one_or_none()
        if s is None:
            db.rollback()
            return []
        profiles = {p.organisation_id: p for p in db.execute(select(OrgBillingProfile)).scalars()}
        invoices = db.execute(select(Invoice).where(Invoice.status.in_(OPEN_STAGES))).scalars().all()
    mails, done = [], []
    for inv in invoices:
        rule = rule_for(s, profiles.get(inv.organisation_id), inv.status)
        due = next_due(inv, rule) if rule else None
        if due is None or now < due:
            continue
        inv.reminders_sent += 1
        inv.last_reminder_at = now
        billing._event(inv, None, "reminder", f"Reminder {inv.reminders_sent} of {rule.max_count}")
        mails.append(_mail(db, inv, inv.reminders_sent))
        done.append(inv.number)
    billing.notify_in_app(db, mails, None)
    db.commit()
    billing.send(db, mails)
    return done


def settings_payload(s: BillingSettings) -> dict:
    return {"reminders_enabled": bool(s.reminders_enabled), "reminder_after_days": s.reminder_after_days,
            "reminder_repeat_days": s.reminder_repeat_days, "reminder_max": s.reminder_max,
            "remind_turacoz": bool(s.remind_turacoz), "remind_client": bool(s.remind_client),
            "remind_payment": bool(s.remind_payment)}


def apply_settings(s: BillingSettings, data: dict) -> None:
    for k in ("reminders_enabled", "remind_turacoz", "remind_client", "remind_payment"):
        if k in data:
            setattr(s, k, 1 if data[k] else 0)
    for k, lo, hi in (("reminder_after_days", 1, 90), ("reminder_repeat_days", 1, 90), ("reminder_max", 0, 20)):
        if k in data and data[k] not in (None, ""):
            v = int(data[k])
            if not lo <= v <= hi:
                raise billing.BillingError(f"{k.replace('_', ' ').capitalize()} must be between {lo} and {hi}.")
            setattr(s, k, v)


def apply_profile(p: OrgBillingProfile, data: dict) -> None:
    mode = data.get("reminder_mode")
    if mode is None:
        return
    if mode not in REMINDER_MODES:
        raise billing.BillingError("Choose Platform default, Off or Custom reminders.")
    p.reminder_mode = mode
    if mode == "custom":
        for k, lo, hi in (("reminder_after_days", 1, 90), ("reminder_repeat_days", 1, 90), ("reminder_max", 0, 20)):
            v = data.get(k)
            if v in (None, ""):
                raise billing.BillingError("Custom reminders need the first reminder, repeat and maximum.")
            v = int(v)
            if not lo <= v <= hi:
                raise billing.BillingError(f"{k.replace('reminder_', '').replace('_', ' ').capitalize()} must be between {lo} and {hi}.")
            setattr(p, k, v)


# ------------------------------------------------------------------ the in-app runner
def start_runner(interval_seconds: int = 3600) -> None:
    """Check for due reminders every hour on a background thread (in addition to any cron job)."""
    import threading
    import time

    from app.database import SessionLocal

    def loop():
        time.sleep(60)  # let the app finish starting
        while True:
            db = SessionLocal()
            try:
                sent = send_due(db)
                if sent:
                    log.info("invoice reminders sent: %s", ", ".join(sent))
            except Exception as exc:  # noqa: BLE001 — never kill the loop
                log.error("invoice reminder run failed: %s", exc)
                db.rollback()
            finally:
                db.close()
            time.sleep(interval_seconds)

    threading.Thread(target=loop, name="invoice-reminders", daemon=True).start()
