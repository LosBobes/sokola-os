from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from app.common.money import MoneyAmount


class OverviewReport(BaseModel):
    """Business dashboard: a snapshot of the organization's health right now,
    plus this-calendar-month billing and a recent attendance window."""

    period_start: dt.date
    period_end: dt.date
    currency: str
    active_member_count: int
    billed_total: MoneyAmount
    collected_total: MoneyAmount
    outstanding_debt_total: MoneyAmount
    attendance_window_days: int
    attendance_recorded_count: int
    attendance_present_count: int
    attendance_rate: float


class OutstandingByStatus(BaseModel):
    status: str
    charge_count: int
    outstanding: MoneyAmount


class FinancialReport(BaseModel):
    """Billed vs. collected over an explicit date range, plus a breakdown of
    all currently-outstanding debt (not time-scoped, debt is a point-in-time
    balance, not something that happened "in" the range)."""

    date_from: dt.date
    date_to: dt.date
    currency: str
    billed_total: MoneyAmount
    collected_total: MoneyAmount
    outstanding_debt_total: MoneyAmount
    outstanding_by_status: list[OutstandingByStatus]


class AttendanceByGroup(BaseModel):
    group_id: str
    group_name: str
    recorded_count: int
    present_count: int
    attendance_rate: float


class AttendanceReport(BaseModel):
    """Attendance rate over a date range, scoped by each session's own
    ``starts_at`` (not by when the attendance row was written)."""

    date_from: dt.date
    date_to: dt.date
    group_id: str | None
    recorded_count: int
    present_count: int
    absent_count: int
    excused_count: int
    late_count: int
    attendance_rate: float
    by_group: list[AttendanceByGroup]


class MembershipTrendPoint(BaseModel):
    period_start: dt.date
    period_end: dt.date
    active_member_count: int


class MembershipTrendByGroup(BaseModel):
    group_id: str
    group_name: str
    active_member_count: int


class MembershipTrendReport(BaseModel):
    """Monthly-bucketed active-membership growth. Membership rows carry only a
    current ``status`` (no historical end date), so each bucket counts
    currently-active memberships that had already joined by the bucket's end , 
    a join-cohort growth curve, not a historical point-in-time snapshot."""

    date_from: dt.date
    date_to: dt.date
    group_id: str | None
    trend: list[MembershipTrendPoint]
    by_group: list[MembershipTrendByGroup]
