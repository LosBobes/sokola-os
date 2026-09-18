---
tip: qa-traceability
modul: M05
modul-id: M05
revizija: "2.0"
status: SPEC_CANDIDATE
datum: 2026-09-16
obavezni-scenariji: 213
---

# M05 — QA, traceability i seed

## 1. Izvršna pravila

Svaki scenario je automatizovan server/API test. UI test može biti dodatni dokaz, ali ne zamenjuje server-side proveru. Vreme je kontrolisano test clock-om; UUID-i, policy hash i payload canonicalization su deterministički. Za svaki neuspeh se proverava: HTTP + code, nepromenjeno stanje baze, odsustvo nedozvoljenog outbox/notifikacionog side effect-a i observability bez PII. Za svaki uspeh se proverava: stanje, version, receipt, tačno jedan audit i odgovarajući outbox.

## 2. Traceability po oblastima

| QA opseg | Master ugovor | Dokaz |
|---|---|---|
| 01–10 | §2.2–2.4, §3.3, §5.1 | Policy/role katalog i fail-closed objava. |
| 11–30 | §2.5–2.6, §3.2, §5.2 | School/platform RoleAssignment lifecycle. |
| 31–48 | §2.7, §3.2, §5.3 | Direct grant/delegacija bez escalation-a. |
| 49–70 | §3.1, §4 | Tenant, permission, subject i child guard. |
| 71–82 | §4.4, §7.1 | Revocation, cache, idempotency, concurrency. |
| 83–112 | §2.8, §3.4, §5.4–5.5, §7.3 | Standardni Support Access. |
| 113–120 | §3.5, §5.6 | Break-glass. |
| 121–129 | §2.9, §3.7, §5.7 | Offline authorization envelope. |
| 130–132 | §3.6, §8–9 | Observability, migracija, source-of-truth. |
| 133–134 | §2.2.1, §3.1, §4.1 | Future-safe authorization domeni i zabrana Organization scope-a. |
| 135–138 | §2.7, §3.2, §4.2, §7.2 | Verifikovani subject-basis, payer/guardian razdvajanje i tenant-safe FK. |
| 139–144 | §2.8, §3.4, §7.1, §7.3 | Normalizovan support scope, approval subset, opaque ticket receipt, konkurentni audit lanac i atomski repair audit. |
| 145–160 | §3.3.2, §3.7, §4 | M08–M12 tačni binding-i, subject scope, offline deny/allow i fail-closed policy seed. |
| 161–180 | §3.3.3, §3.7, §4 | M13–M16 binding-i, content/child/payer zaštita i offline deny. |

## 3. Deterministički scenariji

### A. Policy i role katalog

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-001` | Jedna ACTIVE revizija; security admin objavljuje validan DRAFT sa tačnim expected version/hash-om. | Novi je ACTIVE, stari SUPERSEDED u jednoj transakciji; jedan audit/outbox/receipt. |
| `M05-QA-002` | Dva konkurentna publish zahteva ciljaju isti DRAFT. | Tačno jedan uspeva; drugi 409 `RBAC_POLICY_REVISION_CONFLICT`; u bazi tačno jedan ACTIVE. |
| `M05-QA-003` | DRAFT binding referencira nepostojeći permission. | 422 `RBAC_POLICY_REVISION_INVALID`; prethodni ACTIVE ostaje netaknut. |
| `M05-QA-004` | Nova revizija uvodi permission bez role binding-a. | Permission je default deny za sve role dok binding/direct grant nije eksplicitno dodat. |
| `M05-QA-005` | Nova revizija RETIRED-uje permission sa aktivnim direct grantom. | Pre vidljivosti nove revizije grant je neefektivan i REVOKED/materializovan; nema stale allow-a. |
| `M05-QA-006` | Publish payload hash ne odgovara kanonskom sadržaju. | 422; nema promene niti success audit-a. |
| `M05-QA-007` | Pokušaj izmena već SUPERSEDED revizije. | 409; objavljena revizija ostaje immutable. |
| `M05-QA-008` | OWNER A podesi sr-Latn UI label `INSTRUCTOR=Predavač/Predavači`, pa pokuša HTML/control label i retire. | Validan override menja samo prikaz; role key/binding/autorizacija ostaju `INSTRUCTOR`. Nevalidan label je 422; posle RETIRED koristi se default. |
| `M05-QA-009` | Kod ili seed traži `SUPER_ADMIN`/trajni `SOKOLA_SUPPORT`. | Validation/build test pada; ne postoji aktivna definicija ni assignment. |
| `M05-QA-010` | PLATFORM_OPERATIONS_ADMIN poziva school business query bez Support grant-a/membership-a. | 404 `RBAC_NOT_FOUND_SAFE`; platform role ne daje tenant pristup niti otkriva School podatak. |

### B. Role assignments

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-011` | OWNER A dodeljuje MANAGER aktivnom membership-u A. | ACTIVE assignment, version 1, invalidation/audit/outbox. |
| `M05-QA-012` | OWNER kreira INSTRUCTOR sa `valid_from=tomorrow`; `rbac.temporal_access_transition` kasni jedan run. | SCHEDULED; pre vremena nije efektivan, od tačnog DB vremena request guard ga tretira ACTIVE, a job zatim jednom materijalizuje status/invalidation bez duplog audit/outbox-a. |
| `M05-QA-013` | Target nema M06 membership A. | 422 `RBAC_MEMBERSHIP_REQUIRED`; nema dodele. |
| `M05-QA-014` | OWNER A šalje membership B uz context A. | Safe 404; nema dokaza da B postoji. |
| `M05-QA-015` | MANAGER pokušava dodeliti MANAGER. | 403 `RBAC_ROLE_ASSIGNMENT_NOT_ALLOWED`. |
| `M05-QA-016` | OWNER dodeljuje LIMITED_ADMIN. | Uspeh; LIMITED_ADMIN dobija samo eksplicitne baseline binding-e, ne sva owner prava. |
| `M05-QA-017` | MANAGER dodeljuje INSTRUCTOR. | Uspeh unutar A. |
| `M05-QA-018` | LIMITED_ADMIN pokušava dodeliti INSTRUCTOR. | 403; UI stanje nije relevantno. |
| `M05-QA-019` | OWNER direktno poziva RBAC-01 za GUARDIAN bez M07 internal proof-a. | 422 `RBAC_GUARDIAN_RELATION_REQUIRED`. |
| `M05-QA-020` | OWNER direktno poziva RBAC-01 za OWNER. | 403; OWNER ide samo M04 nomination + M02/internal tokom. |
| `M05-QA-021` | M04/M02 internal tok pokuša OWNER sa budućim `valid_from` ili non-null `valid_until`; zatim se jedini važeći OWNER suspenduje/opoziva. | Vremenski OWNER je 422 `RBAC_ROLE_VALIDITY_INVALID`; last-owner promena je 409 `RBAC_LAST_OWNER_PROTECTED`; jedini OWNER ostaje ACTIVE. |
| `M05-QA-022` | Primary OWNER sa još jednim ownerom se opoziva bez M04 transfera. | 409 `RBAC_PRIMARY_OWNER_TRANSFER_REQUIRED`. |
| `M05-QA-023` | OWNER prvo suspenduje niži assignment sa unknown reason-om, zatim sa dozvoljenim reason-om i tačnom verzijom. | Prvi poziv 422 `RBAC_REASON_INVALID` bez promene; drugi SUSPENDED i sledeći request targeta denied. |
| `M05-QA-024` | Reactivate SUSPENDED pre isteka uz active membership. | ACTIVE, version +1; stare sesije nisu authorization dokaz. |
| `M05-QA-025` | Revoke role sa tri open direct grant-a. | Role i sva tri granta REVOKED u jednoj transakciji. |
| `M05-QA-026` | Reactivate REVOKED/EXPIRED assignment. | 409 `RBAC_ROLE_INVALID_TRANSITION`; potreban nov ID. |
| `M05-QA-027` | Rok non-owner assignment-a prođe, `rbac.temporal_access_transition` nije radio, zatim dva workera materijalizuju isti red. | Sledeći request ga odmah smatra EXPIRED; jedan worker atomarno materijalizuje role+child grant/invalidation, drugi dobija isti business rezultat bez duplikata. |
| `M05-QA-028` | M06 membership SUSPENDED, role ACTIVE. | Role je neefektivna bez menjanja istorijskog statusa; request denied. |
| `M05-QA-029` | M06 membership prelazi `TERMINATED`. | Svi open role/grant zapisi te epizode atomarno REVOKED; nova epizoda ih ne oživljava. |
| `M05-QA-030` | School DEACTIVATED pa reactivated. | Tokom deactivation nema context-a; posle reactivation treba nov context, samo još važeće role mogu važiti. |

