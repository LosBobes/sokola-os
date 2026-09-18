---
tip: modulni-implementacioni-ugovor
modul-id: M11
naziv: Prisustvo i offline evidencija
status: SPEC_CANDIDATE
revizija: "1.2"
datum: 2026-09-08
schema-zavisnosti: [M09, M10]
read-portovi: [M04, M06, M09, M10]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M12, M13, M14, M17, M18, M19, M21, M28]
offline-policy: ALLOW_ATTENDANCE_ONLY
---

# M11 — Prisustvo i offline evidencija

## 1. Cilj, autoritet i granice

M11 je jedini vlasnik evidencije prisustva na M10 terminu i jedinog H0 offline mutation toka u SOKOLA OS. Standardni tok sa početnog ekrana mora omogućiti: otvori današnji termin → označi izuzetke → pregledaj i potvrdi. Kada nema izuzetaka, dovoljne su dve primarne interakcije; sa jednim izuzetkom najviše tri. Dodatne namerne izmene nisu veštački sakrivene radi brojanja klikova.

M11 poseduje `AttendanceSession`, zamrznuti `AttendanceRosterEntry`, `AttendanceRecord`, append-only `AttendanceCorrection`, server `AttendanceCommandReceipt` i protokol klijentske offline operacije.

M11 ne poseduje Group/Enrollment, TermOccurrence, podatke osobe/deteta, opravdanje odsustva, make-up termin, članarinu, popust ili billing. H0 nema biometriju, geolokaciju, automatsko prepoznavanje prisutnosti niti offline health/guardian podatke. Budući `attendance.makeup` ostaje podrazumevano `OFF` i zahteva poseban ugovor.

## 2. Entiteti, polja i lokalni model

### 2.1. Kanonski statusi

`AttendanceStatus` ima tačno: `UNRECORDED`, `PRESENT`, `ABSENT`, `LATE`.

`ClientSyncStatus` ima tačno: `PENDING_SYNC`, `SYNCED`, `SYNC_FAILED`. To je klijentsko stanje operacije, nije vrednost `AttendanceRecord.status`, ne ulazi u billing i ne zamenjuje server receipt.

### 2.2. `AttendanceSession`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `term_occurrence_id`, `group_id` | UUID | NE | Jedan session po M10 occurrence-u; unique school/occurrence. |
| `roster_as_of` | InstantUTC | NE | Tačno M10 `starts_at`. |
| `roster_digest` | SHA-256 | NE | Canonical sort roster entry ID + enrollment/version snapshot. |
| `status` | enum | NE | `DRAFT`, `CONFIRMED`, `LOCKED`. |
| `confirmed_at`, `locked_at` | InstantUTC | DA | Uslovno. |
| `confirmed_by_account_id`, `locked_by_account_id` | UUID | DA | Uslovno. |
| `correction_deadline_at` | InstantUTC | NE | `ends_at + school correction_window_hours`, snapshot. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | UInt64 | NE | CAS. |

School correction window default je 168h; konfigurabilno `24..720h`. Session se otvara od `starts_at-30min` do deadline-a. Pre tog prozora 409. Posle deadline-a obična promena je zaključana; status se pri read/write-u deterministički materializuje u LOCKED u istoj transakciji ako još nije.

### 2.3. `AttendanceRosterEntry`

Zamrznuti minimalni roster: `id`, `school_id`, `attendance_session_id`, `participant_profile_id`, `group_enrollment_id`, `enrollment_version`, `effective_at`, `created_at`. Unique session/participant. Roster se dobija iz M09 `GetRosterAsOf(group, occurrence.starts_at)`. Ne čuva ime, datum rođenja, kontakt, zdravlje, staratelja ili finansije; prikazni podaci se dobijaju iz M06 autorizovane projekcije.

Naknadni upis/ispis ne menja roster. Ispravka pogrešnog istorijskog roster-a je zasebna admin operacija `CorrectAttendanceRoster`, zahteva reason, audit i potvrdu da ne pravi duplicate participant; nije offline.

