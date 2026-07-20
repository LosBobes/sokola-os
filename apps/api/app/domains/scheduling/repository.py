from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.common.enums import RecordStatus
from app.domains.groups.models import Group
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment
from app.domains.scheduling.enums import SessionStatus
from app.domains.scheduling.models import Session, SessionSeries


def get_org_group(db: DbSession, organization_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.organization_id == organization_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def is_org_trainer(db: DbSession, organization_id: str, person_id: str) -> bool:
    """A trainer is a person holding an ACTIVE TRAINER role in this organization.
    Used to keep series/trainer assignment tenant-scoped."""
    stmt = select(RoleAssignment.id).where(
        RoleAssignment.person_id == person_id,
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.role_code == RoleCode.TRAINER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


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


# --- Recurring series -------------------------------------------------------


def get_org_series(
    db: DbSession, organization_id: str, series_id: str
) -> SessionSeries | None:
    stmt = select(SessionSeries).where(
        SessionSeries.id == series_id,
        SessionSeries.organization_id == organization_id,
        SessionSeries.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_series(db: DbSession, organization_id: str) -> list[SessionSeries]:
    stmt = (
        select(SessionSeries)
        .where(
            SessionSeries.organization_id == organization_id,
            SessionSeries.record_status == RecordStatus.ACTIVE,
        )
        .order_by(SessionSeries.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def existing_series_start_times(db: DbSession, series_id: str) -> set[dt.datetime]:
    """Every start instant already materialized for a series (any status). The
    natural key ``(series_id, starts_at)`` makes generation idempotent."""
    stmt = select(Session.starts_at).where(Session.series_id == series_id)
    return set(db.execute(stmt).scalars().all())


def list_series_sessions(
    db: DbSession,
    organization_id: str,
    series_id: str,
    *,
    status: SessionStatus | None = None,
    starts_from: dt.datetime | None = None,
) -> list[Session]:
    stmt = select(Session).where(
        Session.organization_id == organization_id,
        Session.series_id == series_id,
        Session.record_status == RecordStatus.ACTIVE,
    )
    if status is not None:
        stmt = stmt.where(Session.status == status)
    if starts_from is not None:
        stmt = stmt.where(Session.starts_at >= starts_from)
    return list(db.execute(stmt.order_by(Session.starts_at)).scalars().all())
