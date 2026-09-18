---
tip: modulni-ugovor
modul-id: M00
status: SPEC_CANDIDATE
verzija: 2.1
datum: 2026-09-15
vlasnik-dokumenta: vlasnik-proizvoda
zavisnosti:
  - DCR-20260907-01
---

# M00 — Arhitektura, moduli i zavisnosti

## 1. Arhitektonski cilj

SOKOLA OS se razvija kao bezbedan multi-tenant modularni monolit dok stvarni zahtevi ne dokažu potrebu za izdvajanjem servisa.

Obavezno ponašanje:

- jedan kanonski identitet osobe i naloga;
- jedan tenant model;
- jedan vlasnik svakog poslovnog podatka;
- stroge modulne granice;
- relacione transakcije za kritične tokove;
- transakcioni outbox za asinhrone posledice;
- server-side autorizacija za svaku komandu i query;
- mogućnost da se modul kasnije izdvoji bez pravljenja paralelnih master tabela sada.

Mikroservisi se ne uvode samo zato što dokumentacija koristi izraz „bounded context“. Izdvajanje je dozvoljeno tek kada postoje merljiv razlog, vlasnik servisa, deployment/observability kapacitet, ugovor kompatibilnosti i migracioni plan.

## 2. Odnos prema postojećem repozitorijumu

Claude Code prvo utvrđuje stvarnu arhitekturu. Ne pretpostavlja framework, ORM, bazu, auth provider, storage, queue, API stil ili deployment platformu. Postojeći repo je tehnička početna tačka; SOKOLA ugovori su autoritet za zahtevano ponašanje.

### 2.1. Pravilo očuvanja

Ako postojeći repo već ima zdravo rešenje koje ispunjava poslovne, bezbednosne i testne kriterijume:

- zadržati ga;
- mapirati ga na kanonski modul;
- dodati ili popraviti test;
- ne raditi masovno preimenovanje samo zbog dokumentacije.

### 2.2. Pravilo korekcije

Postojeće rešenje se menja kada dokazivo:

- curi podatke između škola ili korisnika;
- oslanja autorizaciju samo na UI;
- duplira source of truth;
- krši zaključani lifecycle ili novčani invariant;
- nije idempotentno tamo gde retry može napraviti duplikat;
- nema podržanu migraciju;
- koristi placeholder/izmišljene podatke kao stvaran backend rezultat;
- ne može biti pokriveno determinističnim testom.

### 2.3. Tehnička odluka programera

Programer bira fizičku realizaciju: REST/GraphQL/RPC/server actions, endpoint strukturu, framework, ORM, folder organizaciju, locking, queue/jobs, cache, storage i deployment. Dokumentacija ne propisuje alat kada ugovor može jednako bezbedno da se sprovede postojećim stackom.

Izbor programera je prihvatljiv kada:

- čuva sve poslovne invariante;
- sprovodi server-side tenant/permission/subject guardove;
- daje proverljiv contract i automatizovane testove;
- ima podržanu migraciju i recovery;
- ne pravi paralelni source of truth;
- ne širi ili sužava MVP bez DCR-a.

## 3. Minimalni fizički oblik sistema

Stvarni nazivi procesa mogu biti drugačiji, ali sistem mora imati sledeće odgovornosti:

| Sloj | Obavezna odgovornost |
|---|---|
| Web/PWA | responsive UI, rute, dozvoljena client validacija, bez auth autoriteta na klijentu |
| Application/API | komande, query-ji, server guardovi, transakcije, error contract |
| Domain moduli | poslovna pravila, lifecycle, invarianti, source-of-truth vlasništvo |
| Relaciona baza | tenant/FK/unique/check ograničenja, transakcije, migracije, audit/outbox |
| Privatni object storage | dokumenti i import fajlovi, bez javnog trajnog URL-a |
| Job runner | retryable background poslovi sa idempotency/lock/recovery ugovorom |
| Outbox/consumer | pouzdana objava događaja i projekcija bez duple posledice |
| Observability | strukturirani logovi, metrics, correlation, alerti, bez tajni i nepotrebnog PII |

Programer bira i zadržava bazu prema stvarnom repou. Izabrana baza mora podržati potrebne transakcije, indekse, ograničenja, migracije, konkurentnost i decimalni tip bez gubitka poslovnog ugovora. M00 ne propisuje vendor baze.

