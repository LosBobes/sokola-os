---
tip: repo-first-klasifikacija
status: TALAS-1-ZAVRSEN-TALAS-2-ODBLOKIRAN
baseline-commit: 92ccccc979fb53979081e84ded0c6e7aae56fb11
datum: 2026-09-18
scope: [M00-M21, M28]
---

# Repo-first klasifikacija — v5.7 ugovori naspram zatečenog koda

Prema `DCR-20260903-07` §3, svaka relevantna oblast dobija **tačno jednu** klasifikaciju sa
repo putanjom i dokazom:

| Oznaka | Značenje |
|---|---|
| `PRESERVE` | Postojeće ponašanje već ispunjava ugovor |
| `ADAPT` | Postojeći kod se minimalno prilagođava |
| `IMPLEMENT` | Capability ne postoji |
| `REMOVE_CONFLICT` | Postojeće ponašanje protivreči aktivnom ugovoru |
| `VERIFY_IN_REPO` | Stanje se ne može dokazati samo statičkim pregledom |

> **Šta ovaj dokument jeste.** Rezultat statičkog pregleda i izvršenog harness-a na commit-u
> `92ccccc`, kao ulaz u planiranje talasa. **Šta nije:** tvrdnja da je bilo koji modul
> `IMPLEMENTED`. Nijedan modul ispod nije prošao svoj v5.7 QA ugovor, jer ti testovi još
> nisu napisani. Zatečeni testovi (293) pokrivaju zatečeni proizvod, ne v5.7 QA tabele.

## 1. Zatečena arhitektura u jednoj slici

FastAPI modularni monolit, 22 domena pod `apps/api/app/domains/`, platformski sloj pod
`apps/api/app/platform/` (audit, outbox, idempotency, **clock** od Talasa 1), PostgreSQL 16
sa 42 tabele i jednim Alembic head-om (`a1c4f2d80b37`), React 19 SPA sa tri role shell-a
(manager / trainer / parent), transakcioni outbox + poll worker, OpenAPI parity gate.

Zatečeni model je **bliži v5.7 ugovorima nego što imena sugerišu**: tenant guard, audit,
outbox i idempotency već postoje kao pravi platformski portovi. Najveći raskoraci su
reprezentacija novca, odsustvo composite tenant FK/UNIQUE i to što v5.7 QA tabele još
nemaju svoje testove.

## 2. Terminološko mapiranje

`DCR-20260903-07` §3 zabranjuje preimenovanje funkcionalnog koda samo radi podudaranja sa
dokumentacijom. Mapa ispod je zato važila kao polazno stanje; odluka O-01 (§8) je svesno
odstupanje od tog pravila za jedan pojam, `Organization → School`.

| v5.7 pojam | Zatečeni kod | Status |
|---|---|---|
| School (H0 security tenant) | `School` / `school_id` | `PRESERVE` — preimenovano po O-01 |
| Organization (negrupišući, **ne** authorization domen) | ne postoji | `IMPLEMENT` (M04) |
| Person | `identity.Person` | `PRESERVE` |
| UserAccount | `identity.AuthAccount` + `AuthIdentifier` | `PRESERVE` |
| School membership | `school.SchoolMembership` | `PRESERVE` |
| Guardian relation | `people.GuardianRelationship` | `PRESERVE` |
| Payer relation | ne postoji kao zaseban autoritet | `IMPLEMENT` (M07/M12) |

✅ **Sudar imena je otklonjen.** Preimenovanje iz odluke O-01 je izvršeno (F-04): tenant se
svuda zove `School`/`school_id`. Reč `Organization` više se ne pojavljuje u kodu, pa je
slobodna za v5.7 značenje — negrupišući sloj iznad škole koji M04 uvodi i koji **nije**
authorization domen.

## 3. Klasifikacija po modulima

### Zajednički portovi (M00/M21 Talas 1)

