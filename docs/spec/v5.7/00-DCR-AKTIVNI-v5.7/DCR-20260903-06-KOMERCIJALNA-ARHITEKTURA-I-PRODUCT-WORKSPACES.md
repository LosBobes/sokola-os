---
tip: decision-record
dcr-id: DCR-20260903-06
status: ACTIVE_ARCHITECTURE_DECISION
datum: 2026-09-03
vault: v5.7
pricing-status: OPEN_NOT_RUNTIME
revizija: "1.2"
---

# DCR-20260903-06 — Komercijalna arhitektura i product workspaces

## 1. Odluka

SOKOLA ostaje **jedna platforma** sa zajedničkim globalnim identitetom, auditom, integracionim standardom i komercijalnim katalogom. Ne pravi se poseban sistem za škole, događaje, hale, balone, kulturne ustanove, festivale ili turnire.

Zaključava se arhitektura koja podržava više proizvoda, billing metrika i ugovornih kombinacija bez hardkodiranja cena. **Ne zaključavaju se** konkretni nazivi paketa, iznosi, procenti, pragovi, popusti, besplatni periodi, poreske stope ili datum početka naplate. Nijedna brojčana cena nije runtime autoritet dok je budući zaseban pricing DCR ne odobri i dok ne postoji objavljena `CommercialPlanVersion`.

## 2. Tri odvojene ose koje se ne smeju pomešati

| Osa | Autoritet | Poslovna garancija |
|---|---|---|
| Ugovor i plaćanje SOKOLA-i | `Organization` + `CommercialAgreement` | Organization je kupac/platiša/primalac računa; jedna Organization može ugovoriti više proizvoda i više operativnih scope-ova. |
| Bezbednosni pristup podacima | M03/M05 authorization domain | Ugovor, račun ili vlasništvo Organization nikada samo po sebi ne daje pregled privatnih podataka. |
| Merenje korišćenja | Vlasnički modul metrike | Upotreba se meri u tačnom operativnom scope-u i periodu, uz immutable evidence; M04 ne izmišlja podatak ako izvor nije dostupan. |

`School` je i dalje jedini H0 tenant za School OS i podatke dece. On je jedinica korišćenja i entitlement-a, ali **nije nužno zaseban platiša niti zaseban račun**. Više škola iste Organization može imati odvojene usage stavke i jedan konsolidovani račun, bez cross-school pristupa.

## 3. Proizvodi i operativni scope-ovi

Početni product registry podržava ključeve:

| Product key | Namena | Operativni scope | Vlasnički modul / status |
|---|---|---|---|
| `SCHOOL_OS` | Core upravljanje školom/akademijom | `SCHOOL` | M00–M21; aktivni MVP obuhvat po postojećim odlukama. |
| `EVENTS` | Events Light, budući Events Pro, turniri i festivali | `SCHOOL`, a za event-only kupca `EVENT_ORGANIZER_WORKSPACE` | Events Light po postojećem scope-u; standalone/Pro ostaje default OFF do M30. |
| `VENUE` | Hala, balon, studio, scena, kulturna ustanova, prostori i booking | `VENUE_OPERATOR_WORKSPACE` + pojedinačni venue/space resursi | Future M33, default OFF. |
| `SPONSORS` | Sponsorship ugovori i atribucija | scope vlasnika kampanje/događaja, bez podataka dece | Future M31, default OFF. |
| `COMMERCE` | Online naplata, platform fee, settlement/payout/refund/dispute | tačna transakcija + njen operativni scope | Future M32, default OFF. |

Turnir i festival nisu novi paralelni core sistemi: oni su tipovi događaja sa svojim pravilima registracije, kapaciteta, timova, termina i naplate. Kulturna ustanova može biti venue operator, event organizer ili hibrid, bez kreiranja lažne škole.

## 4. Hibridni kupac i više gradova/lokacija

- Jedna Organization može imati više škola u različitim gradovima, a svaka škola više M08 lokacija/prostora i više M06/M09 instruktora.
- Grad, lokacija, vrtić, prostor, trener/instruktor i broj održanih Events Light događaja **ne proizvode automatsku dodatnu SOKOLA naknadu**.
- Naplativa je samo metrika koja postoji u prihvaćenoj, objavljenoj plan verziji i aktivnoj stavci ugovora.
- Hibridni kupac ima jedan `CommercialAgreement` sa više `CommercialAgreementItem` redova; ne otvaraju se dupli nalozi, Organizations ili nepovezane pretplate.
- Ista upotreba ne sme biti naplaćena dvaput kroz dva proizvoda ili dva pravila. Svako charge pravilo ima `exclusivity_group_key`; za isti chargeable event/transaction može pobediti najviše jedno SOKOLA pravilo iz grupe.