## 4. Kanonski registar modula

Oznake `M00-M34` su arhitektonski moduli. UI identifikatori uvek nose prefiks `UI-`; modulni identifikatori u traceability registru nose `MOD-`.

Kolona `schema prerequisites` navodi samo fizičku FK/constraint zavisnost. `Read/events/orchestration` navodi ugovorne odnose koji ne daju pravo direktnog upisa u tuđi modul.

### 4.1. Aktivni M00–M16 Core registar

| Modul | Jedina odgovornost | Schema prerequisites | Read/events/orchestration | Horizont |
|---|---|---|---|---|
| `M00` | scope, zajednički ugovori, DoD | nema | nema | H0 |
| `M01` | account, provider identity, session, revocation | M06 `Person` | M00 | H0 |
| `M02` | invite-only poziv i atomska aktivacija | M04 `School`, M06 `SchoolPersonProfile` | M01, M03, M04, M05, M06, M07 kroz application orchestration | H0 |
| `M03` | tenant security/context/isolation | M01 `Session`, M04 `School` | M06 membership i M05 workspace samo kroz application read composition | H0 |
| `M04` | `Organization`, `School`, owner term, SaaS subscription/commercial foundation | core nema; owner cross-ref FK-ovi se dodaju u završnoj deferred-constraint fazi posle M02/M05/M06 | M03 init i M06/M09 usage facts samo kroz neutralne application coordinatore; M02 revoke port | H0 foundation |
| `M05` | authorization policy, role/grant i Support Access | M06 `SchoolMembership` | M01 session, M03 tenant, M04 entitlement, M06 membership facts, M07 subject facts | H0 |
| `M06` | `Person`, school membership i neutralni participant/staff profili | M04 `School` | M01 account indikator samo kroz application/query composition; M06 domen ne čita M01 niti poziva M05 | H0 |
| `M07` | family, guardian relation, contact/payer designation i child/payer scope | M04 `School`, M06 `SchoolMembership` | M06 facts; M05 čita M07 subject port, ne obrnuto | H0 |
| `M08` | `Branch`, `Program`, `Location`, online access, `Space`, jedini occupancy master | M04 `School` | M05 guard kroz application layer; M10/M16 koriste transakcioni occupancy port | H0 |
| `M09` | `Group`, enrollment/transition/transfer i staff assignment | M06, M08 | M10/M11 koriste as-of read; cena je isključivo M12 | H0 |
| `M10` | lokalna recurrence namera, occurrence, Group/Staff conflicts | M08, M09 | M08 occupancy u istoj transakciji; emituje outbox, ne zove M14 | H0 |
| `M11` | frozen roster, attendance/corrections i jedini H0 offline mutation queue | M09, M10 | M05 offline lease/permission; emituje minimalni outbox bez automatske attendance poruke | H0 |
| `M12` | fee/version/assessment, porodične obaveze/uplate/alokacije/credit/refund | M04, M06, M07 | M08/M09/M16 billing-scope read; emituje outbox; ne menja source modul | H0 |
| `M13` | ručna komunikacija, draft/publish/isporuka | M04, M06 | M07/M09 audience read; ne poseduje sistemske notifikacije | H0 |
| `M14` | `SystemNotification` i `AttentionItem` | M01, M04 | `CONSUMES_EVENT` od M05, M10, M12, M13 i M16; M13 current draft-warning eligibility kroz read-only port | H0 pomoćno |
| `M15` | dokument, immutable verzija, access i acceptance evidence | M04, M06 | M07/M09 scope read; M15 sme read-only da validira M16 EVENT scope | H0 |
| `M16` | Events Light lifecycle | M04, M08, M09 | M10 schedule read; neutralni application coordinator može orkestrirati M16+M12 owner portove; emituje događaje, ne poziva M12/M14/M15 | H0 |

### 4.2. Foundation migracioni redosled

Minimalni redosled kreiranja schema ankera je: M04 `School` -> M06 `Person`/`SchoolMembership` -> M01 -> M03 -> M05 -> M07 -> M02 -> M04 deferred cross-module constraints. Odloženi M04 FK-ovi ka M06/M02/M05 postaju obavezni pre aktivacije i koriste `DEFERRABLE` semantiku kada atomska Foundation transakcija kreira obe strane. Ovo nije redosled čitanja dokumentacije niti dozvola za parcijalno uključivanje use-case-a.

