# Alignment: Početni ekrani i navigacija

**oblast:** `navigacija-i-pocetni-ekrani` · status not marked `odobreno` · **app @ `3c2d074`**

## Summary

**Partial — this is a web concern and the skeleton exists.** Role-based home
screens and the app shell are built; the full navigation surface (the "Više"
menu, per-role completeness, context header) is partly there.

## Implemented (verified)

- **I1 — Role-based home screens.** `apps/web/src/routes/RoleHome.tsx` gives each
  role one dominant next action (PARENT → events, TRAINER → schedule, staff →
  manager surfaces).
- **I2 — App shell + context header.** `apps/web/src/components/shell.tsx` +
  `shell.css`; the active school/role is surfaced (PRD 01 §27 requires this in the
  header).
- **I3 — Tenant-first entry.** `apps/web/src/routes/Entry.tsx` (school code →
  login → context), including the no-tenant-access safe state
  (`apps/web/src/auth/session.tsx`).
- **I4 — Manager sub-routes.** `manager/People|Schedule|Money|Attendance|Communications.tsx`.

## Partial / Missing

- **M1 — "Više" / overflow menu (Dizajn-ekrana-07-Pristup-i-meni-Vise).** Not
  built as a distinct surface.
- **M2 — Per-role completeness.** Only manager + parent(events) + trainer(home)
  routes exist; trainer attendance flow, parent money/schedule views are missing
  (tracked in the relevant domain reports).
- **M3 — Context switcher UI.** Switching between schools/roles (PRD 01 §28) — the
  backend `/me/contexts` exists; the in-app switcher completeness is unverified.

## Plan

Wave 4 polish, evolving alongside the domain routes each home links to. Low risk,
high perceived-completeness payoff once Wave 1–2 backends exist to navigate to.

## Open questions

1. Frontmatter not `odobreno` — confirm v1.0 scope.
2. Design specs live under `~/Downloads/SOKOLA/Dizajn-ekrana-*`; align the shell
   against `Dizajn-ekrana-07` for the menu.
