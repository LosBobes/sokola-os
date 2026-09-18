---
tip: modulni-implementacioni-ugovor
modul-id: M12
naziv: Cenovnici, zaduženja, uplate i porodični kredit
status: SPEC_CANDIDATE
revizija: "1.6"
datum: 2026-09-16
schema-zavisnosti: [M04, M06, M07]
read-portovi: [M04, M06, M07, M08, M09, M16]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M13, M14, M15, M17, M18, M19, M20, M21, M28]
offline-policy: DENY
---

# M12 — Cenovnici, zaduženja, uplate i porodični kredit

## 1. Cilj, autoritet i granice

M12 vodi novac koji škola naplaćuje svojim porodicama/platiocima: objavljene cene, deterministički obračun, zaduženja, primljene uplate, raspodelu, korekcije, porodični kredit, instrukcije za plaćanje i kontrolisani dokaz spoljnog povraćaja.

Ovo nije naplata SOKOLA SaaS usluge školi. M04 komercijalni ugovor SOKOLA↔Organization/School ostaje potpuno odvojen i ne kreira M12 `Obligation`/`PaymentRecord`.

M12 nije fiskalna kasa, knjigovodstveni glavni dnevnik, banka, payment processor, SEF/e-faktura ili poreski savetnik. H0 ne tvrdi da je uplata primljena na osnovu generisanog IPS QR koda, ručnog screenshota ili callback-a bez verifikovanog adaptera. Stripe, lokalni provider, fiskalizacija i bank feed ulaze kroz izolovane adaptere/feature flag, bez promene jezgra.

M12 ne poseduje Person/Participant, Family/guardian/payer vezu, Program/Group/Enrollment ili Event. Cene ne smeju biti u M09 Group niti M16 Event. M11 attendance nije input u H0 obračun.

## 2. Money ugovor, entiteti i relacije

### 2.1. `MoneyAmount`

- baza: `NUMERIC(18,2)`/ekvivalentni exact decimal;
- API: decimal string regex `^-?(0|[1-9][0-9]{0,15})\.[0-9]{2}$`;
- valuta: ISO 4217 uppercase, u H0 jedna M04 School currency; svaka money tabela je ipak nosi;
- račun: decimal bez binary float; intermediate scale najmanje 8; samo konačni knjiženi iznos `ROUND_HALF_UP` na 2 decimale;
- zabrane: integer minor-unit kao kanonski API/model, float/double, implicitna valuta, sabiranje različitih valuta.

Nulti ili negativni ulaz nije uplata/zaduženje. Negativni ledger delta je dozvoljen samo tipiziranoj compensating operaciji.

### 2.2. `FinancialProfile`

School profil za instrukciju plaćanja: `id`, `school_id`, `legal_recipient_name`, `bank_account_ciphertext`, `bank_account_fingerprint`, `country_code`, `payment_model_code`, `reference_template_version`, `key_version`, `status` (`DRAFT`, `ACTIVE`, `REVOKED`), `valid_from`, `valid_until nullable`, `created_at`, `revoked_at nullable`, `version`. DRAFT/ACTIVE zahtevaju `revoked_at=NULL`; REVOKED zahteva non-null `revoked_at` i zadržava `valid_from`. `valid_until`, kada postoji, mora biti strogo posle `valid_from`; ACTIVE profil važi samo za `valid_from<=database_now<valid_until` ili bez gornje granice. Najviše jedan efektivni ACTIVE profil po školi i payment modelu. Raw bank account se ne loguje/eventuje/lista; dekriptuje se samo za server generisanje instrukcije ili ovlašćen detail.

### 2.3. `FeeRule` i `FeeRuleVersion`

`FeeRule`: `id`, `school_id`, `code`, `name`, `scope_type` (`PROGRAM`, `GROUP`, `EVENT`), `scope_id`, `billing_frequency` (`MONTHLY`, `ONE_TIME`), `status` (`DRAFT`, `ACTIVE`, `RETIRED`), `current_version_no`, `created_at`, `updated_at`, `version`. Unique school/code; najviše jedno ACTIVE pravilo po scope/frequency, osim eksplicitno kompozabilnih rule type-ova koji nisu H0.

`FeeRuleVersion`: `id`, `school_id`, `fee_rule_id`, `version_no`, `amount`, `currency_code`, `effective_from`, `effective_until nullable`, `billing_timing` (`ADVANCE`, `ARREARS`), `proration_mode` (`FULL_PERIOD`, `FROM_NEXT_PERIOD`, `DAILY_PRORATA`), `published_at`, `published_by_account_id`, `content_hash`. Immutable posle publish-a. Effective periodi istog rule-a se ne preklapaju; `effective_until`, kada postoji, strogo je posle `effective_from`.

Uslovi/cenovnik prikazani korisniku kao dokument pripadaju M15 i tamo se vezuju za `FINANCE` scope uz M12 read-validaciju tačne `FeeRuleVersion`. M12 ne čuva `document_version_id`, ne poziva M15 i ne dobija povratni schema/read dependency; finansijska verzija ostaje autoritet iznosa, valute, perioda i proration pravila.

`DAILY_PRORATA` je podržan model, ali feature `finance.daily_prorata` je default `OFF`. Kada je ON: `round_half_up(base_amount × eligible_calendar_days / calendar_days_in_billing_period, 2)`. Oba broja uključuju početni i isključuju dan posle effective end-a; timezone je School IANA zona. Pauza utiče samo ako kasniji M09 membership ugovor izričito emituje billing-effective interval; ništa se ne izvodi iz attendance-a.

### 2.4. `BillingPolicy`

Jedan aktivan snapshot po školi: `id`, `school_id`, `generation_day` `1..31`, `generation_local_time`, `time_zone`, `default_due_day` `1..31`, `auto_apply_family_credit` bool default `false`, `split_billing_enabled` bool default `false`, `daily_prorata_enabled` bool default `false`, `status` (`ACTIVE`, `SUPERSEDED`), `effective_from`, `version`.

Ako mesec nema generation/due dan, koristi se poslednji kalendarski dan. Job run key je school + lokalni billing period; DST se rešava M10 principom gap forward/earlier overlap, uz persisted UTC run instant.

### 2.5. `FamilyBillingAccount`

`id`, `school_id`, `family_id`, `currency_code`, `status` (`ACTIVE`, `FROZEN`, `CLOSED`), `created_at`, `updated_at`, `version`; unique `(school_id,family_id,currency_code)`. Family je M07 tenant-safe. FROZEN sprečava nova zaduženja/credit trošenje, ne skriva istoriju ili primljenu uplatu. Close zahteva nula otvorenih obaveza, nula credit balance/reservation i nema aktivne odgovornosti.

### 2.6. `BillingResponsibilityRule`