M02 acceptance je poslednji Foundation use-case: application sloj orkestrira M01, M03, M04, M05, M06 i M07 u jednoj lokalnoj transakciji modularnog monolita. Nijedan od tih domena ne upisuje direktno u tabelu drugog modula mimo vlasničkog command porta.

M05 ima schema i read zavisnost ka M06 zato što `RoleAssignment` referencira `SchoolMembership`. M01 ima schema zavisnost ka M06 zato što `UserAccount.person_id` referencira `Person`. M06 domen ne čita M01 i nema zavisnost ka M05; account indikator se komponuje izvan M06, a M06 use-case se poziva tek nakon application-level M01/M03/M05 guardova. Ovo su jedini kanonski smerovi; suprotni smerovi su zabranjeni.

M03 ne zove M05 iz domain sloja. Available-school/workspace odgovor je application read composition. Tenant autoritet ostaju M01 session + M04 School + M03 security state; workspace nikad nije authorization dokaz.

### 4.3. Operational Core migracije i smer zavisnosti

Posle Foundation-a minimalni ugovorni/migracioni redosled je: M08 → M09 → M10 → M11 → M16 → M12 → M15 → M13 → M14. M12 FK osnova prema M04/M06/M07 već postoji; M08/M09/M16 scope se validira read-only portom i tipiziranim source ID-em, bez upisa u source modul. M15 EVENT scope čita M16, a M13 document reference čita M15. M14 dolazi poslednji kao consumer i nijedan producer ga ne poziva.

- M08 ne čita M10; M10 je consumer M08 occupancy port-a.
- M09 ne čita M10/M11/M12; schedule, attendance i cena ostaju njihovi domeni.
- M10 ne čita M11; M11 uzima occurrence i as-of roster.
- M11 ne poziva M12 radi obračuna; attendance nije H0 billing input.
- M12 ne menja enrollment/event kada napravi assessment/obligation. Neutralni application coordinator može u jednoj lokalnoj transakciji orkestrirati M09/M16 owner port i M12 owner port; M09/M16 ne pozivaju M12, M12 ne poziva nazad producer tokom iste komande i nema reverse domain import-a.

### 4.4. Core event granica

M16 upisuje minimalni domain event u transakcioni outbox u istoj transakciji sa poslovnom promenom. M14 događaj konzumira asinhrono i idempotentno. M16 ne poziva M14 komandu, query ili adapter i ne čeka isporuku. M15 može read-only da validira EVENT scope; M16 nema reverse dependency ka M15.

### 4.5. Završni Core moduli

| Modul | Vlasništvo | Schema osnova | Integracija |
|---|---|---|---|
| M17 | Privacy purpose, consent, DSAR, retention, legal hold | M04, M06, M15 | Owner portovi i M15 evidence application coordinator; nema reverse domain poziva |
| M18 | Report definicije, projekcije, snapshot, export | M04 | Read/event consumer; ne menja owner podatke |
| M19 | Shell, navigation, search projection, PWA transport | M04 | Batch read composition; M03 je context autoritet |
| M20 | Onboarding progress i import staging/execution | M04 | Lokalne owner transakcije preko application coordinator-a |
| M21 | Audit/outbox transport, jobs, operativni dokazi | M04 | Platform interfejsi od početka; M17 policy ulazi kao versioned application snapshot; business module ostaje event owner |

Ova tabela sama nije dokaz acikličnosti runtime poziva. Topološki redosled se proverava odvojeno po tipu zavisnosti prema §4.5.1, ne samo po broju modula.

#### 4.5.1. Obavezna klasifikacija svake međumodulske veze

