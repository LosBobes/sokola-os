---
tip: modulni-ugovor
modul-id: M00
status: SPEC_CANDIDATE
verzija: 1.1
datum: 2026-09-01
vlasnik-dokumenta: osnivač
zavisnosti: []
---

# M00 — Kanonski scope i redosled isporuke

## 1. Svrha

Ovaj dokument daje programeru i Claude Code-u jedan nedvosmislen odgovor na četiri pitanja:

1. šta tačno mora biti završeno kao SOKOLA OS MVP;
2. šta se radi posle MVP-a, ali pre spoljnog pilota;
3. šta je opciono i ne sme uticati na MVP;
4. kojim redosledom se radi kada se stvarni repo razlikuje od dokumentacije.

Ovo je implementacioni ugovor. Nije vizija proizvoda, marketinški tekst niti zahtev da programer piše dodatne izveštaje pre početka rada.

## 2. Normativni izrazi

- **MORA** — obavezno za navedeni acceptance.
- **NE SME** — zabranjena implementacija ili ponašanje.
- **TREBA** — preporučena realizacija; drugačije rešenje je dozvoljeno samo ako daje isto ili bolje dokazivo ponašanje.
- **MOŽE** — opciono ponašanje koje ne sme promeniti obavezni scope.
- **AKTIVNI DOKUMENT** — dokument koji nije označen `HISTORICAL`, `SUPERSEDED`, `DEFERRED` ili `NON_NORMATIVE`.

## 3. Četiri isporučna horizonta

| Horizont | Status | Sadržaj | Uticaj na MVP acceptance |
|---|---|---|---|
| `H0_MVP_REQUIRED` | obavezno sada | Core 7, Događaji Light, 42 površine, CSV/XLSX import, sigurnosne i platformske osnove potrebne za rad | definiše MVP |
| `H1_POST_MVP_PRE_PILOT_REQUIRED` | logički posle H0, može u istoj coding rundi | mySOKOLA Basic i pre-pilot integracije/projekcije | ne menja MVP; mora biti završeno pre spoljnog pilota |
| `H2_PILOT_READINESS` | obavezno pre stvarnih podataka | tenant/security/privacy/restore/runbook/allowlist i operativna spremnost | ne dodaje proizvodne funkcije |
| `H3_OPTIONAL_DEFAULT_OFF` | opciono | Operations Light, Link, Skills, Events Pro, Sponsors/Network, Commerce, Growth | ne utiče na MVP ni mySOKOLA acceptance |

Kodiranje ne zahteva prekid između horizonata. Horizont određuje zavisnost, status funkcije i acceptance, a ne administrativno čekanje.

Programer može organizovati H0 i H1 commitove u istoj razvojnoj rundi. H3 registry nije implementaciona specifikacija u ovom paketu; svaki H3 modul zahteva budući zaseban master, QA i scope odobrenje.

## 4. H0 — tačan MVP scope

### 4.1. Proizvodno jezgro

MVP sadrži Core 7:

1. Ljudi i grupe;
2. Raspored i termini;
3. Prisustvo i osnovni napredak, gde napredak u MVP-u znači samo redovnost dolazaka;
4. Članarine, uplate i dugovanja;
5. Komunikacija škole;
6. Dokumenti i ugovori;
7. Izveštaji i pregled poslovanja.

Osma dodatna oblast je `Događaji Light`.

### 4.2. Obavezne pomoćne oblasti

Sledeće nisu dodatni proizvodi, već obavezna podrška MVP-u:

- Identity i invite-only autentifikacija;
- aktivna škola i aktivan prikazni workspace (M03 §1 — workspace ne menja M05 permission uniju);
- multi-tenancy;
- RBAC i server-side autorizacija;
- vlasnička zaštita i Support Access;
- Organization/School osnova;
- ljudi, guardian veze i članstva u školi;
- ogranci, programi, lokacije i prostori;
- onboarding nove škole;
- kontrolisani CSV/XLSX import;
- privatnost, saglasnosti i zahtevi;
- operativna pretraga;
- dashboard i navigacija;
- responsive web/PWA instalacija bez lažnog offline uspeha;
- audit, idempotency, concurrency, jobs, telemetry i bezbedne greške;
- migracije, sintetički seed, backup/restore dokaz i handover.

