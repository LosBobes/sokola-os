---
name: prd-align
description: Parse a SOKOLA product document (a PRD following the 27-section Serbian template, or the MVP/roadmap docs) and align it against what the app actually implements — backend domains, OpenAPI contract, web routes, DB migrations and tests — then report per-requirement coverage as Implemented / Partial / Missing / Conflict with file evidence. Use when the user drops new SOKOLA docs, asks to "align the docs with the app", "check PRD coverage", "what's missing vs the spec", or "parse this product doc against the current build".
---

# PRD Align: turn a product doc into a coverage verdict against the real app

The SOKOLA product docs are structured PRDs written to a fixed 27-section
Serbian template. This skill parses one (or several) and checks it against the
**implementation as it actually exists** — never against memory or against the
doc's own claims. Output is a per-requirement alignment report an engineer can
act on.

Docs are authoritative for *intent*; the code + OpenAPI spec are authoritative
for *reality*. When they disagree, that disagreement is the finding.

## Inputs

- **Docs root** — default `~/Downloads/SOKOLA`. Contains `prd/00-…16-*.md`,
  plus `Vizija.md`, `Roadmap.md`, `Mapa-ekrana-MVP.md`, design specs under
  `Dizajn-ekrana-*`, and the template in `Templejti/PRD-templejt.md`. If the
  user names a different path or pastes a doc, use that.
- **App root** — this repo (`apps/api` FastAPI backend, `apps/web` React
  frontend, `openapi/` contract, `apps/api/**/versions` migrations).

If the docs root does not exist, ask the user for the path once, then proceed.

## Procedure

### 1. Capture the app surface (do this first, every time)

Run the helper so alignment is grounded in current reality:

```
.claude/skills/prd-align/scripts/app-surface.sh
```

It prints backend domains, OpenAPI paths + methods + operationIds, web routes,
and DB migrations. Everything downstream references this output.

### 2. Select and parse the PRD

If the user named a doc, use it. Otherwise ask which `oblast` / PRD to align,
or offer to sweep all of `prd/`.

Read the PRD and extract its frontmatter `oblast`, `status`, `verzija`. Then
pull the sections that carry checkable requirements (numbers match
`Templejti/PRD-templejt.md`; a couple of docs are off-by-one in early
sections — match by heading text, not just number):

- **§5 Korisnici i prava** — roles × can/can't. Each cell is an authz rule.
- **§6 Obim** — in-scope vs explicitly out-of-scope (do NOT flag out-of-scope
  items as "missing").
- **§8 Glavni korisnički tok** — the happy path; should map to endpoints.
- **§10 Poslovna pravila** — business rules; each must be single-valued and
  verifiable in `service.py`.
- **§11 Stanja i statusi** — state machine; check against `enums.py`.
- **§12 Podaci** — fields in / shown / hidden; check against `models.py` +
  `schemas.py` (hidden fields must not leak into response schemas).
- **§13/§14/§15/§16 Deca/privatnost, obaveštenja, fajlovi, finansije** — only
  if the checkbox says "Da"; these carry the sensitive rules.
- **§17 Ekrani** — screens × role × action; check against web routes.
- **§19 Trag promena** — audit expectations; check against the platform
  audit/outbox spine.
- **§22 Kriterijumi prihvatanja** — the Ako/Kada/Onda acceptance criteria;
  each should have a test.
- **§23 Obavezne provere** — the mandatory checklist (tenant isolation,
  idempotency, network-safety, audit).

### 3. Map to the app

Use `references/domain-map.md` to jump from `oblast` to the owning backend
domain(s) and web route(s). Then gather evidence:

- Endpoints: `router.py` of the domain **and** the matching OpenAPI paths.
- Data: `models.py` / `schemas.py` (does §12 have a home? do "hidden" fields
  stay out of read schemas?).
- Rules & states: `service.py` / `enums.py` for §10 and §11.
- UI: `apps/web/src/routes/**` for §17.
- Tests: `apps/api/tests/**` for §22/§23.

If the map's backend cell is **(none)**, don't trust it blindly — grep the
codebase for the concept first; it may live inside a neighbouring domain.

### 4. Classify every extracted requirement

| Verdict | Meaning |
|---|---|
| **Implemented** | Endpoint/field/rule/screen/test exists and matches intent. Cite the file. |
| **Partial** | Exists but incomplete (e.g. endpoint present, business rule from §10 not enforced; or read schema leaks a §12-hidden field). |
| **Missing** | No implementation found and it's in-scope per §6. |
| **Conflict** | Code does something the PRD forbids, or contradicts a §10 rule / §5 permission. Highest priority. |
| **Out of scope** | Listed under §6 "Ne ulazi" — record but never count as a gap. |

Cross-cutting rules that are easy to get wrong and worth an explicit check on
every PRD: **tenant isolation** (school A cannot see school B),
**server-side authorization** (§5 enforced in service, not just UI),
**idempotency** (repeat request makes no duplicate), and **audit trail** (§19).
These recur in §23 of every PRD and in this repo's platform spine.

### 5. Report

Produce a Markdown report, most severe first (Conflict → Missing → Partial →
Implemented). For each requirement: the verdict, a one-line rationale, and a
`file:line` citation. Structure:

```
# Alignment: <PRD name> (oblast: <x>, v<verzija>) vs app @ <git short sha>

## Summary
<N implemented / N partial / N missing / N conflict>, one-paragraph verdict.

## Conflicts        (fix first — code contradicts the spec)
## Missing          (in-scope, not built)
## Partial          (built, but a rule/field/state is unmet)
## Implemented      (verified, with evidence)
## Out of scope     (per §6 — not gaps)
## Open questions   (PRD §25 items still unresolved, or ambiguities you hit)
```

Offer to write the report to `docs/alignment/<oblast>.md` in the repo if the
user wants it persisted. When sweeping multiple PRDs, also emit a one-line-per-
PRD coverage matrix at the top.

## Rules of the road

- **Evidence or it didn't happen.** Every Implemented/Partial verdict needs a
  real `file:line`. If you can't cite it, it's Missing or an Open question.
- **Never edit the product docs** unless explicitly asked — this skill reads
  them. It may write alignment reports into the app repo.
- **Don't fix as you go.** Alignment is a read/report pass. If the user wants
  fixes, do them as a separate, explicit step after they see the report.
- **Serbian docs, English code.** Concept names differ across the language
  boundary (`clanarina`→charge/billing, `prisustvo`→attendance,
  `saglasnost`→consent). Translate intent; match on behaviour, not literal
  strings.
- **Scope discipline.** §6 "Ne ulazi u ovu verziju" and PRDs whose `status`
  is `nacrt` (draft) are not commitments — note them, don't score them as gaps.
