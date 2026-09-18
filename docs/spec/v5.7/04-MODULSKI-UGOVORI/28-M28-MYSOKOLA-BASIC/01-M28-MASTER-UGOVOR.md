---
tip: modulni-implementacioni-ugovor
modul-id: M28
naziv: mySOKOLA Basic parent-first portal
status: SPEC_CANDIDATE
revizija: "1.6"
datum: 2026-09-16
schema-zavisnosti: [M01, M04, M07]
read-portovi: [M01, M03, M04, M05, M06, M07, M10, M11, M12, M13, M14, M15, M16, M17, M19]
consumes-events-from: [M01, M03, M04, M05, M06, M07, M10, M11, M12, M13, M14, M15, M16, M17]
application-guardovi: [M01, M03, M04, M05, M07]
platform-interface: [M21]
offline-policy: DENY_PRIVATE_CONTENT_AND_BUSINESS_WRITES
horizont: H1_POST_MVP_PRE_PILOT_REQUIRED
feature-state: DEFAULT_OFF_UNTIL_PILOT_ALLOWLIST
---

# M28 — mySOKOLA Basic

## 1. Cilj, granice i Non-Goals

M28 je privatni, mobile-first parent/payer portal u istom SOKOLA sistemu. On sastavlja minimalne, trenutno autorizovane projekcije postojećih Core izvora i nudi jednu jasnu ulaznu tačku za roditelja/staratelja ili platioca. M28 ne postaje vlasnik deteta, naloga, guardian veze, rasporeda, prisustva, finansija, komunikacije, notifikacije, dokumenta, saglasnosti ili događaja.

M28 Basic obavezno pruža, po jednoj eksplicitno aktivnoj školi:

- `Moja deca` i dozvoljeni osnovni profil za ACTIVE M07 guardian linkove;
- danas/naredne aktivnosti i raspored deteta iz M10;
- read-only istoriju prisustva iz M11;
- sopstvene payer obaveze, evidentirane uplate, kredit i IPS QR instrukciju iz M12;
- samo objavljene komunikacije/automatske notifikacije namenjene actor-u iz M13/M14;
- dozvoljene dokumente i elektronsko prihvatanje iz M15;
- privacy notice/consent zadatke i granularne odluke iz M17;
- Events Light prikaz, prijavu/odjavu povezanog deteta i status iz M16;
- sopstveni profil/dozvoljeni kontakt i aktivne sesije iz M06/M01;
- eksplicitni izbor škole i siguran povratak kroz deep link iz M03/M19.

M28 je `POST_MVP_PRE_PILOT_REQUIRED` i nije uslov za H0 tehnički PASS. Ne uvodi dodatne H0 surface ID-jeve: unapređuje tačno postojeće kataloške površine `P01`–`P08`, koje u H0 imaju Core fallback ponašanje definisano M00/M19 ugovorom. M28 prošireno H1 ponašanje može se kodirati u istoj široj rundi, ali ima zaseban feature state i acceptance; dok nije efektivno, `P01`–`P08` ostaju na H0 fallback-u. Server mora zahtevati svih pet nezavisnih uslova: efektivan M04 `MYSOKOLA_BASIC` entitlement, ACTIVE M28 pilot enrollment, runtime feature flag ON za školu, M05 `portal.mysokola.access`, i aktuelan M07 guardian ili payer subject basis.

Non-goals M28 Basic:

- nalog, login ili direktno dopisivanje deteta;
- otvorena registracija, auto-link po emailu ili „kod škole“ kao pristup;
- cross-school globalna pretraga, finansijski zbir, document export ili Family merge;
- prikaz drugih staratelja, njihovih kontakata, porodičnog grafa ili tuđe payer odgovornosti;
- offline private content ili bilo koji offline business write;
- menjanje attendance zapisa, payment statusa, guardian authority, rasporeda ili Person identiteta;
- kartično/Stripe plaćanje, automatsko knjiženje banke ili automatski refund;
- chat, društveni feed, leaderboard, reklamno praćenje, AI procena deteta;
- safety/health note, nacionalni identifikator ili slike ličnih dokumenata;
- native aplikacija kao poseban backend/source of truth;
- objedinjeni kalendar više škola u Basic verziji. Arhitektura podržava isti globalni account i eksplicitni switch, ali cross-school data projection zahteva budući poseban privacy ugovor i default je OFF.

## 2. Entiteti, polja i relacije

`Identifier` je UUID; `InstantUTC` je TIMESTAMPTZ; `Version` je UInt64 CAS; svi runtime ključevi su English ASCII; UI tekst je i18n. Svaki tenant-bound red ima `school_id` i `UNIQUE(school_id,id)`. FK ka tenant-owned targetu je composite `(school_id,target_id)`; FK ka globalnom M01 account-u je običan account FK, ali command/query obavezno dokazuje njegov aktuelni school access/basis i nikad ga ne tretira kao tenant grant. M28 server projekcije sa PII su envelope-encrypted i nikad se ne šalju telemetry-ju.