### 4.3. Kanonske 42 UI površine

Broj se ne menja:

| Prefiks | Akter/oblast | Broj |
|---|---|---:|
| `A01–A03` | SOKOLA administrator | 3 |
| `X01–X04` | zajednički pristup | 4 |
| `O01–O07` | vođeno otvaranje škole | 7 |
| `M01–M15` | vlasnik i menadžer | 15 |
| `T01–T05` | trener ili nastavnik | 5 |
| `P01–P08` | roditelj ili staratelj | 8 |
| **Ukupno** |  | **42** |

Tačan naziv, `surface_key`, akter, owner ugovor, offline politika i acceptance svake površine zaključani su u [[04-M00-H0-SCREEN-CATALOG-42]]. Broj bez tog kataloga nije dovoljan implementacioni ugovor.

`M06–M09` su MVP površine kontrolisanog uvoza i ne smeju biti prebačene u future scope:

- `M06` — izbor fajla;
- `M07` — pregled i validacija;
- `M08` — duplikati i izuzeci;
- `M09` — rezultat i kontrolni izveštaj.

Roditeljske H0 površine imaju sledeće stabilno funkcionalno značenje; prefiks `P` je UI ID, ne modul broj:

| UI ID | H0 površina | Jedini poslovni izvori |
|---|---|---|
| `P01` | roditeljski početni pregled i izbor povezanog deteta | M03/M05/M07 + minimalne owner projekcije |
| `P02` | Moja deca / osnovni dozvoljeni profil | M06/M07 |
| `P03` | raspored povezanog deteta | M10 uz M07 subject guard |
| `P04` | prisustvo povezanog deteta | M11 read projekcija; bez write-a |
| `P05` | sopstvene finansijske obaveze, uplate i IPS instrukcija | M07 payer basis + M12 |
| `P06` | objavljene komunikacije i sistemske notifikacije | M13/M14 |
| `P07` | dozvoljeni dokumenti, prihvatanja i privacy/consent zadaci | M15/M17 |
| `P08` | Događaji Light i prijava povezanog deteta | M16, uz M12 coordinator samo kada postoji fee |

M28 ne dodaje devetu H0 površinu niti menja broj 42; on ove funkcije komponuje/redirectuje u zasebni H1 portal uz sopstveni flag i acceptance. Account/session security ostaje zajednička `X` površina M01/M19, ne novi parent business master.

### 4.4. Obavezni end-to-end tokovi MVP-a

MVP mora dokazati najmanje sledeće tokove:

1. vlasnik/menadžer kreira ili dopunjava strukturu škole;
2. ovlašćena osoba uvozi polaznike, primarne staratelje i članstva zvaničnim CSV/XLSX šablonom;
3. menadžer kreira pojedinačni i ponavljajući termin;
4. trener vidi samo svoje grupe/termine i evidentira prisustvo;
5. roditelj vidi samo svoju povezanu decu i dozvoljene podatke;
6. menadžer priprema i objavljuje mesečne obaveze;
7. ovlašćena osoba evidentira gotovinsku ili bankovnu uplatu van sistema;
8. roditelj vidi važeću obavezu, istoriju uplata i IPS QR instrukciju;
9. menadžer kreira nacrt i objavljuje Komunikaciju ciljnoj publici;
10. menadžer kreira Događaj Light koji organizuje škola ili evidentira gostujući/spoljni događaj, a roditelj prijavljuje i odjavljuje dozvoljenu decu kada taj tip događaja koristi interni registration tok;
11. dokument je uploadovan, autorizovan, preuzet i auditovan;
12. M12 izveštaji koriste stvarne izvore, sedam tabova i kanonske formule;
13. privremena osoba se povezuje sa pravim identitetom bez duplikata;
14. pokušaj pristupa drugoj školi ili tuđem detetu je bezbedno odbijen;
15. retry/dupli klik ne pravi duplu poslovnu posledicu.

