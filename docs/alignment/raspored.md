# Alignment: Raspored i termini

**oblast:** `raspored` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

## Summary

**~3 implemented · 1 partial · ~8 missing.** Single-session creation and
**conflict detection** (the hardest correctness piece) are real and tested. The
recurring-schedule engine that the PRD is mostly about — weekly rules, 12-week
generation, series edits, cancellation, trainer/room changes — exists only as a
model (`SessionSeries`) with no endpoints.

## Implemented (verified)

- **I1 — Single session create (§9, §10, §11).** `POST /schedule/sessions` →
  `create_session` (`apps/api/app/domains/scheduling/service.py:36`);
  `Session` + `SessionStatus` (scheduled/cancelled/completed)
  (`scheduling/models.py`, `enums.py`). Tests `tests/test_scheduling.py` (3).
- **I2 — Conflict check (§16–19).** `POST /schedule/conflict-check` →
  `check_conflicts` (`scheduling/service.py:22`); the overlap rule and
  "conflict is a hard block" behaviour is the strongest part of this domain.
- **I3 — List schedule (§35.1).** `GET /schedule/sessions` →
  `list_schedule` (`scheduling/service.py:108`), org-scoped.

## Partial

- **P1 — Recurring series model (§7, §8).** `SessionSeries` +
  `SessionSeriesFrequency` exist (`scheduling/models.py`, `enums.py`), and
  `SessionChangeReasonCode`/`SessionCancellationReasonCode` are defined — but no
  endpoint creates a series, activates a weekly rule, or generates sessions.

## Missing (in-scope, not built)

- **M1 — Weekly rule create + first activation (§7, §13).** No series endpoint.
- **M2 — 12-week-ahead generation + auto top-up (§12, §14).** No generation job.
- **M3 — Edit single / this-and-future / all-future (§21, §22, §23).** No edit
  endpoints (reason enums exist, unused).
- **M4 — Trainer swap (§24), room/space change (§25).** No endpoints; room change
  also blocked by missing Room entity (PRD 02 M2).
- **M5 — Cancel session + reasons (§26, §27), reactivate cancelled (§28).** No
  cancel endpoint (`SessionCancellationReasonCode` unused).
- **M6 — Automatic notifications on change (§30, §31), failed-delivery handling
  (§32).** No auto-notify (ties to PRD 08).
- **M7 — Capacity from space (§20).** Needs Room entity (PRD 02).
- **M8 — Trainer schedule (T03) + parent schedule screens (§35.4, §35.5).** Web has
  `manager/Schedule.tsx` only.

## Open questions

1. Wave 2 keystone: the series-generation endpoint + 12-week job unlocks most of
   this PRD. The conflict engine it must reuse already exists (`service.py:22`).
2. Room-dependent items (M4 room change, M7 capacity) depend on PRD 02.
