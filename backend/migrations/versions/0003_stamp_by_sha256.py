"""stamps are keyed by their SHA-256: CHECK on skill_categories (BE-51)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# Same text as app.models.catalog.STAMP_BY_SHA256, frozen here.
STAMP_BY_SHA256 = """
    (stamp_sha256 IS NULL AND stamp_key IS NULL AND stamp_mime IS NULL)
    OR (stamp_sha256 ~ '^[0-9a-f]{64}$' AND (
        (stamp_mime = 'image/svg+xml' AND stamp_key = 'stamps/' || stamp_sha256 || '.svg')
        OR (stamp_mime = 'image/png' AND stamp_key = 'stamps/' || stamp_sha256 || '.png')))
"""

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        op.f("ck_skill_categories_stamp_by_sha256"), "skill_categories", STAMP_BY_SHA256
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("ck_skill_categories_stamp_by_sha256"), "skill_categories", type_="check"
    )
