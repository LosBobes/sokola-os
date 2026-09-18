---
tip: modulni-implementacioni-ugovor
modul-id: M03
naziv: Multi-tenancy i aktivni tenant kontekst
status: SPEC_CANDIDATE
datum: 2026-09-08
revizija: "1.2"
schema-zavisnosti: [M01, M04]
read-portovi: [M06]
application-kompozicija: [M05, M07]
izlazni-portovi-za: [M02, M05, M17, M19, M20, M21, M28]
---

# M03 — Multi-tenancy i aktivni tenant kontekst

## 1. Svrha, autoritet i rezultat

M03 zaključava kako SOKOLA razdvaja podatke škola, kako prijavljeni korisnik bira tačno jednu aktivnu školu i jedan prikazni workspace i kako server tenant kontekst ponovo dokazuje pri svakoj zaštićenoj radnji.

Kanonski rezultat je:

- `School` je jedina operativna bezbednosna tenant granica;
- globalni `Person`, `UserAccount` i `AuthIdentity` nisu tenant i ne daju pristup nijednoj školi;
- jedna autentifikovana sesija ima najviše jednu aktivnu školu i jedan izabrani prikazni workspace;
- izabrani workspace/uloga određuje navigaciju i početni ekran, ali ne proširuje niti sužava stvarna prava; M05 računa uniju svih aktivnih dodela uloga i dozvola iste osobe u aktivnoj školi, a M03/M07 tenant i subject guardovi tu uniju dodatno ograničavaju;
- klijentski `school_id`, slug, kod škole, ruta, cookie, header ili lokalno zapamćen izbor samo su predlog, nikad autoritet;
- server za svaki command, query, list, count, search, export, download, realtime subscribe i user-scoped job ponovo proverava tenant, membership, ulogu/dozvolu i subject scope;
- nijedan odgovor, keš, job, storage ključ, outbox događaj ili izveštaj ne sme mešati škole.

M03 je obavezna H0 osnova. Nema feature flag koji u produkcionom ili pilot okruženju isključuje tenant izolaciju.

## 2. Granice modula i non-goals

M03 ne postaje paralelni vlasnik podataka drugih modula:

| Podatak/odluka | Vlasnik | M03 uloga |
|---|---|---|
| autentifikovani nalog, sesija i `authorization_version` | M01 | prvo zahteva validan M01 principal/session |
| Invitation token i activation lifecycle | M02 | daje tenant-status i context portove; ne čuva Invitation |
| `School`, Organization odnos i subscription foundation | M04 | koristi `School.id`, status i security revision; ne pravi Organization |
| uloge, dozvole, role assignment i Support Access | M05 | application coordinator koristi M05 za workspace opcije i autorizaciju; M03 čuva samo prikazni `workspace_key` i ne importuje M05 domain/schema |
| `Person`, `SchoolMembership` i školski profil | M06 | proverava aktivan membership kroz M06 port; ne vodi membership lifecycle |
| guardian/child i subject prava | M07 | M07 subject guard se izvršava posle M03 context resolvera u application pipeline-u; M03 ne importuje M07 |
| ogranci, programi, lokacije i prostori | M08 | proverava da reference pripadaju aktivnoj školi; nisu zasebni tenanti |
| grupe, upisi i staff assignment | M09 | proverava tenant-safe relacije; ne vodi njihove lifecycle-e |
| privatnost, DSAR i retention | M17 | daje izolovane izvršne granice; M17 određuje pravni workflow |
| shell, deep-link i PWA ponašanje | M19 | daje context API i invalidaciju; M19 renderuje površine |
| audit, jobs, telemetry i handover infrastruktura | M21 | definiše obavezne tenant dimenzije i fail-closed ugovor |

M03 ne uvodi novi `Tenant` master pored `School`, ne daje automatski cross-school pristup Organization-u, ne spaja podatke više škola u MVP-u, ne uvodi nalog deteta, ne definiše javnu registraciju i ne odlučuje fizičku strategiju baze.

## 3. Normativni pojmovi

| Pojam | Značenje |
|---|---|
| `School` | Jedan operativni tenant. ID je stabilan, opaque i ne reciklira se. |
| `TenantLocator` | Slug, kod škole, hostname ili drugi locator koji pomaže navigaciji. Nije tajna i nikad nije dozvola. |
| `AvailableTenantContext` | Server-side izvedena, minimalna škola sa dozvoljenim prikaznim workspace opcijama koje korisnik trenutno sme da izabere. Nije novi master. |
| `SessionTenantContext` | M03 zapis trenutne škole i prikaznog workspace-a u jednoj M01 sesiji. On je preference/routing stanje, ne samostalni dokaz prava. |
| `TenantExecutionContext` | Nepersistirani request/job kontekst nastao nakon svih obaveznih guardova. Jedini je dozvoljeni ulaz tenant repository/use-case sloju. |
| `tenant_access_version` | Monotona security revizija škole ili strogo ekvivalentan mehanizam. Menja se kada tenant-wide pristup mora odmah da zastari. |
| `context_version` | Monotona revizija izbora konteksta unutar jedne sesije. Sprečava da stari tab ili spori odgovor nastavi rad u prethodnoj školi. |
| `membership evidence` | Aktivni M06 `SchoolMembership` koji povezuje `Person` i `School`. Sam po sebi nije uloga. |
| `workspace_key` | Registrovan prikazni fokus (`ADMIN`, `INSTRUCTOR`, `GUARDIAN`, `PAYER` ili budući eksplicitni ključ). Nije role assignment, permission filter niti authorization dokaz. |
| `effective role set` | Sve aktuelne M05 role/permission dodele osobe u aktivnoj školi. M05 nad njima računa uniju dozvola; tenant i subject guardovi mogu samo dodatno suziti rezultat. |
| `subject scope` | M07/M05 ograničenje nad konkretnim detetom, grupom, ogrankom, dokumentom ili drugim subjektom. |
| `PLATFORM scope` | Eksplicitni SOKOLA administrativni kontekst. Nije lažni tenant i ne daje redovan pristup tenant podacima. |

## 4. Kanonska tenant topologija

