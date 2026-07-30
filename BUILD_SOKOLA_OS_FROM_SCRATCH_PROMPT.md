# Build Prompt: SOKOLA OS, from scratch to production

> Paste everything below into a capable autonomous coding agent (or hand it to a small team). It is a
> single, self-contained specification. It reconstructs the SOKOLA OS platform described in the
> archived `SOKOLA_COMPLETE_MASTER_ARCHIVE` and, unlike that archive, which deliberately stopped at
> "portable, not production authorized", it carries the product all the way to a live, production-ready
> system. Do not skip the completion gates in Part 9; closing them is the whole point.

---

## 0. Role and operating rules for the agent

You are the lead engineer building **SOKOLA OS**, a multi-tenant SaaS for running sports clubs, dance
schools, and training organizations. Build it as a **fast modular monolith**, not a microservice mesh
and not a sprawling ERP. Work in disciplined, verifiable increments. Every increment ends green on an
automated verifier before the next begins.

Non-negotiable working rules:

- **Modular monolith.** One API, one web app, one PostgreSQL database. Domains are separated *in code*,
  not over the network. Extract a service only when a domain provably has a different load, lifecycle,
  team, or security profile, never for cosmetic tidiness.
- **Scope discipline.** Do not add capabilities outside the P0 domain list (Part 3) without an explicit
  written change record justifying a real user workflow. No gamification, no marketplace, no public API,
  no mySOKOLA, no Events ERP in the first production release, those are later, sequenced work packages
  (Part 10). Naming them does not authorize building them.
- **Every increment is provable.** Static checks (types, lint, OpenAPI/router parity, migration
  audit, tenant-boundary audit) plus real integration tests must pass. "It compiles" is not evidence.
- **Security and tenancy are built in from the first endpoint**, not bolted on. See Part 6.
- **User-facing language is Serbian (Latin) product vocabulary**; technical identifiers stay in logs and
  audit only (Part 8, glossary).

---

## 1. Product vision

SOKOLA OS is the daily operating system for a training organization. It must work perfectly on its own,
before any ecosystem layer exists. It answers, for each role:

- **Manager/Owner/Admin:** who are my members, what's scheduled, who owes money, what needs sending.
- **Trainer:** what's on today, who showed up.
- **Parent:** what's next for my child, what do I need to do, what changed, what do I owe.

Design target: a frequent task takes **at most three primary decisions** after sign-in and context
selection (a risky financial/destructive action may add exactly one safety confirmation). Fast reads
(p95 < 300 ms), fast mutations (p95 < 700 ms excluding external providers), no infinite feeds, no screen
that loads an entire history.

The long-term ecosystem (build later, in order): **Core OS → mySOKOLA (personal/family layer) →
Integrations & public API → Marketplace → Events ERP.** Keep the core clean enough that these attach as
natural extensions, not bolt-ons.

---

## 2. Technology stack

Match these unless you have a concrete reason to deviate; they are proven for this shape of product.

| Layer | Choice |
|---|---|
| Backend language | Python 3.12+, fully type-annotated, `mypy --strict` |
| Frontend language | TypeScript (strict), Node.js ≥ 22 for the build |
| Monorepo | Polyglot workspace: `apps/api` (Python, `uv`), `apps/web` (React, npm), `packages/contracts` (OpenAPI doc + generated TS client) |
| API framework | FastAPI (modular monolith; one router package per domain) |
| Validation | Pydantic v2 models on every request/response schema |
| ORM / DB | SQLAlchemy 2.0 (typed) + Alembic migrations + PostgreSQL |
| Web | React 19 + Vite + React Router (a typed API client is generated from the OpenAPI doc) |
| Shared types | The single checked-in OpenAPI 3 doc is the contract: Pydantic generates it on the api side, web consumes a generated typed client. `packages/contracts` stays dependency-free. |
| API contract | FastAPI-generated OpenAPI 3, checked in and frozen; a gate verifies router/OpenAPI parity |
| Auth (prod) | External OIDC provider (SOKOLA stores identity links + authorization context, **never** local password hashes or reset tokens) |
| Money | Integer minor units only. No floating-point money. Default currency `RSD`. |
| Async work | Transactional **outbox** + Python worker process. No direct coupling of side effects to request commits. |
| Object storage | Private-keyed provider (S3-compatible), signed/authorized retrieval only |
| Containers | Dockerfiles for api / web / worker; one `compose.m0.yml` local topology |
| CI | `ruff` + `mypy` + `pytest` + Alembic migration audit + contract parity + real integration suite |

