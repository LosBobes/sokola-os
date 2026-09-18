"""Outbox consumer: turns domain events from other domains into in-app
:class:`~app.domains.communications.models.Notification` rows (PRD 08 M1).

Wired the same way every outbox consumer is: :func:`register` binds these
handlers to event types, and :mod:`app.handlers` calls it once at process
startup (worker) or test setup. A handler receives the worker's session and the
:class:`~app.platform.outbox.models.OutboxMessage`, and neither commits nor
rolls back: the worker owns the transaction, so these writes land together with
the message's inbox claim and DELIVERED status (see
``app.platform.outbox.worker``).

Cross-domain reads here go through *models* only (never another domain's
service/repository/router), which is exactly what the architecture gate
allows (see ``scripts/check_architecture.py``). This is deliberately a
read-only fan-out: we resolve "who is affected" from the payload and the
current state of the referenced record, then write ``Notification`` rows.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.billing.models import Charge
from app.domains.communications.enums import NotificationDeliveryStatus
from app.domains.communications.models import Notification
from app.domains.events.enums import RegistrationStatus
from app.domains.events.models import EventRegistration
from app.domains.groups.models import GroupMembership
from app.domains.people.enums import GuardianAccessStatus
from app.domains.people.models import GuardianSchoolAccess
from app.domains.scheduling.models import Session as ScheduleSession
from app.platform.outbox.models import OutboxMessage
from app.platform.outbox.worker import register_handler

_REASON_LABELS = {
    "WEATHER": "vremenskih uslova",
    "TRAINER_UNAVAILABLE": "nedostupnosti trenera",
    "HOLIDAY": "praznika",
    "LOW_ATTENDANCE": "malog broja prijavljenih",
    "TIME_CHANGE": "promene termina",
    "LOCATION_CHANGE": "promene lokacije",
    "TRAINER_CHANGE": "promene trenera",
    "OTHER": "drugog razloga",
}


def _reason_label(code: str | None) -> str:
    if code is None:
        return "nepoznatog razloga"
    return _REASON_LABELS.get(code, "drugog razloga")


def _group_recipients(db: Session, school_id: str, group_id: str) -> set[str]:
    """A group's active members plus the active guardians of any of them."""
    member_ids = set(
        db.execute(
            select(GroupMembership.person_id).where(
                GroupMembership.group_id == group_id, GroupMembership.ended_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    if not member_ids:
        return set()
    return member_ids | _guardians_of(db, school_id, member_ids)


def _guardians_of(db: Session, school_id: str, child_ids: set[str]) -> set[str]:
    return set(
        db.execute(
            select(GuardianSchoolAccess.guardian_person_id).where(
                GuardianSchoolAccess.school_id == school_id,
                GuardianSchoolAccess.child_person_id.in_(child_ids),
                GuardianSchoolAccess.status == GuardianAccessStatus.ACTIVE,
            )
        )
        .scalars()
        .all()
    )


def _notify(
    db: Session,
    message: OutboxMessage,
    *,
    recipients: set[str],
    title: str,
    body: str,
    entity_type: str,
    entity_id: str,
) -> None:
    """Insert one ``Notification`` per recipient.

    ``source_message_id`` is kept as provenance (which event produced this
    notification), not as de-duplication: the inbox claim in the worker is what
    makes a redelivery a no-op now."""
    if not recipients or message.school_id is None:
        return
    for person_id in sorted(recipients):
        db.add(
            Notification(
                school_id=message.school_id,
                person_id=person_id,
                event_type=message.event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                title=title,
                body=body,
                delivery_status=NotificationDeliveryStatus.DELIVERED,
                source_message_id=message.id,
            )
        )
    db.flush()


def _handle_session_event(
    db: Session, message: OutboxMessage, *, title: str, body_template: str
) -> None:
    session_id = message.payload.get("session_id")
    if not session_id or message.school_id is None:
        return
    session = db.get(ScheduleSession, session_id)
    if session is None:
        return
    recipients = _group_recipients(db, message.school_id, session.group_id)
    session_title = session.title or "trening"
    reason = _reason_label(message.payload.get("reason"))
    body = body_template.format(title=session_title, reason=reason)
    _notify(
        db,
        message,
        recipients=recipients,
        title=title,
        body=body,
        entity_type="session",
        entity_id=session.id,
    )


def handle_session_changed(db: Session, message: OutboxMessage) -> None:
    _handle_session_event(
        db,
        message,
        title="Termin je izmenjen",
        body_template="Termin „{title}“ je izmenjen zbog {reason}.",
    )


def handle_session_cancelled(db: Session, message: OutboxMessage) -> None:
    _handle_session_event(
        db,
        message,
        title="Termin je otkazan",
        body_template="Termin „{title}“ je otkazan zbog {reason}.",
    )


def handle_session_reactivated(db: Session, message: OutboxMessage) -> None:
    _handle_session_event(
        db,
        message,
        title="Termin je ponovo aktiviran",
        body_template="Termin „{title}“ je ponovo aktiviran.",
    )


def handle_billing_run_posted(db: Session, message: OutboxMessage) -> None:
    billing_run_id = message.payload.get("billing_run_id")
    if not billing_run_id or message.school_id is None:
        return
    charged_ids = set(
        db.execute(select(Charge.person_id).where(Charge.billing_run_id == billing_run_id))
        .scalars()
        .all()
    )
    if not charged_ids:
        return
    recipients = charged_ids | _guardians_of(db, message.school_id, charged_ids)
    _notify(
        db,
        message,
        recipients=recipients,
        title="Novo zaduženje",
        body="Izdato je novo zaduženje za plaćanje. Proverite iznos u obračunu.",
        entity_type="billing_run",
        entity_id=billing_run_id,
    )


def handle_event_registered(db: Session, message: OutboxMessage) -> None:
    event_id = message.payload.get("event_id")
    if not event_id or message.school_id is None:
        return
    rows = db.execute(
        select(
            EventRegistration.child_person_id,
            EventRegistration.registered_by_person_id,
        ).where(
            EventRegistration.event_id == event_id,
            EventRegistration.status == RegistrationStatus.REGISTERED,
        )
    ).all()
    if not rows:
        return
    child_ids = {r.child_person_id for r in rows}
    recipients = (
        child_ids
        | {r.registered_by_person_id for r in rows}
        | _guardians_of(db, message.school_id, child_ids)
    )
    _notify(
        db,
        message,
        recipients=recipients,
        title="Prijava na događaj potvrđena",
        body="Prijava na događaj je uspešno evidentirana.",
        entity_type="event",
        entity_id=event_id,
    )


def register() -> None:
    """Bind this domain's handlers to the event types it reacts to. Called once
    from :func:`app.handlers.register_all`."""
    register_handler("session.changed", handle_session_changed)
    register_handler("session.cancelled", handle_session_cancelled)
    register_handler("session.reactivated", handle_session_reactivated)
    register_handler("billing_run.posted", handle_billing_run_posted)
    register_handler("event.registered", handle_event_registered)
