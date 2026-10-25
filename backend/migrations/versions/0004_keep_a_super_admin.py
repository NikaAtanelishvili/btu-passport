"""keep_a_super_admin: the last SUPER_ADMIN can't be revoked or demoted (BE-52)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Locking every SUPER_ADMIN row first makes two concurrent revocations wait for each other,
# so they can't both see "someone else is still a super admin" and leave none.
TRIGGER = """
CREATE FUNCTION keep_a_super_admin() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.role = 'SUPER_ADMIN' AND (TG_OP = 'DELETE' OR NEW.role <> 'SUPER_ADMIN') THEN
        PERFORM 1 FROM user_roles WHERE role = 'SUPER_ADMIN' ORDER BY email FOR UPDATE;
        IF NOT EXISTS (SELECT 1 FROM user_roles
                       WHERE role = 'SUPER_ADMIN' AND email <> OLD.email) THEN
            RAISE EXCEPTION 'the last super admin can''t be revoked or demoted';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER keep_a_super_admin BEFORE UPDATE OR DELETE ON user_roles
    FOR EACH ROW EXECUTE FUNCTION keep_a_super_admin();
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(TRIGGER)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS keep_a_super_admin ON user_roles")
    op.execute("DROP FUNCTION IF EXISTS keep_a_super_admin()")
