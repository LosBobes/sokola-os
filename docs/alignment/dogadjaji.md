# Alignment: Događaji za škole

**oblast:** `dogadjaji` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

## Summary

**~5 implemented · 1 partial · ~2 missing.** The most complete domain. Event
creation, listing, child registration, and registration cancellation all exist
with full status/capacity/cancellation enums, and it is the one domain with a
parent-facing route in the web app.

## Implemented (verified)

- **I1 — Create event (§ događaj).** `POST /events` → `create_event`
  (`apps/api/app/domains/events/service.py:26`); `Event`, `EventType`,
  `EventCategory`, `EventStatus`, `EventCapacityMode` (`events/models.py`,
  `enums.py`). Tests `tests/test_events.py` (4).
- **I2 — List events (§ pregled).** `GET /events` → `list_events` (`service.py:42`).
- **I3 — Register children (§ prijava deteta).** `POST /events/{id}/registrations`
  → `register_children` (`service.py:49`); `EventRegistration`,
  `RegistrationStatus`.
- **I4 — Cancel registration (§ otkazivanje).** `POST /events/{id}/registrations/{rid}/cancel`
  → `cancel_registration` (`service.py:147`); `CancellationReasonCode`.
- **I5 — Parent-facing surface.** `apps/web/src/routes/parent/Events.tsx`;
  `RoleHome` routes PARENT to events (`apps/web/src/routes/RoleHome.tsx`).

## Partial

- **P1 — Capacity + waitlist edges.** `EventCapacityMode` exists; hard-cap /
  waitlist behaviour at the boundary not fully verified against the PRD.

## Missing (in-scope, not built)

- **M1 — Event lifecycle edges.** Event edit/cancel-whole-event and status
  transitions beyond DRAFT/registration are not surfaced as endpoints (only
  registration-level cancel exists).
- **M2 — Event notifications.** Automatic reminders/updates depend on PRD 08
  (comms handlers).

## Open questions

1. This domain is a good reference pattern for finishing others (rich enums +
   real endpoints + tests + web route). Use it as the template for Wave 2 work.
