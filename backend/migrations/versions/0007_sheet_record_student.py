"""sheet_record_student: sheet_records.student_id, a WAITING row's student for the admin link

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. WAITING rows are decided again on every sync, so they fill it then."""
    op.add_column("sheet_records", sa.Column("student_id", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_sheet_records_student_id_students"),
        "sheet_records",
        "students",
        ["student_id"],
        ["student_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_sheet_records_student_id_students"), "sheet_records", type_="foreignkey"
    )
    op.drop_column("sheet_records", "student_id")