### 2.4. `AttendanceRecord`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `session_id`, `roster_entry_id` | UUID | NE | Unique session/roster entry. |
| `status` | AttendanceStatus | NE | Početno `UNRECORDED`. |
| `minutes_late` | UInt16 | DA | Samo za LATE; `1..min(1440, occurrence duration)`. Null je dozvoljen kada broj nije pouzdano evidentiran. |
| `last_changed_by_account_id` | UUID | DA | Null samo pre prvog unosa. |
| `last_changed_at` | InstantUTC | DA | Uslovno. |
| `version` | UInt64 | NE | Početno 1; per-record CAS. |

Nema free-text child beleške. `ABSENT` nije isto što i opravdano odsustvo; opravdanje nije H0 status ovog modula.

### 2.5. `AttendanceCorrection`

Append-only: `id`, `school_id`, `record_id`, `from_status`, `to_status`, `from_minutes_late`, `to_minutes_late`, `correction_kind` (`INITIAL_CONFIRMATION`, `ORDINARY_CORRECTION`, `ADMIN_AFTER_LOCK`, `ROSTER_CORRECTION`), `reason_code`, `actor_account_id`, `command_id`, `created_at`. Reason je obavezan za ordinary/admin/roster correction, nije potreban za initial confirmation. Unique record/command_id.

### 2.6. `AttendanceCommandReceipt`

`id`, `school_id`, `session_id`, `idempotency_key_hash`, `payload_hash`, `actor_account_id`, `authorization_version`, `outcome` (`APPLIED`, `ALREADY_EQUIVALENT`, `REJECTED_CONFLICT`, `REJECTED_AUTH`, `REJECTED_EXPIRED`), `response_status`, `response_digest`, `created_at`, `expires_at`. Receipt najmanje 30 dana; ne sadrži imena ni raw token/key.

### 2.7. Klijentska offline operacija

Offline queue zapis nije server domain entitet. Dozvoljeni sadržaj:

- opaque `operation_id` i idempotency key;
- school/session/occurrence/group/roster_entry ID;
- minimalni prikazni naziv učesnika samo za aktivni ekran;
- predloženi AttendanceStatus/minutes_late;
- per-record `base_version`, roster_digest, `issued_at`, `display_expires_at`, `lease_expires_at`, M01 `session_idle_expires_at_at_issue` i `session_absolute_expires_at`;
- `ClientSyncStatus` i bezbedni error code.

Zabranjeni su datum rođenja, adresa/kontakt, health/safety, guardian, finance, dokumenti, fotografija/avatar, auth token u payload-u i slobodan tekst. Storage je šifrovan/session-bound gde platforma omogućava; key ne sme biti trajno dostupan drugom korisniku profila uređaja. Service worker notification/payload nema child podatak.

## 3. Poslovna pravila, potvrda i konflikti