1. `School` je tenant čak i kada više škola pripada istoj `Organization`.
2. `OrganizationSchool` iz M04 ne stvara implicitno pravo nad drugom školom.
3. Branch, Program, Location, Space, Group i Event nisu tenanti; svaki pripada jednoj školi.
4. `Person`, `UserAccount`, `AuthIdentity` i `Organization` su globalni, ali su globalni samo po identitetu/modelu — nisu globalno pretraživi školskoj administraciji.
5. `SchoolMembership`, `SchoolPersonProfile`, `RoleAssignment`, `GuardianChildLink` i svi operativni Core zapisi su tenant-scoped.
6. Promena vlasničke Organization veze ne menja `school_id` niti premešta operativne podatke.
7. Spoljni organizator događaja ne postaje tenant automatski.
8. Tenant merge, deljenje jednog operativnog zapisa između dve škole i hard delete škole nisu MVP operacije.

Fizička strategija može biti zajednička šema sa `school_id`, šema/baza po tenant-u ili hibrid, ako već postoji u repou i dokazivo sprovodi isti ugovor. Zajednička šema mora koristiti tenant kolone i tenant-safe veze iz §7. Izolovana šema/baza mora imati proverljivo routing mapiranje, zabranu pogrešnog connection target-a i iste cross-tenant testove.

## 5. Izvori istine i minimalni podatkovni model

### 5.0. Kanonski logički tipovi

Fizički SQL/ORM/API tip može biti drugačije imenovan, ali mora dokazivo čuvati sledeću semantiku bez gubitka:

| Logički tip | Tačno značenje |
|---|---|
| `Identifier` | Immutable opaque identifikator sa najmanje 128 bita prostora; nije poslovni broj, naziv ili locator i nikad se ne reciklira. |
| `UInt64` | Ceo broj `1..9_223_372_036_854_775_807`; monotone verzije se uvećavaju tačno za 1 i ne resetuju se. |
| `InstantUTC` | Trenutak sa vremenskom zonom, skladišten kao UTC/TIMESTAMPTZ sa preciznošću najmanje milisekunde; serijalizuje se sa eksplicitnom `Z`/UTC oznakom. |
| `Code64` | ASCII string dužine `1..64`, case-sensitive, iz zatvorenog registra; bez Unicode homoglifa i slobodnog PII teksta. |
| `DisplayString120` | UTF-8 prikazni tekst `1..120`; trimuje se samo na ivicama i nije identity/security ključ. |
| `Nullable<T>` | Polje može biti `null` samo u izričito navedenim stanjima; prazan string nije zamena za `null`. |

Svi `created_at`, `updated_at`, `selected_at`, `invalidated_at` i slični trenuci nastaju na serveru. Klijent ih ne određuje.

### 5.1. Referencirani entitet `School`

M04 ostaje vlasnik `School` lifecycle-a. M03 čita, ali ne duplira sledeći ugovor:

- `id: Identifier`, PK, obavezno i immutable;
- `status: enum<IN_PREPARATION, ACTIVE, DEACTIVATED>`, obavezno; UI prevodi su `U pripremi`, `Aktivna`, `Deaktivirana`;
- `updated_at: InstantUTC`, obavezno.

`School.status` ostaje jedini autoritet poslovnog statusa škole.

### 5.2. Entitet `TenantSecurityState`

M03 poseduje tačno jedan trajni security zapis za svaku školu:

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `school_id` | `Identifier` | NE | PK i FK → `School.id`; immutable; tačno 1:1. |
| `tenant_access_version` | `UInt64` | NE | Default `1`; raste tačno za 1 pri svakoj tenant-wide sigurnosnoj invalidaciji. |
| `created_at` | `InstantUTC` | NE | Server vreme kreiranja. |
| `updated_at` | `InstantUTC` | NE | Server vreme poslednje promene. |
| `last_invalidated_at` | `Nullable<InstantUTC>` | DA | `null` do prve invalidacije. |
| `last_invalidation_reason_code` | `Nullable<Code64>` | DA | Obavezno iff `last_invalidated_at != null`. |
| `version` | `UInt64` | NE | Default `1`; optimistic concurrency verzija reda. |

`CHECK((last_invalidated_at IS NULL) = (last_invalidation_reason_code IS NULL))`. Ne postoji drugi M03 status škole. `tenant_access_version` se povećava u istoj poslovnoj transakciji sa deaktiviranjem/reaktiviranjem škole ili drugom tenant-wide sigurnosnom promenom. Stvarno čitanje `School.status` ostaje obavezno; verzija omogućava momentalno obaranje stale konteksta i sekundarnih projekcija.

### 5.3. Entitet `SessionTenantContext`

Postoji najviše jedan tekući zapis po M01 sesiji. Prethodne izbore čuva audit, ne paralelni aktivni redovi.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK, immutable. |
| `session_id` | `Identifier` | NE | FK → M01 `Session.id`; `UNIQUE(session_id)`. |
| `user_account_id` | `Identifier` | NE | FK → M01 `UserAccount.id`; mora odgovarati nalogu sesije i izvodi se server-side. |
| `school_id` | `Identifier` | NE | FK → `School.id`; trenutna aktivna škola sesije. |
| `workspace_key` | `Code64` | NE | Registrovan prikazni fokus; nema FK ka M05 i nije authorization dokaz. |
| `status` | `enum<ACTIVE, INVALIDATED>` | NE | Jedino `ACTIVE` je upotrebljivo. |
| `context_version` | `UInt64` | NE | Početno `1`; raste tačno za 1 pri select/switch/clear/invalidation promeni. |
| `tenant_access_version_at_selection` | `UInt64` | NE | Snapshot M03 verzije pri izboru; nije trajni allow dokaz. |
| `authorization_version_at_selection` | `UInt64` | NE | Snapshot M01 verzije pri izboru; nije trajni allow dokaz. |
| `selected_at` | `InstantUTC` | NE | Server vreme poslednjeg uspešnog select/switch-a. |
| `last_validated_at` | `InstantUTC` | NE | Operativni trag; ne dozvoljava preskakanje nove provere. |
| `invalidated_at` | `Nullable<InstantUTC>` | DA | Obavezno iff `status=INVALIDATED`. |
| `invalidation_reason_code` | `Nullable<Code64>` | DA | Obavezno iff `status=INVALIDATED`. |
| `version` | `UInt64` | NE | Optimistic concurrency verzija reda, početno `1`. |

Obavezna ograničenja:

