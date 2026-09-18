---
modul-id: M21
tip: normativni-job-katalog
status: SPEC_CANDIDATE
katalog-verzija: 1
datum: 2026-09-16
broj-job-definicija: 40
---

# M21 — runtime job katalog v1

## 1. Zajednički izvršni ugovor

Samo niže navedeni English ASCII `job_key` može imati published definiciju u ovom obuhvatu. H0 ključevi mogu imati `enabled_default=true` samo kada je njihov owner capability efektivan; M28 ključ `portal.pilot_enrollment_expiry` ima `enabled_default=false` sve dok M28 feature nije omogućen za najmanje jednu pilot školu. Svaki trigger pravi ili pronalazi tačno jedan `JobExecution` po navedenom semantic key-u. Vreme u bazi je UTC; `local_date` i lokalni raspored računaju se iz aktuelne IANA zone škole i verzije owner policy-ja sačuvane u semantic key-u.

Za local schedule koji padne u nepostojeće DST vreme koristi se prvi validan instant posle gap-a. Za duplirano lokalno vreme koristi se raniji offset. Semantic key sadrži `school_id:local_date:local_schedule_key:policy_version`, pa se izvršava tačno jednom bez obzira na dva UTC kandidata. Event job semantic key uvek uključuje originalni `message_id`; aggregate verzija je dodatni stale guard, ne zamena za message dedupe.

Retry profili:

| Profil | Max attempts | Backoff posle neuspeha | Retryable allow-list | Terminalno bez retry-a |
|---|---:|---|---|---|
| `FAST_5` | 5 | 5s, 15s, 45s, 120s + full jitter 0..20% | `DEPENDENCY_UNAVAILABLE`, `RATE_LIMITED`, `LOCK_TIMEOUT`, `LEASE_LOST` | validation, auth, unsupported schema, tenant mismatch, invariant/version conflict |
| `STANDARD_4` | 4 | 30s, 2m, 10m + full jitter 0..20% | isto | isto |
| `BATCH_3` | 3 | 1m, 5m + full jitter 0..20% | isto + `OBJECT_STORE_TRANSIENT`, `SCANNER_TRANSIENT` | unsafe file, parser/schema/PII violation, owner invariant conflict |
| `BILLING_5` | 5 | 5m, 30m, 2h, 8h + full jitter 0..20% | `DEPENDENCY_UNAVAILABLE`, `LOCK_TIMEOUT`, `LEASE_LOST` | nedokaziva istorija/presek, validation/auth/schema/tenant/invariant conflict |
| `NO_AUTO_RETRY` | 1 | nema | nijedan | svaki neuspeh; ručni recovery pravi novi odobren trigger |

Lease mora biti kraći od max runtime-a. Heartbeat interval je najviše jedna trećina lease-a. Svaki checkpoint/result commit proverava najnoviji fencing token. `FORBID_OVERLAP` je podrazumevan po `(job_key,execution_scope_key)`, gde je ključ tačno `SCHOOL:<school_id>` ili `PLATFORM`; `ALLOW_BOUNDED(n)` je naveden samo gde je dozvoljen. Manual/recovery trigger zahteva katalogom navedeni M21/owner permission, reason code i audit.

## 2. Published definicije

