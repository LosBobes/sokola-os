---
tip: dcr
status: POTVRĐENO
datum: 2026-09-01
verzija: v5.7
revizija: "1.1"
vlasnik-dokumenta: osnivač
tagovi:
  - sokola-os
  - dcr
  - repo-first
  - programmer-decision
  - events-light
  - mysokola
  - operations-light
---

# DCR-20260901-02 — Repo-first izrada, tehnička sloboda programera i tipovi događaja

Aktivni poslovni izvod za v5.7. Proces predaje određuje DCR-20260903-07; modulna konsolidacija DCR-20260907-01. Ovaj izvod ne uvodi novu odluku.

## 1. Konačna odluka o načinu izrade

SOKOLA OS se ne pravi ponovo od početka. Programer i Claude Code moraju nastaviti od stvarnog postojećeg repozitorijuma, postojeće baze, migracija, ruta, komponenti i već implementiranih tokova.

Redosled za svaku funkciju je:

1. pregledaj postojeće stanje;
2. utvrdi da li već ispunjava aktivni poslovni ugovor;
3. zadrži validno rešenje i potvrdi ga testom;
4. dopuni ono što nedostaje;
5. ispravi stvarnu kontradikciju ili grešku;
6. vrati diff, migracije, testove i dokaz.

Masovni rewrite, novi paralelni projekat ili zamena ispravnog rešenja nisu dozvoljeni bez konkretnog tehničkog razloga i migracionog plana.

## 2. Podela odgovornosti

Dokumentacija SOKOLA OS određuje:

- poslovni cilj i scope;
- korisničke uloge i dozvole;
- podatke i njihove invariante;
- lifecycle i dozvoljene tranzicije;
- šta korisnik vidi i može da uradi;
- tenant, privacy i security granice;
- idempotency, concurrency i audit očekivanja;
- acceptance kriterijume i obavezne test scenarije;
- šta ulazi u MVP, mySOKOLA, Operations i buduće faze.

Programer određuje fizičku tehničku realizaciju, u skladu sa postojećim repoom:

- programski jezik i framework;
- REST, GraphQL, RPC, server actions ili drugi odgovarajući API/transport stil;
- tačne endpoint nazive i URL strukturu, osim već zaključanih korisničkih deep-linkova;
- ORM/query builder i fizičku šemu migracija;
- organizaciju foldera i paketa;
- dependency injection, service/repository obrasce;
- locking/concurrency mehanizam koji dokazivo sprovodi ugovor;
- queue/job runner/outbox realizaciju;
- cache, storage, email i druge adaptere;
- test alate, CI i deployment postupak.

Dokumentacija ne sme programeru propisati alat bez poslovnog ili bezbednosnog razloga. Programer ne sme tehničkim izborom promeniti poslovno ponašanje, scope, dozvole ili zaštitne granice.

## 3. API pravilo

SOKOLA dokumentacija definiše semantičke komande, query-je, input/output obaveze, guardove i greške. Programer bira fizički API stil.

Obavezno je da izabrani API ima proverljiv ugovor:

- ako je REST: OpenAPI ili ekvivalentan machine-readable ugovor;
- ako je GraphQL: verzionisana schema i autorizacioni resolver testovi;
- ako je RPC/tRPC: izvezena/verzionisana contract schema i contract testovi;
- ako su server actions/in-process use cases: eksplicitne input/output šeme, stabilni command/query ID-evi i integration testovi;
- za integration events: verzionisana event schema.

Nije dozvoljeno stvarati paralelni REST API samo da bi postojao OpenAPI ako postojeći repo koristi drugi validan ugovorni stil.

## 4. Finalni paket za programera

Konačni developer paket nastaje tek kada se detaljno razrade svi dogovoreni moduli. M00 je arhitektonski početak, ne završna predaja za kodiranje celog proizvoda.

Finalni ZIP mora biti samostalan i sadržati:

- jedan kratak `00-CLAUDE-CODE-IZVRSI.md` kao izvršnu ulaznu tačku;
- aktivne poslovne i modulne ugovore;
- jasan MVP scope i zasebne acceptance kriterijume;
- pune M00–M21 i M28 ugovore; M22–M27/M29–M34 ostaju samo jasno označen budući registar van predaje;
- mapu zahteva, modula i UI površina;
- zahteve za migracije, seed, testove i povratni izveštaj;
- zabranu ponovne izgradnje od nule;
- instrukciju da Claude Code prvo čita stvarni repo;
- format dokaza koji programer proverava posle isporuke.

Integracioni promptovi kojima se gradi Obsidian vault nisu deo finalnog developer ZIP-a. Izvršna Claude Code ulazna tačka jeste deo finalnog developer ZIP-a.

## 5. mySOKOLA u istoj rundi i isključenje H3

mySOKOLA može biti implementirana u istoj široj razvojnoj rundi sa MVP-om nad stabilnim owner portovima, uz zaseban H1 acceptance i podrazumevano isključen pilot flag. Operations Light i ostali H3 moduli ne kodiraju se u ovoj predaji, jer paket ne sadrži njihove master/QA ugovore.

To ne menja njihove statuse:

- mySOKOLA ostaje van MVP acceptance-a, `DEFAULT_OFF` do pre-pilot provere;
- Operations Light ostaje `REGISTERED_FUTURE / DEFAULT_OFF / OUTSIDE_CURRENT_DELIVERY`;
- F-O01 ne ulazi u 42 MVP površine;
- trener i roditelj nemaju Operations pristup;
- MVP se proverava odvojeno od M28 čak i kada su njihovi commitovi u istoj razvojnoj rundi;
- agent ne kreira future H3 tabele/rute/jobove iz registry zapisa; nepoznat ili isključen capability failuje closed.

„Posle MVP-a“ za mySOKOLA označava logičku zavisnost i zaseban acceptance, a ne obavezno drugi ugovor, drugi repozitorijum ili administrativno čekanje. Kada su potrebni Core izvori stabilni, programer može nastaviti u istom branchu ili seriji commitova.

## 6. Događaji Light — dva obavezna porekla

Svaki Događaj Light mora imati eksplicitno poreklo/ulogu škole:

| Kanonska vrednost | UI naziv | Značenje |
|---|---|---|
| `SCHOOL_ORGANIZED` | Organizuje škola | aktivna škola je organizator i vodi dozvoljeni interni tok događaja |
| `EXTERNAL_ORGANIZER` | Gostujući / spoljni događaj | događaj organizuje druga organizacija, a škola evidentira svoje učešće, članove i dozvoljene interne obaveze |

Poreklo događaja nije isto što i lokacija. Oba tipa mogu biti održana:

- na lokaciji škole;
- na spoljnoj lokaciji;
- na više lokacija ako kasniji ugovor to dozvoli;
- online.

### 6.1. Događaj koji organizuje škola

Škola može da upravlja:

- nazivom, kategorijom, opisom i terminom;
- odgovornom osobom;
- lokacijom;
- internom ciljnom grupom;
- kapacitetom i prijavama u Light obimu;
- dozvoljenom događajnom obavezom;
- komunikacijom i statusom;
- dolaskom/evidencijom u dozvoljenom Light obimu.

### 6.2. Gostujući/spoljni događaj

Škola najmanje evidentira:

- naziv i vrstu događaja;
- naziv spoljnog organizatora kao minimizovan display snapshot, bez kontakta i bez automatskog kreiranja korisničkog naloga ili novog tenant-a;
- spoljni referentni broj ili javni URL kada postoji, bez access tokena, credential-a ili ličnih podataka;
- datum/vreme i lokaciju;
- odgovornu osobu iz škole;
- grupe/polaznike koji učestvuju;
- interni status učešća škole;
- dozvoljenu internu komunikaciju i dokumente.

Light modul ne pokušava da bude sistem spoljnog organizatora. Spoljna zvanična prijava, ugovor, dobavljač, transport, smeštaj, sponzori i složeni troškovi ostaju Events Pro/Operations ugovori, osim minimalne reference potrebne da škola vodi svoje učešće.

## 7. Source-of-truth za događaje

Oba porekla koriste isti kanonski `Event` model i isti tenant scope. Zabranjeno je praviti poseban `GuestEvent` master koji duplira Event.

Obavezna semantička polja; fizički nazivi/adapterski mapping mogu pratiti postojeći repo samo ako machine-readable ugovor dokazuje isto značenje:

- `origin_type`: `SCHOOL_ORGANIZED | EXTERNAL_ORGANIZER`;
- `school_id`;
- `external_organizer_name` nullable na nivou kolone, ali obavezan i non-empty za `EXTERNAL_ORGANIZER`, a obavezno null za `SCHOOL_ORGANIZED`;
- `external_reference` nullable;
- `responsible_staff_profile_id`;
- jedan ili više tipiziranih M16 `EventLocation` redova, ili vremenski ograničen `location_tbd=true` prema M16 publish pravilu;
- lifecycle, registracije i audit iz M16 ugovora.

Invarianti:

- `SCHOOL_ORGANIZED` ne zahteva spoljnog organizatora;
- `SCHOOL_ORGANIZED` zabranjuje `external_organizer_name`; `external_reference` je dozvoljen samo kao neosetljiva operativna referenca ako M16 schema to eksplicitno prihvati;
- `EXTERNAL_ORGANIZER` zahteva minimizovan naziv spoljnog organizatora; spoljna referenca ostaje opciona;
- spoljašnji organizator ne dobija SOKOLA nalog automatski;
- događaj uvek ostaje tenant-scoped zapis škole koja ga evidentira;
- `origin_type` je immutable od kreiranja događaja; greška se rešava otkazivanjem pogrešnog draft/event toka i kreiranjem novog događaja, bez prepisivanja istorije.

## 9. Acceptance

Odluka je integrisana kada:

1. nijedan aktivni dokument ne nalaže greenfield rebuild;
2. repo-first pravilo postoji u startnom i izvršnom dokumentu;
3. fizički API/stack ostaju `PROGRAMMER_DECISION`;
4. ugovorno ponašanje i acceptance ostaju obavezni;
5. mySOKOLA može biti u istoj coding rundi uz zaseban acceptance; Operations i ostali H3 ostaju van ove predaje;
6. finalni developer paket je jasno odvojen od međupaketa za dokumentacionu integraciju;
7. Events Light svuda razlikuje `SCHOOL_ORGANIZED` i `EXTERNAL_ORGANIZER`;
8. poreklo događaja nije pomešano sa lokacijom;
9. ne postoji paralelni `GuestEvent` source of truth;
10. testovi pokrivaju oba tipa događaja i njihove negativne slučajeve.
