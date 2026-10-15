"""Invoice every monthly-billed workspace for last month's waiting requests.

    cd backend && ./venv/bin/python scripts/run_monthly_invoices.py            # last month
    cd backend && ./venv/bin/python scripts/run_monthly_invoices.py 2026-09    # a given month

Schedule it on the 1st of every month (cron: `0 6 1 * *`). Safe to re-run: requests already invoiced
are skipped.
"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.services import billing  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) > 1:
        month = datetime.date.fromisoformat(f"{sys.argv[1]}-01")
    else:
        month = (datetime.datetime.now(billing.IST).date().replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    db = SessionLocal()
    made = []
    for org in billing.monthly_orgs(db):
        if billing.profile_missing(billing.profile_of(db, org.id)):
            print(f"skipped {org.name}: billing profile incomplete")
            continue
        inv = billing.bill_month(db, org, month, None)
        if inv:
            mails = billing.invoice_created_mails(db, inv)
            billing.notify_in_app(db, mails, None)
            db.commit()
            billing.send(db, mails)
            made.append(f"{inv.number} {org.name} INR {inv.total}")
    print(f"{month:%B %Y}: {len(made)} invoice(s)")
    for line in made:
        print(" ", line)
