"""Audit log writes (BE-21). Rows are append-only (trigger audit_log_append_only).

Started in M2 for `cli bootstrap`; BE-21 (M4) adds the request-actor helpers.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    entity: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
) -> None:
    """Add an audit row in the caller's transaction. A NULL actor means the system."""
    db.add(
        AuditLog(
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
    )
