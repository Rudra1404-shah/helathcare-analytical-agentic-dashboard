"""Structured audit logging for clinical record access.

``CLAUDE.md`` requires every read or write on a clinical record to emit an audit
event. Events are emitted as structured log records on the ``unhp.audit``
logger rather than written to MongoDB: the platform's collection catalogue is
fixed at twelve, and an audit trail belongs in append-only log infrastructure
where the application itself cannot rewrite it.

Every event answers the same four questions -- who, what, which record, and
when -- so a downstream log pipeline can index them uniformly.
"""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any

from beanie import PydanticObjectId

from src.domain.enums import UserRole
from src.domain.models.base import utcnow

__all__ = ["AuditAction", "audit_event", "audit_logger"]

audit_logger = logging.getLogger("unhp.audit")


class AuditAction(StrEnum):
    """What the actor did to the record."""

    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    EXPORT = "EXPORT"


def audit_event(
    action: AuditAction,
    collection: str,
    actor_id: PydanticObjectId | None = None,
    actor_role: UserRole | None = None,
    document_id: PydanticObjectId | None = None,
    hospital_id: PydanticObjectId | None = None,
    detail: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Emit one audit event and return it.

    The event is returned as well as logged so tests can assert on its contents
    without parsing log output.

    Args:
        action: What happened.
        collection: The collection touched, e.g. ``"patient_cases"``.
        actor_id: The acting account, or ``None`` for an anonymous attempt.
        actor_role: The acting role, when known.
        document_id: The affected document, when a single one is involved.
        hospital_id: Hospital the record belongs to, for tenant-scoped filtering.
        detail: Short human-readable note, e.g. ``"discharged"``.
        occurred_at: Override the timestamp; defaults to now.

    Returns:
        The emitted event as a plain dictionary.
    """
    event: dict[str, Any] = {
        "action": action.value,
        "collection": collection,
        "actor_id": str(actor_id) if actor_id is not None else None,
        "actor_role": actor_role.value if actor_role is not None else None,
        "document_id": str(document_id) if document_id is not None else None,
        "hospital_id": str(hospital_id) if hospital_id is not None else None,
        "detail": detail,
        "occurred_at": (occurred_at or utcnow()).isoformat(),
    }
    audit_logger.info("audit", extra={"audit": event})
    return event
