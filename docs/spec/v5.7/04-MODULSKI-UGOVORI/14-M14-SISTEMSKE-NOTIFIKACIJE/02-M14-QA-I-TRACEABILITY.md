---
tip: qa-traceability
modul-id: M14
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-15
obavezni-scenariji: 69
---

# M14 — QA i traceability

Seed: škole A/B, guardian/payer/staff subjekti, opozvani basis, controllable outbox broker i email provider. Svaki test proverava business redove, consumed-event receipt, audit/outbox i odsustvo PII u logovima.

| QA ID | Scenario | Očekivano |
|---|---|---|
| M14-QA-001 | Validan `OccurrenceRescheduledV1`. | Notification za trenutno ovlašćene pogođene primaoce. |
| M14-QA-002 | Isti event/version 20 puta. | Jedan consumer receipt i jedan notification po recipient/type. |
| M14-QA-003 | Isti event ID, novija verzija. | Nova evaluacija dozvoljena, bez prepisivanja stare. |
| M14-QA-004 | Registrovan validan event type nema M14 policy mapping. | `IGNORED_BY_POLICY`; bez korisničke poruke. |
| M14-QA-005 | Unknown schema version. | Quarantine/terminal attention; bez materialization-a. |
| M14-QA-006 | Payload hash mismatch. | Security failure; bez poruke; PII-safe signal. |
| M14-QA-007 | Source module nije dozvoljen za type. | Odbijeno/quarantine. |
| M14-QA-008 | School ne postoji. | Terminal fail bez existence leak-a. |
| M14-QA-009 | Related entity pripada B, event kaže A. | Odbijeno + security signal. |
| M14-QA-010 | Dva workera isti event. | PK/fencing: jedan side effect. |
| M14-QA-011 | Consumer padne pre commit-a. | Retry pravi jedan rezultat. |
| M14-QA-012 | Consumer padne posle commit-a pre ack-a. | Redelivery je no-op. |
| M14-QA-013 | M14 outage 6h. | Source commit-i uspevaju; backlog se kasnije prazni. |
| M14-QA-014 | Tenant A veliki backlog, B mali. | Tenant-fair obrada; B ne gladuje. |
| M14-QA-015 | `AttendanceRecordedV1`. | Nema mapping-a/notification-a. |
| M14-QA-016 | Attendance correction/lock/sync event. | Nula SystemNotification redova. |
| M14-QA-017 | Finansijski event sa amount parametrom. | Privacy schema odbija parametar. |
| M14-QA-018 | Message params sadrže ime/email/free text. | Odbijeno/terminal fail; podatak nije logovan. |
| M14-QA-019 | Proizvoljan URL umesto route key-a. | Odbijeno route-key registrom. |
| M14-QA-020 | Guardian ACTIVE pri consume-u. | Dobija dozvoljenu subject-scoped notifikaciju. |
| M14-QA-021 | Guardian opozvan pre consume-a. | Nije recipient. |
| M14-QA-022 | Guardian opozvan posle materialization-a. | Read i deep link safe 404. |
| M14-QA-023 | PAYER dobije svoj ObligationCreated. | Samo neutralna finance notifikacija. |
| M14-QA-024 | PAYER pokuša event/attendance obaveštenje. | Nije recipient; nema child hint-a. |
| M14-QA-025 | Staff assignment istekao pre consume-a. | Nema group notification. |
| M14-QA-026 | Account ima dva relevantna basis-a. | Jedan notification po event/type. |
| M14-QA-027 | Recipient account DISABLED. | Delivery SUPPRESSED. |
| M14-QA-028 | Active B context čita A listu. | Nema A rezultata; safe 404. |
| M14-QA-029 | Guardian list. | Samo trenutno autorizovan subject opseg. |
| M14-QA-030 | MarkRead validan. | UNREAD→READ, server UTC. |
| M14-QA-031 | MarkRead retry. | Isti read_at/result. |
| M14-QA-032 | Parallel MarkRead. | Jedna tranzicija. |
| M14-QA-033 | MarkRead tuđe poruke. | Safe 404. |
| M14-QA-034 | Expired notification. | Nije u default listi; retention ostaje. |
| M14-QA-035 | Validan attention event. | Jedan OPEN item. |
| M14-QA-036 | Duplicate attention event. | Bez duplikata. |
| M14-QA-037 | Neovlašćen staff vidi attention. | Deny/conceal. |
| M14-QA-038 | Guardian/PAYER attention query. | Deny/prazno. |
| M14-QA-039 | Resolve validan version/reason. | RESOLVED + audit. |
| M14-QA-040 | Parallel resolve/dismiss. | Prvi commit; drugi 409. |
| M14-QA-041 | Resolution menja source aggregate. | Takav port ne postoji. |
| M14-QA-042 | PLATFORM_SECURITY_ADMIN sa permission+step-up aktivira DRAFT policy. | Nova ACTIVE; stara RETIRED atomski + audit. |
| M14-QA-043 | Paralelne policy aktivacije. | Tačno jedna ACTIVE. |
| M14-QA-044 | School OWNER ili platform actor bez permission/step-up aktivira policy. | 403; nijedna revizija nije promenjena. |
| M14-QA-045 | Izmena ACTIVE policy ili čitanje stare notification istorije. | Izmena odbijena; istorija čuva original policy_revision_no. |
| M14-QA-046 | Email validan. | QUEUED→DISPATCHED. |
| M14-QA-047 | Provider accepted bez delivered dokaza. | DISPATCHED, ne DELIVERED. |
| M14-QA-048 | Transient fail. | Backoff+jitter, max8/48h. |
| M14-QA-049 | Permanent bounce. | PERMANENTLY_FAILED bez retry-ja. |
| M14-QA-050 | Duplicate callback. | Jedna tranzicija. |
| M14-QA-051 | Dva delivery workera. | Lease/fencing: jedan side effect. |
| M14-QA-052 | Email fail. | In-app ostaje. |
| M14-QA-053 | Push flag OFF. | Nema push delivery-ja. |
| M14-QA-054 | Push test flag ON. | Payload samo generic type+opaque ID/route. |
| M14-QA-055 | Offline MarkRead/resolve. | DENY. |
| M14-QA-056 | Support traži params/recipients. | Odbijeno; samo health agregat. |
| M14-QA-057 | Page size 101. | 422/max100; cursor stabilan. |
| M14-QA-058 | Log/trace scan. | Bez payload-a, recipienta, params/provider raw. |
| M14-QA-059 | Cross-tenant FK injection. | DB odbija, bez curenja. |
| M14-QA-060 | Dependency scan. | Nema source→M14/M14→M13 poziva; samo outbox. |
| M14-QA-061 | Validan `CommunicationDraftExpiryWarningRequestedV1`. | Neutralna notifikacija samo current author-u; nema subject/body/audience/child podatka. |
| M14-QA-062 | Warning event se ponovi 20 puta. | Jedan consumed receipt/notification/delivery set. |
| M14-QA-063 | Draft je izmenjen ili purge-ovan pre consume-a. | Current M13 eligibility resolver vraća stale/not-applicable; nema notifikacije. |
| M14-QA-064 | PLATFORM scope event sa null school ID-em ulazi u school notification policy. | Ne materijalizuje school notification; M21 operativni tok preuzima gde je registrovan. |
| M14-QA-065 | Conditional-null DB matrica za DRAFT policy, UNREAD notification, OPEN attention i terminal delivery. | Validne početne kombinacije prolaze bez lažnih timestamp-a; svaka nevalidna kombinacija je DB-rejected. |
| M14-QA-066 | Ista attention source generacija stigne nakon što je prvi item već RESOLVED. | Full semantic unique vraća postojeći terminalni item; nema ponovnog OPEN reda. Nova source generacija pravi nov item. |
| M14-QA-067 PAR | Dva workera planiraju fanout od 1.201 primaoca. | Jedan plan/barrier/hash i uređeni nepreklapajući segmenti; drugi worker dobija isti plan bez duplih delivery-ja. |
| M14-QA-068 | Guardian je u frozen recipient set-u, ali je opozvan pre svog segment commit-a. | Current subject recheck daje SUPPRESSED; nema content/contact leak-a. Ako je opozvan posle materialization-a, list/read/deep link je safe 404. |
| M14-QA-069 | Policy i Delivery lifecycle conditional matrice, uključujući IN_APP provider ref zabranu. | Svaka nedozvoljena actor/time/lease/provider/error kombinacija je DB-rejected; kompletan acceptance zahteva 69/69 stvarno izvršenih testova bez failed/skipped/flaky. |

Obavezni suite: event-schema contract, property dedupe, stvarno paralelni consumer/policy/resolve testovi, two-tenant API/DB, provider callback, backlog fairness, authorization, offline i telemetry-redaction.
