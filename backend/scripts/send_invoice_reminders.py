"""Send the invoice reminders that are due (Billing Settings → Reminders, and each workspace's own setting).

    cd backend && ./venv/bin/python scripts/send_invoice_reminders.py

The app also checks every hour (INVOICE_REMINDERS_AUTORUN); use this from cron when that is switched off.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.services import billing_reminders  # noqa: E402

if __name__ == "__main__":
    db = SessionLocal()
    sent = billing_reminders.send_due(db)
    print(f"{len(sent)} reminder(s) sent" + (f": {', '.join(sent)}" if sent else ""))
