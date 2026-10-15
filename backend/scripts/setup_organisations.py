"""Create the organisation tables and put every existing user into the SMBT workspace.

    cd backend && ./venv/bin/python scripts/setup_organisations.py

Idempotent: tables are created only if missing, SMBT only once, and only users without a
membership get one. Superusers stay platform-wide (no membership). Django tables are not altered.

Also sets up the Turacoz team: a "system" workspace whose members are Turacoz staff (all users of
type Reviewer). They are assigned to SMBT as Reviewers so their review work there carries on.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.core.files import save_bytes  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.models import Organisation, OrgAssignment, OrgMembership, User, utcnow  # noqa: E402
from app.services.org_common import new_join_code  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SMBT = {"name": "SMBT", "slug": "smbt", "kind": "university", "website": "https://smbt.edu.in/"}
TURACOZ = {"name": "Turacoz", "slug": "turacoz", "kind": "system", "website": "https://turacoz.com/"}
# columns added to org_membership after it was first created (our own table, not Django's)
MEMBERSHIP_COLUMNS = {
    "is_poc": "ALTER TABLE org_membership ADD COLUMN is_poc TINYINT(1) NOT NULL DEFAULT 0",
    "designation": "ALTER TABLE org_membership ADD COLUMN designation VARCHAR(150) NOT NULL DEFAULT ''",
}


def create_tables() -> None:
    sql = (HERE / "organisations.sql").read_text()
    with engine.begin() as conn:
        for chunk in sql.split(";"):
            stmt = "\n".join(line for line in chunk.splitlines() if not line.strip().startswith("--")).strip()
            if stmt:
                conn.execute(text(stmt))
        have = set(conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'org_membership'")).scalars())
        for column, ddl in MEMBERSHIP_COLUMNS.items():
            if column not in have:
                conn.execute(text(ddl))


def seed_smbt() -> None:
    db = SessionLocal()
    try:
        org = db.execute(select(Organisation).where(Organisation.slug == SMBT["slug"])).scalar_one_or_none()
        if org is None:
            logo = save_bytes((HERE / "assets" / "smbt-logo.png").read_bytes(), "organisation_logos", "smbt-logo.png")
            org = Organisation(**SMBT, logo=logo, status="active", join_code=new_join_code(db), approved_at=utcnow())
            db.add(org)
            db.flush()
            print(f"Created SMBT organisation (id {org.id}), join code {org.join_code}")
        members = set(db.execute(select(OrgMembership.user_id)).scalars())
        added = 0
        for user in db.execute(select(User).where(User.is_superuser == 0)).scalars():
            if user.id not in members:
                db.add(OrgMembership(organisation_id=org.id, user_id=user.id, role="member", status="active"))
                added += 1
        db.commit()
        print(f"Added {added} users to SMBT")
    finally:
        db.close()


def seed_turacoz() -> None:
    db = SessionLocal()
    try:
        team = db.execute(select(Organisation).where(Organisation.slug == TURACOZ["slug"])).scalar_one_or_none()
        if team is None:
            team = Organisation(**TURACOZ, logo="", status="active", join_code=None, approved_at=utcnow())
            db.add(team)
            db.flush()
            print(f"Created the Turacoz team workspace (id {team.id})")
        smbt = db.execute(select(Organisation).where(Organisation.slug == SMBT["slug"])).scalar_one()
        moved = assigned = 0
        for user in db.execute(select(User).where(User.user_type == "reviewer", User.is_superuser == 0)).scalars():
            m = db.execute(select(OrgMembership).where(OrgMembership.user_id == user.id)).scalar_one_or_none()
            if m is None:
                db.add(OrgMembership(organisation_id=team.id, user_id=user.id, role="member", status="active"))
                moved += 1
            elif m.organisation_id == smbt.id:
                m.organisation_id, m.role, m.is_poc, m.designation = team.id, "member", 0, ""
                moved += 1
            else:
                continue  # already in the team (or deliberately elsewhere)
            if not db.execute(select(OrgAssignment.id).where(
                    OrgAssignment.organisation_id == smbt.id, OrgAssignment.user_id == user.id,
                    OrgAssignment.role == "reviewer")).first():
                db.add(OrgAssignment(organisation_id=smbt.id, user_id=user.id, role="reviewer", designation="Reviewer"))
                assigned += 1
        db.commit()
        print(f"Moved {moved} reviewers to the Turacoz team; {assigned} assigned to SMBT as Reviewers")
    finally:
        db.close()


if __name__ == "__main__":
    create_tables()
    seed_smbt()
    seed_turacoz()
