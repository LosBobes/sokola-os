---
tip: qa-traceability
modul-id: M06
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-15
obavezni-scenariji: 35
---

# M06 — QA i traceability

Svaki scenario je automatizovan DB/API test sa kontrolisanim clock-om. Uspeh proverava stanje, version, jedan receipt/audit/outbox; neuspeh proverava HTTP+code, nepromenjenu bazu i odsustvo success side effect-a. Repo status ostaje `REPO_UNVERIFIED`.

| QA ID | Scenario | Očekivano | Trag |
|---|---|---|---|
| `M06-QA-001` | Kreira se dete bez birth date, kontakta i naloga. | `Person` + DRAFT `PARTICIPANT` membership uspevaju; nema `UserAccount`. | §1, §3.1 |
| `M06-QA-002` | M06 endpoint pokuša da kreira `UserAccount`. | Port ne postoji; contract test pada. | §0, §1.2 |
| `M06-QA-003` | Dve različite osobe imaju isto ime. | Oba reda postoje; ime nije uniqueness ključ. | §2.1, §3.4 |
| `M06-QA-004` | Dve osobe dele samo isti email blind index. | Drugi create uspeva kao candidate; nema merge/account link-a. | §3.4 |
| `M06-QA-005` | Uz aktivan sensitive-ID capability i validan purpose, exact JMBG blind index se poklapa. | Candidate attention item; nema automatskog merge-a niti izlaganja postojećeg ID-a neovlašćenom actor-u. | §2.2, §3.4 |
| `M06-QA-006` | Contact update menja email. | Ciphertext+blind index menjaju se atomarno; stari index se ne koristi. | §2.1, §7 |
| `M06-QA-007` | Isti idempotency key i isti CreatePerson payload. | Replay originalnog rezultata; jedan Person/audit/outbox. | §7 |
| `M06-QA-008` | Isti key, drugo prezime. | 409 `M06_IDEMPOTENCY_KEY_REUSED`; bez drugog reda. | §6, §7 |
| `M06-QA-009` | Ista osoba dobija GUARDIAN i STAFF membership u A. | Oba mogu postojati; odvojeni prirodni ključevi. | §2.3, §3.2 |
| `M06-QA-010` | Ista osoba dobija STAFF u A i B. | Nezavisni tenant redovi; A nema promenu. | §3.2, §4 |
| `M06-QA-011` | Drugi otvoreni PARTICIPANT membership u A. | 409 `M06_MEMBERSHIP_ALREADY_CURRENT`. | §2.3, §6 |
| `M06-QA-012` | Dva paralelna create zahteva za isti membership. | Tačno jedan commit; drugi stabilan 409. | §3.1, §7 |
| `M06-QA-013` | Prva epizoda istog membership ključa. | `is_first_activation=true`. | §3.5 |
| `M06-QA-014` | Nova epizoda posle TERMINATED. | Novi ID, `is_first_activation=false`; istorija ostaje. | §3.5, §5.1 |
| `M06-QA-015` | ACTIVE → SUSPENDED bez reason-a. | 422 `M06_VALIDATION_FAILED`; status ostaje ACTIVE. | §2.3, §5.1 |
| `M06-QA-016` | TERMINATED → ACTIVE. | 409 `M06_MEMBERSHIP_INVALID_TRANSITION`. | §5.1 |
| `M06-QA-017` | Terminate poslednjeg OWNER membership-a. | Application guard vraća `RBAC_LAST_OWNER_PROTECTED`; obe oblasti nepromenjene. | §3.9, §6 |
| `M06-QA-018` | Dva owner terminate/revoke toka paralelno. | Lock redosled ostavlja najmanje jednog efektivnog OWNER-a. | §3.9, §7 |
| `M06-QA-019` | ParticipantProfile se veže na STAFF membership. | 422 `M06_PROFILE_TYPE_MISMATCH`. | §2.5, §6 |
| `M06-QA-020` | Profil `school_id=A`, membership iz B. | 404 `M06_NOT_FOUND_SAFE`; DB FK odbija i direktan upis. | §2.5, §4 |
| `M06-QA-021` | Dva paralelna create profila za isti membership. | Jedan commit; drugi 409 `M06_PROFILE_ALREADY_EXISTS`. | §2.5, §7 |
| `M06-QA-022` | Discipline SPORT/DANCE/DRAMA/MUSIC/EDUCATION/OTHER. | Svaka se čuva bez promene autorizacione semantike. | §2.5, §8.5 |
| `M06-QA-023` | Administrative note sadrži JMBG ili zdravstveni podatak. | 422 `M06_VALIDATION_FAILED`; podatak se ne loguje. | §2.4, §4 |
| `M06-QA-024` | Upis JMBG bez aktivnog lawful purpose-a. | 422 `M06_SENSITIVE_PURPOSE_INVALID`; nema ciphertext-a. | §2.2, §6 |
| `M06-QA-025` | M17 policy verifier nedostupan. | 503 `M06_SENSITIVE_POLICY_UNAVAILABLE`; fail-closed. | §2.2, §6 |
| `M06-QA-026` | Validan JMBG unos za osobu uz pravni osnov. | Samo encrypted envelope+blind index; plaintext odsutan iz DB/log/audit/outbox/receipt hash-a. | §2.2, §4, §7 |
| `M06-QA-027` | Actor bez reveal prava čita sensitive identifier. | 403 `M06_FORBIDDEN`; pokušaj auditovan bez vrednosti. | §4 |
| `M06-QA-028` | Access se opozove tokom safety-note read-a. | 409 `M06_CONCURRENT_AUTHORIZATION_CHANGE`; response nema plaintext. | §3.1, §4 |
| `M06-QA-029` | Actor A čita Person samo sa membership-om u B. | 404 `M06_NOT_FOUND_SAFE`; isti oblik kao unknown ID. | §4 |
| `M06-QA-030` | Local merge dve osobe čije su sve veze samo u A. | Atomski re-parent/history/MERGED; jedan audit/outbox. | §2.7, §3.15 |
| `M06-QA-031` | Merge ima otvoren isti membership ključ ili vezu u B. | Prvi slučaj 409 `M06_MERGE_MEMBERSHIP_CONFLICT`; drugi 409 `M06_CROSS_TENANT_MERGE_NOT_SUPPORTED`; nema partial write-a. | §3.14-15, §6 |
| `M06-QA-032` | M02 proverava Person bez birth date, minor-a, adult-a i MERGED reda. | Redom `NOT_ELIGIBLE`, `NOT_ELIGIBLE`, `ELIGIBLE`, `NOT_ELIGIBLE`; pre finalnog accept-a ponovna provera. | §7.2 |
| `M06-QA-033` | M02/M04 prosledi SchoolPersonProfile A sa Person B ili profil škole B u kontekstu A. | Composite DB constraint i port vraćaju safe 404; nema invitation/nominacije ili existence hint-a. | §2.4, §4, §7.2 |
| `M06-QA-034` | Direktan SQL pokušaj M07/M05 reference sa istim school ID-em, ali membership ID-em druge Person. | Triple composite FK `(school_id,id,person_id)` odbija upis; nema cross-person role/relation veze. | §2.3, §4 |
| `M06-QA-035` | Backup/replica/log/telemetry test za Person ime, datum rođenja, kontakt, JMBG i safety note. | Storage/backup/replica su encrypted at rest i u tranzitu; observability nema PII; field-level ciphertext postoji za kontakt/JMBG/safety note. | §2.1–2.5, §4 |

## Obavezni seed

- School A i B; osobe adult, minor, unknown-age i merged candidate.
- Membership epizode za sva četiri tipa i sva četiri statusa.
- Cross-tenant profile/FK negativni par.
- Dva active owner kandidata za concurrency test.
- Sensitive policy: valid, invalid i unavailable adapter.

## Izvršni minimum

Suite tagovi: `m06-unit`, `m06-db-constraints`, `m06-api`, `m06-tenant-negative`, `m06-pii`, `m06-idempotency`, `m06-concurrency`, `m06-merge`, `m06-migration`. Pokrenuto 35, prošlo 35, preskočeno 0; u suprotnom M06 nije spreman za programmer candidate.