- `CHECK(status='ACTIVE' AND invalidated_at IS NULL AND invalidation_reason_code IS NULL OR status='INVALIDATED' AND invalidated_at IS NOT NULL AND invalidation_reason_code IS NOT NULL)`;
- `UNIQUE(session_id)`;
- `workspace_key` mora pripadati zatvorenom application workspace registru; dostupnost korisniku proverava application coordinator preko M05, bez M03→M05 import-a;
- `context_version`, `version`, `tenant_access_version_at_selection` i `authorization_version_at_selection` su `>=1`.

Invarianti:

- najviše jedan kontekstni red po `session_id`;
- `session_id` pripada istom `user_account_id`;
- `school_id` mora biti server-side potvrđen; `workspace_key` je prikazna preferencija koju coordinator prihvata samo iz trenutno dozvoljenih opcija;
- zapis ne ostaje aktivan kada M01 sesija istekne ili je opozvana;
- kontekst ne sadrži listu permissions, guardian prava, finansijske subject-e ili kopije tenant podataka kao trajni autoritet;
- `workspace_key` ne sužava i ne proširuje efektivna prava; M05 ih računa iz svih aktivnih dodela uloga/dozvola iste osobe u aktivnoj školi;
- izbor u jednoj sesiji ne menja aktivni kontekst druge sesije istog naloga.

### 5.4. Query model `AvailableTenantContext`

Ovo je query model, ne master tabela. Minimalni rezultat:

- `school_id: Identifier` ili bezbedni `context_ref: Identifier`;
- `school_display_name: DisplayString120` i opcioni `logo_ref: Identifier`;
- `school_mode=REGULAR | SETUP_ONLY`;
- `workspace_options[]`, najmanje jedna stavka `{workspace_key: Code64, display_name: DisplayString120, description: Nullable<DisplayString120>}`;
- `last_used_workspace_key: Nullable<Code64>` hint, bez statusa autoriteta;
- opciona, purpose-limited imena povezane dece samo za roditeljski chooser kada M07 izričito dozvoli;
- `context_etag: Code64` ili ekvivalentna jaka verzija za stale proveru.

Ne vraća finansije, dug, prisustvo, dokumente, sadržaj poruka, broj članova, druge škole osobe niti razlog bezbednosnog ograničenja.

### 5.5. Nepersistirani `TenantExecutionContext`

Nastaje za jedan request ili jedan tenant job i najmanje sadrži:

- `session_id: Nullable<Identifier>` ili provereni service/job principal;
- `user_account_id: Nullable<Identifier>` i `person_id: Nullable<Identifier>` kada je actor korisnik;
- `school_id: Identifier`;
- `workspace_key: Code64` kao prikazna preferencija korisničkog toka;
- `context_version: UInt64`;
- aktuelni `authorization_version: UInt64` i `tenant_access_version: UInt64`;
- `correlation_id: Identifier`;
- `operation_id: Code64` — deklarisani command/query/job ID;
- nema ugrađenu M05 permission odluku niti M07 subject rezultat; oni nastaju u sledećim, zasebnim application guard koracima nad ovim kontekstom.

Ne serializuje se kao klijentski autoritativan token. Svaki modul prima ovaj kontekst preko application boundary-ja umesto sirovog `school_id` stringa. M05 i M07 nad njim donose zasebne fail-closed odluke.

## 6. Kada je tenant kontekst dozvoljen

### 6.1. Redovan rad

Kombinacija se pojavljuje kao `REGULAR` samo kada istovremeno važi:

1. M01 sesija i nalog su aktivni;
2. `UserAccount.person_id` određuje osobu; klijent je ne bira;
3. `School.status=ACTIVE`;
4. postoji aktuelni M06 membership evidence za istu osobu i školu sa statusom `ACTIVE`;
5. application coordinator je iz M05 izveo najmanje jednu dozvoljenu workspace opciju za istu školu;
6. izabrani `workspace_key` je među trenutno dozvoljenim prikaznim opcijama, dok M05 efektivna prava računa kao uniju svih aktivnih dodela u aktivnoj školi;
7. M05/M07 nisu opozvali potreban permission/subject scope;
8. security/authorization verzije nisu stale.

M06 `DRAFT`, `SUSPENDED` i `TERMINATED` članstvo ne daju redovan workspace pristup.

### 6.2. Škola u pripremi

`School.status=IN_PREPARATION` može dati samo `SETUP_ONLY` kontekst ovlašćenom prvom vlasniku/onboarding akteru. Taj kontekst otvara samo O01–O07 i eksplicitne M20/M04 setup komande. Ne otvara redovan Finance, Attendance, Documents, Reporting ili guardian workspace. M05 zaključava tačan permission registry.

### 6.3. Deaktivirana škola

`School.status=DEACTIVATED` nije dozvoljeni korisnički kontekst. Podaci ostaju sačuvani, ali redovne komande, query-ji, download-i, websocket-i i user-scoped jobs fail-closed. Druge škole korisnika ostaju dostupne. Platform recovery i vremenski ograničen Support Access pripadaju M05/M04 i nikad nisu implicitni bypass.

### 6.4. Jedan ili više konteksta

- tačno jedna dozvoljena škola i jedan workspace: server ih može automatski izabrati i otvoriti početnu površinu;
- jedna škola sa više workspace opcija: bira se samo prikazni workspace; izbor ne menja efektivna M05 prava;
- više škola: prikazuje se X03, grupisano po školi sa njenim workspace opcijama;
- nijedna kombinacija: neutralno M01 `NO_ACCESS`/X04 stanje;
- zapamćeni prethodni izbor: koristi se samo kao hint i mora proći celu novu proveru;
- ista osoba sa dve uloge u istoj školi dobija jedan tenant kontekst sa dve workspace opcije; M05 računa uniju aktivnih dozvola, a subject scope se proverava po konkretnoj radnji;
- isti nalog može u različitim M01 sesijama imati različite aktivne kontekste.

## 7. Tenant-safe relacioni ugovor

Za zajedničke tenant tabele važi:

