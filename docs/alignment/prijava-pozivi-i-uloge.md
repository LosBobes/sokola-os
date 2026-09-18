# Alignment: Prijava, pozivi i korisničke uloge

**oblast:** `prijava-pozivi-i-uloge` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

> This PRD is a bespoke 41-section document, not the 27-section template — sections were matched by heading text.

## Summary

**~15 implemented · 6 partial · ~12 missing · 1 conflict.** The **identity and
login half is solidly built** — external OIDC login, no local passwords
(structurally enforced), one global identity idempotent on the provider subject,
server-derived active context, immediate revocation. The **invitation and
role-administration half is essentially unbuilt**: the `Invitation` model and all
its statuses exist but have zero endpoints, so the whole "Pozivi" chapter (§16–24,
§34) and all role-assignment/permission flows (§25, §26, §14, §15) are missing.
One design-level conflict: authorization is by role name, contradicting the
PRD's rule that a role name alone must not grant area access (§19.2, §25.5).

## Conflict (fix first)

**C1 — Authorization by role name; PRD requires per-area/scoped permissions.**
§19.2, §25.5 and §15's full-vs-limited manager split require access to follow
*granted areas*, not the role label. Code grants domain access purely by
`RoleCode`: e.g. `require_roles(RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN)`
gives every ADMIN full roster access by name (`apps/api/app/domains/people/router.py:16`,
`apps/api/app/security/deps.py:74`). One flat `MANAGER` code, no per-area grant,
no policy layer (`apps/api/app/domains/identity/enums.py:21`). *Failure:* an ADMIN
invited "for finances only" would also pass roster and other ADMIN-gated guards.

## Missing (in-scope, not built)

- **M1 — Entire invitation lifecycle (§16–24).** Model + `InvitationStatus`
  (PENDING/ACCEPTED/EXPIRED/REVOKED/REISSUED) + `expires_at`
  (`apps/api/app/domains/identity/models.py:120`, `enums.py:59`) referenced only
  in `models.py`/`enums.py` — no router/service/repository/endpoint. Send, expiry,
  single-use accept, revoke-with-reason, reissue-voids-prior, accept-existing
  (§21), accept-new (§22) all unbuilt.
- **M2 — Wrong-account invite rejection (§23).** No accept path exists to reject a
  mismatched account against the invite target.
- **M3 — Role assignment & permission-change endpoints (§25, §26).** No router
  mutates `RoleAssignment` except implicit OWNER at org creation
  (`apps/api/app/domains/organization/service.py:51`).
- **M4 — Protected owner: last active owner cannot be removed (§14).** No guard,
  no removal endpoint.
- **M5 — Ownership add/transfer controlled action (§14).** Absent.
- **M6 — Scoped admin & limited manager (§19.1/19.2, §25.4/25.5).** See C1.
- **M7 — Parent-invite-to-specific-child + additional-guardian invite (§19.4/19.5, §37).**
  No invite path; `parent` domain only lists already-linked children
  (`apps/api/app/domains/parent/router.py`).
- **M8 — Trainer group-assignment path (§19.3).** `RoleAssignment.scope_type = GROUP`
  exists (`identity/models.py:95`) but nothing assigns a trainer to groups.
- **M9 — SOKOLA support temporary access (§33).** No support-access concept.
- **M10 — Login-email change re-linking (§8).** No SOKOLA re-verification flow.
- **M11 — Duplicate → controlled review (§32).** `PersonMergeRecord` is append-only
  with no endpoint by design; weak-match detection + review path absent.
- **M12 — Screens X01/X02 + invite-management UI (§34.1/34.2/34.5).** No invite
  backend to render against.

## Partial

- **P1 — Deactivated school (§31).** `get_context` rejects an archived org
  (`apps/api/app/security/deps.py:57`), but no deactivate/reactivate endpoint.
- **P2 — Audit history (§36).** Spine fires on `organization.created`
  (`organization/service.py`, `AuditDataClass.ROLE`); most listed events have no
  emitters because those actions have no endpoints.
- **P3 — Session-expiry + idempotency (§11).** Idempotency spine +
  `tests/test_idempotency.py`; web client never auto-replays a mutation
  (`apps/web/src/api/client.ts:67`); no expiry test tied to this flow.
- **P4 — Logout removes sensitive data / back-button (§12).** `/auth/logout` ends
  the session; client-side clearing unverified.
- **P5 — Context-switch data clearing (§28).** `setAuthHeaders` resets identity;
  full cache clearing unverified.
- **P6 — Screens X03/X04 (§34.3/34.4).** Context selection + no-access state exist
  (`apps/web/src/routes/Entry.tsx`, `auth/session.tsx`); invite-driven variants absent.

## Implemented (verified)

- **I1 — OIDC login, no local password (§6/§7/§9).** `apps/api/app/security/oidc.py:56`;
  `apps/api/app/domains/auth/router.py`. Tests `tests/test_oidc.py:33,53`.
- **I2 — No password/hash/reset stored (§7).** Enforced by architecture gate
  `PASSWORD_PATTERN` (`apps/api/scripts/check_architecture.py`).
- **I3 — One global identity, idempotent on subject (§5/§21/§22).** `oidc.py:61`;
  `AuthAccount` unique per person (`identity/models.py:45`). Test `test_oidc.py:46`.
- **I4 — External login without active role does not open a school (§9).**
  `apps/api/app/security/deps.py:42`. Test `tests/test_security.py:68`.
- **I5 — Server-derived context; saved choice ≠ authorization (§27/§28).**
  `apps/api/app/security/context.py`, `deps.py:42`; `/me/contexts` only ACTIVE
  (`identity/service.py`). Tests `test_security.py:54,74`.
- **I6 — Exactly one active school+role (§27).** `deps.py:43`.
- **I7 — Immediate revocation blocks new requests (§30).** `deps.py:51`; disabled
  account revokes session (`security/auth.py:79`). Test `test_oidc.py:76`.
- **I8 — Can't use another's context; errors don't confirm hidden records (§23/§30).**
  `deps.py:48`. Test `test_security.py:74`.
- **I9 — First owner on bootstrap (§13/§25.2).** `organization/service.py:51`.
  Test `test_organization.py:10`.
- **I10 — Child has identity, cannot log in (§37).** `StudentLoginAuthorization.login_enabled`
  defaults False (`identity/models.py:105`).
- **I11 — Weak matches never auto-merge (§32).** `oidc.py` links only on exact subject.
- **I12 — Provider-outage soft failure (§10/§40).** `auth/router.py` → `?login=failed`;
  `apps/web/src/routes/Entry.tsx` soft notice.

## Out of scope (§38 — not gaps)

Local password/change/reset, public school registration, self-service role
assignment, ordinary invite for a protected owner, child login, public profile,
auto-merge of ambiguous duplicates, support access without approval, two active
schools, unified multi-school view, rights hidden behind UI only, login via
unverified identity, sharing/permanently-active invites, revealing other schools.
Several are **actively guaranteed** by the implementation (I2, I5, I6, I10, I11).

## Open questions

1. Is the invitation model an intentional stub for a later increment, or was
   wiring dropped? Biggest single gap.
2. §25.4 "roditelj ne vidi nepovezano dete" — the `parent` child-scoping was not
   fully traced; likely enforced, worth a targeted check.
3. C1: policy/permission layer over `RoleCode`, or scoped role variants? Blocks
   §15, §19.2, §25.4, §25.5 (and PRDs 02/03/04).
4. 41-section bespoke structure vs the 27-section template — worth reconciling.
