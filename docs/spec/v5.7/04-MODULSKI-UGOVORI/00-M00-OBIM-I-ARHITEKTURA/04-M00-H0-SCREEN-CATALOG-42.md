---
tip: h0-screen-catalog
status: SPEC_CANDIDATE
obim: M00-M21
broj-povrsina: 42
datum: 2026-09-15
---

# M00 — Kanonski katalog 42 H0 UI površine

## 1. Autoritet i pravila

Ovaj katalog daje jedinstveno poslovno značenje svakom H0 UI ID-ju. UI ID i `surface_key` su stabilni ugovorni identifikatori; M19 sme vezati jednu ili više allow-listed ruta za istu površinu. Konkretan URL, framework, komponenta i vizuelni raspored ostaju repo-first odluka. Jedna površina sme imati tabove, detail rute ili responsive prikaze, ali se ne sme razlomiti tako da sakrije obavezni korak, niti spojiti tako da promeni autorizaciju ili domain owner-a.

`P01`–`P08` su H0 guardian/payer portal-foundation ID-jevi sa direktnom, subject-guarded Core/M19 kompozicijom. To ne aktivira M28. M28 je H1 pilot/projection overlay koji, tek uz svih pet svojih guardova, unapređuje iste ID-jeve; kada je OFF ili neefektivan, H0 fallback ostaje. Zato katalog ima tačno 42 ID-ja, a M28 ne uvodi 43. površinu niti postaje H0 PASS uslov.

Svaka privatna površina prolazi M01 session → M03 aktivni school context → M04 status/entitlement → M05 permission → owner resource guard → M07 subject/payer guard gde je primenljivo. UI visibility nije autorizacija. Svaki response nosi i klijent pre rendera proverava `school_id`, `context_version` i `authorization_version`. Skriven ili cross-tenant resurs daje safe 404. Poznat resurs bez akcione dozvole daje 403.

Offline poslovne mutacije su zabranjene osim M11 attendance reda na T02. Minimalni M19 shell/cache ne daje pravo da se finansije, dokumenti, saglasnosti, komunikacije, događaji, RBAC ili import izvrše offline. „Tri klika” se meri po M19 pravilima samo za navedene česte tokove; složeni administrativni unos nije lažno skraćen uklanjanjem potvrde ili validacije.

## 2. Platformske i zajedničke površine — A01–A03, X01–X04

| UI ID | `surface_key` | Površina i dozvoljeni akter | Poslovni owner / backend ugovor | Standardni ishod i offline |
|---|---|---|---|---|
| `A01` | `PLATFORM_CUSTOMERS_SCHOOLS` | Organizations, škole i provisioning; samo odgovarajuća platformska uloga | M04 Organization/School komande; M05 platform permission; M21 audit | Server-confirmed create/lifecycle; online, step-up/reason/ticket gde M04 zahteva. |
| `A02` | `PLATFORM_COMMERCIAL` | SaaS product/plan/agreement/entitlement upravljanje; samo PLATFORM_BILLING_ADMIN | M04 COM-01..20; M05 `platform.commercial.catalog.manage`, `platform.commercial.plans.manage`, `platform.commercial.agreements.manage`, `platform.commercial.agreements.acceptance.record`, `platform.commercial.adjustments.manage`, `platform.commercial.read` | Nema school-data pristupa iz payer veze; online, bez skrivene naknade ili retroaktivne cene. |
| `A03` | `PLATFORM_SECURITY_OPERATIONS` | Accounts, operacije i support radni red; samo tačna platform security/operations uloga | M01 account lifecycle, M05 Support Access/break-glass, M21 jobs/audit/release evidence | Maskirani minimum; nema trajnog impersonation-a; online i potpuno auditovano. |
| `X01` | `ACCESS_SIGN_IN` | Prijava postojećeg odraslog naloga | M01 provider/session; M19 pre-auth deep-link binding | Bez otvorene registracije i bez email auto-link-a; samo javni shell može offline. |
| `X02` | `ACCESS_INVITATION` | Prihvatanje važeće pozivnice i prvo povezivanje identiteta | M02 invitation/activation coordinator sa M01/M03–M07 owner portovima | Jedna atomska aktivacija ili potpuni rollback; online; token se nikad ne loguje/cache-uje. |
| `X03` | `ACCESS_CONTEXT` | Izbor aktivne škole i prikaznog workspace-a | M03 context switch; M05 workspace options; M19 shell | Organization nije pristup; switch rotira context version i purge-uje stari tenant prikaz. |
| `X04` | `ACCESS_ACCOUNT_SECURITY` | Lična bezbednost naloga, aktivne sesije i odjava | M01 session/logout/logout-all; M19 installation purge | Server receipt za revoke; lokalni purge obavezan i pri grešci provider logout-a. |

