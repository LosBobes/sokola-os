---
tip: modulni-implementacioni-ugovor
modul-id: M19
naziv: Dashboard, navigacija, globalna pretraga i PWA shell
status: SPEC_CANDIDATE
revizija: "1.7"
datum: 2026-09-15
schema-zavisnosti: [M04]
read-portovi: [M01, M03, M04, M05, M06, M07, M08, M09, M10, M11, M12, M13, M14, M15, M16, M17, M18]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M20, M21, M28]
offline-policy: ALLOW_M11_TRANSPORT_ONLY
horizont: H0_MVP_REQUIRED
---

# M19 — Dashboard, navigacija, globalna pretraga i PWA shell

## 1. Cilj i granice

M19 je zajednički web/PWA shell koji sastavlja autorizovani početni ekran, navigaciju, izbor prikaznog workspace-a, globalnu pretragu, deep-link resolution, instalacioni/update tok, minimalni cache i transport jedinog H0 offline write toka iz M11. Omogućava da standardna akcija bude dostupna za najviše tri osnovne interakcije bez skrivanja obavezne potvrde.

M19 nije authorization autoritet, ne poseduje session/tenant/role/Person/guardian/poslovni podatak, ne menja izvore drugih modula i ne računa M18 metrike. Prikazni workspace ne sužava niti proširuje M05 efektivnu uniju prava. Search rezultat, route, UI visibility, cache, JWT claim ili organization membership nisu dokaz pristupa.

H0 navigation manifest i dashboard composition implementiraju tačno 42 površine iz [[../00-M00-OBIM-I-ARHITEKTURA/04-M00-H0-SCREEN-CATALOG-42]]. M19 sme menjati responsive prezentaciju i redosled prema permission-u, ali ne značenje UI ID-ja, domain owner, offline politiku ili H0 zbir.

Non-goals: native aplikacija; proizvoljan dashboard builder; offline finansije/dokumenti/saglasnosti/događaji/RBAC; globalna cross-school pretraga; indeks dokumenta/poruke/health/finance sadržaja; biometrija/geolokacija; tracking za marketing; third-party search SaaS u H0; silent service-worker update usred mutacije; automatsko izvršenje command-bar radnje; M28 pilot lifecycle, portal projekcije i H1 mySOKOLA ponašanje. M19 ipak poseduje zajednički shell/routing i H0 Core fallback kompoziciju `P01`–`P08`; to nije M28 aktivacija niti paralelni parent domen.

## 2. Entiteti i klijentski ugovori

Svi server ID-jevi su UUID; `*_at` su UTC `TIMESTAMPTZ`; `version` je `BIGINT >=1`. Polje je obavezno osim kada piše nullable. UI tekst je isključivo i18n (`sr-Latn`, `sr-Cyrl`, `hr`, `en` najmanje); runtime identifikatori su English ASCII. Aggregate/command tenant red sa surrogate `id` ima `school_id`, `UNIQUE(school_id,id)` i kompozitni tenant integritet; keyed search/checkpoint/receipt bez `id` ima eksplicitni kompozitni PK/UNIQUE koji počinje sa `school_id` i nijedan tenant-less lookup.

### 2.1 `ShellPreference`

`id`, `account_id`, `school_id`, `preferred_workspace_key`, `locale`, `timezone_display_mode enum(SCHOOL,DEVICE)`, `density enum(COMFORTABLE,COMPACT)`, `reduced_motion boolean`, `last_safe_route_key nullable`, `status ACTIVE|ARCHIVED`, `archived_at nullable`, `version`, `created_at`, `updated_at`. Unique `(account_id,school_id)` za ACTIVE; `archived_at` je null iff ACTIVE. Workspace je preference; M03/M05 ponovo rešavaju dozvoljenost. Nema child/finance/search sadržaja.

### 2.2 `NavigationManifestVersion`

`NavigationManifestVersion`: `id`, `manifest_key`, `version_no`, `workspace_key`, `status DRAFT|PUBLISHED|RETIRED`, `content_hash`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`; unique `(manifest_key,version_no)`. `NavigationManifestItem`: `id`, `manifest_version_id`, `item_key`, `surface_id` iz tačnog M00 kataloga 42 površine, `route_template`, `i18n_key`, `icon_key`, `required_permission_expression`, `required_capability`, `resource_scope_type`, `order_no`, `mobile_primary boolean`; unique `(manifest_version_id,item_key)` i `(manifest_version_id,order_no)`. Više item/detail ruta sme pripadati istoj površini, ali svaki item pripada tačno jednoj. Version i svi item-i postaju immutable jednim publish commit-om. Partial unique dozvoljava najviše jednu PUBLISHED verziju po `(manifest_key,workspace_key)`; publish naslednika atomski retires prethodnika. Manifest određuje prikaz, ne autorizaciju; unknown surface/permission/capability/route ili dupli item/order blokira publish. Release contract proverava da unija PUBLISHED H0 manifesta pokriva svih 42 `surface_id` bez dodatne površine.

### 2.3 `DashboardCompositionVersion`

`DashboardCompositionVersion`: `id`, `composition_key`, `workspace_key`, `version_no`, `status DRAFT|PUBLISHED|RETIRED`, `content_hash`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`; unique `(composition_key,version_no)`. `DashboardWidgetDefinition`: `id`, `composition_version_id`, `widget_key`, `source_query_key`, `required_permission_expression`, `required_capability`, `priority`, `size enum(S,M,L)`, `empty_state_key`, `freshness_contract`; unique `(composition_version_id,widget_key)` i `(composition_version_id,priority)`. Version i widget-i postaju immutable jednim publish commit-om. Partial unique dozvoljava najviše jednu PUBLISHED verziju po `(composition_key,workspace_key)`; publish naslednika atomski retires prethodnika. Widget koristi jedan backend-for-frontend composition query ili owner query; frontend ne radi N+1 fan-out.