| Oblast | Klasifikacija | Putanja / dokaz |
|---|---|---|
| Transakcija (jedan lokalni commit) | `PRESERVE` | `app/db.py`, session-per-request |
| Audit | **`PRESERVE` (dopunjeno u ovom radu)** | `app/platform/audit/` + `app/platform/audit/models.py`: per-tenant hash lanac, `verify_chain`/`verify_all_chains` i DB trigger koji odbija `UPDATE`/`DELETE` |
| Outbox (producer) | `PRESERVE` | `app/platform/outbox/service.py` — transakcioni enqueue, `FOR UPDATE SKIP LOCKED`, lease takeover, backoff, `DEAD_LETTER` |
| Inbox (consumer) | **`PRESERVE` (uvedeno u ovom radu)** | `app/platform/inbox/` — `InboxRecord(consumer, message_id)`; claim se upisuje u istoj transakciji kao i efekti handlera |
| Dead-letter dual control | **`PRESERVE` (uvedeno u ovom radu)** | `app/platform/outbox/dead_letter.py` — request/approve/reject, odobravalac ne sme biti podnosilac, replay/discard efekat, sve u zapečaćenom audit lancu. HTTP vezivanje čeka M05 support access (vidi F-09) |
| Idempotency receipt | `PRESERVE` | `app/platform/idempotency/service.py:hash_params` već radi kanonski hash (sortirani ključevi, kompaktni separatori) i odbija isti ključ sa drugim podacima. Expected-version semantika ostaje `VERIFY_IN_REPO` |
| **Clock** | **`PRESERVE` (uvedeno u ovom radu)** | `app/platform/clock.py` — UTC-aware, freezable; svih 17 zatečenih `datetime.now` mesta prevedeno |
| Exact decimal | **`PRESERVE` (uvedeno u ovom radu)** | `app/common/money.py` — Decimal, `NUMERIC(18,2)`, decimal string na žici; float se odbija. Vidi F-03 |
| Storage | `ADAPT` | `app/domains/documents/storage.py` — lokalni FS; nema tenant particije ni signed URL-a |
| PII-free observability | **`PRESERVE` (uvedeno u ovom radu)** | `app/platform/observability.py` — `safe_error`/`redact`; outbox `last_error` i log linija više ne nose PII. Vidi F-10 |

### Foundation (Talas 2)

| Modul | Klasifikacija | Putanja / dokaz |
|---|---|---|
| M01 Identity | `ADAPT` | `app/domains/identity/`, `app/security/{auth,password,oidc}.py`. Email+password i Google OIDC rade; session revocation i M01 revocation-on-every-request nisu dokazani |
| M02 Pozivnice | `ADAPT` | `identity/invite_tokens.py`, `Invitation` model, `tests/test_invitations.py`. Invite-only postoji; M02 ugovor je znatno širi (55 KB master) |
| M03 Multi-tenancy | `ADAPT` | `app/security/context.py`. Server-derived context postoji i testiran je; **nedostaju composite tenant FK/UNIQUE i RLS** (§7) |
| M04 School/Subscription | `IMPLEMENT` (§2.1–2.5 urađeno) | Anchor postoji: `organization`, `organization_school`, `school_locator`, `school_status_transition`, prošireni `school` (`app/domains/school/{models,anchor,locator}.py`, migracija `a4d76f2b91c0`, 30 testova). **Ostaje:** owner nomination/primary term (§2.6–2.7), entitlement i usage (§2.8–2.10), komercijalni sloj (§2.12–2.20), SCH-01..06 kao komande |
| M05 RBAC | `ADAPT` | `app/security/permissions.py` — per-area granted-areas model, restrikcija može samo sužavati. Nema support/break-glass pristupa ni v5.7 permission registra |
| M06 Ljudi i članstva | `PRESERVE`/`ADAPT` | `domains/people/`, `domains/organization/`, `tests/test_people_lifecycle.py` |
| M07 Roditelji/staratelji | `ADAPT` | `people.GuardianRelationship`, `GuardianOrganizationAccess`. **Payer relation ne postoji odvojeno od guardian-a** — M07/M12 zahtev |

### Operational Core (Talas 3)

| Modul | Klasifikacija | Putanja / dokaz |
|---|---|---|
| M08 Lokacije/resursi | `ADAPT` | `domains/structure/` — `Location`, `Room`, `Category`, `Program` |
| M09 Grupe/programi/upisi | `ADAPT` | `domains/groups/` — `Group`, `GroupMembership` sa lifecycle-om |
| M10 Raspored i termini | `ADAPT` | `domains/scheduling/` — `SessionSeries` + `Session`, recurrence, scoped edit. **DST resolver čuva lokalnu nameru, ali gap/overlap nije testiran** |
| M11 Prisustvo | `ADAPT` | `domains/attendance/`. **Offline mutation queue ne postoji** — M11 je jedini H0 offline write |
| M12 Finansije | `ADAPT` | `domains/billing/`, `domains/payments/` — reprezentacija novca usklađena sa §3 (F-03 otklonjen). I dalje nema append-only ledger/credit modela |
| M13 Komunikacija | `ADAPT` | `domains/communications/` — `Announcement`, ručno slanje |
| M14 Sistemske notifikacije | `ADAPT` | `communications.Notification` + outbox handleri. **M13 i M14 dele domen**, a ugovor traži da M14 bude zaseban idempotentni outbox consumer |
| M15 Dokumenti | `ADAPT` | `domains/documents/`. Nema immutable version/evidence ni session-bound re-autorizacije download range-a |
| M16 Događaji Light | `ADAPT` | `domains/events/` — `Event`, `EventRegistration`. Fee registration coordinator (M16+M12 u jednom commit-u) ne postoji |

