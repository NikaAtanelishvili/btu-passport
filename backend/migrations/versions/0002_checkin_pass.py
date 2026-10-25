"""check-in pass: event_participants.pass_nonce, used once per event

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('event_participants', sa.Column('pass_nonce', sa.Text(), nullable=True))
    op.create_unique_constraint(
        op.f('uq_event_participants_event_id_pass_nonce'),
        'event_participants',
        ['event_id', 'pass_nonce'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f('uq_event_participants_event_id_pass_nonce'), 'event_participants', type_='unique'
    )
    op.drop_column('event_participants', 'pass_nonce')
