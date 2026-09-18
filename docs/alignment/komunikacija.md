# Alignment: Obaveštenja i komunikacija

**oblast:** `komunikacija` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

## Summary

**~2 implemented · 1 partial · ~4 missing.** Manual announcements (with a
preview + recipient snapshot) work. The event-driven notification half — the
automatic messages other PRDs promise (schedule change, billing, event) — plus
delivery tracking and an in-app inbox, is missing.

## Implemented (verified)

- **I1 — Publish announcement (§ obaveštenja).** `POST /communications/announcements`
  → `publish` (`apps/api/app/domains/communications/service.py:51`);
  `Announcement`, `AnnouncementRecipient`, `AnnouncementStatus`,
  `AnnouncementTargetType` (`communications/models.py`, `enums.py`).
  Tests `tests/test_communications.py` (2).
- **I2 — Preview with recipient snapshot (§ ko prima).** `POST /communications/announcements/preview`
  → `preview` (`service.py:42`); `_resolve_recipients` + `_snapshot_hash`
  (`service.py:26,37`) freeze the audience deterministically before send.

## Partial

- **P1 — Targeting (§ ko prima).** `AnnouncementTargetType` supports audience
  selection, but the range of targets (per-group, per-event, per-role) vs the
  PRD's full matrix is not verified.

## Missing (in-scope, not built)

- **M1 — Automatic event-driven notifications.** Schedule change (PRD 05 §30),
  billing, and event notifications are not emitted. The outbox spine exists
  (`app/platform/outbox`, `app/handlers.py`) but no comms handler consumes those
  events.
- **M2 — Delivery-failure handling (PRD 05 §32 pattern).** No retry/failed-delivery
  state surfaced to the sender.
- **M3 — In-app inbox / read state.** No per-recipient inbox or read tracking
  endpoint.
- **M4 — Safe email content rules (§ imejl).** Email sending itself is not wired
  (no provider); the PRD's "email must not contain X" rules are unenforced because
  there is no email path yet.

## Open questions

1. Wave 4: wiring comms handlers onto existing outbox events (schedule/billing/
   events) is the highest-value next step and reuses `app/handlers.py`.
2. Is transactional email in scope for v1.0, or in-app only? Affects M4.
