---
modul-id: M18
tip: qa-traceability
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
obavezni-scenariji: 125
---

# M18 — QA, seed i traceability

## 1. Deterministički clock i seed

Clock=`2026-10-31T12:00:00Z`; School A zone=`Europe/Belgrade`, currency=`RSD`; School B zone=`Europe/Zagreb`, currency=`EUR`. A ima Branch A1/A2, grupe G1/G2, petnaest učesnika, dva guardian naloga za isto dete, instructor-a ograničenog na G1 i finance manager-a. B koristi iste lokalne nazive i različite UUID-eve. Periodi uključuju DST 25.10.2026, prazne podatke, cancelled occurrence/obligation/event, correction/reversal, UNRECORDED attendance, unknown capacity, duplicate/out-of-order outbox i mixed legacy currency. Nema realnih PII; domen `example.invalid`.

## 2. QA matrica

| ID | Scenario | Očekivanje |
|---|---|---|
| M18-QA-001 | Publish valid MetricDefinitionVersion. | PUBLISHED immutable, hash/version/audit/outbox. |
| M18-QA-002 | Publish sa nepoznatim source contract-om. | 422 DEFINITION_INVALID; nema promene. |
| M18-QA-003 | Dve preklopljene published verzije. | DB/domain odbija. |
| M18-QA-004 | Edit published definicije. | Odbijeno; nova verzija jedini put. |
| M18-QA-005 | Retire definiciju korišćenu snapshot-om. | Novi query je ne bira; snapshot ostaje dokaziv. |
| M18-QA-006 | Report sadrži user SQL/formulu. | 422; allow-list samo. |
| M18-QA-007 | Save private view. | ACTIVE; canonical filter hash. |
| M18-QA-008 | Shared view bez manage permission. | 403. |
| M18-QA-009 | Dva update-a iste view verzije. | Jedan commit; drugi 409. |
| M18-QA-010 | Archive view pa update. | Terminalno; update odbijen. |
| M18-QA-011 | Active participants sa dva enrollment join reda. | Participant count DISTINCT=1. |
| M18-QA-012 | Enrollment active samo na početku, ne na kraju. | Nije active_participants_end. |
| M18-QA-013 | Start tačno na period start. | Uključen. |
| M18-QA-014 | Start tačno na end_exclusive. | Isključen. |
| M18-QA-015 | Correction menja enrollment end. | Jedan efektivni ended count. |
| M18-QA-016 | New=7, ended=3. | Net change=4; numeratori prikazani. |
| M18-QA-017 | Cancelled occurrence u periodu. | Nije scheduled; cancellation count zaseban. |
| M18-QA-018 | Occurrence završio bez attendance session-a. | Delivered prema M10, ne prema M11. |
| M18-QA-019 | Capacity 10, roster 8. | Utilization=80.0000%. |
| M18-QA-020 | Jedan occurrence capacity UNKNOWN. | Izuzet iz rate; PARTIAL + coverage. |
| M18-QA-021 | Zero known capacity. | Null/NOT_APPLICABLE; nema divide-by-zero. |
| M18-QA-022 | DST lokalni dan 25h. | Svaki occurrence jednom, tačne UTC granice. |
| M18-QA-023 | 6 PRESENT,2 LATE,1 ABSENT,1 UNRECORDED. | Presence=8/9; recorded=9/10. |
| M18-QA-024 | Svi UNRECORDED. | Presence null; coverage=0%. |
| M18-QA-025 | ABSENT zapis. | Nije „opravdan”; ostaje ABSENT. |
| M18-QA-026 | Attendance correction PRESENT→ABSENT. | As-of pre/posle daje odgovarajuće stanje; ne duplira. |
| M18-QA-027 | M16 ARRIVED postoji. | Ne ulazi u M11 rate. |
| M18-QA-028 | M11 PRESENT postoji. | Ne ulazi u M16 event rate. |
| M18-QA-029 | M12 assessments 1000.00+250.50. | assessed=1250.50 exact decimal. |
| M18-QA-030 | PaymentRecord 1000 bez allocation-a. | cash_received=1000.00; cash_allocated/covered za obligations=0.00. |
| M18-QA-031 | Allocation 600 + credit application 100. | cash_allocated=600, credit_applied=100, covered=700; kredit nije cash. |
| M18-QA-032 | Allocation reversed. | Neefektivan u as-of posle reversal-a. |
| M18-QA-033 | Cancel paid obligation generiše credit. | Outstanding 0; credit jednom; reconciliation tačan. |
| M18-QA-034 | Due juče, remaining 50. | overdue=50 prema School local today. |
| M18-QA-035 | Due danas. | Nije overdue (`due_date < today`). |
| M18-QA-036 | RSD i EUR u istom total query-ju. | 409 CURRENCY_MIXED; nema konverzije. |
| M18-QA-037 | Decimal 0.1+0.2. | 0.30, bez float artefakta. |
| M18-QA-038 | Cohort DUE_IN_PERIOD sa cash=600, credit=100, obligations=1000. | cash_collection=60%; coverage=70%; numeratori odvojeni. |
| M18-QA-039 | Uplata ovog meseca za staru obligation van cohort-a. | Ulazi u cash_received po datumu, ali ne naduvava collection/coverage izabranog cohort-a. |
| M18-QA-040 | Family ledger +500-200 i nema ACTIVE reservation. | Available credit=300.00. |
| M18-QA-041 | Non-finance manager traži credit. | 403; nema amount/count leak-a. |
| M18-QA-042 | M13 poruka ima tri edit revision-a istog root-a. | Published communication count=1. |
| M18-QA-043 | M14 DELIVERED bez read receipt-a. | Delivery count da; read rate nije izmišljen. |
| M18-QA-044 | Failed/retried notification terminalno delivered. | Jedan recipient outcome prema M14 efektivnom stanju. |
| M18-QA-045 | SCHOOL event REGISTERED=7, CANCELLED=2. | Active registrations=7. |
| M18-QA-046 | EXTERNAL event INTERESTED=20, CONFIRMED=5. | Interest=20, participants=5. |
| M18-QA-047 | Event snapshot=10: ARRIVED=4, NO_SHOW=1, UNRECORDED=5. | `event_attendance_rate=80%`, `event_attendance_recorded_rate=50%`; M11 nije čitan. |
| M18-QA-048 | Cancelled event sa istorijskim registracijama. | Status filter determinističan; istorija nije obrisana. |
| M18-QA-049 | A actor šalje B school/filter ID. | Safe 404, nula rows/count/cursor/cache/job. |
| M18-QA-050 | A/B imaju isti group naziv. | Samo A UUID scope; nema kolizije. |
| M18-QA-051 | Query count prvo globalno pa UI filter. | Security test pada; nema response-a. |
| M18-QA-052 | Instructor G1 traži school overview. | 403. |
| M18-QA-053 | Instructor G1 traži G2 attendance. | Safe 404. |
| M18-QA-054 | Instructor G1 traži G1 attendance. | Samo assignment-scoped agregat. |
| M18-QA-055 | Guardian direktno pozove school report. | 403/route absent; koristi M28 subject projection. |
| M18-QA-056 | Support traži business KPI/export. | 403; samo PII-free projection health. |
| M18-QA-057 | Break-glass traži finance report. | 403; nema override-a. |
| M18-QA-058 | Cohort od 4 participant-a po filteru. | SUPPRESSED; bez indikatora identiteta. |
| M18-QA-059 | Cohort 5. | Agregat dozvoljen ako svi drugi guardovi prolaze. |
| M18-QA-060 | Published stablo ima jednu primarno suppressed leaf ćeliju; dva sibling-a imaju isti najmanji count. | Dodatno se suppress-uje sibling sa leksikografski manjim kanonskim `dimension_key`; algoritam ide bottom-up do fixed point-a i isti bitmap koriste UI/export. |
| M18-QA-061 | Timing valid/invalid hidden dimension. | Ujednačen safe response envelope; nema existence oracle-a. |
| M18-QA-062 | Projection fact sadrži ime/email. | Schema/privacy test pada. |
| M18-QA-063 | Log sadrži filter child ID ili amount. | Observability test pada/redaction. |
| M18-QA-064 | Cache key bez auth version-a. | Security test pada. |
| M18-QA-065 | Access revoke posle keširanja. | Sledeći request fail-closed; cache nije vraćen. |
| M18-QA-066 | Logout/user switch. | Lokalni agregatni cache obrisan. |
| M18-QA-067 | Offline `RunReport`; uređaj ima ranije autorizovan nefinansijski aggregate star 14 min, zatim session hard-expiry ili tenant switch. | Novi run je DENY. Prethodni aggregate je `STALE` samo dok session/context/auth hard-expiry dokaz važi i starost je ≤15 min; expiry/switch ga odmah zaključava i briše. Finansijski rezultat se nikad ne kešira offline. |
| M18-QA-068 | Svaki required stream je kontigvan do potvrđenog barrier-a za knowledge presek. | FRESH. |
| M18-QA-069 | Kontigvni stream barrier-i kasne iza ciljnog preseka. | STALE, lag prikazan. |
| M18-QA-070 | Nedostaje ili ima gap bilo koji obavezni M12 stream/barrier za finansijsku sekciju. | Finansijska sekcija je `UNAVAILABLE` i nema iznos/rate; druge nezavisne kompletne sekcije smeju se prikazati sa sopstvenim freshness statusom. |
| M18-QA-071 | Projection FAILED bez sigurnog snapshot-a. | UNAVAILABLE/503. |
| M18-QA-072 | Isti outbox event 3 puta. | Jedan fact/rezultat. |
| M18-QA-073 | Producer sequence/version 3 stigne pre 2. | Current fact se ne vraća unazad, ali checkpoint ne preskače rupu; nije FRESH dok 2/barrier dokaz ne stigne. |
| M18-QA-074 | Tombstone/correction event. | Stara efektivna činjenica zamenjena, ne sabrana. |
| M18-QA-075 | Worker padne posle fact commit-a pre checkpoint-a. | Retry dedupe; checkpoint napreduje bez duplikata. |
| M18-QA-076 | Dva rebuild worker-a. | Fencing dozvoljava samo novijem publish. |
| M18-QA-077 | Query tokom rebuild-a. | Poslednji kompletan snapshot STALE ili UNAVAILABLE; nema polovine. |
| M18-QA-078 | Identical dashboard i export snapshot. | Isti query/result hash i vrednosti. |
| M18-QA-079 | Empty count/sum. | 0/0.00; jasno EMPTY. |
| M18-QA-080 | Empty rate. | null NOT_APPLICABLE, ne 0%. |
| M18-QA-081 | Start>end ili range 367 dana interactive. | 422 PERIOD_INVALID. |
| M18-QA-082 | as_of > now+2min. | 422 AS_OF_INVALID. |
| M18-QA-083 | Cursor iz druge škole/query hash-a. | Safe invalid/404; nema rows. |
| M18-QA-084 | Export 100001 red. | 413; nema truncation/fajla. |
| M18-QA-085 | CSV vrednost počinje `=cmd`. | Bezbedan tekst, formula se ne izvršava. |
| M18-QA-086 | XLSX decimal/date. | Typed cell, ista kanonska vrednost/zona. |
| M18-QA-087 | Export sadrži nedozvoljenu hidden kolonu. | Schema test pada; fajl nije publish-ovan. |
| M18-QA-088 | Identičan `RequestReportExport` retry i deset isporuka istog `ReportExportRequestedV1`. | Isti job/receipt, jedan logical `reports.export_generate` execution i najviše jedan finalni objekat. |
| M18-QA-089 | Isti key, drugi filter. | 409 IDEMPOTENCY_CONFLICT. |
| M18-QA-090 | USER cancel RUNNING dok late `reports.export_generate` worker završava. | CANCELLED zahteva USER_REQUESTED+actor+time; fence sprečava SUCCEEDED/object publish, privremeni object nije downloadable. |
| M18-QA-091 | Download pre success. | 409 NOT_READY. |
| M18-QA-092 | Access se opozove pre/dok export radi, odnosno posle SUCCEEDED pre download-a. | Pre publish-a job završava CANCELLED/AUTHORIZATION_CHANGED bez finalnog object-a; posle SUCCEEDED svaki ticket/range read je odbijen i postojeći session REVOKED. |
| M18-QA-093 | Single-use export ticket drugi put. | 410; samo jedna download session. |
| M18-QA-094 | SUCCEEDED object pređe 24h; postoji i nereferenciran temp object stariji od 24h plus noviji object sa sličnim key prefiksom. | `reports.export_expiry_cleanup` daje EXPIRED+durable deletion receipt za tačan finalni object, briše tačan orphan i ne dodiruje noviji/referencirani object. |
| M18-QA-095 | Legacy shadow reconciliation. | Sve obavezne count/money formule identične; ambiguity exception, bez guess-a. |
| M18-QA-096 | Restore projection iz owner izvora. | Rebuild daje isti result hash; tenant-negative prolazi. |
| M18-QA-097 | Ledger balance 100.00, ACTIVE credit reservation 30.00. | `available_family_credit=70.00`; rezervisani iznos nije ponovo potrošiv. |
| M18-QA-098 | Capacity WARNING=10, roster=12. | Seat utilization=120.0000%; nema clamp-a na 100 niti overflow-a. |
| M18-QA-099 | M09 enrollment `starts_on` na local period start. | Broji se; upit ne koristi nepostojeći `starts_at`. |
| M18-QA-100 | Vremenski završen SCHEDULED occurrence bez dokaza održavanja. | Ulazi u tehnički `delivered_occurrences` po M10 izvedenom pravilu, ali UI opis jasno kaže neotkazan završen termin, ne potvrđeno održan čas. |
| M18-QA-101 | Backdated PaymentAllocation reversal zabeležen posle starog knowledge preseka. | Stari snapshot hash ostaje; novi knowledge presek koriguje isti effective period bez dupliranja. |
| M18-QA-102 | Required M12 producer stream ima sequence gap. | Finance sekcija UNAVAILABLE; nema partial headline broja. |
| M18-QA-103 | Jedina leaf ćelija je primarno suppressed; zatim isti rizik nastaje na dva nivoa parent stabla. | Na svakom nivou bottom-up algoritam bira najmanji vidljivi sibling uz `dimension_key` tie-break ili suppress-uje parent bez sibling-a; fixed point i finalni bitmap su byte-identični za UI/export. |
| M18-QA-104 | Instructor radi sa sopstvenom grupom od četiri člana. | Operativni roster/prisustvo ostaju dostupni subject-authorized ruti; M18 child-derived analytics ćelija je suppressed. |
| M18-QA-105 | Dva definition publish-a sa preklopljenim effective intervalima. | Jedan commit; drugi 409; tačno jedna current verzija za instant. |
| M18-QA-106 | Export download prekid i HTTP range resume. | Ista aktivna download session do fiksnog TTL-a; svaki range reautorizovan. |
| M18-QA-107 | NFR profil nije izvršen ili nema dataset/commit/query-plan dokaz. | Nema performance PASS tvrdnje; release evidence ostaje incomplete. |
| M18-QA-108 | Publish `ReportDefinitionVersion` referencira nepoznatu/neobjavljenu metric verziju ili dimenziju nespojivu sa metric schema-om. | 422 `REPORT_DEFINITION_INVALID`; nema delimično objavljene verzije, a prethodna PUBLISHED verzija ostaje jedini izvršivi autoritet. |
| M18-QA-109 | DRAFT metric/report definition. | Publish/retire actor-vremena su null; DB odbija izmišljene vrednosti i PERCENT/RATIO bez denominator pravila. |
| M18-QA-110 | Dva publish-a iste definition verzije/intervala u trci. | Tačno jedan commit; prethodna formula/interval ostaje dokaziv; drugi 409. |
| M18-QA-111 | Projection REBUILDING bez kompletnog source preseka. | Samo lease/fence su aktivni; complete cutoff/time su null; ne može biti FRESH. |
| M18-QA-112 | Stari projection worker završi posle novog fencing tokena. | Nema checkpoint/snapshot promene; orphan privremeni rezultat nije vidljiv. |
| M18-QA-113 | Snapshot UNAVAILABLE zbog required source gap-a. | Result object/key/hash/row_count su null; missing code non-empty; nema headline broja. |
| M18-QA-114 | PARTIAL snapshot bez optional missing code-a ili FRESH sa missing code-om. | DB/schema CHECK odbija obe kombinacije. |
| M18-QA-115 | `reports.export_generate` pokuša SUCCEEDED pre durable encrypted object/hash-a ili bez drugog current auth/source recheck-a. | Commit odbijen; status ostaje RUNNING/FAILED/CANCELLED prema tačnom uzroku, bez downloadable reference. |
| M18-QA-116 | Cancel RUNNING i stale worker object publish u trci. | Fencing/CAS daje CANCELLED; stale object nije referenciran i cleanup ga briše. |
| M18-QA-117 | Dva paralelna consume-a jednog export ticket-a. | Samo jedna ACTIVE download session; drugi 410 bez dodatnog object pristupa. |
| M18-QA-118 | Range resume posle authorization revoke-a. | Ponovna autorizacija odbija byte i session postaje REVOKED; ticket se ne oživljava. |
| M18-QA-119 | SUCCEEDED export pređe 24h TTL. | EXPIRED; object obrisan, dokazna metadata ostaje po retention policy-ju. |
| M18-QA-120 | Regresija kroz postojeći skup 001–119 izvrši se nad tačno evidentiranim repo commit-om, migration head-om i dataset/config hash-em. | Evidencija je potpuna i reproduktivna; nijedan rezultat nije izveden iz dokumentacije bez stvarnog testa. |
| M18-QA-121 | Metric AST sadrži SQL string, unknown funkciju/field, dubinu 9 ili 33 node-a. | Publish 422; ništa izvršivo nije sačuvano. Validan zatvoreni AST daje isti canonical hash i plan u ponovljenom build-u. |
| M18-QA-122 | ReportFact proba dve value kolone, MONEY bez valute, COUNT sa valutom ili TOMBSTONE sa vrednošću. | Svaka nevalidna kombinacija je DB-rejected; validna typed vrednost prolazi bez float konverzije. |
| M18-QA-123 | M06 ParticipantProfile je INACTIVE, ali M09 enrollment je stale ACTIVE; M13 poruka je publishovana pa withdrawn, uz jednu correction poruku. | Participant se ne broji; originalni i correction publish se broje po jednom, withdrawal ne briše istorijski count. |
| M18-QA-124 PAR | Isti source message/sequence istovremeno ulazi u dve projekcije i dvaput u istu projekciju. | Svaka projekcija ima svoj receipt; unutar iste projekcije unique daje jedan efekat. |
| M18-QA-125 | Dva završena occurrence-a imaju po 10 očekivanih polaznika; prvi M11 session ima 9 evidentiranih i 1 UNRECORDED, drugi session nikad nije otvoren. Zasebno se pokušava publish CHILD_DERIVED metrike sa pragom 4. | `attendance_recorded_rate=9/20=45.0000%`; neotvoren termin ne nestaje iz denominatora. Metric publish sa pragom 4 je 422, dok je H0 prag tačno 5. Kompletan prolaz zahteva 125/125, 0 failed/skipped/flaky. |