### Završni H0 (Talas 4)

| Modul | Klasifikacija | Putanja / dokaz |
|---|---|---|
| M17 Privatnost | `ADAPT` | `domains/privacy/` — `ConsentRecord`, `DataSubjectRequest`, `RetentionPeriod` |
| M18 Izveštaji | `ADAPT` | `domains/reports/`. **Nema `PARTIAL`/`UNAVAILABLE` semantike, bitemporalnog cutoff-a, version hash-a ni <5 suppression-a** |
| M19 Dashboard/pretraga/PWA | `ADAPT` | `domains/search/`, `apps/web/` tri role shell-a. `apps/web/public/manifest.webmanifest` postoji, ali **nema service worker-a**, pa nema ni offline sloja ni M19 pravila „privatni PWA payload nije offline cache" |
| M20 Onboarding/import | `ADAPT` | `domains/onboarding/`, `domains/data_import/` sa `ImportBatch`/`ImportRow` staging-om. Usklađenost sa import schema v1 nije proverena |
| M21 Platformska pouzdanost | `IMPLEMENT` | **Od 40 job definicija iz kataloga v1 ne postoji nijedna kao imenovan job.** Postoji samo outbox poll worker. Nema lease/fencing, DR/restore ni release evidence |

### H1 (Talas 5)

| Modul | Klasifikacija | Putanja / dokaz |
|---|---|---|
| M28 mySOKOLA Basic | `IMPLEMENT` | `domains/parent/` postoji kao parent shell, ali nema entitlement/pilot/flag/permission/basis guardova. Mora ostati `DEFAULT_OFF_UNTIL_PILOT_ALLOWLIST` |

### H0 UI površine

`04-M00-H0-SCREEN-CATALOG-42.md` definiše 42 H0 ekrana. Zatečeni `apps/web/` ima tri role
shell-a, ali binding ekran→ugovor nije rađen. Klasifikacija: `VERIFY_IN_REPO`.

## 4. Nalazi (`CHALLENGE_NOT_APPLIED` kandidati)

### F-01 — `ALL_FUTURE` je čitao zidni sat (OTKLONJENO)

- **Dokument:** M10 master; `00-CLAUDE-CODE-IZVRSI.md` §2 talas 1 ("clock" port), §3 ("Trenuci su UTC/TIMESTAMPTZ").
- **Repo dokaz:** `app/domains/scheduling/service.py:442` je koristio `dt.datetime.now(tz=dt.UTC)` kao granicu za `ALL_FUTURE`; `tests/test_scheduling_series.py` vezuje seriju za fiksni `2026-09-01`.
- **Posledica:** test `test_edit_scope_all_future` je prolazio do `2026-09-01`, a od tada pada (`assert 9 == 12`) — pad zavisi od kalendara mašine, ne od koda. Isto je pretilo celom `scheduling` test modulu preko `_MAX_SCHEDULING_PAST` (730 dana) od `2028-09-01`.
- **Primenjeno rešenje:** uveden `app/platform/clock.py` (talas-1 port), svih 17 mesta prevedeno na njega, test modul zamrznut na `2026-08-31T09:00:00+00:00`. **Poslovno ponašanje nije menjano** — `ALL_FUTURE` i dalje znači "od sada nadalje"; promenjeno je samo to što "sada" više nije zidni sat.
- **Status:** `APPLIED`. `pytest` 293 passed, 0 failed.

### F-02 — root `npm run verify` je bio neispravan (OTKLONJENO)

- **Repo dokaz:** `package.json` je navodio `packages/contracts` (ne postoji) i `apps/api` (Python, nema `package.json`) kao npm workspace-e, a `verify:parity`/`verify:arch`/`verify:migrations` su pozivali tri `.mjs` skripte koje ne postoje. `npm query .workspace` je vraćao `[]`, a `npm run verify:arch` `MODULE_NOT_FOUND`. Web paket se zove `sokola-web`, pa je i `dev:web --workspace @sokola/web` bio mrtav.
- **Posledica:** nijedan root script nije radio. Nije bio CI pad (CI poziva Python komande direktno), ali ulazna tačka koja izgleda kao harness nije radila.
- **Primenjeno rešenje:** `workspaces` je sada samo `apps/web` (jedini stvarni npm paket); mrtvi `verify:*` script-ovi su uklonjeni; `verify` poziva stvarni harness (`verify:spec` → `verify:api` → web typecheck/build). Root ostaje tanak omotač i ne postaje drugi izvor istine.
- **Status:** `APPLIED`.

### F-03 — novac je bio integer minor-unit master (OTKLONJENO)