Hard dependency rule: **new runtime dependencies default to zero.** Each addition needs a purpose,
security, and removal analysis.

---

## 3. Domain scope (P0, the first production release)

Exactly these product domains, each a FastAPI router package with `router → application service → domain
policy → SQLAlchemy repository → outbox events`:

`identity`, `auth/context`, `organization`, `people`, `groups`, `scheduling`, `attendance`, `billing`,
`payments`, `events` (light), `imports`, `communications`, `documents`, `parent`, `privacy`,
`reporting`, `operations`.

Approximate surface budget (freeze it and enforce with a gate): **~120 API operations across ~105
paths**. Growth requires a signed change record.

Dependency direction (enforced by a static audit):
- routers call only their own domain service;
- domain services use their own policies, shared `common` primitives, and SQLAlchemy repositories;
- `common` never imports a product domain;
- `contracts` is dependency-free;
- **domains never import another domain's service**: they communicate via stable records and versioned
  outbox events;
- web consumes `contracts`; it never re-implements backend authorization.

Code-health ratchet: no new service > 600 lines, no new method > 120 lines, no import cycles, no
domain→domain service import. Existing oversized units may not grow.

---

## 4. Data model

PostgreSQL via SQLAlchemy 2.0 (typed `Mapped[...]` models) with Python `enum` types. Around **48 tables /
58 enums** at P0. Reproduce this model (names are canonical `sokola*` / no legacy brand). Group them by
domain:

**Identity & access**
- `Person` (global identity; `PersonIdentityStatus`: PROVISIONAL | CLAIMED | VERIFIED | MERGED | ARCHIVED)
- `AuthAccount`, `AuthIdentifier` (maps external OIDC subject/email/phone to a Person, the *only* auth authority)
- `RoleAssignment` (`RoleCode`: OWNER, MANAGER, ADMIN, TRAINER, PARENT, STUDENT, a **closed access
  template facade only**, never a profile/credential taxonomy; `RoleScopeType`, `RoleAssignmentStatus`)
