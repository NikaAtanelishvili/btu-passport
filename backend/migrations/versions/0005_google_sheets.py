"""google_sheets: sync runs, per-row decisions, source_record_id, SHEET submissions (SH-03)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OUTCOMES = (
    "'PROCESSED', 'DUPLICATE', 'WAITING', 'IGNORED', 'ERROR', 'CHANGED_AFTER_PROCESSING', "
    "'REVOKED_IN_SHEET', 'CREATED', 'UPDATED', 'UNCHANGED', 'CONFLICT'"
)


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, condition)


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('skill_awards', 'legacy_record_id', new_column_name='source_record_id')
    op.execute(
        "ALTER TABLE skill_awards RENAME CONSTRAINT uq_skill_awards_legacy_record_id"
        " TO uq_skill_awards_source_record_id"
    )
    op.add_column('skill_awards', sa.Column('earned_through', sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f('ck_skill_awards_earned_through_length'),
        'skill_awards',
        'length(earned_through) <= 120',
    )
    _replace_check('award_submissions', 'kind', "kind IN ('DIRECT', 'EVENT', 'SEED', 'SHEET')")
    _replace_check(
        'jobs', 'type', "type IN ('ISSUE_VERSION', 'ANCHOR_BATCH', 'SHEET_SYNC')"
    )

    op.create_table(
        'sheet_sync_runs',
        sa.Column('run_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('trigger', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('counts', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.CheckConstraint("trigger IN ('SCHEDULE', 'MANUAL', 'UPLOAD')", name=op.f('ck_sheet_sync_runs_trigger')),
        sa.CheckConstraint("status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED')", name=op.f('ck_sheet_sync_runs_status')),
        sa.PrimaryKeyConstraint('run_id', name=op.f('pk_sheet_sync_runs')),
    )
    op.create_index(
        'sheet_sync_runs_one_active',
        'sheet_sync_runs',
        [sa.text('(true)')],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )
    op.create_table(
        'sheet_records',
        sa.Column('tab', sa.Text(), nullable=False),
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('row_hash', sa.Text(), nullable=False),
        sa.Column('outcome', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('award_id', sa.BigInteger(), nullable=True),
        sa.Column('version_id', sa.BigInteger(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("tab IN ('Students', 'Skills Catalog', 'Verified Skills')", name=op.f('ck_sheet_records_tab')),
        sa.CheckConstraint(f"outcome IN ({OUTCOMES})", name=op.f('ck_sheet_records_outcome')),
        sa.ForeignKeyConstraint(['award_id'], ['skill_awards.award_id'], name=op.f('fk_sheet_records_award_id_skill_awards')),
        sa.ForeignKeyConstraint(['version_id'], ['passport_versions.version_id'], name=op.f('fk_sheet_records_version_id_passport_versions')),
        sa.ForeignKeyConstraint(['run_id'], ['sheet_sync_runs.run_id'], name=op.f('fk_sheet_records_run_id_sheet_sync_runs')),
        sa.PrimaryKeyConstraint('tab', 'key', name=op.f('pk_sheet_records')),
    )
    op.create_index('sheet_records_outcome', 'sheet_records', ['outcome'], unique=False)


def downgrade() -> None:
    """Downgrade schema. Refused while Sheet submissions exist (their kind would break the
    CHECK); queued Sheet sync jobs are dropped."""
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM award_submissions WHERE kind = 'SHEET'")):
        raise RuntimeError("Sheet awards exist; downgrading past 0005 would lose where they came from")
    op.drop_index('sheet_records_outcome', table_name='sheet_records')
    op.drop_table('sheet_records')
    op.drop_index('sheet_sync_runs_one_active', table_name='sheet_sync_runs')
    op.drop_table('sheet_sync_runs')
    op.execute("DELETE FROM jobs WHERE type = 'SHEET_SYNC'")
    _replace_check('jobs', 'type', "type IN ('ISSUE_VERSION', 'ANCHOR_BATCH')")
    _replace_check('award_submissions', 'kind', "kind IN ('DIRECT', 'EVENT', 'SEED')")
    op.drop_constraint(op.f('ck_skill_awards_earned_through_length'), 'skill_awards', type_='check')
    op.drop_column('skill_awards', 'earned_through')
    op.execute(
        "ALTER TABLE skill_awards RENAME CONSTRAINT uq_skill_awards_source_record_id"
        " TO uq_skill_awards_legacy_record_id"
    )
    op.alter_column('skill_awards', 'source_record_id', new_column_name='legacy_record_id')
