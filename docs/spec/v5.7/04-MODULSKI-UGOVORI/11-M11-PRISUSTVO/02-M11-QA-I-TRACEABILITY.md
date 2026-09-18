---
tip: qa-traceability
modul-id: M11
status: SPEC_CANDIDATE
revizija: "1.2"
datum: 2026-09-08
obavezni-scenariji: 78
---

# M11 — QA i traceability

Fiksirani clock; dva tenant-a; occurrence sa 20 i 500 participant-a; owner/manager/instructor/substitute/guardian/payer; dva browser profila i dva prava DB transaction workera. `PAR` nije sekvencijalna simulacija.

| ID | Scenario | Očekivanje |
|---|---|---|
| M11-QA-001 | Open 31 min pre starta. | 409 too early. |
| M11-QA-002 | Open tačno 30 min pre. | DRAFT + frozen roster + UNRECORDED. |
| M11-QA-003 | Open retry. | Isti session; bez duplicate. |
| M11-QA-004 | Roster as-of start. | Samo efektivni M09 enrollment-i. |
| M11-QA-005 | Ispis posle starta. | Entry ostaje. |
| M11-QA-006 | Upis posle starta. | Entry nije dodat. |
| M11-QA-007 | Server initial records. | Svi UNRECORDED, nikad PRESENT. |
| M11-QA-008 | UI all-present predlog bez confirm-a. | Nema server mutacije. |
| M11-QA-009 | Navigacija/timeout sa draftom. | Nema auto-submit. |
| M11-QA-010 | Explicit all-present confirm. | Svi PRESENT + CONFIRMED. |
| M11-QA-011 | Jedan ABSENT, jedan LATE. | Tačna mapa/count i corrections. |
| M11-QA-012 | Nedostaje roster entry u payload-u. | 409, potpuni rollback. |
| M11-QA-013 | Dupli/tuđ entry. | 409/404 safe. |
| M11-QA-014 | Stale roster digest. | 409. |
| M11-QA-015 PAR | Identični paralelni confirm-i. | APPLIED + ALREADY_EQUIVALENT. |
| M11-QA-016 PAR | Različiti paralelni confirm-i. | Jedan uspeh, drugi 409. |
| M11-QA-017 | Confirm retry isti key. | Isti receipt, jedan outbox. |
| M11-QA-018 | Isti key, promenjen status. | 409 idempotency reuse. |
| M11-QA-019 | LATE bez minutes. | Dozvoljeno. |
| M11-QA-020 | LATE minutes 0/preko duration. | 422. |
| M11-QA-021 | PRESENT sa minutes_late. | 422. |
| M11-QA-022 | ABSENT nije EXCUSED. | Nema implicitnog statusa/pravdanja. |
| M11-QA-023 | Ordinary correction sa reason/version. | Uspeh + append correction. |
| M11-QA-024 | Ordinary correction bez reason. | 422. |
| M11-QA-025 PAR | Dve correction različitih record-a. | Obe uspevaju. |
| M11-QA-026 PAR | Dve correction istog record-a. | Jedna uspeva, druga version conflict. |
| M11-QA-027 | Correction tačno pre deadline-a. | Dozvoljena prema server clock-u. |
| M11-QA-028 | Correction tačno na/posle deadline-a. | 409 locked. |
| M11-QA-029 | Lazy materialization lock-a. | Session postaje LOCKED atomski. |
| M11-QA-030 | Admin after lock bez permission. | 403. |
| M11-QA-031 | Admin after lock bez step-up. | 401. |
| M11-QA-032 | Admin after lock sa guardovima/reason. | Correction, session ostaje LOCKED. |
| M11-QA-033 | Unlock zahtev. | Nepostojeća/nedozvoljena komanda. |
| M11-QA-034 | Instructor aktivno dodeljen. | Može view/record tu grupu. |
| M11-QA-035 | Assignment istekao pre sync-a. | REJECTED_AUTH/SYNC_FAILED. |
| M11-QA-036 | Instructor druga grupa. | 404/403 bez leak-a. |
| M11-QA-037 | Cross-tenant session UUID. | Safe 404. |
| M11-QA-038 | Guardian admin session endpoint. | Odbijeno; samo M28 child projection. |
| M11-QA-039 | Payer attendance. | Odbijeno. |
| M11-QA-040 | Offline lease validan. | Scope samo actor/school/session do min deadline-a. |
| M11-QA-041 | Lease >issued+12h pokušaj. | Server cap. |
| M11-QA-042 | Lease preko occurrence+4h. | Server cap. |
| M11-QA-043 | Lease preko session absolute expiry. | Server cap. |
| M11-QA-044 | Offline confirm → reconnect. | PENDING→SYNCED samo posle receipt-a. |
| M11-QA-045 | Mrežni 5xx. | Ostaje pending/retry sa istim key-em. |
| M11-QA-046 | Lease expiry pre reconnect-a. | SYNC_FAILED; nema auto-write. |
| M11-QA-047 | Session revoke pre reconnect-a. | SYNC_FAILED + local purge. |
| M11-QA-048 | School membership revoke. | Sync denied fail-closed. |
| M11-QA-049 | Tenant switch. | Queue/cache/key odmah obrisani. |
| M11-QA-050 | Logout/session expiry/logout-all. | Isto purge bez mreže. |
| M11-QA-051 | Drugi korisnik na uređaju. | Ne može pročitati/dekriptovati prethodni roster. |
| M11-QA-052 | Offline payload inspection. | Samo dozvoljeni minimalni fields. |
| M11-QA-053 | Service-worker push/log. | Nema imena/statusa deteta. |
| M11-QA-054 | Disjoint offline record changes. | Obe se mogu merge-ovati uz važeće versions. |
| M11-QA-055 | Same-record offline stale change. | SYNC_FAILED conflict; no overwrite. |
| M11-QA-056 | Reauth posle failed, novi lease/base. | Samo explicit retry vraća PENDING. |
| M11-QA-057 | Finance/document komanda u M11 queue. | Odbijena pre slanja/na serveru. |
| M11-QA-058 | Max 500 roster. | Uspeh u limitu. |
| M11-QA-059 | 501 roster. | Eksplicitna 422/limit greška, bez truncation. |
| M11-QA-060 | M09/M10 outage pri open-u. | 503, nema partial session-a. |
| M11-QA-061 | Audit/outbox failure. | Business change rollback. |
| M11-QA-062 | Outbox payload. | Opaque ID/count; nema PII. |
| M11-QA-063 | List count/cache. | Tenant/subject guard pre total/cache. |
| M11-QA-064 | Authorization revoke između check/commit. | Precommit recheck rollback. |
| M11-QA-065 | Status enum schema. | Tačno UNRECORDED/PRESENT/ABSENT/LATE. |
| M11-QA-066 | Sync enum schema. | Tačno PENDING_SYNC/SYNCED/SYNC_FAILED, odvojeno. |
| M11-QA-067 | Attendance confirm. | Ne kreira/menja M12 Obligation. |
| M11-QA-068 | Attendance correction. | Ne menja M09 enrollment ili M10 occurrence. |
| M11-QA-069 | HTML/BiDi/control u reason/display. | Reason je Code64; display sanitized u M06 projekciji. |
| M11-QA-070 | Performance fixture 100 entries. | Meri cilj; rezultat priložen implementacionom DoD-u. |
| M11-QA-071 | Receipt/log inspection. | Nema raw idempotency key/token/PII. |
| M11-QA-072 | DB school mismatch FK. | Baza odbija. |
| M11-QA-073 | Uređaj offline pređe `display_expires_at`, lease još traje. | Roster imena/status mapa nisu vidljivi; samo neutralan locked-unsynced indikator. |
| M11-QA-074 | Isti account online pre session/lease expiry traži recovery. | Novi auth/tenant/assignment/roster/version check prethodi prikazu diff-a; nema auto-write-a. |
| M11-QA-075 | Session absolute expiry dok postoji zaključan draft. | Lokalni queue, prikaz i key se brišu bez mreže; recovery preko nove sesije nije moguć iz starog payload-a. |
| M11-QA-076 | Remote revoke dok je telefon u airplane mode-u. | Nema lažne remote-wipe tvrdnje; prikaz se zaključava najkasnije na lokalnom display expiry-ju, reconnect purge-uje pre rendera/sync-a. |
| M11-QA-077 | Reconnect pre display expiry-ja posle remote revoke-a. | Prvi server check odbija, UI freeze+purge; nijedan payload ne odlazi u owner write. |
| M11-QA-078 | Kompletna M11 regresija se izvrši nad tačno evidentiranim repo commit-om, migration head-om i offline fixture hash-em. | Prolaz zahteva 78/78 stvarno izvršenih testova i 0 failed/skipped/flaky; lease/display/session rokovi koriste fiksirani clock. |

## Traceability

| Garancija | Normativno | QA |
|---|---|---|
| Frozen roster i statusi | 01 §2–3 | 2–7, 19–22, 65–68 |
| Brza ali eksplicitna potvrda | 01 §1, §3 | 8–18 |
| Corrections/lock | 01 §2.5, §3, §5 | 23–33 |
| Tenant/RBAC/child privacy | 01 §4 | 34–39, 47–53, 62–64, 69–72 |
| Offline/idempotency/conflict | 01 §2.6–2.7, §3, §7 | 15–18, 25–26, 40–57, 73–78 |
| Granice modula | 01 §1, §3 | 57, 67–68 |