### C. Direct permission, delegacija i unija

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-031` | OWNER grantuje DIRECT_DELEGABLE school permission LIMITED_ADMIN-u; kontrolni poziv koristi unknown grant reason. | Validan poziv daje ACTIVE grant u tačnom scope-u; unknown reason je 422 bez upisa. |
| `M05-QA-032` | MANAGER pokušava preneti permission koji sam nema. | 403 `RBAC_PERMISSION_ACTOR_LACKS_PERMISSION`. |
| `M05-QA-033` | MANAGER ima ciljni permission ali nema `school.rbac.permissions.delegate`. | 403; oba uslova su obavezna. |
| `M05-QA-034` | OWNER pokušava direct grant permission-a `ROLE_ONLY`. | 403 `RBAC_PERMISSION_NOT_DELEGABLE`. |
| `M05-QA-035` | School actor pokušava grant platform permission-a. | 403; platform/school scope se ne meša. |
| `M05-QA-036` | Permission traži CHILD scope, body šalje SCHOOL. | 422 `RBAC_PERMISSION_SCOPE_INVALID`. |
| `M05-QA-037` | Scope ref pripada B, context/grant A. | Safe 404; grant ne nastaje. |
| `M05-QA-038` | GUARDIAN role + CHILD grant + aktivni M07 link. | Bazni M05 sloj prolazi; M07 i dalje odlučuje kategoriju pristupa. |
| `M05-QA-039` | Isti grant, ali link opozvan. | 404 `RBAC_NOT_FOUND_SAFE`; nema child payload-a ni indikatora postojanja deteta. |
| `M05-QA-040` | Parent role SUSPENDED, grant ACTIVE. | Grant je neefektivan. |
| `M05-QA-041` | Grant `valid_until` prošao bez JOB-a. | Lazy EXPIRED; request denied. |
| `M05-QA-042` | Drugi request_id pokušava isti otvoren prirodni grant. | 409 `RBAC_PERMISSION_GRANT_EXISTS`; jedan red. |
| `M05-QA-043` | Isti request_id + isti payload ponovljen posle uspeha. | 200 replay, isti ID/result; bez duplog audit/outbox-a. |
| `M05-QA-044` | Isti request_id + drugi scope_ref. | 409 `RBAC_IDEMPOTENCY_KEY_REUSED`; nema promene. |
| `M05-QA-045` | Dva različita ključa paralelno grant-uju isti prirodni ključ. | Tačno jedan uspeva, drugi semantički 409; unique constraint poslednja zaštita. |
| `M05-QA-046` | Podaci pokušavaju person-level DENY override. | Schema/API odbija 422; MVP nema paralelni deny model. |
| `M05-QA-047` | Actor ima MANAGER+INSTRUCTOR; bira Instructor workspace. | Efektivna unija oba seta ostaje ista. |
| `M05-QA-048` | Jedna role SUSPENDED, druga ACTIVE. | Unija uključuje samo ACTIVE vremenski važeće dodele/grantove. |

### D. Tenant, authorization i zaštita dece

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-049` | OWNER A poziva resource B poznatim UUID-em. | 404 `RBAC_NOT_FOUND_SAFE`; response bez tenant/name/count hint-a. |
| `M05-QA-050` | School A i C su ista Organization; OWNER A traži C. | 404; Organization ne prenosi pristup. |
| `M05-QA-051` | Unknown UUID i stvarni cross-tenant UUID. | Isti schema/code/status i bez materijalne timing/enumeration razlike. |
| `M05-QA-052` | Resource je A, actor A nema permission. | 403 `RBAC_FORBIDDEN`. |
| `M05-QA-053` | Lista A ima 7 vidljivih + 3 skrivena reda. | `items/count/cursor` računati samo nad 7. |
| `M05-QA-054` | Potpisani cursor iz A koristi se u B; kontrolni slučaj koristi sintaksno nevalidan cursor u A. | Cross-tenant cursor vraća 404 `RBAC_NOT_FOUND_SAFE`; sintaksno nevalidan cursor vraća 422 `RBAC_CURSOR_INVALID`; nijedan ne vraća rezultate. |
| `M05-QA-055` | Cache za istog account-a u A i B. | Različit ključ uključuje school/policy/auth/tenant/subject versions; nema deljenja. |
| `M05-QA-056` | JWT/client tvrdi permission koji server catalog nema. | Claim se ignoriše; 403/503 prema server autoritetu. |
| `M05-QA-057` | Policy store nije dostupan, cache freshness nedokazana. | 503 `RBAC_POLICY_UNAVAILABLE`; nema protected payload-a. |
| `M05-QA-058` | Membership store nije dostupan. | Fail-closed; nema fallback-a na staru sesiju. |
| `M05-QA-059` | OWNER bazno ima document view, ali child subject guard odbija konkretan record. | 403; permission ne preskače subject guard. |
| `M05-QA-060` | INSTRUCTOR traži roster nedodeljene grupe. | 404 `RBAC_NOT_FOUND_SAFE`; dodeljene grupe rade pozitivnim kontrolnim testom. |
| `M05-QA-061` | SUBSTITUTE_INSTRUCTOR traži drugi termin iste grupe. | 403; samo eksplicitno dodeljen termin prolazi. |
| `M05-QA-062` | GUARDIAN traži dete bez ACTIVE M07 link-a. | 404 `RBAC_NOT_FOUND_SAFE`; nema sugestije da dete postoji. |
| `M05-QA-063` | Signed download URL izdat dok actor ima pravo, zatim role revoked pre download-a. | Download ponovo proverava i odbija; URL nije autoritet. |
| `M05-QA-064` | Realtime subscription aktivan, role revoked. | Server prekida channel; ponovni event se ne isporučuje. |
| `M05-QA-065` | Background callback u ime korisnika sa starom version. | Odbijen pre side effect-a; service principal ne preskače user scope. |
| `M05-QA-066` | HIGH komanda prođe prvi check, permission revoked pre commit-a. | Precommit recheck vraća 409 `RBAC_CONCURRENT_CHANGE`; nema business upisa. |
| `M05-QA-067` | M01 account SUSPENDED, school role ACTIVE. | Svaki protected M05 request 401/403 fail-closed; records ostaju istorijski. |
| `M05-QA-068` | M03 tenant_access_version promenjena posle role update-a. | Stari context rejected; klijent mora re-resolve. |
| `M05-QA-069` | M04 entitlement uključen, actor nema permission. | 403; entitlement nije permission. |
| `M05-QA-070` | Feature flag uključen za tenant, actor nema permission/subject. | 403; flag nije permission. |

