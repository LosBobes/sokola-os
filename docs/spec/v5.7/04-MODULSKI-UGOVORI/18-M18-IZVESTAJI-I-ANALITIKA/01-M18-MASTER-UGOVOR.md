---
tip: modulni-implementacioni-ugovor
modul-id: M18
naziv: Izveštaji i analitika
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
schema-zavisnosti: [M04]
read-portovi: [M04, M06, M07, M08, M09, M10, M11, M12, M13, M14, M16, M17]
consumes-events-from: [M04, M06, M08, M09, M10, M11, M12, M13, M14, M16, M17]
application-guardovi: [M01, M03, M05]
platform-interface: [M21]
izlazni-portovi-za: [M19]
offline-policy: DENY
horizont: H0_MVP_REQUIRED
---

# M18 — Izveštaji i analitika: master ugovor

## 1. Cilj i granice

M18 daje tačne, objašnjive i tenant-safe operativne izveštaje nad kanonskim podacima vlasničkih modula. Poseduje katalog metrika, definicije izveštaja, materijalizovane projekcije, refresh run, snapshot, export job i receipt. Ne poseduje niti menja Person, upis, termin, prisustvo, finansijski ledger, poruku, notifikaciju ili događaj.

H0 ima tačno sedam površina: `SCHOOL_OVERVIEW`, `MEMBERSHIP_ENROLLMENT`, `SCHEDULE_CAPACITY`, `ATTENDANCE`, `FINANCE`, `COMMUNICATION`, `EVENTS`. Svaki rezultat prikazuje period, School IANA zonu, `as_of`, freshness, completeness, definiciju metrike i dozvoljen drill-down.

Non-goals: računovodstveni/fiskalni izveštaj; poreska prijava; BI data lake; proizvoljni SQL/report builder; cross-school benchmarking; rangiranje dece/trenera; dijagnoza/predikcija; LTV/churn forecast; marketing attribution; obračun plata; venue-rental komercijala; menjanje izvornog zapisa; offline generisanje; automatsko slanje izveštaja. Te mogućnosti zahtevaju zaseban ugovor/flag i ne utiču na H0 PASS.

## 2. Tipovi, entiteti i polja

Svi ID-jevi su UUID; `*_at` su UTC `TIMESTAMPTZ`; poslovni datum se izvodi u School IANA zoni. Polje je obavezno osim kada piše nullable. Aggregate/command red sa surrogate `id` koristi tenant-prefiksirani PK/UNIQUE; keyed projection/receipt bez `id` ima eksplicitni kompozitni PK/UNIQUE koji počinje sa `school_id` i nijedan tenant-less lookup. Novac je `NUMERIC(18,2)` ili strogo ekvivalentan decimal, API/export kao kanonski decimalni string + ISO 4217. Procenat koristi tačan decimalni ugovor; udeo podskupa je 0–100, dok iskorišćenost WARNING kapaciteta sme biti iznad 100. Agregacija i izračunavanje koriste proširenu decimalnu preciznost bez overflow-a ili clamp-a; odnos se interno računa većom preciznošću pa `ROUND_HALF_UP` na 4 decimale. Nema float-a.

### 2.1 `MetricDefinitionVersion`

Immutable posle publish-a: `id`, `metric_key varchar(96)`, `version_no int`, `surface enum(SCHOOL_OVERVIEW,MEMBERSHIP_ENROLLMENT,SCHEDULE_CAPACITY,ATTENDANCE,FINANCE,COMMUNICATION,EVENTS)`, `name_i18n_key`, `description_i18n_key`, `value_type enum(COUNT,MONEY,PERCENT,RATIO,DURATION)`, `unit nullable`, `numerator_definition`, `denominator_definition nullable`, `zero_denominator_rule enum(ZERO,NULL_NOT_APPLICABLE) nullable`, `time_basis enum(EVENT_INSTANT,AS_OF_END,INTERVAL_OVERLAP,LOCAL_BUSINESS_DATE)`, `source_contract_versions jsonb`, `allowed_dimensions text[]`, `default_date_range`, `max_interactive_days`, `sensitivity enum(AGGREGATE,CHILD_DERIVED,FINANCIAL)`, `minimum_cohort_size int`, `effective_from`, `effective_until nullable`, `status DRAFT|PUBLISHED|RETIRED`, `content_hash char(64)`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`. Unique `(metric_key,version_no)`; objavljeni efektivni intervali istog `metric_key` ne smeju se preklapati i za jedan instant postoji najviše jedna verzija. Denominator i zero-denominator rule su oba obavezna za PERCENT/RATIO, a oba null za COUNT/MONEY/DURATION.

U H0 je `minimum_cohort_size=5` tačno za CHILD_DERIVED, a `0` za AGGREGATE/FINANCIAL; nijedna report definicija ili tenant view ne može sniziti metric prag.

`numerator_definition` i `denominator_definition` nisu SQL, template ili izvršivi kod, već zatvoreni versioned deklarativni AST. Dozvoljeni node tipovi su tačno `FACT_FIELD`, `CONSTANT_DECIMAL`, `COUNT_DISTINCT`, `SUM`, `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE_NULL_SAFE` i `MAX_ZERO`; operand može referencirati samo published registry `fact_type.field_key`, a filter samo allow-listed dimension/operator/value schema. Maksimalna dubina je 8, najviše 32 node-a i 16 filter uslova. Zabranjeni su proizvoljna funkcija, join, subquery, SQL/string expression, script, network/file poziv i user-supplied field. Publish kompajlira AST u determinističan plan, validira type/unit/currency i hashira canonical JSON; runtime izvršava samo taj plan.

### 2.2 `ReportDefinitionVersion`

`id`, `report_key`, `version_no`, `surface` iz istog enum-a, `metric_versions jsonb`, `allowed_filters jsonb`, `allowed_groupings jsonb`, `default_sort`, `drilldown_contract`, `export_schema_version`, `max_interactive_days`, `effective_from`, `effective_until nullable`, `status DRAFT|PUBLISHED|RETIRED`, `content_hash`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`. Immutable posle publish-a osim lifecycle/effectivity polja; objavljeni intervali istog `report_key` se ne preklapaju; nema user SQL/formule. Tenant može sačuvati samo dozvoljen view nad ovom definicijom.