### 2.1 `MySokolaPilotEnrollment`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id` | Identifier | NE | School je M04 tenant; unique otvoren enrollment po školi. |
| `status` | enum | NE | `REQUESTED`, `ACTIVE`, `SUSPENDED`, `REJECTED`, `REVOKED`, `EXPIRED`. |
| `requested_by_account_id`, `requested_at` | Identifier, InstantUTC | NE | ACTIVE school OWNER sa `school.portal.pilot.request`; ne aktivira feature. |
| `request_reason_code` | Code64 | NE | Zatvoren rollout reason. |
| `approval_ticket_ref` | string(1..128)? | DA | Obavezan za svaki platform-decided status; ne sadrži PII. |
| `decided_by_platform_account_id` | Identifier? | DA | Obavezno za platform-initiated odluku; null samo za REQUESTED i SYSTEM_CLOCK expiry. Actor ima tačan `platform.portal.pilot.decide` ili `platform.portal.pilot.security_manage` ključ. |
| `decided_at` | InstantUTC? | DA | Obavezno za svaki status osim REQUESTED, uključujući SYSTEM_CLOCK expiry. |
| `activated_at` | InstantUTC? | DA | Vreme prve uspešne aktivacije; jednom postavljeno ostaje immutable. Obavezno ako je enrollment ikada bio ACTIVE. |
| `effective_from`, `effective_until` | InstantUTC?, InstantUTC? | DA | ACTIVE zahteva from; until opcion, ali ako postoji strogo posle from. |
| `ended_at`, `end_reason_code` | InstantUTC?, Code64? | DA | Obavezno za SUSPENDED/REJECTED/REVOKED/EXPIRED. |
| `entitlement_version_at_activation` | Version? | DA | Obavezno kada je ikada aktiviran; nije budući auth dokaz. |
| `version`, `created_at`, `updated_at` | Version/InstantUTC | NE | CAS/server time. |

Partial unique `(school_id) WHERE status IN ('REQUESTED','ACTIVE','SUSPENDED')`. ACTIVE je efektivan samo unutar `[effective_from,effective_until)` i dok svi runtime guardovi i M04 entitlement važe. Enrollment je rollout allowlist, ne role/permission. Svaka promena statusa dopisuje `MySokolaPilotTransition`; mutable status je trenutna projekcija, ne jedina istorija.

Conditional state matrica: REQUESTED ima sva decision/activation/effectivity/end polja null; prvi ACTIVE zahteva platform actor/time/ticket, `activated_at=effective_from`, entitlement version i null end polja; SUSPENDED zahteva prethodnu aktivaciju, `ended_at`+reason i zadržava prethodnu effectivity kao istorijsku current-row metadata-u koja više nije grant; reaktivirani ACTIVE postavlja novi `effective_from`, čisti end polja i ne menja prvi `activated_at`; REJECTED zahteva platform actor/time/ticket+end polja i nema activation/entitlement; REVOKED zahteva platform security actor/time/ticket+end polja, a activation polja su non-null samo ako je ranije bio ACTIVE; EXPIRED zahteva null platform actor/ticket, system decision/end time+reason i prethodnu aktivaciju. Transition istorija je autoritet za svaku prethodnu suspenziju/reaktivaciju.

### 2.1.1 `MySokolaPilotTransition`

Append-only istorija: `id`, `school_id`, `pilot_enrollment_id`, `transition_no UInt32`, `from_status nullable`, `to_status`, `actor_account_id nullable`, `actor_domain SCHOOL|PLATFORM|SYSTEM_CLOCK`, `reason_code`, `ticket_ref nullable`, `effective_from nullable`, `effective_until nullable`, `entitlement_version nullable`, `request_id`, `occurred_at`, `row_hash`, `previous_row_hash nullable`. Unique `(school_id,pilot_enrollment_id,transition_no)` i `(school_id,pilot_enrollment_id,request_id)`. UPDATE/DELETE nisu aplikaciono dozvoljeni; korekcija je nova transition odluka. `SYSTEM_CLOCK` je dozvoljen samo za ACTIVE/SUSPENDED → EXPIRED, zahteva null `actor_account_id` i deterministic system request ID; SCHOOL/PLATFORM zahtevaju non-null actor.

### 2.2 `MySokolaPreference`

`id`, `school_id`, `account_id`, `default_guardian_child_link_id nullable`, `locale`, `timezone_display_mode SCHOOL|DEVICE`, `compact_cards boolean`, `last_safe_portal_route_key nullable`, `status ACTIVE|ARCHIVED`, `archived_at nullable`, `version`, `created_at`, `updated_at`. Partial unique `(school_id,account_id) WHERE status='ACTIVE'`; `archived_at` je null iff ACTIVE i non-null iff ARCHIVED. Default child link mora biti aktuelan M07 link tog account-a/škole pri set i svakom read-u; po revoke-u se preference ne koristi i background cleanup je best-effort, ne security guard. Ne čuva child ime, finansije ili search istoriju.

### 2.3 `MySokolaHomeProjection`

