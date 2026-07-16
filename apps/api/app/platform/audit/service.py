from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.platform.audit.models import AuditLog


def record_audit(
    session: Session,
    *,
    data_class: AuditDataClass,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    organization_id: str | None = None,
    actor_person_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit entry within the caller's transaction."""
    entry = AuditLog(
        organization_id=organization_id,
        actor_person_id=actor_person_id,
        data_class=data_class,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        context=context,
    )
    session.add(entry)
    return entry
