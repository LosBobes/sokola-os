---
tip: decision-change-record
status: ACTIVE
datum: 2026-09-09
revizija: "2.3"
programerski_kandidat_status: PROGRAMMER_CANDIDATE_CODE_REPOSITORY_UNVERIFIED
foundation_propagation_status: INCLUDED_IN_SAME_REPLACEMENT_PACK
superseduje: "DCR-20260907-01 revizije 1.0-1.2 i samo konfliktne delove ranijih aktivnih odluka"
---

# DCR-20260907-01 - Kanonska konsolidacija pre programerske predaje

## 1. Autoritet i način primene

Ova revizija zamenjuje ranije revizije istog DCR-a. Ne otvara v5.8, novi vault niti paralelni source of truth.

Odluke iz ovog DCR-a i aktivni fajlovi primenjuju se zajedno. DCR ne sme tvrditi da je drugi modul izmenjen ako njegov aktivni ugovor nije u istom samostalnom paketu. Ovaj paket sadrži M00–M21 i M28 master/QA/integration ugovore; dokumentacioni status je `PROGRAMMER_CANDIDATE`, a stanje aplikacionog koda je zasebno `CODE_REPOSITORY_UNVERIFIED` do pregleda konkretnog repoa.

`PROGRAMMER_CANDIDATE` znači da je normativni paket dovoljno zatvoren da implementacioni agent mapira postojeći kod i radi po njemu. Ne znači `IMPLEMENTED`, `CODE_COMPLETE`, `CORE_COMPLETE`, migracije primenjene ili testovi prošli. Te tvrdnje zahtevaju commit, migration head i izvršne test dokaze iz stvarnog repozitorijuma.

## 2. Zaključane granice proizvoda

- Aktivni dokumentacioni kontinuitet ostaje v5.7.
- Projekat je brownfield: postojeći ispravan kod se čuva, a menja se samo dokazani gap.
- Specifikacija određuje ponašanje, podatke, dozvole, greške i acceptance. Programer bira stack, framework, ORM, fizički API stil, strukturu repoa, mehanizam zaključavanja, queue, cache i deployment.
- H0 je Core 7 + Događaji Light, kontrolisani CSV/XLSX import i njihove foundations.
- Dete nema `UserAccount` u H0.
- MVP je invite-only. Javna self-registration ne kreira nalog, osobu, članstvo ili pristup.
- M28 mySOKOLA Basic je H1, odvojen acceptance, default OFF do pilot allowlist-e.
- Operations i budući event-only/venue-only proizvodi ostaju default OFF i nisu H0 acceptance.
- Finalni programmer paket ne sadrži lična imena, privatnu prepisku, recovery izveštaje, audit delte niti supersedovane dokumente.
- Supersedovani pre-modulski PRD/dizajn, recovery i audit-delta materijali nisu normativni i ne ulaze u programmer candidate. Za M00–M21/M28 entity, enum, command, permission, ownership i lifecycle važe samo aktivni ugovori u ovom paketu.

## 3. Jedini vlasnik svakog domena