- `StudentLoginAuthorization` (separates a child's identity from login permission)
- `Invitation` (`InvitationType`, `InvitationStatus`; invitations expire and may be reissued)
- `PersonMergeRecord` (reserved, append-only merge evidence; no self-service dedup endpoint)
- `Workspace` (reserved commercial/ownership container; no subscriptions/entitlements in P0)

**Organization**
- `Organization` (`OrganizationType`: SCHOOL, SPORTS_CLUB, DANCE_SCHOOL, COURSE_PROVIDER,
  EVENT_ORGANIZER, BUSINESS, OTHER; default timezone), `Branch`, `Hall`, `Program`
- `OrganizationMembership`, `MembershipPeriod` (`MembershipStatus`, `MembershipPeriodStatus`)

**People / guardianship**
- `GuardianRelationship` (`GuardianRelationshipType`), `GuardianOrganizationAccess` (`GuardianAccessStatus`)
- `ExternalPersonReference`

**Groups**
- `Group` (`GroupCapacityMode`), `GroupMembership`, `GroupMembershipPeriod` (`GroupMembershipEndReason`)

**Scheduling & attendance**
- `SessionSeries` (`SessionSeriesFrequency`; stores local time + timezone), `Session`
  (`SessionStatus`, `SessionChangeReasonCode`, `SessionCancellationReasonCode`; generated sessions store
  UTC, single-instance edits are session *changes*, never destructive series edits)
- `AttendanceRecord` (`AttendanceStatus`, `AttendanceOverrideReasonCode`; batch carries an
  `attendanceVersion` for optimistic concurrency)

**Billing & payments**
- `BillingRun` (`BillingRunStatus`), `BillingRunItem`, `Charge` (`ChargeStatus`, `ChargeSourceType`,
  `ChargeCancellationReasonCode`; `amountDueMinor`), `DiscountType`
- `PaymentRecord` (`PaymentRecordStatus`, `PaymentMethod`, `PaymentVoidReasonCode`; ledger record,
  voidable, never edited in place; partial → PARTIALLY_PAID; overpayment rejected at P0)
- `FinancialReviewCase` (`FinancialReviewType`, `FinancialReviewStatus`)

**Events (light)**
- `Event` (`EventType`, `EventCategory`, `EventStatus`, `EventAudienceType`, `EventCapacityMode`)
- `EventAudienceBranch`, `EventAudienceGroup`, `EventAudienceMembership`
- `EventRegistration` (`RegistrationStatus`, `CancellationReasonCode`; registration is child-membership
  based; cancellation ≠ deletion)

**Imports**
- `ImportBatch` (`ImportType`, `ImportStatus`), `ImportRow` (`ImportRowStatus`), `ImportMutation`
  (`ImportMutationType`, `ImportResolutionAction`), preview/review before any invitation is sent

**Communications**
- `Announcement` (`AnnouncementStatus`, `AnnouncementTargetType`), `AnnouncementAudience`,
  `AnnouncementRecipient`, `AnnouncementRead`, `AnnouncementDeliveryStatus` (recipient set is snapshotted
  with a hash; publish only if the snapshot still matches)

**Documents**
- `Document` (`DocumentCategory`, `DocumentVisibility`, `DocumentLifecycleStatus`, `DocumentScanStatus`),
  `DocumentAccessLog` (`DocumentAccessAction`), PDF/JPG/PNG ≤ 10 MB, private keys, signed retrieval,
  malware scan, **no medical categories**

**Privacy**
- `ConsentRecord` (`ConsentPurpose`, `ConsentStatus`), `DataRequest` (`DataRequestType`,
  `DataRequestStatus`), `DataRequestEvent`

**Platform**
- `AuditLog` (`AuditDataClass`), `OutboxMessage` (`OutboxStatus`), `IdempotencyRecord`, `RecordStatus`

Every tenant-scoped table carries the organization key and is filtered server-side. Amounts bounded to
PostgreSQL `Integer` minor units at P0. Deliver as ordered, reversible Alembic migrations (the archive had
14 migration steps building the schema up domain by domain; mirror that incremental discipline, and keep
autogenerated migrations reviewed, never blindly applied).

---

## 5. API contract

- One OpenAPI 3 document (`openapi/sokola-p0-v1.openapi.json`), title "SOKOLA OS P0 API", generated from
  the FastAPI app (Pydantic schemas + route metadata) and checked into the repo.
- Tags & rough counts: schedule 12, events 12, organizations 11, privacy 11, groups 9, communications 8,
  imports 7, operations 7, people 6, documents 6, billing 5, identity 5, attendance 4, charges 4,
  financial-reviews 3, health 3, parent 3, payments 2, internal 2, me 1.
- A release gate verifies **every router operation** against the checked-in document: the freshly
  generated OpenAPI must match it (matching route, success status, authorization classification, and
  idempotency requirement). Drift between generated and committed OpenAPI, orphan router ops, or orphan
  OpenAPI paths **fail the build**. No second API description and no GraphQL at P0; the only codegen
  permitted is the typed web client generated from this one OpenAPI doc.
- Standard cross-cutting contract for every endpoint: pagination on all growing collections, consistent
  error envelope (no stack traces / provider names / internal DTO terms leaked), idempotency keys on
  financial/registration/import/notification mutations, optimistic-version / snapshot-hash echoes where
  listed above.

---

## 6. Security & multi-tenancy (build in from endpoint #1)

Isolation rule: **an organization may never read a person just because that person exists globally.** A
person becomes visible only through an explicit organization-scoped relationship (membership, group
membership, guardian access, role assignment).

Server-derived context: the client may *request* a context but never *grant* one:
1. Authenticate via OIDC. 2. Resolve global `Person` + `AuthAccount`. 3. `/me/contexts` returns only
active membership-role combinations. 4. Client selects one. 5. Requests carry a context token/session
reference. 6. Server resolves membership/org/role/scope from the DB. 7. **Every referenced resource is
re-checked against the active organization on every read and write.**

Forbidden: client-supplied role names; trusting client tenant IDs; a global `isAdmin` flag; a user table
with one `schoolId`+`role`. A dev-only header adapter (`x-sokola-person-id`,
`x-sokola-role-assignment-id`, behind `ALLOW_INSECURE_DEV_AUTH=true`) is allowed **for local dev only**
and must be impossible to enable in production.

Required production controls (all in scope for completion): OIDC login + session inactivity expiry,
rate limiting / brute-force protection, restricted CORS, secrets outside the repo, TLS everywhere,
provider-managed encryption for DB/backups/object storage, daily backups retained 30 days with a tested
restore, audit logs for relationship/role/payment/document/data-request changes, EU-region hosting with
documented subprocessors. Tenant-aware cache keys, per-org storage prefixes, per-tenant rate limits and
quotas, and **cross-tenant negative tests** are mandatory.

---

## 7. Core engineering invariants

- **Idempotency:** repeated request + same key → same result; same key + different params → rejected.
  Applies to payments, refunds/voids, event registration, billing runs, payment records, announcements,
  imports. Keys stored per organization + operation.
- **Outbox:** in one transaction, write the business change *and* the domain event to `OutboxMessage`,
  then commit both. A worker delivers email, rebuilds read models, calls partners. Side effects never
  ride inside the primary business transaction. Versioned event envelopes for anything external.
- **State machines (explicit, per domain, no generic workflow engine):** ended membership reactivates
  by opening a new period, not by deleting history; cancelled registration reactivates before deadline;
  attended/no-show cannot be silently cancelled; payments void, never overwrite; imports require
  preview → review → apply; invitations expire and reissue.
- **Money/time:** integer minor units, ISO currency, no fiscal invoices at P0, no payment-gateway
  capture at P0 (external payment records only); recurring schedules store local time + timezone,
  generated sessions store UTC.
- **Practical CQRS without a framework:** commands mutate canonical data; query services return
  optimized read models; dashboards never assemble 20 domains in the browser; read models are
  rebuildable; canonical financial data lives only in billing/payments.
- **Feature flags ≠ authorization:** a user must pass *both* the flag and the permission check.

---

## 8. Web product experience

Role-based shells, **not** one universal dashboard with hidden items. Each role gets its own home, at
most **five** primary destinations, and one dominant next action.

- **Manager:** Today · People & groups · Schedule · Money · More (communications, documents, imports,
  reports, setup, Events Light).
- **Trainer:** Today · Schedule · Groups · Messages · Profile/context. Attendance reachable from Today
  in one action, savable in one deliberate action after exception edits.
- **Parent:** Home · Schedule/activity · Events · Finances · More (messages, documents, privacy,
  profile/context). Home answers: what's next, what needs action, what changed, which child is active.

**Semantic design system** (small, repo-owned, zero heavy UI-kit dependency): a `design-tokens.css`
splitting brand/neutral primitives from semantic roles (surface/border/text/action, success/warning/
error/info, focus-ring, 44px min target, spacing/type/radius/elevation, motion + reduced-motion). Product
components consume semantic aliases only, **never raw color values in TSX**. Shared primitives:
ProductShell, RoleNavigation, ContextSwitcher, PageHeader, primary/secondary actions, Field/Select/
Checkbox, StatusBadge (status by text+tone, never color alone), ResponsiveDataList (table on wide,
labelled stacked cells on mobile), Pagination, SystemState/LoadingState, InlineNotice, ConfirmDialog
(native dialog + focus restoration), RouteAnnouncer (polite route announcement + focus to main). A new
primitive is allowed only if it removes duplication in ≥2 surfaces or is required for accessibility/state
safety.

**Responsive navigation:** persistent sidebar > 920px (`aria-current`, icon+label+description); at
≤ 920px a sticky header + fixed bottom bar with exactly five 44px targets, safe-area insets, no
horizontal-scroll nav. Navigation availability is never permission, re-validate on the server.

**Shared state & recovery contract.** Every non-normal state answers: *what happened / what was
preserved / what is the safe next action.* States: loading (`aria-busy`, no fake values), empty
(distinguish no-records vs no-filter-results vs no-context vs role-hidden), network error (say saved data
& login are unchanged; controlled retry; never blind re-mutate), permission denied (reveal nothing;
offer context change; never imply URL editing grants access), stale/version conflict (reload canonical;
require review & reapply; never silent overwrite), partial background failure (separate canonical success
from secondary failure; don't re-invite the primary action), manual recovery (freeze unsafe auto-retry;
show canonical status; documented operator path), success (confirms the *business* outcome, not the
click; financial/destructive/publish require deliberate confirmation showing scope/count/amount/audience).

**Accessibility target WCAG 2.2 AA:** visible focus, skip link, landmarks, 44px targets, text alongside
icon+color, `aria-live` route/state, programmatic field-error association, native dialog semantics,
reduced motion. This must be validated live on real devices/AT for completion, not just asserted in code.

**Product language:** Serbian Latin, one noun/verb per task across all roles (e.g. *škola* not tenant,
*prisustvo* / *sačuvaj prisustvo*, *obračun članarina* / *pregled obračuna*, *podaci su promenjeni u
međuvremenu* for a version conflict, *potrebna ručna provera* for manual recovery). Parent/child surfaces
never reveal staff notes, another child's data, raw identifiers, or hidden moderation signals.

---

## 9. The eight critical journeys (P0 acceptance backbone)

Each is role-specific, wired to real API operations through one shared adapter that maps outcomes to the
canonical UI states (401/403 → permission, 409 → conflict/review, missing/5xx mutation response →
**manual recovery, never automatic replay**). Each routine happy path = exactly **three** primary
actions; safety branches may exceed it.

1. **Manager creates a one-off session**: Raspored → Novi termin → Sačuvaj termin. Adapter auto-calls
   conflict preview before the idempotent create; a conflict keeps the draft.
2. **Trainer records attendance**: Danas → Izaberi termin → Sačuvaj prisustvo. Load roster +
   `attendanceVersion`, default all PRESENT, send only exceptions, one idempotent PUT; 409 → reload &
   review, never silent overwrite.
3. **Parent registers child/children**: Događaji → Izaberi dete/decu → Potvrdi prijavu. Only children
   from active guardian access; one command may carry multiple child IDs.
4. **Parent cancels a registration**: Događaji → Otkaži prijavu → Potvrdi otkazivanje. Cancellation ≠
   deletion; history stays canonical; no automatic-refund promise.
5. **Manager posts a billing run**: Finansije → Pregledaj obračun → Proknjiži obaveze. Exact preview
   hash sent to create; create and post have separate idempotency keys; unknown outcome → manual recovery.
6. **Administrator records a payment**: Izaberi zaduženje → Evidentiraj uplatu → Sačuvaj uplatu.
   External-payment record, not a provider capture; missing response → unknown-commit verification first.
7. **Manager publishes an announcement**: Komunikacija → Pregledaj primaoce → Objavi poruku. Recipient
   preview returns count + snapshot hash; publish succeeds only if both still match; delivery failure is
   a partial state, not a reason to re-publish.
8. **Manager creates a provisional person**: Ljudi → Dodaj osobu → Sačuvaj osobu. Possible-duplicate is
   a deliberate safety branch requiring explicit confirmation + written reason.

---

## 10. Verification harness (ship these alongside the code)

Automate, and run in CI on every change:

- `ruff` + `mypy --strict`; SQLAlchemy metadata check + `alembic check` (models ↔ migrations in sync);
  migration static audit (naming, reversibility, no destructive drift).
- OpenAPI ↔ router parity gate: regenerate the doc, diff against the committed one, orphans fail.
- Architecture/simplicity fitness: dependency-direction audit, service/method size ratchet, surface-count
  budget, dependency allowlist, no domain→domain imports, no local-password schema.
- Tenant-boundary audit: static + **real cross-tenant HTTP negative tests** (org A cannot read/write org
  B through any endpoint).
- Unit tests per domain policy + service; integration suite against real PostgreSQL.
- Web: production build, static accessibility interaction checks, bundle/performance baseline capture.
- Privacy-safe analytics: task-outcome events only, free of unnecessary child/person data.
- Provider contract smoke: storage upload/checksum/download/idempotency/callback.

---

## 11. Taking it to completion (the gates the archive left open)

The reference archive stopped at "portable PASS / not production authorized." **Completion means closing
all of these with retained evidence**: this section is the difference between a demo and a product:

1. **Real database:** `alembic upgrade head` on the release machine; clean-DB and copied-data migration +
   seed runs on the target PostgreSQL version, with a downgrade path proven for each migration.
2. **Real auth:** OIDC token / introspection / claim-mapping / revocation / provider-outage tests green.
   Replace the dev header adapter; make it un-enableable in prod.
3. **Real HTTP tenant/role/guardian isolation suite** against SQLAlchemy + PostgreSQL, including
   cross-tenant attack attempts.
4. **Concurrency:** billing, capacity, scheduling, and payment race tests; post-commit interruption /
   unknown-commit recovery proven.
5. **Outbox at load:** multi-worker claim, retry, stale-lease takeover, dead-letter reconciliation.
6. **Provider adapters:** real storage (signature inspection, malware quarantine, signed download),
   email, event/webhook delivery, with outage/replay evidence and idempotency.
7. **Infra:** `docker compose up --build --wait` (and/or target orchestration) green; image + SBOM scan
   with **no unresolved high/critical findings**, immutable digests.
8. **Edge:** distributed rate limiting / WAF configured with bypass/abuse tests.
9. **Observability:** structured logs, metrics, dashboards, alert delivery, and one exercised incident
   runbook. Define SLOs + error budgets per key flow (sign-in success, attendance-record success,
   financial-posting success, key-screen latency, message-delivery accuracy, recovery time), manage
   reliability by numbers, not by "it won't go down."
10. **Backup/restore:** timed isolated-restore rehearsal with reconciliation and sign-off.
11. **Frontend quality:** responsive + WCAG 2.2 AA validated on real desktop/mobile/assistive tech;
    representative load test.
12. **Sign-off:** founder/developer/security/operations acceptance recorded.

Only when all twelve carry evidence is the product production-authorized. Ship it, run a real pilot with
a live club, and let pilot metrics (time-to-first-value, task step counts, completion rate, attendance-
recording regularity, receivables collected) calibrate the next work package.

---

## 12. What NOT to build yet (red list)

Without a formal decision record backed by a named customer workflow, quantified value, security/
retention analysis, acceptance tests, and a rollback plan, do **not** add: microservices / Kubernetes /
Kafka / service mesh; a generic workflow / rules / form-builder / custom-field engine; event sourcing as
the primary write model; GraphQL beside REST; native mobile / offline sync; a second auth or identity
model; local passwords / reset / MFA implementation; marketplace / partner portal / public API over
ORM models; gamification, leaderboards, virtual currency, wallet, or blockchain achievements;
multi-currency ledger or payment-gateway capture before finance requirements are contracted; tenant-
specific code forks; any AI feature without a clear user problem and a human-review boundary.

After P0 ships and a pilot validates it, open the later layers **in this order**: mySOKOLA identity/
profile/portfolio → ethical gamification (progress/achievements/quests, age-based, anti-abuse, no
public minor leaderboards) → ecosystem API & integrations (`/public/v1`, OAuth clients, scopes, webhook
registry, sandbox, metering) → marketplace (verified directory → request/match → booking → payments →
trust network) → Events ERP (venues/zones/sessions/staffing/ticketing/POS/sponsors/settlement). Each is
its own work package with its own scope lock, acceptance matrix, and rollback plan. A roadmap entry is
never feature authorization.
```
```

---

**Definition of done for this prompt's execution:** a live, multi-tenant SOKOLA OS with the domains in
Part 3, the data model in Part 4, the eight journeys in Part 9 working end-to-end against real
PostgreSQL and OIDC, all twelve completion gates in Part 11 closed with evidence, and a green CI pipeline
running the Part 10 harness on every change.
