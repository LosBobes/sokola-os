---
tip: decision-change-record
dcr-id: DCR-20260903-07
naslov: Jednokratna predaja i kontrolisana etapna implementacija
datum: 2026-09-09
revizija: "2.0"
status: APPROVED
superseduje: DCR-20260903-07-revizija-1.0
---

# DCR-20260903-07 — Jednokratna predaja i kontrolisana etapna implementacija

## 1. Odluka

Programeru se predaje jedan sanitizovan i samostalan v5.7 programmer candidate sa M00–M21 i M28. Ne šalju se parcijalni modulni paketi, radne delte, interni razgovori niti naknadne korektivne komande koje su već ugrađene u aktivne ugovore.

M22–M27 i M29–M34 nisu deo ove implementacione predaje. Njihovi M00/DCR registry zapisi samo rezervišu vlasništvo i fail-closed buduće granice; nisu izvršna specifikacija, dozvola za kreiranje schema/ruta/jobova niti zahtev da ih agent kodira. Za bilo koji H3 modul potreban je naknadni zaseban programmer candidate sa masterom, QA ugovorom i eksplicitnim scope odobrenjem.

Implementacioni agent radi u postojećem brownfield repozitorijumu i deli posao na tehničke talase radi bezbednih migracija i testiranja. Ti talasi nisu odvojene dokumentacione predaje i ne zahtevaju pauzu ili novu dozvolu između njih kada je prethodni zavisni korak dokazivo prošao.

## 2. Obavezni implementacioni talasi

| Talas | Potpun obuhvat | Uslov aktivacije funkcije |
|---:|---|---|
| 1 | zajednički M00/M21 portovi: transakcija, receipt, audit, outbox/inbox, clock, exact decimal, storage i PII-free observability | Postojeći kod je prvo mapiran; nema paralelnog frameworka ili platformskog subsystem-a. |
| 2 | M04 School anchor → M06 → M01 → M03 → M05 → M07 → M02 → odloženi M04 composite constraint-i | Auth, tenant, permission i subject guard postoje pre izlaganja use-case-a. |
| 3 | M08 → M09 → M10 → M11 → M16 → M12 → M15 → M13 → M14 | Svaki owner modul ima backward-safe migraciju, idempotency, audit/outbox i svoj QA dokaz. |
| 4 | M17 → M18 → M19 → M20 → završne M21 job/DR/release veze | Privacy, report truth/freshness, PWA/search, import i operativni acceptance povezani su sa stvarnim owner portovima. |
| 5 | M28 mySOKOLA Basic | Tek nad stabilnim owner portovima; ostaje `DEFAULT_OFF_UNTIL_PILOT_ALLOWLIST` i ima zaseban H1 acceptance. |

Agent sme tehnički pripremiti kompatibilnu šemu kasnijeg talasa ranije kada to smanjuje migracioni rizik, ali ne sme aktivirati nepotpun use-case, zaobići guard ili proglasiti H1 delom H0 acceptance-a.

## 3. Repo-first klasifikacija

Svaka relevantna oblast dobija tačno jednu klasifikaciju sa repo putanjom i dokazom:

- `PRESERVE` — postojeće ponašanje već ispunjava ugovor;
- `ADAPT` — postojeći kod se minimalno prilagođava;
- `IMPLEMENT` — capability ne postoji;
- `REMOVE_CONFLICT` — postojeće ponašanje protivreči aktivnom ugovoru;
- `VERIFY_IN_REPO` — stanje se ne može dokazati samo statičkim pregledom.

Ne radi se big-bang rewrite niti preimenovanje funkcionalnog koda samo radi podudaranja sa nazivom iz dokumentacije. Poslovni rezultat, tenant/security guard, podaci, migracija i test dokaz moraju ipak biti ekvivalentni aktivnom ugovoru.

## 4. Svaki talas mora dati

1. backward-safe schema/migracioni redosled;
2. idempotentan backfill i reconciliation bez izmišljanja podataka;
3. primenjene composite FK/UNIQUE/CHECK i potrebne indekse;
4. automatizovane owner, integration, tenant-negative, subject-negative, concurrency i failure-injection testove;
5. rollback ili forward-recovery koji ne oživljava opozvani pristup ili nevalidan poslovni zapis;
6. stvarne komande, exit kodove i broj passed/failed/skipped/flaky testova;
7. changed-file/migration/test izveštaj koji automatski sastavlja implementacioni agent.

Ovo nije obaveza vlasnika proizvoda da ručno prikuplja međufazne izveštaje. Agent može nastaviti sledeći talas čim su zavisnosti stvarno zadovoljene, a objedinjeni dokaz vraća na kraju rada.

## 5. Sadržaj jedinstvenog programmer candidate-a

Paket sadrži samo:

- aktivne DCR-ove;
- četiri aktivna M00 ugovora;
- tačno jedan master i jedan QA ugovor za M01–M21 i M28, plus njihove potrebne registre, schema, integration i handover dokumente;
- `00-START-OVDE-PROGRAMER.md`, izvršnu repo-first instrukciju i prazan `CURRENT-CODE-BASELINE.md` ugovor;
- dokumentacioni validation report i SHA-256 manifest.

Paket ne sadrži lična imena, stvarne PII podatke, credentials, istorijske promptove, recovery/audit delte, interni razgovor, paralelni source of truth niti tvrdnju da je kod već implementiran.

## 6. Sanitizovani test podaci

Dozvoljeni su samo sintetički podaci. Email koristi rezervisani domen `example.invalid`; ID-jevi i tajne su test vrednosti bez veze sa stvarnim osobama ili tenantima. Dokumentacioni QA scenario je zahtev, ne rezultat testa.

## 7. Naziv transportnog ZIP-a

Naziv spoljnog ZIP-a bira vlasnik proizvoda u trenutku slanja. Implementacioni agent se oslanja na interne putanje i manifest, ne na naziv spoljnog fajla.

## 8. Novi nalaz tokom implementacije

Agent sme i mora prijaviti problem koji dokumentaciona revizija nije videla. Ne menja kanon tiho: vraća `CHALLENGE_NOT_APPLIED` sa dokumentom/paragrafom, repo dokazom, posledicom i minimalnim predlogom. Bezbednosni problem zaustavlja samo zavisnu opasnu mutaciju; sve nezavisne stavke se završavaju.

Ova procedura čuva mogućnost stručne korekcije bez pretvaranja implementacije u niz nepotrebnih administrativnih gate-ova.
