# Usaglašena logika

Pravila dogovorena na osnovu beleški „Predlozi na osnovu trenutne radne verzije“.
Ovo su odluke, ne predlozi: kod, migracije i testovi ih sprovode, pa ih ne treba
ponovo dogovarati pri svakoj izmeni. Gde je pravilo pokriveno testom, test je
naveden , on je mesto gde se pravilo lomi ako ga neko slučajno promeni.

---

## 1. Lokacija je opšti pojam, ne „sala“

Aktivnosti se ne dešavaju samo u sali, pa model nosi pojam **lokacija**
(`structure_location`), a vrsta mesta je zaseban podatak (`Location.kind`):

`SPORTS_HALL` · `FIELD` · `KINDERGARTEN` · `SCHOOL` · `THEATRE` · `OUTDOOR` ·
`ONLINE` · `OTHER`

- Filter u Rasporedu je **„Sve lokacije“**.
- Postojeći redovi su migracijom označeni kao `OTHER`, nikada kao `SPORTS_HALL`:
  stari model nije imao vrstu, pa bi „sala“ bila izmišljen podatak.
- Termin (`session`), serija termina (`session_series`) i događaj (`event`)
  nose `location_id`.

## 2. Termini i događaji dele isti Raspored

Raspored je jedan kalendar. Filteri: **Sve aktivnosti / Termini / Događaji**,
plus Sve grupe, Svi treneri, **Sve lokacije**.

- Događaj je vizuelno različit od termina (isprekidana ivica, zvezdica, druga
  podloga , ne samo boja) i klik otvara njegov detalj.
- Podaci koje događaj nosi: naziv, kategorija (`EventType`, uključujući `Kamp` i
  `Pripreme`), datum/vreme početka i kraja, lokacija, **slobodan tekst za
  detaljnije lokacije**, odgovorna osoba, opis, status.
- Više lokacija za jedan događaj (npr. „Zlatibor , hotel X, teren Y“) rešava se
  poljem `location_note` uz jednu strukturisanu lokaciju. Kamp na više mesta je
  **jedan** događaj, ne nekoliko.
- `GET /events/calendar` je feed za osoblje i vraća i nacrte i otkazane
  događaje , planer mora da vidi ono što još nije objavio. Roditeljska lista
  (`GET /events`) i dalje prikazuje samo objavljeno.
- Aktivnost koja traje više dana prikazuje se kao **raspon datuma**, ne kao
  „10:57–10:57“.

## 3. Grupa je izvor podrazumevanih vrednosti

Grupa nosi `default_trainer_person_id` i `default_location_id`.

- Novi termin (i nova serija) **kopira** te vrednosti pri kreiranju.
- Kopira, ne čita kroz: promena podrazumevanog trenera grupe **ne sme** da
  prepiše ko je vodio prošli utorak.
- Vlasnik/menadžer može da promeni trenera i lokaciju **samo za taj termin**.
- Izričito poslat `null` znači „namerno nedodeljeno“ i pobeđuje nad
  podrazumevanom vrednošću; izostavljeno polje nasleđuje.

_Testovi:_ `tests/test_locations_and_defaults.py`

## 4. Ponavljajući termini

Serija je pravilo (`session_series`) plus termini koje je generisala. U formi
„Novi termin“ štiklirano „Ponavlja se“ pravi pravilo **i** generiše termine u
jednom koraku , pravilo bez termina ostavilo bi prazan kalendar.

Izmena termina iz serije nudi tri opsega:

| Izbor | Šta menja |
|---|---|
| Samo ovaj termin | samo tu jednu pojavu |
| Ovaj i svi naredni termini | šablon serije + svaku pojavu od ove nadalje |
| Cela serija | šablon serije + svaku predstojeću pojavu |

Prošli termini se **nikada** ne menjaju , oni su evidencija onoga što se desilo.

## 5. Polaznici i osoblje su različite stvari

Dva odvojena podatka, jer odgovaraju na dva pitanja:

- `OrganizationMembership.member_type` , šta je osoba **školi**:
  `ATTENDEE` (polaznik) · `STAFF` · `GUARDIAN` · `CONTACT`
- `GroupMembership.role` , u kom svojstvu je vezana za **grupu**:
  `MEMBER` (polaznik) · `TRAINER` · `ASSISTANT` · `OTHER_STAFF`

Posledice, sprovedene u kodu:

- U evidenciju prisustva ulaze **samo** `MEMBER` redovi.
- Obračun članarine tereti **samo** `MEMBER` redove.
- Ograničen kapacitet grupe troše **samo** polaznici; drugi trener ne popunjava
  grupu.
- Osoba može postojati bez naloga. Nalog je zaseban čin (kontrolisani poziv +
  uloga), pa se trener može dodeliti terminu i samo na osnovu `STAFF` članstva.

_Testovi:_ `tests/test_participant_vs_staff.py`

## 6. Prisustvo ima tačno dva stanja

**Prisutan** i **Odsutan**. Ništa treće.

- „Opravdano“ / „Neopravdano“ više ne postoje u interfejsu , ni na dugmadima ni
  u zbirnom pregledu. Da li je odsustvo opravdano je drugo pitanje i vodi se
  drugde.
- Zbirni pregled prikazuje: **prisutnih, odsutnih, neevidentiranih**.
- Procenat je `Prisutan / (Prisutan + Odsutan)`, dakle nad **evidentiranim**, ne
  nad spiskom. Neevidentirani se ne broje kao odsutni: lista koju niko nije ni
  otvorio inače bi prijavila „0% prisutnih“ umesto „prisustvo nije uneto“.
- Isti račun koristi i pregled na početnoj; termin bez sačuvane evidencije se
  uopšte ne uračunava (inače bi neuneto prisustvo prijavilo 100%).

## 7. „Aktivni članovi“ broji samo polaznike

Broji aktivna članstva tipa `ATTENDEE`. Ne ulaze: vlasnik, treneri/nastavnici,
roditelji/staratelji, kontakt osobe, neaktivni i arhivirani.

Migracija popunjava tip iz postojećih dodela uloga, pa je broj tačan od prvog
zahteva posle deploy-a, bez ručnog čišćenja. Osnivač škole se upisuje kao
`STAFF` , nova škola ne sme da krene sa „1 aktivan član“ pre nego što je iko
upisan.

## 8. Obaveštenja i komunikacija su dve stvari

- **„Obaveštenja“** (zvonce) , lične/sistemske notifikacije. Zvonce je
  **privremeno uklonjeno** dok iza njega ne stoji inbox: dugme koje pokazuje
  crvenu tačku i ne radi ništa čita se kao pokvareno, a ne kao nedovršeno.
- **„Komunikacija“** , objave i poruke koje škola šalje roditeljima i trenerima.
  Podnaslov u navigaciji je „Objave i poruke“, da se dva pojma ne preklapaju.

## 9. Tekst i formati

| Bilo | Sada |
|---|---|
| „Šta danas traži vašu pažnju?, Marko“ | „Šta danas traži vašu pažnju, Marko?“ |
| „Završeno prisustvo %“ | „Završena evidencija prisustva“ |
| „Europe/Belgrade“ | „Vremenska zona: Beograd“ |
| `2026-08` | „avgust 2026“ |
| „Nalog i podešavanja“ | „Nalog i podrška“ |
| status „Dospelo“ bez datuma | „Dospelo“ + datum dospeća, ili „Neplaćeno“ |

**Datumi se svuda pišu `DD.MM.YYYY`.** Formatiranje je centralizovano u
`src/lib/format.ts` , nijedan ekran ne sklapa datum sam i ne oslanja se na to
koji locale pregledač ima. (Izuzetak van naše kontrole: kalendar koji iscrtava
sam pregledač u `<input type="date">` prati podešavanja operativnog sistema.)

**„Dospelo“ je tvrdnja o vremenu, ne o statusu.** Neplaćeno zaduženje čiji je
rok tek sledeće nedelje nije dospelo. Reč se prikazuje samo kada rok postoji
**i** kada je prošao, i nikada bez datuma pored sebe.

Vlasniku škole se ne prikazuje „obratite se administratoru vaše škole“ , on to
i jeste. Vlasnik dobija kontakt SOKOLA podrške.

## 10. UI/UX

- **Horizontalni scroll na desktopu** rešen je u uzroku, ne sakrivanjem:
  `grid-template-columns: 250px minmax(0, 1fr)` i `min-width: 0` na koloni
  stranice, plus `minmax(0, …)` u form-gridovima. `overflow-x: hidden` bi samo
  sakrio dokaz i isekao sadržaj s njim.