Replaceable server-side read model, nikad source of truth: `id`, `school_id`, `account_id`, `context_version`, `authorization_version`, `guardian_basis_version_set_hash`, `payer_basis_version_set_hash`, `source_position_set jsonb`, `projection_schema_version`, `generation_no UInt64`, `payload_ciphertext nullable CiphertextEnvelopeV1`, `payload_hash nullable CHAR(64)`, `freshness_status FRESH|STALE|UNAVAILABLE|INVALIDATED`, `missing_source_codes text[]`, `invalidation_reason_codes text[]`, `generated_at`, `hard_expires_at` (najviše 5 min), `invalidated_at nullable`, `version`. Unique `(school_id,account_id,context_version,authorization_version,projection_schema_version,generation_no)`; partial unique current `(school_id,account_id,context_version,authorization_version,projection_schema_version) WHERE freshness_status IN ('FRESH','STALE','UNAVAILABLE')`. UNAVAILABLE zahteva null payload/hash, null invalidated time, najmanje jedan zatvoren missing-source code i praznu invalidation listu; FRESH/STALE zahtevaju payload/hash, obe reason liste prazne i null invalidated time. INVALIDATED zahteva `invalidated_at`, null payload/hash, praznu missing-source listu i najmanje jedan zatvoren security/source-version invalidation code; historical private payload se kriptografski/bezbedno uklanja, a metadata ostaje samo po M17 retention-u.

`source_position_set` je zatvorena schema: niz `{owner_module,stream_key,contiguous_sequence_no,schema_version,owner_barrier_hash}` bez display/PII/business vrednosti. `payload_hash` je tačno SHA-256 nad celim randomizovanim ciphertext envelope byte nizom i služi object/integrity proveri, ne identity linking-u ili plaintext fingerprint-u. Envelope AAD vezuje `M28`, `MySokolaHomeProjection`, field, `school_id`, `id`, `account_id`, context/auth verzije, projection schema i generation. Authentication/hash mismatch, unknown envelope/key verzija ili AAD iz drugog reda/tenant-a daje `M28_OWNER_SOURCE_UNAVAILABLE`, invalidaciju i security incident; nema pokušaja rendera ili global/plaintext fallback-a. Rebuild enkriptuje novom aktivnom tenant key verzijom i tek zatim atomarno invalidira prethodni current red; stari key ostaje dostupan samo do bezbednog purge-a svih referenci.

Payload je zatvoren schema: dozvoljeni section descriptors, opaque subject/resource ID-jevi, minimalni display labeli, business status/količine i next-action route key-evi. Nema kontakta druge odrasle osobe, guardian grafa, health podatka, dokument/message sadržaja, bank reference, raw provider payload-a ili cross-school podatka. Projection se koristi tek posle request-time guardova i poređenja svih verzija; mismatch/unknown source znači `INVALIDATED|UNAVAILABLE`, nikad stale private render.

### 2.4 `MySokolaOnboardingProjection`

Derived/replaceable: `id`, `school_id`, `account_id`, `context_version`, `authorization_version`, `subject_scope_hash`, `guardian_basis_version_set_hash`, `required_task_set_version`, `business_status NOT_STARTED|ACTION_REQUIRED|COMPLETE|BLOCKED`, `projection_status CURRENT|INVALIDATED`, `task_refs_ciphertext nullable CiphertextEnvelopeV1`, `task_refs_hash nullable CHAR(64)`, `blocker_codes text[]`, `invalidation_reason_codes text[]`, `source_version_set_hash`, `projection_schema_version`, `generation_no UInt64`, `generated_at`, `hard_expires_at` najviše 5 min, `invalidated_at nullable`, `version`. Unique generation tuple kao HomeProjection i partial unique jedan CURRENT za isti context/auth/subject/schema. CURRENT zahteva task ciphertext/hash, null invalidated time i praznu invalidation listu; `blocker_codes` je non-empty tačno za business status BLOCKED, a prazan za ostala tri stanja. INVALIDATED zahteva null task payload/hash, non-null invalidated time, praznu blocker listu i najmanje jedan zatvoren invalidation reason. Task ref sadrži samo owner module/type/opaque ID/decision kind/route; pravni tekst, hash i dokaz ostaju M15/M17. `COMPLETE` znači da trenutno nema obaveznog nerešenog zadatka za taj exact subject scope; nije blanket pravna potvrda za buduće verzije.

`task_refs_hash` je SHA-256 randomizovanog envelope byte niza. Envelope AAD vezuje modul/entity/field, `school_id`, `id`, `account_id`, context/auth/subject/source/task-set/schema/generation vrednosti; kopija između naloga, scope-a, generacija ili škola ne prolazi authentication. Hard-expired CURRENT red se ne dekriptuje/renderuje: u istoj fenced rebuild proceduri postaje INVALIDATED bez payload-a ili se vraća `UNAVAILABLE` dok nova generation nije spremna.

### 2.5 `MySokolaCommandReceipt`

Samo za M28-owned komande (pilot request/lifecycle, system expiry i preference): `id`, `school_id`, `actor_type USER|SYSTEM`, `actor_account_id nullable`, `actor_scope_key Code128`, `command_name`, `idempotency_key_hash`, `request_hash`, `outcome SUCCEEDED|REJECTED`, `result_ref nullable`, `response_digest`, `created_at`, `expires_at` najmanje 30 dana. Unique `(school_id,actor_scope_key,command_name,idempotency_key_hash)`. USER zahteva non-null account i `actor_scope_key='ACCOUNT:'+lower(uuid)`; SYSTEM zahteva null account, `actor_scope_key='SYSTEM'` i tačno allow-listed `ExpireMySokolaPilot`. Time se ne oslanja na SQL UNIQUE semantiku nullable kolone. SUCCEEDED zahteva result ref, REJECTED ga ima null. Owner poslovna komanda vraća receipt svog modula; M28 ga ne kopira kao drugi autoritet.

