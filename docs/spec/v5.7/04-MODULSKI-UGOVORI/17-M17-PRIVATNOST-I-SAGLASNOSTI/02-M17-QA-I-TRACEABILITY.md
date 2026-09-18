---
tip: qa-traceability
modul-id: M17
status: SPEC_CANDIDATE
revizija: "1.9"
datum: 2026-09-15
obavezni-scenariji: 107
---

# M17 — QA i traceability

Svaki scenario je automatizovan gde god tehnički može biti automatizovan. Testovi koriste zamrznut clock, dve škole, stvarnu konkurentnost za race scenarije i sintetičke podatke. `Skipped` kritičan test znači pad M17 acceptance-a.

| ID | Scenario | Očekivani rezultat |
|---|---|---|
| M17-QA-001 | Objavi potpun purpose CONTRACT. | PUBLISHED, immutable hash, receipt/audit/outbox. |
| M17-QA-002 | CONSENT + REQUIRED_FOR_SERVICE. | 422; nema upisa. |
| M17-QA-003 | LEGAL_OR_SIMILAR_EFFECT u H0. | 422 fail-closed. |
| M17-QA-004 | Published interval se preklapa. | 409; stara verzija nepromenjena. |
| M17-QA-005 | Update published purpose. | Odbijeno; nova verzija obavezna. |
| M17-QA-006 | Publish notice sa M15 hash mismatch. | 409; nema publish-a. |
| M17-QA-007 | Notice acknowledgement. | M15 evidence, ne ConsentDecision. |
| M17-QA-008 | Odbijena optional PHOTO saglasnost. | Osnovna usluga ostaje dostupna. |
| M17-QA-009 | Bundled PHOTO+VIDEO payload. | 422 `M17_BUNDLED_CONSENT_FORBIDDEN`. |
| M17-QA-010 | Public web+social u jednom scope-u. | 422; granularne definicije obavezne. |
| M17-QA-011 | Grant za sebe, validna verzija. | GRANTED + append-only decision/evidence. |
| M17-QA-012 | Decline za dete, validan guardian. | DECLINED; nema negativne funkcionalne posledice van scope-a. |
| M17-QA-013 | Guardian druge škole. | Safe 404; zero leak. |
| M17-QA-014 | Opozvan guardian posle form load-a. | Precommit deny; nema decision-a. |
| M17-QA-015 | Dupli identičan grant/key. | Jedan red; isti receipt. |
| M17-QA-016 | Isti key, druga odluka. | 409 idempotency mismatch. |
| M17-QA-017 | Dva aktivna guardian-a paralelno daju GRANTED i DECLINED. | Oba append-only decision-a ostaju sačuvana; giver head-ovi su odvojeni; `ANY_DECLINE_BLOCKS` agregat je DECLINED; nema last-write-wins niti školskog override-a. |
| M17-QA-018 | Withdraw GRANTED. | Novi M17 WITHDRAWN red i M15 `CONSENT_WITHDRAWN` evidence u istom commit-u; version bump/outbox. |
| M17-QA-019 | Ponovni grant posle withdrawal-a. | Novi GRANTED red; istorija očuvana. |
| M17-QA-020 | Withdraw i media publish paralelno. | Publish radi fresh recheck; posle withdrawal commit-a ne prolazi. |
| M17-QA-021 | Material consent version publish. | Effective state RECONSENT_REQUIRED. |
| M17-QA-022 | Non-material copy version. | State ostaje samo uz isti semantic registry. |
| M17-QA-023 | Klik na stale definition/hash. | 409 i nova verzija. |
| M17-QA-024 | Retired definition prima grant. | 409 not active. |
| M17-QA-025 | Staff-assisted grant bez step-up. | 401; nema evidence-a. |
| M17-QA-026 | Staff-assisted bulk grant. | 422/403; nijedan subject promenjen. |
| M17-QA-027 | Migration boolean bez source evidence-a. | NOT_ASKED, ne GRANTED. |
| M17-QA-028 | Legacy bundled photo/video. | Oba RECONSENT_REQUIRED. |
| M17-QA-029 | AuthorizeProcessing valid consent. | Purpose/version/head/security TTL≤60s. |
| M17-QA-030 | Cache freshness nepoznata. | Authoritative read ili deny. |
| M17-QA-031 | Submit self ACCESS uz session assurance. | RECEIVED/VALIDATING po policy-ju. |
| M17-QA-032 | Submit child request bez guardian scope-a. | Safe 404/403 bez subject leak-a. |
| M17-QA-033 | Identity insufficient. | IDENTITY_PENDING; nema izvoza. |
| M17-QA-034 | Nedozvoljena request tranzicija. | 409; version nepromenjen. |
| M17-QA-035 | Dupli Submit isti key. | Jedan request/receipt. |
| M17-QA-036 | ACCESS export uključuje drugo lice. | Redakcija; manifest kategorije. |
| M17-QA-037 | ACCESS export cross-tenant query pokušaj. | Safe 404; zero rows/cache leak. |
| M17-QA-038 | Rectification append-only payment-a. | Korektivni owner zapis; original očuvan. |
| M17-QA-039 | ERASURE bez blokera. | Owner receipts, COMPLETED. |
| M17-QA-040 | ERASURE uz finansijsku obavezu čuvanja. | PARTIALLY_COMPLETED + zatvoren reason. |
| M17-QA-041 | Active legal hold pre planiranja. | Obuhvaćen task BLOCKED_BY_HOLD. |
| M17-QA-042 | Hold aktiviran tokom delete race-a. | Precommit recheck; ništa obrisano. |
| M17-QA-043 | Hold druge kategorije. | Ne blokira nepovezan task. |
| M17-QA-044 | Hold aktivira isti requester+approver. | 403 dual-control. |
| M17-QA-045 | Hold expiry job ponovljen. | Jedna EXPIRED tranzicija/receipt. |
| M17-QA-046 | Retention nije dospeo. | 409/no task. |
| M17-QA-047 | Dva workera lease isti task. | Jedan fencing winner. |
| M17-QA-048 | Stale worker commit posle re-lease-a. | Odbijen. |
| M17-QA-049 | Owner port privremeno pada. | FAILED_RETRYABLE; request IN_PROGRESS. |
| M17-QA-050 | Max retry iscrpljen. | FAILED_FINAL/manual review; nema false completion. |
| M17-QA-051 | Svi taskovi uspešni. | Request COMPLETED + response doc. |
| M17-QA-052 | Mešoviti success/pravni izuzetak. | PARTIALLY_COMPLETED. |
| M17-QA-053 | Export ticket iskorišćen dvaput paralelno. | Tačno jedan download. |
| M17-QA-054 | Export ticket posle guardian revoke-a. | Reauthorization deny. |
| M17-QA-055 | Export >100k redova. | Segmenti+manifest; bez memory spike-a. |
| M17-QA-056 | IP bez active necessity policy-ja. | NULL/odbijeno. |
| M17-QA-057 | IP uz policy. | Encrypted + kraći retention. |
| M17-QA-058 | Log/error/outbox inspection. | Nema PII/raw token/content. |
| M17-QA-059 | Support standard grant. | Samo masked aggregate; bez DSAR sadržaja. |
| M17-QA-060 | Break-glass pokuša grant consent. | Odbijeno i auditovano. |
| M17-QA-061 | Deaktivirana škola podnosi compliance request. | Minimalni intake dozvoljen; redovna obrada blokirana. |
| M17-QA-062 | Same Person, dve škole. | Odluke i export strogo odvojeni. |
| M17-QA-063 | Query count pre subject filter-a. | Architecture/integration test pada. |
| M17-QA-064 | Tenant ID samo iz body-ja. | Odbijeno; koristi execution context. |
| M17-QA-065 | Consent state optimistic-final offline. | Deny; nema queue-a/upisa. |
| M17-QA-066 | Logout/tenant switch sa privacy formom. | Osetljiv memory/cache očišćen. |
| M17-QA-067 | Unknown purpose/event schema consumer. | Quarantine/fail-closed bez PII. |
| M17-QA-068 | Backup restore u drugu školu. | Tenant binding validation odbija. |
| M17-QA-069 | Cursor tenant promenjen. | 400/404; nema stranice druge škole. |
| M17-QA-070 | Rate limit DSAR, accessibility override. | 429 standardno; auditovana dozvoljena iznimka. |
| M17-QA-071 | Negative dependency scan. | M17 ne menja M06/M07/M15/M21 tabele direktno. |
| M17-QA-072 | Guardian A GRANTED, B DECLINED, zatim B authority opozvan. | `RECONSENT_REQUIRED/GUARDIAN_AUTHORITY_CHANGED`; nema automatskog GRANTED; istorija očuvana. |
| M17-QA-073 | Novi guardian dodat posle postojećeg GRANTED. | Authority-set hash se menja; RECONSENT_REQUIRED do nove odluke pod aktuelnim skupom. |
| M17-QA-074 | DECLINED i WITHDRAWN head postoje istovremeno. | Deterministični prioritet daje DECLINED nezavisno od redosleda event-a. |
| M17-QA-075 | M15 evidence insert failure tokom consent coordinator-a. | M17 decision, audit, outbox i receipt svi rollback; nema parcijalnog dokaza. |
| M17-QA-076 | Evidence decision ne odgovara M17 decision-u ili requirement/hash-u. | 422/409; nema nijednog owner upisa. |
| M17-QA-077 | M28 feature OFF, ali H0 authenticated PWA intake postoji. | Kanal je `AUTHENTICATED_WEB_PWA`; nema zavisnosti od M28 aktivacije. |
| M17-QA-078 | `CONTRACT_ACCEPTANCE` ili `PRIVACY_NOTICE_ACK` purpose se objavi kao opciona saglasnost sa akcijom „Povuci saglasnost”. | Publish 422; ne nastaje consent definicija/odluka/evidence. Neophodni ugovor i potvrda obaveštenja ostaju pravno-specifični M15 acceptance/acknowledgement tokovi, bez lažnog consent pravnog osnova. |
| M17-QA-079 | DRAFT/PUBLISHED/RETIRED version lifecycle polja. | DB CHECK prihvata samo tačne publish/retire actor-time kombinacije; početni red nema izmišljene vrednosti. |
| M17-QA-080 | DRAFT LegalHold. | Activation/release/expiry polja su null; ne utiče na disposition. |
| M17-QA-081 | ACTIVE hold istekne sistemskim job-om. | EXPIRED sa DB-clock vremenom i determinističkim receipt-om; bez lažnog release actor-a. |
| M17-QA-082 | WAITING_FOR_SUBJECT request. | Oba pause polja su non-null; u drugim neterminalnim stanjima su null. |
| M17-QA-083 | Request se proglasi COMPLETED bez response document-a ili pre terminalnih taskova. | DB/application guard odbija; nema lažnog completion-a. |
| M17-QA-084 | PrivacyTask lease istekne dok stari worker commit-uje. | Fencing odbija stale commit; retry dobija novi token/generaciju. |
| M17-QA-085 | ACCESS export izgradi dva segmenta za account requester-a; zasebno ručno verifikovani requester nema UserAccount. | Self-service manifest pokriva uređene hash-eve i ticket važi samo requester account-u. Accountless slučaj nema self ticket: koristi CONTROLLED_STAFF_HANDOFF DRAFT→APPROVED uz različitog approver-a, staff step-up i mode-bound ticket; nijedan byte/link/password/prilog ne ide emailom. |
| M17-QA-086 | Dva paralelna consume-a istog export ticket-a. | Tačno jedna download session; drugi zahtev 404/410 bez target oracle-a. |
| M17-QA-087 | Range resume tokom važeće export session. | Svaki range reautorizovan; fiksni TTL se ne produžava. |
| M17-QA-088 | Guardian/authorization revoke pre sledećeg range-a. | Byte nije vraćen; session REVOKED i audit bez PII. |
| M17-QA-089 | AVAILABLE artifact pređe 24h. | EXPIRED, svi objekti obrisani po receipt-u; manifest/status ostaju prema retention policy-ju. |
| M17-QA-090 PAR | Export traži 21 segment ili prelazi kompletan limit; zasebno dva staff actor-a paralelno završavaju odobren handoff, jedan bez recipient re-verification-a. | Limit daje 413 ili zasebno odobrene artifact-e bez truncation-a. Samo jedan validan completion daje CONSUMED, package hash i artifact REVOKED/deletion receipt; pokušaj bez in-person provere je 409 `M17_HANDOFF_INVALID`, bez lažnog delivery-ja. |
| M17-QA-091 | ADULT_SELF decision sa guardian/participant poljem ili CHILD bez njih. | DB conditional CHECK odbija; ispravni subject modeli prolaze. |
| M17-QA-092 | Isti `request_id` i idempotency key se legitimno koriste u školi A i školi B. | Nastaju dva potpuno odvojena tenant-scoped `PrivacyCommandReceipt` rezultata; nema unique kolizije, cross-tenant replay-a niti vraćanja ID-ja iz druge škole. |
| M17-QA-093 | Dva system worker-a upisuju isti privacy command receipt uz null account. | Nenull isti `actor_scope_key=SYSTEM:<job_key>` i unique daju tačno jedan receipt/efekat; drugi je idempotentni replay. |
| M17-QA-094 | AUTHENTICATED_WEB_PWA decision nema giver account ili recorder nije isti nalog/sesija. | DB/application guard odbija; nema M17/M15/audit/outbox/receipt upisa. |
| M17-QA-095 | STAFF_ASSISTED decision nema stvarni staff recorder, step-up, permission, giver presence ili reason. | 403/422 i potpuni rollback. |
| M17-QA-096 | Ovlašćeni staff beleži odluku prisutnog davaoca koji nema SOKOLA nalog. | Decision i evidence imaju giver Person, null giver account i stvarni staff recorder/basis/reason; ne kreira se nalog. |
| M17-QA-097 | API_MIGRATION nema trusted system identity, source system/hash ili reason. | 422; nema odluke niti evidence-a i nema pretpostavljenog opt-in-a. |
| M17-QA-098 | Dokaziva istorijska odluka davaoca bez SOKOLA naloga se migrira. | M17/M15 imaju isti giver/subject, trusted recorder, source proof i istorijski occurred/effective datum; giver account ostaje null. |
| M17-QA-099 | M17 i M15 se razlikuju po recorder/channel/source proof-u iako je decision isti. | Coordinator odbija i rollback-uje sve owner upise, audit/outbox i receipt. |
| M17-QA-100 | `ConsentGiverState=RECONSENT_REQUIRED` ima non-null effective datum ili NOT_ASKED zadržava head. | DB CHECK odbija; istorijski head je dozvoljen samo u RECONSENT_REQUIRED i nikad ne daje aktivan consent. |
| M17-QA-101 | ConsentEffectiveState ima effective/reason kombinaciju protivnu svom stanju. | DB CHECK odbija; `state_changed_at` ostaje obavezan. |
| M17-QA-102 PAR | Dve platform retention verzije sa null school i istim key/version ili dva preklapajuća school override intervala. | Nenull `policy_scope_key` + unique/exclusion constraint odbijaju duplikat/preklapanje; nema SQL NULL rupe. |
| M17-QA-103 | EMAIL_INTAKE DSAR pokušava direktno RECEIVED sa izmišljenim assurance/Person/verification vezama; authenticated intake ima i nema dovoljan assurance. | Email je IDENTITY_PENDING+UNVERIFIED sa restricted M15 intake dokumentom i null Person/subject/basis/method/actor/time vezama; authenticated zahtev je RECEIVED samo uz dokazanu sesiju/basis i usklađen immutable verification trio, inače IDENTITY_PENDING. |
| M17-QA-104 PAR | Dva consent projection update-a koriste istu `version`, a M15 pokušava fizički FK nazad ka M17. | Jedan CAS commit, drugi 409/recompute; dependency/schema test potvrđuje samo M17→M15 fizičke reference. |
| M17-QA-105 PAR | Requester i worker paralelno izvrše `CancelDataSubjectRequest` i LEASED owner task; testira se varijanta pre owner poziva, posle durable owner receipt-a i trka sa `CompleteAll`. | Pre owner poziva task je CANCELLED i request završava CANCELLED bez response document-a; durable owner receipt daje SUCCEEDED task i PARTIALLY_COMPLETED sa M15 odgovorom; request-row lock+expected version daju tačno jedan terminalni ishod. Nijedan request-owned task ne ostaje aktivan, policy task bez `request_id` nije dotaknut. |
| M17-QA-106 PAR | Dva verifikatora paralelno pokušaju da EMAIL/STAFF intake vežu za različite requester/subject parove; manual metod pokušava da sačuva kopiju/broj dokumenta; zasebno se REJECTED zahtev završava bez response dokumenta. | Tačno jedan expected-version identity binding sa usklađenim method/assurance/actor/time triom može uspeti, nema email auto-linka, kopije/broja dokumenta ni cross-tenant oracle-a; drugi dobija 409. REJECTED bez M15 response document-a je DB/application-invalid. |
| M17-QA-107 PAR | IDENTITY_PENDING proof stiže pre, tačno na i posle `min(received_at+168h,statutory_due_at)` istovremeno sa `privacy.dsar_orchestration`; pokušava se i direktan CancelByRequester pre verifikacije, pa se job ponavlja. | Sveži DB cutoff, ne redosled worker-a, odlučuje: samo proof proveren pre deadline-a može dati VALIDATING; na/posle deadline-a nastaje jedan EXPIRED receipt. Nevezan intake se ne može označiti requester-CANCELLED, nema oživljavanja, duplog audit/receipt-a ni brisanja M15 intake dokaza. Acceptance zahteva 107/107 stvarno izvršenih testova bez failed/skipped/flaky. |

## Traceability

| Ugovor | Master | QA |
|---|---|---|
| Purpose/legal basis/granularity | §2.1–2.6, §3 | 1–30 |
| Subject requests/rights | §2.9, §3, §5.3 | 31–40, 51–55, 103, 105–107 |
| Retention/legal hold/tasks | §§2.7–2.8,2.10,5.4,7 | 41–52 |
| Tenant/security/privacy | §4, §7 | 13–14, 36–37, 53–70 |
| Ownership/dependencies | §1, §2.12 | 71 |
| Conditional-null i lifecycle | §§2.12,5 | 79–84, 91, 102–107 |
| Privacy export/download | §§2.11,5.5,7 | 85–90 |
| Evidence actor/source proof | §§2.4,2.12,3 | 94–99 |
| Complete suite | §8 | 107 |

Seed mora sadržati dve škole i sve varijante iz master §8. Test tagovi: `m17-unit`, `m17-db-constraints`, `m17-api`, `m17-tenant-negative`, `m17-subject-negative`, `m17-consent`, `m17-dsar`, `m17-retention`, `m17-legal-hold`, `m17-worker-concurrency`, `m17-storage`, `m17-observability`, `m17-migration`.
