from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.domains.reports import service
from app.domains.reports.schemas import (
    AttendanceReport,
    FinancialReport,
    MembershipTrendReport,
    OverviewReport,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(prefix="/reports", tags=["reports"])

_reports = require_permission(PermissionArea.REPORTS)
ReportsContext = Annotated[ContextDep, Depends(_reports)]


@router.get("/overview", response_model=OverviewReport, operation_id="getOverviewReport")
def get_overview(db: DbDep, context: ReportsContext) -> OverviewReport:
    return service.overview(db, context)


@router.get(
    "/financial", response_model=FinancialReport, operation_id="getFinancialReport"
)
def get_financial_report(
    db: DbDep,
    context: ReportsContext,
    date_from: Annotated[dt.date, Query()],
    date_to: Annotated[dt.date, Query()],
) -> FinancialReport:
    return service.financial_report(db, context, date_from, date_to)


@router.get(
    "/attendance", response_model=AttendanceReport, operation_id="getAttendanceReport"
)
def get_attendance_report(
    db: DbDep,
    context: ReportsContext,
    date_from: Annotated[dt.date, Query()],
    date_to: Annotated[dt.date, Query()],
    group_id: Annotated[str | None, Query()] = None,
) -> AttendanceReport:
    return service.attendance_report(db, context, date_from, date_to, group_id)


@router.get(
    "/membership-trend",
    response_model=MembershipTrendReport,
    operation_id="getMembershipTrendReport",
)
def get_membership_trend_report(
    db: DbDep,
    context: ReportsContext,
    date_from: Annotated[dt.date, Query()],
    date_to: Annotated[dt.date, Query()],
    group_id: Annotated[str | None, Query()] = None,
) -> MembershipTrendReport:
    return service.membership_trend(db, context, date_from, date_to, group_id)
