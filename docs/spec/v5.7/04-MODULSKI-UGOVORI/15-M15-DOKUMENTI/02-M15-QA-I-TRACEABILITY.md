---
tip: qa-traceability
modul-id: M15
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-15
obavezni-scenariji: 94
---

# M15 — QA i traceability

| QA ID | Scenario | Očekivano |
|---|---|---|
| M15-QA-001 | Create validan Document. | 201 DRAFT. |
| M15-QA-002 | Scope ID iz B. | Safe 404. |
| M15-QA-003 | SCHOOL scope sa scope_id. | 422. |
| M15-QA-004 | EVENT scope validan M16 portom. | Dozvoljen. |
| M15-QA-005 | M16 port unavailable. | 503, nema upisa. |
| M15-QA-006 | Prepare PDF ≤10MiB. | UPLOADING + opaque object key. |
| M15-QA-007 | 0 byte ili >10MiB. | 422. |
| M15-QA-008 | DOCX/ZIP/executable. | 422. |
| M15-QA-009 | PDF ekstenzija, EXE bytes. | REJECTED. |
| M15-QA-010 | Polyglot/active PDF. | REJECTED. |
| M15-QA-011 | Password/encrypted PDF. | REJECTED. |
| M15-QA-012 | Malware scan positive. | REJECTED/quarantine. |
| M15-QA-013 | Scan callback duplicate. | Jedan outcome. |
| M15-QA-014 | Scan engine unknown. | Fail closed. |
| M15-QA-015 | Finalize size/hash mismatch. | 422, object quarantine. |
| M15-QA-016 | Pokušaj menjanja AVAILABLE bytes/hash. | DB/API odbija. |
| M15-QA-017 | Nova verzija. | version_no+1; stara immutable. |
| M15-QA-018 | Paralelno kreiranje version_no. | Jedna po broju; retry/stale. |
| M15-QA-019 | Publish SCANNING/REJECTED. | 409. |
| M15-QA-020 | Publish AVAILABLE. | Document PUBLISHED/current_version atomski. |
| M15-QA-021 | Paralelni publish v2/v3. | Jedan current; drugi 409. |
| M15-QA-022 | DB fail pri current switch-u. | Potpun rollback. |
| M15-QA-023 | Retire document. | Nova preuzimanja blokirana. |
| M15-QA-024 | Withdraw version. | Hash/evidence ostaju. |
| M15-QA-025 | Zdravstveni dokument kategorisan pravilno. | 422 forbidden. |
| M15-QA-026 | Zdravstveni sadržaj pod OTHER. | 422; nema bypass-a. |
| M15-QA-027 | Guardian active child scope. | Vidi dozvoljen dokument. |
| M15-QA-028 | Guardian opozvan. | Safe 404. |
| M15-QA-029 | Guardian drugog deteta. | Safe 404. |
| M15-QA-030 | PAYER ordinary contract. | Nema pristup. |
| M15-QA-031 | PAYER svoj PAYMENT_PROOF+M12 basis. | Dozvoljen. |
| M15-QA-032 | PAYER tuđa obaveza. | Safe 404. |
| M15-QA-033 | Instructor dodeljena grupa STAFF visibility. | Dozvoljen prema binding-u. |
| M15-QA-034 | Instructor nedodeljena grupa. | Safe 404. |
| M15-QA-035 | Issue download ticket. | Digest-only, ttl≤60s, bound subject/version. |
| M15-QA-036 | Raw ticket u DB/logu. | Static/runtime test fail; 0 nalaza. |
| M15-QA-037 | Ticket consume jednom. | USED; tačno jedna ACTIVE DownloadSession; još nema tvrdnje da je ceo stream završen. |
| M15-QA-038 | Ponovni consume. | 410 neutralno. |
| M15-QA-039 | Expired ticket. | 410. |
| M15-QA-040 | Drugi account koristi ticket. | 410/404 bez leak-a. |
| M15-QA-041 | Guardian revoke posle issue. | Consume fail closed. |
| M15-QA-042 | Authorization version promenjen. | Ticket revoked/fail. |
| M15-QA-043 | Trajni/public storage URL scan. | 0. |
| M15-QA-044 | Email/push attachment scan. | 0. |
| M15-QA-045 | Create validan ACCEPTANCE requirement. | DRAFT. |
| M15-QA-046 | Requirement cilja mutable/nonavailable verziju. | 409. |
| M15-QA-047 | Optional decision mandatory=true. | 422. |
| M15-QA-048 | Activate requirement. | ACTIVE immutable binding. |
| M15-QA-049 | Paralelne aktivacije konfliktnog requirement-a. | Jedna ACTIVE. |
| M15-QA-050 | Guardian vidi tačnu verziju/hash pa ACCEPT. | Append-only evidence kompletan. |
| M15-QA-051 | Acceptance bez participant authority. | 403/safe 404. |
| M15-QA-052 | Requirement/version promenjen tokom prikaza. | 409 stale. |
| M15-QA-053 | Double-click isti key. | Jedan evidence/receipt. |
| M15-QA-054 | Isti key druga odluka. | 409. |
| M15-QA-055 | Dva guardian-a istog deteta. | Dva evidence; M17 odlučuje sufficiency. |
| M15-QA-056 | ACK privacy notice. | ACKNOWLEDGED, ne consent. |
| M15-QA-057 | DECLINE optional photo/video. | App ostaje dostupna; nema ACTIVE M17 consent-a. |
| M15-QA-058 | Povlačenje M17 consent-a. | U jednoj lokalnoj transakciji nastaju M17 WITHDRAWN decision i M15 `CONSENT_WITHDRAWN` evidence; stari decision/evidence ostaju. |
| M15-QA-059 | UI tvrdi QES/kvalifikovani potpis. | Content/static test pada. |
| M15-QA-060 | Assisted acceptance bez step-up/reason. | 403/422. |
| M15-QA-061 | Assisted acceptance sa prisutnim giverom. | Evidence actor/basis/audit kompletan. |
| M15-QA-062 | Bulk/retroactive assisted acceptance. | Odbijeno. |
| M15-QA-063 | IP policy absent. | IP NULL. |
| M15-QA-064 | IP policy active. | Encrypted + retention_until; nije u logu. |
| M15-QA-065 | Retired doc posle acceptance-a. | Evidence/hash očuvani. |
| M15-QA-066 | Legal hold. | Object purge zaustavljen samo za target scope. |
| M15-QA-067 | Retention expiry bez hold-a. | Kontrolisan purge/tombstone, audit očuvan po ugovoru. |
| M15-QA-068 | Offline download/accept. | DENY; nema IndexedDB sadržaja. |
| M15-QA-069 | Support download/accept/content. | Odbijeno. |
| M15-QA-070 | Log/metric inspection. | Bez title/filename/hash/ticket/person/child/IP. |
| M15-QA-071 | Two-tenant FK/object-key substitution. | DB/storage policy odbija. |
| M15-QA-072 | Dependency scan. | M15 samo read-validira M16; nema M16→M15, nema QES ni prostog replaces-only modela. |
| M15-QA-073 | Dva paralelna consume-a istog ticket-a. | Jedan Ticket USED i jedna DownloadSession; drugi 410; nema dva raw session tokena. |
| M15-QA-074 | Range resume posle mrežnog prekida. | Ista ACTIVE DownloadSession i fiksni TTL; svaki range ponavlja authorization guard. |
| M15-QA-075 | Revoke guardian/access između dva range zahteva. | Sledeći range odbijen, sesija REVOKED; prethodno poslati bajtovi se ne mogu udaljeno vratiti. |
| M15-QA-076 | DRAFT Document ili UPLOADING Version bez terminalnih timestamp-a. | Validan insert bez izmišljenih datuma; DB conditional CHECK prolazi. |
| M15-QA-077 | AVAILABLE version bez `available_at` ili WITHDRAWN bez reason/time. | DB/API odbija. |
| M15-QA-078 | OPTIONAL_DECISION dobije `CONSENT_GRANTED`, zatim withdrawal. | Tačne dve immutable evidence vrednosti, exact requirement/version/hash i jedan M17 effective head. |
| M15-QA-079 | M15 pokušava direktan M17 domain call ili M17 direktan M15 table write. | Architecture test pada; dozvoljen je samo neutralni coordinator nad owner portovima. |
| M15-QA-080 | UPLOADING ili SCANNING Version ima scan-result, available ili withdraw polje. | DB CHECK odbija; početna stanja ne izmišljaju rezultat skeniranja. |
| M15-QA-081 | REJECTED Version nema engine/result/completed dokaz ili ima `available_at`. | DB CHECK odbija; odbijanje je potpuno dokazivo i nikad dostupno. |
| M15-QA-082 | DRAFT requirement ima activation/retire actor ili vreme. | DB CHECK odbija. |
| M15-QA-083 | ACTIVE/RETIRED requirement nema tačan activation/retire actor-time par. | DB CHECK odbija svaku nepotpunu kombinaciju. |
| M15-QA-084 | Browser evidence tvrdi SUBJECT, ali recorder nije isti giver account ili nema aktivnu sesiju. | 422/403; nema evidence/audit/outbox/receipt upisa. |
| M15-QA-085 | STAFF_ASSISTED nema recorder account, step-up, prisustvo davaoca ili reason. | 422/403; nema parcijalnog dokaza. |
| M15-QA-086 | Prisutni davalac nema SOKOLA nalog, a ovlašćeni staff beleži odluku. | Dozvoljeno uz giver Person, stvarni staff recorder, basis/reason i kompletan audit; ne kreira se lažni nalog davaoca. |
| M15-QA-087 | API_MIGRATION nema allow-listed system identity, source system/hash ili reason. | 422 `M15_SOURCE_EVIDENCE_REQUIRED`; nema pretpostavljenog opt-in-a. |
| M15-QA-088 | Dokaziva istorijska odluka davaoca bez SOKOLA naloga se migrira. | Append-only evidence sadrži giver Person, trusted recorder identity, source hash i istorijski `occurred_at`; account ostaje null. |
| M15-QA-089 | M17 decision i M15 evidence se razlikuju po giver/subject/recorder/channel/source proof-u. | Coordinator odbija i rollback-uje oba owner upisa, audit/outbox i receipt. |
| M15-QA-090 | Dve paralelne komande ciljaju isti requirement/giver/subject/generation. | Nenull `subject_scope_key` i unique daju tačno jedan evidence; druga vraća isti receipt ili 409 za drugi payload. |
| M15-QA-091 PAR | Dve komande istovremeno postavljaju sledeći DocumentAccess. | Document CAS i active-interval constraint daju tačno jedan novi ACTIVE red; prethodni je jednom RETIRED, loser dobija 409 bez preklapanja. |
| M15-QA-092 | `EXPLICIT_REQUIREMENT_SUBJECTS` subjekt otvara tačnu verziju pre svoje odluke. | Current requirement+subject guard dozvoljava prikaz; ne kreira evidence i ne predstavlja subjekt kao acceptor. Opozvan basis daje safe 404. |
| M15-QA-093 | M15 requirement dobija M17 purpose/basis/version/hash snapshot koji se ne poklapa ili pokušava fizički M15→M17 FK/schema zavisnost. | Aktivacija je 409/422 bez upisa; schema dependency test potvrđuje jednosmerni M17→M15 FK i odsustvo ciklusa. |
| M15-QA-094 | Isti bytes se uploadaju kao druga verzija istog Document-a i kao verzija drugog Document-a. | Prvi slučaj dedupe/conflict bez duple verzije; drugi je dozvoljen uz odvojeni logical Document. Acceptance zahteva 94/94 stvarno izvršena testa bez failed/skipped/flaky. |

Suite uključuje parser/malware test fixture-e, property hash, paralelni publish/requirement/evidence, sva tri dokazna actor/channel toka, tenant API+DB+storage, authorization revoke, retention/legal hold i redaction.