### E. Revocation, cache, idempotency i concurrency

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-071` | Role revoke commit završen, novi request počinje 1 ms kasnije sa starim cache entry-jem. | Denied; autoritativna/version provera ne dopušta stale allow. |
| `M05-QA-072` | Request je počeo pre revoke-a, ali još nije commit-ovao. | HIGH/CRITICAL precommit recheck ga blokira; read response ne vraća zaštićene podatke ako verzija više nije važeća. |
| `M05-QA-073` | Business upis moguć, ali audit/outbox/receipt insert pada. | Cela command transakcija rollback; klijent ne dobija uspeh. |
| `M05-QA-074` | Outbox consumer dobije isti event tri puta. | Jedna invalidacija/notifikacija; consumer dedupe po event ID-u. |
| `M05-QA-075` | Cache entry nema dokazanu policy/tenant version. | Autoritativni read ili 503 fail-closed; nikad allow iz stale cache-a. |
| `M05-QA-076` | Dva OWNER-a paralelno pokušaju opozive koji zajedno ostavljaju nula owner-a. | Lock/constraint dopušta najviše bezbedan rezultat; najmanje jedan ACTIVE OWNER ostaje. |
| `M05-QA-077` | Grant i parent role revoke paralelno. | Završno nema efektivnog granta; nema orphan open granta. |
| `M05-QA-078` | Kreiranje vremenski ograničenog PLATFORM_SECURITY_ADMIN-a ili revoke poslednjeg važećeg security admina. | Prvo je 422 `RBAC_ROLE_VALIDITY_INVALID`, drugo 409 `RBAC_LAST_SECURITY_ADMIN_PROTECTED`; platforma uvek ima najmanje jednog eksplicitno ACTIVE security admina. |
| `M05-QA-079` | PLATFORM_SECURITY_ADMIN pokušava sebi dodeliti dodatnu platform rolu. | 403 `RBAC_ROLE_ASSIGNMENT_NOT_ALLOWED`; self-assign ne nastaje. |
| `M05-QA-080` | Security admin sa step-up ≤5m, reason-om i ticket-om dodeljuje rolu drugom ACTIVE account-u; ponavlja isti request. | Tačno jedan assignment, jedan audit/outbox; retry vraća isti rezultat. |
| `M05-QA-081` | SuspendRole sa stale expected_version. | 409 `RBAC_ROLE_STALE_VERSION`; current stanje netaknuto. |
| `M05-QA-082` | Aplikacioni race prođe do DB partial unique constraint-a. | Jedan open assignment/grant; constraint error mapiran u stabilan M05 409, bez 500. |

### F. Standardni Support Access

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-083` | Named support agent bez M06 membership-a u A, ali sa platform support rolom, traži sebi A uz ticket na kojem je assignee, validan purpose, masked read, 60m. | PENDING request + notice owner-u; nema pristupa pre approval-a. Drugi agent ili ticket-assignee mismatch dobija 422 `SUPPORT_TICKET_INVALID_OR_NOT_ASSIGNED` bez otkrivanja tuđeg naloga/ticketa. |
| `M05-QA-084` | Ticket ref je prazan/predugačak, account nije assignee ili verifier nije dostupan. | Nevalidan ref je 422 `SUPPORT_TICKET_REQUIRED`; mismatch je 422 `SUPPORT_TICKET_INVALID_OR_NOT_ASSIGNED`; outage je 503 `SUPPORT_TICKET_VERIFICATION_UNAVAILABLE`; nema request-a. |
| `M05-QA-085` | Slobodan unknown purpose code. | 422 `SUPPORT_PURPOSE_INVALID`. |
| `M05-QA-086` | Trajanje 14 minuta. | 422 `SUPPORT_DURATION_INVALID`. |
| `M05-QA-087` | Trajanje 121 minut. | 422 `SUPPORT_DURATION_INVALID`. |
| `M05-QA-088` | Resource scope sadrži resource B uz school A; kontrolni slučaj sadrži nevažeću kombinaciju capability/resource u A. | Prvi zahtev vraća 404 `RBAC_NOT_FOUND_SAFE`; drugi 422 `SUPPORT_SCOPE_INVALID`; nema request-a i B se ne otkriva. |
| `M05-QA-089` | Active OWNER A sa step-up 2m odobrava PENDING. | APPROVED + ACTIVE grant vezan za named support account; notice/audit/outbox. |
| `M05-QA-090` | MANAGER A pokušava approval bez owner role. | 403 `SUPPORT_APPROVER_NOT_ALLOWED`. |
| `M05-QA-091` | Isti UserAccount je support target i owner approver. | 403 `SUPPORT_SELF_APPROVAL_FORBIDDEN`. |
| `M05-QA-092` | Test clock pređe request expiry, JOB nije radio; owner approve. | 410 `SUPPORT_REQUEST_EXPIRED`; request efektivno EXPIRED, nema grant-a. |
| `M05-QA-093` | Owner smanjuje 120m/5 capabilities na 30m/2. | Uspeh; grant ima uži scope/trajanje. |
| `M05-QA-094` | Owner pokušava dodati capability/resource ili duže trajanje. | 422 `SUPPORT_SCOPE_INVALID`/`SUPPORT_DURATION_INVALID`. |
| `M05-QA-095` | Drugi support account startuje tuđ grant. | 403 `SUPPORT_GRANT_NOT_ACTIVE`/out-of-scope; audit deny. |
| `M05-QA-096` | Named agent bez regularnog A context-a/membership-a startuje validnu sesiju. | ACTIVE session i request-scoped `SupportTenantExecutionContext`; ne nastaje AvailableTenantContext/RoleAssignment. Svaki response nosi obavezni support banner, actor/ticket/expiry. |
| `M05-QA-097` | MODULE_RECORD_READ_MASKED čita dozvoljeni record sa imenom/kontaktom. | Dozvoljena tehnička polja ostaju; identitet/kontakt su maskirani, audit sadrži HMAC ref. |
| `M05-QA-098` | Standard support traži health/special-category/document content/photo. | 403 `SUPPORT_ACTION_OUT_OF_SCOPE` čak i ako owner pokušao da ga doda. |
| `M05-QA-099` | Controlled repair poziva tačan odobren command/resource i validan expected_version. | Business guardovi rade; jedan repair/audit/activity zapis. Drugi resource/command je 403. |
| `M05-QA-100` | Support activity durable store nije dostupan. | 503 `SUPPORT_AUDIT_UNAVAILABLE`; read/mutation se ne izvršava. |
| `M05-QA-101` | Support pokušava CSV/bulk/signed download. | 403 `SUPPORT_EXPORT_FORBIDDEN`; bez fajla/job-a. |
| `M05-QA-102` | Support pokušava čitati/linkovati AuthIdentity ili promeniti account status. | 403; bez account/auth side effect-a. |
| `M05-QA-103` | Support pokušava role/permission/owner transfer. | 403; grant ne predstavlja RBAC pravo. |
| `M05-QA-104` | Support pokušava payment/refund/family-ledger mutation. | 403; nijedan finansijski zapis ne nastaje. |
| `M05-QA-105` | OWNER A prvo šalje unknown revoke reason, zatim dozvoljeni reason tokom active session. | Prvi poziv 422 `SUPPORT_DECISION_REASON_INVALID`; drugi odmah REVOKE-uje grant/session, bumpuje version, gasi realtime i blokira sledeći request. |
| `M05-QA-106` | Grant expiry prođe usred session-a bez JOB-a. | Sledeći request 410, session efektivno EXPIRED; nema protected payload-a. |
| `M05-QA-107` | Request/approve/start/end/revoke tok. | Škola dobija po jednu deduplikovanu notifikaciju bez PII za svaku propisanu fazu. |
| `M05-QA-108` | OWNER poziva SUP-Q03 za A. | Vidi A activity; RFC8785/domain hash chain i tenant-HMAC key verzija su reproduktivni, bez raw child/ref/payload-a. |
| `M05-QA-109` | MANAGER bez explicit `school.support.activity.view` poziva SUP-Q03. | 403; direct grant pozitivna kontrola otvara samo A log. |
| `M05-QA-110` | Dva StartSupportSession zahteva različitih request_id paralelno. | Tačno jedna ACTIVE session; drugi 409 `SUPPORT_SESSION_CONFLICT`. |
| `M05-QA-111` | Active session nema aktivnosti 15m. | Sledeći request denied, session ENDED; novi start moguć samo ako grant još ACTIVE. |
| `M05-QA-112` | Approve retry istog idempotency ključa posle uspeha. | Isti grant/result replay; nema drugog granta/audit-a/notifikacije. |

