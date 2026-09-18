---
tip: modulni-implementacioni-ugovor
modul-id: M14
naziv: Sistemske notifikacije i pažnja
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-15
schema-zavisnosti: [M01, M04]
consumes-events-from: [M05, M10, M12, M13, M16]
read-portovi: [M06, M07, M09, M13]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M17, M18, M19, M21, M28]
offline-policy: DENY
---

# M14 — Sistemske notifikacije i pažnja

## 1. Cilj, autoritet i granice

M14 asinhrono konzumira odobrene, PII-minimizovane domain događaje i materijalizuje lične `SystemNotification`, staff-only `AttentionItem` i sopstvenu `NotificationDelivery`. M14 je jedini vlasnik tih zapisa.

Izvorni modul u svojoj poslovnoj transakciji upisuje outbox; nikada ne poziva M14 command/query/adapter i ne čeka isporuku. M14 ne odlučuje da li je izvorna radnja uspela, ne menja source aggregate, ne poseduje ručnu komunikaciju/M13 delivery i ne proizvodi notifikaciju iz attendance statusa. H0 kanali su IN_APP i EMAIL; web push je feature-flagged OFF, bez osetljivog payload-a. SMS/Viber/WhatsApp nisu H0.

## 2. Entiteti i polja

Tipovni ugovor: svi `id`, `*_id`, event/actor/resource reference su UUID; svi `*_at` su UTC `TIMESTAMPTZ`; `version` je `BIGINT >= 1`; hash je lowercase `CHAR(64)`; zatvoreni kodovi su `varchar(96)` + DB `CHECK`/registry FK; JSON je ograničeni `JSONB` validiran versioned schemom. Polje je obavezno osim kada eksplicitno piše nullable. Svaki tenant FK je kompozitan. Aggregate/command red sa surrogate `id` ima `UNIQUE(school_id,id)`; keyed receipt/projection bez surrogate ID-a ima eksplicitni kompozitni PK/UNIQUE koji počinje sa `school_id` kada je SCHOOL scope i nikad tenant-less lookup.

`ConsumedDomainEvent`: `consumer_id=M14`, `event_id`, `event_version`, `source_module`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `event_type`, `payload_schema_version`, `payload_hash`, `consumed_at`, `outcome` (`MATERIALIZED`,`IGNORED_BY_POLICY`,`FAILED_TERMINAL`); PK `(consumer_id,event_id,event_version)`. `school_id` je non-null iff SCHOOL i null iff PLATFORM. M14 H0 user notification mapping ispod prihvata samo SCHOOL događaje; PLATFORM incident ide u M21 operacije, ne u izmišljeni school.

`NotificationPolicyRevision`: `id`, `revision_no`, `status` (`DRAFT`,`ACTIVE`,`RETIRED`), `effective_at nullable`, `content_hash`, `created_at`, `activated_at nullable`, `activated_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`. DRAFT ima sva lifecycle polja null; ACTIVE zahteva effective/activation actor-time par i null retire par; RETIRED zadržava activation par i zahteva retire actor-time par. `effective_at<=database_now` pri aktivaciji. Immutable posle ACTIVE; partial unique dozvoljava tačno jednu ACTIVE reviziju. Policy mapira zatvoren `event_type` na notification/attention tip, recipient resolver, channel i suppression pravilo.

`SystemNotification`: `id`, `school_id`, `recipient_account_id`, `notification_type`, `source_event_id`, `source_event_version`, `related_entity_type`, `related_entity_id`, `message_key`, `message_params_json`, `deep_link_route_key`, `deep_link_params_json`, `status` (`UNREAD`,`READ`), `read_at nullable`, `policy_revision_no`, `created_at`, `expires_at` nullable, `version`. `read_at` je null iff UNREAD i non-null iff READ. JSON sadrži opaque ID/code/date, nikad ime deteta, amount, email, body ili free text. Unique `(school_id,recipient_account_id,source_event_id,source_event_version,notification_type)`.

`AttentionItem`: `id`, `school_id`, `item_type`, `source_event_id`, `source_event_version`, `related_entity_type/id`, `source_generation_key varchar(160)`, `assigned_scope_type` (`OWNER_MANAGER`,`FINANCE_STAFF`,`SCHEDULE_STAFF`,`SYSTEM_OPERATIONS`), `status` (`OPEN`,`RESOLVED`,`DISMISSED`), `resolution_code nullable`, `resolved_by_account_id nullable`, `created_at`, `due_at`, `resolved_at nullable`, `version`. `source_generation_key` je PII-free kanonski ključ iz policy mapping-a i source business generacije, na primer `EVENT_VERSION:<event_id>:<version>`; nije slobodan tekst. Sva tri resolution polja su null iff OPEN i non-null za RESOLVED/DISMISSED. Unique `(school_id,item_type,related_entity_type,related_entity_id,source_generation_key)` važi kroz sve statuse: retry iste generacije ne može ponovo otvoriti već rešen/dismissed item, dok nova legitimna generacija dobija drugi ključ.