### 2.6 Relacije i zabrana paralelnog modela

| M28 podatak | Vlasnički autoritet | M28 sme | M28 ne sme |
|---|---|---|---|
| account/session | M01 | prikaz sopstvenih aktivnih sesija i revoke komanda kroz M01 | drugi account, sopstveni auth token storage |
| school/context | M04/M03 | list dozvoljenih škola i eksplicitni switch | Organization kao pristup, dva aktivna tenanta u jednom private response-u |
| child/person | M06/M07 | minimalni guardian-linked read | kopija Person/guardian graph-a ili Payer kao guardian |
| schedule/attendance | M10/M11 | child-scoped read | write/correction/offline queue za roditelja |
| finance | M12 + M07 payer basis | sopstveni billing scope, IPS instruction, dozvoljeni apply-credit command | zbir više škola, optimistic PAID, card checkout |
| communication/notification | M13/M14 | objavljeno/current-recipient | draft, recipient lista, poruka tuđeg subjecta |
| document/evidence/consent | M15/M17 | autorizovani read i owner decision coordinator | local file cache, objedinjena „GDPR saglasnost“, M28 evidence |
| event | M16 (+M12 coordinator kada fee postoji) | view/register/cancel linked child | direktan table write ili frontend M16→M12 orkestracija |

## 3. Poslovna pravila, invarianti i edge cases

1. Dete nema `UserAccount`, Session, portal role ili login. Portal actor je uvek odrasli M01 account povezan preko M06 Person i M07 basis-a.
2. Pristup je invite-only. Email/telefon su kontakt, nikad account/person/guardian auto-link ključ.
3. Svaki private request prolazi: M01 session → M03 exact School/context_version → M04 ACTIVE School + `MYSOKOLA_BASIC` entitlement → ACTIVE M28 pilot enrollment + runtime flag → M05 exact permission → M07 current guardian/payer basis → owner resource/subject guard → pre-serialization version recheck.
4. `portal.mysokola.access` otvara samo shell. Nijedan business section nije vidljiv bez odgovarajućeg owner permission-a i basis-a. GUARDIAN nije PAYER; PAYER nije GUARDIAN.
5. Pre izbora škole Global Home prikazuje samo dozvoljene school/workspace opcije, bez child imena, brojeva, obaveza, poruka ili rasporeda. Nakon switch-a response-i stare škole se odbacuju po `context_version` pre rendera.
6. Basic radi u jednoj aktivnoj školi. Ne sabira niti sortira privatne elemente više škola u istom payload-u. Account može eksplicitno menjati školu bez novog naloga.
7. `ListMyChildren` prvo filtrira ACTIVE M07 linkove, pa resolve-uje minimalni M06 prikaz. Revoke/termination odmah uklanja novu dostupnost; cache/outbox nije security autoritet.
8. Payer-only actor dobija samo M12 finansijski subject koji njegov ACTIVE M07 payer link dozvoljava. Ne dobija child profil, schedule, attendance, documents, event ili communication čak i kada obligation referencira dete.
9. Finance prikaz razlikuje `amount_due`, evidentirane uplate, alokacije i `available_family_credit`; nema hidden FX konverzije, float-a ili zbiranja različitih valuta. Nedokaziv obavezni M12 source je `UNAVAILABLE`, ne nula/PARTIAL iznos. IPS QR je instrukcija, ne dokaz uplate.
10. M13 prikazuje samo PUBLISHED komunikaciju čiji current recipient/subject guard prolazi. Draft, withdrawn sadržaj prema owner pravilu i tuđa recipient lista nisu dostupni. Delivery ne znači read.
11. M14 prikazuje samo actor-ove notifikacije sa safe parametrima. Push payload nema ime deteta, iznos, dokument/poruku ili razlog prisustva; otvara deep link koji ponavlja sve guardove.
12. M15 download koristi jednokratni ticket koji izdaje kratku session-bound download sesiju; svaki range ponovo proverava trenutni subject/access. Dokument se ne kešira offline.
13. M15 acceptance i M17 consent odluka ostaju odvojeni. Ugovor/pravilnik može biti `ACCEPTED`, privacy notice `ACKNOWLEDGED`, a foto/video consent zasebno `GRANTED|DECLINED|WITHDRAWN`. Opciono odbijanje ne blokira portal/uslugu.
14. M28 onboarding ne poseduje dokaz. Klik poziva M15/M17 application coordinator i `COMPLETE` se prikazuje tek posle owner receipt-a i osveženog source hash-a.
15. Event registration ili pojedinačno otkazivanje za jedno linked dete poziva po jedan application endpoint. Ako događaj ima fee, neutralni coordinator atomski poziva M16/M12 owner portove; frontend nikad prvo menja registraciju, pa zasebno kreira/otkazuje zaduženje. Guardian cutoff je M16 autoritet. Otkazivanje Event-a odmah uklanja collectible prikaz kroz M12 source barrier iako batch cancellation još radi; plaćeni deo postaje M12 family credit, a spoljni refund nikad nije automatski. Critical odgovor nije finalan bez server receipt-a.
16. M11 prisustvo je parent read-only. Roditelj ne dobija staff offline queue niti komandu correction/lock.
17. Optimistic UI je dozvoljen samo za M28 preference. Mark-read, consent, acceptance, event registration, credit apply i session revoke čekaju server; pending može biti prikazan, ali ne kao finalan success.
18. Private data je network-only u Basic verziji. Service worker kešira samo javne versioned app-shell assete. IndexedDB/Cache Storage ne sadrže child, finance, document, consent, message, event registration ili portal projection payload.
19. Server-side Home/Onboarding projection TTL nije grant. Ako je hard expiry dostignut, AAD/hash ne prolazi ili se auth/context/entitlement/pilot/permission/M07/source verzija ne poklapa, projection se ne dekriptuje/serialize-uje i request vraća safe recovery/error uz fenced invalidaciju/rebuild.
20. Portal queries imaju stable cursor default 20/max 50; owner module limit može biti stroži. Filtriranje/subject guard prethodi count-u, ranking-u i pagination-u.
21. Standardni quick flow cilja najviše tri primarne interakcije samo iz tačno definisanog početnog stanja u `03-M28-SCREEN-TO-COMMAND-I-P01-P08.md`. Multi-child, fee, conflict, pravni sadržaj i nedostajući context su otvoreno brojani izuzeci.
22. Opoziv guardian/payer link-a, membership-a, account-a, entitlement-a, pilot enrollment-a ili feature flag-a važi za svaki request koji počne posle commit-a. High-risk write ponavlja verzije neposredno pre commit-a. Online signal odmah freeze/purge; offline app shell nema private payload koji bi mogao ostati čitljiv.
23. Portal telemetry sadrži route key, result/error code, duration, device/network bucket i rotirajući pseudonim; nikad child/person/resource raw ID, school naziv, iznos, search tekst, dokument/message naslov/sadržaj ili URL parametar.
24. Section failure je izolovan samo kada ne menja bezbednost. `SESSION|TENANT|ENTITLEMENT|PILOT|AUTHORIZATION|SUBJECT` failure zatvara ceo private shell; business owner outage prikazuje `UNAVAILABLE` za tu sekciju bez izmišljene nule.
25. Feature OFF/revoke ne briše owner podatke. On samo onemogućava M28 surface; H0 parent rute ostaju prema njihovom sopstvenom rollout/migration statusu dok `RETIRE_AFTER_MIGRATION` nije dokazano završen.