### 2.3 `SavedReportView`

`id`, `school_id`, `owner_account_id`, `report_definition_version_id`, `name varchar(120)`, `normalized_name`, `canonical_filter_json`, `canonical_grouping_json`, `visibility enum(PRIVATE,SCHOOL_SHARED)`, `status ACTIVE|ARCHIVED`, `archived_at nullable`, `version`, `created_at`, `updated_at`. Shared zahteva `school.reports.manage`; filter ne sme sadržati ime, email, slobodan tekst ili tuđi child ID bez subject prava. Unique `(school_id,owner_account_id,normalized_name)` za ACTIVE; `archived_at` je null iff ACTIVE.

### 2.4 `ReportProjectionCheckpoint`

`school_id`, `projection_key`, `projection_version`, `source_positions jsonb`, `required_source_streams jsonb`, `last_complete_recorded_cutoff nullable`, `last_complete_effective_cutoff nullable`, `status HEALTHY|LAGGING|REBUILDING|FAILED`, `started_at`, `completed_at nullable`, `failure_code nullable`, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token bigint`, `version`, `updated_at`. Unique `(school_id,projection_key)`. REBUILDING jedini ima lease hash/until i `completed_at=NULL`; HEALTHY/LAGGING imaju oba complete cutoff-a i completed time; FAILED zahteva completed time+failure code. Za svaki obavezni M21 producer stream pozicija čuva poslednji kontigvni `producer_sequence_no`, potvrđeni stream-head/barrier i schema version. Najveći viđeni broj ili timestamp nije dokaz kompletnosti kada postoji sequence gap.

### 2.5 `ReportFact` i `ReportSourceReceipt`

Implementacija može koristiti normalizovane projection tabele ili ekvivalentan read model, ali svaki red obavezno ima `id`, `school_id`, `fact_type`, `source_module`, `source_stream_key`, `producer_sequence_no`, `source_message_id`, `source_entity_id`, `source_version`, `effective_from`, `effective_until nullable`, `recorded_at`, `local_business_date`, dozvoljene opaque dimension ID-jeve, `count_value nullable BIGINT`, `decimal_value nullable NUMERIC(28,8)`, `duration_millis nullable BIGINT`, `currency_code nullable ISO4217`, `fact_effect enum(UPSERT,TOMBSTONE)`, `supersedes_fact_id nullable`, `projection_version`, `ingested_at`. UPSERT zahteva tačno jedno od tri typed value polja; MONEY zahteva decimal+currency, druga dva tipa zabranjuju currency. TOMBSTONE zahteva sva value/currency polja null. Unique `(school_id,source_message_id,fact_type)` i `(school_id,source_module,source_entity_id,source_version,fact_type)`. Nema imena, kontakta, health/consent sadržaja, raw poruke, bank reference ili dokument sadržaja. Ispravka izvora pravi novu bitemporalnu verziju/tombstone; nikad ne prepisuje činjenicu potrebnu ranijem knowledge preseku i ne sabira se sa prethodnom efektivnom verzijom.

`ReportSourceReceipt`: `school_id`, `projection_key`, `source_stream_key`, `producer_sequence_no`, `source_message_id`, `payload_hash`, `source_schema_version`, `status APPLIED|IGNORED_STALE|QUARANTINED`, `recorded_at`, `processed_at`, `failure_code nullable`. Unique `(school_id,projection_key,source_stream_key,producer_sequence_no)` i unique `(school_id,projection_key,source_message_id)`. `failure_code` je non-null iff QUARANTINED. Isti message ili stream sequence sa drugim hash-em je security/integrity incident. Checkpoint može napredovati samo kroz kontigvan niz receipt-a koji odgovara M21 stream barrier-u.

### 2.6 `ReportSnapshot`

`id`, `school_id`, `report_definition_version_id`, `requested_by_account_id`, `authorization_version`, `canonical_query_hash`, `period_start_local`, `period_end_exclusive_local`, `timezone`, `currency_code nullable`, `effective_as_of`, `knowledge_as_of`, `source_barriers jsonb`, `freshness_status enum(FRESH,STALE,PARTIAL,UNAVAILABLE)`, `missing_source_codes text[]`, `row_count nullable`, `result_object_key nullable`, `encryption_key_ref nullable`, `result_hash nullable`, `expires_at`, `created_at`. Snapshot metadata je immutable; rezultat je šifrovan i tenant-keyed. FRESH/STALE/PARTIAL zahtevaju result object/key/hash i row_count; UNAVAILABLE zahteva sva result polja null i najmanje jedan missing-source code. FRESH/STALE imaju praznu missing listu, PARTIAL ima najmanje jedan opcioni missing code. FINANCIAL rezultat sa nedokazanim obaveznim barrier-om je UNAVAILABLE, ne broj.

### 2.7 `ReportExportJob` i download autorizacija

`ReportExportJob`: `id`, `school_id`, `report_definition_version_id`, `snapshot_id nullable`, `requested_by_account_id`, `authorization_version_at_request`, `canonical_query_hash`, `format CSV|XLSX`, `export_schema_version`, `currency_code nullable`, `status QUEUED|RUNNING|SUCCEEDED|FAILED|EXPIRED|CANCELLED`, `row_limit`, `row_count nullable`, `storage_object_key nullable`, `content_sha256 nullable`, `encryption_key_ref nullable`, `requested_at`, `started_at nullable`, `completed_at nullable`, `expires_at nullable`, `cancelled_at nullable`, `cancelled_by_account_id nullable`, `cancel_reason_code nullable enum(USER_REQUESTED,ADMINISTRATIVE_CANCEL,AUTHORIZATION_CHANGED,SOURCE_INVALIDATED)`, `failure_code nullable`, `idempotency_key_hash`, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token UInt64`, `version`, `updated_at`. RUNNING jedini ima aktivan lease. SUCCEEDED zahteva row/object/hash/key/completed/expires polja i nema failure/cancel; FAILED zahteva failure+completed i nema cancel/result object; CANCELLED zahteva cancel time+reason, USER/ADMIN razlog zahteva actor, SYSTEM razlozi ga zabranjuju; EXPIRED je dozvoljen samo iz SUCCEEDED, briše object/key, zadržava content hash/row count/completed/expires dokaznu metadata-u i nema cancel/failure. Ostali statusi zabranjuju terminalna polja koja im ne pripadaju. Jedan job/fajl pripada jednoj školi, jednoj valuti i jednom schema version-u.