### 4.5. Četrnaest nepromenljivih granica

1. Core 7 + Događaji Light.
2. Tačno 42 MVP UI površine.
3. Invite-only pristup.
4. `Person != UserAccount`.
5. Dete nema nalog.
6. Trener nema pristup Core finansijama.
7. Roditeljske uplate su samo `CASH` i `BANK_TRANSFER`.
8. IPS QR je samo instrukcija za uplatu.
9. Nema kartičnog plaćanja u MVP-u.
10. Nema automatskog knjiženja bankarskih uplata.
11. Nema automatskog povraćaja novca.
12. `FamilyCreditLedger` (append-only, M12) postoji kao obavezan entitet. Nema bezuslovne ili skrivene automatske primene kredita: auto-primena je tenant capability, podrazumevano `OFF`, dok škola eksplicitno ne uključi objavljeno pravilo. Kredit sam po sebi nije zabranjen; zabranjeno je tiho/automatsko trošenje bez tog eksplicitnog uključivanja.
13. Čuvanje ili korekcija prisustva ne šalje automatsku poruku roditelju.
14. Future modeli ne aktiviraju mySOKOLA, SOKOLA Link, Skills ili Operations funkcije unutar MVP-a.

### 4.6. Eksplicitno van MVP-a

- nalog deteta;
- otvorena registracija;
- native mobilna aplikacija;
- offline mutacija je globalno zabranjena osim M11 attendance toka, jedinog H0 izuzetka sa eksplicitnim redom operacija, idempotencijom, server-side ponovnom autorizacijom i determinističkim rešavanjem konflikta;
- kartice, bank feed, automatsko IPS knjiženje;
- automatski ili skriveni refund; bezuslovna automatska primena kredita bez eksplicitnog tenant uključivanja (`FamilyCreditLedger` ostaje obavezan M12 ledger);
- full accounting, payroll, porezi, SEF i fiskalizacija;
- marketplace i settlement;
- javni profili dece;
- chat, društvena mreža, leaderboard;
- AI procenjivanje dece;
- Operations Light kao uslov MVP-a;
- M28 pilot/projection sloj kao uslov H0 acceptance-a. `P01`–`P08` jesu H0 portal-foundation površine sa M00/M19 Core fallback-om; M28 ih samo unapređuje iza H1 allowlist/feature guard-a i ne dodaje novi surface ID.

## 5. H1 — mySOKOLA posle MVP-a, pre pilota

### 5.1. Status

mySOKOLA Basic je zasebna verzionisana etapa:

`POST_MVP_PRE_PILOT_REQUIRED / APPROVED_FOR_IMPLEMENTATION_AFTER_MVP / DEFAULT_OFF_UNTIL_PILOT_ALLOWLIST`.

„Posle MVP-a“ označava zavisnost i odvojeni acceptance, ne obavezno drugu razvojnu rundu. Kada su potrebni Core modeli i ugovori stabilni, programer može implementirati mySOKOLA u istoj široj rundi sa MVP-om.

### 5.2. Obavezna vrednost prve verzije

mySOKOLA Basic je privatni parent-first portal koji roditelju/staratelju daje konsolidovan, dozvoljen pogled na:

- današnje i naredne aktivnosti deteta;
- raspored i promene;
- prisustvo u dozvoljenom obimu;
- finansijske obaveze, važeće uplate, dug i IPS instrukciju;
- objavljene Komunikacije;
- prijave na Događaje Light;
- dozvoljene dokumente;
- profil, dozvoljene kontakte i aktivne sesije.

### 5.3. Ne-ciljevi

mySOKOLA Basic nema:

- nalog deteta;
- otvorenu registraciju;
- chat ili društvenu mrežu;
- javni profil;
- monetizaciju poena;
- direktnu izmenu attendance/finance master evidencije;
- podatke druge dece ili škola bez aktivne guardian/school veze;
- direktno čitanje privatnih tabela bez server-side permission i subject guard-a.

### 5.4. Veza sa P01–P08

MVP roditeljske površine ostaju deo H0 acceptance-a. Pre-pilot mySOKOLA implementacija mora da dokumentuje i sprovede migracionu mapu za svaku od njih:

`REUSE`, `REDIRECT`, `REPLACE` ili `RETIRE_AFTER_MIGRATION`.

Nije dozvoljeno održavati dve različite istine o finansijama, događajima, guardian vezama ili objavljenim komunikacijama.

### 5.5. Minimalni pre-pilot acceptance

- guardian revoke odmah ukida novi i keširani pristup;
- context switch nikad ne meša decu ili škole;
- finansijski total koristi iste važeće Core Finance zapise;
- draft Komunikacija nikad nije vidljiv roditelju;
- IPS ostaje instrukcija;
- dete nema auth flow;
- deep-link posle prijave vraća samo dozvoljeni resurs ili safe fallback;
- session/device revoke radi;
- mobilni prikaz i accessibility prolaze;
- telemetry nema imena deteta, sadržaj poruke ili finansijski iznos.

Detaljni model, rute, komande, projection freshness, UX stanja i QA pripadaju posebnom modulu `M28 — mySOKOLA`.

## 6. H2 — pilot readiness

Pilot readiness nije novi proizvod. To je stanje sistema posle MVP-a i mySOKOLA.

### 6.1. Tehnički minimum

- server-side tenant i subject autorizacija;
- cross-tenant automatizovani testovi sa najmanje dve škole;
- drugi roditelj i guardian revoke slučaj;
- backup i uspešan restore rehearsal;
- podržan migration/forward-recovery put;
- release vezan za poznati commit;
- monitoring, alerting, correlation i incident runbook;
- email/storage/job adapteri imaju failure testove;
- secret i PII redaction;
- privatni upload i signed access;
- support access je isključen ili vremenski ograničen i auditovan;
- feature flag/allowlist/kill-switch ponašanje testirano;
- staging koristi samo sintetičke podatke do odobrenja realnog pilota.

### 6.2. Vlasničke/pravne vrednosti

Programer ne donosi pravne odluke. Sistem mora omogućiti konfiguraciju i tehničko sprovođenje kada se potvrde:

- pravna osnova obrade;
- DPA/uslovi/politike i saglasnosti;
- retention;
- hosting i podizvršioci;
- DPIA odluka;
- procedura zahteva, incidenta i podrške.

Nerešena pravna vrednost ne blokira strukturu, testove ili sintetički staging. Blokira samo upotrebu stvarnih podataka za tok na koji se odnosi.

## 7. H3 — opciono i podrazumevano isključeno

| Modul/proizvod | Status | Pravilo |
|---|---|---|
| Operations Light | `REGISTERED_FUTURE / DEFAULT_OFF / OUTSIDE_CURRENT_DELIVERY` | ne implementira se iz ovog paketa i ne utiče na MVP/mySOKOLA acceptance |
| SOKOLA Link Basic | `OPTIONAL / DEFAULT_OFF` | javni snapshot, nikad direktno privatne tabele |
| Skills Light | `OPTIONAL / DEFAULT_OFF` | bez dijagnoze, AI ocene ili javnog rangiranja |
| Events Pro | `FUTURE` | nadogradnja Events Light, ne promena Light ugovora |
| Sponsors/Network | `FUTURE` | zasebni agreement, privacy i commercial ugovor |
| Commerce | `FUTURE` | ne menja MVP `PaymentRecord` bez finansijskog ugovora |
| Growth CRM | `FUTURE` | inquiry nije automatski Person, član ili nalog |

Operations Light se ne implementira u ovoj razvojnoj predaji. Njegov registar samo sprečava buduće preklapanje vlasništva; zaseban kandidat mora definisati entitete, komande, dozvole, greške, migracije i QA pre kodiranja.

## 7a. Događaji Light — poreklo događaja

MVP obavezno podržava dve vrednosti porekla događaja:

| Vrednost | UI naziv | Uloga škole |
|---|---|---|
| `SCHOOL_ORGANIZED` | Organizuje škola | škola je organizator i vodi dozvoljeni Light tok |
| `EXTERNAL_ORGANIZER` | Gostujući / spoljni događaj | događaj organizuje druga organizacija, a škola vodi sopstveno učešće |