Određuje ko finansijski snosi buduću naknadu, bez davanja child-data prava: `id`, `school_id`, `participant_profile_id`, `family_billing_account_id`, `payer_child_link_id`, `scope_type` (`ALL`, `PROGRAM`, `GROUP`, `EVENT`), `scope_id` null iff ALL, `share_basis_points` UInt16 `1..10000`, `effective_from`, `effective_until`, `status` (`ACTIVE`, `ENDED`), `created_at`, `version`.

Payer link mora biti ACTIVE M07 link za isto dete i Family. Scope precedence je tačno `EVENT > GROUP > PROGRAM > ALL`; koristi se samo najviši nivo koji ima kompletan važeći set, bez sabiranja nivoa. Za svaki participant/scope/effective instant zbir tog seta je tačno 10000. Kada `split_billing_enabled=false`, postoji tačno jedan share 10000. Kada je flag true, maksimalno 4 share-a; iznosi se dele metodom largest remainder: floor na 2 decimale po share-u, preostali centi redom po najvećem necelom ostatku, pa stabilno po rule ID-u. Ukupan zbir mora biti tačno assessment total.

M07 sponsor payer link bez `family_id` nije H0 eligible za `BillingResponsibilityRule` niti FamilyCredit pristup. School admin može evidentirati stvarno primljenu sponzorsku uplatu na izričito izabran FamilyBillingAccount/obavezu, ali sponsor time ne dobija vidljivost Family računa; samouslužni sponsor billing zahteva budući zaseban ugovor.

### 2.7. `BillingRun`, `BillingRunScopeItem` i `BillingAssessment`

`BillingRun`: `id`, `school_id`, `billing_period` (`YYYY-MM` u School zoni), `run_scope_hash`, `status` (`PREVIEW`, `CONFIRMED`, `FAILED`, `CANCELLED`), `policy_version`, `preview_hash`, `included_count`, `excluded_count`, `total_amount`, `currency_code`, `idempotency_key_hash`, `prepared_at`, `confirmed_at nullable`, `failed_at nullable`, `failure_code nullable`, `cancelled_at nullable`, `cancel_reason_code nullable`, `version`. PREVIEW ima sva terminalna polja null; CONFIRMED zahteva samo `confirmed_at`; FAILED zahteva samo `failed_at+failure_code`; CANCELLED zahteva samo `cancelled_at+cancel_reason_code`. Ova matrica je DB CHECK. Partial unique `(school_id,billing_period,run_scope_hash) WHERE status='CONFIRMED'`; ponovno generisanje istog ili preklapajućeg source/period-a dodatno zaustavlja Assessment unique ključ.

`BillingRunScopeItem`: `id UUID`, `school_id UUID`, `billing_run_id UUID`, `source_type` (`GROUP_ENROLLMENT`,`EVENT_REGISTRATION`,`MANUAL_ADJUSTMENT`), `source_id UUID`, `source_parent_id nullable UUID`, `source_version UInt64`, `scope_item_hash CHAR(64)`, `created_at TIMESTAMPTZ`. Tenant-safe FK `(school_id,billing_run_id)` i unique `(school_id,billing_run_id,source_type,source_id)` su obavezni. `source_parent_id` je non-null samo za EVENT_REGISTRATION i tada je M16 Event ID; za ostale tipove je null. Scope nije neograničeni array u jednom polju.

`BillingAssessment`: immutable ukupan obračun za jedno dete/source/period: `id`, `school_id`, `run_id` nullable za one-time, `participant_profile_id`, `fee_rule_version_id`, `source_type` (`GROUP_ENROLLMENT`, `EVENT_REGISTRATION`, `MANUAL_ADJUSTMENT`), `source_id`, `source_parent_id` nullable, `period_start`, `period_end`, `base_amount`, `adjustment_amount`, `total_amount`, `currency_code`, `calculation_facts_json`, `calculation_hash`, `created_at`. Za `EVENT_REGISTRATION`, `source_id=EventRegistration.id` i `source_parent_id=Event.id` su obavezni i potvrđeni istim tenant-bound M16 fact/version snapshot-om u transakciji kreiranja; za ostale source tipove `source_parent_id` je `NULL`. JSON sadrži samo tipizirane billing činjenice/IDs/date/decimal strings; nema PII/free text. Unique school/source/fee-version/period.

Preview ne kreira Assessment/Obligation, ledger ili notification. `ConfirmBillingRun` ponovo izračunava authoritative input hash i sve-ili-ništa kreira assessments i obligations; stale preview je 409.

### 2.8. `Obligation`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `assessment_id` | UUID | NE | Tenant-safe. |
| `participant_profile_id` | UUID | NE | Snapshot subject, ne autorizacioni dokaz. |
| `family_billing_account_id`, `payer_child_link_id` | UUID | NE | Odgovornost važeća na assessment date. |
| `amount_due` | MoneyAmount | NE | `>0`; zbir po assessment-u = total. |
| `currency_code` | ISO 4217 | NE | School/account/assessment ista valuta. |
| `due_date` | LocalDate | NE | School-local datum. |
| `status` | enum | NE | `UNPAID`, `PARTIALLY_PAID`, `PAID`, `CANCELLED`. |
| `cancel_reason_code` | Code64 | DA | Obavezan za cancel. |
| `created_at`, `updated_at`, `version` | InstantUTC/UInt64 | NE | CAS. |

Status je izveden iz efektivnih payment allocation-a i efektivnih `FamilyCreditApplication`, osim eksplicitnog CANCELLED. `OVERDUE` je projekcija: due_date < tenant today, remaining > 0, nije CANCELLED; nije enum. Nulti assessment se čuva radi traceability, ali se ne kreira Obligation.

Za event-backed obligation query dodatno vraća izvedeni `source_cancellation_state` (`NONE`, `PENDING_MATERIALIZATION`, `COMPLETED`). To nije novi `Obligation.status`. Ako M16 autoritativni Event već ima `CANCELLED`, a svi pripadajući M12 redovi još nisu materijalizovani kao CANCELLED, stanje je `PENDING_MATERIALIZATION`, `remaining_collectible=0.00` i nijedna payment instruction, reminder ili nova allocation ka toj obavezi nije dozvoljena.

### 2.9. `PaymentInstruction`

`id`, `school_id`, `family_billing_account_id`, `obligation_id` nullable, `financial_profile_id`, `method` (`IPS_QR`, `BANK_TRANSFER`), `amount`, `currency_code`, `reference_ciphertext`, `reference_fingerprint`, `payload_ciphertext`, `expires_at`, `status` (`ACTIVE`, `EXPIRED`, `REVOKED`), `created_at`, `version`. Generisanje instrukcije nikad ne kreira PaymentRecord ili PAID status. IPS payload se validira prema aktuelnom nacionalnom adapter profilu; adapter verzija je zabeležena.

### 2.10. `PaymentReconciliationCandidate`

