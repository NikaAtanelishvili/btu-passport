"""`python -m cli demo-reset --yes` (M10): back to a clean demo from inside any deployment
(Railway shell, a prod container), where `make demo-reset`'s docker and psql steps aren't
available. Same result: the Sheet back to the seed data (cli sheets-reset), an empty schema,
migrations, seed, the accounts (demo-users when ENV=demo, else bootstrap --dev-users) and
issue-pending. Object storage and the chain are kept: new versions get new codes, so new
Merkle roots. A running worker may fail while the tables are gone; it is restarted."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def main(*, yes: bool) -> None:
    if not yes:
        sys.exit(
            "demo-reset deletes every row in the database and every Sheet row below the seed "
            "data. Run it again with --yes."
        )
    from cli import bootstrap, demo_users, seed, sheets
    from cli.__main__ import issue_pending

    s = get_settings()
    if s.google_sheets_id:
        sheets.reset()  # exits, changing nothing, when the seed rows moved
    else:
        print("demo-reset: GOOGLE_SHEETS_ID is empty; no Sheet to reset")

    engine = create_engine(s.database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()
    print("demo-reset: database emptied")

    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    seed.main()
    if s.env == "demo":
        demo_users.main()
    else:
        bootstrap.main(dev_users=True)
    issue_pending()
    print("demo-reset: done; the worker renders and anchors the seed passports")
