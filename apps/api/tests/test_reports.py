"""Reporting domain (PRD 13). Every report is a live aggregate over other
domains' rows, these tests seed billing/payments/attendance/membership data
across TWO schools and check both the arithmetic and that org B's data
never leaks into org A's report (and vice versa)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.domains.attendance.enums import AttendanceStatus
from app.domains.attendance.models import AttendanceRecord
from app.domains.billing.enums import ChargeStatus
from app.domains.billing.models import Charge
from app.domains.groups.enums import GroupMembershipStatus
from app.domains.groups.models import Group, GroupMembership
from app.domains.identity.enums import RoleCode
from app.domains.payments.enums import PaymentMethod, PaymentRecordStatus
from app.domains.payments.models import PaymentRecord
from app.domains.scheduling.enums import SessionStatus
from app.domains.scheduling.models import Session as ScheduleSession
from app.domains.school.enums import MembershipStatus
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_membership, bootstrap_actor, make_person

# --- Seed helpers --------------------------------------------------------------


def _group(db: Session, actor: Actor, name: str = "G") -> Group:
    group = Group(school_id=actor.school.id, name=name)
    db.add(group)
    db.commit()
    return group


def _group_member(
    db: Session,
    actor: Actor,
    group: Group,
    *,
    given: str = "Član",
    status: GroupMembershipStatus = GroupMembershipStatus.ACTIVE,
    created_at: dt.datetime | None = None,
) -> GroupMembership:
    person = make_person(db, given=given, family="P")
    add_membership(db, person=person, school=actor.school)
    now = dt.datetime.now(tz=dt.UTC)
    membership = GroupMembership(
        group_id=group.id,
        school_id=actor.school.id,
        person_id=person.id,
        joined_at=created_at or now,
        status=status,
    )
    if created_at is not None:
        membership.created_at = created_at
    db.add(membership)
    db.commit()
    return membership


def _charge(
    db: Session,
    actor: Actor,
    *,
    person_id: str,
    amount_due: str,
    amount_paid: str = "0.00",
    status: ChargeStatus = ChargeStatus.OPEN,
    created_at: dt.datetime | None = None,
) -> Charge:
    charge = Charge(
        school_id=actor.school.id,
        person_id=person_id,
        description="Članarina",
        currency="RSD",
        amount_due=amount_due,
        amount_paid=amount_paid,
        status=status,
    )
    if created_at is not None:
        charge.created_at = created_at
    db.add(charge)
    db.commit()
    return charge


def _payment(
    db: Session,
    actor: Actor,
    *,
    charge_id: str,
    amount: Decimal,
    created_at: dt.datetime | None = None,
) -> PaymentRecord:
    payment = PaymentRecord(
        school_id=actor.school.id,
        charge_id=charge_id,
        amount=amount,
        currency="RSD",
        method=PaymentMethod.CASH,
        status=PaymentRecordStatus.RECORDED,
    )
    if created_at is not None:
        payment.created_at = created_at
    db.add(payment)
    db.commit()
    return payment


def _session(
    db: Session, actor: Actor, group: Group, *, starts_at: dt.datetime
) -> ScheduleSession:
    session = ScheduleSession(
        school_id=actor.school.id,
        group_id=group.id,
        starts_at=starts_at,
        ends_at=starts_at + dt.timedelta(hours=1),
        status=SessionStatus.SCHEDULED,
    )
    db.add(session)
    db.commit()
    return session


def _attendance(
    db: Session, actor: Actor, session: ScheduleSession, person_id: str, status: AttendanceStatus
) -> None:
    db.add(
        AttendanceRecord(
            school_id=actor.school.id,
            session_id=session.id,
            person_id=person_id,
            status=status,
        )
    )
    db.commit()


# --- Overview -------------------------------------------------------------------


def test_overview_report(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db, org_name="Klub A")
    noise = bootstrap_actor(db, org_name="Klub B")

    # Membership: actor itself is 1 active member; add 2 more active + 1 suspended.
    p1 = make_person(db, given="Ana", family="A")
    p2 = make_person(db, given="Bane", family="B")
    p3 = make_person(db, given="Ceda", family="C")
    add_membership(db, person=p1, school=actor.school)
    add_membership(db, person=p2, school=actor.school)
    add_membership(
        db, person=p3, school=actor.school, status=MembershipStatus.SUSPENDED
    )
    # Noise org: different count entirely.
    for _ in range(5):
        noise_p = make_person(db, given="X", family="X")
        add_membership(db, person=noise_p, school=noise.school)

    now = dt.datetime.now(tz=dt.UTC)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Exactly the period's inclusive lower bound, always <= the real "now" the
    # endpoint will see, so it can never land outside "this period" regardless
    # of what time of day/month the test happens to run.
    this_month = current_month_start
    last_month_end = current_month_start - dt.timedelta(seconds=1)

    # This period: 2 charges billed (1.000,00 + 500,00), 1 payment collected (1.000,00).
    c1 = _charge(db, actor, person_id=p1.id, amount_due=Decimal("1000.00"), created_at=this_month)
    _charge(db, actor, person_id=p2.id, amount_due=Decimal("500.00"), created_at=this_month)
    _payment(db, actor, charge_id=c1.id, amount=Decimal("1000.00"), created_at=this_month)
    # Reflect the payment on the charge itself (a real payment flow would do this
    # via payments.service; here we seed both ledgers directly for report math).
    c1.amount_paid = Decimal("1000.00")
    c1.status = ChargeStatus.PAID
    db.commit()

    # Last period: must NOT be counted in "this period" billed/collected.
    _charge(db, actor, person_id=p1.id, amount_due=Decimal("9999.99"), created_at=last_month_end)

    # Outstanding debt is a point-in-time balance (not period-scoped): the second
    # charge (500,00 due, 0 paid) plus the older one (9.999,99 due, 0 paid).
    expected_outstanding = "10499.99"  # 500,00 + 9.999,99

    # Noise org charges must never leak into org A's totals.
    noise_person = make_person(db, given="Y", family="Y")
    add_membership(db, person=noise_person, school=noise.school)
    _charge(
        db, noise, person_id=noise_person.id, amount_due=Decimal("70000.00"), created_at=this_month
    )

    # Attendance in the recent (30-day) window: 3 present, 1 absent.
    group = _group(db, actor)
    m1 = _group_member(db, actor, group)
    session = _session(db, actor, group, starts_at=now - dt.timedelta(days=5))
    _attendance(db, actor, session, m1.person_id, AttendanceStatus.PRESENT)
    session2 = _session(db, actor, group, starts_at=now - dt.timedelta(days=2))
    _attendance(db, actor, session2, m1.person_id, AttendanceStatus.PRESENT)
    _attendance(db, actor, session2, p1.id, AttendanceStatus.PRESENT)
    _attendance(db, actor, session2, p2.id, AttendanceStatus.ABSENT)
    # Outside the 30-day window: must not affect the rate.
    old_session = _session(db, actor, group, starts_at=now - dt.timedelta(days=40))
    _attendance(db, actor, old_session, p1.id, AttendanceStatus.ABSENT)

    resp = client.get("/reports/overview", headers=actor.headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["active_member_count"] == 4  # actor + p1 + p2 + m1's own person
    assert body["billed_total"] == "1500.00"
    assert body["collected_total"] == "1000.00"
    assert body["outstanding_debt_total"] == expected_outstanding
    assert body["attendance_recorded_count"] == 4
    assert body["attendance_present_count"] == 3
    assert body["attendance_rate"] == 0.75

    # Org isolation: org B's own overview sees only its own 7 active members
    # (its actor + 5 seeded + noise_person) and none of org A's money.
    other = client.get("/reports/overview", headers=noise.headers).json()
    assert other["active_member_count"] == 7
    assert other["billed_total"] == "70000.00"
    assert other["collected_total"] == "0.00"


# --- Financial --------------------------------------------------------------


def test_financial_report(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db, org_name="Klub A")
    other = bootstrap_actor(db, org_name="Klub B")
    person = make_person(db, given="Ana", family="A")
    add_membership(db, person=person, school=actor.school)

    in_range = dt.datetime(2026, 1, 15, tzinfo=dt.UTC)
    before_range = dt.datetime(2025, 12, 20, tzinfo=dt.UTC)
    after_range = dt.datetime(2026, 2, 5, tzinfo=dt.UTC)

    open_charge = _charge(
        db, actor, person_id=person.id, amount_due=Decimal("1000.00"), created_at=in_range
    )
    _payment(db, actor, charge_id=open_charge.id, amount=Decimal("400.00"), created_at=in_range)
    open_charge.amount_paid = Decimal("400.00")
    open_charge.status = ChargeStatus.PARTIALLY_PAID
    db.commit()

    paid_charge = _charge(
        db,
        actor,
        person_id=person.id,
        amount_due=Decimal("600.00"),
        amount_paid=Decimal("600.00"),
        status=ChargeStatus.PAID,
        created_at=in_range,
    )
    _payment(db, actor, charge_id=paid_charge.id, amount=Decimal("600.00"), created_at=in_range)

    # Out-of-range charges/payments must not affect the totals.
    _charge(db, actor, person_id=person.id, amount_due=Decimal("5000.00"), created_at=before_range)
    _charge(db, actor, person_id=person.id, amount_due=Decimal("8000.00"), created_at=after_range)

    # Other org's data must never leak in.
    other_person = make_person(db, given="X", family="X")
    add_membership(db, person=other_person, school=other.school)
    _charge(
        db, other, person_id=other_person.id, amount_due=Decimal("9999.99"), created_at=in_range
    )

    resp = client.get(
        "/reports/financial",
        headers=actor.headers,
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["billed_total"] == "1600.00"  # 1.000,00 + 600,00, in-range only
    assert body["collected_total"] == "1000.00"  # 400,00 + 600,00, in-range only

    # Outstanding debt is point-in-time: open_charge (600,00 outstanding) plus the
    # two out-of-range OPEN charges (5.000,00 + 8.000,00), never the other org's.
    by_status = {row["status"]: row for row in body["outstanding_by_status"]}
    assert body["outstanding_debt_total"] == "13600.00"
    assert by_status["PARTIALLY_PAID"]["outstanding"] == "600.00"
    assert by_status["PARTIALLY_PAID"]["charge_count"] == 1
    assert by_status["OPEN"]["outstanding"] == "13000.00"
    assert by_status["OPEN"]["charge_count"] == 2

    other_resp = client.get(
        "/reports/financial",
        headers=other.headers,
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
    ).json()
    assert other_resp["billed_total"] == "9999.99"
    assert other_resp["collected_total"] == "0.00"


def test_financial_report_rejects_inverted_range(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    resp = client.get(
        "/reports/financial",
        headers=actor.headers,
        params={"date_from": "2026-02-01", "date_to": "2026-01-01"},
    )
    assert resp.status_code == 400


# --- Attendance ---------------------------------------------------------------


def test_attendance_report(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db, org_name="Klub A")
    other = bootstrap_actor(db, org_name="Klub B")

    group_a = _group(db, actor, name="Grupa A")
    group_b = _group(db, actor, name="Grupa B")
    member_a = _group_member(db, actor, group_a, given="Ana")
    member_b = _group_member(db, actor, group_b, given="Bane")

    in_range = dt.datetime(2026, 2, 10, tzinfo=dt.UTC)
    out_of_range = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)

    session_a = _session(db, actor, group_a, starts_at=in_range)
    _attendance(db, actor, session_a, member_a.person_id, AttendanceStatus.PRESENT)

    session_b = _session(db, actor, group_b, starts_at=in_range)
    _attendance(db, actor, session_b, member_b.person_id, AttendanceStatus.ABSENT)

    # Outside the requested range: must not affect any total.
    stale_session = _session(db, actor, group_a, starts_at=out_of_range)
    _attendance(db, actor, stale_session, member_a.person_id, AttendanceStatus.ABSENT)

    # Other org: must never leak in.
    other_group = _group(db, other, name="Grupa X")
    other_member = _group_member(db, other, other_group, given="Iks")
    other_session = _session(db, other, other_group, starts_at=in_range)
    _attendance(db, other, other_session, other_member.person_id, AttendanceStatus.PRESENT)

    resp = client.get(
        "/reports/attendance",
        headers=actor.headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recorded_count"] == 2
    assert body["present_count"] == 1
    assert body["absent_count"] == 1
    assert body["attendance_rate"] == 0.5

    by_group = {row["group_id"]: row for row in body["by_group"]}
    assert by_group[group_a.id]["present_count"] == 1
    assert by_group[group_a.id]["recorded_count"] == 1
    assert by_group[group_b.id]["present_count"] == 0
    assert by_group[group_b.id]["recorded_count"] == 1

    # Filtered by group: only group A's single PRESENT record.
    filtered = client.get(
        "/reports/attendance",
        headers=actor.headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28", "group_id": group_a.id},
    ).json()
    assert filtered["recorded_count"] == 1
    assert filtered["present_count"] == 1
    assert filtered["attendance_rate"] == 1.0

    other_resp = client.get(
        "/reports/attendance",
        headers=other.headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28"},
    ).json()
    assert other_resp["recorded_count"] == 1
    assert other_resp["present_count"] == 1


def test_attendance_report_unknown_group_is_404(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    resp = client.get(
        "/reports/attendance",
        headers=actor.headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28", "group_id": "grp_missing"},
    )
    assert resp.status_code == 404


# --- Membership trend -----------------------------------------------------------


def test_membership_trend_report(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db, org_name="Klub A", given="Šef")
    other = bootstrap_actor(db, org_name="Klub B")

    jan = dt.datetime(2026, 1, 10, tzinfo=dt.UTC)
    feb = dt.datetime(2026, 2, 10, tzinfo=dt.UTC)
    mar = dt.datetime(2026, 3, 10, tzinfo=dt.UTC)

    p_jan = make_person(db, given="Jan", family="P")
    add_membership(db, person=p_jan, school=actor.school, created_at=jan)
    p_feb = make_person(db, given="Feb", family="P")
    add_membership(db, person=p_feb, school=actor.school, created_at=feb)
    p_mar = make_person(db, given="Mar", family="P")
    add_membership(db, person=p_mar, school=actor.school, created_at=mar)
    # A suspended member must never count as "active".
    p_susp = make_person(db, given="Susp", family="P")
    add_membership(
        db,
        person=p_susp,
        school=actor.school,
        status=MembershipStatus.SUSPENDED,
        created_at=jan,
    )

    # Other org: must never leak in.
    other_person = make_person(db, given="X", family="X")
    add_membership(db, person=other_person, school=other.school, created_at=jan)

    resp = client.get(
        "/reports/membership-trend",
        headers=actor.headers,
        params={"date_from": "2026-01-01", "date_to": "2026-03-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["trend"]) == 3
    jan_bucket, feb_bucket, mar_bucket = body["trend"]
    # January bucket: only members who joined strictly before Feb 1 count , 
    # p_jan (joined Jan 10). The bootstrap actor joined "now" (well after
    # March), so it never appears in any of these historical buckets.
    assert jan_bucket["active_member_count"] == 1
    assert feb_bucket["active_member_count"] == 2  # + p_feb
    assert mar_bucket["active_member_count"] == 3  # + p_mar

    other_resp = client.get(
        "/reports/membership-trend",
        headers=other.headers,
        params={"date_from": "2026-01-01", "date_to": "2026-03-31"},
    ).json()
    assert other_resp["trend"][-1]["active_member_count"] == 1


def test_membership_trend_by_group(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_a = _group(db, actor, name="Grupa A")
    group_b = _group(db, actor, name="Grupa B")
    _group_member(db, actor, group_a, given="Ana")
    _group_member(db, actor, group_a, given="Bane")
    _group_member(db, actor, group_b, given="Ceda")
    # An ended group membership must not count.
    _group_member(db, actor, group_b, given="Duda", status=GroupMembershipStatus.ENDED)

    resp = client.get(
        "/reports/membership-trend",
        headers=actor.headers,
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
    )
    body = resp.json()
    by_group = {row["group_id"]: row for row in body["by_group"]}
    assert by_group[group_a.id]["active_member_count"] == 2
    assert by_group[group_b.id]["active_member_count"] == 1


def test_membership_trend_rejects_wide_range(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    resp = client.get(
        "/reports/membership-trend",
        headers=actor.headers,
        params={"date_from": "2000-01-01", "date_to": "2030-01-01"},
    )
    assert resp.status_code == 400


# --- Authorization --------------------------------------------------------------


def test_reports_require_reports_permission(client: TestClient, db: Session) -> None:
    trainer = bootstrap_actor(db, role=RoleCode.TRAINER, given="Trener")
    resp = client.get("/reports/overview", headers=trainer.headers)
    assert resp.status_code == 403

    parent = bootstrap_actor(db, role=RoleCode.PARENT, given="Roditelj")
    resp2 = client.get("/reports/overview", headers=parent.headers)
    assert resp2.status_code == 403


def test_manager_can_reach_reports(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db, role=RoleCode.MANAGER)
    resp = client.get("/reports/overview", headers=manager.headers)
    assert resp.status_code == 200