`required_permission_expression` je zatvoren JSON AST: leaf je samo `PERMISSION` sa jednim tačnim ključem iz aktivnog M05 registra; kompozitni node je `ALL_OF` ili `ANY_OF` sa 1..16 child node-ova. Dubina je najviše 4, ukupno najviše 32 node-a; prazan, unknown, wildcard, `NOT`, string-script i proizvoljan kod su zabranjeni. `required_capability` je tačno jedan aktivan M04 capability ključ ili literal `NONE`, nikad nullable guess. Publish validira i hashira canonical AST; shell ga koristi samo za visibility, dok svaki endpoint ponavlja server authorization.

### 2.4 `SearchDocument`

Purpose-limited current projekcija: `school_id`, `entity_type enum(PARTICIPANT,GUARDIAN,STAFF,GROUP,PROGRAM,LOCATION,EVENT)`, `entity_id`, `source_version`, `display_label_ciphertext nullable`, `display_label_encryption_key_version nullable UInt32`, `secondary_label_ciphertext nullable`, `secondary_label_encryption_key_version nullable UInt32`, `normalized_search_tokens_ciphertext_or_protected_index nullable`, `protected_index_version nullable UInt32`, `protected_index_key_version nullable UInt32`, `exact_contact_hmac nullable`, `exact_contact_hmac_key_version nullable UInt32`, `status ACTIVE|TOMBSTONED`, `search_policy_version`, `updated_at`. Unique `(school_id,entity_type,entity_id)`. ACTIVE zahteva display label, protected tokens i njihove key/schema verzije; svako ciphertext/HMAC polje je null ili non-null zajedno sa svojom key verzijom. TOMBSTONED zahteva sva label/token/contact i key-version polja null. Nema DOB, health, consent, finance, document/message body, bank/reference, guardian graph ili raw email/phone. `exact_contact_hmac` je tenant-keyed i dozvoljen samo posebno ovlašćenom admin search-u; rezultat nikad ne prikazuje sirov kontakt kao sugestiju.

`SearchDocumentScopeBinding`: `school_id`, `entity_type`, `entity_id`, `scope_dimension_type enum(SCHOOL_WIDE,SCHOOL_MEMBERSHIP,PARTICIPANT_PROFILE,GROUP,PROGRAM,LOCATION,STAFF_ASSIGNMENT,GUARDIAN_LINK)`, `scope_dimension_id`, `source_version`, `created_at`; unique `(school_id,entity_type,entity_id,scope_dimension_type,scope_dimension_id)` i composite FK `(school_id,entity_type,entity_id)` ka SearchDocument-u. ACTIVE dokument mora imati kompletan, ne-prazan binding skup izveden iz tačno iste owner verzije; TOMBSTONED dokument nema nijedan binding. `SCHOOL_WIDE` zahteva `scope_dimension_id=school_id`, dozvoljen je samo za owner-policy tip koji ima tenant-wide view permission i zabranjen je kao prečica za participant/guardian subject guard. Polimorfni dimension target nema lažni SQL FK: M19 consumer pre commit-a obavezno poziva odgovarajući typed owner batch-read port i dokazuje isti `school_id`, dozvoljen tip i aktuelnu source verziju. Neuspešna ili nepoznata provera daje QUARANTINED receipt i ne menja current dokument/binding.

`SearchProtectionKeyState`: `school_id`, `purpose enum(PROTECTED_TOKEN_INDEX,EXACT_CONTACT)`, `state STABLE|PREPARING|DUAL_READ|CUTOVER`, `write_key_version UInt32`, `read_key_versions UInt32[]`, `previous_key_version nullable UInt32`, `rotation_started_at nullable`, `cutover_at nullable`, `version`, `updated_at`; unique `(school_id,purpose)`. Key material nije u tabeli. STABLE ima tačno jedan read key jednak write key-u i null rotation polja. PREPARING/DUAL_READ imaju tačno dva različita read ključa `[previous,write]`, non-null previous/start i null cutover. CUTOVER ima samo novi write key u read skupu, zadržava previous/start i zahteva cutover vreme dok traje kontrolisani rollback prozor. Svaka verzija mora postojati u tenant-bound managed key registry-ju.

H0 search index mora biti u istoj kontrolnoj granici kao aplikacioni podaci, enkriptovan at rest i bez slanja third-party search servisu. Ako stack ne podržava zaštićen fuzzy index, koristi tenant-particionisan DB search sa minimalnom projekcijom; tehnička realizacija je slobodna, garancija nije.

### 2.5 `SearchProjectionCheckpoint`

