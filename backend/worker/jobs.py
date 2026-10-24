"""Job handlers (BE-27, BE-28). Each runs in its own session; the loop commits on success."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

Payload = dict[str, Any]


@dataclass(frozen=True)
class JobHandler:
    run: Callable[[Session, Payload], None]
    # Called once, in a fresh transaction, when the job fails its last attempt.
    give_up: Callable[[Session, Payload, str], None] | None = None


HANDLERS: dict[str, JobHandler] = {}