| Podatak ili ponašanje | Jedini vlasnik | Zabranjeni paralelni autoritet |
|---|---|---|
| `UserAccount`, `AuthIdentity`, `AuthProviderRegistration`, `Session`, auth revocation | M01 | auth polja na `Person`; email kao identity/link ključ |
| `Invitation`, acceptance attempt, token digest i invite delivery | M02 | javna registracija; M13/M14 kao vlasnik invitation lifecycle-a |
| `TenantSecurityState`, tenant context i izolacija | M03 | novi `Tenant` master; Organization-wide pristup |
| `Organization`, `School`, school lifecycle, primary owner term, SaaS subscription/commercial foundation | M04 | M03 kao vlasnik `School`; M12 kao vlasnik SaaS naplate |
| policy, role, permission, authorization evaluation i Support Access | M05 | UI-only autorizacija; `SUPER_ADMIN`; trajni impersonation |
| `Person`, `SchoolPersonProfile`, `ParticipantProfile`, `StaffProfile`, `SchoolMembership` | M06 | `Person` u M01; uloga na `SchoolMembership` |
| `Family`, `FamilyMembership`, `GuardianChildLink`, `PayerChildLink`, verifikacija odnosa i primary guardian/payer designation | M07 | porodica kao authorization scope; payer status kao child-access dokaz |
| `Branch`, `Program`, `Location`, `LocationOnlineAccess`, `Space`, `SpaceOccupancyBlock` | M08 | `Branch` u M04; `Program` u M09; online tajna u schedule-u |
| `Group`, `GroupEnrollment`, transition history, transfer i `StaffGroupAssignment` | M09 | cena/schedule u grupi; `Program` master |
| raspored, recurrence i konkretni termini | M10 | attendance ili event kao termin master |
| attendance session, frozen as-of roster, record, correction i jedini H0 offline mutation queue | M11 | automatska poruka roditelju; drugi offline write domen |
| `FeeRuleVersion`, billing assessment, roditeljske obaveze, uplate/alokacije, tri korektivna toka, refund review i append-only `FamilyCreditLedgerEntry` | M12 | cena u M09/M16; M04 SaaS obračun; IPS instrukcija kao dokaz uplate |
| ručno kreirana komunikacija, draft, publish i njena isporuka | M13 | automatske sistemske notifikacije |
| `SystemNotification`, `AttentionItem` i potrošnja outbox događaja | M14 | sinhroni poziv source modula ka M14 |
| `Document`, immutable `DocumentVersion`, access i `DocumentAcceptanceEvidence` | M15 | kvalifikovani elektronski potpis bez eIDAS implementacije |
| `Event` i Events Light lifecycle | M16 | drugi `GuestEvent`; cena/kotizacija kao M16 source of truth |
| pravni osnov, privacy notice, granularne photo/video saglasnosti, withdrawal, retention i legal hold | M17 | jedna opšta "GDPR saglasnost" |
| report definicije/verzije, projekcije, koherentni snapshot-i i report export | M18 | client-side sabiranje; M18 kao business owner izvornog podatka |
| shell, navigation/composition manifest, globalna tenant-safe pretraga i PWA transport | M19 | M19 kao auth/tenant/owner autoritet; privatni service-worker cache |
| onboarding projekcija i kontrolisani CSV/XLSX import staging/execution | M20 | email auto-link; import kao owner master ili direct table write |
| audit/outbox/inbox transport, job runtime, dead letter, telemetry, backup/restore i release evidence | M21 | M21 kao business owner; PII u operativnom payload-u |
| mySOKOLA pilot, preference i portal projekcije | M28 | kopija child/finance/document/event mastera; cross-school privatna agregacija |

## 4. Zavisnosti bez kružnog autorstva

### 4.1. Četiri dozvoljene vrste odnosa

| Vrsta | Značenje |
|---|---|
| `SCHEMA_DEPENDENCY` | Modul A poseduje kolonu/FK čiji je cilj entitet modula B. Ovo određuje migracioni redosled. |
| `READ_CONTRACT` | A čita verzionisan, read-only port B-a. Nema direktnog pisanja u B. |
| `CONSUMES_EVENT` | A asinhrono konzumira minimalni događaj B-a. Producer nikad ne čeka consumer. |
| `APPLICATION_ORCHESTRATION` | Viši application sloj poziva više modula u jednom use-case-u. To nije dozvola da moduli pozivaju jedan drugog kružno. |

### 4.2. Foundation schema zavisnosti

| Od | Ka | Vrsta | Razlog |
|---|---|---|---|
| M01 | M06 | `SCHEMA_DEPENDENCY` | `UserAccount.person_id` referencira M06 `Person`. |
| M03 | M01 | `SCHEMA_DEPENDENCY` | `SessionTenantContext.session_id` referencira M01 `Session`. |
| M03 | M04 | `SCHEMA_DEPENDENCY` | tenant security/context redovi referenciraju M04 `School`. |
| M06 | M04 | `SCHEMA_DEPENDENCY` | `SchoolMembership.school_id` i tenant profili referenciraju `School`. |
| M05 | M06 | `SCHEMA_DEPENDENCY` | `RoleAssignment.school_membership_id` ima tenant-safe FK ka `SchoolMembership`. |
| M07 | M06 | `SCHEMA_DEPENDENCY` | family/guardian/payer veze koriste tenant-safe M06 `SchoolMembership` dokaz za svaku uključenu osobu. |
| M07 | M04 | `SCHEMA_DEPENDENCY` | svi M07 poslovni redovi pripadaju jednoj školi. |
| M02 | M04 | `SCHEMA_DEPENDENCY` | svaki poziv pripada jednoj školi. |
| M02 | M06 | `SCHEMA_DEPENDENCY` | svaki poziv cilja unapred postojeću odraslu `Person` kroz tenant-safe `SchoolPersonProfile`. |