| Tip veze | Smer i dozvola | Pravilo ciklusa |
|---|---|---|
| `SCHEMA_PREREQUISITE` | tabela/constraint consumer-a → schema owner | mora biti DAG; deferred FK menja vreme migracije, ne smer vlasništva |
| `DOMAIN_READ_OR_CALL` | domain consumer → javni owner read/command port | mora biti DAG; nema reentrantnog owner→consumer povratka u istoj putanji |
| `APPLICATION_GUARD` | use case → M01 session → M03 context → M05 permission → owner resource/subject guard | nije domain import; guard modul ne poziva zaštićeni domen nazad |
| `APPLICATION_COORDINATOR` | neutralni application use case orkestrira dva ili više owner porta | hyperedge, ne vlasništvo; nijedan owner domen ne zavisi od coordinator-a niti upisuje tuđu tabelu |
| `EVENT_CONSUMPTION` | producer → M21 outbox/transport → consumer inbox | asinhrono i at-least-once; producer ne zove consumer, consumer ne potvrđuje producer command |
| `PLATFORM_INTERFACE` | poslovni modul koristi M00/M21 audit/outbox/job/storage port; infrastruktura implementira port | dependency inversion; M21 ne importuje poslovni consumer radi callback-a |

Posebno zaključane klasifikacije:

- M04 subscription usage je `APPLICATION_COORDINATOR`: coordinator čita M06/M09 as-of facts i poziva M04 snapshot command; nema M04 domain→M09 poziva, pa M09→M04 School guard ne pravi ciklus.
- M02 activation, M04 provisioning, M10/M16 occupancy, M15/M17 consent evidence i M20 row execution su application coordinatori sa jednom lokalnom transakcijom modularnog monolita.
- M17 retention/legal-hold policy se M21 disposition-u predaje kao immutable versioned snapshot. M21 ne poziva M17 domen tokom obrade sopstvenog reda; M17 koristi M21 platform port, ne M21 business read model.
- M14/M18/M19 projekcije su `EVENT_CONSUMPTION`; njihov read model ne daje producer-u reverse zavisnost.
- `schema-zavisnosti` i `read-portovi` frontmatter polja smeju sadržati samo prva dva odgovarajuća tipa. `application-*`, `event-*` i platform edges moraju biti odvojeno imenovani, nikad ugurani u read listu da bi se sakrio ciklus.
- `izlazni-portovi-za`/`application-korisnici` je izvedeni consumer indeks, ne reverse dependency: mora kao minimum sadržati svaki aktivni modul koji owner-a navodi u `read-portovi` ili `consumes-events-from`, a sme dodatno navesti jasno dokumentovan application, platform ili budući consumer. Nedostajući aktivni consumer je validator greška; dodatni consumer ne daje pravo direktnog table write-a.

### 4.6. Operations Light

| Modul | Cilj | Tvrde zavisnosti | Horizont |
|---|---|---|---|
| `M22` Staff & Work | angažovanja i evidencija rada | M05, M06, M09, M10, M21 | H3 |
| `M23` Places & Resources | prostor/resurs i rezervacije | M08, M10, M21 | H3 |
| `M24` Assets & Inventory | sredstva, zalihe, izdavanje i movement ledger | M03, M05, M16, M21, M23 | H3 |
| `M25` Event Logistics & Transport | prevoz, manifest, logistički zadaci i incidenti | M16, M22–M24 | H3 |
| `M26` Vendors/Procurement/Operational Costs | dobavljači i operativni troškovi, ne računovodstvo | M03, M05, M15, M16, M21 | H3 |

### 4.7. Post-MVP i budući proizvodi

| Modul | Cilj | Tvrde zavisnosti | Horizont |
|---|---|---|---|
| `M27` SOKOLA Link | javne stranice škole/događaja preko objavljene revizije | M08, M16, M17, M21 | H3 |
| `M28` mySOKOLA | privatni parent-first portal | schema: M01/M04/M07; request/authorization: M01/M03–M07; owner read/command: M06/M07/M10–M17; shell: M19; platform: M21; nema M02/M08/M09/M18/M20 hard dependency | H1 |
| `M29` Skills Light | framework i privatne procene veština | M06, M09–M11, M17, M28 | H3 |
| `M30` Events Pro | višednevni događaji, agenda, čekanje, logistika | M16, M22–M29 po capability-ju | H3 |
| `M31` Sponsors | sponsor agreement, paketi, delivery i fee evidencija | M16, M27, M30, M32 | H3 |
| `M32` Commerce/Settlement | order, charge, refund, payout/settlement | M12, M16, M17, M21 | H3 |
| `M33` Venue/Freelancer Network | verifikovani pružaoci usluga i kontrolisana konverzija | M06, M08, M22–M32 | H3 |
| `M34` Growth CRM | inquiry, lead, consent i konverzija | M06, M13, M17, M27 | H3 |

