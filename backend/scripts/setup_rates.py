"""Create the rate card tables (standard services and university / organisation rate cards).

    cd backend && ./venv/bin/python scripts/setup_rates.py

Idempotent: tables are created only if missing. No services are added — they are entered in the admin.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent

if __name__ == "__main__":
    sql = (HERE / "rates.sql").read_text()
    with engine.begin() as conn:
        for chunk in sql.split(";"):
            stmt = "\n".join(line for line in chunk.splitlines() if not line.strip().startswith("--")).strip()
            if stmt:
                conn.execute(text(stmt))
    print("Rate card tables are ready.")