`ReportExportDownloadTicket`: `ticket_digest`, `school_id`, `export_job_id`, `account_id`, `authorization_version`, `issued_at`, `expires_at` najviše 60s, `used_at nullable`, `status ACTIVE|USED|EXPIRED|REVOKED`. `ReportExportDownloadSession`: `session_digest`, `school_id`, `export_job_id`, `account_id`, `authorization_version`, `status ACTIVE|COMPLETED|EXPIRED|REVOKED`, `issued_at`, `expires_at` najviše 10min bez produženja, `last_range_at nullable`, `completed_at nullable`, `version`. Atomski consume pravi tačno jednu sesiju; svaki initial/range zahtev reautorizuje M01/M03/M05, `school.reports.export`, isti school/snapshot/job i current authorization version. Nema javnog/trajnog URL-a; mrežni resume koristi aktivnu sesiju, ne ticket drugi put.

### 2.8 `ReportCommandReceipt`

`id`, `school_id`, `actor_account_id`, `command_name`, `idempotency_key_hash`, `request_hash`, `outcome SUCCEEDED|REJECTED`, `result_ref nullable`, `response_hash`, `created_at`, `expires_at`. Unique `(school_id,actor_account_id,command_name,idempotency_key_hash)`. SUCCEEDED zahteva result ref; REJECTED ga ima null. Čuva se najmanje 30 dana.

### 2.9 Zajednička conditional-null matrica

- Definition DRAFT ima publish/retire actor-vremena null; PUBLISHED zahteva publish par i null retire par; RETIRED zahteva oba para. Novi publish atomarno zatvara prethodni efektivni interval bez menjanja formule prethodne verzije.
- Ticket `used_at` je non-null iff USED; Session `completed_at` je non-null iff COMPLETED. EXPIRED/REVOKED nikad ne vraća byte.
- Stale/istekao lease ne sme promeniti checkpoint, export job, object reference ili snapshot. Storage write se finalizuje pre SUCCEEDED commit-a; orphan privremeni object briše `reports.export_expiry_cleanup` i nikad nije downloadable.

## 3. Kanonske metrike i formule

Intervali su poluotvoreni `[start,end)`. „Na kraju perioda” znači instant neposredno pre `end_exclusive`. Filteri se primenjuju nad izvorom pre agregacije. Distinct se radi po kanonskom owner ID-u, ne po join redovima.