1. Svaki operativni zapis ima `school_id NOT NULL` ili ima jednu obaveznu, nepromenljivu FK putanju koja ga jednoznačno vezuje za tenant. Za bezbednosno kritične i često query-ovane zapise preferira se direktni `school_id`.
2. Tenant parent tabela izlaže `UNIQUE(school_id, id)` ili ekvivalentan composite target.
3. Veza dva tenant entiteta koristi `(school_id, related_id) → (school_id, id)` composite FK ili ekvivalent koji baza i integration test dokazivo sprovode.
4. Unique poslovni ključ uključuje `school_id`, osim kada je izričito globalan (`AuthIdentity issuer+subject`, globalni provider registry i slično).
5. FK ka globalnom `Person`, `UserAccount`, `AuthIdentity` ili `Organization` ostaje obična globalna FK. Tenant pripadnost globalne osobe dokazuje se zasebnim membership/relationship guardom; globalne tabele ne dobijaju lažni `school_id`.
6. Polimorfna veza ne može koristiti samo `target_type + target_id` bez tenant dimenzije i type-specific validacije. Prednost imaju eksplicitne join tabele za osetljive veze.
7. Tenant child se ne može prebaciti promenom `school_id`. Transfer između škola, ako ikada bude odobren, pravi nov tenant zapis i kontrolisanu migraciju/snapshot — ne update vlasništva postojećeg reda.
8. `school_id` se ne prima kroz mass-assignable DTO za update. Izvodi se iz `TenantExecutionContext`.
9. Hard delete ili ponovno korišćenje `school_id` je zabranjeno.
10. Migracija ne sme nejasan legacy red proizvoljno pridružiti prvoj ili jedinoj školi; ide u exception report i ostaje van aktivnog toka.

Row-Level Security, schema-per-tenant ili database-per-tenant mogu biti dodatna zaštita, ali nisu zamena za application guard, contract test i tenant-safe relacije. Ako se koristi PostgreSQL RLS, aplikaciona konekcija ne sme imati `BYPASSRLS`; owner bypass mora biti kontrolisan/`FORCE ROW LEVEL SECURITY` gde je primenljivo; pooled connection tenant promenljiva postavlja se transakciono i ne sme preći u sledeći request.

## 8. Obavezni request guard pipeline

Za svaki zaštićeni tok redosled je:

1. M01 `AUTH-03 ValidateSession`;
2. učitati server-side `SessionTenantContext` ili zahtevati izbor;
3. proveriti `context_version`, `authorization_version` i aktuelni `tenant_access_version`;
4. učitati aktuelni `School.status`;
5. ponovo dokazati M06 ACTIVE membership u istoj školi;
6. izgraditi `TenantExecutionContext`;
7. tenant-scoped repository filtrira/vezuje svaki resource prema kontekstu;
8. application pipeline zatim izvršava M05 permission/workspace guard i M07 subject guard nad tim istim kontekstom; M03 ih ne poziva iz svog domain sloja;
9. visokorizična mutacija ponavlja verzioni/context guard neposredno pre commit-a;
10. audit/outbox dobija isti `school_id` i `correlation_id`.

Endpoint ne sme prvo učitati red samo po globalnom ID-u, pa tek zatim proveriti školu ako time error, timing, log ili serialization može otkriti postojanje. Bezbedni obrazac je tenant-scoped lookup (`WHERE school_id = active_school AND id = resource_id`) ili ekvivalent u izabranoj topologiji.

Cross-tenant ili guessed resource vraća `NOT_FOUND_SAFE`/404. `FORBIDDEN`/403 se koristi kada je resurs već pronađen u aktivnom dozvoljenom tenantu, ali M05/M07 pravo za radnju nedostaje.

## 9. Lifecycle aktivnog konteksta

`ABSENT` je odsustvo reda pre prvog izbora; trajni statusi su samo `ACTIVE` i `INVALIDATED`.

| Iz | Radnja/uslov | U | Dozvoljeno | Posledica |
|---|---|---|---:|---|
| `ABSENT` | TEN-01, validna sesija/škola/workspace | `ACTIVE` | DA | Kreira red sa `context_version=1`. |
| `ABSENT` | TEN-02 clear | `ABSENT` | DA | Idempotentni no-op receipt; nema reda. |
| `ACTIVE A/workspace1` | TEN-01 izbor A/workspace2 | `ACTIVE A/workspace2` | DA | Menja prikaz i povećava `context_version`; ne menja M05 permission uniju; čisti workspace UI cache. |
| `ACTIVE A` | TEN-01 izbor B | `ACTIVE B` | DA | Povećava `context_version`; puna client/server tenant invalidacija za A pre prikaza B. |
| `ACTIVE` | TEN-02 clear | `INVALIDATED` | DA | Razlog `USER_CLEARED`; uklanja zaštićene podatke, zadržava M01 sesiju. |
| `ACTIVE` | M01 logout/session expiry/revoke | `INVALIDATED` | DA | Razlog iz M01; context više nije upotrebljiv. |
| `ACTIVE` | membership/role/guardian opoziv koji uklanja potreban access | `INVALIDATED` | DA | Sledeći zahtev ne koristi stari pristup; ne bira se drugi tenant bez korisničkog izbora. |
| `ACTIVE` | škola deaktivirana/security revision bump | `INVALIDATED` | DA | Redovan pristup trenutno prestaje. |
| `INVALIDATED` | TEN-01, M01 sesija i novi izbor ponovo potpuno validni | `ACTIVE` | DA | Isti tekući red dobija novu reviziju, nova polja izbora i `context_version+1`; prethodna istorija ostaje u auditu. |
| `INVALIDATED` | TEN-01 nakon M01 session revoke/expiry | `INVALIDATED` | NE | `TENANT_AUTHENTICATION_REQUIRED`; nijedan kontekst ne oživljava. |
| bilo koje stanje `vN` | mutacija sa `expected_context_version != N` | nepromenjeno | NE | `TENANT_CONTEXT_STALE` ili `TENANT_SWITCH_CONFLICT`; pobedničko stanje ostaje. |
| `INVALIDATED` | identičan retry već izvršene invalidacije | `INVALIDATED` | DA | Vraća originalni receipt; ne povećava verziju ponovo. |

Nijedna promena `SessionTenantContext.status`, škole ili workspace-a ne menja M01 nalog, M06 članstvo ili M05 dodelu uloge. Nema automatskog failover-a u drugu školu jer bi to moglo promeniti poslovni kontekst bez jasne radnje korisnika.

## 10. Promena konteksta i zaštita od mešanja podataka

`TEN-01 SelectOrSwitchTenantContext` je atomska server-side radnja nad jednom sesijom:

1. prima opaque željeni school-context/workspace reference, `request_id` i `expected_context_version`;
2. zaključava trenutni session context ili daje ekvivalentan serializable rezultat;
3. ponovo izračunava dozvoljene škole, workspace opcije i aktuelni M05 effective-role set;
4. odbija nepostojeću/opozvanu kombinaciju bez otkrivanja zašto;
5. povećava `context_version` i čuva novi izbor;
6. durable beleži audit/outbox invalidaciju;
7. vraća minimalni context bootstrap i dozvoljenu početnu rutu.