## 5. Source-of-truth vlasništvo

| Podatak | Jedini master vlasnik | Dozvoljena projekcija/reference | Zabranjeno |
|---|---|---|---|
| osoba i kontakt | M06 (`Person`, isključivo) | portal/growth purpose-limited snapshot | Person po proizvodu; M01 kao vlasnik Person podatka |
| nalog, OIDC i sesija | M01 | auth/session view | OIDC na `Person` i drugi nalog u portalu |
| guardian veza | M07 | mySOKOLA access projection | client-side guardian autorizacija |
| škola | M04 | M03 tenant security/context; ostali moduli referenciraju | M03 ili drugi modul kao parallel `School` owner |
| tenant security/context | M03 | request/job execution context | paralelni `Tenant` master |
| porodica i guardian/payer foundation | M07 | M05/M12/mySOKOLA purpose-limited scope | Family kao authorization dokaz ili finance ledger |
| ogranak/program | M08 | Events/Portal/Link/Operations reference | paralelna branch/program tabela u M04/M09 |
| grupa | M09 | Events/Portal/Link/Operations reference | paralelna group tabela |
| lokacija | M08 | Schedule/Events/Operations reference | odvojeni `Hall` ili `Venue` master za isti objekat |
| termin | M10 | Portal/reporting projection | portal menja termin direktno |
| prisustvo | M11 | Portal/reporting projection | izvedena kopija kao master |
| obaveza/uplata/alokacija | M12 | portal/reporting neutralna projekcija | Commerce/Operations menja MVP finance |
| ručna komunikacija | M13 | Published-only portal projection | automatska `SystemNotification` kao M13 zapis |
| sistemske notifikacije | M14 | autorizovana korisnička projekcija | source modul sinhrono poziva M14 |
| dokument i verzija/dokaz prihvatanja | M15 | autorizovana reference/snapshot metadata | javni Link direktno čita private storage |
| događaj/prijava | M16 | Link/Portal/Logistics reference/projection | novi Event po proizvodu |
| import candidate | M20 | samo preview/result | candidate tretiran kao Person pre execute-a |
| publication revision | M27 | public renderer | public renderer čita privatne tabele |
| portal projekcija | M28 | samo read model | portal postaje auth/finance/attendance master |

### 5.1. Event poreklo bez paralelnog modela

Kanonski `Event` podržava:

- `SCHOOL_ORGANIZED` — školu kao organizatora;
- `EXTERNAL_ORGANIZER` — gostujući/spoljni događaj na kome škola vodi sopstveno učešće.

`origin_type` je nezavisan od lokacije. Za spoljni događaj dozvoljeni su minimalni `external_organizer_name` i `external_reference` snapshot/reference podaci. Ne uvodi se drugi `GuestEvent`, drugi tenant ili automatski nalog spoljnog organizatora.

## 6. Zavisnosti u kodu

### 6.1. Dozvoljen smer

- UI/transport poziva application use case.
- Application use case koristi javni interfejs svog ili nižeg modula.
- Domain ne zavisi od web frameworka, UI-a ili provider SDK-a.
- Infrastruktura implementira port/interfejs koji modul poseduje.
- Reporting i portal čitaju dozvoljene query modele/projekcije.
- Future modul referencira Core stabilnim ID-em i javnim ugovorom.

### 6.2. Zabranjen smer

- direktan upis u tabelu drugog modula;
- UI koji sam odlučuje da je korisnik autorizovan;
- Finance koji importuje UI kod;
- Events koji pravi novu Person/Location evidenciju;
- mySOKOLA koji direktno menja attendance ili payment status;
- Link koji query-uje privatne Core tabele u javnom requestu;
- shared `utils` paket koji sadrži skrivenu poslovnu logiku više modula;
- circular module dependency rešena globalnim mutable servisom.

## 7. Predložena repo organizacija

Claude mapira ovo na postojeću strukturu; ne mora masovno da preimenuje repo.