`NotificationDelivery`: `id`, `school_id`, `notification_id`, `recipient_account_id`, `channel IN_APP|EMAIL|WEB_PUSH`, `status QUEUED|DISPATCHED|RETRY_SCHEDULED|DELIVERED|PERMANENTLY_FAILED|SUPPRESSED`, `provider_message_ref nullable` opaque, `attempt_count`, `next_attempt_at nullable`, `last_error_class nullable`, `created_at`, `updated_at`, `version`; unique `(school_id,notification_id,channel)`. `WEB_PUSH` red se ne kreira dok flag nije ON. `next_attempt_at` je non-null samo za QUEUED/RETRY_SCHEDULED; terminalni statusi ga imaju null. Email/contact se resolve-uje just-in-time i ne čuva u delivery-ju.

`NotificationFanoutPlan`: `id`, `school_id`, `source_event_id`, `source_event_version`, `policy_revision_id`, `recipient_snapshot_barrier nullable`, `recipient_set_hash nullable`, `recipient_count nullable UInt32`, `segment_size UInt16` (1..500), `status PLANNING|READY|RUNNING|COMPLETED|FAILED`, `materialized_count UInt32` default 0, `suppressed_count UInt32` default 0, `failure_code nullable`, `started_at nullable`, `completed_at nullable`, `version`, `created_at`, `updated_at`; unique `(school_id,source_event_id,source_event_version,policy_revision_id)`. PLANNING nema barrier/hash/count/runtime rezultat; READY zahteva barrier/hash/count; RUNNING dodatno zahteva started time; COMPLETED zahteva completed time, null failure i `materialized_count+suppressed_count=recipient_count`; FAILED zahteva completed time+safe failure code.