### 3.1 Obavezni edge cases

| # | Scenario | Deterministički ishod |
|---:|---|---|
| 1 | Account je GUARDIAN u A i PAYER u B | Global Home samo dve school opcije; posle izbora A child sekcije bez B finansija, posle switch-a B samo finance scope bez A child podatka. |
| 2 | Dvoje povezane dece, event prihvata samo jedno | UI nudi samo eligible dete; server ponavlja M07/M16 guard. Skriveno dete ne ulazi u count. |
| 3 | Guardian link se opozove dok je child page otvoren | Sledeći request/pre-serialization check safe 404; online signal freeze/purge; nema child labela u erroru. |
| 4 | Payer vidi obligation koji posredno pripada detetu bez guardian prava | Prikazuje samo M12 billing subject/obavezu; nema child profile deep link-a, attendance ili schedule-a. |
| 5 | IPS QR je otvoren, banka kasnije primi uplatu | QR ostaje instrukcija; UI ne kaže PAID dok M12 PaymentRecord/Allocation nije server-confirmed. |
| 6 | Consent document dobije novu published verziju | Onboarding postaje ACTION_REQUIRED samo po M15/M17 applicability pravilima; stari evidence ostaje immutable. |
| 7 | Opciono foto consent je DECLINED | Portal i neophodne usluge rade; foto processing ostaje deny. |
| 8 | Dva guardian-a istovremeno odlučuju uz ANY_DECLINE_BLOCKS | M17 deterministički prioritet važi; M28 ne radi last-write-wins. |
| 9 | Event registracija i capacity poslednje mesto se trkaju | M16 lock/CAS daje jednom potvrdu; drugi dobija tačan conflict, bez M12 orphan zaduženja. |
| 10 | M12 source barrier ima gap | Finance section `UNAVAILABLE`; nema headline total-a. |
| 11 | Deep link iz push-a vodi cross-tenant/ukinutom dokumentu | M19 bound intent + svi guardovi; neutralan safe fallback bez existence oracle-a. |
| 12 | Service worker je offline | Otvara samo javni shell sa online-required stanjem; nema prethodnih private kartica/iznosa/imena. |
| 13 | Pilot enrollment istekne usred sesije | Svaki novi request deny; visokorizična komanda pre commit-a failuje/rollback; owner podaci ostaju. |
| 14 | Preference pokazuje na revoked child link | Ignoriše se i bezbedno bira prvi aktuelni link/empty state; stale ID se ne resolve-uje u label. |
| 15 | Jedan owner query kasni, a context se promeni | Ceo stari response odbačen po context_version; nema jednog frame-a stare škole. |
| 16 | Guardian otkaže fee registraciju, a M12 write padne | UI dobija neuspeh; ni M16 status ni M12 obaveza/credit se ne menjaju. |
| 17 | Škola otkaže događaj dok M12 batch kasni | Event je odmah CANCELLED; finance prikaz ne nudi plaćanje/reminder i pokazuje neutralno „obrada otkazivanja”, bez lažnog duga ili obećanog refund-a. |
| 18 | Uplata stigne posle otkazivanja događaja | M12 može potvrditi stvarno primljen novac samo na payer account-u; ne alocira ga otkazanoj obavezi i knjiži raspoloživ credit jednom. |