Klijent pre prikaza nove škole mora:

- zaustaviti/cancelovati prethodne tenant requestove;
- obrisati query/store cache, rezultate pretrage, filtere, pagination cursore, otvorene profile/dokumente, izabrano dete, draft upload reference i optimističke izmene prethodne škole;
- ukloniti tenant PWA/cache-storage podatke koji nisu bezbedno namespace-ovani;
- zatvoriti realtime subscriptions prethodne škole;
- tek zatim učitati shell i podatke novog konteksta.

Svaki response nosi ili je interno vezan za `context_version`. Spor odgovor iz A koji stigne posle switch-a na B mora biti odbačen pre renderovanja. Service worker ne sme vratiti privatni response iz A kao offline/stale fallback u B.

Ako postoji nesačuvana forma, UI traži potvrdu napuštanja pre poziva switch komande. Nesačuvan tenant draft se ne prenosi u novu školu. Ako je mutacija već poslata, switch ne pretpostavlja ishod: čeka potvrđen rezultat ili prikazuje bezbedno stanje koje se kasnije revalidira u izvornom kontekstu.

## 11. Izolacija izvan običnog requesta

| Površina | Obavezno pravilo |
|---|---|
| list/count/search | tenant filter se primenjuje pre paginacije/agregacije; total ne broji druge škole |
| export | jedan export batch pripada jednoj školi; permissions/subject se proveravaju pri zahtevu i download-u |
| cache | ključ najmanje uključuje school, viewer/role/subject, auth/context/security verziju i query fingerprint |
| browser/PWA | privatni tenant response nije trajni shared offline asset; switch/logout/revoke čisti ili kriptografski/namespace bezbedno odvaja podatke |
| realtime | subscription se otvara iz `TenantExecutionContext`; switch/revoke zatvara kanal ili ga server odbija pri sledećoj poruci |
| storage | privatni objekat ima tenant partition/reference; signed URL se izdaje tek posle nove provere i kratko važi |
| outbox/event | svaki tenant događaj ima `tenant_id=school_id`; platform događaj koristi eksplicitni platform scope, ne `null` po navici |
| job/queue | payload i execution context nose school ID, job ID, purpose i actor/service principal; worker nikad ne koristi „trenutni globalni tenant“ |
| cron preko svih škola | platform coordinator enumeriše dozvoljene škole, zatim pravi izolovan rad po školi; failure jedne ne menja drugu |
| email/notification | recipient i sadržaj se ponovo izvode u istom tenant/subject scope-u; template cache je tenant-safe |
| audit | tenant ID je obavezan za tenant radnju; actor/support context i correlation se čuvaju bez nepotrebnog PII |
| telemetry/logovi | tenant se pseudonimizuje kada nije potreban raw ID; nema imena škole/deteta, tokena ili finansijskog sadržaja |
| reporting | tenant filter je deo izvora metrike, ne naknadni UI filter; cross-tenant platform agregat koristi poseban purpose-limited put |

User-initiated background posao ponovo proverava da je tenant aktivan i da je access evidence važeći pri izvršenju ako rezultat daje novi pristup, izvoz, poruku, finansijsku posledicu ili dokument. Ako je radnja namerno zasnovana na immutable approval snapshot-u, vlasnički modul mora to eksplicitno reći; M03 ne pretpostavlja snapshot authorization.

## 12. Komande, query-ji i interni portovi

### TEN-Q01 ListMyAvailableTenantContexts

Input: `cursor: Nullable<Code64>`, `page_size: UInt64` default `20`, raspon `1..100`. Zahteva validnu M01 sesiju. Application query coordinator kombinuje M03 School/security, M06 ACTIVE membership i M05 dozvoljene workspace opcije bez stvaranja M03→M05 domain zavisnosti. Rezultat: `{items: AvailableTenantContext[], next_cursor: Nullable<Code64>, result_version: Code64}`. Ima jednu stavku po školi i ugnježdene `workspace_options`; ne pravi duplikat tenant-a po ulozi. Sort škola je determinističan: poslednje validno korišćenje opadajuće, zatim normalizovani naziv škole, zatim opaque ID; workspace opcije se sortiraju po stabilnom display redosledu pa po `workspace_key`. Default page je 20 škola, maksimum 100. Ne vraća nedozvoljene škole, opozvane role, finansije ili razlog opoziva. Prazna lista je uspešan neutralan rezultat.

### TEN-Q02 GetActiveTenantContext

Nema body input; sesija dolazi isključivo iz M01 credential-a. Vraća `{school_id, school_mode, workspace_key, context_version, context_etag, allowed_start_route}` samo ako ceo §8 pipeline prolazi. Ne vraća permission listu kao autoritet. Stale ili invalidan kontekst se atomarno invalidira i vraća `TENANT_CONTEXT_REQUIRED` uz neutralan recovery hint, bez zaštićenog payload-a.

### TEN-01 SelectOrSwitchTenantContext

Input: `desired_school_context_ref: Identifier`, `workspace_key: Code64`, `request_id: Identifier`, `expected_context_version: UInt64`, opciono server-side `return_intent_id: Identifier`. Application coordinator potvrđuje da je key u trenutno dozvoljenim M05 workspace opcijama, pa M03 atomski čuva samo preference. Isti `request_id` i payload vraćaju isti rezultat; isti key sa drugim school/workspace kontekstom je `TENANT_IDEMPOTENCY_KEY_REUSED`. Ne menja globalni account, membership, role assignment niti efektivna prava.

### TEN-02 ClearTenantContext

Input: aktivna sesija i `request_id: Identifier`. Invalidira samo tenant izbor te sesije, povećava context version, zatvara realtime i invalidira server/browser projekcije. Ne odjavljuje M01 sesiju i ne utiče na druge sesije. Retry je idempotentan.

### TEN-03 InvalidatePersonSchoolAccess

Interni port za M02/M05/M06/M07/M17. Input: `person_id: Identifier`, `school_id: Identifier`, `reason_code: Code64`, izvorni aggregate/version, `request_id: Identifier`, `correlation_id: Identifier`. Promena membership/role/guardian izvora i durable M03 invalidation marker moraju biti ista lokalna DB transakcija ili ekvivalent bez stale-access prozora. Sledeći zahtev za tu školu fail-closed ponovo čita izvor; druge škole ostaju dostupne. M01 account-wide revoke poziva se samo ako vlasnički bezbednosni ugovor to zahteva.

