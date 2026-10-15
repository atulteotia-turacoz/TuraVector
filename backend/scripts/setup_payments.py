"""Create the payment_gateway table and the Stripe / Razorpay / CCAvenue rows (Razorpay active).

    cd backend && ./venv/bin/python scripts/setup_payments.py

Idempotent: the table is created only if missing and existing rows (and their keys) are kept.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.services import payments  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def create_table() -> None:
    sql = (HERE / "payments.sql").read_text()
    with engine.begin() as conn:
        for chunk in sql.split(";"):
            stmt = "\n".join(line for line in chunk.splitlines() if not line.strip().startswith("--")).strip()
            if stmt:
                conn.execute(text(stmt))


def seed() -> None:
    db = SessionLocal()
    try:
        rows = payments.ensure_rows(db)
        if not any(r.is_active for r in rows):
            razorpay = next(r for r in rows if r.code == "razorpay")
            razorpay.is_active, razorpay.is_enabled = 1, 1  # Razorpay is the gateway in use; keys are added in the admin
        db.commit()
        print("Gateways:", ", ".join(f"{r.name}{' (active)' if r.is_active else ''}" for r in rows))
    finally:
        db.close()


if __name__ == "__main__":
    create_table()
    seed()
