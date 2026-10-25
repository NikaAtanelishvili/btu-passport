"""Audit log page schemas (BE-53)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditRow(BaseModel):
    id: int
    at: datetime
    actor_email: str | None  # None: the system (worker tick, CLI)
    action: str
    entity: str
    entity_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