| Metric key | Formula i obavezna semantika |
|---|---|
| `active_participants_end` | COUNT DISTINCT M06 ParticipantProfile čiji su SchoolMembership i ParticipantProfile ACTIVE na kraju perioda i koji ima najmanje jedan M09 ACTIVE enrollment na istom preseku. Neaktivan M06 profil se ne broji čak i ako je stale M09 enrollment ostao ACTIVE. |
| `new_enrollments` | COUNT M09 enrollment čiji M09 `starts_on` ulazi u lokalni poslovni period; reactivation red se broji ako je novi kanonski enrollment, ali isti source ID samo jednom. |
| `ended_enrollments` | COUNT enrollment-a čiji nenulti M09 `ends_on` ulazi u lokalni poslovni period; korekcija istog završetka ne duplira. |
| `net_enrollment_change` | `new_enrollments - ended_enrollments`; nije isto što i razlika snapshot populacija ako postoje migracije/korekcije. |
| `scheduled_occurrences` | COUNT non-cancelled M10 occurrence sa startom u periodu. Otkazan termin je zaseban count. |
| `delivered_occurrences` | COUNT occurrence sa status=SCHEDULED i ends_at<=as_of prema M10 izvedenom COMPLETED pravilu; označava vremenski završene neotkazane termine, ne dokaz da je čas zaista održan; ne izvodi se iz attendance session-a. |
| `scheduled_capacity` | SUM M09/M10 efektivnog capacity snapshot-a za scheduled occurrences; UNKNOWN capacity se isključuje i completeness postaje PARTIAL. |
| `seat_utilization_percent` | `100 * SUM(roster_count_at_occurrence) / SUM(effective_capacity)` samo za occurrence-e sa poznatim capacity; numerator i denominator se prikazuju. Ne koristi attendance. |
| `attendance_recorded_rate` | `100 * COUNT(M11 status IN {PRESENT, ABSENT, LATE}) / COUNT(expected roster entries)` za vremenski završene, neotkazane M10 occurrence-e čiji start ulazi u period. Za occurrence sa M11 session-om denominator je njegov efektivni frozen/corrected M11 roster; bez session-a denominator je istorijski M09 `GetRosterAsOf(group,occurrence.starts_at)` skup koji bi `OpenAttendanceSession` koristio. Neotvoren čas zato daje nula evidentiranih u brojniku, ali njegov očekivani roster ostaje u imenitelju. Zero denominator=`NULL_NOT_APPLICABLE`. |
| `attendance_presence_rate` | `100 * COUNT(status IN {PRESENT, LATE}) / COUNT(status IN {PRESENT, ABSENT, LATE})`; UNRECORDED nije odsutan i izuzima se iz imenitelja; prikazuje recorded coverage. |
| `late_rate` | `100 * COUNT(status = LATE) / COUNT(status IN {PRESENT, ABSENT, LATE})`. |
| `assessed_amount` | SUM M12 `BillingAssessment.total_amount` po assessment period/source pravilima; nulti assessment se uključuje kao 0.00 radi reconciliation-a. |
| `obligated_amount` | SUM non-cancelled M12 `Obligation.amount_due` iz eksplicitno izabranog obligation cohort-a (CREATED_IN_PERIOD ili DUE_IN_PERIOD, default DUE_IN_PERIOD), po valuti i istom as-of preseku kao oba collection/coverage numerator-a. Nikad se ne sabiraju različite valute. |
| `cash_received_amount` | SUM efektivnih M12 PaymentRecord iznosa po `received_at` u periodu; uključuje još nealocirani deo, ali ne FamilyCreditApplication. Prikazuje se kao cash-flow operativna metrika, ne kao pokriće izabranih obaveza. |
| `cash_allocated_amount` | SUM efektivnih PaymentAllocation na izabrani obligation cohort as-of; reversed/corrected allocation ne ostaje efektivan. |
| `credit_applied_amount` | SUM efektivnih FamilyCreditApplication na isti obligation cohort as-of; nije nova gotovinska naplata. |
| `obligation_covered_amount` | `cash_allocated_amount + credit_applied_amount` za isti cohort; PaymentRecord bez allocation-a ne pokriva konkretnu obavezu. |
| `outstanding_amount` | SUM `max(amount_due - effective_allocations - effective_credit_applications,0)` za non-cancelled obligations as-of kraj perioda. |
| `overdue_amount` | outstanding samo gde `due_date < school_local_today(as_of)`; OVERDUE nije status u bazi. |
| `cash_collection_rate` | `100 * cash_allocated_amount / obligated_amount` za isti izabrani obligation cohort. Kredit ne ulazi u numerator. |
| `obligation_coverage_rate` | `100 * obligation_covered_amount / obligated_amount` za isti cohort. Cohort je eksplicitno `CREATED_IN_PERIOD` ili `DUE_IN_PERIOD`, default `DUE_IN_PERIOD`; ne koristi payment-date numerator sa nepovezanim denominatorom. |
| `available_family_credit` | SUM M12 append-only ledger delta as-of MINUS SUM iznosa ACTIVE FamilyCreditReservation u istom family account/currency/as-of preseku; prikazuje se samo finance-ovlašćenom akteru, nikad po detetu. |
| `communication_published` | COUNT svakog zasebnog M13 `PublishedCommunication` čiji `published_at` ulazi u period, tačno jednom po ID-u. Kasnije WITHDRAWN ne briše istorijski publish count; correction poruka se broji kao novi publish jer je novi `PublishedCommunication` sa correction linkom. Draft edit/archive se nikad ne broji. |
| `notification_delivery` | count po M14 terminalnom delivery outcome-u; `DELIVERED` nije `READ`. Read-rate nije H0 ako M14 nema autoritativan read receipt. |
| `event_registrations` | COUNT aktivnih M16 SCHOOL `REGISTERED` ili EXTERNAL `CONFIRMED_PARTICIPANT`; `INTERESTED` je zasebna metrika i nije učesnik. |
| `event_attendance_recorded_rate` | `100 * COUNT(M16 EventAttendance status IN {ARRIVED,NO_SHOW}) / COUNT(M16 EventParticipantSnapshot)` za događaje u periodu; svaki snapshot učesnik ulazi jednom, uključujući UNRECORDED. Zero denominator=`NULL_NOT_APPLICABLE`; ne meša se sa M11. |
| `event_attendance_rate` | `100 * ARRIVED / (ARRIVED + NO_SHOW)`; UNRECORDED je izuzet samo iz ovog outcome rate imenitelja, dok se pokrivenost prikazuje zasebnim `event_attendance_recorded_rate`. |