Poreklo nije lokacija. Gostujući događaj može biti u školskoj ili spoljnoj lokaciji, a događaj škole može biti organizovan na iznajmljenoj/spoljnoj lokaciji.

Oba tipa koriste isti `Event` source of truth. Ne pravi se paralelni `GuestEvent`. Za spoljni događaj čuvaju se minimalni organizer snapshot/reference, odgovorna osoba škole, učesnici/grupe, termin, lokacija i interni status. Složena zvanična prijava kod spoljnog organizatora, transport, smeštaj, dobavljači i troškovi pripadaju Events Pro/Operations ugovorima.

## 8. Redosled rada u repozitorijumu

Programer/Claude Code radi ovim redom:

1. pročita stvarni repo, migracije, testove i deployment konfiguraciju;
2. popuni `CURRENT-CODE-BASELINE.md` dokazima iz repoa;
3. mapira postojeće module na kanonske SOKOLA module;
4. za svaku stavku proveri da li validna implementacija već postoji;
5. postojeće ispravno rešenje zadržava i pokriva testom;
6. nedostajuće ili kontradiktorno rešenje implementira najmanjom bezbednom promenom;
7. migracije, testovi i dokumentacija nastaju u istom radu;
8. završava H0 MVP;
9. vraća programeru tehničke rezultate na pregled;
10. kada su Core zavisnosti stabilne, nastavlja H1 mySOKOLA u istoj ili narednoj coding rundi;
11. zatim završava H2 pilot readiness;
12. H3 radi samo ako ne remeti prioritetni redosled.

Nema obaveznog početnog eseja, procene trajanja ili čekanja vlasničkog odgovora. Ako postoji stvarna neodlučiva kontradikcija, bira se bezbedan reverzibilan default, evidentira se pretpostavka i nastavlja sve što od nje ne zavisi.

## 9. Pravilo promene scope-a

Promena je scope promena samo ako:

- dodaje ili uklanja MVP korisnički zadatak;
- menja neku od 42 površine kao ugovornu obavezu;
- menja identitet, tenant granicu, ulogu ili dozvolu;
- uvodi novi novčani tok;
- uvodi javno objavljivanje privatnih podataka;
- aktivira future modul u MVP-u;
- menja obavezni import target ili guardian pravilo.

Refaktor, adapter, naziv foldera, ORM, framework, queue ili cloud provider nisu scope promena dok čuvaju ugovoreno ponašanje i dokaze.

## 10. Završna odluka M00

**Status dokumentacije (DCR-20260907-01 revizija 2.3): `PROGRAMMER_CANDIDATE`; status aplikacionog koda: `CODE_REPOSITORY_UNVERIFIED`.** M00–M21 i M28 su jedan samostalan normativni ulaz. To dozvoljava repo-first implementaciju, ali ne tvrdi da su kod, migracije ili testovi već završeni.

**M15 napomena (DCR-20260907-01 §7):** Dokumenti koriste immutable `DocumentVersion` sa hash-om — nema advanced diff/rollback UI-ja, ali istorija verzija ostaje dokaziva, nikad "prosta referenca bez dokaza".

Implementacioni prioritet je:

> **MVP sa CSV/XLSX importom → tehničko prihvatanje → mySOKOLA Basic → pilot readiness → spoljni pilot → opcioni moduli.**

Ovaj redosled se primenjuje bez dodatnih procesnih kapija za kodiranje.

## 11. Granica između zahteva i tehničke realizacije

SOKOLA ugovori određuju šta funkcija radi, ko joj pristupa, koji su podaci/invarianti i kako se prihvata. Programer bira kako će to fizički sprovesti u postojećem repou, uključujući API stil, framework, ORM, foldere, locking, jobs, cache i deploy.

Ako izabrani API nije REST, ne uvodi se dodatni REST sloj samo radi dokumentacije. Mora postojati odgovarajući proverljiv contract za stvarno korišćeni stil: OpenAPI za REST, GraphQL schema, RPC contract schema ili eksplicitne server-action/use-case input/output šeme i contract testovi.
