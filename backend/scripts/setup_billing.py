"""Create the billing tables, add the GST columns to rate_service and the settings row.

    cd backend && ./venv/bin/python scripts/setup_billing.py

Idempotent. Run scripts/setup_rates.py first.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent

# columns added to our own rate_service table (scripts/rates.sql)
RATE_SERVICE_COLUMNS = {
    "sac_code": "ALTER TABLE rate_service ADD COLUMN sac_code VARCHAR(20) NOT NULL DEFAULT '' AFTER unit",
    "tax_overseas": "ALTER TABLE rate_service ADD COLUMN tax_overseas TINYINT(1) NOT NULL DEFAULT 0 AFTER tax_percent",
}

# reminder settings and tracking, added after the first release of scripts/billing.sql
LATER_COLUMNS = {
    "billing_settings": {
        "reminders_enabled": "TINYINT(1) NOT NULL DEFAULT 1",
        "reminder_after_days": "INT NOT NULL DEFAULT 3",
        "reminder_repeat_days": "INT NOT NULL DEFAULT 3",
        "reminder_max": "INT NOT NULL DEFAULT 3",
        "remind_turacoz": "TINYINT(1) NOT NULL DEFAULT 1",
        "remind_client": "TINYINT(1) NOT NULL DEFAULT 1",
        "remind_payment": "TINYINT(1) NOT NULL DEFAULT 1",
    },
    "org_billing_profile": {
        "reminder_mode": "VARCHAR(10) NOT NULL DEFAULT 'default'",  # default | off | custom
        "reminder_after_days": "INT NULL",
        "reminder_repeat_days": "INT NULL",
        "reminder_max": "INT NULL",
    },
    "invoice": {
        "status_changed_at": "DATETIME(6) NULL",
        "reminders_sent": "INT NOT NULL DEFAULT 0",
        "last_reminder_at": "DATETIME(6) NULL",
    },
}

if __name__ == "__main__":
    sql = (HERE / "billing.sql").read_text()
    with engine.begin() as conn:
        for chunk in sql.split(";"):
            stmt = "\n".join(line for line in chunk.splitlines() if not line.strip().startswith("--")).strip()
            if stmt:
                conn.execute(text(stmt))
        have = set(conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() "
            "AND table_name = 'rate_service'")).scalars())
        for col, ddl in RATE_SERVICE_COLUMNS.items():
            if col not in have:
                conn.execute(text(ddl))
        for table, cols in LATER_COLUMNS.items():
            present = set(conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() "
                "AND table_name = :t"), {"t": table}).scalars())
            for col, ddl in cols.items():
                if col not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        conn.execute(text("UPDATE invoice SET status_changed_at = updated_at WHERE status_changed_at IS NULL"))
        if not conn.execute(text("SELECT COUNT(*) FROM billing_settings")).scalar():
            conn.execute(text("INSERT INTO billing_settings (company_name, state, state_code, country, invoice_prefix, "
                              "updated_at) VALUES ('Turacoz Healthcare Solutions', 'Delhi', '07', 'India', 'TC', NOW(6))"))
    print("Billing tables are ready.")