### TEN-04 InvalidateSchoolAccess

Interni M04/platform port. Input: `school_id: Identifier`, `reason_code: Code64`, `source_version: UInt64`, `request_id: Identifier`, `correlation_id: Identifier`. Zaključava School/security state, povećava `tenant_access_version`, auditira i emituje `tenancy.school_access_invalidated`. Rezultat: `{school_id, tenant_access_version, invalidated_at}`. Ne mora sinhrono update-ovati svaki session red da bi bio bezbedan: svaki sledeći request poredi verziju/status i odbija stale kontekst. Outbox zatvara realtime i čisti sekundarne cache/projekcije, ali nije jedini guard.

### TEN-05 InitializeTenantSecurityState

Interni M04/M20 port pri kreiranju škole. Input: `school_id: Identifier`, `request_id: Identifier`, `correlation_id: Identifier`. Idempotentno uspostavlja `TenantSecurityState(tenant_access_version=1, version=1)` u istoj transakciji sa tenant provisioningom ili strogo ekvivalentnim recovery ugovorom. Rezultat: `{school_id, tenant_access_version=1}`. Ne daje članstvo, ulogu, pretplatu ni pristup.

### TEN-PORT-01 ResolveTenantExecutionContext

Jedini podržani application port kojim modul dobija tenant context. Zahteva deklarisani command/query ID i sprovodi §8. Ne postoji opcija `skipTenantCheck=true` u redovnom Core kodu.

### TEN-PORT-02 AssertSameTenantReferences

Pre mutacije proverava da svaki tenant-scoped referencirani ID pripada aktivnoj školi i da globalni Person/UserAccount ima potreban M06/M07 odnos. Spolja vraća safe 404/422 prema error ugovoru; detalj se čuva samo u sigurnom correlation logu.

### TEN-PORT-03 ExecuteTenantScopedJob

Kreira izolovani execution context iz job payload-a i aktuelnog School/security stanja. Platform batch se fan-out-uje po tenant-u. Worker koji ne može dokazati tenant ne izvršava poslovni upis.

### TEN-PORT-04 `SupportTenantExecutionContext`

**Ovo NIJE `AvailableTenantContext`, NIJE regularni prikazni workspace i NIJE M06 membership.** To je zaseban, request-scoped tenant execution context koji M05 Support Access koristi kada named platform support actor pristupa jednoj konkretnoj školi pod aktivnim `SupportAccessGrant`-om.

- **Autoritet pristupa:** isključivo tačan, još-važeći `SupportAccessGrant` + `SupportAccessSession` iz M05 — ne regularna school membership/role dodela.
- **Nema tihog fallback-a:** ako grant/session istekne ili se opozove, `SupportTenantExecutionContext` odmah prestaje da važi za sledeći zahtev — `TEN-PORT-01` ga ne izdaje niti obnavlja iz cache-a.
- **Ne pojavljuje se u `TEN-Q01 ListMyAvailableTenantContexts`** — support pristup nije redovan izbor škole/workspace-a korisnika.
- **Scope je tačno onaj koji je grant naveo** (exact capability/resource scope iz M05 §3.4) — širi tenant pristup od odobrenog scope-a nije dozvoljen čak i unutar iste škole.
- Svaki zahtev pod ovim kontekstom nosi vidljiv support-session marker u audit zapisu; M03 §15 audit/outbox pravila ostaju identična, uz dodatno polje `support_session_ref`.
- Promena regularnog prikaznog workspace-a od strane istog naloga (ako support actor ima i sopstveni redovni pristup nekoj drugoj školi) ne menja niti produžava `SupportTenantExecutionContext` — to su dva potpuno nezavisna konteksta u istoj sesiji.

## 13. Error katalog

| Kod | Transport | Ponašanje |
|---|---:|---|
| `TENANT_AUTHENTICATION_REQUIRED` | 401 | M01 sesija ne važi; nema tenant podatka. |
| `TENANT_INPUT_INVALID` | 400 | Tip, obavezno polje, cursor, page size ili zatvoreni code nije validan; nema tenant detalja. |
| `TENANT_CONTEXT_REQUIRED` | 409 | Potreban je izbor ili je stari izbor invalidiran; bez razloga/tuđih podataka. |
| `TENANT_CONTEXT_STALE` | 409 | `expected_context_version` ili security revision nije aktuelna; osvežiti chooser/bootstrap. |
| `TENANT_CONTEXT_NOT_AVAILABLE` | 403 | Ranije dozvoljeni kontekst više nije dostupan; redovni payload nije vraćen. |
| `TENANT_SETUP_ONLY` | 403 | Škola u pripremi ne dozvoljava redovnu radnju; nudi samo dozvoljeni onboarding. |
| `TENANT_NOT_FOUND_SAFE` | 404 | Klijentski tenant/locator nije pronađen ili nije dozvoljen; isti spoljašnji oblik. |
| `TENANT_RESOURCE_NOT_FOUND_SAFE` | 404 | Resurs ne postoji u aktivnom tenant-u ili pripada drugom; ne razlikuje se. |
| `TENANT_RELATION_INVALID` | 422 | Ovlašćeni actor unutar aktivne škole šalje reference koje ne mogu pripadati istoj dozvoljenoj transakciji, bez otkrivanja drugog tenant-a. |
| `TENANT_SWITCH_CONFLICT` | 409 | Paralelna promena konteksta; pobednički kontekst ostaje aktivan. |
| `TENANT_IDEMPOTENCY_KEY_REUSED` | 409 | Isti request ID sa drugim payload-om. |
| `TENANT_AUTHORITY_UNAVAILABLE` | 503 | School/membership/RBAC/subject autoritet nije pouzdano dostupan; zahtev je fail-closed i bez zaštićenog payload-a. |
| `TENANT_ISOLATION_FAILURE` | 500 | Nedostaje obavezni server tenant dokaz; radnja je fail-closed i correlation alert se podiže. |

M05/M07 `FORBIDDEN`/403 važi tek kada je resurs dokazano u aktivnoj školi, ali konkretna radnja ili subject nije dozvoljen.

## 14. Idempotency, concurrency i transakcione granice