1. `OpenAttendanceSession` zaključava occurrence, dobija M09 as-of roster i atomski kreira session, roster entries i UNRECORDED records. Retry vraća isti session.
2. Server nikada inicijalno ne upisuje PRESENT. UI sme prikazati predlog „svi prisutni“, ali jasno označen kao nepotvrđen draft.
3. Pre slanja UI prikazuje zbir PRESENT/ABSENT/LATE/UNRECORDED, upozorenje ako su svi ostali na predlogu, i zahteva eksplicitan `Confirm`. Nema auto-submit, timer submit ili confirmation na navigaciju.
4. `ConfirmAttendance` šalje konačnu mapu za svaki roster entry, roster_digest i base record versions. Nepoznat/dupliran/nedostajući entry je 409; ne pravi delimičan session.
5. Prvi confirm zaključava Session red i u jednoj transakciji menja svaki record, upisuje corrections, session CONFIRMED, receipt, audit i outbox.
6. Paralelni confirm sa semantički identičnom mapom vraća `ALREADY_EQUIVALENT`; drugačija mapa vraća 409 i trenutni server version metadata bez imena.
7. Posle potvrde ordinary correction menja samo navedene record-e uz per-record expected version i reason. Različiti record-i mogu se bezbedno spojiti; isti stale record ne može last-write-wins.
8. Posle LOCKED samo `school.attendance.correct_after_lock` uz step-up ≤10min, reason i admin audit može kreirati `ADMIN_AFTER_LOCK`; Session ostaje LOCKED.
9. Attendance status ne menja M09 Enrollment, M10 occurrence, M12 obavezu ili pravo pristupa.
10. LATE je poslovni status; `minutes_late` nije obavezan ako precizan minut nije poznat. Za status koji nije LATE mora biti null.
11. Offline lease izdaje server tek posle online M01/M03/M05/M09/M10 provere. `lease_expires_at` je najranije od: izdavanje+12h, occurrence `ends_at+4h`, session correction deadline, M01 `session_idle_expires_at_at_issue` i session absolute expiry. Odvojeni `display_expires_at` je najranije od: izdavanje+60 min, `lease_expires_at`, session idle expiry pri izdavanju i session absolute expiry. Posle display expiry-ja offline UI više ne prikazuje roster imena/status mapu. Zbog obaveznog purge-a na session expiry-ju M11 ne pokušava da produži M01 sesiju offline lease-om.
12. Sync ponovo proverava trenutnu session/tenant/permission/assignment autorizaciju neposredno pre commit-a. Stari lease ili cached grant nije nova autorizacija.
13. Istekao/opozvan lease ne auto-sinhronizuje: operacija postaje `SYNC_FAILED`. Posle `display_expires_at` ostaje samo neutralan indikator da postoji zaključan unsynced pokušaj; sadržaj se ne prikazuje. Online reautorizacija istog account-a u istoj još-važećoj M01 sesiji i poslovnom prozoru može izdati novi lease, ponovo učitati autorizovani roster/current versions i ponuditi eksplicitni recovery diff. Stari payload se nikad sam ne primenjuje niti otkriva pre te provere.
14. Logout, lokalno poznat session expiry, logout-all/revoke signal, account/access revoke saznat na reconnect-u, tenant switch ili drugi korisnik odmah briše queue, roster prikaz i ključeve. Brisanje ne čeka dodatni mrežni poziv. Potpuno offline uređaj ne može primiti udaljeni revoke; `display_expires_at` zato garantuje lokalni freeze najkasnije 60 minuta od poslednje online autorizacije, a reconnect radi revoke check i purge pre rendera/sync-a. Nema tvrdnje o daljinskom wipe-u nedostupnog uređaja.
15. M11 je jedini H0 offline write. Finansijske, dokumentacione i druge komande ne smeju se prošvercovati kroz ovaj queue.

### 3.1. Edge cases

| # | Scenario | Ishod |
|---:|---|---|
| 1 | Učesnik je ispisan posle početka termina. | Ostaje na frozen as-of rosteru. |
| 2 | Učesnik se upiše posle početka. | Nije dodat retroaktivno. |
| 3 | Dva uređaja potvrde isti sadržaj. | Prvi APPLIED, drugi ALREADY_EQUIVALENT. |
| 4 | Dva uređaja potvrde različit status istog deteta. | Prvi commit; drugi 409/SYNC_FAILED, bez overwrite-a. |
| 5 | Offline uređaji menjaju različitu decu. | Per-record versions dozvoljavaju oba ako session/window/auth važe. |
| 6 | Lease istekne dok je telefon offline. | Nema auto-write; SYNC_FAILED. |
| 7 | Instruktoru se opozove assignment pre sync-a. | REJECTED_AUTH, purge/failed bez PII. |
| 8 | Cross-tenant session ID je validan. | Safe 404. |
| 9 | All-present draft se napusti bez confirm-a. | Server ostaje DRAFT/UNRECORDED. |
| 10 | Correction deadline prođe tokom request-a. | Precommit clock recheck odbija običnu correction. |
| 11 | Admin correction posle lock-a. | Dozvoljena samo specijalnim permission+step-up+reason; session LOCKED. |
| 12 | LATE sa 0 ili većim brojem od trajanja. | 422. |
| 13 | Service worker se aktivira pod drugim nalogom. | Pre čitanja briše tuđ session-bound cache. |
| 14 | M09/M10 port nije dostupan pri prvom open-u. | 503; nema parcijalnog session-a. |