Ulaz iz bank/provider adaptera pre potvrde: `id`, `school_id`, `provider_key`, `external_transaction_fingerprint`, `received_amount`, `currency_code`, `received_at`, `reference_ciphertext`, `match_status` (`UNMATCHED`, `SINGLE_MATCH`, `AMBIGUOUS`, `REJECTED`, `POSTED`), `candidate_account_ids` encrypted/opaque projection, `created_at`, `version`. Unique school/provider/fingerprint. `AMBIGUOUS/UNMATCHED` ne kreira uplatu dok ovlašćeni actor ne odabere jedan account uz audit.

### 2.11. `PaymentRecord`, allocation i tri odvojene korekcije

`PaymentRecord`: `id`, `school_id`, `family_billing_account_id`, `payer_person_id nullable`, `method` (`CASH`, `BANK_TRANSFER`, `EXTERNAL_PROVIDER`), `flow_type` (`MANUAL_ENTRY`, `RECONCILIATION`), `received_amount` >0, `currency_code`, `received_at`, `provider_key nullable`, `external_transaction_fingerprint nullable`, `payment_attempt_id UUID`, `status` (`CONFIRMED`, `REVERSED`), `created_by_account_id`, `created_at`, `version`. Unique `(school_id,payment_attempt_id)` je obavezan. RECONCILIATION zahteva non-null `provider_key` i fingerprint; MANUAL_ENTRY zahteva oba null. EXTERNAL_PROVIDER dodatno zahteva aktivan i verifikovan adapter čiji je ključ jednak `provider_key`; u H0 je uvek odbijen. Partial unique `(school_id,provider_key,external_transaction_fingerprint) WHERE provider_key IS NOT NULL AND external_transaction_fingerprint IS NOT NULL` sprečava duplo knjiženje provider transakcije bez oslanjanja na SQL NULL semantiku. Jedan red je jedna stvarno primljena transakcija. H0 prihvata samo CASH i BANK_TRANSFER; IPS QR se knjiži kao BANK_TRANSFER tek posle stvarnog dokaza prijema.

`PaymentAllocation`: immutable `id`, school, payment_record_id, obligation_id, amount >0, created_by_correction_id nullable, created_at. Alocira se samo na non-cancelled obligation iste škole/account-a/valute. Jedna uplata može pokriti više dece samo kada su njihove obaveze na istom FamilyBillingAccount-u, u istoj školi i valuti. Zbir efektivnih allocation-a ne prelazi payment; zbir po obligation-u ne prelazi amount_due.

Tri toka se nikad ne mešaju:

1. `PaymentReversal` — ceo evidencioni zapis nije važeća stvarna uplata; original postaje REVERSED.
2. `PaymentAllocationCorrection` + `PaymentAllocationReversal` — novac jeste primljen, ali je raspodela bila pogrešna; stari allocation-i se append-only poništavaju, novi nastaju atomski.
3. `RefundReview` — novac jeste primljen/credit postoji, odlučuje se da li se spolja vraća; nije negativna uplata i ne menja istoriju bez confirmation-a.

`PaymentReversal` je append-only: `id`, `school_id`, `payment_record_id`, `reversal_reason_code`, `reversed_by_account_id`, `reversed_at`, `command_id`, `command_receipt_id`, `causal_effect_hash`, `created_at`; unique `(school_id,payment_record_id)` i `(school_id,command_id)`. Nastaje atomski sa prelazom originalnog PaymentRecord-a u REVERSED i svim tipiziranim allocation/credit kompenzacijama; originalni payment se ne briše niti mu se menja iznos.

`PaymentAllocationCorrection` je append-only: `id`, `school_id`, `payment_record_id`, `reason_code`, `requested_by_account_id`, `original_effective_allocation_set_hash`, `replacement_allocation_set_hash`, `command_id`, `created_at`; unique `(school_id,command_id)`. Hash originalnog seta mora odgovarati zaključanom efektivnom stanju; mismatch je 409 bez ijednog reversal/new-allocation reda.

`PaymentAllocationReversal` je append-only: `id`, `school_id`, `payment_allocation_id`, `allocation_correction_id nullable`, `payment_reversal_id nullable`, `amount`, `created_at`. Tačno jedan od dva causal ID-a je non-null; `amount` je tačno jednak originalnom allocation iznosu. Unique `(school_id,payment_allocation_id,allocation_correction_id)` kada je correction prisutan i unique `(school_id,payment_allocation_id,payment_reversal_id)` kada je payment reversal prisutan sprečavaju duplu kompenzaciju. Svi FK-ovi uključuju `school_id`.

### 2.12. `FamilyCreditLedgerEntry`, `FamilyCreditApplication` i `FamilyCreditReservation`

Ledger entry je append-only: `id`, `school_id`, `family_billing_account_id`, `entry_type` (`OVERPAYMENT_CREDIT`, `CANCELLED_OBLIGATION_CREDIT`, `CREDIT_APPLICATION`, `APPLICATION_REVERSAL`, `PAYMENT_REVERSAL_DEBIT`, `ALLOCATION_CORRECTION_ADJUSTMENT`, `EXTERNAL_REFUND_DEBIT`, `MANUAL_CORRECTION`), `delta_amount` signed MoneyAmount nonzero, `currency_code`, `source_type`, `source_id`, `causal_entry_id` nullable, `reason_code`, `actor_account_id` nullable za system, `command_id`, `entry_sequence` UInt16, `created_at`. Unique `(school_id,family_billing_account_id,command_id,entry_sequence)` i tip/source causal dedupe sprečavaju ponavljanje, a dozvoljavaju više tipiziranih knjiženja jedne komande. Nema balance kolone koja se ručno prepisuje; balance = suma ledger delta.

`FamilyCreditApplication`: `id`, `school_id`, `family_billing_account_id`, `obligation_id`, `debit_ledger_entry_id`, `amount` >0, `status` (`ACTIVE`, `REVERSED`), `reversal_ledger_entry_id nullable`, `created_at`, `reversed_at nullable`, `version`. ACTIVE zahteva oba reversal polja null; REVERSED zahteva oba non-null. ACTIVE application smanjuje remaining obligation isto kao efektivna PaymentAllocation. Reversal je dozvoljen samo compensating komandom i upisuje jednak pozitivan `APPLICATION_REVERSAL`; stari application/ledger red se ne menja osim lifecycle statusa/version-a.

Pozitivan višak stvarno potvrđene uplate odmah daje `OVERPAYMENT_CREDIT`; ne otvara automatski refund i ne nestaje. Kada policy auto-apply=false, credit čeka explicit `ApplyFamilyCredit`. Kada je true, u istoj transakciji kreiranja nove obaveze koristi se najstariji raspoloživi pozitivan credit, zatim obaveze sortirane `(due_date,created_at,id)`; svaka primena je negativan ledger entry + ACTIVE `FamilyCreditApplication`.