## 4. Tenant & Security Guard

- Svaki M28 red i projection nosi `school_id`; composite FK i unique sprečavaju da pilot/preference/projection spoje account/resource druge škole. Globalni M01 account nije tenant grant.
- M03 context se uzima samo sa servera. `school_id` iz URL/body/headera je hint koji mora tačno odgovarati aktivnom context-u; ne bira tenant samostalno.
- Existing cross-tenant, hidden child/payer/document/event/message i nepostojeći ID vraćaju isti `M28_NOT_FOUND_SAFE` oblik i ekvivalentnu cache/timing klasu. 403 se koristi samo za poznatu same-tenant surface čije postojanje actor sme da zna.
- Child query zahteva ACTIVE M07 guardian basis za exact child. Finance query zahteva ACTIVE payer basis za exact M12 billing scope. Unija role dozvola ne spaja subject scope-ove.
- Support nema portal impersonation, trajni shadow account ili default M28 pravo. Standardni M05 support grant ne otkriva child/finance/document/message/consent sadržaj. Break-glass ne postaje guardian/payer i ne može doneti pravnu odluku ili event registration u ime porodice.
- Private HTTP response je `Cache-Control: no-store` osim izričite server-side encrypted projection; browser/proxy/service-worker ga ne skladišti. Signed URL/ticket nije trajni bearer i nije u referrer/logu.
- CSP, output encoding, CSRF zaštita cookie komandi, same-origin service-worker scope i allow-list route parametri su obavezni. Rich text se renderuje sanitizer-om vlasničkog modula; M28 ne uvodi svoj HTML bypass.
- Audit/outbox/receipt nose opaque ID/status/version/reason/correlation, bez child imena, iznosa, sadržaja, kontakta ili raw consent odgovora. Security deny audit ne potvrđuje da target postoji.
- Rate limit je per tenant+account+operation uz neutralan response; ne pravi cross-tenant count/timing oracle.
- Data export nije M28 generička akcija. M17 DSAR i vlasnički export ugovori ostaju jedini dozvoljeni tokovi.

## 5. Lifecycle & transitions

### 5.1 `MySokolaPilotEnrollment`

| From | Komanda/uslov | To | Guard/efekat |
|---|---|---|---|
| — | `RequestMySokolaPilot` | REQUESTED | ACTIVE School OWNER, entitlement može još nedostajati; request nije aktivacija. |
| REQUESTED | `ActivateMySokolaPilot` | ACTIVE | `platform.portal.pilot.decide`+step-up+ticket, efektivan entitlement, runtime flag konfigurabilan; version bump/cache invalidation. |
| REQUESTED | `RejectMySokolaPilot` | REJECTED | `platform.portal.pilot.decide`, reason+ticket; terminalno. |
| ACTIVE | `SuspendMySokolaPilot` | SUSPENDED | `platform.portal.pilot.security_manage`, step-up+security reason+ticket; odmah deny novih request-a. |
| SUSPENDED | `ReactivateMySokolaPilot` | ACTIVE | `platform.portal.pilot.decide`, svi uslovi ponovo dokazani, nova effective_from/version; novi append-only transition, stari razlog suspenzije ostaje dokaziv. |
| REQUESTED/ACTIVE/SUSPENDED | `RevokeMySokolaPilot` | REVOKED | `platform.portal.pilot.security_manage`, reason+step-up+ticket+audit; terminalno. |
| ACTIVE/SUSPENDED | `effective_until <= database_now` | EXPIRED | M21 `portal.pilot_enrollment_expiry`/read-time guard; terminalno. |
| REJECTED/REVOKED/EXPIRED | bilo šta | — | novi rollout zahtev je novi red. |

### 5.2 Preference, projections i onboarding

| Entitet | From | Događaj | To |
|---|---|---|---|
| Preference | — | Set valid self preference | ACTIVE |
| Preference | ACTIVE | Update expected version | ACTIVE v+1 |
| Preference | ACTIVE | Account/school disposition | ARCHIVED |
| HomeProjection | — | Build posle svih guardova | FRESH ili UNAVAILABLE |
| HomeProjection | FRESH | freshness prag pređe, sources kompletni | STALE |
| HomeProjection | bilo koji | auth/context/basis/source version mismatch | INVALIDATED |
| HomeProjection | STALE/UNAVAILABLE/INVALIDATED | potpuni rebuild pod novim verzijama | prethodni current atomarno → INVALIDATED, `generation_no+1` postaje novi FRESH/UNAVAILABLE red |
| OnboardingProjection | — | derive | CURRENT red sa NOT_STARTED/ACTION_REQUIRED/COMPLETE/BLOCKED |
| OnboardingProjection | CURRENT | owner evidence/task/auth/basis/version promena | stari red INVALIDATED bez payload-a; nova generation CURRENT sa izvedenim business statusom |