## 4. Tenant & Security Guard

Online i sync redosled: M01 session → M03 school context/version → M05 permission → M10 occurrence + M09 active staff assignment/subject → per-session/roster guard → precommit authorization recheck. Offline lease je ograničen capability receipt, ne auth session i ne može promeniti actor/school/session.

M05 registruje:

| Permission | Opseg |
|---|---|
| `school.attendance.view` | Evidencija samo dozvoljene grupe/child projection. |
| `school.attendance.record` | Open/confirm/ordinary correction za aktivno dodeljenu grupu. |
| `school.attendance.lock` | Ranije ručno zaključavanje uz reason. |
| `school.attendance.correct_after_lock` | Admin ispravka posle lock-a uz step-up/reason. |
| `school.attendance.roster_correct` | Izuzetna korekcija frozen roster-a; admin/online only. |

Owner/Manager imaju administrative ključeve; Instructor/Substitute view+record samo tokom efektivne M09 dodele; LimitedAdmin samo eksplicitno; Guardian dobija minimalni linked-child read preko M28, ne group roster; Payer nema attendance pristup. Payer odnos nikad ne daje child status.

List/count/export prvo primenjuje school i subject guard. Cross-tenant/hidden child je 404. Audit/outbox imaju opaque IDs, status transition, version, actor/correlation; nema imena, minutes_late u telemetry-ju, slobodnog teksta ili lokalnog queue sadržaja. Error telemetry dozvoljava samo kod, operation type, pseudonimizovan tenant/actor, latency/retry count.

## 5. Lifecycle & transitions

### 5.1. AttendanceSession

| From | Komanda/vreme | To |
|---|---|---|
| — | OpenAttendanceSession u prozoru | DRAFT |
| DRAFT | ConfirmAttendance | CONFIRMED |
| DRAFT/CONFIRMED | deadline ili LockAttendance | LOCKED |
| LOCKED | AdminCorrectAfterLock | LOCKED; correction samo |

Nema unlock u H0.

### 5.2. AttendanceRecord

| From | Komanda | To |
|---|---|---|
| UNRECORDED | Initial confirm | PRESENT/ABSENT/LATE |
| PRESENT/ABSENT/LATE | Ordinary correction pre deadline | PRESENT/ABSENT/LATE |
| bilo koji | Admin correction posle lock-a | PRESENT/ABSENT/LATE |
| bilo koji | direktno u UNRECORDED | Zabranjeno posle prvog evidentiranja |

### 5.3. ClientSyncStatus

| From | Događaj | To |
|---|---|---|
| — | Lokalni explicit confirm/change | PENDING_SYNC |
| PENDING_SYNC | Server APPLIED/ALREADY_EQUIVALENT | SYNCED |
| PENDING_SYNC | Conflict/auth/expiry/terminal validation | SYNC_FAILED |
| SYNC_FAILED | Isti korisnik reautorizuje i eksplicitno retry-uje sa novim base/lease | PENDING_SYNC |

## 6. Error catalog