- TEN-01–TEN-05 koriste stabilni `request_id` i kanonski payload hash.
- Jedinstvenost receipt-a je najmanje `(session/account ili internal-source scope, command_id, request_id)`; tenant ID je deo fingerprint-a gde postoji.
- Select/switch zaključava session context parent red ili koristi ekvivalentan compare-and-swap nad `context_version`.
- Dva taba sa istim expected version-om: tačno jedan switch uspeva; drugi dobija konflikt i mora učitati pobednički kontekst.
- Stari request sa `context_version=N` ne može commit-ovati nakon uspešnog switch-a na `N+1`. Visokorizične mutacije proveravaju context i auth/security verzije neposredno pre commit-a.
- Membership/guardian/role revoke ne čeka eventualni outbox da bi novi request bio odbijen; koristi autoritativni read-through/version guard.
- Školska deaktivacija i `tenant_access_version` bump su atomski sa M04 status promenom.
- Tenant context switch ne prebacuje nedovršenu business transakciju u drugi tenant.
- Retry nakon network timeout-a vraća isti context rezultat ili aktuelni stale konflikt; nikad ne kreira paralelni aktivni context.

## 15. Audit, outbox i telemetry

Audit događaji:

- `tenancy.context_selected`;
- `tenancy.context_switched`;
- `tenancy.context_cleared`;
- `tenancy.context_selection_rejected`;
- `tenancy.person_school_access_invalidated`;
- `tenancy.school_access_invalidated`;
- `tenancy.cross_tenant_access_denied`;
- `tenancy.isolation_invariant_failed`.

Audit nosi pseudoreference actor/session, `school_id` kada je bezbedno i relevantno, staru/novu role/context referencu, reason code, correlation i vreme. Ne sadrži child imena, finansije, dokument payload, token, cookie ili kompletnu listu drugih škola.

Obavezni outbox događaji:

- `tenancy.user_school_access_invalidated.v1`;
- `tenancy.school_access_version_changed.v1`;
- `tenancy.session_context_changed.v1`.

Envelope prati M00. Consumer je idempotentan po `event_id`/dedupe ključu. Cache/realtime/PWA projection cleanup je consumer posledica, ali request guard ostaje autoritet.

Telemetry meri context-resolution latency, izbor/switch uspeh, stale konflikte, denied cross-tenant pokušaje, job isolation failure i invalidation lag. Dimenzije koriste environment, build, command/query ID, kategoriju uloge i pseudonimizovani tenant kada je potreban; nema korisničkog ili child PII. Security-critical denied/failure događaji se ne sample-uju.

## 16. UI X03, deep-link i tri klika

X03 ostaje postojeća MVP površina „Izaberite školu i ulogu“.

Kartica prikazuje naziv/logo škole, dozvoljene prikazne workspace opcije, minimalni opis i poslednje korišćen izbor kao hint. Workspace opcija nije prikaz „trenutno jedinih dozvola”; korisnik sa više uloga zadržava uniju efektivnih M05 prava u toj školi, dok UI prikazuje fokus izabranog workspace-a. Za roditelja se mogu prikazati minimalna imena povezane dece samo kada M07 chooser projection to dozvoli. Ne prikazuju se finansije, prisustvo, dokumenti, poruke ili ukupni broj članova.

Obavezna stanja: loading, jedna škola/workspace auto-entry, više škola ili workspace opcija, nema konteksta, setup-only, ranije dostupna škola više nije dostupna, stale switch, mrežna/serverska greška i safe fallback.

Tri klika:

- jedna škola/jedan workspace: login povratak → automatski početni ekran, bez dodatnog izbora;
- više škola/workspace opcija: otvori chooser → izaberi školu → izaberi/otvori workspace, najviše tri SOKOLA akcije;
- promena iz header-a: „Promeni školu ili ulogu“ → škola → workspace/otvori, najviše tri akcije; menja fokus prikaza, ne M05 permission uniju.

Deep-link iz druge dozvoljene škole prvo prikazuje školu i traži potvrdu switch-a; sadržaj se ne preuzima/renderuje pre uspešne server potvrde. Return intent se čuva server-side ili strogo allowlist-uje; open redirect nije dozvoljen.

Javni kod/slug škole može samo pronaći tenant entry/onboarding ekran. Ne kreira nalog, članstvo, ulogu, guardian vezu ili sesiju i ne menja invite-only odluku. Odgovor mora biti enumeration-safe kada locator nije javno objavljen.

Na mobilnom uređaju kartica/role kontrola ima čitljiv naziv i dovoljno veliki hit target; chooser radi tastaturom, fokus ide na naslov posle greške, a status nije prenet samo bojom.

## 17. Kritični edge case-ovi

| Slučaj | Obavezni rezultat |
|---|---|
| vlasnik škole A i roditelj u B | dve odvojene tenant opcije; dozvole i podaci se nikada ne uniraju preko škola |
| roditelj i trener u istoj školi | jedan tenant kontekst, dve workspace opcije; M05 prava su unija aktivnih dodela u A, a M07 child scope i dalje ograničava roditeljske podatke |
| roditelj sa decom u više škola | chooser pokazuje minimalni kontekst; nakon izbora samo deca te škole |
| isto dete u dve škole | jedan globalni Person, dva odvojena membership/guardian/operativna skupa |
| dve škole istog naziva | opaque ID odlučuje; UI daje dodatni bezbedni kontekst bez curenja |
| dve škole iste Organization | nema cross-school pristupa niti zajedničkog operativnog query-ja |
| role opozvan dok je ekran otvoren | sledeći request odbijen; context očišćen ili drugi validan ponuđen |
| membership suspendovan tokom unosa | commit recheck odbija upis; UI čuva samo bezbedan lokalni draft ili ga uklanja |
| škola deaktivirana tokom job-a | novi tenant upis prestaje; posao ide u kontrolisani failed/cancelled recovery |
| dva taba menjaju školu | jedan pobednik; stale tab ne renderuje odgovor/commit iz starog context-a |
| spor response A stigne u B | context version mismatch ga odbacuje pre store/render koraka |
| offline/PWA cache posle switch-a | nema prikaza privatnih podataka A u B niti lažnog offline success-a |
| direktan ID resursa škole B iz A | 404 istog oblika kao nepostojeći ID |
| list/count/search sa praznim A | ne otkriva broj ili postojanje redova B |
| unscoped cache key | test mora pasti; takav cache se ne koristi |
| websocket ostane otvoren posle switch/revoke | kanal se zatvara/ponovo autorizuje pre sledećeg payload-a |
| user job se izvršava posle revoke-a | ponovna provera ga odbija ako vlasnički modul nema immutable approval snapshot |
| import fajl/kandidat iz B prosleđen u A | 404; worker i storage ne čitaju B |
| tenant child referencira parent iz B | DB/application guard odbija celu transakciju |
| globalni Person ima članstvo u B | škola A ne saznaje da B postoji |
| nema aktivne role uz aktivni membership | nema workspace context-a; membership nije permission |
| škola `U pripremi` | samo setup-only komande/površine |
| school code prosleđen trećem licu | locator sam ne daje pristup niti potvrđuje privatne podatke |
| Organization vlasništvo se promeni | isti `school_id`; tenant podaci i prava se ne prenose automatski |
| support korisnik ima platform role bez grant-a | nema tenant podataka; M05 Support Access je obavezan |

