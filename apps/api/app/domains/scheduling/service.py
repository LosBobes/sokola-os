from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as DbSession

from app.common.enums import AuditDataClass
from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.domains.scheduling import repository
from app.domains.scheduling.enums import (
    SessionEditScope,
    SessionSeriesFrequency,
    SessionStatus,
)
from app.domains.scheduling.models import Session, SessionSeries
from app.domains.scheduling.schemas import (
    ConflictCheckResponse,
    SeriesGenerateRequest,
    SeriesGenerateResult,
    SessionCancel,
    SessionDraft,
    SessionEdit,
    SessionSeriesCreate,
    SessionSeriesSummary,
    SessionSummary,
    SkippedOccurrence,
)
from app.platform import clock
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def check_conflicts(
    db: DbSession, context: RequestContext, draft: SessionDraft
) -> ConflictCheckResponse:
    if repository.get_org_group(db, context.organization_id, draft.group_id) is None:
        raise NotFoundError("Grupa nije pronađena.")
    conflicts = repository.find_conflicts(
        db, context.organization_id, draft.group_id, draft.starts_at, draft.ends_at
    )
    return ConflictCheckResponse(
        has_conflict=bool(conflicts),
        conflicts=[SessionSummary.model_validate(s) for s in conflicts],
    )


def create_session(
    db: DbSession,
    context: RequestContext,
    draft: SessionDraft,
    idempotency_key: str | None,
) -> SessionSummary:
    """Journey 1. Idempotent one-off session create. A true time conflict for the
    same group is refused (409), the client previewed it and keeps its draft."""
    params = {
        "group_id": draft.group_id,
        "starts_at": draft.starts_at.isoformat(),
        "ends_at": draft.ends_at.isoformat(),
        "title": draft.title,
        "trainer_person_id": draft.trainer_person_id,
        "location_id": draft.location_id,
    }
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "scheduling.create_session", idempotency_key, params
        )
        if guard.replay is not None:
            return SessionSummary.model_validate(guard.replay["body"])

    group = repository.get_org_group(db, context.organization_id, draft.group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")

    # The group is the default source for who leads the session and where it is
    # held. An explicitly-sent field always wins (including an explicit null,
    # which is how the caller says "deliberately unassigned"); an omitted field
    # inherits the group's default.
    trainer_person_id = (
        draft.trainer_person_id
        if "trainer_person_id" in draft.model_fields_set
        else group.default_trainer_person_id
    )
    location_id = (
        draft.location_id
        if "location_id" in draft.model_fields_set
        else group.default_location_id
    )
    _require_trainer_in_org(db, context, trainer_person_id)
    _require_location_in_org(db, context, location_id)

    conflicts = repository.find_conflicts(
        db, context.organization_id, draft.group_id, draft.starts_at, draft.ends_at
    )
    if conflicts:
        raise ConflictError(
            "Termin se preklapa sa postojećim terminom grupe.",
            details={
                "code": "SESSION_CONFLICT",
                "conflicts": [
                    SessionSummary.model_validate(s).model_dump(mode="json") for s in conflicts
                ],
            },
        )

    session = Session(
        organization_id=context.organization_id,
        group_id=draft.group_id,
        trainer_person_id=trainer_person_id,
        location_id=location_id,
        title=draft.title,
        starts_at=draft.starts_at,
        ends_at=draft.ends_at,
    )
    db.add(session)
    db.flush()

    result = SessionSummary.model_validate(session)
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="session.created",
        entity_type="session",
        entity_id=session.id,
        summary=f"Kreiran termin {session.starts_at.isoformat()}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="session.created",
        payload={"session_id": session.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(db, guard, status=201, body=result.model_dump(mode="json"))
    db.commit()
    return result


def list_schedule(
    db: DbSession, context: RequestContext, start: dt.datetime, end: dt.datetime
) -> list[SessionSummary]:
    sessions = repository.list_sessions_in_range(db, context.organization_id, start, end)
    return [SessionSummary.model_validate(s) for s in sessions]


# --- Recurring series -------------------------------------------------------


def _to_utc(day: dt.date, local_time: dt.time, tz_name: str) -> dt.datetime:
    """Materialize a local wall-clock (date + time in a timezone) to a UTC instant."""
    local = dt.datetime.combine(day, local_time, tzinfo=ZoneInfo(tz_name))
    return local.astimezone(dt.UTC)


def _monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def _occurrence_dates(
    series: SessionSeries, horizon_start: dt.date, horizon_end: dt.date
) -> list[dt.date]:
    """Every date in ``[horizon_start, horizon_end)`` on a matching weekday, honoring
    the series frequency (weekly / every-other-week)."""
    weekdays = set(series.weekdays)
    anchor_monday = _monday(series.start_date)
    step = 2 if series.frequency is SessionSeriesFrequency.BIWEEKLY else 1
    dates: list[dt.date] = []
    day = max(horizon_start, series.start_date)
    while day < horizon_end:
        if day.weekday() in weekdays:
            weeks_since = (_monday(day) - anchor_monday).days // 7
            if weeks_since % step == 0:
                dates.append(day)
        day += dt.timedelta(days=1)
    return dates


def _require_trainer_in_org(
    db: DbSession, context: RequestContext, trainer_person_id: str | None
) -> None:
    if trainer_person_id is None:
        return
    if not repository.is_org_trainer(db, context.organization_id, trainer_person_id):
        # Same error for foreign/nonexistent, never leak cross-tenant existence.
        raise NotFoundError("Trener nije pronađen.")


def _require_location_in_org(
    db: DbSession, context: RequestContext, location_id: str | None
) -> None:
    if location_id is None:
        return
    if not repository.is_org_location(db, context.organization_id, location_id):
        # Same error for foreign/nonexistent, never leak cross-tenant existence.
        raise NotFoundError("Lokacija nije pronađena.")


def create_series(
    db: DbSession, context: RequestContext, body: SessionSeriesCreate
) -> SessionSeriesSummary:
    """M1. Create a weekly recurrence rule and activate it (concrete sessions are
    materialized by a subsequent generate call)."""
    group = repository.get_org_group(db, context.organization_id, body.group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")
    if body.frequency is SessionSeriesFrequency.MONTHLY:
        raise BadRequestError("Mesečna učestalost još nije podržana.")

    # Same group-as-default rule as a one-off session, so "svake srede u 18:00"
    # inherits the group's trainer and place without re-typing them.
    trainer_person_id = (
        body.trainer_person_id
        if "trainer_person_id" in body.model_fields_set
        else group.default_trainer_person_id
    )
    location_id = (
        body.location_id
        if "location_id" in body.model_fields_set
        else group.default_location_id
    )
    _require_trainer_in_org(db, context, trainer_person_id)
    _require_location_in_org(db, context, location_id)

    series = SessionSeries(
        organization_id=context.organization_id,
        group_id=body.group_id,
        trainer_person_id=trainer_person_id,
        location_id=location_id,
        title=body.title,
        frequency=body.frequency,
        weekdays=body.weekdays,
        start_date=body.start_date,
        timezone=body.timezone,
        local_time=body.local_time,
        duration_minutes=body.duration_minutes,
    )
    db.add(series)
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="session_series.created",
        entity_type="session_series",
        entity_id=series.id,
        summary=f"Kreirana serija termina '{series.title}'.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="session_series.created",
        payload={"series_id": series.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    db.commit()
    return SessionSeriesSummary.model_validate(series)


def list_series(db: DbSession, context: RequestContext) -> list[SessionSeriesSummary]:
    return [
        SessionSeriesSummary.model_validate(s)
        for s in repository.list_series(db, context.organization_id)
    ]


def generate_sessions(
    db: DbSession, context: RequestContext, series_id: str, body: SeriesGenerateRequest
) -> SeriesGenerateResult:
    """M2. Materialize concrete sessions over a rolling ``weeks``-week horizon.
    Idempotent: existing occurrences are skipped (natural key = series + start),
    and occurrences that would clash with another booking are flagged, not created."""
    series = repository.get_org_series(db, context.organization_id, series_id)
    if series is None:
        raise NotFoundError("Serija termina nije pronađena.")
    if series.frequency is SessionSeriesFrequency.MONTHLY:
        raise BadRequestError("Mesečna učestalost još nije podržana.")

    from_date = body.from_date or clock.now().date()
    horizon_start = max(series.start_date, from_date)
    horizon_end = from_date + dt.timedelta(weeks=body.weeks)

    existing = repository.existing_series_start_times(db, series_id)
    created = 0
    skipped_existing = 0
    skipped_conflicts: list[SkippedOccurrence] = []

    for day in _occurrence_dates(series, horizon_start, horizon_end):
        starts_at = _to_utc(day, series.local_time, series.timezone)
        ends_at = starts_at + dt.timedelta(minutes=series.duration_minutes)
        if starts_at in existing:
            skipped_existing += 1
            continue
        conflicts = repository.find_conflicts(
            db, context.organization_id, series.group_id, starts_at, ends_at
        )
        if conflicts:
            skipped_conflicts.append(
                SkippedOccurrence(starts_at=starts_at, reason="SESSION_CONFLICT")
            )
            continue
        session = Session(
            organization_id=context.organization_id,
            group_id=series.group_id,
            series_id=series.id,
            trainer_person_id=series.trainer_person_id,
            location_id=series.location_id,
            title=series.title,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        db.add(session)
        db.flush()
        existing.add(starts_at)
        created += 1

    result = SeriesGenerateResult(
        series_id=series.id,
        created_count=created,
        skipped_existing=skipped_existing,
        skipped_conflicts=skipped_conflicts,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
    )
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="session_series.generated",
        entity_type="session_series",
        entity_id=series.id,
        summary=(
            f"Generisano {created} termina za seriju '{series.title}' "
            f"({len(skipped_conflicts)} preskočeno zbog preklapanja)."
        ),
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    if created or skipped_conflicts:
        enqueue(
            db,
            event_type="session_series.generated",
            payload={
                "series_id": series.id,
                "organization_id": context.organization_id,
                "created_count": created,
                "skipped_conflicts": len(skipped_conflicts),
            },
            organization_id=context.organization_id,
        )
    db.commit()
    return result


def _apply_field_changes(session: Session, edit: SessionEdit, tz_name: str) -> bool:
    """Apply the edit's non-time and time fields to one session. Returns True if the
    session's time window moved (so the caller re-checks for conflicts)."""
    if edit.title is not None:
        session.title = edit.title
    if edit.trainer_person_id is not None:
        session.trainer_person_id = edit.trainer_person_id
    if edit.location_id is not None:
        session.location_id = edit.location_id

    if edit.local_time is None and edit.duration_minutes is None:
        return False

    old_duration = int((session.ends_at - session.starts_at).total_seconds() // 60)
    if edit.local_time is not None:
        local_date = session.starts_at.astimezone(ZoneInfo(tz_name)).date()
        session.starts_at = _to_utc(local_date, edit.local_time, tz_name)
    duration = edit.duration_minutes if edit.duration_minutes is not None else old_duration
    session.ends_at = session.starts_at + dt.timedelta(minutes=duration)
    return True


def _guard_no_conflict(db: DbSession, context: RequestContext, session: Session) -> None:
    conflicts = repository.find_conflicts(
        db,
        context.organization_id,
        session.group_id,
        session.starts_at,
        session.ends_at,
        exclude_session_id=session.id,
    )
    if conflicts:
        raise ConflictError(
            "Izmena termina se preklapa sa postojećim terminom grupe.",
            details={
                "code": "SESSION_CONFLICT",
                "conflicts": [
                    SessionSummary.model_validate(s).model_dump(mode="json") for s in conflicts
                ],
            },
        )


def edit_session(
    db: DbSession, context: RequestContext, session_id: str, edit: SessionEdit
) -> list[SessionSummary]:
    """M3. Edit a session at SINGLE / THIS_AND_FUTURE / ALL_FUTURE scope. A scoped
    edit updates the series template and every affected scheduled occurrence."""
    session = repository.get_org_session(db, context.organization_id, session_id)
    if session is None:
        raise NotFoundError("Termin nije pronađen.")
    if session.status is not SessionStatus.SCHEDULED:
        raise ConflictError("Samo zakazani termin može biti izmenjen.")
    _require_trainer_in_org(db, context, edit.trainer_person_id)
    _require_location_in_org(db, context, edit.location_id)

    series: SessionSeries | None = None
    if edit.scope is not SessionEditScope.SINGLE:
        if session.series_id is None:
            raise BadRequestError("Termin nije deo serije, moguća je samo pojedinačna izmena.")
        series = repository.get_org_series(db, context.organization_id, session.series_id)
        if series is None:
            raise NotFoundError("Serija termina nije pronađena.")

    tz_name = series.timezone if series is not None else "Europe/Belgrade"

    if edit.scope is SessionEditScope.SINGLE:
        targets = [session]
    else:
        assert series is not None
        # Update the template so future top-ups inherit the change.
        if edit.title is not None:
            series.title = edit.title
        if edit.trainer_person_id is not None:
            series.trainer_person_id = edit.trainer_person_id
        if edit.location_id is not None:
            series.location_id = edit.location_id
        if edit.local_time is not None:
            series.local_time = edit.local_time
        if edit.duration_minutes is not None:
            series.duration_minutes = edit.duration_minutes
        if edit.scope is SessionEditScope.THIS_AND_FUTURE:
            boundary = session.starts_at
        else:  # ALL_FUTURE
            boundary = clock.now()
        targets = repository.list_series_sessions(
            db,
            context.organization_id,
            series.id,
            status=SessionStatus.SCHEDULED,
            starts_from=boundary,
        )

    for target in targets:
        moved = _apply_field_changes(target, edit, tz_name)
        if moved:
            db.flush()
            _guard_no_conflict(db, context, target)

    db.flush()
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="session.edited",
        entity_type="session",
        entity_id=session.id,
        summary=f"Izmenjen termin ({edit.scope.value}), razlog {edit.reason.value}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"scope": edit.scope.value, "reason": edit.reason.value},
    )
    enqueue(
        db,
        event_type="session.changed",
        payload={
            "session_id": session.id,
            "series_id": session.series_id,
            "scope": edit.scope.value,
            "reason": edit.reason.value,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return [SessionSummary.model_validate(t) for t in targets]


def cancel_session(
    db: DbSession, context: RequestContext, session_id: str, body: SessionCancel
) -> SessionSummary:
    """M5. Cancel a scheduled session with a reason. The slot frees up for others."""
    session = repository.get_org_session(db, context.organization_id, session_id)
    if session is None:
        raise NotFoundError("Termin nije pronađen.")
    if session.status is SessionStatus.CANCELLED:
        raise ConflictError("Termin je već otkazan.")
    if session.status is SessionStatus.COMPLETED:
        raise ConflictError("Završen termin ne može biti otkazan.")

    session.status = SessionStatus.CANCELLED
    session.cancellation_reason = body.reason
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="session.cancelled",
        entity_type="session",
        entity_id=session.id,
        summary=f"Otkazan termin, razlog {body.reason.value}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"reason": body.reason.value, "note": body.note},
    )
    enqueue(
        db,
        event_type="session.cancelled",
        payload={
            "session_id": session.id,
            "reason": body.reason.value,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return SessionSummary.model_validate(session)


def reactivate_session(
    db: DbSession, context: RequestContext, session_id: str
) -> SessionSummary:
    """M5. Reactivate a cancelled session, refused if the slot is no longer free."""
    session = repository.get_org_session(db, context.organization_id, session_id)
    if session is None:
        raise NotFoundError("Termin nije pronađen.")
    if session.status is not SessionStatus.CANCELLED:
        raise ConflictError("Samo otkazan termin može biti ponovo aktiviran.")

    conflicts = repository.find_conflicts(
        db,
        context.organization_id,
        session.group_id,
        session.starts_at,
        session.ends_at,
        exclude_session_id=session.id,
    )
    if conflicts:
        raise ConflictError(
            "Termin se preklapa sa postojećim terminom grupe.",
            details={
                "code": "SESSION_CONFLICT",
                "conflicts": [
                    SessionSummary.model_validate(s).model_dump(mode="json") for s in conflicts
                ],
            },
        )

    session.status = SessionStatus.SCHEDULED
    session.cancellation_reason = None
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="session.reactivated",
        entity_type="session",
        entity_id=session.id,
        summary="Termin ponovo aktiviran.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="session.reactivated",
        payload={"session_id": session.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    db.commit()
    return SessionSummary.model_validate(session)