| # | `job_key` / owner | Trigger i semantic key | Scope/concurrency | Runtime; lease/hb; retry |
|---:|---|---|---|---|
| 1 | `auth.session_expiry_cleanup` / M01 | hourly UTC minute 07; `utc_hour:partition` | PLATFORM; bounded 4 partitions | 600s; 90s/30s; STANDARD_4 |
| 2 | `invitation.expiry_scan` / M02 | every 15m; `school:utc_quarter_hour` | PER_SCHOOL; FORBID_OVERLAP | 300s; 60s/20s; STANDARD_4 |
| 3 | `invitation.delivery_dispatch` / M02 | every 1m; `school:utc_minute:delivery_shard` | PER_SCHOOL; bounded 4 shards | 180s; 45s/15s; FAST_5 |
| 4 | `tenant.authorization_invalidation_dispatch` / M03 | PLATFORM event `identity.authorization_invalidated`; `consumer_name:message_id` | PLATFORM; bounded 4 account shards | 120s; 45s/15s; FAST_5 |
| 5 | `commercial.effective_transition` / M04 | every 5m; `utc_5m_bucket:agreement_shard:transition_policy_version` | PLATFORM coordinator; bounded 4 isolated agreement shards | 300s; 60s/20s; STANDARD_4 |
| 6 | `rbac.temporal_access_transition` / M05 | every 1m; `utc_minute:scope_kind:scope_shard` | PLATFORM coordinator; bounded 4 isolated shards | 300s; 60s/20s; STANDARD_4 |
| 7 | `rbac.support_access_expiry` / M05 | every 1m; `utc_minute:shard` | PLATFORM; bounded 4 | 60s; 30s/10s; FAST_5 |
| 8 | `schedule.recurrence_materialize` / M10 | daily 01:00 school local and event on series version; `school:series_id:series_version:horizon_end` | PER_SCHOOL; bounded 2 | 1800s; 180s/60s; STANDARD_4 |
| 9 | `attendance.auto_lock` / M11 | every 5m; `school:utc_5m_bucket:lock_policy_version` | PER_SCHOOL; FORBID_OVERLAP | 300s; 60s/20s; STANDARD_4 |
| 10 | `finance.billing_generate` / M12 | daily 00:15 school local; `school:local_date:billing_policy_version` | PER_SCHOOL; FORBID_OVERLAP | 3600s; 180s/60s; STANDARD_4 |
| 11 | `finance.reminder_eligibility` / M12 | daily 09:00 school local; `school:local_date:reminder_policy_version` | PER_SCHOOL; FORBID_OVERLAP | 1800s; 180s/60s; STANDARD_4 |
| 12 | `finance.event_cancellation_materialize` / M12 | event `EventCancelledV1`; `consumer_name:message_id`; schema/aggregate version su stale/compatibility guardovi | PER_SCHOOL; bounded 2 events | 3600s; 180s/60s; BILLING_5 |
| 13 | `communication.delivery_dispatch` / M13 | every 1m; `school:utc_minute:channel:delivery_shard` | PER_SCHOOL; bounded 2/channel | 300s; 60s/20s; FAST_5 |
| 14 | `communication.draft_retention` / M13 | daily 02:30 school local; `school:local_date:retention_policy_version` | PER_SCHOOL; FORBID_OVERLAP | 1800s; 180s/60s; STANDARD_4 |
| 15 | `notification.dispatch` / M14 | event Notification queued; `message_id:notification_id:version` | PER_SCHOOL; bounded 4 | 120s; 45s/15s; FAST_5 |
| 16 | `notification.retry_due` / M14 | every 1m; `school:utc_minute:channel` | PER_SCHOOL; bounded 2/channel | 180s; 45s/15s; FAST_5 |
| 17 | `documents.malware_scan` / M15 | event object uploaded; `message_id:document_version_id` | PER_SCHOOL; bounded 2 | 900s; 120s/40s; BATCH_3 |
| 18 | `documents.storage_expiry_cleanup` / M15 | daily 03:00 school local; `school:local_date:retention_policy_version` | PER_SCHOOL; FORBID_OVERLAP | 1800s; 180s/60s; STANDARD_4 |
| 19 | `events.deadline_transition` / M16 | every 5m; `school:utc_5m_bucket:event_policy_version` | PER_SCHOOL; FORBID_OVERLAP | 300s; 60s/20s; STANDARD_4 |
| 20 | `privacy.retention_disposition` / M17 | daily 01:30 school local; `school:local_date:policy_version` | PER_SCHOOL; FORBID_OVERLAP | 3600s; 180s/60s; STANDARD_4 |
| 21 | `privacy.dsar_orchestration` / M17 | every 15m; `school:utc_quarter_hour` | PER_SCHOOL; FORBID_OVERLAP | 1800s; 180s/60s; STANDARD_4 |
| 22 | `privacy.export_expiry_cleanup` / M17 | every 15m; `school:utc_quarter_hour:artifact_shard` | PER_SCHOOL; bounded 2 shards | 600s; 90s/30s; STANDARD_4 |
| 23 | `reports.projection_consume` / M18 | owner outbox event; `consumer_name:message_id` | PER_SCHOOL; bounded 4 streams | 300s; 60s/20s; FAST_5 |
| 24 | `reports.projection_gap_recovery` / M18 | every 1m kada gap postoji; `school:stream_key:first_missing_sequence` | PER_SCHOOL; FORBID_OVERLAP/stream | 600s; 90s/30s; STANDARD_4 |
| 25 | `reports.export_generate` / M18 | event `ReportExportRequestedV1`; `consumer_name:message_id` | PER_SCHOOL; bounded 2 exports | 3600s; 180s/60s; BATCH_3 |
| 26 | `reports.export_expiry_cleanup` / M18 | every 15m; `school:utc_quarter_hour:export_shard` | PER_SCHOOL; bounded 2 shards | 600s; 90s/30s; STANDARD_4 |
| 27 | `search.projection_consume` / M19 | owner outbox event; `consumer_name:message_id` | PER_SCHOOL; bounded 4 | 300s; 60s/20s; FAST_5 |
| 28 | `pwa.intent_installation_expiry` / M19 | every 5m; `utc_5m_bucket:artifact_shard` | PLATFORM; bounded 4 isolated shards | 300s; 60s/20s; STANDARD_4 |
| 29 | `import.file_scan` / M20 | event import uploaded; `message_id:batch_id:file_hmac_key_version:file_hmac` | PER_SCHOOL; bounded 2 | 900s; 120s/40s; BATCH_3 |
| 30 | `import.parse_validate` / M20 | event scan clean; `message_id:batch_id:schema_version` | PER_SCHOOL; bounded 2 | 1800s; 180s/60s; BATCH_3 |
| 31 | `import.execute` / M20 | event import confirmed; `message_id:execution_id:preview_hash` | PER_SCHOOL; max 4 row workers inside one execution; one execution per school | 7200s; 180s/60s; BATCH_3 |
| 32 | `import.issue_report_generate` / M20 | event `ImportIssueReportRequestedV1`; `consumer_name:message_id` | PER_SCHOOL; bounded 2 reports | 1800s; 180s/60s; BATCH_3 |
| 33 | `import.expiry_cleanup` / M20 | daily 04:00 school local; `school:local_date:retention_policy_version` | PER_SCHOOL; FORBID_OVERLAP | 1800s; 180s/60s; STANDARD_4 |
| 34 | `operations.audit_segment_seal` / M21 | day 1 at 00:30 UTC for previous UTC month; `partition_key:period_start` | PLATFORM; bounded 4 partitions | 1800s; 180s/60s; NO_AUTO_RETRY |
| 35 | `operations.audit_chain_verify` / M21 | daily 05:00 UTC; `utc_date:partition_shard` | PLATFORM; bounded 4 | 3600s; 180s/60s; NO_AUTO_RETRY |
| 36 | `operations.backup_create` / M21 | daily 02:00 UTC; `utc_date:backup_policy_version` | PLATFORM; FORBID_OVERLAP | 14400s; 300s/60s; NO_AUTO_RETRY |
| 37 | `operations.backup_verify` / M21 | event backup completed; `backup_id:verification_policy_version` | PLATFORM; bounded 2 | 7200s; 300s/60s; NO_AUTO_RETRY |
| 38 | `operations.restore_rehearsal` / M21 | manual before pilot, then quarterly approved schedule; `rehearsal_plan_id:backup_id` | PLATFORM; FORBID_OVERLAP; dual control | 28800s; 300s/60s; NO_AUTO_RETRY |
| 39 | `commercial.subscription_usage_snapshot` / M04 | monthly day 1 at 00:10 school local; `school:billing_month:usage_rule_version` | PER_SCHOOL; FORBID_OVERLAP | 1800s; 180s/60s; BILLING_5 |
| 40 | `portal.pilot_enrollment_expiry` / M28 | every 1m; `utc_minute:school_shard` | PER_SCHOOL; FORBID_OVERLAP | 120s; 45s/15s; FAST_5 |

