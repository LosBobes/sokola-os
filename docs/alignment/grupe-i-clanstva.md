# Alignment: Grupe i upis članova

**oblast:** `grupe-i-clanstva` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

## Summary

**~3 implemented · 2 partial · ~7 missing.** Groups and basic enrollment (add a
member) exist with a capacity mode. The two pillars of this PRD — **pricing**
(group base monthly price + member discount, §16–17) and the **enrollment
lifecycle** (suspend/resume/transfer/end, §21–30) — are missing. Pricing is
absent even at the data layer, which also starves billing (PRD 07) of a fee source.

## Implemented (verified)

- **I1 — Create group + capacity mode (§5, §11–14).** `POST /groups` →
  `create_group` (`apps/api/app/domains/groups/service.py:22`);
  `GroupCapacityMode` enum (`groups/enums.py`) supports unlimited/warn/hard modes;
  `Group.capacity` (`groups/models.py:28`). Tests `tests/test_groups.py` (3).
- **I2 — List groups (§31).** `GET /groups` (`groups/service.py:34`), org-scoped.
- **I3 — Enroll a member (§18) + list members (§31).** `POST /groups/{id}/members`
  → `add_member` (`groups/service.py:39`), `GET /groups/{id}/members`.
  `GroupMembership` (`groups/models.py`).

## Partial

- **P1 — Enrollment end reason (§24).** `GroupMembership.end_reason` +
  `GroupMembershipEndReason` exist (`groups/models.py:52`, `enums.py`) — but no
  end/suspend endpoint sets them.
- **P2 — Member in multiple groups (§19).** `GroupMembership` is per-group so the
  data allows it, but there's no cross-group view/enrollment guardrails.

## Missing (in-scope, not built)

- **M1 — Group base monthly price (§16) + member discount (§17).** No price/discount
  columns on `Group` or `GroupMembership` (confirmed: `groups/models.py` has no
  money fields). Blocks billing derivation (PRD 07).
- **M2 — Enrollment lifecycle: suspend/resume/end (§21, §22, §23, §24).** No endpoints.
- **M3 — Transfer to another group (§25–29), financial consequence of transfer
  (§28), cross-school transfer (§29).** Absent.
- **M4 — Program / location link on group (§7).** No `program_id`/`location_id`
  (depends on PRD 02 entities).
- **M5 — Trainer assignment to group (§8, §30).** No trainer-group link endpoint
  (ties to PRD 01 M8 scope=GROUP).
- **M6 — "U pripremi" group state (§9).** Only active/archived RecordStatus; no
  DRAFT/PREPARING for groups.
- **M7 — Screens M03/new group/detail/new enrollment/transfer (§33).** Web has no
  groups route.

## Open questions

1. Wave 2: decide the pricing shape (flat monthly on group + per-member discount)
   before wiring billing, since PRD 07's runs need it.
2. Program/location links depend on PRD 02 — sequence after 02.