`SearchProjectionCheckpoint`: `school_id`, `entity_type`, `source_high_watermark`, `status HEALTHY|LAGGING|REBUILDING|FAILED`, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token UInt64`, `started_at`, `completed_at nullable`, `failure_code nullable`, `version`, `updated_at`; unique `(school_id,entity_type)`. REBUILDING jedini ima lease hash/until i nema completed time; HEALTHY/LAGGING zahtevaju completed time i bez failure-a; FAILED zahteva completed time+failure code.

`SearchProjectionReceipt`: append-only `school_id`, `entity_type`, `entity_id`, `source_version`, `source_event_id`, `payload_hash`, `outcome APPLIED|IGNORED_STALE|QUARANTINED`, `failure_code nullable`, `processed_at`; unique `(school_id,source_event_id)` i `(school_id,entity_type,entity_id,source_version)`. `failure_code` je non-null iff QUARANTINED. Isti event/version sa drugim hash-em je integrity incident. Receipt, a ne SearchDocument current row, dokazuje dedupe; out-of-order stara verzija ne oživljava tombstone.

### 2.6 `DeepLinkIntent`

Kratkotrajan server-side zapis: `id`, `binding_type enum(PRE_AUTH_BROWSER,AUTHENTICATED_SESSION)`, `browser_nonce_hash nullable`, `session_id nullable`, `account_id nullable`, `target_route_key`, `opaque_target_ciphertext nullable`, `target_encryption_key_version nullable UInt32`, `expected_school_hint_hmac nullable`, `school_hint_hmac_key_version nullable UInt32`, `created_at`, `expires_at` (najviše 10 min), `bound_at nullable`, `consumed_at nullable`, `rejected_reason_code nullable`, `status PRE_AUTH_PENDING|AUTH_BOUND_PENDING|CONSUMED|EXPIRED|REJECTED`, `version`.

Conditional-null ugovor je obavezan:

- `PRE_AUTH_BROWSER` zahteva `browser_nonce_hash`, a zabranjuje `session_id`, `account_id` i bilo kakvo resolve-ovanje ciljnog resursa;
- `AUTHENTICATED_SESSION` zahteva `session_id` i `account_id`, a zabranjuje `browser_nonce_hash`;
- `opaque_target_ciphertext/target_encryption_key_version` i `expected_school_hint_hmac/school_hint_hmac_key_version` su null/non-null parovi. Pre-auth target koristi platform-scoped, domain-separated deep-link encryption key, a school hint platform-scoped, domain-separated HMAC ključ; nijedan bira tenant ključ niti potvrđuje da škola postoji pre autentifikacije. Posle bind-a hint je samo očekivanje koje se poredi sa server-izvedenim eligible M03 context-om, nikad tenant grant. Plaintext target, raw URL/query, invite/auth token, naziv i PII se ne čuvaju;
- pre-auth intent se posle uspešne prijave atomarno vezuje za tačno novu sesiju i account samo ako se poklope hash jednokratnog browser nonce-a, TTL i allow-list route; isti pre-auth intent se ne može vezati za drugu sesiju;
- tek `AUTH_BOUND_PENDING` intent može jednom da se resolve-uje, nakon M01/M03/M05 i owner subject/resource guardova. Resolve i terminalni `CONSUMED|REJECTED` prelaz su jedna transakcija;
- svaki terminalni `CONSUMED|REJECTED|EXPIRED` prelaz u istom commit-u briše `browser_nonce_hash`, `opaque_target_ciphertext`, `target_encryption_key_version`, `expected_school_hint_hmac` i `school_hint_hmac_key_version`. `target_route_key`, status, vremena i minimalna binding/receipt metadata mogu ostati kao dokaz, ali više ne postoji reverzibilni ciljni identifikator ili school hint.

### 2.7 `PwaInstallation`

`id`, `account_id`, `installation_public_id`, `platform_family`, `app_version`, `last_seen_at`, `status ACTIVE|REVOKED|EXPIRED`, `created_at`, `updated_at`, `revoked_at nullable`, `expired_at nullable`, `version`. ACTIVE zahteva oba terminalna vremena null; REVOKED zahteva samo `revoked_at`; EXPIRED zahteva samo `expired_at`. ACTIVE installation je hard-validna samo dok je `database_now < last_seen_at + 90 dana`; na granici od 90 dana više ne može dobiti privatni shell/cache čak i ako cleanup worker kasni. `last_seen_at` se pomera CAS-om samo posle uspešno autentifikovanog PWA compatibility/heartbeat odgovora i najviše jednom u 24 sata; običan javni asset request ne produžava rok. Nema fingerprinting atributa, child ID-a ni push endpointa; push subscription pripada M14. Jedan public ID je random, rotira se na logout/user switch. REVOKED/EXPIRED su terminalni; novi pristup pravi nov random public ID, ne oživljava stari red.

### 2.8 `ShellCommandReceipt`

Za preference/deep-link/install/config komande: `id`, `account_id nullable`, `actor_type USER|BROWSER|SYSTEM`, `school_id nullable`, `actor_scope_key Code160`, `tenant_scope_key Code80`, `command_name`, `idempotency_key_hash`, `request_hash`, `outcome SUCCEEDED|REJECTED`, `result_ref nullable`, `response_hash`, `created_at`, `expires_at`. Unique `(actor_scope_key,tenant_scope_key,command_name,idempotency_key_hash)`. USER zahteva account i `actor_scope_key='ACCOUNT:'+lower(uuid)`; BROWSER zahteva null account i `actor_scope_key='BROWSER:'+browser_nonce_hmac`, samo za `CapturePreAuthDeepLinkIntent`; SYSTEM zahteva null account i `actor_scope_key='SYSTEM:'+system_identity_key` za allow-listed platform komandu. `tenant_scope_key` je `SCHOOL:<uuid>` samo uz server-validiran context, inače tačno `GLOBAL`; nullable `school_id` nije deo dedupe autoriteta. Raw nonce/system secret se ne čuva. SUCCEEDED zahteva result ref; REJECTED ga ima null. Minimum 30 dana za server commands.

### 2.9 Conditional-null konfiguracija i deep link

- Manifest/Composition DRAFT ima publish/retire actor-vremena null; PUBLISHED zahteva publish par i null retire par; RETIRED zahteva oba para. Item/widget red bez objavljenog parent version-a nije izvršiva konfiguracija.
- PRE_AUTH_PENDING zahteva `binding_type=PRE_AUTH_BROWSER`, nonce hash, a session/account/bound/consumed/rejected polja su null. Uspešan bind atomarno briše nonce, postavlja `binding_type=AUTHENTICATED_SESSION`, session/account/`bound_at` i status AUTH_BOUND_PENDING.
- CONSUMED zahteva `consumed_at` i null rejected reason; REJECTED zahteva zatvoren reason i null consumed time. EXPIRED nema consumed time i ne može biti bindovan/resolve-ovan. `bound_at` ostaje null ako je PRE_AUTH zahtev odbijen/istekao pre login-a, a non-null ako je terminal nastao posle bind-a. Sva tri terminalna statusa zahtevaju null nonce/opaque-target/school-hint polja i njihove key-version parove; DB CHECK sprečava terminalni red koji zadržava taj sadržaj.
- SearchDocument tombstone purge, brisanje svih SearchDocumentScopeBinding redova i corresponding receipt upisuju se atomarno; current row više nema povratni PII token. Reaktivacija zahteva strogo veću source version, ponovnu typed owner proveru i novi APPLIED receipt.

### 2.10 Klijentski storage ugovor

Odvojene baze/cache namespace po `(installation_public_id,account_public_id,school_id,context_version,authorization_version,app_schema_version)`. `installation_public_id` je random M19 vrednost koja se obavezno rotira pri logout/user switch-u; nije credential ni browser fingerprint. `context_version` je kanonska monotona verzija aktivnog M03 konteksta; M19 ne uvodi paralelni naziv `session_generation`. Dozvoljeno: versioned app shell statički asseti; minimalni navigation/dashboard aggregate response sa hard TTL najviše 15 minuta i lokalnim hard-expiry vremenom; M11 allow-list queue/snapshot iz M11 ugovora. Zabranjeno: auth token u IndexedDB/localStorage, Person profil, guardian/family graf, finansije, dokumenti, poruke, saglasnosti, event registration, globalni search index ili search istorija. Cache Storage ne kešira authenticated API response generičkim URL ključem.

## 3. Poslovna pravila i invarijante

1. Bootstrap redosled: validate M01 session → resolve M03 context/options → load M05 effective permissions/authorization version → M04 entitlement → manifest/composition → autorizovani data query. Nema privatnog rendera pre complete guard-a.
2. Jedna aktivna School i jedan prikazni workspace po M03 sesiji. Svi tabovi iste sesije moraju revalidirati njen context_version pri promeni; nezavisni tenant konteksti po tabu nisu dozvoljeni. Workspace menja raspored UI-ja, ne M05 uniju prava.
3. Global Home pre izbora škole prikazuje samo dozvoljene škole/workspace opcije i neutralne akcije; nema counts, child names, finance ili schedule iz više škola.
4. Context switch atomarno izdaje novu M03 `context_version`, prekida relevantne requests/subscriptions, zatvara modale, čisti tenant cache/search state/M11 queue prema M03/M11 pravilima i tek zatim renderuje novu školu.
5. Svaki response nosi `school_id`, `context_version`, `authorization_version`; klijent ga odbacuje ako se ne poklapa sa trenutnim context-om, čak i ako je HTTP 200.
6. Back/forward istorija ne vraća tenant podatke starog context-a; route se ponovo resolve-uje.
7. Navigation item se prikazuje samo ako permission+capability prolaze, ali server endpoint ponavlja sve guardove. Sakrivanje nije kontrola.
8. Dashboard widget failure je izolovan; kritični `SESSION/TENANT/AUTH` failure zatvara ceo privatni shell. Widget ne prikazuje lažnu nulu umesto error/empty/partial.
9. M18 widget prikazuje metric version, period i freshness. Finance `PARTIAL/UNAVAILABLE` nikad nije headline success.
10. Command bar se otvara `Meta+K`, `Ctrl+K` ili mobilnom Search akcijom; ne presreće prečicu unutar input/textarea/contenteditable osim eksplicitnog UI dugmeta.
11. Query se šalje posle najmanje 2 normalizovana znaka; debounce 150–250ms; prethodni request se otkazuje i response sequence guard odbacuje zakasneli rezultat.
12. Search normalizacija proizvodi tri indeksna tokena po reči: (a) Unicode NFKC + Unicode casefold + trim/internal-whitespace collapse, uz originalno pismo; (b) kanonsku srpsku latinicu mapiranjem ćiriličnih slova, uključujući `љ→lj`, `њ→nj`, `џ→dž`, `ђ→đ`, `ћ→ć`, `ч→č`, `ш→š`, `ж→ž`; (c) ASCII fallback `č|ć→c`, `š→s`, `ž→z`, `đ→dj`, `dž→dz`. Već latinični token prolazi iste (b)/(c) fold korake. Display ostaje izvorno pismo. Ovaj mehanizam služi samo matching/ranking-u i nikad identity linking-u; runtime key nema transliteraciju/homoglif zamenu.
13. Search source prvo primenjuje tenant, permission i subject/assignment scope, zatim matching/ranking/count. Nema „postoji ali nemate pristup”, total-a skrivenih redova ili suggestions iz drugog scope-a.
14. Ranking je tačno: exact prefix original-normalized tokena > whole-token prefix original-normalized > kanonska-latinica match > ASCII-fallback match > fuzzy distance do 1 za token 4..7 ili do 2 za token ≥8; token kraći od 4 nema fuzzy. Zatim type priority po workspace-u, original-normalized display i entity UUID. Isti input, published normalization version i source snapshot daju isti redosled.
15. Result cap 20 po response-u, ukupno najviše 50 kroz cursor; hard max 100 za administrativnu typed list rutu, ne command-bar. Query max 80 Unicode scalar-a; najviše 8 tokena.
16. Command bar rezultat samo navigira na read/detail/create surface; destruktivna/finansijska/RBAC radnja zahteva domen ekran, validaciju i potvrdu. Nema auto-command-a.
17. Child result prikazuje samo minimalni naziv + dozvoljeni context label. Avatar, DOB, guardian, health i balance nisu rezultat.
18. Recent search query/entity istorija se ne čuva server-side niti trajno na uređaju u H0. Dozvoljene su statične „brze akcije” izvedene iz permission-a.
19. Pre-auth deep link može samo sačuvati allow-list route i enkriptovan opaque target iza jednokratnog browser nonce-a; pre autentifikacije se ne proverava postojanje targeta i odgovor je isti za postojeći, nepostojeći i skriven target. Posle atomskog vezivanja za novu sesiju bira se/validira škola, pa se ponavljaju permission/resource/subject guardovi. Skriven/cross-tenant target završava na neutralnom safe fallback-u bez naziva, count-a ili timing oracle-a.
20. Redirect target je allow-list route key, nikad otvoren URL; sprečava open redirect/path traversal/protocol injection.
21. Server-side opoziv važi odmah: svaki novi request/realtime reconnect posle commit-a ponovo proverava M01/M03/M05 verzije i failuje closed. Online revoke signal, lokalno uočeni session expiry, logout ili user switch odmah zamrzavaju privatni UI, prekidaju requests/realtime, brišu privatni cache/IndexedDB i zahtevaju service-worker purge acknowledgment; ako purge ne uspe, privatni shell ostaje blokiran. Uređaj koji je potpuno offline ne može primiti remote purge signal: zato nijedan privatni M19 cache ne sme biti prikazan posle svog lokalnog hard-expiry-ja (najviše 15 min od poslednje uspešne serverske reautorizacije), a M11 snapshot/queue prati svoj stroži lease i reautorizaciju. Pri prvom reconnect-u ili ranijem lokalnom signalu radi se freeze+purge pre bilo kog privatnog rendera. Ovaj ugovor ne tvrdi nemogući daljinski wipe offline uređaja.
22. M11 je jedini H0 offline business write. M19 samo transportuje njegov kriptografski/session-bound queue i prikazuje `PENDING_SYNC|SYNCED|SYNC_FAILED`; ne menja M11 payload/merge pravila.
23. Sve druge offline akcije su read-only ili blokirane. UI ne prikazuje „Sačuvano”, „Plaćeno”, „Prihvaćeno”, „Prijavljeno” bez server receipt-a.
24. Optimistic UI je dozvoljen za lokalnu preference i M11 draft; domain entity ne dobija finalni status pre servera. Failure vraća stanje i objašnjiv safe error.
25. Service worker nikada ne cache-uje auth callback/invitation/download/signed URL, dokument, finance, consent, search response ili `Set-Cookie` response. Private API default `no-store` osim eksplicitne M19 allow-list projekcije.
26. App update se preuzima u pozadini, ali aktivira tek kada nema unsynced M11 queue/draft. Critical security update može blokirati shell, prvo čuva kompatibilan M11 queue i zahteva eksplicitnu migraciju ili sync; nikad ga tiho odbacuje.
27. Schema mismatch starog cache-a failuje closed i purge-uje; migration funkcija je verzionisana, idempotentna i testirana.
28. PWA install nije uslov korišćenja; browser web radi isto. Push permission se ne traži pri prvom renderu nego posle kontekstualnog korisničkog izbora; M14 poseduje subscription/delivery.
29. Accessibility: WCAG 2.2 AA cilj; potpuna keyboard navigacija, visible focus, semantic landmarks, label/error association, minimum target 44×44 CSS px za primarne mobilne akcije, reduced motion i screen-reader status za sync/error.
30. „Tri klika” je merljiv standardni tok, ne univerzalna garancija za svaki izuzetak. Brojanje počinje na učitanom, autorizovanom Home-u odgovarajućeg workspace-a sa već izabranom školom i završava prikazom server-confirmed rezultata ili traženog read prikaza. Login, izbor škole kada nije izabrana, unos poslovnog sadržaja i obavezna potvrda moraju biti navedeni u scenariju; ne smeju se sakriti da bi metrika prošla. Izuzeci koji zahtevaju rešavanje konflikta, izbor između više subjekata, pravnu potvrdu ili dodatne obavezne podatke mogu preći tri interakcije i moraju biti eksplicitno označeni kao izuzeci.
31. Search projection prihvata samo M21 envelope sa validnim payload hash-em i school scope-om, zatim typed owner batch-read potvrđuje isti tenant/entity/version i kompletan binding skup. SearchDocument, scope binding-i i APPLIED receipt commit-uju zajedno; nema parcijalnog current reda. Search key rotacija je tenant-scoped: STABLE koristi jedan key; početak rotacije atomski uvodi novi write key i stari+novi read skup u PREPARING; PREPARING backfill-uje aktuelne redove CAS-om bez plaintext loga; DUAL_READ je dozvoljen tek kada je backfill potpun i oba query puta daju isti autorizovani skup; CUTOVER uklanja stari key iz read skupa tek kada verifier potvrdi 100% ACTIVE redova, typed bindings i nula divergence-a. Posle kontrolisanog rollback prozora CUTOVER→STABLE čisti rotation metadata, a stari key se povlači tek kada ga nijedan važeći red/evidence ne referencira. Abort pre CUTOVER vraća STABLE na stari key samo posle dokazivog reverse-backfill/reconciliation-a; posle CUTOVER povratak je nova rotacija, ne tajni fallback. Nedostupan ključ ili konflikt verzija daje `SEARCH_INDEX_UNAVAILABLE`, ne fallback na globalni/plaintext indeks.
32. M21 izvršava jedini cleanup ključ `pwa.intent_installation_expiry`. U bounded keyset stranicama, uz lease/fencing i `database_now`, atomski materializuje DeepLinkIntent EXPIRED na `expires_at<=now` i PwaInstallation EXPIRED na `last_seen_at+90 dana<=now`, scrub-uje intent sadržaj, emituje content-free audit/receipt i ne dodiruje noviji CAS red. Request-time TTL/inactivity provera je autoritet i ne čeka job. Retry istog business ključa daje isti terminalni rezultat; trka consume/revoke/heartbeat protiv cleanup-a ima tačno jednog CAS pobednika i nikad ne vraća terminalan red u ACTIVE/pending stanje.

### 3.1 Kanonski standardni UX tokovi

| Tok i početno stanje | Obavezne primarne interakcije | Kraj merenja | Izuzetak |
|---|---:|---|---|
| Coach Home, jedan sledeći današnji termin | 1. otvori termin; 2. potvrdi unapred prikazanu evidenciju | server receipt za M11 evidenciju | promena statusa jednog ili više učesnika dodaje jednu grupisanu interakciju; konflikt ide u poseban resolve tok |
| Manager/Coach Home | 1. otvori `Danas/Raspored` | autorizovana dnevna lista | promena filtera nije deo standardnog toka |
| Manager Home | 1. otvori finansijski sažetak | M18/M12 prikaz sa freshness stanjem | detalj jedne obaveze je druga interakcija; nema write potvrde u ovom toku |
| Manager Home sa quick action | 1. `Nova poruka`; 2. unese sadržaj; 3. potvrdi publish | server receipt M13 | izbor složene publike/attachment-a je izuzetak i meri se zasebno |
| Home sa Events karticom | 1. otvori događaj; 2. izaberi dozvoljenu akciju/subjekta na istoj strani; 3. potvrdi | server receipt M16 | fee/payment ili višestruki eligibility konflikt ide u zaseban online tok |

### 3.2 Edge cases

| # | Scenario | Ishod |
|---|---|---|
| 1 | A search response stigne posle switch-a na B | Odbacuje se po `context_version`; ne renderuje ni trenutak. |
| 2 | Dva taba: jedan A, drugi switch na B | Session context politika M03 određuje `context_version`; svaki tab revalidira, nema cache mešanja. |
| 3 | Workspace INSTRUCTOR, actor ima i MANAGER | UI je instructor-first; M05 unija ostaje ista, subject guard i dalje važi. |
| 4 | Deep link ka child-u posle guardian revoke-a | Safe fallback/404; lokalni cache purge. |
| 5 | Query „an” daje 300 rezultata | Najviše 20, stabilan cursor; skriveni ne ulaze u count/ranking. |
| 6 | Latin „Dj” traži ćirilični „Ђ” | Kanonska transliteracija matchuje; display ostaje original; ranking stabilan. |
| 7 | Korisnik ukuca email bez admin exact-search prava | Nema contact lookup/indikatora. |
| 8 | Offline klik „plati”/„prijavi događaj” | Jasno online-required; nema queue-a ni optimistic success-a. |
| 9 | Update čeka, a M11 ima PENDING_SYNC | Ne aktivira novu verziju dok queue nije sync/rešena ili kompatibilno migrirana. |
| 10 | Purge IndexedDB quota/browser error | Privatni shell blokiran; retry/clear-site-data instrukcija; nema prelaska drugom korisniku. |
| 11 | Nedostaje obavezna finansijska source barijera | Widget je `UNAVAILABLE`; nema headline total-a ni partial finansijskog iznosa. |
| 12 | Malicious redirect `javascript:` | 422/rejected; samo route key allow-list. |

## 4. Tenant i security guard

Svaki bootstrap/query/search/deep-link/data fetch koristi M01 session, M03 server context, M04 ACTIVE/entitlement, M05 permission, owner resource guard i M07 subject guard gde je dete. Organization/global Person/workspace ne preskaču pipeline. Cross-tenant/hidden je safe 404; poznata vidljiva surface bez akcione permission je 403.

Search index, scope binding, cache, cursor, realtime channel, web worker message i telemetry nose tenant + `context_version` ili su potpuno javni statički asset. Composite FK drži binding uz SearchDocument iste škole, a typed owner batch-read i source-envelope provera sprečavaju da polymorphic entity/dimension iz druge škole uopšte uđe u projekciju. Search query se ne loguje. Rate limit je per tenant+actor+installation i ne pravi cross-tenant side channel.

Active-school search zahteva `school.search.use`; nema globalne cross-school pretrage. Exact contact lookup dodatno zahteva `school.search.exact_contact`. Objavljivanje shell konfiguracije zahteva `platform.shell.configuration.publish`, a ručni rebuild projekcije `platform.search.projections.rebuild`. Tačni binding-i i zabrane su jedino u M05 permission registru. Self preference/installation/deep-link komande koriste self guard i ne stvaraju delegabilan business permission.

Content Security Policy, Trusted Types gde ih stack podržava, output encoding i zabrana unsafe HTML sprečavaju XSS; CSRF zaštita važi za cookie-auth commands; service worker scope je samo aplikacioni origin/path; nema caching cross-origin credential response-a. Secrets nisu u bundle-u, manifestu, source map-u ili telemetry-ju.

## 5. Lifecycle i transitions

| Entitet | Iz | Operacija | U |
|---|---|---|---|
| ShellPreference | — | Set valid self preference | ACTIVE |
| ShellPreference | ACTIVE | Update expected version | ACTIVE v+1 |
| ShellPreference | ACTIVE | Account/school disposition | ARCHIVED |
| Manifest/Composition | — | Create | DRAFT |
| Manifest/Composition | DRAFT | Publish valid routes/permissions/hash | PUBLISHED |
| Manifest/Composition | PUBLISHED | PublishNewVersion | nova PUBLISHED verzija; stara immutable |
| Manifest/Composition | PUBLISHED | Retire | RETIRED |
| SearchDocument | — | Project | ACTIVE |
| SearchDocument | ACTIVE | Source update | ACTIVE v+1 |
| SearchDocument | ACTIVE | Source hidden/deleted | TOMBSTONED |
| SearchDocument | TOMBSTONED | Valid source reactivation | ACTIVE novija source version |
| SearchProtectionKeyState | — | Initialize tenant/purpose key | STABLE |
| SearchProtectionKeyState | STABLE | StartRotation sa novim managed key-em | PREPARING |
| SearchProtectionKeyState | PREPARING | Potpun backfill + reconciliation | DUAL_READ |
| SearchProtectionKeyState | DUAL_READ | 100% query/binding verifier PASS | CUTOVER |
| SearchProtectionKeyState | CUTOVER | Rollback window istekao, reference proverene | STABLE na novom key-u |
| SearchProtectionKeyState | PREPARING/DUAL_READ | Abort + reverse-backfill/reconciliation PASS | STABLE na prethodnom key-u |
| Checkpoint | — | Initialize | REBUILDING |
| Checkpoint | FAILED/HEALTHY/LAGGING | Rebuild | REBUILDING |
| Checkpoint | REBUILDING/LAGGING | Complete | HEALTHY |
| Checkpoint | HEALTHY | Lag | LAGGING |
| Checkpoint | HEALTHY/LAGGING/REBUILDING | Fatal | FAILED |
| DeepLinkIntent | — | CapturePreAuth + browser nonce hash | PRE_AUTH_PENDING |
| DeepLinkIntent | PRE_AUTH_PENDING | BindAfterLogin, isti nonce/TTL | AUTH_BOUND_PENDING |
| DeepLinkIntent | PRE_AUTH_PENDING | nonce mismatch/second bind | REJECTED |
| DeepLinkIntent | PRE_AUTH_PENDING/AUTH_BOUND_PENDING | Request-time TTL ili `pwa.intent_installation_expiry` | EXPIRED + target/hint scrub |
| DeepLinkIntent | AUTH_BOUND_PENDING | Resolve once, svi guardovi | CONSUMED ili REJECTED |
| Installation | — | Register | ACTIVE |
| Installation | ACTIVE | Logout/revoke | REVOKED |
| Installation | ACTIVE | 90 dana bez uspešnog autentifikovanog PWA heartbeat-a, request-time ili `pwa.intent_installation_expiry` | EXPIRED |

ARCHIVED preference, RETIRED konfiguracija, CONSUMED/REJECTED/EXPIRED intent i REVOKED/EXPIRED installation su terminalni. `PRE_AUTH_PENDING` se nikad ne vraća iz `AUTH_BOUND_PENDING`. Search reactivation je strogo novija source verzija sa novim append-only receipt-om; current tombstone PII se ne zadržava. Key-state prelazi su CAS-auditovani i ne dozvoljavaju direktan STABLE→CUTOVER, DUAL_READ→stari STABLE bez reverse verifier-a niti povratak sa CUTOVER-a kao običan rollback.

## 6. Error catalog

| Code | HTTP | Značenje |
|---|---:|---|
| `SHELL_UNAUTHENTICATED` | 401 | Sesija nije validna. |
| `SHELL_FORBIDDEN` | 403 | Surface/action nije dozvoljena. |
| `SHELL_NOT_FOUND_SAFE` | 404 | Skriven/cross-tenant target. |
| `SHELL_CONTEXT_REQUIRED` | 409 | Nema aktivnog školskog context-a. |
| `SHELL_CONTEXT_STALE` | 409 | Response/request `context_version` je zastareo. |
| `SHELL_WORKSPACE_UNAVAILABLE` | 409 | Preference više nije dozvoljena. |
| `SHELL_MANIFEST_INVALID` | 422 | Route/permission/capability manifest nevažeći. |
| `SHELL_ROUTE_INVALID` | 422 | Route key/param nije allow-list. |
| `SHELL_DEEPLINK_BINDING_INVALID` | 409 | Nonce, sesija ili conditional-null binding nisu validni. |
| `SHELL_DEEPLINK_EXPIRED` | 410 | Intent istekao/iskorišćen. |
| `SEARCH_QUERY_INVALID` | 422 | Dužina/token/Unicode ugovor nije validan. |
| `SEARCH_NOT_FOUND_SAFE` | 404 | Skriven scope/entity. |
| `SEARCH_RATE_LIMITED` | 429 | Bezbedni actor/tenant limit. |
| `SEARCH_INDEX_UNAVAILABLE` | 503 | Nema bezbedne projekcije. |
| `PWA_OFFLINE_OPERATION_DENIED` | 409 | Operacija nije M11 dozvoljeni offline tok. |
| `PWA_CACHE_SCHEMA_MISMATCH` | 409 | Cache mora biti očišćen/migriran. |
| `PWA_PURGE_REQUIRED` | 409 | Privatni shell blokiran do purge-a. |
| `PWA_UPDATE_BLOCKED_PENDING_SYNC` | 409 | M11 queue sprečava aktivaciju. |
| `SHELL_IDEMPOTENCY_CONFLICT` | 409 | Isti key, različit payload. |
| `SHELL_VERSION_CONFLICT` | 409 | Expected version konflikt. |
| `SHELL_INTERNAL_SAFE` | 500 | Neočekivana greška bez PII/stack leak-a. |

## 7. API, idempotency, concurrency i NFR

Queries: `BootstrapShell`, `GetGlobalHomeOptions`, `GetNavigationManifest`, `GetDashboardComposition`, `SearchAuthorizedEntities`, `ResolveBoundDeepLink`, `GetPwaCompatibility`, `GetSyncSummary`. Commands: `SetWorkspacePreference`, `CapturePreAuthDeepLinkIntent`, `BindDeepLinkIntentAfterLogin`, `ConsumeBoundDeepLinkIntent`, `RegisterPwaInstallation`, `RecordAuthenticatedPwaHeartbeat`, `RevokePwaInstallation`, `AcknowledgeClientPurge`, `PublishManifestVersion`, `PublishCompositionVersion`, `RebuildSearchProjection`. `RecordAuthenticatedPwaHeartbeat` zahteva M01 session, isti account/installation i current authorization version; rezultat je isti red bez write-a ako prethodni uspešan heartbeat nije stariji od 24 sata.

`BootstrapShell` vraća jedan signed/hashed envelope: account public ref, active school/`context_version`, display workspace, permission/capability digests, navigation, critical dashboard queries i cache policy; bez globalnog role/child dump-a. Search cursor je MAC-protected i vezan za tenant, `context_version`, actor authorization version, query hash, types/filter i projection watermark.

Write koristi Idempotency-Key/request hash/receipt; expected version za preference/config. Deep-link bind/consume zaključava intent red i koristi compare-and-set status/version; identičan retry vraća isti terminalni receipt, a isti ključ sa drugim nonce/session/target hash-om vraća konflikt. Context switch koristi monotonic `context_version`, a logout M01 security/session generation; late response ne može pobediti. Search consumer koristi append-only receipt unique po event-u i entity/version-u; rebuild čuva samo digest lease tokena i fencing. AbortController ili ekvivalent otkazuje stale fetch, ali server svejedno autorizuje. M11 queue concurrency ostaje isključivo M11 CAS ugovor.

Referentni profil `SOKOLA-NFR-PWA-V1`: Android uređaj sa 4 fizička jezgra, 4 GB RAM-a i Chrome verzijom zaključanom u CI zapisu; viewport 360×800; RTT 150 ms, downlink 1.6 Mbps, uplink 750 Kbps, packet loss 1%; seed 25.000 učesnika/1.000 grupa po školi, 20 search rezultata, pet dashboard widgeta; najmanje 30 merenih prolaza nakon pet warm-up prolaza, cold test sa čistim storage-om, warm test sa version-compatible javnim assetima. Budžeti: warm shell interactive p95 ≤2.5s, cold p95 ≤4.0s; javni cached offline shell ≤1.0s; command bar open p95 ≤100ms; search p95 ≤300ms server/≤500ms visible; context switch p95 ≤1.2s bez owner data pre guard-a. Field p75: LCP ≤2.5s, INP ≤200ms, CLS ≤0.1. Initial authenticated route gzip JS ≤250KiB, CSS ≤60KiB, pojedinačni lazy route JS ≤180KiB. Dokaz mora sadržati commit, build/config hash, browser/device profil, dataset hash, raw percentile summary i bundle report; cilj se ne smatra dostignutim dok taj dokaz ne postoji. Prekoračenje blokira release osim dokumentovanog, vremenski ograničenog waiver-a product+security owner-a.

Availability: shell mora dati bezbedan error/retry; nikad beskonačan spinner >10s. Search/dashboard imaju timeout/circuit breaker i izolovan fallback. Lista/search cursor default 20, max 50 command-bar; ostale typed liste default 25/max100. Nema sinhronog N+1; composition batchuje/fan-out ograničeno na serveru.

## 8. Audit, telemetry, migration i acceptance

Audit: manifest/composition publish/retire, workspace switch preference, deep-link reject security incident, installation revoke, forced purge/update i search admin exact-contact use. Običan search query/click se ne auditira sa tekstom; security counter ima samo category/code. M21 telemetry: route key, app version, device class bucket, network bucket, durations, CWV, error code, pseudonimizovan tenant/actor; nema URL params, search text, entity/child ID, title, amount ili content.

Migracija/brownfield: inventar ruta/dashboard/search/service-worker/cache; `PRESERVE|ADAPT|IMPLEMENT|REMOVE_CONFLICT`; ukloniti localStorage token i generički private API cache; versionirati DB/cache; shadow search poredi samo synthetic allow-list rezultate; dva tenant-a i dva user switch-a; service-worker rollback zadržava kompatibilnost M11 queue-a. Nepoznata ruta/permission/cache red se ne guess-uje.

Acceptance: role/workspace dashboards; Global Home bez cross-school data; context switch race; safe deep links; command bar keyboard/mobile/accessibility; deterministički bilingual search; child minimization; revoke/purge; samo M11 offline; update pending-sync; 3-click tokovi; performance/bundle/RUM; CSP/XSS/CSRF/open redirect; duplicate/out-of-order projection; 100% QA, 0 skipped/flaky. Status ostaje `SPEC_CANDIDATE` do repo/migration/test dokaza.