### G. Break-glass

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-113` | Incident commander sa step-up, active incident, exact A scope i 20m aktivira. | ACTIVE minimal grant + PENDING ratification; notice školi i full activity audit. |
| `M05-QA-114` | Reason `CUSTOMER_REQUEST`, nema active incident ref-a ili incident verifier nije dostupan. | 422 `BREAK_GLASS_REASON_INVALID`/`BREAK_GLASS_INCIDENT_REQUIRED`; outage je 503 `BREAK_GLASS_INCIDENT_VERIFICATION_UNAVAILABLE`; nema granta. |
| `M05-QA-115` | Requested duration 31m. | 422; nema granta. |
| `M05-QA-116` | Aktivator pokušava i ratifikaciju. | 409 `BREAK_GLASS_RATIFIER_DISTINCT_REQUIRED`. |
| `M05-QA-117` | Nema ratifikacije do +10m, JOB kasni. | Grant request-time REVOKED, ratification MISSED; kasna ratifikacija 410. |
| `M05-QA-118` | Notification delay 61m/bez containment razloga; zatim validan delay 45m. | Prvi 422; drugi dozvoljen, ali notice obavezno poslat najkasnije +45m/+60m limit. |
| `M05-QA-119` | Ratifikovan break-glass pokušava export, payment, owner/RBAC, identity ili audit delete. | Svaka radnja 403 `BREAK_GLASS_SCOPE_FORBIDDEN`; grant ne proširuje prohibicije. |
| `M05-QA-120` | Grant se završi; +24h review nije završen, zatim se završi kasno. | Review DUE→OVERDUE + alert; SUP-10 ga vodi COMPLETED uz očuvano kašnjenje i school-visible summary. |

### H. Offline authorization envelope

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-121` | RBAC-10 traži lease za permission sa offline `DENY`. | 409 `OFFLINE_OPERATION_NOT_ALLOWED`; nema lease-a. |
| `M05-QA-122` | Permission je `QUEUE_ALLOWED`, actor trenutno prolazi sve guardove, exact device/resource. | ACTIVE lease sa versions, nonce hash i max ops; nema child details. |
| `M05-QA-123` | Klijent traži 13h. | Server capuje/odbija prema ugovoru; izdati expiry nikad >12h. |
| `M05-QA-124` | Lease A/device1 koristi device2 ili school B. | 403 `OFFLINE_LEASE_SCOPE_MISMATCH`. |
| `M05-QA-125` | Logout/session expiry/school switch/revoke događaj. | Local integration test briše/kriptografski onesposobljava tenant cache i lease; nema podatka nakon drugog login-a. |
| `M05-QA-126` | Capture je bio u lease roku, ali membership/role/subject opozvan pre sync-a. | `OFFLINE_SYNC_AUTHORIZATION_CHANGED`, finalni `SYNC_FAILED`; business upis ne nastaje. |
| `M05-QA-127` | Attendance lease ima različite issued+12h, term_end+4h, correction deadline i session-expiry granice. | Expiry je tačno najranija od četiri vrednosti. |
| `M05-QA-128` | Inspect IndexedDB/local snapshot. | Samo M11 allow-list operation/idempotency, school/session/roster/participant/group/term refs, potreban display name, proposed status/minutes, digest/base-version/lease/sync code; nema DOB/kontakta/health/guardian/finance/docs/avatar/token/free-text notes. |
| `M05-QA-129` | Klijent pokuša offline AssignRole/Grant/Support approval. | UI/API queue odbija; nijedna M05 administrativna operacija nije enqueue-ovana ni optimistic-final. |