`FamilyCreditReservation`: `id`, `school_id`, `family_billing_account_id`, `refund_review_id`, `amount` >0, `status` (`ACTIVE`, `RELEASED`, `CONSUMED`), `released_at nullable`, `consumed_at nullable`, `resolution_reason_code nullable`, `created_at`, `version`. ACTIVE zahteva sva resolution polja null; RELEASED zahteva samo `released_at+resolution_reason_code`; CONSUMED zahteva samo `consumed_at+resolution_reason_code`. Unique `(school_id,refund_review_id)` osigurava najviše jednu rezervaciju po review-u. Available credit = ledger balance − zbir ACTIVE reservations; nikad <0. Refund-required odluka rezerviše credit; odluka no-refund oslobađa; potvrđen spoljni refund atomski upisuje `EXTERNAL_REFUND_DEBIT` i CONSUMED.

Kredit nikad ne prelazi školu, FamilyBillingAccount ili valutu. Povezana deca u drugim Family account-ima ne dele kredit.

### 2.12a. `FinancialDualControlApproval`

Svaka ručna `CorrectFamilyCredit` korekcija, bez obzira na iznos, zahteva odobrenje druge osobe. Approval nije slobodan tekst niti uploadovani dokaz, već tenant-bound izvršni zapis:

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id` | UUID | NE | PK i tenant; composite FK ka ciljnom account-u. |
| `action_type` | enum | NE | U H0 tačno `FAMILY_CREDIT_CORRECTION`. |
| `target_family_billing_account_id` | UUID | NE | Ista škola; ne otkriva drugi tenant. |
| `canonical_command_hash` | ContentHash | NE | Hash tačnih `school_id`, target ID/version, signed decimal amount, currency i zatvorenog reason code-a. |
| `requested_by_account_id`, `requested_at` | UUID, InstantUTC | NE | Inicijator koji jedini sme kasnije izvršiti vezanu korekciju. |
| `request_step_up_verified_at` | InstantUTC | NE | Na početku request-a starost najviše 5 minuta. |
| `approved_by_account_id`, `approved_at`, `approval_step_up_verified_at` | UUID, InstantUTC | uslovno | Sva tri iff APPROVED/CONSUMED; approver mora biti različit od requester-a. |
| `expires_at` | InstantUTC | NE | Tačno `requested_at + 15 minuta`; ne produžava se odobrenjem ili retry-em. |
| `status` | enum | NE | `PENDING`, `APPROVED`, `CONSUMED`, `REVOKED`, `EXPIRED`. |
| `consumed_command_receipt_id`, `consumed_at` | UUID, InstantUTC | uslovno | Oba iff CONSUMED; isti approval se troši jednom. |
| `revoked_by_account_id`, `revoked_at`, `revocation_reason_code` | UUID, InstantUTC, ReasonCode | uslovno | Sva tri iff REVOKED. |
| `version`, `created_at`, `updated_at` | UInt64, InstantUTC | NE | CAS i audit vremena. |

Partial unique nad `(school_id,target_family_billing_account_id,canonical_command_hash,requested_by_account_id)` za `PENDING|APPROVED` sprečava paralelna otvorena odobrenja istog zahteva. Requester i approver u svojim request-ovima moraju imati važeću M01 sesiju, svež step-up star najviše 5 minuta, isti M03 tenant i `finance.credit.correct`; pre `CorrectFamilyCredit` commit-a oba account-a i permission-a proveravaju se ponovo, approval mora biti APPROVED, neistekao, sa istim hash-em i expected version-om. Payload ili target-version promena zahteva novi approval. Self-approval je 403. Istek je autoritativan na read/command guard-u i bez materialization job-a. Korekcija, MANUAL_CORRECTION ledger entry, approval `APPROVED→CONSUMED`, audit, outbox i command receipt commit-uju zajedno ili ništa.

`request_step_up_verified_at` i `approval_step_up_verified_at` nikad se ne prihvataju iz klijentskog payload-a. Handler ih kopira isključivo iz server-side verifikovanog M01 authentication context-a i poredi sa `database_now`; klijentski timestamp, header ili JWT custom claim ne može osvežiti niti produžiti step-up.

### 2.13. `RefundReview`

`id`, `school_id`, `family_billing_account_id`, `trigger_type` (`PAYER_REQUEST`, `DUPLICATE_PAYMENT_SUSPECTED`, `CANCELLED_OBLIGATION`, `MANUAL`), `source_id`, `requested_amount`, `status` (`OPEN`, `REFUND_NOT_REQUIRED`, `REFUND_REQUIRED`, `REFUNDED_EXTERNALLY`), `decision_reason_code nullable`, `decided_by_account_id nullable`, `decided_at nullable`, `refund_method nullable`, `refund_reference_ciphertext nullable`, `refunded_by_account_id nullable`, `refunded_at nullable`, `version`. OPEN zahteva sva decision/refund polja null. REFUND_NOT_REQUIRED i REFUND_REQUIRED zahtevaju decision reason/actor/time, a sva refund polja ostaju null; REFUND_REQUIRED dodatno zahteva tačno jednu ACTIVE rezervaciju. REFUNDED_EXTERNALLY zadržava decision dokaz i zahteva sva refund polja plus CONSUMED rezervaciju i odgovarajući `EXTERNAL_REFUND_DEBIT`. Refund se nikada izvršava automatski; zapis `REFUNDED_EXTERNALLY` samo potvrđuje dokazano izvršenje izvan jezgra. Payer vidi neutralan status i iznos, ne interne reason/actor/reference podatke.

## 3. Poslovna pravila i invarijante

1. Fee verzija, responsibility share i eligibility uzimaju se `as-of` početka billing perioda/source occurrence-a; kasnija promena ne menja postojeći Assessment.
2. Generisanje je tačno jednom po source/rule/period. Job retry i ručna potvrda istog scope-a ne dupliraju zaduženje.
3. Preview nema finansijski side effect. Confirm je all-or-nothing i stale hash failuje pre prvog Assessment-a. Svaki `ConfirmBillingRun`, bez obzira na broj redova ili iznos, zahteva step-up koji je na početku request-a star najviše 5 minuta; H0 nema tenant-konfigurabilan prag koji bi ovaj uslov mogao isključiti.
4. `amount=0.00` ne pravi Obligation; negativan finalni rezultat je invalid i mora se modelovati korekcijom/credit-om.
5. Split OFF zahteva jednu 100% responsibility. Split ON zahteva zbir 10000 basis points i determinističko 2-decimalno deljenje.
6. Attendance, broj dolazaka i M10 completed ne utiču na H0 članarinu.
7. Generisanje IPS QR/payment instruction-a nije dokaz uplate.
8. Manual payment actor izjavljuje da je novac stvarno primljen; zahteva permission, online server confirm i audit. Bank candidate mora biti POSTED najviše jednom.
9. Allocation zaključava PaymentRecord, FamilyBillingAccount i Obligation-e u stabilnom UUID redosledu; DB/transaction garantuje granice zbira.
10. Residual primljene uplate posle allocation-a postaje credit u istoj transakciji; nikad se odbacuje ili automatski naplaćuje drugoj porodici.
11. Cancel paid obligation čini payment allocation/credit application neefektivnim kroz tipiziranu system correction/reversal i stvara jednak `CANCELLED_OBLIGATION_CREDIT` za stvarno primljeni payment deo; već korišćen family credit se vraća jednakim `APPLICATION_REVERSAL`. Ne izvršava refund i ne duplira credit.
12. PaymentReversal mora poništiti allocation i neiskorišćen credit koji je taj payment stvorio. ACTIVE credit applications koje su potomci tog payment credit-a vraćaju se compensating application reversal-om i ponovo otvaraju ciljne obaveze. Ako je potomak već spolja refundiran ili ga nije moguće atomski vratiti bez negativnog available balance-a, reversal je blokiran i zahteva dokumentovanu recovery korekciju; nema negativnog skrivenog salda.
13. AllocationCorrection ponovo izračunava residual credit i upisuje samo compensating ledger entries; nikad UPDATE/DELETE starog ledger-a.
14. RefundReview ne zaključava novac dok nije REFUND_REQUIRED; tada mora postojati ACTIVE reservation. Spoljni refund bez dovoljne rezervacije je 409.
15. Direct ledger insert/update/delete van M12 command handler-a je zabranjen DB privilegijama/aplikacionom granicom.
16. `auto_apply_family_credit` default je false. Promena važi samo za buduće obligations; ne troši postojeći credit odmah.
17. Nema cross-currency conversion u H0.
18. M12 write/offline i konačan optimistic success su zabranjeni; UI koristi `PENDING_SERVER_CONFIRMATION` samo kao prolazni view status, nikad domain success.
19. Objavljene cene i obavezne naknade moraju biti vidljive pre upisa/registracije kroz dozvoljenu projekciju; nema skrivenog fee-ja dodatog tek pri plaćanju.
20. Porezi/fiskalizacija su adapter output; H0 iznos koji se duguje ne dobija naknadnu skrivenu platform fee stavku.
21. `CancelAssessmentObligations` je jedini skupni finansijski owner port za otkazivanje jednog immutable Assessment-a. U jednom commit-u zaključava Assessment, sve njegove FamilyBillingAccount redove stabilno po UUID-u i sve njegove Obligation redove stabilno po UUID-u; svaki non-CANCELLED red prelazi u CANCELLED uz postojeću allocation/credit reversal semantiku. Ili su svi redovi, ledger efekti, audit, outbox i receipt upisani, ili nije upisano ništa.
22. Pojedinačno otkazivanje naplative M16 registracije koristi neutralni M16+M12 coordinator. Coordinator prvo zaključava Event pa EventRegistration, zatim poziva M12 owner port u M12 lock redosledu i u istoj lokalnoj DB transakciji commit-uje M16 cancellation i sve M12 cancellation efekte. Frontend nikad ne radi dva odvojena write poziva.
23. `EventCancelledV1` je autoritativni signal za skupno otkazivanje svih `BillingAssessment.source_type=EVENT_REGISTRATION` redova čiji je `source_parent_id` taj Event. M12 consumer radi at-least-once sa M21 inbox/job receipt-om; za svaki Assessment koristi deterministički command identity `message_id:assessment_id` i može bezbedno nastaviti posle parcijalno obrađenog batch-a. Parcijalnost između assessment-a je operativno dozvoljena, ali nijedan pojedinačni assessment ne sme biti parcijalan.
24. Commit M16 Event cancellation-a je trenutna naplatna barijera, nezavisno od kašnjenja consumer-a. Svaki M12 read, reminder izbor, `GeneratePaymentInstruction` i komanda koja bi alocirala novac na event-backed obligation mora pre M12 lock-ova dobiti aktuelni M16 Event fact; za write neutralni coordinator zaključava sve referencirane Event redove stabilno po UUID-u pre M12 redova i ponavlja verzije pred commit. CANCELLED/unknown/unavailable fact failuje zatvoreno: nema nove instrukcije, reminder-a ili allocation-a. Verifikovana pristigla uplata može biti zabeležena samo na FamilyBillingAccount kao neraspoređen credit, nikad na otkazanu obavezu.
25. Otkazivanje obaveze nikada automatski ne šalje novac van sistema. Efektivno plaćeni deo postaje tačno jedan family credit po pravilima 11–14; eventualni spoljni refund prolazi zaseban `RefundReview` i `ConfirmExternalRefund` tok.
26. Svaki `CorrectFamilyCredit` zahteva svež step-up requester-a i odvojeno odobrenje drugog trenutno ovlašćenog account-a iz §2.12a; nema praga, self-approval-a, ponovne upotrebe ili odobrenja koje nadživljava payload/version promenu.

### 3.1. Edge cases

| # | Scenario | Ishod |
|---:|---|---|
| 1 | Generation day 31 u februaru. | Poslednji dan meseca u School zoni. |
| 2 | Cena se promeni posle preview-a. | Confirm 409 stale; ništa kreirano. |
| 3 | Dva confirm-a istog run-a. | Jedan commit, drugi isti receipt/already confirmed. |
| 4 | 50/50 na 100.01. | 50.01/50.00 po largest remainder + stable ID. |
| 5 | Split flag OFF, dva payer share-a. | 409/422, bez obligations. |
| 6 | Jedna uplata za dvoje dece iste porodice. | Dozvoljene višestruke allocation obaveze istog account-a/currency. |
| 7 | Dvoje dece su u različitim Family account-ima. | Jedan PaymentRecord ne može pokriti oba. |
| 8 | IPS QR skeniran, nema bank confirmation-a. | Obligation ostaje nepromenjen. |
| 9 | Bank reference odgovara dva account-a. | Candidate AMBIGUOUS; nema PaymentRecord. |
| 10 | Uplata 120.00, dug 100.00. | Allocation 100.00 + credit 20.00 atomski. |
| 11 | Paralelno trošenje poslednjih 20.00 credit-a. | Account lock dozvoli najviše ukupno 20.00. |
| 12 | Poništen payment čiji credit je već refundiran. | 409 PAYMENT_REVERSAL_BLOCKED; nema negativnog salda. |
| 13 | Paid obligation se canceluje. | Otvoreni dug ne postoji; iznos prelazi u credit, refund nije automatski. |
| 14 | Cross-tenant obligation UUID. | Safe 404. |
| 15 | Payer nije guardian. | Vidi samo svoje finansijske obligation-e; nema child profil. |
| 16 | Currency payment-a nije School/account currency. | 422; nema conversion-a. |
| 17 | Guardian otkaže naplativu registraciju, M12 korak padne. | I M16 registracija i M12 stanje ostaju nepromenjeni; 503, bez orphan cancellation-a. |
| 18 | Event je otkazan, a cancellation consumer kasni. | Finance read pokazuje `PENDING_MATERIALIZATION` i `remaining_collectible=0.00`; reminder/instruction/allocation su blokirani. |
| 19 | Event cancellation i payment allocation se trkaju. | Globalni Event→account→obligation lock redosled daje: ili allocation prethodi pa se zatim pretvara u credit, ili je allocation odbijen; nema izgubljenog ili dvostrukog novca. |
| 20 | `EventCancelledV1` isporučen deset puta ili worker padne na 51. assessment-u. | Inbox/command receipt ne duplira credit; završeni assessment-i ostaju završeni, retry nastavlja preostale. |
| 21 | Bank transfer stigne posle event cancellation-a. | Verifikovan PaymentRecord može nastati na tačnom account-u, ali nema allocation-a na cancelled event obligation; ceo raspoloživ iznos postaje credit. |
| 22 | Jedna event registracija ima split 50/50 obaveze. | Obe obaveze i svi odgovarajući compensating ledger efekti commit-uju zajedno ili nijedan. |

## 4. Tenant, security i privacy

Svaka komanda: M01 session → M03 school/version → M05 permission → M07 payer/guardian/admin subject basis → M12 resource/account guard → precommit authorization/version recheck. M07 PayerChildLink daje samo finansijski scope. Family, email, bank reference, Group ili Organization nisu auth dokaz.

Minimalni M05 ključevi:

| Permission | Svrha |
|---|---|
| `finance.view` | Dozvoljeni financial read; payer/guardian samo subject-scoped. |
| `finance.fee_rules.manage` | FeeRule/version publish/retire. |
| `finance.billing.preview` | Prepare preview bez side effect-a. |
| `finance.billing.confirm` | Confirm run/obligations; svež step-up je obavezan za svaki confirm. |
| `finance.obligations.manage` | One-time/cancel adjustment. |
| `finance.payments.record_cash` | Potvrda stvarno primljene gotovine. |
| `finance.payments.record_bank` | Reconciliation/manual bank confirmation. |
| `finance.payment_allocations.correct` | AllocationCorrection. |
| `finance.payments.reverse` | PaymentReversal; step-up+reason. |
| `finance.credit.apply` | Manual credit primena. |
| `finance.credit.correct` | Manual ledger correction; svež step-up i drugi različit ovlašćeni approver obavezni su za svaku korekciju. |
| `finance.refund_reviews.decide` | Odluka/refund reservation. |
| `finance.refunds.confirm_external` | Potvrda stvarnog spoljnog refund-a; step-up. |
| `finance.financial_profile.manage` | Bank profile/ključevi; step-up. |

Owner/Manager dobijaju policy-defined admin skup; LimitedAdmin samo eksplicitne grantove. Instructor nema finance. GUARDIAN odnos sam ne daje finance pravo; isti account mora imati zaseban PAYER assignment/ACTIVE payer basis ili school admin ulogu. Payer dobija samo obligations/credit/refund neutralnu projekciju povezanu sa svojim ACTIVE payer link-om. Payer ne vidi ime/kontakt drugog payer-a, procenat/obavezu drugog Family account-a niti druge child podatke. Standardni Support Access i break-glass nikad ne otvaraju payment, allocation, ledger, refund ili bank profile podatke/komande, čak ni ako requested scope to navede.

Cross-tenant/skriven subject vraća 404. Aggregate count/export/filter/cache primenjuje tenant+subject pre rezultata. Bank account/reference, refund reference i raw provider payload su envelope-encrypted; fingerprint je keyed HMAC, ne plain hash. Nikad se ne loguju/eventuju. Event/audit koristi opaque ID, exact amount+currency samo u strogo zaštićenom audit store-u; observability metrike nemaju amount, reference, ime ili child ID.

## 5. Lifecycle & transitions

| Entitet | From | Komanda | To |
|---|---|---|---|
| FinancialProfile | —/DRAFT | Create/Activate | DRAFT/ACTIVE |
| FinancialProfile | ACTIVE | Rotate/Revoke | stari REVOKED, novi ACTIVE / REVOKED |
| FeeRule | — | Create | DRAFT |
| FeeRule | DRAFT | PublishVersion/Activate | ACTIVE |
| FeeRule | ACTIVE | PublishNewVersion | ACTIVE, immutable nova verzija |
| FeeRule | DRAFT/ACTIVE | Retire | RETIRED terminalno za nove assessment-e |
| BillingRun | — | Prepare | PREVIEW |
| BillingRun | PREVIEW | Confirm | CONFIRMED |
| BillingRun | PREVIEW | Cancel | CANCELLED |
| BillingRun | PREVIEW | unrecoverable calculate failure | FAILED |
| Obligation | — | Confirm assessment | UNPAID |
| Obligation | UNPAID | partial/full allocation | PARTIALLY_PAID/PAID |
| Obligation | PARTIALLY_PAID | allocation/reversal | UNPAID/PARTIALLY_PAID/PAID |
| Obligation | UNPAID/PARTIALLY_PAID/PAID | Cancel | CANCELLED + credit za efektivno pokriveno |
| PaymentRecord | — | Record/Post candidate | CONFIRMED |
| PaymentRecord | CONFIRMED | ReversePayment | REVERSED terminalno |
| RefundReview | — | Open | OPEN |
| RefundReview | OPEN | DecideNoRefund | REFUND_NOT_REQUIRED |
| RefundReview | OPEN | DecideRefundRequired | REFUND_REQUIRED + reservation |
| RefundReview | REFUND_REQUIRED | CorrectDecisionNoRefund | REFUND_NOT_REQUIRED + release |
| RefundReview | REFUND_REQUIRED | ConfirmExternalRefund | REFUNDED_EXTERNALLY + debit/consume |
| CreditReservation | — | refund required | ACTIVE |
| CreditReservation | ACTIVE | no-refund correction | RELEASED |
| CreditReservation | ACTIVE | external refund | CONSUMED |
| FinancialDualControlApproval | — | RequestFamilyCreditCorrectionApproval | PENDING |
| FinancialDualControlApproval | PENDING | ApproveFamilyCreditCorrection | APPROVED |
| FinancialDualControlApproval | PENDING/APPROVED | revoke ili read-time expiry | REVOKED/EXPIRED |
| FinancialDualControlApproval | APPROVED | CorrectFamilyCredit isti hash/version | CONSUMED |

`FeeRuleVersion`, `BillingAssessment`, `PaymentAllocation`, correction/reversal i ledger entry su append-only/immutable; stanje se menja novim zapisom.

## 6. Error catalog

| Kod | HTTP | Opis |
|---|---:|---|
| `M12_VALIDATION_FAILED` | 422 | Field/decimal/currency/period nije validan. |
| `M12_NOT_FOUND_SAFE` | 404 | Resurs/subject nije vidljiv. |
| `M12_PERMISSION_DENIED` | 403 | Akcija na poznatom resursu nije dozvoljena. |
| `M12_VERSION_CONFLICT` | 409 | CAS konflikt. |
| `M12_CURRENCY_MISMATCH` | 422 | Različite valute. |
| `M12_FEE_VERSION_OVERLAP` | 409 | Effective period se preklapa. |
| `M12_RESPONSIBILITY_INCOMPLETE` | 409 | Share zbir nije 10000 ili nema validnog payer/account-a. |
| `M12_SPLIT_BILLING_DISABLED` | 409 | Više share-a dok je flag OFF. |
| `M12_BILLING_RUN_STALE_PREVIEW` | 409 | Input hash se promenio. |
| `M12_BILLING_ALREADY_CONFIRMED` | 409 | Različit zahtev za već potvrđen scope. |
| `M12_SOURCE_CANCELLED` | 409 | Autoritativni source je otkazan; nova instrukcija, reminder ili allocation nisu dozvoljeni. |
| `M12_SOURCE_CANCELLATION_INCOMPLETE` | 503 | Ne može se dokazati kompletna cancellation materijalizacija jednog Assessment-a; nema parcijalnog commit-a tog Assessment-a. |
| `M12_ALLOCATION_EXCEEDS_PAYMENT` | 409 | Efektivne alokacije > payment. |
| `M12_ALLOCATION_EXCEEDS_OBLIGATION` | 409 | Efektivne alokacije > dug. |
| `M12_ALLOCATION_SCOPE_MISMATCH` | 422 | Druga škola/account/currency. |
| `M12_PAYMENT_DUPLICATE` | 409 | Isti attempt/external transaction. |
| `M12_PAYMENT_NOT_CONFIRMED` | 409 | Instrukcija/kandidat nije dokaz primljene uplate. |
| `M12_PAYMENT_MATCH_AMBIGUOUS` | 409 | Više mogućih account-a. |
| `M12_PAYMENT_METHOD_DISABLED` | 409 | Provider/payment rail nije aktiviran za školu. |
| `M12_ACCOUNT_NOT_ACTIVE` | 409 | FamilyBillingAccount je FROZEN/CLOSED za traženu radnju. |
| `M12_PAYMENT_REVERSAL_BLOCKED` | 409 | Descendant credit/refund ne može bezbedno da se odmota. |
| `M12_CREDIT_INSUFFICIENT` | 409 | Available credit nije dovoljan. |
| `M12_REFUND_RESERVATION_REQUIRED` | 409 | Nema dovoljne aktivne rezervacije. |
| `M12_TRANSITION_NOT_ALLOWED` | 409 | Lifecycle greška. |
| `M12_IDEMPOTENCY_KEY_REUSED` | 409 | Isti key, drugi payload/scope. |
| `M12_PRECONDITION_REQUIRED` | 428 | Nedostaje expected version/hash. |
| `M12_STEP_UP_REQUIRED` | 401 | Rizična akcija traži svežu potvrdu. |
| `M12_DUAL_CONTROL_REQUIRED` | 409 | Nema važećeg, različitim actorom odobrenog i nepotrošenog approval-a za tačan correction hash/version. |
| `M12_DEPENDENCY_UNAVAILABLE` | 503 | Autoritativni M07/M08/M09/M16/adapter port nije dostupan. |
| `M12_RATE_LIMITED` | 429 | Tenant/actor limit. |

## 7. API, idempotency, concurrency i NFR

Komande: `Create/Activate/RotateFinancialProfile`, `CreateFeeRule`, `PublishFeeRuleVersion`, `RetireFeeRule`, `SetBillingPolicy`, `SetBillingResponsibilities`, `PrepareBillingRun`, `ConfirmBillingRun`, `CreateOneTimeAssessment`, `CancelObligation`, `CancelAssessmentObligations`, `ConsumeEventCancelled`, `GeneratePaymentInstruction`, `IngestReconciliationCandidate`, `ResolvePaymentMatch`, `RecordPayment`, `CorrectPaymentAllocation`, `ReversePayment`, `ApplyFamilyCredit`, `RequestFamilyCreditCorrectionApproval`, `ApproveFamilyCreditCorrection`, `RevokeFamilyCreditCorrectionApproval`, `CorrectFamilyCredit`, `Open/Decide/CorrectRefundReview`, `ConfirmExternalRefund`.

### 7.1. Command ugovori

| Komanda | Obavezni poslovni ulaz | Atomski rezultat |
|---|---|---|
| `PublishFeeRuleVersion` | rule/version, amount string, currency, effective range, proration, expected rule version | Immutable version + rule current pointer + audit/outbox/receipt. |
| `SetBillingResponsibilities` | participant, scope, 1–4 account/payer/share reda, effective range, expected current set hash | Kompletna nova važeća responsibility revizija; nikad partial share set. |
| `PrepareBillingRun` | billing_period, normalizovani scope items, due date/policy version | PREVIEW/hash/counts; nula assessment/obligation. |
| `ConfirmBillingRun` | run ID/version, expected preview hash, fresh step-up proof | CONFIRMED + svi Assessment/Obligation/credit application redovi ili ništa; step-up važi za svaki batch. |
| `CreateOneTimeAssessment` | source type/id, participant, fee version ili eksplicitni MANUAL_ADJUSTMENT+reason, due date | Assessment + responsibility-split obligations; nulti iznos bez obligation-a. |
| `CancelObligation` | obligation/version, reason | CANCELLED + allocation correction + equal credit za efektivno pokriveno. |
| `CancelAssessmentObligations` | assessment ID, expected immutable calculation hash, source cancellation type/ref/version, zatvoreni reason | Svi non-CANCELLED obligations tog Assessment-a CANCELLED + tačni compensating allocation/application/credit redovi + audit/outbox/receipt u jednom commit-u; identičan retry vraća isti rezultat. |
| `ConsumeEventCancelled` | verifikovani `EventCancelledV1` message ID/schema, school/event ID i event version | Pronalaženje samo M12 assessment-a preko `(school_id,EVENT_REGISTRATION,source_parent_id)`; idempotentno cancellation izvršenje po assessment-u; completion tek kada su svi redovi obuhvaćeni. |
| `GeneratePaymentInstruction` | account, optional obligation, exact amount/currency, method | ACTIVE instruction; nijedan PaymentRecord/status change. |
| `IngestReconciliationCandidate` | provider key, external fingerprint, exact amount/currency/time, encrypted reference | Unique candidate + deterministic match status; nema money post-a. |
| `ResolvePaymentMatch` | candidate/version, one account, allocation targets | Candidate POSTED + jedan PaymentRecord + allocation/credit. |
| `RecordPayment` | account, payer optional, CASH/BANK, amount/currency/time, allocation targets, attempt ID | Payment + valid allocations + residual credit. |
| `CorrectPaymentAllocation` | payment/version, replacement allocations, reason | Correction + old reversals + new allocations + compensating credit entries. |
| `ReversePayment` | payment/version, reason | PaymentReversal + status/allocations/credit causal unwind ili potpuni 409. |
| `ApplyFamilyCredit` | account/version, obligation/version, amount | Negative ledger + ACTIVE FamilyCreditApplication + obligation recompute; available nikad negativan. |
| `RequestFamilyCreditCorrectionApproval` | account/version, signed amount, currency, zatvoren reason, fresh step-up | PENDING approval vezan za canonical correction hash i requester-a, rok 15 minuta. |
| `ApproveFamilyCreditCorrection` | approval/version, fresh step-up | APPROVED samo od drugog trenutno ovlašćenog account-a; payload se ne menja. |
| `RevokeFamilyCreditCorrectionApproval` | approval/version, reason | PENDING/APPROVED→REVOKED; nema ledger efekta. |
| `CorrectFamilyCredit` | account/version, signed amount, reason, approval ID/version, fresh requester step-up | Append-only MANUAL_CORRECTION + APPROVED→CONSUMED + audit/outbox/receipt u jednom commit-u; nema balance UPDATE-a. |
| `OpenRefundReview` | account, source, requested amount, reason | OPEN review; bez rezervacije/refund-a. |
| `DecideRefundReview` | review/version, required/not-required, reason | Status; REQUIRED atomski ACTIVE reservation. |
| `CorrectRefundReview` | review/version, no-refund reason | REFUND_NOT_REQUIRED + reservation RELEASED. |
| `ConfirmExternalRefund` | review/version, method, encrypted reference, actual amount, step-up | REFUNDED_EXTERNALLY + ledger debit + reservation CONSUMED. |

### 7.2. Query ugovori

`ListFeeRules`, `GetBillingPreview`, `List/GetObligations`, `List/GetPayments`, `GetFamilyCreditBalanceAndHistory`, `List/GetRefundReviews`, `GetFinancialProfileMasked` uvek primenjuju school+subject pre count/page. Payer projekcija vraća samo sopstveni account, svoj payable iznos/status/due date, neutralan payment/credit/refund status i dozvoljenu payment instruction; ne vraća druge share-ove, druge payer-e, interne correction/reason/actor podatke ili bank ciphertext. Za event-backed obligation projekcija pre iznosa/current action-a proverava M16 Event fact i primenjuje `source_cancellation_state`; otkazani source nikad nije collectible dok worker kasni. School admin detalj zahteva odgovarajući permission. Cursor page je default 25/max 100; sync range max 366 dana.

M12 ne poseduje bulk/report export komandu, export job, fajl ni download ticket. Finansijski export pripada isključivo M18: M18 čita verzionisani, tenant-safe M12 report source port nakon sopstvenih M01/M03/M05 guardova, snapshot/barrier provere i `school.reports.finance.view` + `school.reports.export` dozvola. M12 ne poziva M18 i ne zna format fajla; vraća samo autorizovane exact-decimal činjenice za jedan `school_id`, valutu i knowledge/effective presek. Svaka direktna ruta koja se predstavlja kao M12 bulk export mora biti odsutna ili odbijena kao nepoznata ruta; nema drugog export pipeline-a.

Svaka write komanda ima active school, Idempotency-Key, correlation_id; mutacije expected version/hash. Hash je canonical payload+school+actor+command. Receipt se čuva najmanje 7 godina za finansijske komande ili duže prema aktivnoj retention/legal-hold politici; raw key se ne čuva. Retry vraća isti response; drugi payload 409.

Lock order: za event-backed write neutralni coordinator prvo zaključava M16 Event redove sortirano, pa M16 EventRegistration redove sortirano; zatim M12 redosled School billing period → BillingRun → FamilyBillingAccount sortirano → PaymentRecord → Obligation sortirano → CreditReservation/Ledger causal chain. Za write bez event source-a počinje M12 redosledom. Nijedan M12 handler ne drži account/obligation lock pa sinhrono poziva M16; potrebni Event fact/lock dobija se pre M12 lock-ova. Spoljni provider poziv nije unutar dugog DB lock-a: koristi provider idempotency + pending adapter operation/outbox, a M12 finansijski success tek posle verifikovanog callback/poll rezultata. H0 external refund je ručna potvrda stvarnog spoljnog izvršenja, ne poziv provideru.

Batch preview/confirm maksimum 10.000 assessment kandidata po run-u. Veći tenant se unapred deli na javno vidljive, nepreklapajuće run scope-ove stabilno po source ID opsegu; svaki run je all-or-nothing i dashboard prikazuje status svih delova, nikad lažni „cela škola potvrđena“ dok neki deo nije CONFIRMED. Assessment unique ključ sprečava dupli source u preklopljenim run-ovima. M12 operativne liste imaju cursor default 25/max 100 i date range najviše 366 dana. Period do pet godina, limit 100.000 redova, šifrovanje, TTL, generisanje i download finansijskog report export-a određuje i izvršava samo M18; M12 source port ne zaobilazi M18 limite niti vraća fajl.

Minimalni indeksi: active fee scope/effective dates; confirmed run school/period; assessment unique source/period; event cancellation lookup `(school_id,source_type,source_parent_id,id)`; obligation account/status/due_date; payment account/received_at i unique fingerprints; allocation payment/obligation; ledger account/created_at/id; refund account/status. p95 list ≤350ms, single payment+≤20 allocations ≤800ms bez adapter outage-a; billing 10k i event cancellation batch mere se kao job SLO, ne HTTP request. Event cancellation batch page je najviše 500 assessment ID-eva i nema OFFSET skeniranje. Query plans, deadlock/parallel money tests i decimal property tests su DoD.

Outbox: `BillingRunConfirmedV1`, `ObligationCreatedV1`, `ObligationCancelledV1`, `EventBillingCancellationCompletedV1`, `PaymentRecordedV1`, `PaymentReversedV1`, `FamilyCreditChangedV1`, `RefundReviewStatusChangedV1`. Minimalno school, opaque IDs, status/version/currency; `EventBillingCancellationCompletedV1` nosi samo event ID/version, processed assessment count i completion status, bez participant/account/amount podataka. Amount se šalje samo ako konkretan consumer ugovor zahteva i payload je access-controlled—M14 notification event ne dobija amount/child name u push payload-u.

## 8. Acceptance sažetak

M12 je prihvatljiv samo uz `02-M12-QA-I-TRACEABILITY.md`: exact-decimal property test, stale preview/all-or-nothing, two-tenant/payer privacy, split largest-remainder, dve paralelne alokacije/credit primene, bank dedupe, IPS no-auto-paid, multi-child samo isti account, tri strogo odvojene korekcije, credit/reversal/refund causal chain, event/registration cancellation atomicity i barrier/race/retry testove, kao i negativnu pretragu `amount_minor`, `price_minor`, binary float i M09/M16 price polja u aktivnom ugovoru.