Svaki money rezultat je particionisan po `currency_code`. H0 School ima jednu valutu, ali query failuje `409 REPORT_CURRENCY_MIXED` ako legacy/projection sadrži više valuta u istom zbiru; ne radi FX konverziju.

## 4. Poslovna pravila i invarijante

1. Metric key+version određuju jedinu formulu; UI ne računa KPI iz sirovih redova.
2. Svaki odgovor vraća `metric_version`, numerator, denominator gde postoji, `effective_as_of`, `knowledge_as_of`, timezone, period `[start,end)`, source barriers, freshness i completeness.
3. Dashboard i export iste definicije, query hash-a, effective/knowledge preseka i source barrier-a daju isti rezultat hash; formatiranje ne menja vrednost.
4. M18 je read-only prema owner modulima. Rebuild projection-a ne emituje poslovni događaj niti menja source.
5. Query je bitemporalan: bira činjenicu čiji efektivni interval važi za `effective_as_of` i čiji `recorded_at` nije posle `knowledge_as_of`. Corrections/reversals zabeleženi posle knowledge preseka ne menjaju postojeći snapshot; novi snapshot sa kasnijim knowledge presekom ih primenjuje bez duplog brojanja originala i korekcije.
6. Empty dataset vraća 0 za count/sum, ali rate sa nultim imeniteljem vraća `null` i `NOT_APPLICABLE`, nikad 0% osim ako definicija izričito kaže ZERO.
7. `effective_as_of` i `knowledge_as_of` ne smeju biti posle server now+clock tolerance 2 min; knowledge presek ne sme biti raniji od minimalnog recorded cutoff-a potrebnog za izabrani snapshot. Budući datum nema buduće činjenice.
8. Interaktivni range max 366 dana. Duži period je async export max 5 godina, ako retention i permission dozvole.
9. Nema implicitnog poređenja perioda različite dužine/DST sati. Calendar poređenja koriste lokalne poslovne datume; duration metrike koriste UTC instants.
10. Parent/guardian portal dobija samo sopstveni subject prikaz preko M28, ne school aggregate M18 endpoint.
11. Instructor vidi samo dodeljene grupe/termine i samo dozvoljene attendance/schedule metrike; nema finance, family credit ili school-wide child count.
12. Small-cohort kontrola važi samo za CHILD_DERIVED analitičke rezultate, ne za operativni, subject-authorized roster. Report definicija dozvoljava samo unapred objavljene dimenzije i tačno jedno nepreklapajuće stablo agregacije po response-u; nema arbitrary NOT/exclusion filtera, proizvoljne liste participant ID-jeva, slobodnog teksta ili paralelnih overlapping total-a. Prvo se svaka leaf ćelija sa manje od 5 distinct participant-a označi `SUPPRESSED`. Zatim se ide deterministički od najdubljeg parent-a ka root-u: ako je parent vidljiv i ima tačno jedno suppressed dete, dodatno se suppress-uje vidljivo sibling dete sa najmanjim distinct-participant count-om, uz tie-break po rastućem kanonskom `dimension_key`; ako sibling ne postoji, suppress-uje se parent. Postupak se ponavlja do fixed point-a, pa se tek onda emituje rezultat. Parent subtotal koristi samo direktnu decu iz istog published stabla. Isti algoritam i isti finalni suppression bitmap važe za UI, cursor stranice i export. Prag smanjuje rizik, ali se ne naziva anonimnošću niti zamenjuje authorization/minimization.
13. Support nema M18 export/drill-down. Standard support vidi samo tehničko projection health bez school business vrednosti; break-glass ne otključava business analytics.
14. `FRESH`: svaki obavezni producer stream ima kontigvne receipt-e do potvrđenog M21 barrier-a za knowledge presek, schema je podržana i lag je unutar objavljenog praga. `STALE`: niz je kompletan, ali potvrđeni barrier/refresh kasni. `PARTIAL`: nedostaje opcioni source/segment ili nije potpuno projektovan, uz eksplicitne opaque kodove. `UNAVAILABLE`: nedostaje required source, postoji sequence gap/hash konflikt/unsupported schema ili se ne može dokazati koherentan presek. Finansijski zbir/rate je `UNAVAILABLE` ako ijedan obavezni M12 stream nije kompletan; nikad PARTIAL headline broj.
15. Projected event se dedupe-uje po message i source entity/version; at-least-once outbox ne menja rezultat. Out-of-order starija aggregate verzija ne vraća current projekciju unazad, ali njen receipt zauzima odgovarajuću stream poziciju. Version 3 pre version 2 ne dokazuje kompletnost: checkpoint ostaje iza rupe dok 2 ili autoritativni tombstone/barrier dokaz ne stigne.
16. Brisanje/pseudonimizacija M17 uklanja zabranjeni drill-down i regeneriše projekciju; zakonito zadržani agregat bez identifikabilnosti može ostati samo po policy-ju.
17. CSV injection neutralizacija: ćelija koja počinje `=`, `+`, `-`, `@`, tab ili CR dobija bezbedno tekstualno kodiranje; formula nikad nije aktivna. XLSX koristi typed cells.
18. Export kolone su allow-list schema; nema hidden UI kolona, raw JSON, encrypted fields, internal reason/actor ili nepotrebnih child podataka.
19. Report nikad ne služi kao authorization dokaz niti source za poslovnu mutaciju.
20. Novi `RunReport`, drill-down i export su offline `DENY`. Finansijski rezultat je uvek network-only/no-store prema M19. Bez mreže UI sme prikazati samo ranije serverski autorizovan, minimizovan NEFINANSIJSKI agregat sa oznakom `STALE` dok su istovremeno važeći lokalni session/context/authorization hard-expiry dokaz i `now-generated_at<=15min`; ako bilo koji uslov nije dokaziv, sekcija je zaključana i cache se briše. Logout, session expiry, access revoke, tenant/context promena ili user switch brišu cache odmah.
21. `RequestReportExport` u jednom commit-u kreira QUEUED red, receipt, audit i `ReportExportRequestedV1`. M21 `reports.export_generate` je jedini generator: claim radi lease/fence, zatim pre prvog source reda i ponovo neposredno pre SUCCEEDED commit-a proverava aktuelne M01/M03/M05 permission/subject/authorization verzije, report/schema/source barrier i School status. Revoke pre publish-a daje CANCELLED/AUTHORIZATION_CHANGED bez finalnog object-a. Streaming je bounded-memory; privremeni object je private, tenant-keyed i ne postaje referenciran/downloadable pre potpunog hash/encryption/row-limit success commit-a.
22. M21 `reports.export_expiry_cleanup` koristi dva odvojena bounded toka: SUCCEEDED sa `expires_at<=database_now` atomarno prelazi u EXPIRED i dobija durable object-deletion receipt; nereferencirani privremeni object-i stariji od 24h brišu se samo kada storage key nije referenciran ni u jednom nonterminal/SUCCEEDED redu. Retry istog cleanup business ključa ne briše tuđ ili noviji object.