### I. Observability, migracija i integritet izvora istine

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-130` | Izvrše se allow/deny/error, support i break-glass tokovi; skeniraju logs/metrics/traces i load seed sa 1.000 permissions/6 roles/200 grantova. | Nema emaila, telefona, imena, DOB, raw child ID-a, reason note-a, tokena ili payload-a; authorization/support p95/p99 zadovoljavaju M05 §3.6 budžete. |
| `M05-QA-131` | Seed ima legacy TRAINER/SUBSTITUTE_TRAINER duplikate, SOKOLA_ADMIN, unknown/orphan PermissionGrant i tanak active SupportAccessGrant. Migracija se pokrene dva puta. | Neutralne role imaju jedan open red; admin dobija samo deterministične platform role iz §7.7 bez tenant bypass-a; neproverljiv grant/support je deny+exception; drugi run no-op bez duplikata. |
| `M05-QA-132` | Static scan aktivnog vaulta/koda/schema seed-a. | Jedan role/permission/support source of truth; nema active `SUPER_ADMIN`, owner wildcard, trajne support role, UI-only auth tvrdnje ni paralelnog TRAINER key-a. |
| `M05-QA-133` | H0 policy ima SCHOOL/PLATFORM ACTIVE, EVENT_ORGANIZER_WORKSPACE/VENUE_OPERATOR_WORKSPACE RESERVED; klijent, seed i background job pokušaju role, permission, context i query u RESERVED/unknown domenu. | Svaki pokušaj fail-closed sa `RBAC_AUTHORIZATION_DOMAIN_UNKNOWN`; nema context-a, assignment-a, business query-ja, cache/job/realtime kanala ni existence hint-a. Aktivacija je moguća samo novom policy revizijom nakon owner resolver + isolation suite-a. |
| `M05-QA-134` | Organization X plaća School A/C i ima hibridni EVENTS/VENUE agreement; actor ima pravo samo u A. Pokuša Organization-wide list/count/search/export i koristi agreement/item ID kao auth dokaz; dodatno, School OWNER u A pokuša COM-01..20 mutaciju bez ijednog od šest `platform.commercial.*` ključeva, i platform actor sa `platform.commercial.read` pokuša COM mutaciju. | Svaki zahtev za C/event/venue vraća 404 `RBAC_NOT_FOUND_SAFE`; ugovor i račun ne stvaraju permission; nema sintetičkog School-a. A ostaje dostupan samo kroz regularni SCHOOL pipeline. School OWNER dobija 403 `RBAC_FORBIDDEN`; `platform.commercial.read` dozvoljava samo query, pa COM mutacija vraća 403 bez odgovarajućeg granularnog ključa. |
| `M05-QA-135` | GUARDIAN dobija CHILD grant čiji je `subject_basis_kind=GUARDIAN_CHILD_LINK`, a `subject_basis_ref` pokazuje ACTIVE M07 link za isto dete i školu. | Grant je efektivan samo za dozvoljene child permission-e i tačno to dete; drugi child je safe 404. |
| `M05-QA-136` | PAYER bez guardian link-a dobija finansijski CHILD grant sa `subject_basis_kind=PAYER_CHILD_LINK` i aktivnim M07 payer dokazom. | Finansijski pregled/plaćanje prolazi za određeno dete; child dokumenti, prisustvo, zdravlje, poruke i profil vraćaju 404 `RBAC_NOT_FOUND_SAFE`. |
| `M05-QA-137` | Payer/guardian subject-basis je opozvan nakon početne autorizacije, a pre HIGH/CRITICAL commit-a. | Precommit recheck vraća 409 `RBAC_CONCURRENT_CHANGE`; nema poslovnog upisa, audita uspeha ni outbox događaja. |
| `M05-QA-138` | Pokuša se upis `RoleAssignment` sa `school_id=A`, a M06 `school_membership_id` pripada B. | Tenant-safe kompozitni FK/constraint odbija upis; API vraća 404 `RBAC_NOT_FOUND_SAFE`, bez cross-tenant detalja. |
| `M05-QA-139` | SUP-01 šalje duplikat scope stavke, wildcard/prefix, praznu stavku ili CONTROLLED_MUTATION bez exact resource/command-a; kontrolni zahtev šalje dve različite validne stavke. | Nevalidan zahtev je 422 `SUPPORT_SCOPE_INVALID` bez request-a; validan upisuje tačno dve normalizovane request stavke i `requested_scope_hash` odgovara canonical JSON-u. |
| `M05-QA-140` | OWNER pri SUP-02 pokuša dodati novi capability/resource/command, ublažiti masku ili READ_ONLY proširiti na CONTROLLED_MUTATION; zatim odobri strogi podskup. | Svako proširenje je 422 `SUPPORT_SCOPE_INVALID` bez prelaza/granta; podskup atomarno daje APPROVED request, jedan grant, njegove stavke i proverljiv `approved_scope_hash`. |
| `M05-QA-141` | Ticket ref je kratka/predvidiva vrednost; verifier ga potvrdi. Pregled baze, logova, trasa i outbox-a se skenira. | Čuva se samo opaque UUID verifier receipt uz poslovno potreban ticket ref; nema hash-a ticket sadržaja, ticket tela ni verifikacionog tokena u logu/eventu. Stari ili promenjen ticket se pri approve-u ponovo verifikuje fail-closed. |
| `M05-QA-142` | Dva support read zahteva iste sesije paralelno pokušaju upis ActivityEvent-a; zatim se jedan allow-listed byte istorijskog reda promeni. | Session chain ima jedinstvene uzastopne `sequence_no`, jedan head i reproduktivan `prev_event_hash/event_hash`; nema fork-a/duplikata/izgubljenog pokušaja, a tamper se otkriva. |
| `M05-QA-143` | CONTROLLED_REPAIR menja business red, ali terminalni support audit/outbox ili receipt simulirano pada pre commit-a. | Cela lokalna transakcija se vraća; nema business promene ni lažnog success-a. Kada nema zajedničke lokalne transakcije, komanda je 403 `SUPPORT_ACTION_OUT_OF_SCOPE` u H0. |
| `M05-QA-144` | Actor ima samo PAYER assignment/CONTACT membership i pokušava bilo koju M05 administrativnu/support akciju; zatim koristi tačno M12 finansijsko pravo za povezano dete. | Sve M05 admin/support akcije su 403 bez existence leak-a; finansijska pozitivna kontrola može proći samo kroz zaseban M12 permission i ACTIVE M07 payer subject-basis. Role label ne može PAYER-u dodati pravo. |

### J. Operational Core M08–M12 policy binding-i

| ID | Početno stanje i radnja | Očekivani rezultat |
|---|---|---|
| `M05-QA-145` | Objavi se nova policy revizija i izlista M08–M12 permission katalog. | Prisutan je svaki i samo svaki ključ iz master §3.3.2 sa tačnim risk/offline/binding/delegation vrednostima; seed hash je ponovljiv. |
| `M05-QA-146` | LIMITED_ADMIN nema direct grant i poziva svaki M08–M12 write/query. | Svaka radnja je deny; naziv uloge ne daje skriveni default. |
| `M05-QA-147` | INSTRUCTOR ima view/record bindings i aktivnu M09 dodelu za Group A. | Vidi samo Group A schedule/roster/attendance; može M11 record u važećem prozoru. |
| `M05-QA-148` | Isti INSTRUCTOR traži Group B bez dodele. | Safe 404/subject deny; binding bez assignment-a nije dovoljan. |
| `M05-QA-149` | SUBSTITUTE assignment/lease istekne pre request-a ili sync-a. | Online i sync fail-closed; nema stale allow-a. |
| `M05-QA-150` | GUARDIAN ima linked child, ali M28 entitlement je OFF. | Admin endpoints su deny; H1 schedule/attendance projekcija nije aktivirana samo role binding-om. |
| `M05-QA-151` | PAYER ima ACTIVE payer basis za account A i `finance.view`/`finance.credit.apply`. | Vidi/primenjuje samo dozvoljene finance podatke account-a A; nema schedule/attendance/group/online access. |
| `M05-QA-152` | GUARDIAN bez PAYER assignment-a traži finance. | Deny; guardian veza sama nije finansijska autorizacija. |
| `M05-QA-153` | Klijent traži offline lease za sve M08–M12 write permission-e. | Samo `school.attendance.record` je `QUEUE_ALLOWED`; svaki drugi daje `OFFLINE_OPERATION_NOT_ALLOWED`. |
| `M05-QA-154` | OWNER traži `school.schedule.conflict_override`. | Deny jer je permission RESERVED bez binding-a; owner nije wildcard. |
| `M05-QA-155` | INSTRUCTOR ima schedule view za online occurrence, zatim traži list svih online URI-jeva. | Konkretan occurrence URI može proći subject guard; list/decrypt drugih lokacija je deny. |
| `M05-QA-156` | OWNER pokušava direct-grant CRITICAL finance/support-like pravo LIMITED_ADMIN-u. | ROLE_ONLY pravo se ne grantuje; transakcija 403/422 bez side effect-a. |
| `M05-QA-157` | OWNER daje dozvoljen direct grant `school.groups.enrollments.manage` LIMITED_ADMIN-u za Group A. | Samo Group A i važeći tenant scope; Group B safe deny; grant ne uklanja resource guard. |
| `M05-QA-158` | Isti account ima MANAGER i PAYER, workspace=PAYER. | Unija dozvola postoji u istoj školi, ali payer child scope ne proširuje admin podatke druge škole/Family; workspace nije auth filter ni grant. |
| `M05-QA-159` | Policy seed se generiše dva puta i jedan permission dobije drugi risk/offline/binding bez revizije. | Identičan seed daje isti hash; promenjena semantika zahteva novu policy reviziju i stari hash ne prolazi. |
| `M05-QA-160` | Permission/assignment/payer basis se opozove između prvog check-a i M08/M09/M10/M11/M12 high-risk commit-a. | Svaki vlasnički modul ponavlja version check, vraća `RBAC_CONCURRENT_CHANGE`/namespaced conflict i radi potpuni rollback. |
| `M05-QA-161` | Policy 1.4 seed sadrži M13–M16 ključeve. | Tačan §3.3.3 katalog/hash; nema missing/extra. |
| `M05-QA-162` | LIMITED_ADMIN bez grant-a poziva M13–M16. | Sve deny. |
| `M05-QA-163` | INSTRUCTOR compose dodeljene/nedodeljene grupe. | Prva uslovno; druga safe deny. |
| `M05-QA-164` | GUARDIAN communication posle link revoke-a. | Safe 404; snapshot nije grant. |
| `M05-QA-165` | PAYER communication/event. | Deny. |
| `M05-QA-166` | PAYER own finance notification. | Samo neutralna own projekcija. |
| `M05-QA-167` | Guardian mark-read tuđe notification. | Safe 404. |
| `M05-QA-168` | Guardian/PAYER attention query. | Deny. |
| `M05-QA-169` | Instructor resolve attention bez scope-a. | Deny. |
| `M05-QA-170` | Guardian document download. | Ticket samo posle M07/M15 guard-a. |
| `M05-QA-171` | PAYER običan child dokument. | Deny; samo svoj PAYMENT_PROOF. |
| `M05-QA-172` | Staff običnim accept pravom prihvata umesto guardian-a. | Deny. |
| `M05-QA-173` | Assisted acceptance bez step-up/giver/reason. | Deny. |
| `M05-QA-174` | Guardian register svoje/tuđe dete. | Svoje uz audience; tuđe safe deny. |
| `M05-QA-175` | Instructor event attendance nedodeljen scope. | Deny. |
| `M05-QA-176` | Owner HARD capacity override. | Deny; WARNING only. |
| `M05-QA-177` | M13–M16 write traži offline lease. | Svaki offline denied. |
| `M05-QA-178` | Support traži communication body/document/event participants. | Scope odbijen. |
| `M05-QA-179` | Subject/permission revoke pre critical commit-a. | Recheck+rollback. |
| `M05-QA-180` | Static route-policy coverage. | Svaki route ima permission+resource+subject guard. |
| `M05-QA-181` | Svaki M17–M21/M28 runtime permission iz owner ugovora. | Tačno jedan red u `03-M05-PERMISSION-REGISTRY-M17-M21-M28.md`; nema skraćenog slash ključa. |
| `M05-QA-182` | Unknown novi route permission. | Policy publish ili startup route binding failuje zatvoreno. |
| `M05-QA-183` | PAYER sa finance basis-om traži child report/event/document koji nije PAYMENT_PROOF. | Deny/safe 404; payer basis ne postaje guardian basis. |
| `M05-QA-184` | Guardian traži globalni school search. | Deny; koristi samo M28 linked-child surface kada je feature aktivan. |
| `M05-QA-185` | Instructor traži school-wide attendance report. | Samo assignment-scoped subset; nema hidden total/count. |
| `M05-QA-186` | Support dobije generic wildcard scope za M17–M21. | Policy publish/grant odbijen; nema default binding-a. |
| `M05-QA-187` | Permission postoji, ali M28 entitlement/allowlist OFF. | Feature ostaje nedostupan; permission nije entitlement. |
| `M05-QA-188` | M20 execute direct-granted LIMITED_ADMIN-u. | Odbijeno; execute je ROLE_ONLY za Owner/Manager. |
| `M05-QA-189` | M21 restore isti actor odobrava i izvršava. | Odbijeno dual-control pravilom. |
| `M05-QA-190` | Nova policy revizija uklanja permission sa aktivnim grantom. | Grant postaje neefektivan u istom security-version commit-u; nema stale allow prozora. |
| `M05-QA-191` | M06/M07 permission catalog extraction. | Svih 16 ključeva postoji tačno jednom u `04-M05-PERMISSION-REGISTRY-M06-M07.md`, bez wildcard/alias reda. |
| `M05-QA-192` | Instructor čita basic podatak učesnika iz dodeljene i nedodeljene grupe. | Dodeljeni subject prolazi; nedodeljeni je safe 404 bez count/timing leak-a. |
| `M05-QA-193` | Guardian čita svoje povezano dete i drugog child ID-a. | Samo ACTIVE linked child minimalna projekcija; drugi je safe 404. |
| `M05-QA-194` | PAYER koristi `school.people.basic.view` preko payer basis-a. | Deny; payer basis nije child profile pravo. |
| `M05-QA-195` | Guardian traži contact druge odrasle osobe u Family. | Deny/safe 404; `school.people.contact.view` self binding ne otkriva druge. |
| `M05-QA-196` | Instructor čita safety note van aktivne assignment/termin scope. | Deny; permission bez subject/purpose guarda nije dovoljan. |
| `M05-QA-197` | M28 Basic pokušava prikaz safety note-a jer Guardian ima subject binding. | Surface/capability guard odbija; M28 Basic ne aktivira safety prikaz. |
| `M05-QA-198` | Manager sensitive identifier reveal bez capability/purpose/step-up. | Deny; sva tri uslova obavezna i read se auditira. |
| `M05-QA-199` | LIMITED_ADMIN dobija direct grant za M06/M07 CRITICAL write. | Policy/grant odbijen; svi su ROLE_ONLY. |
| `M05-QA-200` | Guardian role bez ACTIVE GuardianChildLink pokušava M07 self/child query. | Deny; role sama nije subject basis. |
| `M05-QA-201` | Isti account ima odvojene GUARDIAN i PAYER basis-e. | Child i finance odluke računaju se zasebno; nijedan basis ne proširuje drugi. |
| `M05-QA-202` | M28 portal access sa Guardian role, ali bez ACTIVE guardian basis-a. | Deny; role i permission sami ne otvaraju shell/private section. |
| `M05-QA-203` | PAYER ima `portal.mysokola.access` i `finance.view`. | Vidi samo exact payer finance scope; nema child/schedule/attendance/event surface. |
| `M05-QA-204` | GUARDIAN ima portal permission, ali M04 entitlement ili M28 pilot ili feature flag nije efektivan. | Svaki nedostajući sloj zasebno fail-closed; nijedan permission ga ne zaobilazi. |
| `M05-QA-205` | OWNER sa `school.portal.pilot.request` šalje zahtev. | Može samo REQUESTED; nema implicitnog activate/feature/entitlement efekta. |
| `M05-QA-206` | PLATFORM_OPERATIONS_ADMIN aktivira/reject/reactivate. | Samo `platform.portal.pilot.decide`, step-up+ticket+expected version; nema school content read-a. |
| `M05-QA-207` | PLATFORM_OPERATIONS_ADMIN pokušava suspend/revoke bez security ključa. | 403; decide ne implicira security manage. |
| `M05-QA-208` | PLATFORM_SECURITY_ADMIN suspend/revoke. | Samo `platform.portal.pilot.security_manage`, step-up+ticket+reason; odmah invalidation. |
| `M05-QA-209` | Standardni Support grant ili break-glass traži M28 portal/decision binding. | Nema default/implicit binding-a; ne postaje guardian/payer/platform rollout actor. |
| `M05-QA-210` | Portal shell permission postoji bez owner document/event/finance permission-a. | Te sekcije su izostavljene pre count-a; nema existence indikatora. |
| `M05-QA-211` | Policy sadrži M28 route bez jednog od pet exact ključeva ili bez composition guarda. | Publish/startup binding failuje zatvoreno. |
| `M05-QA-212` | OWNER/MANAGER poziva `finance.billing.confirm` bez svežeg step-up-a i `finance.credit.correct` bez drugog različitog trenutno ovlašćenog actor-a; payload koristi mali iznos/batch radi pokušaja zaobilaženja. | Policy+M12 composition odbija svaki slučaj; nema threshold bypass-a, self-approval-a, ledger-a ili obligation-a. Validna dva actora i step-up i dalje prolaze M12 subject/resource guard. |
| `M05-QA-213` | Kompletna M05 regresija i policy seed izvrše se nad tačno evidentiranim repo commit-om, migration head-om i policy hash-em. | Prolaz zahteva 213/213 stvarno izvršenih testova i 0 failed/skipped/flaky; svi M06–M21/M28 permission ključevi moraju biti exact i unique. |

## 4. Minimalni seed podaci

| Fixture | Sadržaj |
|---|---|
| `ORG-X`, `ORG-Y` | Organization X ima School A/C; Y ima School B. Dokazuje da Organization ne prenosi pristup. |
| `SCHOOL-A/B/C` | ACTIVE škole; dodatno A2 DEACTIVATED i A3 IN_PREPARATION/SETUP_ONLY. |
| `UA-X/P-X` | OWNER A, GUARDIAN B; dva tenant konteksta, bez cross-unije. |
| `UA-Y/P-Y` | MANAGER + INSTRUCTOR A; dokazuje union/workspace. |
| `P-LIMITED`, `P-INSTR`, `P-SUB`, `P-GUARD`, `P-PAYER` | Sve school role, sa dodeljenim/nedodeljenim group/term/child subjectima; PAYER nema guardian ili M05 admin prava. |
| Membership epizode | ACTIVE, SUSPENDED i TERMINATED; ponovljeno članstvo sa novim ID-em. |
| Role/grant stanja | SCHEDULED, ACTIVE, SUSPENDED, REVOKED, EXPIRED; open/natural duplicate kandidati. |
| `PLAT-SEC-1/2` | Dva security admina radi self-assign/last-admin i break-glass ratification testova. |
| `PLAT-OPS`, `SUPPORT-1/2`, `INCIDENT-1` | Odvojene platform role; nijedna nema implicitni tenant access. |
| Support fixtures | Pending valid/expired requests; active/revoked/expired grants; active/idle sessions; allowed/forbidden scope. |
| Break-glass fixtures | Jedan ratifikovan, jedan bez ratifikacije, jedan overdue review. |
| Offline fixtures | Device1/2; active/expired/revoked lease; minimalni roster bez realnog PII. |
| Authorization domain fixtures | SCHOOL/PLATFORM ACTIVE; EVENT/VENUE workspaces RESERVED; unknown domain; Organization X sa School A/C i hibridnim commercial item-ima bez auth grant-a. |

## 5. Test suite prijem

Suite pada ako je bilo koji očekivani test preskočen, flaky ili zavisan od realnog vremena/mreže. Obavezni suite tagovi su `m05-unit`, `m05-db-constraints`, `m05-api`, `m05-tenant-negative`, `m05-subject-negative`, `m05-domain-negative`, `m05-concurrency`, `m05-support`, `m05-breakglass`, `m05-offline-envelope`, `m05-operational-core-policy`, `m05-content-events-policy`, `m05-mysokola-policy`, `m05-observability`, `m05-migration`. Izveštaj navodi tačan broj pokrenutih/prošlih/palih/preskočenih testova; nula preskočenih za 212 scenarija.
