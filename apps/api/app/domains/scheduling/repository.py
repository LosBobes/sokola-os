from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.common.enums import RecordStatus
from app.domains.groups.models import Group
from app.domains.scheduling.enums import SessionStatus
from app.domains.scheduling.models import Session


def get_org_group(db: DbSession, organization_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.organization_id == organization_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def find_conflicts(
    db: DbSession,
    organization_id: str,
    group_id: str,
    starts_at: dt.datetime,
    ends_at: dt.datetime,
    *,
    exclude_session_id: str | None = None,
) -> list[Session]:
    """Scheduled sessions for the same group whose time range overlaps the draft.
    Half-open overlap: existing.starts < new.ends AND existing.ends > new.starts."""
    stmt = select(Session).where(
        Session.organization_id == organization_id,
        Session.group_id == group_id,
        Session.status == SessionStatus.SCHEDULED,
        Session.starts_at < ends_at,
        Session.ends_at > starts_at,
    )
    if exclude_session_id is not None:
        stmt = stmt.where(Session.id != exclude_session_id)
    return list(db.execute(stmt.order_by(Session.starts_at)).scalars().all())


def get_org_session(db: DbSession, organization_id: str, session_id: str) -> Session | None:
    stmt = select(Session).where(
        Session.id == session_id,
        Session.organization_id == organization_id,
        Session.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_sessions_in_range(
    db: DbSession, organization_id: str, start: dt.datetime, end: dt.datetime
) -> list[Session]:
    stmt = (
        select(Session)
        .where(
            Session.organization_id == organization_id,
            Session.record_status == RecordStatus.ACTIVE,
            Session.starts_at >= start,
            Session.starts_at < end,
        )
        .order_by(Session.starts_at)
    )
    return list(db.execute(stmt).scalars().all())