## 3. Vođeno otvaranje škole — O01–O07

Sve O površine zahtevaju M03 `SETUP_ONLY` ili regularni ACTIVE context sa odgovarajućim pravom. One komponuju postojeće owner ugovore; M20 ne postaje vlasnik School, Person, Group, finansije, dokumenta ili privacy odluke.

| UI ID | `surface_key` | Površina | Poslovni owner / backend ugovor | Završni dokaz i offline |
|---|---|---|---|---|
| `O01` | `ONBOARDING_SCHOOL_PROFILE` | Osnovni profil, locale i IANA timezone škole | M04 School profile/timezone komande | Validan server receipt; promena zone sa istorijom zahteva migration tok; online. |
| `O02` | `ONBOARDING_OWNER_ACCESS` | Status initial-owner nominacije, poziva i pristupa | M04 nomination + M02 invite + M01/M06/M05 atomska aktivacija | Nema javnog naloga ili prečice; online. |
| `O03` | `ONBOARDING_STRUCTURE` | Branch, discipline/program, location i space minimum | M08 owner komande | Najmanje jedna izvršiva struktura ili jasan blocker; online. |
| `O04` | `ONBOARDING_GROUPS_STAFF` | Group, staff assignment i početni termin | M09 Group/StaffAssignment + M10 schedule; M08 occupancy | Conflict je server-authoritative; nema implicitnog RBAC grant-a; online. |
| `O05` | `ONBOARDING_PEOPLE_IMPORT` | Ulaz u kontrolisani participant/guardian/enrollment import | M20 onboarding/readiness i M06–M09 owner koordinacija | Upućuje na M06–M09 UI tok; raw fajl nije IndexedDB/offline sadržaj. |
| `O06` | `ONBOARDING_FINANCE_GOVERNANCE` | Valuta, osnovni fee/billing config, obavezni dokumenti i privacy purpose-i | M04 currency; M12; M15; M17 | Svaki owner commit zasebno dokaziv; pravni tekst/odluka se ne pretpostavlja; online. |
| `O07` | `ONBOARDING_REVIEW_ACTIVATE` | Readiness pregled, blockeri i zahtev za School aktivaciju | M20 derived readiness + M04 activation; M21 evidence | Readiness nije pravni/pilot GO; aktivacija je server-confirmed, step-up/auditovana; online. |

## 4. Vlasnik i menadžer — M01–M15

UI prefiks `M` u ovoj tabeli znači manager surface, ne modul. Import ID-jevi M06–M09 ostaju tačno zaključani.

