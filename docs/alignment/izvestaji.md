# Alignment: Izveštaji i pregled poslovanja

**oblast:** `izvestaji` · status not marked `odobreno` · **app @ `3c2d074`**

## Summary

**0 implemented · entire domain absent.** No reporting domain, no aggregation
endpoints, no dashboards beyond per-role home screens. The data it would read
(attendance, billing, membership, events) largely exists, so this is a
read-model layer, not new source data.

## Missing (all of it)

- Business overview / dashboard (members, revenue, attendance rate, debts).
- Financial reports (billed vs collected, outstanding debts) — reads PRD 07.
- Attendance/participation reports — reads PRD 06.
- Membership/enrollment trend reports — reads PRD 03/04.
- Export of reports.

## Plan

Wave 3, **late** — reporting reads across billing/attendance/membership/events,
so it is most valuable once those domains' data is complete (especially PRD 04
pricing → 07 billing, and PRD 05 series → 06 attendance). Build as read-only
aggregates that never mutate; respect tenant isolation on every query.

## Open questions

1. Frontmatter not `odobreno` — confirm v1.0 scope.
2. Which handful of reports are the pilot must-haves vs later? (Revenue +
   outstanding debts + attendance rate are the usual first three.)
