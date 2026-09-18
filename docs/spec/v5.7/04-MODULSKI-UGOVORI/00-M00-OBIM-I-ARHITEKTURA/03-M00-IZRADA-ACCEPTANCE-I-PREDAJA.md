---
tip: modulni-ugovor
modul-id: M00
status: SPEC_CANDIDATE
verzija: 1.1
datum: 2026-09-01
vlasnik-dokumenta: osnivač
zavisnosti:
  - M00-scope
  - M00-arhitektura
---

# M00 — Izrada, acceptance i predaja programeru

> **Aktuelni obuhvat:** [[../../00-DCR-AKTIVNI-v5.7/DCR-20260907-01-Kanonska-Konsolidacija-M00|DCR-20260907-01 revizija 2.3]] zaključava jedan čist M00–M21 programmer candidate i M28 kao zaseban H1/default-OFF ugovor. Ovo menja samo obuhvat predaje, ne poslovne invarijante modula.

## 1. Namena

Ovaj dokument pretvara arhitekturu u izvršan redosled rada. Programer može dati ceo vault i stvarni repo Claude Code-u, pustiti ga da implementira, zatim pregledati promene, ispraviti greške i vratiti vlasniku proverljiv rezultat.

Dokument ne zahteva procenu trajanja, početni esej, dnevne izveštaje ili čekanje nove dozvole. Zahteva samo kod, migracije, testove i trag koji omogućava proveru.

Programer odlučuje fizičko „kako“ prema postojećem repou. Vault definiše kompletno „šta“, zaštitne granice i acceptance.

## 2. Pravilo „inspect, preserve, complete, prove“

Za svaku radnu celinu Claude Code mora:

1. **Inspect** — pročitati stvarni kod, šemu, migracije, rute i testove.
2. **Preserve** — zadržati validno postojeće rešenje.
3. **Complete** — dopuniti nedostajuće ponašanje najmanjom koherentnom promenom.
4. **Prove** — dokazati rezultat testom i povezati ga sa zahtevom.

Ne sme se raditi masovni rewrite samo zato što se nazivi ili struktura razlikuju od primera u dokumentaciji.

## 3. Radni talasi

### Talas 0 — repo baseline i zaštita postojećeg rada

**Ulaz:** stvarni repo + ovaj sanitizovani v5.7 programmer candidate.

**Radnje:**

- sačuvati trenutni branch/commit;
- pokrenuti postojeći install/build/lint/typecheck/test;
- utvrditi migration head i bazu;
- popuniti `CURRENT-CODE-BASELINE.md`;
- napraviti mapu modula, tabela, ruta i ekrana;
- evidentirati postojeće prolazne/padajuće testove;
- ne popravljati nevezane korisničke izmene.

**Izlaz:** poznat baseline i početni regresioni dokaz. Rad se nastavlja i kada pojedina repo činjenica ostane nepoznata, osim kada baš ta činjenica onemogućava konkretnu izmenu.

### Talas 1 — identitet, tenant i dozvole

**Moduli:** M01–M07.

**Obavezno:**

- `Person` i `UserAccount` razdvojeni;
- OIDC mapping samo na nalogu;
- invite-only tok;
- aktivna škola i uloga;
- tenant guard na command/query/list/count/search/export;
- formalne Core dozvole;
- role assignment bez privilege escalation;
- guardian subject guard;
- support access vremenski ograničen i auditovan.

**Kritični test:** roditelj/trener/admin škole A ne vidi niti menja podatke škole B kroz direktan ID, listu, count, search, export, cache ili job.

### Talas 2 — struktura škole, ljudi i grupe

**Moduli:** M06–M09.

**Obavezno:**

- vrste osoba i školski profili;
- roditelj/staratelj–dete veza;
- primarni kontakt kao eksplicitno pravilo;
- Branch/Program/Location/Space razdvojeni;
- `Location`, ne hardkodirani `Hall` kao jedini model;
- GroupEnrollment odvojen od StaffAssignment;
- samo polaznik ulazi u prisustvo i članarinu;
- default trener/lokacija;
- transfer i istorija upisa bez prepisivanja istorije.

### Talas 3 — svakodnevno operativno jezgro

**Moduli:** M10–M13 i M16.

**Obavezno:**

- pojedinačni i ponavljajući termini;
- trener/lokacija nasleđeni iz grupe uz override;
- konflikt i stale version ponašanje;
- prisustvo sa tačno `UNRECORDED/PRESENT/ABSENT/LATE`; `UNRECORDED` se ne računa kao odsustvo, `LATE` ulazi u presence numerator, a opravdano/neopravdano nije H0 status;
- attendance correction history;
- članarine, obaveze, dospeće, payment/allocation i tri odvojena korektivna toka;
- Komunikacija sa persisted draft-om i immutable published zapisom;
- Događaji Light sa `SCHOOL_ORGANIZED` i `EXTERNAL_ORGANIZER` poreklom, prijavom/odjavom i bez duplikata;
- poreklo događaja odvojeno od lokacije;
- gostujući događaj koristi isti `Event`, bez paralelnog `GuestEvent` mastera.