## 3. Posebne zabrane i dozvole

- Scheduled owner job samo pronalazi eligible redove po owner pravilima; scheduler ne izmišlja business datum, reminder sadržaj, billing iznos, event rezultat ili retention osnov.
- M02 ima tačno dva published scheduled ključa: `invitation.expiry_scan` i `invitation.delivery_dispatch`. Expiry scan u odvojenim bounded stranicama pod stabilnim row-lock redosledom materijalizuje (a) `Invitation` ACTIVE→EXPIRED sa invalidacijom neterminalnih attempt-a i (b) jedinu M02 §4.4 tombstone tranziciju za `InvitationTokenDeliverySecret.delete_after<=database_now`, uključujući secret-e već terminalnih invitation-a. Read-time expiry i zabrana dekripcije od `delete_after` važe i pre job-a; nema grace perioda niti zasebnog secret-cleanup runtime aliasa.
- `invitation.delivery_dispatch` je jedini M02 delivery worker. Obrađuje samo dospele QUEUED ili RETRYABLE_FAILED generacije dok su invitation i secret još efektivni, koristi M02 lease/fencing i stabilan provider idempotency ključ, a business-attempt limit ostaje M02 autoritet. M21 `FAST_5` retry je retry jednog job execution-a zbog infrastrukturnog kvara i ne povećava M02 dozvoljeni broj provider submission pokušaja.
- `tenant.authorization_invalidation_dispatch` prihvata samo allow-listed M01 PLATFORM event sa null `school_id`; kroz application coordinator paginirano pronalazi pogođene M03/M05/M07 projection reference po opaque account ID-u i invalidira ih idempotentno. Ne emituje se po jedan event iz M01 po školi, ne kopira membership ili child podatke u payload i ne predstavlja autorizacioni autoritet: svaki request već failuje na M01 version proveri pre dispatcher-a.
- `rbac.temporal_access_transition` materijalizuje samo M05 vremenske tranzicije School/Platform RoleAssignment-a, PermissionGrant-a i OfflineAuthorizationLease-a. PLATFORM coordinator fan-out-uje school redove u odvojene tenant transakcije; request-time `database_now` guard je autoritet i pre job-a. OWNER i PLATFORM_SECURITY_ADMIN nisu vremenski ograničivi u H0, pa job ne može napraviti školu bez owner-a ili platformu bez security admina.
- `communication.delivery_dispatch` obrađuje samo M13 EMAIL delivery redove; IN_APP dostupnost nastaje u publish commit-u. Due claim, provider poziv i callback koriste M13 SUBMITTING lease/fencing/provider-idempotency ugovor. Buduće zakazano objavljivanje nije H0 i ne postoji `communication.scheduled_publish` runtime ključ.
- M12 job emituje owner outbox; ne poziva M14 komandu. `finance.event_cancellation_materialize` obrađuje samo verifikovan M16 `EventCancelledV1`, pronalazi M12 assessment-e preko tenant-bound `source_parent_id`, obrađuje najviše 500 po cursor stranici i koristi deterministic `message_id:assessment_id` owner command identity; M16 se ne poziva nazad dok se drži M12 lock. M16 deadline job ne poziva M12/M14/M15. M14 je consumer.
- `reports.export_generate` prihvata samo M18 `ReportExportRequestedV1`, ponavlja trenutni actor/tenant/permission/subject/source guard pre prvog reda i neposredno pre SUCCEEDED publish-a, koristi bounded-memory streaming i lease/fencing, i nikad ne objavljuje parcijalan ili nešifrovan object. `reports.export_expiry_cleanup` materijalizuje TTL, opoziva ticket/session byte pristup, briše finalni object i nereferencirane privremene object-e uz durable deletion receipt.
- `pwa.intent_installation_expiry` materijalizuje M19 DeepLinkIntent TTL i 90-dnevnu neaktivnost PwaInstallation-a. Request-time TTL/hard-expiry ostaje autoritet; terminalni deep-link target ciphertext/HMAC se tombstone-uje i job ne pokušava remote brisanje browser cache-a.
- `commercial.effective_transition` je PLATFORM coordinator nad agreement shard-ovima jer jedan M04 agreement može obuhvatiti više škola/scope-ova. Jedan aggregate lock/CAS određuje parent tranziciju; svaki school entitlement efekat ostaje tenant-safe. Read-time interval/status guard važi i pre job-a, a job ne može aktivirati istekao ili samo delimično validan agreement.
- `import.issue_report_generate` prihvata samo M20 `ImportIssueReportRequestedV1`, koristi originalni message ID za inbox/job dedupe i pre prvog reda i AVAILABLE publish-a ponavlja M01/M03/M05/authorization-version/source-hash guard. Stream je bounded-memory, object private+encrypted, payload je samo row number/column key/error code; stale fencing, promenjen source ili revoke ne mogu objaviti byte. `import.expiry_cleanup` opoziva ticket/session i briše finalne i orphan temp object-e uz durable deletion receipt.
- M06/M07 retention nema zaseban runtime job: M17 `privacy.retention_disposition` planira i poziva njihove idempotentne owner portove. M08 nema temporary occupancy claim koji ističe: CONFIRMED blok ostaje istorijski dok ga owner/source eksplicitno ne otkaže. M09 roster/staff efektivnost računa se as-of iz poluotvorenih datuma i append-only transition istorije; nema status-materialization job-a. Nepoznati stari ključevi za ta tri slučaja moraju failovati kao unpublished.
- `portal.pilot_enrollment_expiry` samo materijalizuje ACTIVE/SUSPENDED → EXPIRED kada je `effective_until <= database_now`; request-time M28 guard isto stanje tretira kao neefektivno i pre job-a. System transition koristi deterministički request ID `school_id:enrollment_id:effective_until` i ne izmišlja platform actor-a.
- `communication.draft_retention` emituje warning jednom od 83. dana i purge-uje od 90. dana neaktivnosti samo posle row-lock/version/last-activity i M17 legal-hold recheck-a; disposition+delete+audit+outbox+receipt su jedan commit. Job payload nema subject/body/recipient podatke.
- `privacy.export_expiry_cleanup` bira M17 AVAILABLE artifact-e čiji je `expires_at<=database_now` i DRAFT/APPROVED controlled-handoff authorization-e čiji je sopstveni rok istekao. Atomski ih označava EXPIRED, briše private segment objekte uz durable deletion receipt kada je artifact istekao i opoziva pripadajući ticket/session pristup. Handoff request-time guard već odbija byte od cutoff-a; worker nije grace period. Retention/legal-hold se primenjuje na dokaznu metadata-u, ali nikad ne produžava download/handoff TTL niti čuva downloadable object posle isteka artifact-a.
- `privacy.dsar_orchestration` pored task koordinacije bira IDENTITY_PENDING zahteve čiji je immutable `identity_verification_deadline_at<=database_now`; request-row lock i expected version daju jednu EXPIRED tranziciju/receipt. Ne vezuje Person po emailu, ne oživljava terminalni zahtev i ne briše M15 intake dokaz mimo retention/legal-hold ugovora.
- `reports.projection_consume` ne proglašava checkpoint svežim dok nema sve sekvence do barijere, uključujući eksplicitno terminalno dispositionovane poruke.
- `import.execute` unutrašnja paralelnost ne menja M20 all-or-nothing po redu, business-key receipt ili cancel pravilo.
- Manual/recovery za owner job zahteva odgovarajući owner permission plus `platform.jobs.manage`; backup/restore/audit job zahteva tačan M21 permission iz M05 registra, step-up i gde je navedeno dual control.
- Katalog određuje gornje granice. Implementacija sme koristiti kraći runtime/lease ili manje paralelizma, ali ne više attempts/concurrency niti širi retry allow-list bez nove published verzije.
