---
tip: dcr
status: POTVRĐENO
datum: 2026-09-01
verzija: v5.7
vlasnik-dokumenta: osnivač
tagovi:
  - sokola-os
  - dcr
  - scope
  - mvp
  - csv-import
  - mysokola
  - pilot
---

# DCR-20260901-01 — MVP CSV import i mySOKOLA pre pilota

Aktivni poslovni izvod za v5.7. Proces predaje određuje DCR-20260903-07; modulna konsolidacija DCR-20260907-01. Ovaj izvod ne uvodi novu odluku.

## 2. Konačna odluka o MVP-u

Aktuelni MVP ostaje:

- Core 7;
- Događaji Light;
- svih 42 kanonskih UI površina;
- pomoćne funkcije potrebne da tih 42 površine rade bezbedno i od početka do kraja;
- kontrolisani import preko površina `M06`, `M07`, `M08` i `M09`.

Kontrolisani import je **obavezni deo MVP-a**, a ne post-MVP foundation.

### 2.1. Obavezni MVP format i tok

MVP mora najmanje da podrži:

- zvanični SOKOLA CSV šablon u UTF-8 kodiranju;
- postojeći zvanični XLSX šablon bez makroa, formula i spoljnih veza, u skladu sa PRD 11;
- upload;
- bezbednosnu proveru fajla;
- parsiranje po eksplicitnoj verziji šeme;
- validaciju;
- pregled pre upisa;
- ručno rešavanje mogućih duplikata i izuzetaka;
- eksplicitnu potvrdu;
- idempotentno izvršenje;
- rezultat po redu;
- kontrolni izveštaj;
- istoriju uvoza i audit;
- odvojeno, naknadno slanje poziva roditeljima.

CSV je obavezni acceptance format. XLSX ostaje deo zaključanog MVP ugovora zato što već postoji u PRD 11, mapi ekrana i zvaničnim šablonima. Implementacija može koristiti zajednički normalizovani parser pipeline, ali CSV i XLSX adapteri moraju dati isti kanonski `ImportCandidate` rezultat.

### 2.2. Granice uvoza

Prva MVP verzija uvozi samo ciljeve definisane zaključanim PRD 11:

- decu/polaznike;
- jednog primarnog roditelja ili staratelja po detetu;
- vezu roditelj/staratelj–dete;
- članstva polaznika u već postojećim programima i grupama;
- lokalne šifre potrebne za kontrolisano povezivanje unutar škole.

Import ne kreira korisničke naloge, ne šalje pozive, ne kreira školu/ogranak/program/grupu/lokaciju i ne knjiži bankovne uplate. Uvoz početnih dugovanja ili istorijskih finansijskih zapisa nije odobren ovim DCR-om i ne sme se dodati bez finansijskog ugovora odgovarajućeg modula.

## 3. Konačna odluka o mySOKOLA

`mySOKOLA Basic` dobija status:

> `POST_MVP_PRE_PILOT_REQUIRED / APPROVED_FOR_IMPLEMENTATION_AFTER_MVP / DEFAULT_OFF_UNTIL_PILOT_ALLOWLIST`

To znači:

- mySOKOLA **nije deo MVP-a**;
- ne menja Core 7, Događaje Light niti acceptance 42 MVP površine;
- ne mora biti završen da bi se MVP kod proglasio tehnički završenim;
- postaje sledeća obavezna proizvodna etapa po logičkom redosledu posle MVP-a;
- implementira se i proverava pre spoljnog pilota sa stvarnim korisnicima i podacima dece;
- programer i Claude Code mogu da nastave direktno na mySOKOLA u istom repozitorijumu, bez čekanja nove procesne dozvole, kada postoji kompletan aktivni implementacioni ugovor za taj modul;
- može se nalaziti u istoj razvojnoj rundi, branchu ili seriji commitova kao MVP, ali ima zaseban status, feature flag i acceptance;
- funkcija ostaje `DEFAULT_OFF` dok njeni testovi, dozvole, tenant izolacija i pilot allowlist nisu spremni.

### 3.1. Odnos prema postojećim roditeljskim MVP površinama

MVP površine `P01–P08` ostaju obavezne za MVP. mySOKOLA ne sme da napravi paralelne master podatke niti drugi identitet roditelja ili deteta.

Pre-pilot implementacija mySOKOLA mora:

- ponovo koristiti postojeće `Person`, `UserAccount`, guardian, school membership, Finance, Events, Communication i Document izvore istine;
- koristiti purpose-limited projekcije samo kada su potrebne za portal;
- napraviti eksplicitnu mapu `P01–P08 → REUSE | REDIRECT | REPLACE | RETIRE_AFTER_MIGRATION`;
- sprečiti istovremeno održavanje dve neusaglašene roditeljske aplikacije;
- zadržati pravilo da dete nema nalog;
- zadržati invite-only pristup roditelja.

## 4. Redosled isporuke

Kanonski redosled je:

1. utvrđivanje stvarnog repo/staging baseline-a;
2. implementacija i testiranje MVP-a: Core 7 + Događaji Light + 42 površine + kontrolisani CSV/XLSX import;
3. tehničko prihvatanje MVP-a na sintetičkim podacima;
4. implementacija i testiranje `mySOKOLA Basic` prema zasebnom detaljnom ugovoru;
5. pilot hardening: bezbednost, privatnost, restore, tenant testovi, runbook, podrška i konfiguracija;
6. spoljni pilot sa allowlist-ovanom školom i minimalnim stvarnim podacima, tek kada su ispunjeni tehnički i pravni uslovi.

Ovaj redosled nije zahtev da programer prekida rad i traži novu dozvolu između koraka. To je redosled zavisnosti i isporuke. Kodiranje, testiranje, sintetički staging i priprema pilot funkcija mogu da se nastave bez procesnog čekanja.

## 5. Pilot nije isto što i kodiranje

Programer i Claude Code mogu odmah da:

- implementiraju MVP;
- implementiraju mySOKOLA kada njegov ugovor bude integrisan;
- implementiraju bezbednosne i operativne elemente za pilot;
- koriste isključivo sintetičke podatke;
- pripreme staging, migracije, seed, testove, backup/restore i runbook.

Spoljni pilot sa stvarnim podacima dece nije automatski odobren završetkom koda. Pre stvarnih podataka moraju biti potvrđeni tenant izolacija, server-side autorizacija, restore, pravna osnova, politike/DPA, retention, hosting/podizvršioci, privatnosna konfiguracija i podrška. Ovi uslovi ne predstavljaju blokadu za tehničku izradu.

## 6. Operations Light i ostali budući proizvodi

Operations Light ostaje `REGISTERED_FUTURE / DEFAULT_OFF / OUTSIDE_CURRENT_DELIVERY`. Nije deo M00–M21/M28 programmer candidate-a, MVP acceptance-a niti obavezna etapa pre mySOKOLA. Ovaj paket ne daje dovoljno ugovora za njegovo kodiranje; implementacija zahteva zaseban budući programmer candidate i ne sme se pokrenuti na osnovu samog registry reda.

SOKOLA Link, Skills Light, Events Pro, Sponsors/Network, Commerce i Growth ostaju zasebni moduli sa sopstvenim acceptance-om i podrazumevano su isključeni.