### Talas 4 — dokumenti, privatnost, izveštaji i shell

**Moduli:** M14, M15, M17–M19.

**Obavezno:**

- zvonce ima stvaran sistemski notification model ili je skriveno;
- privatni dokument upload/download i audit;
- consent/DSAR/export struktura;
- M12 ima stvarni backend, sedam tabova i 63 kanonska pokazatelja;
- dashboard metrike koriste iste izvore kao detaljni prikazi;
- navigacija odgovara ulozi;
- PWA ne potvrđuje offline mutaciju;
- obavezna loading/empty/error/forbidden/stale/read-only stanja.

### Talas 5 — onboarding i MVP import

**Modul:** M20.

**Obavezno:**

- `M06–M09` potpuno upotrebljivi;
- zvanični CSV UTF-8 i XLSX adapter;
- schema version i file hash;
- MIME/content sniffing i zlonamerni fajlovi odbijeni;
- validate/preview bez kanonskog upisa;
- dedupe samo u aktivnoj školi;
- ručna odluka za nejasne slučajeve;
- approval zamrzava candidate set i očekivane target verzije;
- execute je idempotentan;
- rezultat po redu: `CREATED`, `LINKED`, `SKIPPED`, `CONFLICTED`, `FAILED`;
- import ne pravi nalog i ne šalje poziv;
- raw fajl se automatski uklanja prema aktivnom bezbednom retention pravilu;
- drugi tenant ne može da pristupi fajlu, preview-u ili kandidatu.

### Talas 6 — platformska pouzdanost

**Modul:** M21.

**Obavezno:**

- DB constraint i application guard rade zajedno gde je kritično;
- audit i telemetry su odvojeni;
- durable outbox;
- job retry/backoff/max attempts/recovery;
- idempotency i concurrency testovi;
- konfiguracija bez runtime placeholder vrednosti;
- backup i restore dokaz;
- migracije i podržan recovery;
- sintetički seed sa dve škole;
- deployment i rollback/forward-recovery dokumentovani prema stvarnom stacku;
- handover omogućava drugoj tehničkoj osobi da podigne sistem.

### Talas 7 — MVP kompletan regresioni krug

**Obavezno:**

- build/lint/typecheck/test prolaze ili je svaki preostali failure precizno označen kao raniji i nerelevantan;
- svih 42 površine mapirane na stvarne rute/komponente;
- svi H0 tokovi prolaze sa sintetičkim podacima;
- owner/manager/admin/trainer/parent test nalozi;
- dve škole i cross-tenant negativni testovi;
- mobile i accessibility osnovna provera;
- nema placeholder KPI, mrtvih kontrola ili interne poruke „čeka backend“;
- migracije prolaze na praznoj i podržanoj prethodnoj bazi;
- seed se ponavlja bez duplikata;
- acceptance evidence vezan za commit.

Posle ovog talasa kod može imati status `MVP_IMPLEMENTED_AWAITING_OWNER_ACCEPTANCE` ili `MVP_ACCEPTED`, prema stvarnom rezultatu pregleda. To ne sprečava tehničku pripremu sledeće etape u istom ili posebnom branchu, prema odluci programera.

Programer može organizovati H1 mySOKOLA u istoj široj razvojnoj rundi kada su potrebne Core zavisnosti stabilne; njeni commitovi, flagovi, testovi i acceptance ostaju odvojivi od MVP-a. H3 nije izvršni obuhvat ovog paketa.

### Talas 8 — mySOKOLA Basic

**Modul:** M28.

Rad počinje iz prihvaćenih Core izvora. Nema drugog `Person`, naloga, guardian odnosa, finance ili events mastera.

**Obavezno:**

- portal context resolver;
- purpose-limited projection ugovori;
- guardian revoke invalidation;
- context switch više dece/škola;
- `P01–P08` migraciona mapa;
- portal rute i deep-link guardovi;
- sesije/uređaji i revoke;
- finansijski, komunikacioni, događajni i dokument projection mapping;
- stale/partial/source unavailable UX bez curenja opozvanih podataka;
- feature OFF, pilot allowlist i kill switch;
- portal security, privacy, accessibility i telemetry testovi.

### Talas 9 — pilot readiness

**Obavezno:**