- **Dokument:** `00-CLAUDE-CODE-IZVRSI.md` §3: „Novac je `NUMERIC(18,2)` […] nema float/double […] ni paralelnog minor-unit mastera".
- **Repo dokaz (pre):** `Money(amount_minor: int)` i šest `integer` kolona: `billing_run.total_minor`, `charge.amount_due_minor`, `charge.amount_paid_minor`, `group.base_monthly_price_minor`, `group_membership.discount_minor`, `payment_record.amount_minor`.
- **Posledica:** bilo je tačno (nema float), ali je bio upravo zabranjeni paralelni master: svaka granica je morala da pamti da 12500 znači 125,00, a svaki čitalac koji zaboravi dobija iznos sto puta pogrešan koji i dalje izgleda uverljivo.
- **Primenjeno rešenje (odluka O-02, izvan reda talasa):** kolone su `NUMERIC(18,2)`, API nosi decimal string, `app/common/money.py` odbija `float` umesto da ga konvertuje (jer je `Decimal(0.1)` = 0.1000000000000000055511151231257827) i odbija veću preciznost od dozvoljene skale. Migracija `e8b47a3c9d16` deli sa 100 u NUMERIC aritmetici, u mestu preko `USING`, pa ne postoji trenutak u kome kolona drži oba zapisa. **Dokazano na stvarnim redovima:** 12500 → 125.00, 1 → 0.01, 0 → 0.00, 999999999 → 9999999.99; downgrade vraća.
- **Dve tačke koje nisu bile puka promena tipa:** billing preview hash je poslovni otisak, a `Decimal` nije JSON-serializabilan i nema stabilan `repr` kroz skale, pa se hešira wire format; `OVERPAYMENT` envelope je nosio iznos, što bi 409 pretvorilo u 500.
- **Web:** klijent radi aritmetiku nad novcem, pa ima sopstveni egzaktni pomoćnik — iznosi ostaju string, a jedina aritmetika je nad celobrojnim minor jedinicama (koje double predstavlja tačno daleko iznad bilo kog iznosa koji škola naplaćuje). `Math.round(amountMajor * 100)` je uklonjen; polja za iznos primaju tekst i prihvataju zarez kao decimalni separator.
- **Status:** `APPLIED`. 333 testa, web build zelen, OpenAPI i `schema.d.ts` regenerisani. Cypress se ne može pokrenuti ovde, pa je novčani tok odigran u stvarnom browseru preko Playwright-a: preview 3000,00 → zaduženje 3000,00 → uplata 1000 ostavlja 2000,00 i `Delimično plaćeno`, bez minor jedinica i bez `NaN` na ekranu.

### F-04 — `Organization` je značio dve stvari (OTKLONJENO)

- **Dokument:** `00-START-OVDE-PROGRAMER.md` §4: „Jedna škola je jedan H0 security tenant; Organization […] nije authorization domen."
- **Repo dokaz (pre):** `Organization` *jeste* bio authorization tenant kroz ceo kod — `organization_id` u 36 tabela i u svakom guard-u.
- **Posledica:** čim M04 uvede pravi v5.7 `Organization` sloj, ista reč bi u istom kodu značila i „tenant" i „ne-tenant grupisanje". To je oblik greške koji proizvede guard napisan nad pogrešnim pojmom, a čita se ispravno.
- **Primenjeno rešenje (odluka O-01, svesno odstupanje od DCR §3):** `Organization` → `School` svuda. Tabele `organization`/`organization_membership`/`guardian_organization_access`, kolona `organization_id` u 36 tabela, 39 ograničenja i indeksa, rute `/organizations` → `/schools`, i **tri uskladištene enum vrednosti** (`role_assignment.scope_type`, `invitation.scope_type`, `announcement.target_type`) plus `granted_areas` tekstualni niz. Migracija `f1c8d24b7a53` preimenuje u mestu — nema kopije ni trenutka u kome red postoji pod oba imena.
- **Dokaz:** `alembic check` potvrđuje da modeli odgovaraju preimenovanoj šemi. Round-trip nad stvarnim redom: `ORGANIZATION | ORGANIZATION,PEOPLE,ROLES` → `SCHOOL | SCHOOL,PEOPLE,ROLES` → nazad, pri čemu `PEOPLE` i `ROLES` ostaju netaknuti. 333 testa prolazi; oba korisnička toka odigrana u stvarnom browseru nad svežom bazom.
- **Posledica po kanon:** reč `Organization` je sada slobodna za v5.7 značenje koje M04 uvodi.
- **Status:** `APPLIED`.

### F-05 — `CURRENT-CODE-BASELINE.md` je istovremeno „popuni me" i hash-pokriven