### 4.1 Granični slučajevi

| # | Scenario | Determinističko ponašanje |
|---|---|---|
| 1 | DST prelaz u Europe/Belgrade | Lokalni dan se mapira na stvarne UTC granice; dan može imati 23/25h, zapis se broji jednom. |
| 2 | Attendance session je samo delimično evidentiran | UNRECORDED nije ABSENT; presence denominator koristi samo evidentirane, coverage je niži. |
| 3 | Otkazana plaćena obaveza | Efektivni reversal/credit iz M12 uklanja iz outstanding; original ostaje traceable. |
| 4 | Uplata u drugom mesecu za staru obavezu | Collection cohort ostaje po izabranim obligations; as-of payment ulazi u njihov numerator, ne u nepovezan cohort. |
| 5 | Dve valute u legacy podacima | Nema zbirne total vrednosti; 409 ili odvojeni currency rows prema report definiciji. |
| 6 | Event EXTERNAL ima 20 INTERESTED i 5 CONFIRMED | participants=5, interest=20; nikad 25. |
| 7 | Isti outbox event isporučen tri puta | Jedan efektivni fact zbog source/version unique. |
| 8 | Novija pa starija source verzija | Starija se beleži kao ignored duplicate/out-of-order; projekcija ostaje na novijoj. |
| 9 | Actor izgubi grupu tokom otvorenog dashboarda | Sledeći query/drill-down reautorizuje; cache authorization version invalidira; nema stale pristupa. |
| 10 | Filter daje cohort od 1 deteta | Red/count/sugestija suppressed; ne potvrđuje postojanje. |
| 11 | Projection jednog izvora kasni | Result je STALE/PARTIAL; ne spaja fresh finance sa starim denominatorom bez oznake. |
| 12 | Export uspe, zatim actor izgubi pristup | Download ponovo proverava session/tenant/permission/subject/authorization version i odbija; objekat se briše po TTL-u. |
| 13 | Source v3 stigne pre v2 | v3 može biti staged, ali checkpoint ne preskače sequence gap; rezultat koji zavisi od tog stream-a nije FRESH. |
| 14 | Backdated reversal je recorded posle sačuvanog snapshot-a | Stari snapshot hash ostaje; novi knowledge presek primenjuje reversal na odgovarajući effective period. |
| 15 | Jedan suppressed red bi se dobio iz parent total-a | Bottom-up algoritam suppress-uje najmanji sibling (tie-break `dimension_key`) ili parent kada sibling ne postoji; fixed point nema subtraction disclosure. |

## 5. Tenant, RBAC, privacy i security guard

Pipeline je: M01 valid session → M03 server-derived tenant context → M04 ACTIVE/entitlement → M05 permission → report definition → dimension/resource scope → child/financial sensitivity guard → M17 purpose/retention → query. `school_id` iz requesta nikad nije autoritet.

Kanonski M05 ključevi su: `school.reports.overview.view`, `school.reports.membership.view`, `school.reports.schedule.view`, `school.reports.attendance.view`, `school.reports.finance.view`, `school.reports.communication.view`, `school.reports.events.view`, `school.reports.drilldown`, `school.reports.export`, `school.reports.manage`. Nijedan skraćeni oblik koji počinje samo tačkom nije runtime ključ. Owner/Manager ne dobijaju implicitni bypass; role binding je u M05 registru. Finance zahteva poseban permission. Limited Admin/Instructor dobijaju samo assignment-scoped subset. Guardian nema school analytics permission.