- MVP i mySOKOLA deployment kandidat vezan za commit;
- najmanje jedna allowlist škola;
- restore rehearsal;
- incident/support runbook;
- privacy/security testovi;
- produkciona konfiguracija i adapteri;
- retention i pravna pravila implementirana kada ih vlasnik/stručnjak potvrdi;
- realni podaci se ne koriste pre potvrde uslova;
- kill switch i rollback scenario provereni.

### Buduća predaja — H3 moduli nisu izvršni talas ovog paketa

Operations Light i ostali H3 moduli ne smeju se razvijati iz ovog candidate-a. Budući zaseban programmer candidate mora dokazati da:

- ne menjaju Core source-of-truth;
- ostaju default-OFF;
- ne uvode nove MVP površine;
- njihovi testovi ne destabilizuju H0/H1;
- ne odlažu ispravku MVP/pilot problema.

## 3a. Tehnička sloboda i obavezni dokaz

Claude Code ne dobija nalog da menja stack. Prvo koristi stvarni repo i programerov izbor.

Dozvoljeni su REST, GraphQL, RPC/tRPC, server actions ili drugi postojeći stil. Obavezni su proverljiv contract, server-side guardovi i testovi. OpenAPI je obavezan samo kada je stvarni interfejs REST; za drugi stil koristi se njegov machine-readable/verzionisani ugovor.

## 4. Definition of Done za modul

Modul nije završen samo zato što postoji ekran. Za svaki aktivni modul mora postojati:

- jasan scope i ne-ciljevi;
- kanonski glossary i source-of-truth;
- fizička šema/migracija ili dokaz da postojeća šema već ispunjava ugovor;
- komande i query-ji;
- role/permission/subject guard;
- lifecycle i invarianti;
- API/error contract;
- idempotency/concurrency/transaction pravila;
- audit i outbox posledice;
- sva relevantna UI stanja;
- report/projection posledice;
- automatizovani testovi;
- evidence vezan za commit;
- dokumentovana migracija/rollback ili forward recovery.

## 5. Definition of Done za UI površinu

Svaka površina ima:

- stabilni UI ID i rutu;
- dozvoljene uloge;
- server-side autorizovan data source;
- primarni korisnički zadatak;
- desktop i mobile ponašanje;
- `loading`, `empty`, `success`, `validation error`, `server error`, `forbidden`, `not found safe`, `stale/conflict` i `read-only` stanje kada je relevantno;
- disabled kontrolu samo kada korisnik dobija razumljivo objašnjenje;
- bez mrtvog dugmeta;
- keyboard/focus i screen-reader minimum;
- e2e test osnovnog zadatka;
- mapu prema odgovarajućem PRD/REQ/komandi.

Skrivanje dugmeta nije authorization test.

## 6. Definition of Done za command

Command je završen kada su implementirani i testirani:

- input validation;
- tenant, permission i subject guard;
- poslovne invariante;
- transakcija;
- idempotency;
- stale/concurrency scenario;
- audit;
- outbox/projection posledice;
- bezbedan response;
- jedan error kod → jedan HTTP status;
- retry ponašanje;
- happy, forbidden, cross-tenant, replay i race test gde je primenljivo.

## 7. Definition of Done za CSV/XLSX import

Import je MVP-završen kada:

1. zvanični šabloni prolaze;
2. pogrešna verzija šablona je odbijena razumljivo;
3. CSV dijakritika, encoding, prazna/duga polja i datumi su testirani;
4. XLSX sa makroom/formulom/spoljnom vezom je odbijen;
5. content-type mismatch i decompression bomb su odbijeni;
6. preview ne menja kanonske podatke;
7. isti file/job/row replay ne pravi duplikat;
8. mogući duplikat zahteva ovlašćenu odluku;
9. drugi tenant ne vidi fajl ni candidate;
10. worker crash i nastavak daju determinističan rezultat;
11. rezultat po redu je vidljiv i izvoziv;
12. pozivi roditeljima ostaju posebna radnja;
13. raw fajl se uklanja prema aktivnom pravilu;
14. clean seed škola može biti uvedena bez ručnog prepisivanja svakog profila.

## 8. Definition of Done za MVP

MVP je tehnički završen kada:

- Core 7 + Događaji Light rade end-to-end;
- školski i gostujući/spoljni Događaji Light prolaze odvojene acceptance scenarije;
- svih 42 površine imaju stvaran rezultat;
- M06–M09 import radi;
- 14 granica nije prekršeno;
- trener nema finansije;
- dete nema nalog;
- parent/guardian scope radi;
- `CASH/BANK_TRANSFER` i IPS-instruction pravilo rade;
- nema automatskog bank posting/refund/credit/attendance message toka;
- M12 nema placeholder podatke;
- cross-tenant i permission testovi prolaze;
- build/migracije/seed/testovi su ponovljivi;
- postoji poznat commit i predajni izveštaj.

