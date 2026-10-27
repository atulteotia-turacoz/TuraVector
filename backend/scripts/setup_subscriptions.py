"""Create the tools / plans / subscriptions tables and add the built-in tools to the catalogue.

    cd backend && ./venv/bin/python scripts/setup_subscriptions.py

Idempotent: tables are created only if missing and existing tools are kept. A starter set of plans
is added only while there are no plans at all; edit, replace or delete them in the admin (Plans & Pricing).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.models import SubscriptionPlan, SubscriptionPlanTool  # noqa: E402
from app.services import external_apps  # noqa: E402
from app.services.subscriptions import utcnow  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent

ALL_TOOLS = ["content_lab", "other_documents", "ext_research_assistant", "ext_turagrammar", "ext_lms"]
# name, description, price (INR), billing period, trial days, audience, featured, tools
STARTER_PLANS = [
    ("TuraGrammar", "Grammar and language checks for your writing.", 299, "monthly", 7, "individual", False,
     ["ext_turagrammar"]),
    ("Researcher Basic", "Manage, review and approve your documents.", 499, "monthly", 7, "individual", False,
     ["content_lab", "other_documents"]),
    ("Researcher Pro", "Every research tool for one researcher.", 1499, "monthly", 14, "individual", True,
     ["content_lab", "other_documents", "ext_research_assistant", "ext_turagrammar"]),
    ("Researcher Pro Yearly", "Researcher Pro billed yearly — two months free.", 14990, "yearly", 14, "individual", False,
     ["content_lab", "other_documents", "ext_research_assistant", "ext_turagrammar"]),
    ("Institution", "All tools, including Tura LMS, for every member of your university or organisation.", 99999,
     "yearly", 30, "organisation", True, ALL_TOOLS),
]


# GST, invoices and cancelling, added after the first release of scripts/subscriptions.sql
LATER_COLUMNS = {
    "subscription_plan": {
        "tax_percent": "DECIMAL(5,2) NOT NULL DEFAULT 18.00 AFTER sort_order",
        "sac_code": "VARCHAR(20) NOT NULL DEFAULT '' AFTER tax_percent",
    },
    "org_subscription": {
        "tax_percent": "DECIMAL(5,2) NOT NULL DEFAULT 0 AFTER notes",
        "tax_amount": "DECIMAL(12,2) NOT NULL DEFAULT 0 AFTER tax_percent",
        "tax_mode": "VARCHAR(10) NOT NULL DEFAULT '' AFTER tax_amount",
        "invoice_id": "BIGINT NULL AFTER tax_mode",
        "cancelled_at": "DATETIME(6) NULL AFTER invoice_id",
    },
}


def create_tables() -> None:
    sql = (HERE / "subscriptions.sql").read_text()
    with engine.begin() as conn:
        for chunk in sql.split(";"):
            stmt = "\n".join(line for line in chunk.splitlines() if not line.strip().startswith("--")).strip()
            if stmt:
                conn.execute(text(stmt))
        for table, cols in LATER_COLUMNS.items():
            present = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = :t"),
                {"t": table})}
            for col, ddl in cols.items():
                if col not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def seed() -> None:
    db = SessionLocal()
    try:
        tools = external_apps.ensure_tools(db)
        db.commit()
        print("Tools:", ", ".join(t.name for t in tools))
        if db.execute(select(func.count()).select_from(SubscriptionPlan)).scalar():
            return
        by_key = {t.key: t for t in tools}
        now = utcnow()
        for order, (name, desc, price, period, trial, audience, featured, keys) in enumerate(STARTER_PLANS, 1):
            plan = SubscriptionPlan(name=name, description=desc, price=price, currency="INR", billing_period=period,
                                    trial_days=trial, audience=audience, is_featured=int(featured), is_active=1,
                                    sort_order=order * 10, created_at=now, updated_at=now)
            plan.plan_tools = [SubscriptionPlanTool(tool_id=by_key[k].id) for k in keys if k in by_key]
            db.add(plan)
        db.commit()
        print("Starter plans:", ", ".join(p[0] for p in STARTER_PLANS))
    finally:
        db.close()


if __name__ == "__main__":
    create_tables()
    seed()