Tenant filter i subject scope su deo source CTE/repository-ja pre join-a, group-by, count-a, pagination-a i suppression-a. Composite tenant FK/unique štite projekcije. Cache key sadrži school, actor authorization version, permission-set hash, report+metric versions, canonical filter hash, as-of bucket i projection watermark. Job, storage, cursor, audit i download nose school scope. Cross-tenant/skriven resurs je safe 404 bez row/count/timing indikatora; poznat dozvoljeno vidljiv report bez akcione permission je 403.

PII nije u fact tabelama, metric labelima, cache key-u, eventu ili telemetry-ju. Drill-down resolve-uje opaque ID kroz owner port tek posle ponovne autorizacije i vraća allow-list. Logs: operation, report key/version, pseudonimizovan tenant/actor, latency, rows bucket, freshness/error code; nema filter vrednosti, child ID-a, imena, iznosa ili export sadržaja.

## 6. Lifecycle i state machine

| Entitet | Iz | Operacija | U | Uslov |
|---|---|---|---|---|
| Metric/Report Definition | — | Create | DRAFT | manage |
| Definition | DRAFT | Publish | PUBLISHED | valid formula/schema/hash; nema overlap |
| Definition | PUBLISHED | PublishNewVersion | nova PUBLISHED; stara dobija zatvoren effectivity interval | novi version_no, non-overlap; oba sadržaja immutable |
| Definition | PUBLISHED | Retire | RETIRED | novi query ne bira je; snapshot ostaje dokaziv |
| SavedView | — | Save | ACTIVE | filter schema validan |
| SavedView | ACTIVE | Update | ACTIVE v+1 | expected version |
| SavedView | ACTIVE | Archive | ARCHIVED | terminalno za mutaciju |
| Projection | — | Initialize/Rebuild | REBUILDING | fencing lease |
| Projection | REBUILDING/LAGGING | Complete | HEALTHY | svi required stream receipt-i kontigvni do potvrđenih barrier-a |
| Projection | HEALTHY | Lag detected | LAGGING | prag prekoračen |
| Projection | bilo koji aktivan | Fatal failure | FAILED | failure code, alert |
| Projection | FAILED | Rebuild | REBUILDING | nova fencing generacija |
| ExportJob | — | Request | QUEUED | auth+limits+receipt |
| ExportJob | QUEUED | `reports.export_generate` claim | RUNNING | lease/fence + current auth/source guard |
| ExportJob | RUNNING | Complete | SUCCEEDED | hash+encrypted object |
| ExportJob | QUEUED/RUNNING | Cancel | CANCELLED | requester/manage; fence sprečava publish |
| ExportJob | QUEUED/RUNNING | Fail | FAILED | safe code |
| ExportJob | SUCCEEDED | TTL/single-use expiry | EXPIRED | object deletion |
| ExportDownloadTicket | — | Issue | ACTIVE | current authorization + SUCCEEDED job |
| ExportDownloadTicket | ACTIVE | Consume jednom | USED | pravi jednu ACTIVE DownloadSession |
| ExportDownloadTicket | ACTIVE | ttl/revoke | EXPIRED/REVOKED | bez sesije |
| ExportDownloadSession | ACTIVE | potpun stream | COMPLETED | content hash/length provera |
| ExportDownloadSession | ACTIVE | ttl/revoke | EXPIRED/REVOKED | sledeći range odbijen |

Terminalni: ARCHIVED SavedView; RETIRED definicija; FAILED/CANCELLED/EXPIRED export. SUCCEEDED prelazi samo u EXPIRED. Retry failed export pravi novi job ili idempotentno vraća isti failure za isti request key; ne oživljava red.

## 7. API ugovori, greške, idempotency i concurrency

Queries: `GetSchoolOverview`, `RunReport`, `GetMetricExplanation`, `ListReportDimensions`, `DrillDownReport`, `GetProjectionHealth`, `GetExportJob`, `StreamReportExportRange`. Commands: `Save/Update/ArchiveReportView`, `Request/CancelReportExport`, `Issue/ConsumeReportExportDownloadTicket`, `CompleteReportExportDownloadSession`, `PublishMetricDefinitionVersion`, `PublishReportDefinitionVersion`, `RebuildReportProjection`.

`RunReport` input: report key/version optional-current, local start, exclusive end, canonical typed filters/groupings, `effective_as_of<=now`, `knowledge_as_of<=now`, cursor. Output: schema version, values as strings/counts, numerator/denominator, suppression flags, timezone/currency, source barriers, freshness/completeness, stable cursor. Interactive rows max 2,000; drill-down cursor default 25/max 100. Export ≤100,000 rows/file; veće se odbija, nema silent truncation; object TTL 24h. Download ticket je single-use ≤60s, a range sesija ima fiksni TTL≤10min i current-authorization recheck.