M28 mySOKOLA ne ulazi u H0 acceptance i ima zaseban H1 acceptance. Operations Light i ostali H3 moduli uopšte nisu deo ove implementacione predaje.

## 9. Definition of Done za mySOKOLA pre-pilot etapu

mySOKOLA je tehnički završena kada:

- koristi samo Core mastere i odobrene projekcije;
- portal permission/subject guard radi na svakom query-ju i komandi;
- revoke guardian/membership/session invalidira pristup;
- više dece/škola se ne meša;
- P01–P08 migraciona mapa je sprovedena;
- finansije, komunikacije, događaji i dokumenti prikazuju samo dozvoljene podatke;
- dete nema nalog;
- portal je mobile/accessibility proveren;
- feature OFF i pilot allowlist rade;
- security, privacy, stale/cache i deep-link testovi prolaze;
- deployment kandidat je vezan za commit.

## 10. Šta programer vraća vlasniku

Programer ne vraća samo ZIP koda bez konteksta. Minimalna predaja sadrži:

1. repository/branch/commit SHA;
2. migration head;
3. staging build ID/URL ako postoji;
4. kratku listu implementiranih modula;
5. listu promenjenih migracija;
6. komande za install/build/test/seed/deploy;
7. sažetak rezultata testova;
8. mapu 42 površine → ruta/status;
9. test naloge i sintetičke podatke za sve uloge;
10. drugi tenant i cross-tenant test;
11. poznate nedovršene ili namerno isključene funkcije;
12. potvrdu feature flagova i njihovog default stanja;
13. rollback/forward-recovery napomenu;
14. listu odluka koje stvarno zahtevaju vlasnika/pravnika/računovođu;
15. potvrdu da stvarni podaci dece nisu korišćeni bez odobrenja.

Ako je M28 mySOKOLA uključena u istu razvojnu rundu, izveštaj je prikazuje u zasebnom odeljku sa flagovima, migracijama, testovima i statusom; ne predstavlja se kao deo MVP PASS-a. H3 se ne prijavljuje kao implementiran jer nije zadat ovim paketom.

## 11. Format tehničkog povratnog izveštaja

```markdown
# SOKOLA implementacioni povratni izveštaj

## Build identitet
- Repo:
- Branch:
- Commit:
- Migration head:
- Staging build:

## Završeno
- MOD/REQ/UI ID — kratko ponašanje — dokaz/test

## Zadržano iz postojećeg koda
- komponenta — zašto je validna — dokaz/test

## Migracije
- ID — svrha — upgrade — recovery

## Testovi
- suite — broj prolaznih/padajućih — komanda

## Poznato nedovršeno
- stavka — uticaj — preporučeni sledeći korak

## Owner/legal/expert vrednosti
- vrednost — bezbedni runtime default — šta blokira

## Bezbednost podataka
- tenant test:
- guardian test:
- restore test:
- korišćeni podaci: SYNTHETIC_ONLY | APPROVED_PILOT
```

## 12. Postupanje sa greškama tokom izrade

- Ako test potvrdi regresiju: popraviti u istom radnom toku i ponoviti zavisne testove.
- Ako migracija ne može bezbedno nazad: dokumentovati forward-recovery pre merge-a.
- Ako dokument i kod koriste druga imena: napraviti mapu/adapter, ne treći paralelni model.
- Ako niži dokument protivreči aktivnom DCR-u: primeniti DCR i ispraviti aktivni dokument.
- Ako nedostaje produkcijska vrednost: koristiti strukturiranu konfiguraciju i bezbedan OFF/error default.
- Ako pravna odluka nedostaje: implementirati strukturu i testove, ali ne aktivirati stvarni tok sa realnim podacima.
- Ako funkcija nije implementirana: prikazati honest empty/disabled state ili sakriti kontrolu; ne vraćati lažni uspeh.

## 13. Završno pravilo

Programer može da koristi Claude Code za MVP, mySOKOLA i pilot hardening u kontinuitetu. Svaka etapa ima svoj acceptance i dokaz, ali nema veštačkog zahteva da razvoj stane samo radi novog dokumenta ili formalne potvrde kada je aktivni ugovor već potpun.

Finalni programmer vault, nakon integracije svih modulnih ugovora, mora imati jednu kratku izvršnu ulaznu tačku `00-CLAUDE-CODE-IZVRSI.md`. Ona nalaže repo-first pregled, implementaciju, testove i povratni izveštaj. Dokumentacioni promptovi korišćeni za izgradnju vaulta ne ulaze u finalni ZIP.