`NotificationFanoutSegment`: `id`, `school_id`, `fanout_plan_id`, `sequence_no UInt32`, `keyset_start_after nullable UUID`, `keyset_end_at nullable UUID`, `segment_input_hash`, `status PENDING|LEASED|SUCCEEDED|FAILED_RETRYABLE|FAILED_TERMINAL`, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token UInt64`, `attempt_count UInt16`, `materialized_count UInt32`, `suppressed_count UInt32`, `last_error_code nullable`, `completed_at nullable`, `version`, `created_at`, `updated_at`; unique `(school_id,fanout_plan_id,sequence_no)` i non-overlapping uređeni keyset intervali. Segment ne čuva ime, kontakt ni recipient listu; svaki primalac se ponovo autorizuje pri materialization-u. LEASED jedini ima lease; SUCCEEDED zahteva completion i zbir jednak stvarno pregledanom segmentu; neuspešni statusi zahtevaju safe error, a samo terminalni failure ima completion. Stale fencing token ne može commit-ovati delivery ili checkpoint.

## 3. Pravila i invarijante

Zatvoren H0 event registar:

| Source event | Ishod |
|---|---|
| `RoleAssignmentChangedV1`, `SupportAccessChangedV1` | affected adult security notification; nikad child data |
| `OccurrenceRescheduledV1`, `OccurrenceCancelledV1` | guardian/staff notification preko current authorized resolvera |
| `ObligationCreatedV1`, `ObligationCancelledV1`, `PaymentRecordedV1`, `PaymentReversedV1` | finance subject recipient; params bez amount-a |
| `EventPublishedV1`, `EventMateriallyChangedV1`, `EventCancelledV1`, `EventRegistrationChangedV1` | authorized guardian/staff/event participant recipient |
| `CommunicationDraftExpiryWarningRequestedV1` | isključivo current author account; neutralna draft-expiry poruka bez subject/body/audience podatka |

Attendance create/correct/lock, `AttendanceRecord.status` i M11 sync događaji su apsolutno `IGNORED_BY_POLICY` i ne smeju imati registry mapping.

1. Consumer proverava schema/version/signature/hash, dozvoljeni source+event par, scope/School i active policy. Registrovan validan događaj bez M14 policy mapping-a je `IGNORED_BY_POLICY`; neregistrovan source/type par, unsupported schema ili nevalidan envelope je `FAILED_TERMINAL`/quarantine bez nagađanja primaoca.
2. Recipient se razrešava iz current M06/M07/M09 facts. Event payload ne nosi email/ime; source može nositi samo opaque affected IDs potrebne ugovoru.
3. Jedan event može dati više notification-a, ali dedupe unique sprečava duplikat pri at-least-once delivery-ju.
4. Source business commit je nezavisan od M14 outage-a. Retry ne menja source.
5. Korisnik pri list/read prolazi current tenant/permission/subject guard. Stari snapshot ne održava pristup posle revoke-a.
6. Notification tekst nastaje server-side iz versioned `message_key` + minimizovanih parametara; source/free text se ne renderuje.
7. Deep link je route key + opaque params, nikad proizvoljan URL; odredišna ruta ponovo autorizuje resource.
8. MarkRead je idempotentan; read ne znači da je email isporučen i obrnuto.
9. AttentionItem ne ide guardian-u/PAYER-u; resolution ne menja source aggregate.
10. PWA push, kada kasnije uključen, payload ima samo generic type, opaque notification ID i tenant-neutral app route; bez PII/amount-a.
11. Sve write operacije korisnika su online-only. Service worker sme cache-ovati samo generički shell, ne notification body/list.

### 3.1. Edge cases

| # | Slučaj | Rezultat |
|---:|---|---|
| 1 | Isti outbox event isporučen 20 puta | Jedan consumed triplet i najviše jedan notification po recipient/type. |
| 2 | Guardian opozvan pre consume-a | Ne dobija notification. |
| 3 | Guardian opozvan posle materialization-a | Sledeći read safe 404; nema pristupa preko deep linka. |
| 4 | Unknown schema version | Quarantine/terminal operational attention; nema korisničke poruke. |
| 5 | M14 nedostupan 6h | Source radi; backlog se tenant-fair obrađuje bez duplikata. |
| 6 | Event A payload sadrži school B entity | Fail closed + security signal; bez materialization-a. |
| 7 | Dva workera konzumiraju isti event | PK/fencing dozvoljava jedan rezultat. |
| 8 | Financial event sadrži amount greškom | Schema/privacy validator odbija i redaktuje log. |
| 9 | Draft expiry warning stigne posle edit-a koji je resetovao rok | M13 version/eligibility ref više ne važi; M14 ne materijalizuje stale warning. |

## 4. Tenant i Security Guard

Consumer ne veruje samo event `school_id`: svaki related ID se potvrđuje autoritativnim tenant-safe portom. Interaktivni request: M01→M03→M05→recipient/attention subject guard; hidden/cross-tenant target safe 404. Permission ključevi: `school.notifications.view_own`, `school.notifications.mark_read_own`, `school.attention.view`, `school.attention.resolve`, `school.notification_delivery.view`; aktivacija globalne policy revizije zahteva `platform.notification.policy.publish`, PLATFORM_SECURITY_ADMIN, step-up i audit. Guardian/Payer samo sopstvene, business-subject dozvoljene notification-e; finance notification PAYER-u ne daje document/child profile. Staff attention prema eksplicitnoj ulozi/scope-u. Support vidi samo delivery health agregat bez recipient/message params; nema impersonation čitanja.

Audit: policy activate, attention resolve/dismiss i security quarantine. Obično materialization/mark-read ide u operativni receipt/telemetry, ne visokoobimni PII audit. Logovi: source module/event type/schema/outcome/latency/school hash; nikad payload JSON, recipient ID, message params ili provider raw response.

## 5. Lifecycle

| Entitet | Iz | Akcija | U |
|---|---|---|---|
| Policy | DRAFT | Activate | ACTIVE |
| Policy | ACTIVE | Activate successor | RETIRED |
| Notification | — | Consume mapped event | UNREAD |
| Notification | UNREAD | MarkRead | READ |
| Notification | READ | MarkRead retry | READ |
| Attention | — | Consume mapped event | OPEN |
| Attention | OPEN | Resolve/ dismiss | RESOLVED/DISMISSED |
| FanoutPlan | — | Create for large recipient set | PLANNING |
| FanoutPlan | PLANNING | Freeze authorized barrier/hash | READY |
| FanoutPlan | READY | Start first segment | RUNNING |
| FanoutPlan | RUNNING | All segments terminal-success | COMPLETED |
| FanoutPlan | PLANNING/READY/RUNNING | Terminal planning/worker failure | FAILED |
| Delivery | — | Materialize authorized recipient/channel | QUEUED |
| Delivery | QUEUED/RETRY_SCHEDULED | Provider accepts dispatch | DISPATCHED |
| Delivery | DISPATCHED | Verified provider delivery | DELIVERED |
| Delivery | QUEUED/DISPATCHED | Allow-listed transient failure | RETRY_SCHEDULED |
| Delivery | QUEUED/DISPATCHED/RETRY_SCHEDULED | Permanent failure ili max 8/48h | PERMANENTLY_FAILED |
| Delivery | QUEUED/RETRY_SCHEDULED | Policy/recipient suppression pre send-a | SUPPRESSED |

READ/RESOLVED/DISMISSED, COMPLETED/FAILED fanout plana i DELIVERED/PERMANENTLY_FAILED/SUPPRESSED delivery-ja su terminalni u redovnom toku. Delivery `provider_message_ref` je obavezan od DISPATCHED nadalje za spoljni kanal, a zabranjen za IN_APP; `last_error_class` postoji samo kada je poslednji pokušaj neuspešan ili je SUPPRESSED sa zatvorenim razlogom. M13 i M14 entiteti nisu deljeni.

## 6. Error katalog

| Kod | HTTP | Značenje |
|---|---:|---|
| `M14_NOT_FOUND_SAFE` | 404 | Skriven/cross-tenant/nepostojeći zapis. |
| `M14_PERMISSION_DENIED` | 403 | Nedozvoljena poznata akcija. |
| `M14_STALE_VERSION` | 409 | CAS. |
| `M14_IDEMPOTENCY_KEY_REUSED` | 409 | Isti key, drugi payload. |
| `M14_INVALID_EVENT_SCHEMA` | 422 | Nepodržan event/schema. |
| `M14_EVENT_TENANT_MISMATCH` | 422 | Source/related tenant mismatch. |
| `M14_INVALID_TRANSITION` | 409 | Lifecycle. |
| `M14_RATE_LIMITED` | 429 | Interactive limit. |
| `M14_DEPENDENCY_UNAVAILABLE` | 503 | Resolver nedostupan; retry, bez guess-a. |

## 7. API, idempotency, concurrency i NFR

Nema javnog `EmitNotification` API-ja. Ingress je `ConsumeDomainEvent(envelope)`. Interaktivno: `ListMyNotifications`, `MarkNotificationRead`, `ListAttentionItems`, `ResolveAttentionItem`, `DismissAttentionItem`. Svaki write ima idempotency/correlation/expected version gde važi. Consumer dedupe triplet se commit-uje zajedno sa notification/attention/delivery redovima; failure pre commit-a se retry-uje.

| API ugovor | Obavezni poslovni input | Uspešan rezultat |
|---|---|---|
| `ConsumeDomainEvent` | signed/versioned envelope, event/schema IDs, school, opaque refs | MATERIALIZED/IGNORED_BY_POLICY/FAILED_TERMINAL receipt |
| `ListMyNotifications` | cursor, status/type filter | samo trenutni account+subject opseg |
| `MarkNotificationRead` | notification ID/version | READ sa stabilnim `read_at` |
| `ListAttentionItems` | cursor, assigned scope/status | staff-scoped minimalna projekcija |
| `ResolveAttentionItem` | item ID/version, resolution code | RESOLVED/version |
| `DismissAttentionItem` | item ID/version, reason code | DISMISSED/version |
| `ListNotificationDeliveryHealth` | agregacioni filter | maskirani counts; bez recipienta/params |
| `ActivatePolicyRevision` | PLATFORM_SECURITY_ADMIN, `platform.notification.policy.publish`, DRAFT revision/version, step-up, reason | tačno jedna ACTIVE revision |

Worker lease+fencing+`SKIP LOCKED`; tenant-fair batching; max batch500; poison event posle 10 pokušaja ide u quarantine bez PII. List cursor default30/max100. Cilj: p95 list≤300ms, consume DB materialization≤500ms za ≤100 recipienta; fanout >100 se segmentira idempotentno preko `NotificationFanoutPlan/Segment`, a partial segment nikad ne proizvodi duplikat. Plan je vezan za jedan authorization/recipient barrier, ali svaki recipient prolazi current subject recheck pri materialization-u; revoke pre tog commit-a daje SUPPRESSED, a revoke posle materialization-a i dalje blokira list/read/deep-link pristup.

Obavezni indeksi: notification inbox `(school_id,recipient_account_id,status,created_at,id)`; attention `(school_id,assigned_scope_type,status,due_at,id)`; consumed-event PK; active-policy unique partial za jednu ACTIVE reviziju; delivery worker partial `(status,next_attempt_at,id)`; quarantine `(outcome,consumed_at,id)`. Payload/params nisu indeksirani niti full-text pretraživi.

## 8. Acceptance kriterijumi

M14 prolazi samo uz QA matricu: at-least-once dedupe, no direct source/M13 calls, M13 draft-warning event, attendance absolute deny, current subject revoke, schema quarantine, payload privacy, conditional-null constraints, deep-link reauth, delivery fencing, two-tenant negative tests, backlog fairness, offline deny i audit/log redaction.