| UI ID | `surface_key` | Površina | Poslovni owner / backend ugovor | Ključni UX/bezbednosni ishod |
|---|---|---|---|---|
| `M01` | `MANAGER_HOME` | Autorizovani dashboard, attention i brze akcije | M19 composition; M18/M14 i owner summary query-ji | Nijedan widget ne prikazuje lažnu nulu; source freshness vidljiv; dnevna akcija dostupna u ≤3 interakcije. |
| `M02` | `MANAGER_SCHEDULE` | Dnevni/nedeljni raspored i uređivanje serije/termina | M10, uz M08 occupancy i M09 facts | Scope THIS/THIS_AND_FUTURE/ENTIRE je eksplicitan; conflict nema client override. |
| `M03` | `MANAGER_PEOPLE_ACCESS` | Ljudi, school membership, guardian/payer veze, role/delegation | M06, M07 i M05 kroz odvojene owner komande | Person/account/role nisu spojeni; sensitive child polja traže poseban guard. |
| `M04` | `MANAGER_PROGRAMS_GROUPS` | Programi, grupe, upisi i staff assignment | M08 Program + M09 Group/Enrollment/StaffAssignment | Cena/raspored/RBAC se ne upisuju u Group; online server receipt. |
| `M05` | `MANAGER_LOCATIONS_SPACES` | Branch, location, space, online access i occupancy | M08; M10/M16 occupancy consumeri | Cross-tenant booking detail je safe 404; online-access tajna se ne prikazuje u listi. |
| `M06` | `MANAGER_IMPORT_UPLOAD` | Izbor zvaničnog CSV/XLSX fajla | M20 schema/file intake | Magic/MIME/schema/limits pre staging-a; online, bez lokalnog trajnog PII. |
| `M07` | `MANAGER_IMPORT_VALIDATE` | Parsing, mapping, validacija i preview | M20 published schema/candidate model | Nema locale guessing-a; preview nije owner stanje; hash je vidljiv dokaz verzije. |
| `M08` | `MANAGER_IMPORT_RESOLVE` | Duplikati, konflikti i izuzeci | M20 duplicate resolution uz M06/M07/M09 read portove | Email/ime nije auto-link; svaki manual target i version ulaze u preview hash. |
| `M09` | `MANAGER_IMPORT_RESULT` | Execution rezultat, rejected report i controlisana recovery | M20 owner receipts/recovery | Per-row atomski ishod i zbir count-a; nema „undo” brisanja; online. |
| `M10` | `MANAGER_BILLING` | Cenovnik, billing run i obaveze | M12 Fee/Assessment/Obligation | Preview nije knjiženje; confirm je online all-or-nothing; tačna valuta/decimal. |
| `M11` | `MANAGER_PAYMENTS_CREDIT` | Uplate, alokacije, porodični kredit i refund review | M12 append-only payment/allocation/credit/refund ugovori | Nema kartičnog/fiktivnog uspeha; auto-credit default OFF; correction ne prepisuje istoriju. |
| `M12` | `MANAGER_REPORTS` | Izveštaji i analitika | M18 definitions/projection/snapshot/export | Period, formula, source cutoff i FRESH/STALE/PARTIAL/UNAVAILABLE su vidljivi; online export. |
| `M13` | `MANAGER_COMMUNICATIONS` | Ručne komunikacije, sistemske notifikacije i attention | M13 manual communication + M14 notification/attention | Publish koristi svež recipient hash; delivery nije read; nema detetu direktnog privatnog chata. |
| `M14` | `MANAGER_GOVERNANCE` | Dokumenti, privacy/consent zadaci i školski Support Access pregled/odobravanje | M15, M17 i M05 Support Access | Odvojeni owner ugovori i dozvole; download single-use; support aktivnost je vidljiva školi. |
| `M15` | `MANAGER_EVENTS` | Events Light lifecycle, registracije i event attendance | M16; neutralni M16+M12 coordinator samo za fee | Događaj i finansija commit-uju atomarno gde je potrebno; whole-event cancel aktivira finance barrier. |

## 5. Trener/nastavnik — T01–T05

| UI ID | `surface_key` | Površina | Poslovni owner / backend ugovor | Ključni UX/bezbednosni ishod |
|---|---|---|---|---|
| `T01` | `INSTRUCTOR_HOME` | Danas, sledeći dodeljeni termini i brzi attendance launch | M19 composition + M10/M09 | Jedan dodir otvara sledeći termin; samo assigned scope; nema finansijskih widgeta. |
| `T02` | `INSTRUCTOR_ATTENDANCE` | Evidencija, korekcija u roku i sync status | M11 | Bez izuzetka dve interakcije, sa izuzetkom najviše tri; jedini H0 offline queue; explicit confirm. |
| `T03` | `INSTRUCTOR_SCHEDULE` | Lični raspored i detalj dodeljenog termina | M10/M09 | Read/cache samo po M19/M11 rokovima; nedodeljeni resurs je safe 404. |
| `T04` | `INSTRUCTOR_GROUPS` | Dodeljene grupe i minimalni participant roster | M09/M06 uz assignment/field guard | Nema guardian grafa, finansija, zdravlja ili nedodeljenih grupa; list filter pre count/page. |
| `T05` | `INSTRUCTOR_UPDATES` | Dozvoljene komunikacije, dokumenti i event obaveštenja | M13/M14/M15/M16 read ugovori | Tabs ne spajaju owner podatke; download/akcija ponavlja owner guard; online za write/download. |