```text
apps/
  web-or-pwa/
  api-or-server/
modules/
  identity/
  tenancy/
  access-control/
  people-relationships/
  school-structure/
  groups/
  schedule/
  attendance/
  finance/
  communication/
  documents/
  events/
  privacy/
  reporting/
  onboarding-import/
  portal-mysokola/
  operations/
platform/
  database/
  auth-adapter/
  storage/
  jobs-outbox/
  telemetry/
  configuration/
contracts/
  api/
  events/
  errors/
tests/
  unit/
  integration/
  contract/
  e2e/
  security/
  restore/
```

Ako je repo full-stack framework sa kolociranim rutama, granice se mogu sprovesti package/folder pravilima, import pravilima, servisnim interfejsima i testovima. Struktura direktorijuma sama po sebi nije acceptance.

## 8. Kanonske tehničke konvencije

### 8.1. Identifikatori

- svi spoljni ID-evi su opaque;
- klijent ne određuje tenant autoritet slanjem `school_id`;
- server razrešava aktivni tenant iz autorizovanog membership/context ugovora;
- stabilni ID se ne reciklira;
- public slug nije dokaz postojanja privatnog resursa.

### 8.2. Tenant polja i veze

- svaki tenant poslovni zapis nosi `school_id` direktno ili ga jednoznačno dokazuje kroz obaveznu FK putanju;
- kritične cross-entity veze koriste composite tenant proveru ili ekvivalentan DB/application guard;
- list/count/search/export/cache/job ponovo primenjuju tenant scope;
- support context se ne tretira kao globalni bypass.

### 8.3. Vreme

- sistemski timestamp se čuva kao timezone-aware UTC instant;
- škola ima kanonsku IANA vremensku zonu, podrazumevano `Europe/Belgrade` samo kada je zaista postavljena;
- schedule čuva informacije potrebne da ponavljanje ostane vezano za lokalno školsko vreme;
- datum i vreme u UI-u prikazuju se u vremenskoj zoni škole;
- DST ambiguous/nonexistent local time mora dati determinističnu validaciju, ne tihu promenu termina.

### 8.4. Novac

- DB i domain koriste `NUMERIC(18,2)` ili strogo ekvivalentan decimalni tip;
- API prenosi iznos kao decimalni string;
- valuta je `RSD`;
- zaokruživanje je `ROUND_HALF_UP` na dve decimale;
- binary floating point i paralelni minor-unit master model su zabranjeni.

### 8.5. Istorija i brisanje

- poslovna istorija se ne prepisuje kada je potrebna za audit/izveštaj;
- lifecycle tranzicija ima actor, vreme, razlog gde je potreban i verziju;
- fizičko brisanje je dozvoljeno samo kada retention/privacy ugovor to izričito dozvoli;
- arhiviranje ne sme ponovo otvoriti unique konflikt koji sprečava razumnu ponovnu upotrebu imena/šifre, ako poslovno pravilo to dozvoljava;
- correction/reversal je eksplicitna nova radnja, ne skrivena izmena istorije.

### 8.6. Optimistic concurrency

Entitet sa konkurentnim mutacijama nosi `version` ili ekvivalent. Stale zahtev vraća kanonski konflikt i ne radi automatski merge ako merge nije eksplicitno definisan.

### 8.7. Kriptografska zaštita i rotacija ključeva

Logički tip `CiphertextEnvelopeV1` je autentifikovano enkriptovan, samopisujući binary envelope. Sadrži najmanje `envelope_version`, allow-listed `algorithm_id`, managed `key_id` ili `key_version`, jedinstveni nonce, ciphertext i authentication tag. Polje nazvano `*_ciphertext` bez zasebnog `*_key_version`/`*_key_ref` čuva ceo ovaj envelope, ne gole enkriptovane bajtove. Kada su verzija ili key ref zasebne kolone, moraju biti null/non-null zajedno sa ciphertext-om i moraju se poklapati sa envelope header-om.