M06 domain/persistence sloj ne uvozi i ne poziva M05. M05 poseduje evaluator i čita M06 `MembershipFacts`; M06 komande se autorizuju u application sloju pre poziva M06 use-case-a. Time ne postoji M05-M06 runtime ciklus.

M03 ne poziva M05 radi tenant autoriteta. M03 razrešava session i School tenant. Application kompozicija zatim poziva M05 za permission i vlasnički modul za resource/subject guard. Lista workspace opcija je read kompozicija M03 + M06 + M05, ne M03 domain zavisnost na M05.

M04 ne poziva M03 domain komandu iz svog domena. School provisioning application use-case u jednoj transakciji kreira M04 `School` i M03 `TenantSecurityState`, ili koristi dokazivo jednaku atomsku orkestraciju.

### 4.3. Foundation read ugovori

| Consumer | Provider | Port |
|---|---|---|
| M02 | M01 | provider proof, account/identity create-or-reuse i auth status |
| M02 | M04 | school status, owner nomination i activation eligibility |
| M02 | M05 | grant-authority snapshot i role/grant activation |
| M02 | M06 | account eligibility i membership create/activate |
| M02 | M07 | verified guardian relation i child/payer subject scope |
| M03 application composition | M06 | active memberships dostupne actoru |
| M03 application composition | M05 | prikazne workspace opcije; nisu tenant autoritet |
| M05 | M06 | `MembershipFacts` sa statusom i version-om |
| M05 | M07 | guardian/payer subject scope resolver |
| M07 | M06 | Person age/classification i school relation facts |

### 4.3a. Operational Core schema i read ugovori

| Consumer | Provider | Vrsta/port |
|---|---|---|
| M08 | M04 | `SCHEMA_DEPENDENCY` ka School; Branch/Program/Location su tenant sadržaj M08. |
| M09 | M06, M08 | Tenant-safe Participant/Staff profile i Program/Branch/Location reference. |
| M10 | M08, M09 | Group/assignment read + M08 occupancy u istoj lokalnoj transakciji. |
| M11 | M09, M10 | Frozen roster `as-of occurrence.starts_at` i occurrence authority. |
| M12 | M04, M06, M07 | Schema tenant/participant/payer-family osnova; M08/M09/M16 scope se validira read-only portom. |

M08-M16 ne uvode kružni domain poziv. M10 orkestrira M08 occupancy kroz transakcioni port; M08 ne poziva M10. M11 čita M09/M10 i emituje outbox; oni ne pozivaju M11. M12 validira billing scope read-only. Kod naplative M09/M16 radnje neutralni application coordinator poziva producer owner port i M12 owner port u jednoj lokalnoj transakciji; M09/M16 ne pozivaju M12, M12 ne poziva nazad producer tokom te komande i nijedan modul ne upisuje tuđu tabelu.

### 4.3b. Final Core i portal ugovori

| Consumer | Provider | Vrsta/port |
|---|---|---|
| M17 | M04, M06, M15 | Tenant/subject/document schema i read; M15/M17 evidence je neutralna application orkestracija u jednom local commit-u. |
| M18 | M04 + M06–M17 događaji/read projekcije | Bitemporalna read/event projekcija; owner podatke ne menja. |
| M19 | M01, M03–M18 | Shell/read composition i event-driven search projection; M03/M05/owner guardovi ostaju autoritet. |
| M20 | M04 + M02/M06–M12 owner portovi | Import staging u M20; svaki poslovni upis poziva owner port kroz application coordinator. |
| M21 | M04 schema + M17 policy snapshot | Platform interface implementira audit/outbox/job/storage/DR; ne poziva business owner radi reentrant odluke. |
| M28 | M01/M04/M07 schema; M01/M03–M07 guards; M06/M07/M10–M17/M19/M21 portovi | H1 portal composition, default OFF; nijedan owner modul ne zavisi od M28. |

Schema i `DOMAIN_READ_OR_CALL` grafovi moraju biti aciklični odvojeno. Event consumer, application coordinator i platform-interface veza ne menjaju domain ownership i ne smeju se koristiti da sakriju direktan kružni poziv.

### 4.4. Migracioni i use-case redosled

Ne postoji jedan linearni redosled koji se sme pogrešno tumačiti kao domain import graf.

