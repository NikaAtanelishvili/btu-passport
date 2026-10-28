"""notify_version_jobs: job type NOTIFY_VERSION for the student email (SH-10)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _types(types: str) -> None:
    op.drop_constraint(op.f("ck_jobs_type"), "jobs", type_="check")
    op.create_check_constraint(op.f("ck_jobs_type"), "jobs", f"type IN ({types})")


def upgrade() -> None:
    """Upgrade schema."""
    _types("'ISSUE_VERSION', 'ANCHOR_BATCH', 'SHEET_SYNC', 'NOTIFY_VERSION'")


def downgrade() -> None:
    """Downgrade schema. Notices not sent yet are dropped."""
    op.execute("DELETE FROM jobs WHERE type = 'NOTIFY_VERSION'")
    _types("'ISSUE_VERSION', 'ANCHOR_BATCH', 'SHEET_SYNC'")