## 5. Podržane billing metrike

Arhitektura mora podržati, ali ne mora odmah aktivirati:

| Metric key | Jedinica i scope | Autoritativni izvor |
|---|---|---|
| `ACTIVE_PARTICIPANT_COUNT` | distinct aktivni učesnik po školi i obračunskom mesecu | M04 `SubscriptionBillingSnapshot` iz M09 enrollment istorije. |
| `ACTIVE_BOOKABLE_SPACE_COUNT` | distinct aktivan naplativ prostor po venue workspace-u/periodu | M33. |
| `EVENT_REGISTRATION_COUNT` | uspešna jedinstvena registracija po događaju/periodu | M30. |
| `EVENT_CAPACITY` | ugovoreni objavljeni kapacitet događaja | M30. |
| `TOURNAMENT_TEAM_COUNT` | prihvaćen jedinstven tim po turniru | M30. |
| `FESTIVAL_REGISTRATION_COUNT` | uspešna registracija/učesnički zapis po festivalu | M30. |
| `REALIZED_DIRECT_TRANSACTION_AMOUNT` | realizovan exact-decimal iznos + ISO 4217 valuta, bez neuspelih/storniranih delova | M32. |
| `REALIZED_MARKETPLACE_TRANSACTION_AMOUNT` | realizovan marketplace iznos | M32. |
| `REALIZED_SPONSORSHIP_AMOUNT` | realizovan, atribuiran sponsorship iznos | M31/M32. |

Svaka metrika ima vlasnika, verziju pravila, period, timezone/currency gde je primenljivo, idempotency key i immutable evidence ref. Nedostupan ili nepotpun izvor daje retryable 503 i **nikad se ne pretvara u nulu**.

## 6. Podržani oblici cene bez hardkodiranja

`CommercialPlanChargeRule` podržava:

- `FIXED_RECURRING`;
- `FIXED_ONE_TIME`;
- `TIERED_USAGE`;
- `PER_UNIT_USAGE`;
- `PERCENTAGE`;
- `PERCENTAGE_WITH_CAP`;
- `FIXED_DISCOUNT`;
- `PERCENTAGE_DISCOUNT`;
- `FREE_PERIOD`;
- `ZERO_RATED_INCLUDED`.

Periodi su `MONTHLY`, `ANNUAL`, `PER_EVENT`, `PER_BOOKING`, `PER_TRANSACTION` ili `NONE`. Novac se čuva kao `NUMERIC(18,2)` ili strogo ekvivalentan exact-decimal tip + ISO 4217 valuta, a API/import/export/event koristi kanonski decimalni string. Procenat ostaje integer basis points. Binary floating-point i paralelni integer minor-unit money model nisu dozvoljeni; isti ugovor važi u svim poslovnim modulima.

Plan je podatak, ne `if/else` u kodu. Objavljena plan verzija je immutable; promena pravi novu buduću verziju. Bez aktivne objavljene verzije sistem ne obračunava cenu i ne bira „razumnu“ vrednost.

## 7. Pravilo bez skrivenih naplata

Svaka SOKOLA charge stavka mora dokazivo imati:

1. aktivan prihvaćen `CommercialAgreementItem`;
2. tačnu immutable `CommercialPlanVersion` i `CommercialPlanChargeRule` ili zasebno potvrđeno transaction pravilo;
3. chargeable scope/period/metric evidence;
4. cenu, valutu, porez i eventualnu eksternu provider naknadu prikazane pre potvrde kada je korisnička transakcija;
5. audit i idempotency vezu koja sprečava duplo knjiženje.

Zabranjeno je:

- retroaktivno povećanje cene;
- automatski add-on, upgrade ili overage bez unapred prihvaćenog pravila;
- naplata po gradu/lokaciji/treneru/događaju samo zato što entitet postoji;
- skrivena aktivacija trial-to-paid prelaza;
- dve SOKOLA platform naknade za istu transakciju u istoj `exclusivity_group_key` grupi;
- predstavljanje naknade payment providera kao SOKOLA naknade ili obrnuto.

Za prag plan ima obavezni `threshold_behavior`:

- `BLOCK` — nova chargeable upotreba se ne dozvoljava iznad ugovorenog praga;
- `REQUIRE_ACCEPTANCE` — prikazuje se ponuda i zahteva novo eksplicitno prihvatanje;
- `CONTRACTED_OVERAGE` — dodatna naplata je dozvoljena samo ako objavljeno pravilo i prihvaćeni ugovor unapred sadrže formulu.

Nijedan drugi ili null ishod nije dozvoljen.

## 8. Fee ekskluzivnost i podržani modeli