Minimalni schema redosled za Foundation je:

1. M04 `Organization`/`School` tenant anchor;
2. M06 `Person` i `SchoolMembership` foundation;
3. M01 account/identity/session tabele sa FK ka `Person`;
4. M03 tenant security/context tabele;
5. M05 policy, role i grant tabele;
6. M07 family/guardian/payer tabele;
7. M02 invitation/attempt/delivery tabele.

Posle koraka 7 dodaju se i validiraju odloženi cross-module FK-ovi M04 owner modela ka M06 `SchoolPersonProfile`, M02 `Invitation` i M05 `RoleAssignment`. Oni su `DEFERRABLE` gde jedna atomska Foundation transakcija kreira obe strane. Pre te završne constraint faze nijedan Foundation use-case nije aktivan i nema dual-write ili perioda bez application guard-a.

Use-case implementacija se aktivira tek kada su svi njeni guardovi dostupni. Invitation acceptance je poslednji Foundation use-case jer orkestrira M01, M03, M04, M05, M06 i M07.

## 5. Tenant i authorization lanac

Za svaki zaštićeni request obavezan je redosled:

1. M01 validira account/session, revocation i `authorization_version`;
2. M03 razrešava tačan `School` tenant i `tenant_access_version`;
3. M06 potvrđuje važeći school membership kada je membership potreban;
4. M05 proverava permission i sveže role/grant verzije;
5. vlasnički modul razrešava resource unutar iste škole;
6. M07 ili drugi vlasnički modul primenjuje subject guard;
7. high-risk mutacija ponavlja security verzije neposredno pre commit-a.

Klijentski `school_id`, ruta, slug, kod škole, workspace, role label, JWT claim ili cache nisu authorization autoritet.

Cross-tenant i cross-subject target vraća isti safe `404` kao nepostojeći target kada actor nema pravo da sazna da resurs postoji. `403` se koristi samo kada actor već sme da zna identitet resursa, ali nema konkretnu akciju.

Opoziv account-a, membership-a, role/grant-a, guardian veze, payer scope-a ili škole važi za svaki request započet posle commit-a. Cache i outbox ne smeju otvoriti stale-allow prozor.

## 6. Globalni data ugovori

### 6.1. Novac

- DB: `NUMERIC(18,2)` ili strogo ekvivalentan exact-decimal tip.
- API/import/export/event: decimalni string u kanonskom formatu, plus ISO 4217 `currency_code`.
- Zaokruživanje: `ROUND_HALF_UP` na currency scale; H0 RSD scale je 2.
- Zabranjeni su binary float i paralelni integer minor-unit modeli.
- M04 poseduje SOKOLA-prema-klijentu komercijalni model; M12 poseduje škola-prema-porodici finansije.

### 6.2. Vreme

- Trenuci u bazi su UTC/TIMESTAMPTZ.
- Svaka škola ima IANA timezone; default `Europe/Belgrade`.
- Lokalna poslovna namera recurrence-a čuva lokalno vreme i zonu, ne samo izvedeni UTC.

### 6.3. Identifikatori i jezik

- Runtime kod, šema, kolone, enum/permission/error/event ključevi koriste English ASCII.
- UI tekst koristi i18n ključeve. Korisnički podaci i prevodi smeju koristiti latinicu i ćirilicu.
- Control, BiDi override, zero-width i soft-hyphen znakovi zabranjeni su u aktivnim dokumentima i runtime identifikatorima.

## 7. Family, guardian i payer foundation

- `Family` je tenant-scoped household/billing grupisanje. Nije authorization scope i samo članstvo u porodici ne otvara podatke deteta.
- Ista osoba sme biti u više porodica; isto dete sme pripadati dvema porodicama zbog podeljenih domaćinstava.
- `GuardianChildLink` je jedini dokaz guardian-child odnosa. Mora biti verifikovan pre digitalnog child pristupa.
- `PrimaryGuardianContactDesignation` je jedini primary-contact autoritet, najviše jedan aktivan po `(school_id, child_person_id)`.
- `PayerChildLink` je odvojen od guardian odnosa. Više aktivnih payer linkova je dozvoljeno radi budućeg split billing-a; ne daju child-data pristup i ne knjiže novac.
- `PrimaryPayerDesignation` bira najviše jedan default billing kontakt među ACTIVE payer linkovima; ne određuje procenat obaveze.
- M07 daje guardian/payer subject basis; M05 daje permission; M12 vodi iznose, odgovornost, split billing i ledger.
- M12 sada poseduje specifikovan `BillingResponsibilityRule`. H0 `split_billing_enabled=false` zahteva jednu odgovornost od 100%; više payer share-ova, do četiri i sa largest-remainder raspodelom, radi samo kada tenant capability bude eksplicitno uključen. Payer share nikada ne daje child-data pravo.