Performance profil `SOKOLA-NFR-REPORTS-V1` koristi jednu veliku sintetičku školu sa 25.000 participant profila, 1.000 grupa, 250.000 godišnjih occurrence-a, 5.000.000 attendance fact verzija i 2.000.000 finansijskih ledger/allocation fact verzija, plus drugi tenant za isolation; 50 konkurentnih aktivnih korisnika; cold i warm cache odvojeno; najmanje 30 merenih ponavljanja posle 5 warm-up poziva. Ciljevi su p95≤800ms za standardni 366-day aggregate i dashboard p95≤1.200ms bez čekanja refresh-a. Rezultat navodi commit, DB/config, dataset hash, query plan i p50/p95/p99; ugovor ne tvrdi da je cilj dostignut pre stvarnog testa.

Svaka command mutacija ima `Idempotency-Key`, canonical request hash i expected version gde postoji. Isti key+isti hash vraća isti receipt; isti key+drugi hash 409. Export unique aktivni `(school,actor,query_hash,format)` može koalescirati identičan zahtev. `reports.export_generate` claim je `FOR UPDATE SKIP LOCKED` ili ekvivalent; lease+fencing sprečava stale DB object/result publish, a inbox dedupe `ReportExportRequestedV1` sprečava drugi logical execution. Projection consumer dedupe-uje message/entity version, ali checkpoint napreduje samo kroz kontigvne stream sequence brojeve do M21 barrier-a. Snapshot se kreira tek kada su svi required segmenti finalizovani za isti effective/knowledge presek; nema half-published ili mešovitog as-of rezultata.

| Code | HTTP | Značenje |
|---|---:|---|
| `REPORT_UNAUTHENTICATED` | 401 | Sesija nevažeća. |
| `REPORT_FORBIDDEN` | 403 | Nedostaje dozvola. |
| `REPORT_NOT_FOUND_SAFE` | 404 | Skriven/cross-tenant report, view, dimension ili job. |
| `REPORT_DEFINITION_INVALID` | 422 | Nepoznata/neobjavljena metrika, formula ili schema. |
| `REPORT_FILTER_INVALID` | 422 | Filter/grouping nije allow-list ili tip nije validan. |
| `REPORT_PERIOD_INVALID` | 422 | Nevažeći/predalek/future period. |
| `REPORT_AS_OF_INVALID` | 422 | Effective/knowledge presek nije dozvoljen ili nije koherentan. |
| `REPORT_SOURCE_GAP` | 503 | Required stream ima sequence gap/hash/schema konflikt; rezultat nije prikazan. |
| `REPORT_CURRENCY_MIXED` | 409 | Nedozvoljen zbir više valuta. |
| `REPORT_VERSION_CONFLICT` | 409 | Expected version/CAS konflikt. |
| `REPORT_IDEMPOTENCY_CONFLICT` | 409 | Isti key, različit request. |
| `REPORT_COHORT_SUPPRESSED` | 422 | Query bi izolovao malo/zaštićeno lice. |
| `REPORT_SOURCE_PARTIAL` | 409 | Kritični report zahteva kompletan source. |
| `REPORT_PROJECTION_UNAVAILABLE` | 503 | Projekcija nema bezbedan rezultat. |
| `REPORT_EXPORT_LIMIT_EXCEEDED` | 413 | Procena/rezultat prelazi limit. |
| `REPORT_EXPORT_EXPIRED` | 410 | Fajl/ticket/session istekao, iskorišćen ili opozvan. |
| `REPORT_EXPORT_NOT_READY` | 409 | Download pre SUCCEEDED. |
| `REPORT_RATE_LIMITED` | 429 | Bezbedni per-tenant/actor limit. |
| `REPORT_STORAGE_FAILED` | 503 | Šifrovani export nije durable. |
| `REPORT_REBUILD_IN_PROGRESS` | 409 | Aktivna fenced rebuild generacija. |
| `REPORT_INTERNAL_SAFE` | 500 | Neočekivana greška bez stack/PII leak-a. |

## 8. Audit, events, migration i acceptance

Audit: publish/retire definicije, shared view promene, export request/complete/download/cancel/expire, manual rebuild i forbidden/suppression incident. Payload: opaque IDs, report/version, filter hash, period, row-count bucket, result/content hash, actor/correlation; bez vrednosti filtera, PII i money vrednosti. Outbox: `ReportDefinitionPublishedV1`, `ReportExportRequestedV1`, `ReportExportCompletedV1`, `ReportProjectionFailedV1`; M18 ne objavljuje source poslovne događaje. Requested event nosi samo job/report/query-hash/schema/actor opaque reference i authorization version, bez filter vrednosti ili rezultata.

Migracija: inventar postojećih dashboard query-ja; svaki `PRESERVE|ADAPT|REMOVE_CONFLICT`; formule se porede na fiksnom golden dataset-u; legacy bez school/source/version ide u exception report i nije aktivan; dual-run shadow poredi counts/money/hash bez PII; cutover tek kada je 100% obaveznih formula jednako, tenant-negative suite prolazi i nema mixed-currency/silent-null. Rollback vraća reader na prethodnu projekciju, ne menja owner data.

Acceptance zahteva: svih sedam površina; formule iz §3; numerator/denominator/freshness; dvotenantske i subject-negative testove; financial reconciliation do centa sa M12; attendance reconciliation sa M11; event distinction; DST; correction/reversal; duplicate/out-of-order events; export injection/TTL/revocation; restore/rebuild; p95 budžete na dokumentovanom dataset-u; nula preskočenih obaveznih QA testova. M18 je `SPEC_CANDIDATE`, ne `IMPLEMENTED`, dok repo, migracije i testovi ne daju dokaz.