Associated data obavezno vezuje ciphertext najmanje za `module_id`, `entity_type`, `field_name`, stabilni record ID, schema/envelope verziju i `school_id` za tenant podatak ili literal `PLATFORM` za platform podatak. Kopiranje ciphertext-a u drugi tenant, red, polje ili tip zato mora pasti authentication proveru. Key material je samo u managed KMS/secret granici; nije u DB redu, object key-u, paketu, logu, eventu, telemetry-ju ili error-u. Missing/retired key, unknown algorithm/envelope verzija ili authentication failure daju fail-closed safe error i security incident; nema plaintext, global-key ili „pokušaj starim formatom” fallback-a.

Rotacija ima dokaziv write/read skup i ne briše stari ključ dok ijedan važeći red/artifact referencira njegovu verziju. Re-encryption je tenant-batched, CAS/fenced i proverava AAD pre zamene; cutover zahteva 100% reconciliation aktivnih redova. Za deterministički lookup niskoentropijskog ili osetljivog sadržaja koristi se domain-separated tenant-keyed HMAC sa sačuvanom key verzijom, nikad raw SHA-256. Raw SHA-256 ostaje dozvoljen za javni/objavljeni immutable dokument, već randomizovan ciphertext ili object-byte integritet kada se hash ne koristi kao identity/linking ključ i nije oracle o privatnom sadržaju.

## 9. Command ugovor

Svaka poslovna mutacija mora definisati:

1. stabilni command ID/naziv;
2. actor i aktivni tenant;
3. input šemu i normalizaciju;
4. početno stanje;
5. role/permission i subject guard;
6. poslovne invariante;
7. transakcioni obim;
8. idempotency ključ i fingerprint payload-a;
9. concurrency očekivanje;
10. dozvoljenu tranziciju;
11. audit zapis;
12. outbox/integration događaje;
13. report/projection posledice;
14. retry ponašanje;
15. bezbedan rezultat;
16. kanonske error kodove i HTTP mapiranje;
17. automatizovane testove.

Isti idempotency ključ i isti payload vraćaju isti poslovni rezultat. Isti ključ sa drugim payload-om vraća konflikt. Idempotency nije zamena za unique constraint i transakciju.

## 10. Query ugovor

Svaki query/list/search/count/export mora:

- razrešiti actor, tenant, permission i subject scope server-side;
- koristiti determinističan sort;
- imati limit/paginaciju;
- ne otkrivati postojanje tuđeg resursa;
- ne vraćati polja „za svaki slučaj“;
- deklarisati freshness ako čita projekciju;
- imati test cross-tenant, revoked-access i empty-result ponašanja;
- ne koristiti cache ključ bez tenant/viewer/subject dimenzije.

## 11. API i greške

Core dobija proverljiv API/application contract kroz module; ne ostaje samo Operations API dokumentovan. Fizički stil je `PROGRAMMER_DECISION` i prati postojeći repo:

- REST → OpenAPI ili strogo ekvivalentan machine-readable ugovor;
- GraphQL → verzionisana schema, resolver auth i contract testovi;
- RPC/tRPC → izvezena contract schema i compatibility testovi;
- server actions/in-process use cases → eksplicitne input/output šeme, stabilni command/query ID-evi i integration testovi;
- integration events → verzionisana event schema.

Ne uvoditi paralelni REST sloj samo da bi se proizveo OpenAPI ako sistem koristi drugi validan ugovorni stil.

Kanonske kategorije:

- `VALIDATION` → 422;
- `UNAUTHENTICATED` → 401;
- `FORBIDDEN` → 403;
- `NOT_FOUND_SAFE` → 404;
- `CONFLICT` → 409;
- `STALE_VERSION` → 409;
- `RATE_LIMITED` → 429;
- `PROVIDER_RETRYABLE` → 502/503 po jednom kanonskom kodu;
- `PROVIDER_TERMINAL` → mapirano po eksplicitnom kodu;
- `INTERNAL_SAFE` → 500.

Jedan kanonski error kod ima jedan HTTP status. Error response vraća `code`, bezbednu poruku, `correlation_id` i opcione bezbedne field greške. Stack trace, SQL, tajna, token i tuđi identifikatori se ne vraćaju korisniku.

## 12. Transakcije i asinhrone posledice

U jednoj ACID transakciji ostaju:

- finansijska uplata/alokacija/reversal poslovna posledica;
- group transfer koji zatvara stari i otvara novi enrollment;
- attendance session i pripadajući zapisi ako se čuvaju zajedno;
- capacity/reservation provera i potvrda;
- publish/withdraw revizija i outbox marker;
- import row target mutation i row result marker prema definisanom batch ugovoru.