## 3. Obavezni test nivoi

`m18-unit-formulas`, `m18-db-constraints`, `m18-contract`, `m18-tenant-negative`, `m18-subject-negative`, `m18-finance-reconciliation`, `m18-attendance-reconciliation`, `m18-event-semantics`, `m18-projection-idempotency`, `m18-concurrency`, `m18-export-security`, `m18-privacy`, `m18-performance`, `m18-migration`, `m18-restore`.

Property testovi generišu permutacije source događaja i dokazuju: rezultat ne zavisi od redosleda isporuke; duplikat ne menja rezultat; zbir money komponenti je exact; period particije ne preklapaju/dvostruko broje; tenant B nikad ne menja A rezultat. Golden dataset ručno ima očekivane numeratore/imenitelje i SHA-256 rezultata.

## 4. Traceability

QA 001–010 → master §§2,5–7; 011–048 i 125 → §3–4; 049–067 → §5; 068–080 → §§2.4–2.6,4; 081–094 → §7; 095–108 → §§2–8; 109–119 → §§2.1–2.9,6–7; 120 → kompletna regresija; 121–124 → AST/typed fact/lifecycle/dedupe. Acceptance pada ako je bilo koji scenario skipped/flaky, ako koristi wall-clock/nedeterminističnu spoljnu mrežu, ako money odstupa i za 0.01, ako suppression/tenant test otkrije count ili ako dashboard nema metric version/effective+knowledge as-of/barrier/freshness/numerator/denominator.