| Kod | HTTP | Opis |
|---|---:|---|
| `M11_VALIDATION_FAILED` | 422 | Status, minute ili payload nije validan. |
| `M11_NOT_FOUND_SAFE` | 404 | Session/occurrence/roster nije vidljiv. |
| `M11_PERMISSION_DENIED` | 403 | Poznat resurs, nedozvoljena akcija. |
| `M11_SESSION_TOO_EARLY` | 409 | Pre starts_at-30min. |
| `M11_SESSION_LOCKED` | 409 | Obična promena posle deadline-a/lock-a. |
| `M11_ROSTER_CHANGED` | 409 | Digest ili entry set ne odgovara. |
| `M11_RECORD_VERSION_CONFLICT` | 409 | Isti record je promenjen. |
| `M11_CONFIRMATION_CONFLICT` | 409 | Session već potvrđen drugačijom mapom. |
| `M11_STATUS_TRANSITION_INVALID` | 409 | Nedozvoljena status promena. |
| `M11_REASON_REQUIRED` | 422 | Correction/lock nema reason. |
| `M11_STEP_UP_REQUIRED` | 401 | Admin correction zahteva svež step-up. |
| `M11_OFFLINE_LEASE_EXPIRED` | 409 | Lease više nije važeći. |
| `M11_OFFLINE_REAUTH_REQUIRED` | 401 | Sync nema aktuelnu autorizaciju. |
| `M11_IDEMPOTENCY_KEY_REUSED` | 409 | Isti ključ, drugi payload/scope. |
| `M11_PRECONDITION_REQUIRED` | 428 | Nedostaje per-record/session expected version. |
| `M11_DEPENDENCY_UNAVAILABLE` | 503 | M09/M10 authority nije dostupan. |
| `M11_RATE_LIMITED` | 429 | Limit. |

## 7. API, idempotency, concurrency, offline i NFR

Komande: `OpenAttendanceSession`, `IssueOfflineAttendanceLease`, `ConfirmAttendance`, `CorrectAttendance`, `LockAttendance`, `AdminCorrectAfterLock`, `CorrectAttendanceRoster`. Svaka ima Idempotency-Key/correlation, school scope; mutacije expected versions. Receipt 30 dana. Confirm payload mora sadržati svaki roster entry tačno jednom; maksimum 500 entry-ja po H0 session-u, veći roster zahteva feature/change odluku, ne silent truncation.

Session lock serijalizuje open/confirm/lock. Record correction zaključava record-e sortirano po UUID. Per-record CAS omogućava disjoint offline merge; ne koristi globalni last-write-wins. Business write, corrections, session status, receipt, audit i outbox su jedna transakcija. Outbox: `AttendanceConfirmedV1`, `AttendanceCorrectedV1`, `AttendanceLockedV1`, agregatni count-ovi i opaque ID; bez imena.

Query: `GetTodayAttendanceLaunch` vraća samo dodeljene današnje occurrence-e, server sort najbliži start; `GetAttendanceSession` minimalna autorizovana projekcija; `ListAttendanceHistory` max 366 dana, cursor default 25 max 100. Cache je school+actor authorization version+subject scoped; attendance mutation invalidira relevantan ključ pre uspešnog response-a.

PWA sync koristi exponential backoff sa jitter-om za mrežne/5xx greške, najviše do lease expiry; 4xx terminalni conflict/auth prelazi u SYNC_FAILED. Nikad ne ponavlja drugi payload pod istim key-em. UI jasno razlikuje lokalni draft, PENDING_SYNC, SYNCED i SYNC_FAILED; „Sačuvano“/konačna potvrda se prikazuje samo posle server success receipt-a.

Performance: launch p95 ≤300ms, session read ≤350ms, confirm 100 entries ≤800ms bez outage-a. Initial PWA attendance route interactive cilj na referentnom mid-range uređaju i kontrolisanoj 4G mreži ≤2.5s warm / ≤4s cold; offline reopen ≤1s. Implementacija mora meriti bundle/query plan i dokumentovati test uslove, ne tvrditi rezultat bez testa.

## 8. Acceptance sažetak

M11 prolazi samo uz `02-M11-QA-I-TRACEABILITY.md`, uključujući pravi parallel confirm/correction, offline expiry/revoke/tenant-switch purge, frozen roster, četiri domen statusa, tri sync statusa, accidental-confirm protection, server-only final success i negativnu proveru da attendance ne menja M12 billing.