Arhitektura mora moći da izrazi procenat sa cap-om za online plaćanje, različit procenat po verifikovanoj sponsorship atribuciji, marketplace fee, provider fee i popuste, ali njihove brojčane vrednosti nisu ovim DCR-om aktivirane.

Pravila:

- `provider_fee` je spoljna procesorska stavka i prikazuje se odvojeno;
- direct SOKOLA transaction fee i marketplace SOKOLA fee za isti promet pripadaju istoj exclusivity grupi i ne sabiraju se;
- ako posebno sponsorship-attribution pravilo zamenjuje drugo SOKOLA sponsorship pravilo, važi tačno jedno;
- neuspešna, odbijena, potpuno refundirana ili ručno/offline evidentirana uplata ne dobija online platform fee osim ako budući ugovor eksplicitno, zakonito i unapred kaže drugačije;
- refund/reversal nikad ne menja originalnu stavku; M32 knjiži korektivni događaj i primenjuje ugovoreno pravilo povraćaja naknade.

## 9. Entitlement, permission i feature flag nisu isto

- `CommercialAgreementItem` dokazuje šta je kupac ugovorio.
- `SchoolProductEntitlement` ili budući product-workspace entitlement određuje da li je capability efektivan u scope-u.
- M05 permission određuje ko sme da ga koristi.
- M03/M07 i vlasnički subject guard određuju nad kojim podacima.
- Feature flag kontroliše rollout i nikad ne proširuje ugovor, permission ili tenant scope.

Aktivacija/ukidanje entitlement-a prati ugovor, ali se obavlja atomarno i auditovano; entitlement nikad sam ne stvara charge niti pristup korisniku.

## 10. Privatnost i izolacija

- Komercijalni katalog, ugovor, usage evidence, charge, invoice i telemetry ne nose ime deteta, datum rođenja, kontakt, zdravstveni podatak, guardian vezu, sadržaj dokumenta ili fotografiju/video.
- Usage čuva agregat i opaque evidence ref. Ako je potreban drill-down za spor, on se radi u vlasničkom school/event modulu uz redovnu tenant/RBAC/subject autorizaciju; ne kopira se u billing.
- Organization ugovor i konsolidovani račun ne daju Organization korisniku automatski pregled škola.
- Event-only i venue-only podaci koriste zasebne authorization domene. `Organization` nije authorization domen, a non-school proizvod ne koristi lažni `School` samo da bi prošao M03/M05.

## 11. Vlasništvo modula i faze

| Odgovornost | Modul |
|---|---|
| Product/metric/plan/agreement foundation | Aktivni M04 ugovor. |
| School usage snapshot `ACTIVE_PARTICIPANT_COUNT` | M04 + M09 port. |
| School entitlement | M04. |
| School/user autorizacija | M03/M05. |
| Event/event-only scope i usage | M30 future, default OFF. |
| Sponsorship atribucija | M31 future, default OFF. |
| Charge assessment, invoice/order/payment/refund/settlement/payout/dispute | M32 future, default OFF. |
| Venue workspace, booking i usage | M33 future, default OFF. |

Aktuelni MVP i dalje koristi ranije potvrđene ručne metode plaćanja gde su definisane. Ovaj DCR ne uključuje automatsku SaaS naplatu, marketplace, kartice ili event/venue self-service u Core acceptance. On samo sprečava da se budući proizvodi grade kao paralelni sistemi ili uz skrivene cene.

## 12. Nepromenljive acceptance garancije

1. Organization A sa School A1/A2 može dobiti jedan ugovor/račun sa dve usage stavke, ali actor A1 bez A2 prava ne vidi A2 podatke.
2. Više gradova, lokacija, vrtića i instruktora ne menja charge bez eksplicitne metrike u prihvaćenom planu.
3. Kada je budući M30 event-only capability eksplicitno omogućen, kupac se provision-uje u `EVENT_ORGANIZER_WORKSPACE`, bez School reda; H0/M16 to sada ne aktivira.
4. Kada je budući M33 venue capability eksplicitno omogućen, venue-only kupac se provision-uje u `VENUE_OPERATOR_WORKSPACE`, bez School reda; H0 to sada ne aktivira.
5. Hibrid ima jedan agreement sa više stavki i nema duplo terećenje istog chargeable događaja.
6. Nijedan iznos se ne generiše iz programskog defaulta kada plan nije objavljen.
7. Buduća cena važi od svog efektivnog datuma; zatvoren period i postojeća charge stavka ostaju na staroj verziji.
8. Nepotpuna usage evidencija ne daje nulu niti račun; daje retry/attention.
9. Svaka naknada je pre obračuna sledljiva do prihvaćenog pravila i posle obračuna do immutable evidence-a.
10. Nijedan komercijalni log, metric label ili račun ne sadrži podatke deteta.