Terminalni su pilot `REJECTED|REVOKED|EXPIRED`, Preference `ARCHIVED` i svaki projection `INVALIDATED` red. Projection rebuild pravi novu generation/red; ne menja owner podatak i ne zadržava invalidirani private payload.

## 6. Error Catalog

| Code | HTTP | Značenje |
|---|---:|---|
| `M28_UNAUTHENTICATED` | 401 | M01 session nije validna. |
| `M28_CONTEXT_REQUIRED` | 409 | Nema aktivne škole/M03 context-a. |
| `M28_CONTEXT_STALE` | 409 | `context_version` se promenio. |
| `M28_NOT_FOUND_SAFE` | 404 | Nepostojeći, cross-tenant ili skriven subject/resource. |
| `M28_FORBIDDEN` | 403 | Poznata same-tenant surface/action nema permission. |
| `M28_ENTITLEMENT_REQUIRED` | 403 | `MYSOKOLA_BASIC` nije efektivan; ne govori ništa o child/resource-u. |
| `M28_PILOT_NOT_ACTIVE` | 403 | Škola nije u aktivnom pilot allowlist stanju. |
| `M28_FEATURE_DISABLED` | 403 | Runtime flag je OFF/kill-switched. |
| `M28_SUBJECT_BASIS_REQUIRED` | 403 | Nema nijedan važeći guardian/payer portal basis. |
| `M28_OWNER_SOURCE_UNAVAILABLE` | 503 | Obavezni owner read nije bezbedno dostupan. |
| `M28_PROJECTION_STALE` | 409 | Projection source/auth digest nije aktuelan; rebuild/retry. |
| `M28_FINANCE_UNAVAILABLE` | 503 | M12 kompletan finansijski presek nije dokaziv. |
| `M28_ONLINE_REQUIRED` | 409 | Private read/business action nije dozvoljena offline. |
| `M28_IDEMPOTENCY_CONFLICT` | 409 | Isti key, drugačiji canonical payload. |
| `M28_VERSION_CONFLICT` | 409 | Expected version/CAS konflikt. |
| `M28_PILOT_TRANSITION_INVALID` | 409 | Lifecycle prelaz nije dozvoljen. |
| `M28_VALIDATION_FAILED` | 422 | Field/route/enum/conditional-null ugovor ne prolazi. |
| `M28_RATE_LIMITED` | 429 | Actor/tenant/operation limit. |
| `M28_INTERNAL_SAFE` | 500 | Neočekivana greška bez stack/PII leak-a. |

Owner komanda zadržava namespaced owner error. M28 BFF ga mapira samo na dokumentovano safe UI stanje; ne pretvara conflict u success i ne otkriva skriven resurs.

## 7. API, idempotency i concurrency

### 7.1 M28-owned queries

| Query | Obavezan input | Output i granice |
|---|---|---|
| `BootstrapMySokola` | važeća session; opciono current context | neutralne school opcije bez private count-a ili kompletan single-school portal envelope; capability/auth/context digests |
| `ListMyPortalSchools` | session | samo škole sa efektivnim portal access path-om; bez child/finance/count podataka |
| `GetMySokolaHome` | context_version | autorizovane section envelope; svaki section je jedan od `AVAILABLE`, `EMPTY`, `STALE`, `UNAVAILABLE`, bez `FORBIDDEN` existence indikatora |
| `ListMyChildren` | context, cursor | samo ACTIVE guardian-linked children; default20/max50 |
| `GetMyChildOverview` | guardian_child_link_id | minimalni M06/M07 + quick owner summaries; bez health/contact drugih lica |
| `GetMySchedule` | child basis, `[start_local,end_exclusive_local)` max 62 dana | M10 child projection u school IANA zoni |
| `GetMyAttendance` | child basis, period/cursor | M11 read-only status; bez staff correction metadata |
| `ListMyBillingScopes` | payer basis | M12 minimalni billing scopes, valuta odvojeno |
| `GetMyFinanceSummary` | billing scope/period | M12 amount_due/payments/allocations/credit/IPS instruction + source freshness |
| `ListMyCommunications` | actor/current subject, cursor | samo M13 published/current recipient items |
| `ListMyNotifications` | actor, cursor | M14 user projection, safe params |
| `ListMyDocuments` | exact M15 scope, cursor | metadata samo; download zaseban ticket/session |
| `GetMyOnboardingTasks` | subject scope | derived M15/M17 task refs/status |
| `ListMyEvents` | child basis/period/cursor | M16 visible/eligible projection; fee status iz coordinator read-a |
| `GetMyProfileAndSessions` | self | minimalni M06 self profile/contact + M01 active session metadata; bez credential-a |

### 7.2 M28-owned commands

`RequestMySokolaPilot`, `ActivateMySokolaPilot`, `RejectMySokolaPilot`, `SuspendMySokolaPilot`, `ReactivateMySokolaPilot`, `RevokeMySokolaPilot`, system-only `ExpireMySokolaPilot`, `SetMySokolaPreference`, `ArchiveMySokolaPreference`. Svaka koristi `Idempotency-Key=request_id`, canonical request hash, expected version gde target postoji, M28 receipt, audit i outbox u istoj lokalnoj transakciji. Isti key+hash vraća isti rezultat; isti key+drugi hash je 409. Pilot transition zaključava School enrollment red; partial unique/CAS daje jednog pobednika. System expiry request ID je deterministički `school_id:enrollment_id:effective_until`, actor je SYSTEM bez izmišljenog account-a.