## 18. Migracija, backfill i recovery

Claude Code prvo popunjava repo baseline i inventariše svaku tabelu kao `GLOBAL`, `PLATFORM` ili `TENANT`. Za svaku tenant tabelu evidentira owner modul, tenant putanju, unique/FK/indekse, repository/query i job/cache/storage korišćenje.

Migracija se radi fazno:

1. dodati nullable/derived tenant kolonu samo kao prelaz ako je potrebna;
2. backfill isključivo iz jednoznačne postojeće FK putanje;
3. nejasne/orphan/cross-school redove staviti u exception report i blokirati iz aktivnog toka;
4. dodati tenant indekse i composite unique targete;
5. dodati composite FK/CHECK/application guardove;
6. prebaciti sve read/write query-je, cache, job i storage reference na tenant execution context;
7. tek posle nula nejasnih aktivnih redova postaviti `NOT NULL`/stroga ograničenja;
8. opozvati/obrisati stare session tenant izbore pri cutover-u i zahtevati novu proveru;
9. pokrenuti dvotenantsku sigurnosnu matricu i migration rehearsal na praznoj i podržanoj prethodnoj bazi.

Ne raditi automatski merge škola, osoba ili tenant podataka. Ako DB ograničenje ne može bezbedno da se vrati, dokumentuje se forward-recovery; rollback nikad ne vraća poznato cross-tenant propusno ponašanje. Backup/restore dokaz i RPO/RTO pripadaju M21.

## 19. Feature/capability ponašanje

- `tenancy.enforcement`: obavezno ON i nije korisnički/tenant feature flag;
- budući mySOKOLA/Operations capability flag nikad ne zaobilazi M03;
- tenant allowlist određuje aktivaciju proizvoda, ne pristup podacima;
- subscription entitlement iz M04 određuje dostupnost funkcije, ne identitet ili cross-school pravo;
- developer/test bypass je dozvoljen samo u izolovanom test runner-u sa sintetičkim podacima i ne sme postojati u deployable production kodnoj putanji;
- pri nedostupnosti membership/permission/security store-a zaštićena radnja fail-closed, bez stale „allow“ rezultata.

## 20. Merljivi tehnički minimum

- authorization freshness nakon uspešnog revoke/deactivate commit-a: nula dozvoljenih novih requestova;
- `TEN-Q01` default page 20, hard maximum 100;
- svaki tenant query ima determinističan sort i bounded pagination;
- svaki cache/job/outbox/storage zapis ima proverljivu tenant dimenziju ili eksplicitni platform/global tip;
- svaki deploy ima automatizovan cross-tenant test sa najmanje dve škole;
- performanse context resolvera, DB topologija, RLS izbor i cache TTL se popunjavaju iz stvarnog repoa u `CURRENT-CODE-BASELINE`; ne smeju oslabiti nultu stale-access granicu;
- RPO/RTO, retention i produkcioni kapacitet ostaju M21/M17 odluke i ne blokiraju kodiranje na sintetičkom stagingu.

## 21. Referentni sigurnosni principi

Ovaj ugovor primenjuje sledeće savremene obrasce bez vezivanja za vendor:

- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) zahteva object-level authorization u svakoj funkciji koja koristi klijentski identifikator da pristupi zapisu;
- [AWS SaaS Tenant Isolation Strategies](https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/saas-tenant-isolation-strategies.html) tretira izolaciju kao poseban, fundamentalni SaaS mehanizam, ne isto što i obična autentifikacija;
- [Microsoft multitenant identity guidance](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/identity) razlikuje korisnički identitet od tenant konteksta i preporučuje praćenje/proveru tenant identiteta;
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), kada se izaberu, daju default-deny bez politike, ali superuser/owner/`BYPASSRLS` izuzeci zahtevaju dodatnu kontrolu.

Normativni autoritet ipak ostaju SOKOLA M00–M03 ugovori; spoljne reference ne menjaju poslovni scope.

## 22. Definition of Done

M03 je implementaciono završen tek kada:

1. postoji jedan School tenant model i nema paralelnog `Tenant` mastera;
2. svaki zaštićeni application ulaz dobija provereni `TenantExecutionContext`;
3. aktivni kontekst je jedna škola + jedan prikazni workspace po sesiji; workspace nije permission filter, a M05 efektivna prava ostaju unija aktivnih dodela u toj školi;
4. auto-selection, X03 i context switch rade prema §6/§16;
5. switch/revoke/deactivate sprečavaju stale render, request, job i realtime pristup;
6. tenant tabele, relacije i unique ograničenja prolaze DB integration testove;
7. list/count/search/export/cache/storage/jobs/outbox/reporting prolaze dvotenantske negativne testove;
8. Organization, school slug/kod i globalni Person ne daju implicitno pravo;
9. cross-tenant ID vraća safe 404, a nedostatak prava u aktivnom tenant-u kontrolisani 403;
10. migracija daje determinističan exception report bez automatskog spajanja;
11. audit/outbox/telemetry ne sadrže nepotreban PII i nisu jedini security guard;
12. svih M03 QA scenarija iz pratećeg dokumenta imaju mapu na automatizovani test/evidence;
13. repo/commit/migration head, izabrana isolation topologija i stvarne test komande vraćaju se tek u završnom Claude Code izveštaju, ne izmišljaju u dokumentaciji;
14. koriste se samo sintetički podaci do odobrenja realnog pilota.