- **Dokument:** `CURRENT-CODE-BASELINE.md` („Claude Code popunjava ovo automatski") naspram `MANIFEST-SHA256.md`, koji taj isti fajl pokriva među 72 hash-ovana fajla.
- **Posledica:** popunjavanje fajla na njegovom mestu trajno obara proveru integriteta transporta.
- **Primenjeno rešenje:** `docs/spec/v5.7/` ostaje bajt-identičan primljenom paketu (manifest prolazi, 72/72), a popunjeni baseline živi na `docs/CURRENT-CODE-BASELINE.md`. Nijedan dokaz nije izgubljen; razdvojeni su „šta je primljeno" i „šta je zatečeno".
- **Status:** `APPLIED` (proceduralno, bez izmene kanona).

### F-06 — nema nijedne od 40 M21 job definicija

- **Repo dokaz:** `app/worker.py` + `app/platform/outbox/worker.py` su jedini pozadinski proces; nema registra job-ova, lease/fencing-a ni dead-letter dual control-a.
- **Posledica:** M21 acceptance (39 H0 job-ova + 1 default-disabled M28) je u celini `IMPLEMENT`, što je najveći pojedinačni preostali obim u H0.
- **Status:** evidentirano kao obim, ne kao kontradikcija.

### F-07 — E2E scenario je vezan za fiksni datum (OTKLONJENO)

- **Repo dokaz:** `apps/web/cypress/e2e/people_and_schedule.cy.ts` je kucao `2026-09-01T17:00` u `session-start`. Raspored podrazumevano lista kotrljajući prozor `danas → danas+90` (`RANGE_DAYS`, `src/routes/manager/Schedule.tsx:49,274`), pa je 2026-09-01 ispao iz prozora kada je datum prošao i `[data-cy=session-row]` se više nije pojavljivao.
- **Posledica:** CI run 109 je pao na `people_and_schedule.cy.ts` sa „Expected to find element: `[data-cy=session-row]`, but never found it". **Nije regresija ovog PR-a:** web koristi JS `new Date()` i ne dodiruje Python clock port; ista klasa truljenja kao F-01, samo na E2E strani. Prethodni zeleni CI (run 108, 2026-08-19) je prošao jer je 2026-09-01 tada bio *u budućnosti*, unutar prozora.
- **Primenjeno rešenje:** datumi u scenariju su sada relativni — `dateTimeInput`, `tomorrow` i `nextWeekday` u `cypress/support/e2e.ts`. Drugi scenario (serija) je popravljen istim potezom iako je slučajno prolazio, jer je uzrok isti. Nijedan test nije preskočen ni oslabljen.
- **Status:** `APPLIED`.

### F-08 — generički inbox (OTKLONJENO)

- **Dokument:** `00-CLAUDE-CODE-IZVRSI.md` §2 talas 1 („outbox/inbox"), §3 („M14 je idempotentni outbox consumer").
- **Repo dokaz (pre):** producer strana je bila dobra, ali consumer strana nije imala inbox — `worker.py` je samo tvrdio da „every handler must be idempotent", a jedini consumer je to rešavao ručno preko `Notification.source_message_id`.
- **Posledica:** garancija je postojala samo za tog jednog consumer-a i samo zato što je autor toga bio svestan.
- **Primenjeno rešenje:** `app/platform/inbox/` sa `InboxRecord(consumer, message_id)` i `UNIQUE(consumer, message_id)`. Ključno je **gde** se claim upisuje: handler sada prima worker-ovu sesiju, pa njegovi upisi, inbox claim i `DELIVERED` status čine **jednu transakciju**. Replay ili vidi claim i ne radi ništa, ili se sve poništi zajedno i pokušava ponovo. Claim se upisuje kroz savepoint, da duplikat ne otruje pozivaočevu transakciju. Pad handlera sada radi `rollback` pre nego što se neuspeh evidentira (u zasebnoj transakciji), pa se delimičan efekat više ne commit-uje uz zapis o grešci.
- **Posledica po M14:** `source_message_id` ostaje kao poreklo (koji događaj je proizveo notifikaciju), ali više nije mehanizam dedupa — to je sada inbox.
- **Status:** `APPLIED`. 8 novih testova, uključujući replay bez ponovnog izvršenja, pad handlera koji ne ostavlja claim, i pad koji ne ostavlja delimičan upis.

### F-09 — dead-letter dual control nema HTTP vezivanje

- **Repo dokaz:** `app/platform/outbox/dead_letter.py` implementira ceo tok (zahtev → odobrenje/odbijanje, invarijanta „druga osoba", replay/discard efekat, audit), ali nema ruter.
- **Zašto:** operatorski endpoint traži M05 support/break-glass model pristupa, koji u repou **ne postoji**. Izmišljanje permisije samo za ovu površinu bilo bi upravo „paralelni authorization sistem" koji arhitektonski mandat zabranjuje.
- **Posledica:** mehanizam je kompletan i testiran (11 testova), ali ga za sada može pozvati samo kod, ne operator kroz API.
- **Minimalni predlog:** vezati na M05 support access čim postoji, u okviru M21 integracije. Do tada nema privremene permisije.
- **Status:** `CHALLENGE_NOT_APPLIED` — svesno odloženo vezivanje, ne nedostatak mehanizma.

### F-10 — `repr(exc)` je unosio PII u dead-letter i logove (OTKLONJENO)

- **Dokument:** `00-CLAUDE-CODE-IZVRSI.md` §3: „Log/metric/event/dead-letter ne sadrže token, credential, raw kontakt, child ime, dokument/poruku, bank reference ili iznos".
- **Repo dokaz:** `worker.py` je čuvao `repr(exc)` u `outbox_message.last_error` i logovao ga. SQLAlchemy uz poruku lepi `[SQL: ...]` i `[parameters: {...}]`, a PostgreSQL dodaje `DETAIL: Failing row contains (...)`. **Dokazano izvršavanjem:** pad pri upisu notifikacije stavio je ime deteta i email staratelja u `repr(exc)` (provereno na stvarnoj bazi pre popravke).
- **Posledica:** svaki pad handlera nad redom sa ličnim podacima trajno je upisivao te podatke u dead-letter zapis i u log — tiho, iz linije koda koja kaže samo `repr(exc)`.
- **Primenjeno rešenje:** `app/platform/observability.py`. Opis greške se **gradi iz strukture**, ne čisti iz teksta: tip izuzetka + SQLSTATE + tabela/kolona/ograničenje. Za bazu je to i precizniji dijagnostički podatak. Slobodan tekst je samo fallback i prolazi kroz `redact` (uklanja `[SQL:]`, `[parameters:]` i `DETAIL:` blokove, maskira email i duge nizove cifara, skraćuje). Skrabovanje samo po obrascima se **ne** oslanja da prepozna ime — zato se primarni put uopšte ne oslanja na tekst.
- **Status:** `APPLIED`. 7 testova, uključujući stvarni put pada worker-a sa imenom deteta, kontaktom i bankarskom referencom u redu.

### F-11 — `npm run typecheck` ne radi u celom repou

- **Repo dokaz:** `apps/web/package.json` ima `typecheck: tsc -b --noEmit`, ali repo nema `src/vite-env.d.ts`, pa TypeScript ne učitava `vite/client` tipove i svaki `import "./nesto.css"` puca sa `TS2882`. **Provereno na čistom `origin/main` u zasebnom worktree-u** — dakle zatečeno, ne posledica ovih izmena.
- **Posledica:** CI ne poziva `typecheck` (poziva `build`, koji prolazi jer `tsc -b` bez `--noEmit` emituje i razrešava drugačije), pa je ostalo neprimećeno. Ali root `verify` lanac koji sam dodao u F-02 poziva `typecheck:web`, pa je i on time polomljen.
- **Minimalni predlog:** dodati `apps/web/src/vite-env.d.ts` sa `/// <reference types="vite/client" />`.
- **Status:** `CHALLENGE_NOT_APPLIED` — ne širim PR o novcu time; ide uz sledeći harness PR.

### F-12 — samouslužno kreiranje škole protivreči M04 §3.2.1

- **Ugovor:** M04 §3.2.1: školu kreira **samo** actor sa `platform.schools.create` i svežom M01 step-up potvrdom. §9.10 traži da se javna self-registration putanja ukloni ako može napraviti nalog/pristup mimo M02.
- **Repo dokaz:** `POST /schools` (`app/domains/school/router.py:28`) dozvoljava bilo kom autentifikovanom licu da osnuje školu i time sebi dodeli `OWNER` role. To je cela postojeća putanja registracije; M20 onboarding, `tests/test_onboarding.py` i Cypress E2E svi počinju od nje.
- **Zašto nije primenjeno sada:** platform actor ne postoji dok ne postoje M05 (permission registry, support access) i M02 (owner nomination/invitation). Uklanjanje putanje sada ne bi je zamenilo ničim — obrisalo bi jedini način da škola nastane, i to u talasu čiji je ceo smisao da pripremi temelj za te module.
- **Šta je ipak urađeno:** putanja sada proizvodi **potpun M04 anchor** (organization + veza, oba lokatora, status tranzicija #1) u istoj transakciji, pa škola nastala kroz nju zadovoljava §3.1.3 i §3.7.1. Organizacija je označena placeholder-om (`case_reference = SELF_PROVISIONED`) da bi je kasniji ORG-04 transfer zamenio stvarnim pravnim licem.
- **Status:** `CHALLENGE_NOT_APPLIED` — svesno odloženo do M02/M05, uz zapisan trag u podacima koji kaže da organizacija nije dokazana.

### F-13 — kontakt škole nema key management osim env promenljivih

- **Ugovor:** M04 §2.0 traži `EncryptedContact` (AEAD sa key version i autentifikovanim context-om) i `Fingerprint256` (keyed HMAC-SHA-256 sa zasebnom verzijom ključa).
- **Repo dokaz:** pre ovog rada repo nije imao nijedan oblik enkripcije podataka u mirovanju. Postojeći presedan za tajne je `app/config.py` (`session_secret`, `password_pepper`) — env promenljive, bez KMS-a.
- **Šta je urađeno:** `app/platform/crypto.py` implementira oba tipa, sa dva **odvojena** keyring-a i rotacijom bez re-enkripcije (svaka sačuvana vrednost nosi verziju koja ju je napravila). Boot odbija neispravan keyring i objavljene dev ključeve van local/test.
- **Šta ostaje otvoreno:** ključevi žive u okruženju. Kompromitovan host čita kontakte. Modul to kaže eksplicitno umesto da implicira jaču garanciju.
- **Status:** `CHALLENGE_NOT_APPLIED` u delu key custody — arhitektonska odluka vlasnika proizvoda, spremna za zamenu KMS-om bez promene šeme.

## 5. Šta je u ovom radu stvarno urađeno

**Talas 0 — baseline i klasifikacija**

1. Paket verifikovan (72/72 SHA-256) i ugrađen u repo kao `docs/spec/v5.7/`, bajt-identičan.
2. `scripts/verify-spec-manifest.sh` — gate koji hvata tihu izmenu kanona (testiran i pozitivno i negativno).
3. Baseline popunjen stvarnim vrednostima i stvarnim exit kodovima → `docs/CURRENT-CODE-BASELINE.md`.
4. Klasifikacija svih M00–M21 + M28 oblasti (ovaj dokument).

**Talas 1 — zajednički portovi**

5. **Clock port** (`app/platform/clock.py`): UTC-aware, freezable; svih 17 zatečenih `datetime.now` mesta prevedeno; 7 testova. Usput otklonjen zatečeni pad (F-01).
6. **Audit seal** (`app/platform/audit/`): per-tenant hash lanac (`chain_key`, `sequence_no`, `prev_hash`, `row_hash`), `audit_chain_head` sa lock-om po lancu, `verify_chain`/`verify_all_chains`, i DB trigger koji odbija `UPDATE`/`DELETE`. Migracija `b7e2a4c91f08` backfiluje postojeće zapise pre nego što trigger počne da važi. 14 testova, uključujući stvarnu detekciju izmene, brisanja iz sredine i brisanja sa kraja.
7. **Inbox port** (`app/platform/inbox/`): `InboxRecord` + promena ugovora handlera (prima sesiju), pa su efekti i claim jedna transakcija. Migracija `c3f81d5e60a2`. 8 testova.
8. **Observability port** (`app/platform/observability.py`): `safe_error`/`redact`; PII više ne curi u dead-letter i logove. Migracija nije potrebna. 7 testova. Vidi F-10.
9. **Dead-letter dual control** (`app/platform/outbox/dead_letter.py`): zahtev/odobrenje/odbijanje sa invarijantom „druga osoba", replay vraća poruku u red sa resetovanim brojem pokušaja, discard je trajan, oba se upisuju u zapečaćeni audit lanac. Migracija `d5a92c74e8b1` sa parcijalnim unique indeksom (najviše jedan otvoren zahtev po poruci). 11 testova.
10. F-02 (root harness), F-07 (E2E fiksni datum), F-08 (inbox) i F-10 (PII u logovima) otklonjeni.

**Talas 2 — M04 school anchor**

11. **Contact protection port** (`app/platform/crypto.py`): `EncryptedContact` kao AES-256-GCM sa autentifikovanim context-om koji se **ne čuva** (ciphertext prebačen u drugi red ne dešifruje se, umesto da se pročita kao kontakt tog reda), i `Fingerprint256` kao keyed HMAC-SHA-256 sa zasebnom verzijom ključa. Dva nezavisna keyring-a, rotacija dodavanjem verzije bez re-enkripcije. Boot guard odbija neispravan keyring i objavljene dev ključeve u staging/production. 21 test. Vidi F-13.
12. **M04 §2.1–2.5 entiteti** (migracija `a4d76f2b91c0`):
    - `organization` — globalni pravno-komercijalni nosilac, nije tenant i nije authorization domain (§3.1.2);
    - `organization_school` — vremenski praćena veza, parcijalni unique `WHERE valid_to IS NULL`, transfer zatvara stari i otvara novi red **na isti trenutak**, pa istorija nema ni rupu ni preklapanje;
    - `school_locator` — `SLUG` i `SCHOOL_CODE`, tačno jedan aktivan po vrsti po školi, unique samo među aktivnima (penzionisana vrednost je istorija, ne rezervacija); rotacija je atomska i stari red pokazuje na novi;
    - `school_status_transition` — append-only autoritet, `UNIQUE(school_id, sequence_no)`, `from_status IS NULL` samo za #1;
    - `school` proširen na §2.2 (`provisioning_reference`, `school_kind`, `status`, `currency`, `language_tag`, `country_code`, kontakt ciphertext/fingerprint/masked, `activated_at`/`deactivated_at`, `version`) sa svim §2.2 `CHECK` ugovorima u bazi.
13. **Konsolidacija statusa:** `lifecycle_status` (IN_PREPARATION/ACTIVE) i `School.record_status` (korišćen kao prekidač deaktivacije) spojeni u jedan `status` po §5.2. Dva polja koja odgovaraju na isto pitanje su način na koji guard proveri pogrešno i deluje ispravno. Mapiranje je tačno §9.2 i ništa više; nepoznata vrednost prekida migraciju umesto da bude pogođena.
14. **Brownfield:** svaka zatečena škola dobija provisioning referencu, organizaciju i vezu, oba lokatora i tranziciju #1, bez promene `School.id`. Organizacije su označene kao placeholder (`SELF_PROVISIONED`) jer platforma nema dokaz o pravnom licu i §9.5 zabranjuje da ga izmisli. Provereno na bazi sa pet namerno nezgodnih redova (dijakritika, prazan slug, ime bez ijednog alfanumeričkog znaka, arhivirana škola, škola sa onboarding istorijom) — i uzvodno i nizvodno.
15. 30 novih testova za anchor, od kojih se sedam ne oslanja na servis nego direktno gađa bazu: to su garancije koje moraju važiti i kada ih neka buduća putanja zaobiđe.

## 6. Šta NIJE urađeno

- Nijedan v5.7 QA scenario nije implementiran. Zatečeni testovi pokrivaju zatečeni proizvod.
- **Talas 1 je završen osim exact decimal porta**, koji se isporučuje kroz F-03 kao zaseban PR (odluka O-02).
- Dead-letter dual control nema HTTP vezivanje dok M05 support access ne postoji (F-09).
- Talasi 2–5 nisu započeti. **Nijedan modul nije `IMPLEMENTED`.**
- F-03 (novac) i F-04 (imenovanje) i dalje čekaju — vidi ispod.
- Web `npm ci` nije uspeo u ovom okruženju (mrežna greška), pa web typecheck/build i Cypress **nisu izvršeni lokalno**; za njih je dokaz jedino CI.

## 7. Predloženi sledeći korak

Redosled je potvrdio vlasnik proizvoda 2026-09-18:

1. ~~**F-03** — novac na `NUMERIC(18,2)`~~ — urađeno.
2. ~~**F-04** — preimenovanje `Organization` → `School`~~ — urađeno.
3. Talas 2 (M04 → M06 → M01 → M03 → M05 → M07 → M02).

## 8. Odluke vlasnika proizvoda (2026-09-18)

Dve odluke odstupaju od onoga što bi implementacioni agent sam izabrao. Evidentiraju se ovde da kanon ne bi bio tiho promenjen, kako `DCR-20260903-07` §8 zahteva.

**O-01 — `Organization` se preimenuje u `School`.**
Agent je predložio da se postojeći `Organization` zadrži netaknut, a da v5.7 Organization kasnije uđe pod drugim imenom, jer `DCR-20260903-07` §3 izričito zabranjuje „preimenovanje funkcionalnog koda samo radi podudaranja sa nazivom iz dokumentacije". Vlasnik proizvoda je izabrao preimenovanje. **To je svesno odstupanje od DCR §3**, prihvaćeno radi jednoznačnosti imena pre nego što M04 uvede pravi Organization sloj. Obim: `organization_id` u 42 tabele, svaki guard, OpenAPI i web. Izvodi se kao zaseban PR sa backward-safe migracijom; poslovno ponašanje se ne menja.

**O-02 — F-03 se radi odmah, pre Talasa 2.**
Agent je predložio da migracija novca sačeka M12 u Talasu 3, po redosledu talasa iz DCR-a. Vlasnik proizvoda je izabrao da se uradi odmah, kao zaseban PR. Prihvaćeno; rizik je zabeležen: menja API i web istovremeno, a Cypress se ne može pokrenuti lokalno, pa E2E dokaz zavisi od CI-ja.