### 7.3 Portal application commands čiji owner nije M28

| Portal endpoint | Owner komanda/coordinator | Garancija |
|---|---|---|
| `SelectMyPortalSchool` | M03 `SelectTenantContext` | atomarno nova context_version; purge stare škole pre rendera |
| `MarkCommunicationRead` | M13 owner command | samo current recipient; owner receipt |
| `MarkNotificationRead` | M14 owner command | samo recipient; owner receipt |
| `RequestDocumentDownload` / range | M15 ticket/session | svaki range reautorizovan; no-store |
| `SubmitDocumentDecision` | M15 owner ili M15/M17 evidence coordinator | tačan ACCEPT/ACK/DECLINE tip; nema bundled consent-a |
| `SubmitConsentDecision` | M17 + M15 evidence coordinator | granularno GRANT/DECLINE/WITHDRAW, jedan local commit |
| `RegisterMyChildForEvent` | M16 ili neutralni M16+M12 coordinator | jedan BFF request, all-or-nothing kada fee postoji |
| `CancelMyChildEventRegistration` | M16 owner ili neutralni M16+M12 coordinator kada fee assessment postoji | M16 cutoff/guardian recheck; free cancellation ili M16 CANCELLED + svi M12 assessment obligations/credit efekti u jednom commit-u; nema automatskog spoljnog refund-a |
| `ApplyMyFamilyCredit` | M12 `ApplyFamilyCredit` | online, ledger append-only, expected versions |
| `RevokeMySession` | M01 revoke command | sopstvena/target session semantika M01 |

Frontend ne poziva owner module sekvencijalno radi jedne atomske poslovne namere. Application coordinator koristi javne owner portove u istoj lokalnoj transakciji modularnog monolita, stabilan lock redosled i jedan response; M28 nema direktan table access.

### 7.4 Concurrency i response binding

- Svaki private response nosi `school_id`, `context_version`, `authorization_version`, relevantni subject/source version hash i `generated_at`; client odbacuje mismatch pre rendera.
- High-risk portal endpoint ponavlja session/context/entitlement/pilot/permission/basis/owner versions neposredno pre commit-a.
- Parallel child event registration/cancellation, credit apply, consent ili mark-read koristi owner unique/CAS/idempotency; fee cancellation prati globalni Event→Registration→M12 lock redosled; M28 ne uvodi last-write-wins.
- Home rebuild ima lease/fencing; samo najnoviji worker može publish-ovati projection za exact version tuple. Duplicate owner event se dedupe-uje preko M21 InboxReceipt.
- Timeout posle owner commit-a rešava se owner idempotency receipt-om; M28 ne šalje novu business nameru sa novim ključem automatski.

## 8. NFR, privacy, audit, migration i acceptance

Referentni profil `SOKOLA-NFR-MYSOKOLA-V1`: Android 4-core/4GB, viewport 360×800, kontrolisana mreža RTT 150ms/down 1.6Mbps/up 750Kbps/loss 1%; School sa 25.000 participants, actor sa 3 linked children, 2 payer scopes, 100 communications, 100 notifications, 100 documents i 50 visible events; pet Home sekcija u prvom envelope-u; 30 merenih prolaza posle pet warm-up. Ciljevi: authenticated warm Home visible p95≤2.5s, cold p95≤4.0s, school switch p95≤1.2s bez stale frame-a, owner list p95≤500ms za 20, interaction response p95≤800ms bez spoljnog provider outage-a; WCAG 2.2 AA; initial portal route JS gzip≤180KiB iznad shared M19 shell-a. Dokaz sadrži commit/build/config/dataset/browser hash, raw percentile i bundle/a11y report; napisani cilj nije dostignut rezultat.

Audit: pilot request/transition, preference change, owner business command prema owner ugovoru, access revoke security event i download/consent/event/credit/session kritične akcije. Običan Home/list read se ne auditira sa sadržajem; high-risk/sensitive read prati owner policy. Telemetry je §3.23 allow-list.

Migracija H0 `P01–P08` mora pratiti `03-M28-SCREEN-TO-COMMAND-I-P01-P08.md`. Stara ruta se ne uklanja dok deep link, back button, permission, a11y, analytics-redaction i rollback test nisu prošli. Nema dve write putanje sa različitom semantikom. Brownfield klasifikacija je `PRESERVE|ADAPT|IMPLEMENT|REMOVE_CONFLICT`; validan H0 owner UI može se reuse-ovati unutar M28 shell-a bez big-bang rewrite-a.

Pre-pilot acceptance zahteva: feature/entitlement/pilot/permission/basis petostruki guard; dva tenanta; guardian i payer odvojeno; revoke races; multi-child; explicit school switch; finance truth/IPS; published-only communication; M15/M17 evidence; document session; event fee create/cancel atomicity i event-cancel barrier; offline no-private-cache; deep link; active session revoke; WCAG/mobile/NFR evidence; P01–P08 migration/rollback; svih 124 M28 QA bez skipped/flaky. Dok repo/migracije/testovi ne postoje, status ostaje `SPEC_CANDIDATE`, ne `IMPLEMENTED` ili pilot `GO`.
