# Alignment: Prisustvo i napredak

**oblast:** `prisustvo` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

## Summary

**~2 implemented · 1 partial · ~3 missing.** Attendance itself is a clean,
complete slice: fetch a session's sheet, save marks, with an override-reason
enum for corrections. The "napredak" (progress) half of the PRD has no model or
endpoint.

## Implemented (verified)

- **I1 — Attendance sheet read (§ attendance).** `GET /schedule/sessions/{id}/attendance`
  → `get_sheet` (`apps/api/app/domains/attendance/service.py:22`,
  `router.py`). Org- and session-scoped.
- **I2 — Save attendance + override reasons.** `PUT /schedule/sessions/{id}/attendance`
  → `save_attendance` (`attendance/service.py:44`); `AttendanceRecord`,
  `AttendanceStatus`, `AttendanceOverrideReasonCode` (`attendance/models.py`,
  `enums.py`). Tests `tests/test_attendance.py` (3).

## Partial

- **P1 — Attendance is per-session; the sheet hangs off a scheduling session.**
  Works, but depends on sessions existing — and recurring generation is missing
  (see PRD 05 M2), so at scale sheets only exist for manually-created sessions.

## Missing (in-scope, not built)

- **M1 — Progress / "napredak" tracking.** No progress model or endpoint anywhere
  (confirmed: attendance domain has only `AttendanceRecord`).
- **M2 — Trainer-facing attendance flow.** Web has `manager/Attendance.tsx`; the
  trainer's own take-attendance screen (T03 flow in PRD 05) is not built.
- **M3 — Attendance-driven notifications / summaries.** None (ties to PRD 08/13).

## Open questions

1. Is "napredak" a v1.0 commitment or a later note? The PRD title includes it but
   nothing tracks skill/progress today — confirm scope before modeling.
