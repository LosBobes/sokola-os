from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.common.errors import BadRequestError, NotFoundError
from app.config import get_settings
from app.domains.attendance.enums import AttendanceStatus
from app.domains.reports import repository
from app.domains.reports.schemas import (
    AttendanceByGroup,
    AttendanceReport,
    FinancialReport,
    MembershipTrendByGroup,
    MembershipTrendPoint,
    MembershipTrendReport,
    OutstandingByStatus,
    OverviewReport,
)
from app.platform import clock
from app.security.context import RequestContext

_OVERVIEW_ATTENDANCE_WINDOW_DAYS = 30
_MAX_TREND_MONTHS = 36  # bound query cost on a wide-open date range


def _day_bounds(date_from: dt.date, date_to: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Inclusive [date_from, date_to] as a half-open UTC datetime range."""
    if date_to < date_from:
        raise BadRequestError("Datum 'do' ne sme biti pre datuma 'od'.")
    start = dt.datetime.combine(date_from, dt.time.min, tzinfo=dt.UTC)
    end = dt.datetime.combine(date_to, dt.time.min, tzinfo=dt.UTC) + dt.timedelta(days=1)
    return start, end


def _month_buckets(date_from: dt.date, date_to: dt.date) -> list[tuple[dt.date, dt.date]]:
    if date_to < date_from:
        raise BadRequestError("Datum 'do' ne sme biti pre datuma 'od'.")
    buckets: list[tuple[dt.date, dt.date]] = []
    cursor = date_from.replace(day=1)
    while cursor <= date_to:
        next_month = (
            cursor.replace(year=cursor.year + 1, month=1)
            if cursor.month == 12
            else cursor.replace(month=cursor.month + 1)
        )
        bucket_end = min(next_month - dt.timedelta(days=1), date_to)
        bucket_start = max(cursor, date_from)
        buckets.append((bucket_start, bucket_end))
        cursor = next_month
        if len(buckets) > _MAX_TREND_MONTHS:
            raise BadRequestError(
                f"Opseg je predugačak (maksimum {_MAX_TREND_MONTHS} meseci)."
            )
    return buckets


def _attendance_rate(present: int, recorded: int) -> float:
    return round(present / recorded, 4) if recorded else 0.0


def _require_group(db: Session, school_id: str, group_id: str) -> None:
    if repository.get_school_group(db, school_id, group_id) is None:
        raise NotFoundError("Grupa nije pronađena.")


@dataclass
class _GroupTally:
    group_name: str
    present: int = 0
    recorded: int = 0


def overview(db: Session, context: RequestContext) -> OverviewReport:
    now = clock.now()
    period_start_date = now.date().replace(day=1)
    period_start, _ = _day_bounds(period_start_date, now.date())
    period_end_exclusive = now

    window_start = now - dt.timedelta(days=_OVERVIEW_ATTENDANCE_WINDOW_DAYS)
    counts = repository.attendance_counts(
        db, context.school_id, window_start, now
    )
    present = counts.get(AttendanceStatus.PRESENT, 0)
    recorded = sum(counts.values())

    return OverviewReport(
        period_start=period_start_date,
        period_end=now.date(),
        currency=get_settings().default_currency,
        active_member_count=repository.active_member_count(db, context.school_id),
        billed_total=repository.billed_total(
            db, context.school_id, period_start, period_end_exclusive
        ),
        collected_total=repository.collected_total(
            db, context.school_id, period_start, period_end_exclusive
        ),
        outstanding_debt_total=repository.outstanding_debt_total(
            db, context.school_id
        ),
        attendance_window_days=_OVERVIEW_ATTENDANCE_WINDOW_DAYS,
        attendance_recorded_count=recorded,
        attendance_present_count=present,
        attendance_rate=_attendance_rate(present, recorded),
    )


def financial_report(
    db: Session, context: RequestContext, date_from: dt.date, date_to: dt.date
) -> FinancialReport:
    start, end = _day_bounds(date_from, date_to)
    breakdown = [
        OutstandingByStatus(
            status=status.value, charge_count=count, outstanding=outstanding
        )
        for status, count, outstanding in repository.outstanding_by_status(
            db, context.school_id
        )
    ]
    return FinancialReport(
        date_from=date_from,
        date_to=date_to,
        currency=get_settings().default_currency,
        billed_total=repository.billed_total(
            db, context.school_id, start, end
        ),
        collected_total=repository.collected_total(
            db, context.school_id, start, end
        ),
        outstanding_debt_total=repository.outstanding_debt_total(
            db, context.school_id
        ),
        outstanding_by_status=breakdown,
    )


def attendance_report(
    db: Session,
    context: RequestContext,
    date_from: dt.date,
    date_to: dt.date,
    group_id: str | None,
) -> AttendanceReport:
    if group_id is not None:
        _require_group(db, context.school_id, group_id)

    start, end = _day_bounds(date_from, date_to)
    counts = repository.attendance_counts(
        db, context.school_id, start, end, group_id
    )
    present = counts.get(AttendanceStatus.PRESENT, 0)
    absent = counts.get(AttendanceStatus.ABSENT, 0)
    excused = counts.get(AttendanceStatus.EXCUSED, 0)
    late = counts.get(AttendanceStatus.LATE, 0)
    recorded = sum(counts.values())

    by_group_rows: dict[str, _GroupTally] = {}
    for g_id, g_name, status, count in repository.attendance_by_group(
        db, context.school_id, start, end, group_id
    ):
        tally = by_group_rows.setdefault(g_id, _GroupTally(group_name=g_name))
        tally.recorded += count
        if status is AttendanceStatus.PRESENT:
            tally.present += count

    by_group = [
        AttendanceByGroup(
            group_id=g_id,
            group_name=tally.group_name,
            recorded_count=tally.recorded,
            present_count=tally.present,
            attendance_rate=_attendance_rate(tally.present, tally.recorded),
        )
        for g_id, tally in sorted(by_group_rows.items(), key=lambda kv: kv[1].group_name)
    ]

    return AttendanceReport(
        date_from=date_from,
        date_to=date_to,
        group_id=group_id,
        recorded_count=recorded,
        present_count=present,
        absent_count=absent,
        excused_count=excused,
        late_count=late,
        attendance_rate=_attendance_rate(present, recorded),
        by_group=by_group,
    )


def membership_trend(
    db: Session,
    context: RequestContext,
    date_from: dt.date,
    date_to: dt.date,
    group_id: str | None,
) -> MembershipTrendReport:
    if group_id is not None:
        _require_group(db, context.school_id, group_id)

    buckets = _month_buckets(date_from, date_to)
    trend: list[MembershipTrendPoint] = []
    for bucket_start, bucket_end in buckets:
        as_of = dt.datetime.combine(bucket_end, dt.time.min, tzinfo=dt.UTC) + dt.timedelta(
            days=1
        )
        count = (
            repository.active_group_membership_count_as_of(
                db, context.school_id, group_id, as_of
            )
            if group_id is not None
            else repository.active_membership_count_as_of(db, context.school_id, as_of)
        )
        trend.append(
            MembershipTrendPoint(
                period_start=bucket_start, period_end=bucket_end, active_member_count=count
            )
        )

    by_group = (
        []
        if group_id is not None
        else [
            MembershipTrendByGroup(group_id=g_id, group_name=g_name, active_member_count=count)
            for g_id, g_name, count in repository.active_membership_by_group(
                db, context.school_id
            )
        ]
    )

    return MembershipTrendReport(
        date_from=date_from, date_to=date_to, group_id=group_id, trend=trend, by_group=by_group
    )
