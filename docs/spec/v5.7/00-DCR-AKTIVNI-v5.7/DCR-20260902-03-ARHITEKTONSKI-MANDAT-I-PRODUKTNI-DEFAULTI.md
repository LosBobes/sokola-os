---
tip: decision-change-record
dcr-id: DCR-20260902-03
status: APPROVED
datum: 2026-09-02
vlasnik: SOKOLA product owner
utice-na: [M07, M10, M11, M12, M13, M16, M17, M21]
---

# DCR-20260902-03 — Arhitektonski mandat i produktni defaulti

## Odluka

Arhitekta samostalno bira najbolje obrazloženo tehničko, sigurnosno, podatkovno i UX rešenje kada postoji jasan najbolji smer. Vlasniku proizvoda podižu se samo odluke koje menjaju poslovni model, cenu, pravnu obavezu, obećanje korisniku, MVP opseg ili nose teško reverzibilnu posledicu.

Javno dostupna dokumentacija konkurentskih i srodnih sistema koristi se kao istraživački input za dobre obrasce i poznate probleme. Ne kopira se tuđi model i ne širi se MVP bez dokazive vrednosti. SOKOLA ugovori, privatnost maloletnika, tenant izolacija i lokalni poslovni kontekst imaju prednost.

## Zaključani podrazumevani ugovori

1. Dodeljeni trener evidentira prisustvo od 30 minuta pre početka do 24 sata posle završetka. Posle toga vlasnik/menadžer koriguje uz obavezan razlog. Korekcija je nova revizija, nikada poslovno stanje „Ispravljena”.
2. Podrazumevano dospeće članarine je 10. u mesecu, uz školski i opcioni grupni override. Za upis usred meseca škola bira „ceo tekući mesec” ili „od sledećeg meseca”; nema automatskog pro-rata obračuna u MVP-u.
3. Nacrti komunikacije su server-side, imaju autosave i optimističko verzionisanje. Brišu se posle 90 dana neaktivnosti uz prethodno upozorenje i auditovani retention posao.
4. Events Light nema listu čekanja. Kanonski `HARD_LIMIT` strogo odbija prekoračenje kapaciteta. `WARNING` dopušta samo eksplicitni staff/admin override sa tačnim permission-om, razlogom i auditom; roditelj nema override. `NO_LIMIT` je treći eksplicitni režim i nema capacity vrednost. Ova terminologija zamenjuje ranije skraćene oznake `HARD`/`SOFT` bez promene poslovne odluke.
5. Škola u MVP-u ručno beleži metod, vreme, verifikatora i referencu dokaza odnosa staratelj–dete. SOKOLA OS ne čuva fotografiju ličnog dokumenta.

## Posledice

- Ove odluke se propagiraju tek u vlasničke module, bez preuranjenog dupliranja njihovih kompletnih ugovora u M01.
- Svaki modul i dalje mora dati lifecycle, greške, permissions, transakcije, audit, retention i QA dokaz.
- Ako buduća pravna analiza zahteva strože pravilo, menja se novim DCR-om; istorija se ne prepisuje.