## 6. Roditelj/staratelj — P01–P08

| UI ID | `surface_key` | Površina | Poslovni owner / backend ugovor | Ključni UX/bezbednosni ishod |
|---|---|---|---|---|
| `P01` | `PORTAL_HOME` | Početni pregled i izbor povezanog deteta | M19 H0 composition; M03/M05/M07 + minimalne owner projekcije | Samo jedna aktivna škola; nema cross-school aggregate-a. |
| `P02` | `PORTAL_CHILDREN` | Moja deca i osnovni dozvoljeni profil; detail je podređena ruta `PORTAL_CHILD_OVERVIEW` | M06/M07 | Tačno aktivni guardian subject; payer-only basis nije dovoljan. |
| `P03` | `PORTAL_SCHEDULE` | Raspored povezanog deteta | M10 + M07 subject guard | Čitanje bez staff/internal podataka; tenant/context metadata obavezna. |
| `P04` | `PORTAL_ATTENDANCE` | Prisustvo povezanog deteta | M11 read projection + M07 | Read-only; roditelj ne koriguje evidenciju. |
| `P05` | `PORTAL_FINANCE` | Sopstvene obaveze, uplate, kredit i IPS instrukcija | M07 payer basis + M12 | Primljen, alociran i raspoloživ novac odvojeni; instrukcija nije uplata. |
| `P06` | `PORTAL_COMMUNICATIONS` | Objavljene komunikacije i sistemske notifikacije; notification tab/ruta je `PORTAL_NOTIFICATIONS` | M13/M14 | Samo current recipient basis; email/push bez osetljivog payload-a. |
| `P07` | `PORTAL_DOCUMENTS` | Dozvoljeni dokumenti, acceptance, notice i granularne saglasnosti; onboarding task ruta je `PORTAL_ONBOARDING` | M15/M17 | Foto/video odluke odvojene; opcioni consent nije uslov usluge; online server evidence. |
| `P08` | `PORTAL_EVENTS` | Events Light i prijava/otkazivanje povezanog deteta | M16; M12 samo fee coordinator/barrier | Standardni tok ≤3 interakcije; bez waitlist-a/optimistic final success-a; online. |

## 7. Obavezna mašinska provera i acceptance

1. Published M19 route registry vezuje svaki H0 business route za tačno jedan UI ID/`surface_key` iz ovog kataloga; svih 42 površine imaju najmanje jednu rutu. Podređene detail/tab rute su dozvoljene, ali nijedan H0 business route ne ostaje bez `surface_id`, niti postoji dodatna površina bez izričite promene kanona.
2. Svaki UI ID se pojavljuje tačno jednom; skup je tačno `A01–A03`, `X01–X04`, `O01–O07`, `M01–M15`, `T01–T05`, `P01–P08`.
3. Svaka aktivna UI business akcija mapira se na postojeću owner query/command porodicu i M05 permission; frontend ne orkestrira per-row ili cross-module mutacije koje pripadaju server application coordinator-u.
4. E2E koristi najmanje dva tenanta i naloge: platform operations, platform billing, school OWNER/MANAGER, INSTRUCTOR, GUARDIAN i PAYER_ONLY. Svaka površina ima success, forbidden, safe-404/cross-tenant gde postoji resource, stale-context i mobile/keyboard test.
5. `T02` je jedina površina koja sme kreirati offline poslovnu operaciju. Statička analiza i runtime policy test moraju odbiti offline queue sa bilo kog drugog `surface_id`/route-a.
6. Standardni tokovi M19: attendance, finance read, communication publish i event register/cancel moraju zadovoljiti definisano brojanje interakcija i jedan atomski finalni mutation request.
7. M28 sme zameniti presentation shell P01–P08 samo za pilot-enabled školu. H0 route značenje, owner ugovori i fallback ostaju nepromenjeni; M28 ne menja zbir od 42.
