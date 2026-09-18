---
tip: qa-traceability
modul-id: M12
status: SPEC_CANDIDATE
revizija: "1.6"
datum: 2026-09-16
obavezni-scenariji: 114
---

# M12 — QA i traceability

Testovi koriste fiksirani clock/tzdata, exact-decimal biblioteku, dve škole/valute, dve Family grupe sa zajedničkim detetom ali odvojenim payer vezama, iste i različite family account-e, OWNER/MANAGER/LIMITED_ADMIN/INSTRUCTOR/GUARDIAN/PAYER/SUPPORT. `PAR` znači stvarne paralelne DB transakcije.

| ID | Scenario | Očekivanje |
|---|---|---|
| M12-QA-001 | API amount `100.00`. | Prihvaćen exact decimal. |
| M12-QA-002 | `100`, `100.0`, float JSON, >2 decimale. | 422. |
| M12-QA-003 | Decimal property set 10k vrednosti. | Zbir/round bez binary drift-a. |
| M12-QA-004 | Druga valuta u istom account-u. | 422. |
| M12-QA-005 | Publish prva FeeRuleVersion. | ACTIVE immutable version/hash. |
| M12-QA-006 | Preklapajući effective version. | 409. |
| M12-QA-007 | Nova cena posle postojećeg assessment-a. | Stari assessment/obligation ne menja iznos. |
| M12-QA-008 | DAILY_PRORATA flag OFF. | 409/422 pri aktivaciji tog rule-a. |
| M12-QA-009 | Prorata ON, poznat period. | Formula i ROUND_HALF_UP tačni. |
| M12-QA-010 | Attendance varira. | Iznos se ne menja. |
| M12-QA-011 | Generation day 31 u februaru. | Run poslednjeg dana School zone. |
| M12-QA-012 | Due day 31 kraći mesec. | Due poslednji dan. |
| M12-QA-013 | DST scheduler gap/overlap. | Persisted deterministički run instant. |
| M12-QA-014 | Prepare preview. | Nema Assessment/Obligation/outbox notification. |
| M12-QA-015 | Confirm nepromenjen preview. | Sve assessment/obligation nastaju. |
| M12-QA-016 | Fee/enrollment/responsibility promenjen. | 409 stale, nula novih redova. |
| M12-QA-017 | Failure na item 500. | Potpun logical rollback; nema partial success. |
| M12-QA-018 PAR | Dva confirm-a istog perioda. | Tačno jedan set; retry isti receipt. |
| M12-QA-019 | Nulti final assessment. | Assessment trace postoji, Obligation ne. |
| M12-QA-020 | Negativni final assessment. | 422/model correction required. |
| M12-QA-021 | Split OFF, jedan 10000 share. | Jedna obligation. |
| M12-QA-022 | Split OFF, dva share-a. | 409. |
| M12-QA-023 | Split ON, share zbir 9999/10001. | 422/409. |
| M12-QA-024 | Split 50/50 od 100.01. | 50.01/50.00 stabilnim ID redom. |
| M12-QA-025 | Četiri share-a. | Dozvoljeno i zbir tačan. |
| M12-QA-026 | Pet share-a. | 422 limit. |
| M12-QA-027 | Payer link opozvan pre confirm-a. | 409 stale/reference; rollback. |
| M12-QA-028 | Payer nije guardian. | Finance read radi, child data ne. |
| M12-QA-029 | Dva Family account-a dele dete. | Svaki vidi samo svoj obligation/share. |
| M12-QA-030 | Cross-tenant payer/account ID. | 404 safe. |
| M12-QA-031 | Generate IPS QR. | Instruction ACTIVE; obligation unchanged. |
| M12-QA-032 | Sken/expiry IPS bez confirmation-a. | Nema PaymentRecord/PAID. |
| M12-QA-033 | Rotate FinancialProfile. | Stari revoked, novi active; old instruction history. |
| M12-QA-034 | Raw bank/reference log/event/search. | Nema plaintext-a. |
| M12-QA-035 | Manual cash uz permission. | Payment+allocation/credit atomski. |
| M12-QA-036 | Manual cash bez permission. | 403. |
| M12-QA-037 | Bank candidate unique match. | Može POSTED jednom. |
| M12-QA-038 | Ambiguous match. | Nema payment do explicit resolve. |
| M12-QA-039 | Unmatched. | Nema payment. |
| M12-QA-040 | Duplicate provider fingerprint. | 409/isti receipt, bez duplicate money. |
| M12-QA-041 | Uplata 120, dug 100. | Allocation 100 + ledger credit 20. |
| M12-QA-042 | Uplata 50, dug 100. | PARTIALLY_PAID/remaining 50. |
| M12-QA-043 | Dve obligations istog account-a/dvoje dece. | Jedan payment može alocirati obe. |
| M12-QA-044 | Obaveze različitih account-a. | 422 scope mismatch. |
| M12-QA-045 | Obaveze različitih valuta/škola. | 422/404, bez leak-a. |
| M12-QA-046 PAR | Dve allocation poslednjeg remaining iznosa. | Najviše jedna/preostali zbir nikad negativan. |
| M12-QA-047 | Allocation >payment residual. | 409. |
| M12-QA-048 | Allocation >obligation remaining. | 409. |
| M12-QA-049 | Correct allocation. | Old reversal + new allocation + credit delta atomski. |
| M12-QA-050 | Correction failure. | Sve rollback; original efektivan. |
| M12-QA-051 | Reverse neiskorišćen payment/credit. | Payment REVERSED; alokacije/credit neutralisani. |
| M12-QA-052 | Reverse nakon credit application koje se može odmotati. | Compensating entries + target obligation reopen atomski. |
| M12-QA-053 | Reverse nakon external refund-a. | 409 PAYMENT_REVERSAL_BLOCKED. |
| M12-QA-054 | PaymentReversal. | Ne kreira RefundReview. |
| M12-QA-055 | AllocationCorrection. | Ne menja PaymentRecord u REVERSED. |
| M12-QA-056 | RefundReview. | Ne pravi negativan PaymentRecord. |
| M12-QA-057 | Cancel unpaid obligation. | CANCELLED, bez credit-a. |
| M12-QA-058 | Cancel partially/fully paid. | Jednak effective paid iznos postaje credit. |
| M12-QA-059 | Auto-apply OFF. | Novi obligation ne troši credit. |
| M12-QA-060 | Explicit ApplyCredit. | Negative ledger + reduced obligation. |
| M12-QA-061 | Auto-apply ON za novu obligation. | Najstariji credit, zatim due_date/created/id. |
| M12-QA-062 PAR | Dva trošenja poslednjeg credit-a. | Ukupno ≤available, jedan conflict/partial po payload-u. |
| M12-QA-063 | Credit druge škole/family/currency. | Nikad primenjen. |
| M12-QA-064 | Manual ledger DB UPDATE/DELETE. | Zabranjen privilege/trigger/test. |
| M12-QA-065 | Manual correction bez step-up/reason/važećeg dual-control approval-a. | Odbijena bez ledger efekta. |
| M12-QA-066 | Open refund review. | OPEN, credit još nije reserved. |
| M12-QA-067 | Decide refund required. | ACTIVE reservation, available smanjen. |
| M12-QA-068 PAR | Refund reserve i credit apply. | Lock garantuje nema overspend-a. |
| M12-QA-069 | Correct no-refund. | Reservation RELEASED. |
| M12-QA-070 | Confirm external refund bez reservation. | 409. |
| M12-QA-071 | Confirm external refund. | Ledger debit + CONSUMED + status atomski. |
| M12-QA-072 | Refund callback/komanda retry. | Jedan debit/refund receipt. |
| M12-QA-073 | Payer refund projection. | Neutralan status/iznos; nema internal actor/reason/reference. |
| M12-QA-074 | Guardian bez payer basis-a. | Sam guardian odnos ne daje credit account drugog payer-a. |
| M12-QA-075 | Instructor finance endpoint. | 403/404. |
| M12-QA-076 | Support bez aktivnog grant-a. | Odbijeno. |
| M12-QA-077 | Support grant ili break-glass traži payment/ledger/refund/bank scope. | Uvek 403; finance sadržaj i komanda nisu dostupni support-u ni maskirano. |
| M12-QA-078 | Cursor škole B se koristi nad M12 listom škole A; zasebno M18 pokuša finance source read škole B pod A kontekstom. | Safe invalid/404 pre count/page/source reda; nema rows, count-a ni indikatora postojanja. |
| M12-QA-079 | Batch 10001. | Determinističko split/job pravilo, nema memory spike/partial. |
| M12-QA-080 | Klijent poziva navodnu direktnu M12 bulk-export rutu; zatim M18 traži finansijski export procenjen na 100001 red. | M12 ruta ne postoji/ne izvršava job; M18 vraća 413 `REPORT_EXPORT_LIMIT_EXCEEDED`, bez fajla ili parcijalnog artefakta. |
| M12-QA-081 | Offline payment/credit/refund. | Deny; nema finalnog success-a. |
| M12-QA-082 | Optimistic PAID pre servera. | UI contract test zabranjuje. |
| M12-QA-083 | Fee visible pre enrollment/payment. | Dozvoljena public/member projection prikazuje tačan iznos/valutu/uslove. |
| M12-QA-084 | Platform fee nije u FeeRule. | Ne može se dodati pri checkout-u. |
| M12-QA-085 | Idempotency same key/payload. | Isti response, jedan effect. |
| M12-QA-086 | Same key/different payload. | 409. |
| M12-QA-087 | Precommit access revoke. | Rollback. |
| M12-QA-088 | Audit/outbox failure. | Business transaction rollback. |
| M12-QA-089 | Outbox/metrics inspection. | Bez PII/reference/raw amount u notification/metrics. |
| M12-QA-090 | DB tenant-mismatch FK. | Baza odbija. |
| M12-QA-091 | Active spec negative search. | Nema `amount_minor`, `price_minor`, `base_monthly_price_minor`, float/double money. |
| M12-QA-092 | M09/M16 entity schema. | Nema vlasničkog price polja. |
| M12-QA-093 | School SaaS subscription promena. | Ne kreira/menja family Obligation. |
| M12-QA-094 | Family payments promena. | Ne menja M04 CommercialAgreement. |
| M12-QA-095 | EXTERNAL_PROVIDER payment dok adapter flag nije aktivan/verifikovan. | 409 PAYMENT_METHOD_DISABLED; nema PaymentRecord-a. |
| M12-QA-096 | M07 sponsor payer link nema Family, pokušava Responsibility/Credit pristup. | Responsibility 422/409; nema Family credit visibility; school-recorded actual payment ne daje sponsor pristup. |
| M12-QA-097 | Postoje ALL, PROGRAM i GROUP responsibility setovi. | Koristi se samo najviši kompletan važeći scope; share-ovi nivoa se ne sabiraju. |
| M12-QA-098 PAR | Dva različita BillingRun scope-a preklapaju isti source/period. | Najviše jedan Assessment/Obligation; drugi run stale/conflict, bez duplog charge-a. |
| M12-QA-099 | Kreiranje EVENT_REGISTRATION assessment-a bez Event parent ID-a ili sa parentom druge škole. | 422/safe 404 ili DB composite-FK/CHECK odbijanje; nema assessment-a. |
| M12-QA-100 | `CancelAssessmentObligations` nad split 50/50 assessment-om. | Obe obligations CANCELLED i svi compensating ledger/credit redovi, audit, outbox i receipt commit-uju zajedno. |
| M12-QA-101 | Failure posle prvog od dva split cancellation efekta. | Potpuni rollback jednog Assessment-a; nijedna obligation/ledger promena nije efektivna. |
| M12-QA-102 | M16 paid registration cancellation; M12 owner korak failuje. | M16 i M12 rollback u istoj lokalnoj transakciji; registracija ostaje aktivna, nema orphan stanja. |
| M12-QA-103 | Event CANCELLED, `EventCancelledV1` još nije obrađen. | Read vraća `PENDING_MATERIALIZATION`, collectible 0.00; instruction/reminder/allocation su blokirani. |
| M12-QA-104 PAR | Event cancellation commit i event-obligation allocation se trkaju. | Ili allocation prethodi pa cancellation stvara tačan credit, ili allocation dobija `M12_SOURCE_CANCELLED`; nema deadlock-a, gubitka ili duplog novca. |
| M12-QA-105 | Isti `EventCancelledV1` 10× i crash posle 50/120 assessment-a. | Inbox/assessment receipt sprečava duplikate; retry završava preostalih 70; completion emitovan jednom. |
| M12-QA-106 | Potvrđen bank transfer stiže posle event cancellation-a. | PaymentRecord postoji na tačnom account-u; nula allocation-a ka event obligation-u; ceo iznos postaje credit jednom. |
| M12-QA-107 | Event fact unavailable ili version promenjen pre event-backed finance write commit-a. | 503/409 fail closed; nula instruction/reminder/allocation efekta i nula M12→M16 poziva dok M12 lock traje. |
| M12-QA-108 | BillingRun PREVIEW/CONFIRMED/FAILED/CANCELLED conditional polja. | DB prihvata samo tačno odgovarajući confirmed/failure/cancel timestamp+reason skup; početni preview nema izmišljeno terminalno vreme. |
| M12-QA-109 PAR | MANUAL_ENTRY nosi provider/fingerprint ili RECONCILIATION nema jedno od njih; dva zahteva nose isti provider fingerprint. | Nevalidna matrica je odbijena; paralelni validni zahtevi knjiže tačno jedan PaymentRecord. |
| M12-QA-110 | ACTIVE/REVERSED credit application i ACTIVE/RELEASED/CONSUMED reservation matrica. | Samo propisani reversal/resolution timestamp+reason skup prolazi; balance/reservation nikad ne postaje negativan. |
| M12-QA-111 | RefundReview prolazi kroz svaku dozvoljenu statusnu kombinaciju. | OPEN nema odluku; REQUIRED ima tačno jednu ACTIVE rezervaciju; NOT_REQUIRED nema refund dokaz; REFUNDED ima kompletan spoljni dokaz, debit i CONSUMED rezervaciju. |
| M12-QA-112 PAR | Dve iste allocation correction/reversal ili payment reversal komande, uz crash posle pripreme kompenzacija. | Unique causal ključevi i jedna transakcija daju tačno jedan reversal/correction set; retry vraća isti receipt, a crash ostavlja nula parcijalnih redova. |
| M12-QA-113 | `ConfirmBillingRun` za 1 i 10.000 redova bez step-up-a, sa step-up-om starim tačno 5m i sa 5m+1µs. | Bez step-up-a i posle granice vraća `M12_STEP_UP_REQUIRED`; tačno na granici je dozvoljeno po fiksiranom clock-u. Veličina/iznos ne menja pravilo; validan confirm ostaje all-or-nothing. |
| M12-QA-114 PAR | Requester pokuša self-approval; drugi actor odobri pa se promeni amount/account version; approval istekne; klijent pošalje lažni sveži step-up timestamp; dva consume-a istog važećeg approval-a trče paralelno i fault se ubaci pre ledger/consume commit-a. | Self je 403; mismatch/expiry/replay daje `M12_DUAL_CONTROL_REQUIRED`; klijentsko vreme/header/claim se ignoriše i ne osvežava M01 dokaz; validan tačan payload commit-uje jedan MANUAL_CORRECTION i jedan CONSUMED approval ili ništa. Kompletan acceptance zahteva 114/114 stvarno izvršenih testova bez failed/skipped/flaky. |

## Traceability

| Garancija | Normativno | QA |
|---|---|---|
| Exact decimal/currency | 01 §2.1 | 1–4, 9, 91 |
| Fee/billing snapshot i source cancellation | 01 §2.3–2.8, §3 | 5–27, 57–58, 97–107 |
| Payer/tenant/privacy | 01 §2.6, §4 | 28–30, 73–78, 87–90, 96 |
| Payment/IPS/dedupe | 01 §2.9–2.11 | 31–48, 109, 112 |
| Tri korektivna toka | 01 §2.11, §3 | 49–58, 112 |
| Family credit/refund i dual control | 01 §2.12–2.13 | 41, 51–72, 110–111, 113–114 |
| UX/offline/granice | 01 §1, §3, §7 | 79–84, 91–96 |
| Idempotency/concurrency/audit | 01 §3, §7 | 18, 40, 46, 50–53, 62, 68, 72, 85–90, 100–114 |
