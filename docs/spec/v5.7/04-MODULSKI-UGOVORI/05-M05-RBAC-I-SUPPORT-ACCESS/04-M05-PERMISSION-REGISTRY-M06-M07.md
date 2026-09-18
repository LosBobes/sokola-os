---
tip: permission-registry
modul-id: M05
status: SPEC_CANDIDATE
revizija: "1.0"
datum: 2026-09-09
obuhvat: [M06, M07]
---

# M05 — kanonski permission registry za M06 i M07

Ovaj dokument zatvara permission ključeve vlasničkih modula M06/M07. `A` je default role binding uz sve tenant/resource/purpose guardove; `S` dodatno zahteva navedeni subject basis; `—` je deny. Svi write-i su online-only. Permission ne zamenjuje ACTIVE M06 membership, M07 link, M04 entitlement ili M17 purpose.

## M06 — ljudi i školska članstva

| Permission key | Risk | OWNER | MANAGER | LIMITED_ADMIN | INSTRUCTOR/SUBSTITUTE | GUARDIAN | PAYER | Scope, guard i delegacija |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `school.people.basic.view` | HIGH | A | A | S | S | S | — | Limited samo explicit grant; staff samo aktivno dodeljeni roster; Guardian samo sebe i ACTIVE linked child; bez globalne liste. |
| `school.people.contact.view` | CRITICAL | A | A | — | — | S | — | Owner/Manager purpose-bound; Guardian samo sopstveni kontakt, ne kontakt druge odrasle; ROLE_ONLY. |
| `school.people.manage` | CRITICAL | A | A | — | — | — | — | Create/edit osnovnog Person/profile zapisa; ROLE_ONLY. |
| `school.memberships.manage` | CRITICAL | A | A | — | — | — | — | M06 lifecycle + last-owner guard; ROLE_ONLY. |
| `school.participant.safety.view` | CRITICAL | S | S | — | S | S | — | Minimalni safety podatak; staff samo dodeljeni aktivni termin/roster, Guardian samo linked child i aktivan purpose; svaki read auditovan; bez direct grant-a. |
| `school.people.sensitive_identifier.manage` | CRITICAL | A | A | — | — | — | — | Capability default OFF, M17 purpose+retention, step-up; ROLE_ONLY. |
| `school.people.sensitive_identifier.reveal` | CRITICAL | A | A | — | — | — | — | Poseban step-up, purpose i audited reveal; ne implicira manage; ROLE_ONLY. |
| `school.people.merge_local` | CRITICAL | A | A | — | — | — | — | Samo tenant-local merge, step-up, preflight svih referenci; ROLE_ONLY. |

M28 Basic ne prikazuje safety note ili child contact samo zato što GUARDIAN binding postoji; potreban je poseban M28 surface/capability koji u H1 Basic nije aktivan.

## M07 — porodice, staratelji i platioci

| Permission key | Risk | OWNER | MANAGER | LIMITED_ADMIN | STAFF | GUARDIAN | PAYER | Scope, guard i delegacija |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `school.families.view` | CRITICAL | A | A | — | — | S | S | Guardian/Payer samo sopstveno minimalno članstvo i povezani subject; nikad druge odrasle/kontakte; ROLE_ONLY. |
| `school.families.manage` | CRITICAL | A | A | — | — | — | — | Family lifecycle; ROLE_ONLY. |
| `school.guardians.view` | CRITICAL | A | A | — | — | S | — | Guardian samo sopstvene ACTIVE/PENDING linkove i minimalni child ref; ROLE_ONLY. |
| `school.guardians.manage` | CRITICAL | A | A | — | — | — | — | Request/approve/reject/revoke uz distinct approver; ROLE_ONLY. |
| `school.guardians.primary_contact.manage` | CRITICAL | A | A | — | — | — | — | Primary designation; step-up; ROLE_ONLY. |
| `school.payers.view` | CRITICAL | A | A | — | — | — | S | Payer samo sopstveni payer basis i minimalni finance subject ref; ROLE_ONLY. |
| `school.payers.manage` | CRITICAL | A | A | — | — | — | — | Payer link verification/revoke; ROLE_ONLY. |
| `school.payers.primary.manage` | CRITICAL | A | A | — | — | — | — | Primary payer designation; step-up; ROLE_ONLY. |

Guardian role ne dobija payer prava; Payer role ne dobija guardian/child profile, attendance, schedule, document, event ili communication pravo. Isti account sa obe odvojene role prolazi svaki subject basis nezavisno.

## Policy validation

Publish mora odbiti wildcard, implicitni OWNER bypass, direct grant za bilo koji CRITICAL red iz ovog dokumenta, Guardian/Payer binding bez aktivnog odgovarajućeg M07 basis-a, staff child read bez aktivnog assignment scope-a, i svaki offline write. Support nema default binding; odobreni support grant ne sme uključiti sensitive identifier reveal, safety content, family graph ili guardian/payer evidence.