- **Mobilna navigacija**: donja traka nosi 4 glavne stavke + „Više“. Ostalo
  (Komunikacija, Događaji, Izveštaji) je izlistano na stranici „Više“, pa ništa
  ne postaje nedostupno.
- **Finansije na uskim ekranima**: tabela se pretvara u kartice (svaka ćelija
  nosi svoju oznaku). Ostaje pravi `<table>`, pa semantika zaglavlja i čitači
  ekrana rade i dalje.
- **Aktivni i selektovani elementi** se ne oslanjaju samo na boju: kombinacija
  boje, podloge/ivice, debljine fonta i pozicionog indikatora (zlatna traka).
- **Tipografija**: osnovna veličina 16px (bila 15), cela skala pomerena za jedan
  korak. Tabelarne ćelije i oznake polja više nisu ispod 12px.
- **Logo**: veći na ulaznom ekranu (tamo brend jeste poruka), manji u zaglavlju
  aplikacije (tamo je samo orijentir).

## 11. NBS IPS QR na uplatnici , pomoć, ne plaćanje

QR kod je **pomoć pri popunjavanju naloga za uplatu** i ništa više.

**Šta jeste:** roditelj skenira kod u svojoj banci i ne prekucava račun, iznos i
poziv na broj.

**Šta nije:** plaćanje. Novac ide direktno sa računa roditelja na račun škole,
kroz njihovu banku. SOKOLA OS nije na toj putanji, ne saznaje da je prenos
obavljen i **nikada sam ne označava zaduženje kao plaćeno** , uplatu ručno
potvrđuje ovlašćena osoba škole nakon provere bankovnog računa. Kartice, platni
gateway, povezivanje sa bankom, automatsko knjiženje i automatski povraćaj
ostaju **van MVP-a**.

Detalji koji su deo pravila:

- Iznos u QR-u je **preostali dug**, ne prvobitni iznos , ponovo štampana
  uplatnica za delimično plaćeno zaduženje traži razliku, nikada ceo iznos.
- Poziv na broj je stalan (izveden iz id-a zaduženja i sačuvan), pa ponovo
  izdata uplatnica nosi isti broj koji je uplatilac već upotrebio. Model 97 sa
  kontrolnim ciframa po ISO 7064 MOD 97-10.
- `GET /charges/lookup?reference=…` vraća zaduženje za poziv na broj sa izvoda ,
  pomoć pri ručnoj potvrdi. Samo čita; ne zatvara zaduženje.
- Škola bez unetog broja računa dobija jasnu poruku umesto polu-validnog QR-a.
- Znakovi koji bi mogli da prekinu polje (`|`, novi red) se uklanjaju iz teksta
  koji unosi korisnik, da naziv škole ne može da falsifikuje ostatak sadržaja.
- Uplatnicu vidi osoblje sa finansijskim ovlašćenjem i roditelj , ali samo za
  svoje dete; tuđe zaduženje se ne razlikuje od nepostojećeg.

_Testovi:_ `tests/test_payment_slip.py`

## 12. Kasnije , javne stranice („SOKOLA Link“)

**Nije deo MVP-a i nije implementirano.** Zabeleženo je samo kao smer, da model
kasnije može da podrži javno objavljivanje bez velikog prepravljanja. Namerno
nisu dodate kolone „za kasnije“ , nekorišćeno polje u šemi je obaveza koju niko
ne održava, a odluke ispod se mogu sprovesti kad za njih dođe vreme.

Kada dođe red na to, važe ova ograničenja:

- Svaka škola opciono dobija javnu landing stranicu (jedan link za bio na
  Instagramu/TikTok-u).
- Javne stranice su **potpuno odvojene** od privatnih podataka aplikacije.
- Škola bira šta je javno. Ništa ne postaje javno automatski.
- Škola i događaj podržavaju javni link + statuse: **Nacrt, Objavljeno,
  Arhivirano** , odvojeno od životnog ciklusa događaja (`EventStatus`), jer
  „otkazan“ i „arhiviran“ nisu isto.
- Na javnim stranicama se **nikada** ne prikazuju: podaci dece i roditelja,
  spiskovi učesnika, prisustvo, finansije, privatni rasporedi, dokumenti,
  interne napomene.

Landing stranice, editor sadržaja, prijavne forme, SEO, analitika i sopstveni
domeni definišu se tek posle stabilnog MVP-a i pilota.
