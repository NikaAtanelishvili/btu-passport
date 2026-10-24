"""Audit log writes (BE-21). Rows are append-only (trigger audit_log_append_only).

Action names: student.create, student.update, award.direct, version.retry, event.create,
event.update, event.open, event.close, event.reopen, event.delete, event.complete,
participant.add, participant.remove, skill.*, category.*, role.grant, role.revoke, bootstrap.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models import AuditLog

if TYPE_CHECKING:
    from app.auth.deps import Principal


def record(
    db: Session,
    actor: "Principal | None",
    action: str,
    entity: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Add an audit row in the caller's transaction. `actor` None means the system."""
    db.add(
        AuditLog(
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
            actor_user_id=actor.user.user_id if actor else None,
            actor_email=actor.user.email if actor else None,
        )
    )