Email, telemetry provider, public cache purge, portal projection i slične spoljne posledice idu preko durable outbox/job mehanizma kada ne mogu bezbedno biti deo transakcije.

Direktan „fire and forget“ async poziv bez durable zapisa nije dozvoljen za važnu poslovnu posledicu.

## 13. Integration event envelope

Svaki događaj najmanje sadrži:

- `event_id`;
- `event_type`;
- `schema_version`;
- `occurred_at`;
- `producer`;
- `school_id` za school-scoped događaj ili eksplicitni `scope_kind=PLATFORM` bez lažnog School ID-a;
- `aggregate_type`;
- `aggregate_id`;
- `aggregate_version`;
- `actor_id`/`actor_type` kada postoji;
- `correlation_id`;
- `causation_id`;
- `source_request_id` kada događaj potiče iz komande, dok je `event_id` obavezni consumer dedupe ključ;
- minimalni payload bez nepotrebnog PII.

Potrošač mora biti idempotentan. Breaking schema promena dobija novu major verziju, compatibility period, backfill/migration plan i registar potrošača.

## 14. Bezbednosni minimum po modulu

Testirati najmanje:

- IDOR/BOLA;
- cross-tenant ID i list/count/search/export;
- revoked membership/guardian;
- privilege escalation i mass assignment;
- CSRF/session i token replay;
- injection i XSS;
- file upload/content sniffing/decompression bomb;
- signed URL i storage path guessing;
- webhook/provider replay gde postoji;
- cache isolation;
- secret i PII redaction;
- rate limit/brute force na auth i javnim rutama;
- support access expiry i audit.

## 15. Testna piramida i dokaz

| Nivo | Obavezni dokaz |
|---|---|
| unit | domain invariant i lifecycle pravilo |
| integration | DB constraint, transakcija, repository i adapter |
| contract | API/event/error schema |
| e2e | uloga-specifičan radni tok kroz UI/API |
| security | tenant/subject/permission negativni scenariji |
| import | parser, duplicate, replay, malicious file, partial result |
| resilience | provider/job retry, worker crash, stale version |
| restore | podizanje podržanog backup-a i verifikacija podataka |

Izjava „radi“ nije evidence. Prihvatljiv dokaz je automatizovani output, code pointer, migracija/schema, kontrolisan screenshot/video za UX, log/metric query bez PII ili restore zapis.

## 16. Arhitektonske zabrane

Programer i Claude Code ne smeju:

- praviti drugi `Person`, `UserAccount`, `School`, `Location`, `Group`, `Event`, `PaymentRecord` ili guardian master;
- uvoditi mikroservis bez dokazivog razloga;
- hardkodirati nerešene produkcione ili pravne vrednosti;
- koristiti klijentski tenant/role kao autoritet;
- računati novac binary floating point tipom;
- uključiti future modul po defaultu;
- sakriti neimplementiranu funkciju lažnim uspehom;
- vraćati placeholder KPI kao stvarni izveštaj;
- tretirati import preview kao kanonski upis;
- pretvoriti mySOKOLA projekciju u master;
- mešati Operations Cost i Core Finance;
- menjati 42 MVP površine bez aktivnog DCR-a;
- pokretati greenfield rebuild dok postojeći repo može da se dopuni;
- menjati validan API stil samo radi usklađivanja sa primerom iz dokumentacije.

## 17. Obavezni izlaz početnog repo mapiranja

Claude Code automatski ažurira `CURRENT-CODE-BASELINE.md` i beleži:

- repo, branch, commit i datum;
- framework/runtime;
- bazu/ORM i migration head;
- auth/OIDC;
- storage;
- email/provider adaptere;
- jobs/queue/cron;
- test runner i postojeće test suite-ove;
- build/deploy target;
- staging URL/build ID ako postoji;
- mapu `kanonski modul → stvarni folder/package/table/ruta/test`;
- potvrđene razlike koje zahtevaju migraciju;
- otvorene repo činjenice koje nije moguće automatski utvrditi.

Ovo mapiranje nastaje u okviru tehničkog rada. Ne traži se od programera da ga ručno piše pre početka.