## 8. Offline, idempotency i concurrency

- Poslovne offline mutacije su default DENY.
- M11 `AttendanceRecord.status` ima tačno četiri domain vrednosti: `UNRECORDED`, `PRESENT`, `ABSENT`, `LATE`. Ova odluka kontrolisano superseduje zabranu statusa `LATE` od 18.08.2026. Client sync stanje nije peta attendance vrednost i čuva se odvojeno.
- Jedini H0 izuzetak je M11 attendance queue sa odvojenim `PENDING_SYNC`, `SYNCED`, `SYNC_FAILED` client stanjem.
- Server AttendanceRecord počinje kao `UNRECORDED`; UI sme predložiti `PRESENT`, ali bez eksplicitnog pregleda i confirm-a nema poslovnog upisa. Offline lease je actor/school/session vezan, sinhronizacija ponavlja autorizaciju, a lokalni podaci se brišu pri logout/session expiry/access revoke/tenant switch/user change.
- Finansije, pozivnice, identity/RBAC, family/guardian, dokumenti i event registracije zahtevaju server confirmation i ne smeju offline prikazati konačan uspeh.
- Svaka write komanda ima stabilni `request_id: UUID`, koji je kanonski idempotency ključ i na HTTP-u se mapira na `Idempotency-Key`, plus canonical payload hash i receipt.
- Isti ključ + isti payload vraća isti rezultat bez novog audit/outbox zapisa.
- Isti ključ + drugi payload vraća 409 namespaced `*_IDEMPOTENCY_KEY_REUSED`.
- Dok je prvi zahtev u toku, identičan retry čeka samo do definisanog kratkog command timeout-a; ako rezultat još nije dostupan vraća 409 `*_IDEMPOTENCY_IN_PROGRESS` i `Retry-After: 1`.
- `expected_version` i DB constraint/lock štite konkurentne izmene; test mora koristiti stvarne paralelne transakcije.

## 9. Outbox, audit i privatnost

- Poslovni commit, audit marker, command receipt i outbox zapis nastaju u istoj lokalnoj transakciji kada su deo iste poslovne odluke.
- Source modul upisuje događaj; ne poziva M14 i ne čeka notification delivery.
- Outbox payload sadrži opaque ID-eve, version, tenant ili eksplicitni platform scope i minimalni reason/type. Ne sadrži ime, email, telefon, raw token, dokument, zdravstveni podatak ili nepotreban iznos.
- Audit i telemetry su odvojeni. Telemetry ne sadrži PII, sadržaj, token ni finansijski iznos.
- Podaci dece se vraćaju po allow-list projekciji; list/count/search/export/cache/realtime/job/storage ponavljaju isti tenant i subject scope.

## 10. Predaja programeru

Čist kandidat obuhvata aktivne M00–M21 ugovore i njihove QA matrice, plus M28 kao H1/default-OFF modul sa zasebnim acceptance-om. Paket se predaje tek kada dokumentacioni cross-module validator i sanitizacija prođu; stanje koda se utvrđuje tek u stvarnom repou.

Programerski paket nalaže implementacionom agentu da prvo pregleda stvarni repo, sačuva validan kod i implementira samo dokazani gap. Paket ne garantuje da je nešto već implementirano.

M28 ostaje H1/default OFF i ne menja H0 acceptance. Implementacioni agent ga radi posle stabilnih owner portova M00–M21 ili paralelno samo kada ista backward-safe migracija/komponenta ne menja H0 poslovnu semantiku.

## 11. Dozvoljeni izazov kanonu

Claude ili implementacioni agent sme prijaviti novi problem, ali ga ne sme tiho rešiti promenom kanona. Nalaz mora sadržati: fajl i paragraf, reproduktibilan dokaz, posledicu, predlog i status `NOT_APPLIED`. Bezbednosni blocker sme zaustaviti samo zavisnu mutaciju; nezavisne zadate zamene moraju biti završene.
