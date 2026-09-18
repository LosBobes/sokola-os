---
modul-id: M20
tip: qa-traceability
status: SPEC_CANDIDATE
revizija: "1.8"
datum: 2026-09-16
obavezni-scenariji: 125
---

# M20 — QA i seed

Seed: School A/B, isti nazivi/code vrednosti ali različiti UUID; 5.000-row official CSV/XLSX; shared guardian; exact external references; possible name/email matches; stale group version; malicious formula/macro/ZIP bomb; worker crash/cancel. Clock fiksan; samo `example.invalid`.

| ID | Scenario | Očekivanje |
|---|---|---|
| M20-QA-001 | Start onboarding posle M04 School. | NOT_STARTED nema izmišljenog startera; jedan active run prelazi u IN_PROGRESS i atomski dobija immutable `started_by_account_id+started_at`. |
| M20-QA-002 | Dva paralelna starta. | Jedan run/receipt. |
| M20-QA-003 | School B ID u A context-u. | Safe 404. |
| M20-QA-004 | Organization membership bez school role. | 403/404, nema run-a. |
| M20-QA-005 | Initial owner nije accepted. | Step BLOCKED; nema prečice. |
| M20-QA-006 | Javna registracija/kod škole. | Ne postoji kao onboarding grant. |
| M20-QA-007 | Svi owner facts validni. | READY_FOR_REVIEW, pa ovlašćeni review→READY. |
| M20-QA-008 | READY pa program ugašen. | Re-evaluation vraća IN_PROGRESS/BLOCKED. |
| M20-QA-009 | Obavezni step SKIPPED. | 422. |
| M20-QA-010 | READY označen kao pilot GO. | Zabranjeno; UI/contract razlikuje readiness/pilot. |
| M20-QA-011 | Download official CSV template. | Published schema/hash, UTF-8. |
| M20-QA-012 | Download XLSX template. | Jedan worksheet, bez formula/macro/link. |
| M20-QA-013 | CSV/XLSX isti podaci. | Isti canonical candidate hash. |
| M20-QA-014 | File 10MiB granica. | Tačno limit dozvoljen; +1 byte 413. |
| M20-QA-015 | 5.000 rows. | Dozvoljeno background; 5.001 odbijeno. |
| M20-QA-016 | 101 kolona/cell >2000 scalars. | Parser limit 422. |
| M20-QA-017 | MIME/extension/magic mismatch. | 415. |
| M20-QA-018 | XLSM/macro. | 422 unsafe. |
| M20-QA-019 | Formula sa cached value. | Ceo file odbijen; value se ne koristi. |
| M20-QA-020 | External workbook link/object. | Odbijen. |
| M20-QA-021 | ZIP bomb/password protected XLSX. | Sandbox limit/odbijen. |
| M20-QA-022 | Malware scanner unavailable. | 503 fail-closed, nema parse-a. |
| M20-QA-023 | CSV nevalidan UTF-8. | 422 encoding. |
| M20-QA-024 | BOM validan. | Parsira bez promene headera. |
| M20-QA-025 | Nekonzistentan delimiter. | 422, nema nagađanja. |
| M20-QA-026 | Više/hidden worksheet-a. | Odbijeno. |
| M20-QA-027 | Auto exact header mapping. | AUTO_EXACT samo official schema. |
| M20-QA-028 | Fuzzy header. | MAPPING_REQUIRED; nema auto-confirm. |
| M20-QA-029 | Obavezni target unmapped. | Blocker. |
| M20-QA-030 | Source column mapiran dvaput. | 422. |
| M20-QA-031 | NFKC/trim normalizacija. | Stabilan candidate hash. |
| M20-QA-032 | Email/name isti kao Person. | Sam po sebi nije auto-link. |
| M20-QA-033 | Exact school external_reference. | Exact candidate, ručno/ugovorno potvrdiv. |
| M20-QA-034 | Isti external_reference u B. | Ne utiče na A. |
| M20-QA-035 | Dva reda istog batch-a imaju isti normalizovani row key/isti payload. | Tenant HMAC digest+key-version unique blokira drugi candidate; plaintext key nije u DB/index/logu i nema owner efekta pre potvrde. |
| M20-QA-036 | Isti row key/drugi payload. | 409 conflict, nema last-write-wins. |
| M20-QA-037 | Possible duplicate unresolved. | RESOLUTION_REQUIRED, confirm blokiran. |
| M20-QA-038 | User potvrdi link uz target version. | Resolution zabeležen/auditovan. |
| M20-QA-039 | Target version se promeni. | Resolution STALE; re-review. |
| M20-QA-040 | Create new uprkos exact key konfliktu. | Odbijeno. |
| M20-QA-041 | Child bez guardian obaveznog polja. | Row blocker. |
| M20-QA-042 | Enrollment target group ne postoji u A. | Blocker; import ga ne kreira. |
| M20-QA-043 | Target B group ID. | Safe blocker/404 bez B labela. |
| M20-QA-044 | Finance/document/health kolona. | Unsupported/ignored samo uz explicit mapping; nikad imported. |
| M20-QA-045 | Preview sa warningom. | Zahteva accepted warning set hash. |
| M20-QA-046 | Preview sa blockerom. | Confirm 409. |
| M20-QA-047 | Mapping promenjen posle preview-a. | Preview hash stale. |
| M20-QA-048 | Group version promenjena posle preview-a. | Execute row BLOCKED/stale. |
| M20-QA-049 | Confirm identičan retry. | Isti execution/receipt. |
| M20-QA-050 | Isti key, drugi preview. | 409 idempotency. |
| M20-QA-051 | Batch >500 bez step-up. | 403. |
| M20-QA-052 | Row create success. | M06+M07+M09 i result/audit/outbox atomarno. |
| M20-QA-053 | M07 failure posle M06 attempt-a. | Ceo row rollback; nema orphan-a. |
| M20-QA-054 | M09 failure. | Nema partial child/guardian za taj row. |
| M20-QA-055 | 499 success, 1 failure. | COMPLETED_WITH_ERRORS, tačni counts. |
| M20-QA-056 | Retry committed row posle worker crash-a. | Owner receipts; nema duplicate-a. |
| M20-QA-057 | Shared guardian u 20 paralelnih rows. | Jedan Person, 20 dozvoljenih relations. |
| M20-QA-058 | Dva worker-a claim isti row. | Lease/fence; jedan effect. |
| M20-QA-059 | Late worker posle lease expiry. | Ne commit-uje result. |
| M20-QA-060 | Cancel pre execute. | Direktno CANCELLED, nema owner write-a. |
| M20-QA-061 | Cancel tokom execute-a. | Batch/execution prvo CANCEL_REQUESTED; novi claim i nova owner transakcija prestaju; aktivna završava; zatim CANCELLED i counts su tačni. |
| M20-QA-062 | Retry samo retryable rows. | Terminal/success se ne ponavljaju. |
| M20-QA-063 | Import šalje M02 invite. | Architecture test pada; nema invite-a. |
| M20-QA-064 | Import kreira UserAccount/School/Group. | Architecture test pada. |
| M20-QA-065 | Candidate se pojavljuje u M18 count-u. | Ne pre owner commit/watermark-a. |
| M20-QA-066 | Offline upload/confirm. | Deny; nema IndexedDB PII/final success-a. |
| M20-QA-067 | Raw filename, `import_row_key`, row payload ili external reference u DB indeksu/logu/eventu/dead-letteru; ciphertext envelope se kopira u drugi school/red/field ili mu nedostaje verzija/tag. | Test pada; row key/payload su samo kanonski `CiphertextEnvelopeV1` vezan AAD-om za tenant/red/polje, lookup je tenant-keyed HMAC, a operativni izlazi nose opaque ID/count/safe code. |
| M20-QA-068 | Outbox/deadletter s PII. | Schema odbija. |
| M20-QA-069 | Raw file public URL. | Nikad; signed single-use auth only. |
| M20-QA-070 | Access revoke pre rejected-report download. | Odbijen; object cleanup. |
| M20-QA-071 | CSV injection u rejected report. | Neutralized text. |
| M20-QA-072 | Raw file terminal +7d. | Obrisano po retention job-u. |
| M20-QA-073 | Candidate PII +30d. | Obrisano/pseudonimizovano prema policy-ju. |
| M20-QA-074 | Legal hold obuhvata batch. | Disposition blokiran samo scope-om; pristup se ne širi. |
| M20-QA-075 | Controlled recovery bez later refs. | Owner deactivation uz expected version/audit. |
| M20-QA-076 | Recovery target ima kasniju promenu/reference. | Manual remediation; nema delete-a. |
| M20-QA-077 | 500-row validation performance. | p95≤60s na dokumentovanom fixture-u. |
| M20-QA-078 | 1.000-row performance. | ≤120s ili background progress; monotonic. |
| M20-QA-079 | Tenant fairness, A 5k/B 10 rows. | B ne čeka završetak celog A batch-a. |
| M20-QA-080 | Brownfield/restore run. | Oba formata, 2 tenanta i failure injection prolaze bez implicitnog update-a. |
| M20-QA-081 | Header tačno schema v1. | Svih 16 header-a, redosled i template SHA odgovaraju published ugovoru. |
| M20-QA-082 | Unknown poslovna kolona. | Blokirana; health/finance/document/free-note kolona ne može biti sakrivena kroz IGNORE. |
| M20-QA-083 | CSV LocalDate `01/02/2026`. | Odbijen bez locale guessing-a; samo ISO. |
| M20-QA-084 | XLSX prava date ćelija uz date1904. | Deterministički isti ISO datum i candidate hash kao CSV. |
| M20-QA-085 | XLSX date-time sa 12:00. | Row invalid; vreme se ne odseca tiho. |
| M20-QA-086 | Boolean `DA`, `1` ili prazno za primary. | Odbijen; schema v1 zahteva literal/boolean TRUE. |
| M20-QA-087 | Literal `NULL`, `N/A` ili `-` u opcionom datumu. | Nije implicitni null; tip validation greška. |
| M20-QA-088 | Child external ref `AbC` i `abc`. | Različiti case-sensitive M06 local codes; nema auto-spajanja. |
| M20-QA-089 | Isti logical row u novom batch-u, isti candidate hash. | Digest alias pronalazi jedan `ImportBusinessKeyReceipt` i vraća iste owner receipts; nema owner poziva/duplikata. |
| M20-QA-090 | Isti logical row u novom batch-u, drugi candidate hash. | Isti digest alias daje 409 `IMPORT_ROW_KEY_CONFLICT`; nema update-a ili last-write-wins. |
| M20-QA-091 | Paralelni batch-evi prvi put izvršavaju isti business key. | Unique ACTIVE digest alias daje jedan trajni receipt/owner effect; drugi čita rezultat ili konfliktuje po hash-u. |
| M20-QA-092 | Existing child ref, različito ime/datum. | RESOLUTION_REQUIRED/BLOCKED; Person nije tiho ažuriran. |
| M20-QA-093 | Existing guardian ref, druga email adresa. | Nema auto-update-a ni identity link-a; owner komanda je zaseban kasniji tok. |
| M20-QA-094 | Confirmation bez `GUARDIAN_RELATION_VERIFIED_BY_SCHOOL`. | Execute 409/422; nema ACTIVE guardian link-a. |
| M20-QA-095 | Već postoji drugi ACTIVE primary guardian. | Row blokiran; import ne superseduje designation. |
| M20-QA-096 | Actor ima import.execute, ali nema jedno owner pravo. | Ceo execution odbijen pre prvog claim-a; nema partial write-a. |
| M20-QA-097 | Import u HARD_LIMIT punu grupu. | Row terminalno odbijen po M09; nema capacity override-a. |
| M20-QA-098 | Cancel i worker claim se trkaju. | Status lock/CAS odlučuje; posle CANCEL_REQUESTED nijedna nova owner transakcija ne počinje. |
| M20-QA-099 | NFR run bez dataset/config hash-a ili sa jednim tenantom. | Cilj nije označen dostignutim. |
| M20-QA-100 | Dva CSV fixture-a nose iste logičke vrednosti, jedan koristi LF, drugi CRLF i opcioni završni newline/BOM. | Parser ih kanonizuje po schema v1 u byte-identičan canonical JSON i isti `candidate_hash`; redni/business receipt sprečava drugi owner efekat. |
| M20-QA-101 | NOT_STARTED/IN_PROGRESS/BLOCKED/READY/CANCELLED onboarding field matrica. | DB prihvata samo tačan current-step, immutable start, readiness/review/cancel i blocker skup; NOT_STARTED nema startera, BLOCKED jedini ima blocker-e i nema izmišljenih polja. |
| M20-QA-102 | COMPLETED i SKIPPED step. | COMPLETED zahteva evidence+completion pair; samo neobavezan step sme SKIPPED uz reason. |
| M20-QA-103 | DRAFT/PUBLISHED/RETIRED import schema; school owner, support i aplikaciona DB rola pokušavaju registry write. | Publish/retire system-identity vremena, M21 release evidence i immutable hash prolaze exact conditional CHECK; sva tri runtime write pokušaja su odbijena i stari template se ne menja. |
| M20-QA-104 | Raw file PENDING/CLEAN/REJECTED/FAILED. | Scan engine/time/failure polja su popunjena samo prema statusu; nebezbedan red nije parsiran. |
| M20-QA-105 | Official 16 kolona + jedna potvrđena bezazlena dodatna kolona. | Dodatna je IGNORE, canonical payload/hash isti kao bez nje; nije deo template-a. |
| M20-QA-106 | Dodatna health/free-note/national-ID kolona mapirana IGNORE. | Ceo fajl `IMPORT_SCHEMA_UNSUPPORTED`; sadržaj ne ulazi u staging/log. |
| M20-QA-107 | Mapping AUTO_EXACT/USER_CONFIRMED/IGNORED conditional polja. | DB odbija target/transform/confirmation kombinaciju koja ne odgovara statusu. |
| M20-QA-108 | Candidate REJECTED/EXECUTED/EXPIRED lifecycle. | Tačno odgovarajuće terminalno vreme/actor; ostala stanja ih nemaju. |
| M20-QA-109 | Duplicate LINK/CREATE/REJECT/STALE conditional polja. | Target/version i resolution actor/time/reason odgovaraju tačno statusu; stale target se ne izvršava. |
| M20-QA-110 | Execution RUNNING bez lease hash-a ili terminalan sa aktivnim lease-om. | DB CHECK odbija; plaintext lease se ne čuva/loguje. |
| M20-QA-111 | 100 redova, cancel posle 17 commit-a. | Tačno 17 efektivnih owner outcome-a, 83 unprocessed; zbir svih count-a=100; novi claim ne počinje. |
| M20-QA-112 | COMPLETED_WITH_ERRORS dok postoji FAILED_RETRYABLE red. | Završetak odbijen; retry ili terminalna klasifikacija obavezna. |
| M20-QA-113 | COMPLETED ima rejected/failed/unprocessed count. | DB/application invariant odbija terminalni status. |
| M20-QA-114 | Worker padne posle owner+business receipt commit-a, pre client odgovora. | Retry čita receipt i upisuje jedan dedupe terminal result; ne ponavlja owner write. |
| M20-QA-115 | Terminalni batch sa `terminal_at=NULL` ili FAILED bez failure code-a. | DB CHECK odbija; error ostaje zatvoren i bez PII. |
| M20-QA-116 | Regresija 001–115 se izvrši nad tačno evidentiranim repo commit-om, migration head-om i parser fixture hash-em. | Evidencija je potpuna i reproduktivna; rezultat se ne proglašava na osnovu dokumentacije. |
| M20-QA-117 | CSV header se parsira sa 0 ili 2 moguća delimiter-a, obavezna kolona je pomerena iza 16 ili dodatna kolona stoji između njih. | `IMPORT_SCHEMA_UNSUPPORTED`; parser ne nagađa delimiter niti mapu. Bezazlene IGNORE kolone dozvoljene su samo posle pozicije 16. |
| M20-QA-118 | Phone je validan `+381...`, a druga phone/email/code vrednost počinje formula-risk znakom; rejected report se otvara u spreadsheet-u. | Validan E.164 phone se prihvata; ostalo se odbija; export ćelije su bezbedno escaped i formula se ne izvršava. |
| M20-QA-119 | XLSX sadrži Excel pseudo-datum 1900-02-29, nejasan serial ili date-time 00:00:01. | Red je nevalidan bez locale/epoch guessing-a; nijedan owner write ne nastaje. |
| M20-QA-120 | Isti canonical payload/row key kroz CSV i XLSX, zatim u drugoj školi i tokom svih `STABLE→PREPARING→DUAL_READ→CUTOVER` rotation koraka, uz konkurentan upload/execute. | Isti tenant+verzija daje iste domain-separated hash/digest vrednosti, druga škola različite; svaki živi receipt dobija oba potrebna aliasa, oba lookup-a vode na isti receipt, file dedupe vidi stari aktivni batch, a cutover bez 100% backfill/reconciliation ne prolazi. Stari candidate hash se proverava zabeleženom verzijom bez lažnog konflikta i nijedan plaintext ključ se ne loguje. |
| M20-QA-121 | Onboarding/Execution/Batch CANCELLED nema propisan start/cancel par, SKIPPED step koristi blocker kao reason, mapping se menja posle confirm-a ili Candidate EXECUTED ima rejected actor. | DB/application ugovor odbija svaku kombinaciju; cancel zadržava tačne actor/time dokaze, skip koristi `completion_reason_code`, potvrđeni mapping je immutable, a candidate ima samo statusu pripadajuća terminalna polja. |
| M20-QA-122 | Duplicate match postaje STALE zbog owner target version promene. | System upisuje stale time+safe reason bez lažnog human resolvera; target se ne izvršava. User-resolution status bez actor/time/reason je odbijen. |
| M20-QA-123 PAR | Dva batch-a steknu isti business key preko istog ili dve rotation digest verzije; prvi rollback-uje ili commit-uje owner rezultat. | Rollback ne ostavlja alias/PENDING/final receipt i drugi sme nastaviti; commit ostavlja sve potrebne alias-e ka jednom receipt-u i daje isti rezultat za isti hash ili 409 za drugi, bez duplog owner write-a. |
| M20-QA-124 | Issue report prolazi QUEUED→BUILDING→AVAILABLE ili FAILED i AVAILABLE→download→EXPIRED/REVOKED, uključujući dva paralelna consume-a i access revoke pre range-a. | Encrypted report sadrži samo row number/column key/error code; jedna download sesija, terminalni report se ne oživljava, revoke/TTL blokira byte, nema javnog URL-a. |
| M20-QA-125 PAR | `RequestImportIssueReport` se ponovi, source issue set se promeni, dva worker-a claim-uju isti report, prvi izgubi lease posle object upload-a, authorization se opozove pre publish-a i cleanup se pokrene dvaput. | Jedan QUEUED report/event/receipt; changed source atomarno daje terminalni FAILED sa `IMPORT_REPORT_SOURCE_CHANGED` i bez object polja, a novi request koristi novi source hash; samo aktuelni fencing token može AVAILABLE; revoke daje REVOKED i nula byte-a; cleanup briše final/temp object jednom uz durable receipt. Katalog sadrži tačno jedan `import.issue_report_generate`. Ukupan acceptance zahteva 125/125, 0 failed/skipped/flaky. |

Suite: parser sandbox, schema/property, tenant-negative, duplicate/concurrency, owner transaction, storage/privacy, lifecycle/recovery, performance, migration/restore. QA 001–010 pokriva onboarding; 011–031, 081–088, 100 i 117–120 schema/parser/hash; 032–050, 089–097 i 122–123 duplicate/owner semantiku; 051–066, 098 i 121 concurrency/lifecycle; 067–080, 099 i 124–125 privacy/NFR/download; 101–115 conditional schema/lifecycle/cancel/receipt; 116 reproduktivnu evidenciju. Acceptance pada na jednom skipped/flaky scenariju.
