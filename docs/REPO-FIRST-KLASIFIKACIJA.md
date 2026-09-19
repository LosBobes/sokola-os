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
| M01 Identity | `ADAPT` | §3.1–3.2, §4.5, §4.7, §4.9, §12, §13 i AUTH-02/03/04/05/08/09/10/11 isporučeni (migracije `a7e4c2f91b08`, `b8d3f60a51c7`, `c4a71e8b35d2`). AUTH-09/10/11 su portovi bez rute dok ne postoji M05. Preostaje AUTH-06/07, §10 rate limiti i provider step-up — vidi F-21, F-22, F-23 |
| M02 Pozivnice | `ADAPT` | `identity/invite_tokens.py`, `Invitation` model, `tests/test_invitations.py`. Invite-only postoji; M02 ugovor je znatno širi (55 KB master) |
| M03 Multi-tenancy | `ADAPT` | `app/security/context.py`. Server-derived context postoji i testiran je; **nedostaju composite tenant FK/UNIQUE i RLS** (§7) |
| M04 School/Subscription | `IMPLEMENT` (§2.1–2.8 urađeno) | Anchor: `organization`, `organization_school`, `school_locator`, `school_status_transition`, prošireni `school` (migracija `a4d76f2b91c0`, 30 testova). Ownership: `school_owner_nomination`, `school_primary_owner_term` sa composite tenant FK-ovima (`app/domains/school/ownership*.py`, migracija `b9e3c05a74d2`, 31 test). Entitlement: `school_product_entitlement` sa read-time pravilom efektivnosti (`app/domains/school/entitlements.py`, migracija `c1f4a86d39b7`, 23 testa). **Ostaje:** subscription usage (§2.9–2.10, blokirano — vidi F-15), komercijalni sloj (§2.12–2.20), SCH-01..06 / ORG-01..04 / OWN-01..04 / ENT-01..02 kao komande sa permisijama i step-up-om |
| M05 RBAC | `ADAPT` | `app/security/permissions.py` — per-area granted-areas model, restrikcija može samo sužavati. Nema support/break-glass pristupa ni v5.7 permission registra |
| M06 Ljudi i članstva | `ADAPT` (§2.1, §2.3–2.7 urađeno) | `Person` §2.1, `school_person_profile` §2.4 (migracija `d2a95e13c7f4`), `school_membership` §2.3 sa MEM-01..05 (`people/membership.py`, migracija `e6b1d47a2c98`), `participant_profile`/`staff_profile`/`person_merge_history_entry` §2.5–2.7 (`people/activity_profiles.py`, migracija `f3c92d81ab45`). 60 testova ukupno. **Ostaje:** §2.2 sensitive identifier (blokiran — vidi F-16), PER/MRG komande i HTTP površina za MEM komande |
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

### F-11 — `npm run typecheck` ne radi u celom repou (POVUČENO — nalaz je bio pogrešan)

- **Šta je tvrđeno:** da `apps/web` nema `src/vite-env.d.ts`, pa svaki `import "./nesto.css"` puca sa `TS2882`, i da je time i root `verify` lanac polomljen.
- **Šta je zapravo izmereno:** provera je pokrenuta u zasebnom worktree-u **u kojem `apps/web/node_modules` nije bio instaliran**. Greške koje sam video bile su `TS2307: Cannot find module 'react'`, `'react-router-dom'`, `react/jsx-runtime` — dakle nedostajuće zavisnosti, ne nedostajuća Vite deklaracija. Zaključak o `vite-env.d.ts` je izveden iz pogrešno pročitanog izlaza.
- **Provereno na čistom `origin/main` sa instaliranim zavisnostima:** `npm run typecheck` (`tsc -b --noEmit`, TypeScript 5.9.3) prolazi, `tsc --noEmit -p tsconfig.json` prolazi, i root lanac (`verify:spec`, `typecheck:web`, `build:web`) prolazi. Pod `moduleResolution: bundler` TypeScript uopšte ne razrešava `.css` import kao modul — dodat probni `import "./nepostojece.css"` takođe prolazi — pa `vite-env.d.ts` ovde ne bi ispravio ništa.
- **Šta stvarno stoji:** `src/vite-env.d.ts` zaista ne postoji, ali ništa u `src/` ne koristi `import.meta.env`, pa trenutno nema šta da tipizira. To je konvencija, ne kvar.
- **Status:** `WITHDRAWN`. Nalaz je bio moja greška u merenju, a ne stanje repoa. Zapisujem ga umesto da ga tiho obrišem, jer je bio i u opisu PR-a #74.

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

### F-14 — M04 referencira M06 `SchoolPersonProfile`, koji u repou ne postoji (OTKLONJENO)

- **Ugovor:** M04 §2.6 traži composite FK `(school_id, target_school_person_profile_id, target_person_id)` → M06 `SchoolPersonProfile(school_id, id, person_id)`.
- **Bilo:** M06 nije bio implementiran, pa je nominacija privremeno pokazivala na `SchoolMembership` — isti oblik ograničenja, druga tabela, i kolona namerno nazvana `target_membership_id` da ime ne tvrdi da postoji entitet koji ne postoji.
- **Primenjeno rešenje:** M06 §2.4 `school_person_profile` postoji (migracija `d2a95e13c7f4`), sa `UNIQUE(school_id, id, person_id)`, i nominacija je prebačena na njega. **Oblik ograničenja se nije promenio**, pa garancija — nominacija ne može pokazati na red druge škole — nije oslabljena ni na trenutak. Migracija prvo pravi profil za svaku zatečenu `(school_id, person_id)` kombinaciju sa članstvom, pa tek onda menja FK; obrnuto bi značilo prozor u kojem ograničenje nije zadovoljivo.
- **Dokaz:** probna baza sa dve osobe, školom, dva članstva i jednom nominacijom — uzvodno nominacija pokazuje na profil iste osobe i iste škole, nizvodno se vraća na `mem_1`. Pun round-trip.
- **Status:** `APPLIED`.

### F-15 — subscription usage (§2.9–2.10) ne može se izračunati: nema istorije statusa upisa

- **Ugovor:** M04 §3.9.4 traži broj distinct osoba čija **poslednja statusna tranzicija strogo pre preseka** glasi `ACTIVE`. §3.9.10 dodaje: kasni JOB koristi istoriju statusa, ne trenutne live kolone, a ako izvorna istorija nije potpuna — ne upisuje izmišljen broj, nego pada sa `SUBSCRIPTION_SOURCE_HISTORY_INCOMPLETE`.
- **Repo dokaz:** `GroupMembership` (`app/domains/groups/models.py`) menja `status` **u mestu**. Postoje `joined_at` i `ended_at`, ali nema nijednog reda koji beleži *kada* je članstvo prešlo u `SUSPENDED` ili nazad. Za bilo koji prošli trenutak T repo ne može da odgovori „koji je bio status ovog upisa u T".
- **Posledica:** snapshot za prošli mesec bio bi tačan samo za članstva koja su ceo mesec bila `ACTIVE` ili su se završila. Slučajevi koje §3.9.6 i §3.10.21 izričito pominju (suspenzija tačno na preseku, suspenzija usred meseca) davali bi pogrešan broj — a pogrešan broj koji izgleda uverljivo je gore od nedostajućeg.
- **Zašto nije zaobiđeno:** računanje iz `status` + `ended_at` bilo bi upravo „guessed zero"/guessed count koji §3.9.10 i §3.11.12 zabranjuju.
- **Minimalni predlog:** M09 dobija `group_membership_status_transition` append-only tabelu istog oblika kao `school_status_transition` (per-membership `sequence_no`, bez rupa). Tek onda §2.9–2.10 mogu da se implementiraju pošteno.
- **Status:** `CHALLENGE_NOT_APPLIED` — §2.8 (entitlement) je isporučen jer ne zavisi od ovoga; §2.9–2.10 čekaju M09.

### F-16 — `PersonSensitiveIdentifier` (§2.2, JMBG) čeka M17 purpose registry

- **Ugovor:** M06 §2.2 traži `lawful_purpose_code` iz **zatvorenog M17 registra**, a capability `people.sensitive_identifier` je **default OFF** i uključuje se tek kada M17 privacy-purpose registry ima potvrđen aktivan osnov i retention. Nepoznat/nevažeći razlog, nedostupan policy ili suvišno prikupljanje moraju biti odbijeni; ako verifier nije dostupan → 503 `M06_SENSITIVE_POLICY_UNAVAILABLE` i vrednost se **ne upisuje**.
- **Repo dokaz:** `app/domains/privacy/models.py` ima `ConsentRecord` sa `ConsentScope` — to je saglasnost osobe za opseg obrade, a ne registar zakonitih svrha sa retention-om koji §2.2 traži. Nema tabele koju bi `lawful_purpose_code` referencirao, ni načina da se „osnov je aktivan" autoritativno potvrdi.
- **Zašto nije zaobiđeno:** JMBG bez proverenog zakonitog osnova je tačno ono što §2.2 sprečava. Napraviti kolonu sa slobodnim `lawful_purpose_code` stringom značilo bi da polje *izgleda* kao da je prošlo policy proveru, a nije — gore nego da ne postoji.
- **Minimalni predlog:** M17 dobija registar svrha (`purpose_code`, aktivan osnov, retention period) i read port kojim M06 proverava osnov u istoj transakciji. Tek onda §2.2.
- **Status:** `CHALLENGE_NOT_APPLIED` — svesno odloženo do M17. Ovo je blokada koja štiti, ne propust.

### F-17 — sesija je bila potpisani kolačić bez servera: opoziv pojedinačne sesije nije bio moguć (OTKLONJENO)

- **Ugovor:** M01 §3.2 traži `Session` sa nepredvidivim `id`, `revoked_at`, `revoke_reason_code`, `idle_expires_at`, `absolute_expires_at` i `authorization_version_at_issue`. §4.7 traži da povećanje `authorization_version` **trenutno** poništi sve sesije naloga za svaki zahtev koji počne posle commit-a. §6 AUTH-04 opoziva **samo prezentovanu** sesiju, AUTH-05 sve.
- **Repo dokaz (pre):** `app/main.py` je montirao Starlette `SessionMiddleware`, a `_establish_session` je upisivao samo `person_id` i `csrf` u potpisani kolačić. Nije bilo tabele sesija, poređenja verzija ni `revoked_at`. `POST /auth/logout` je radio `request.session.clear()` — brisao kolačić u **tom** pretraživaču i ništa više. Kolačić izdat na tuđem uređaju važio je do isteka potpisa bez obzira na sve što se u međuvremenu dogodilo nalogu.
- **Rešenje (primenjeno, migracija `b8d3f60a51c7`):** `auth_session` je server-side red; potpisani kolačić nosi samo neprozirni credential, a baza čuva isključivo njegov SHA-256 digest. `AUTH-03 ValidateSession` teče pre svake zaštićene radnje i proverava hash, opoziv, **oba** isteka (30 min idle / 12 h absolute, §3.2 fail-closed default), `UserAccount.status = ACTIVE` i **tačno** poklapanje `authorization_version`.
- **Zašto poređenje verzije, a ne zastavica:** §4.7 kaže „bezbednost ne sme zavisiti od eventualnog outbox potrošača". Validacija čita `user_account` u **sopstvenoj transakciji** zahteva, pa između commit-a i odbijanja ne postoji keš koji bi mogao da zastari — M01-QA-021 nema prozor jer nema druge kopije odgovora. Outbox događaj `identity.authorization_invalidated` se i dalje emituje (§13, `scope_kind=PLATFORM`, `school_id=NULL`, dedupe key `user_account_id:authorization_version`), ali za gašenje realtime kanala i projekcija — nikad kao dokaz. Test `test_the_outbox_event_is_not_the_guard` briše događaj i pokazuje da odbijanje i dalje stoji.
- **Status:** `OTKLONJENO` za §3.2, §4.7, AUTH-03, AUTH-04 i AUTH-08. AUTH-05 (`LogoutAll` HTTP površina) čeka §12 idempotency receipt-e — vidi F-21.

### F-18 — Google prijava je usvajala postojeći nalog po jednakom email-u (OTKLONJENO)

- **Ugovor:** M01 §4.5: „Email podudaranje samo po sebi nikada ne linkuje nalog niti spaja osobe." §7 ponavlja: nema automatskog linkovanja preko jednakog email-a, telefona, imena, datuma rođenja, referral tokena ili invitation URL-a.
- **Repo dokaz (pre ovog PR-a):** `app/security/oidc.py::jit_provision` je, kada `sub` nije poznat, zvao `find_person_by_email(db, email)` i — ako nađe osobu — **zakačio Google subject na taj nalog** i vratio tu osobu. Ko god može da natera providera da tvrdi tuđu adresu, dobio bi tuđi nalog.
- **Rešenje (primenjeno):** `jit_provision` je sada idempotentan isključivo na `issuer + sub`. Nepoznat subject pravi novu osobu i novi nalog; ne traži nikoga po adresi. `find_person_by_email` je zamenjen sa `find_person_by_login_email`, koji gleda **samo** local-password identitete — tamo je adresa login handle tog providera, kao što je `sub` Google-ov, a ne most između providera.
- **Cena, svesno prihvaćena:** ista osoba koja se ranije registrovala lozinkom, a sada se prijavi Google-om, dobija **drugu** `Person`. To je M06 merge slučaj (postoji `PersonMergeRecord` tok), ne nešto što auth sme da reši tiho. §4.4 je izričit: običan login ne kreira ni ne spaja osobe.
- **Status:** `OTKLONJENO` — test `test_google_login_does_not_adopt_a_password_account_by_email` (M01-QA-012).

### F-19 — `password_auth_enabled` je bio podrazumevano `True`, a §4.9 traži OFF (OTKLONJENO)

- **Ugovor:** M01 §4.9: „Ne postoji local fallback login... ako za njega nema eksplicitnog adaptera, konfiguracije i testova. **Podrazumevano je OFF.**"
- **Repo dokaz (pre):** `app/config.py` → `password_auth_enabled: bool = True`. Adapter, konfiguracija i testovi **postoje** (`app/security/password_auth.py`, `SOKOLA_PASSWORD_AUTH_ENABLED`, `tests/test_password_auth.py`), pa metod nije bio sporan — sporan je bio default.
- **Rešenje (primenjeno):** default je `False`. Nijedan postojeći deployment se ne menja: `compose.prod.yml` već prosleđuje `"${SOKOLA_PASSWORD_AUTH_ENABLED:-true}"`, a `ops/hetzner/.env.prod.example` i `apps/api/.env.example` već imaju `=true`. Test suite eksplicitno postavlja `SOKOLA_PASSWORD_AUTH_ENABLED=true` u `conftest.py` — jer *jeste* deployment koji koristi adapter, i to treba da kaže naglas umesto da se osloni na default.
- **Zašto je default bitan iako se ništa ne menja:** deployment koji nikad nije rekao „da" nije rekao „da". Način prijave koji postoji zato što ga niko nije isključio je oblik svake slučajne auth površine.
- **Status:** `OTKLONJENO` — test `test_password_auth_is_off_by_default` proverava **deklarisani default polja**, ne konstruisani `Settings` (konstrukcija čita okruženje, pa bi dokazala samo da ga je suite uključio).

### F-20 — provider registry je postojao, ali ga callback nije proveravao (OTKLONJENO)

- **Ugovor:** M01 §3.2 + §6 AUTH-02: callback `issuer` mora se **tačno** poklopiti sa aktivnom registracijom, a audience/redirect/algoritam moraju biti na allowlist-i; inače `PROVIDER_NOT_ALLOWED` (M01-QA-019).
- **Repo dokaz (pre):** `auth_provider_registration` je postojala i bila popunjena, ali je `google_callback` verovao isključivo Authlib validaciji. Adapter koji je neko konfigurisao, a niko registrovao, mogao je da prijavljuje ljude — što je razlika između fail-closed registra i dekorativnog.
- **Rešenje (primenjeno):** `auth_providers.verify_callback` proverava aktivnu registraciju, **bajt-za-bajt** issuer, audience na allowlist-i, `alg` iz ID token header-a i redirect URI. Prazna audience lista odbija sve — deployment koji nije deklarisao svoj client id nije ga deklarisao, i „nekonfigurisano" ne sme da znači „bilo šta". Sve odbijanja vraćaju **istu** poruku (§11: „bez detalja konfiguracije"), sa testom koji to proverava za četiri različita razloga.
- **Šta ovo *ne* zamenjuje:** Authlib i dalje dokazuje da je token pravi. Registar odgovara na drugo pitanje — sme li pravi token od tog issuer-a uopšte da se koristi ovde.
- **Uz to (§13):** `auth.login_started`, `auth.login_failed` i `auth.login_succeeded` se sada upisuju. Neuspeh koji se nikad nije razrešio u nalog ostavlja `user_account_id` prazan, a reason code ne razlikuje „nepoznata adresa" od „pogrešna lozinka" — inače bi audit trail rekonstruisao enumeration oracle koji §11 drži van response body-ja, a log čita više ljudi nego odgovor.
- **Status:** `OTKLONJENO` za registry enforcement i login audit. §10 rate limiti (AUTH-01: 5/IP/10min, callback 20/IP/10min) ostaju — vidi F-23.

### F-21 — AUTH-05/09/10/11 i §12 receipt-i (DELIMIČNO OTKLONJENO)

- **Ugovor:** M01 §6 AUTH-05 traži da server, **pre** version bump-a i u istoj transakciji, sačuva minimalni `AuthCommandReceipt` za `(user_account_id, AUTH-05, request_id, canonical_payload_hash)`. Posle opoziva sopstvene sesije, identičan retry sme da upotrebi hash prezentovanog **opozvanog** credential-a isključivo da nađe isti receipt i vrati prethodni uspeh (M01-QA-020). §12 dodaje `Idempotency-Key` ↔ body `request_id` poklapanje, `IDEMPOTENCY_IN_PROGRESS` sa `Retry-After: 1` i `IDEMPOTENCY_KEY_REUSED`.
- **Rešenje (primenjeno, migracija `c4a71e8b35d2`):** `auth_command_receipt` je **account-scoped**, ne school-scoped — jedan nalog dopire do više škola, a §8 drži tenancy van auth putanje, pa postojeći `app/platform/idempotency` (sa `school_id NOT NULL`) ne odgovara. Kolona `revoked_credential_hash` je tačno ono što §6 traži: digest credential-a koji je ta komanda opozvala, kojim njegov nosilac može da preuzme **taj jedan** rezultat i ništa drugo. `retain_until` se upisuje, ne računa pri sweep-u, da naknadno skraćivanje session lifetime-a ne bi retroaktivno obrisalo receipt-e na koje klijent još ima pravo.
- **Šta je isporučeno:** AUTH-05 `LogoutAll` sa HTTP površinom (`POST /auth/logout-all`); AUTH-09/10/11 kao **portovi**, sa `expected_version`, zatvorenim reason kodovima, revoke-all i auditom.
- **Zašto AUTH-09/10/11 nemaju rutu:** §6 za svaku traži M05 dozvolu (`platform.accounts.suspend` i srodne), a M05 permission registry ne postoji. Ruta koja ne proverava ništa — ili proverava dozvolu koju je ovaj repo sam izmislio — bila bi gora od nepostojeće: izgledala bi kao da je ugovor ispunjen. Imena dozvola su deklarisana u `auth_enums.py` da M05 ima šta da registruje.
- **Status:** `OTKLONJENO` za §12 receipt-e, AUTH-05, AUTH-09, AUTH-10 i AUTH-11 kao portove. `CHALLENGE_NOT_APPLIED` za HTTP površine AUTH-09/10/11 — čekaju M05.

### F-22 — AUTH-05/06/07 traže „svežu ponovnu autentifikaciju", a nijedan adapter ne podržava step-up

- **Ugovor:** §6 AUTH-05 traži „aktivnu sesiju i **svežu ponovnu autentifikaciju** kada je provider podržava"; AUTH-06 i AUTH-07 traže je bezuslovno. §10 dodaje da step-up aktivira „samo provider ili eksplicitno odobrena konfiguracija, nikad ne aplikacioni improvizovani tok".
- **Repo dokaz:** Google adapter (`app/security/oidc.py`) ne šalje `prompt=login` ni `max_age`, i ne čita `auth_time` iz tokena; local-password adapter nema pojam step-up-a. `auth_session.auth_time` postoji i puni se, ali trenutno vremenom izdavanja sesije, ne trenutkom kada je provider stvarno autentifikovao osobu.
- **Zašto nije improvizovano:** §10 izričito zabranjuje aplikacioni improvizovani tok. Ponovno traženje lozinke u našoj formi nije provider step-up i dalo bi lažan osećaj da je AUTH-06/07 uslov ispunjen.
- **Minimalni predlog:** Google adapter dobija `prompt=login` + `max_age` na step-up putanji i upisuje `auth_time` iz ID tokena; local-password adapter dobija eksplicitnu ponovnu proveru lozinke **označenu kao slabiju** u `assurance_context`, pa politika može da odbije step-up za osetljive komande.
- **Status:** `CHALLENGE_NOT_APPLIED` — ide zajedno sa callback hardening isečkom (F-20), koji ionako dira isti adapter. AUTH-05 je isporučen sa aktivnom sesijom kao jedinim uslovom, i to je u PR-u eksplicitno rečeno.


### F-23 — §10 rate limiti još ne postoje

- **Ugovor:** M01 §6 AUTH-01 traži 5 startova po IP za 10 min i 10 po browser/device signalu za 24 h; §10 dodaje 20 callback neuspeha po IP za 10 min. Limiti su **keyed hash** IP/device signala, kratko se čuvaju po M17 i ne koriste se za profilisanje. Prekoračenje je `RATE_LIMITED` bez detalja (M01-QA-013).
- **Repo dokaz:** nema nijednog rate limitera; `RateLimitedError` sa `Retry-After` postoji u `app/common/errors.py` od ovog isečka, ali ga niko ne podiže.
- **Zašto nije ovde:** potreban je brojački store sa TTL-om. Repo nema Redis, a tabela u Postgresu za brojanje po IP-u je izvodljiva ali je zaseban dizajn (retention po M17, keyed hash sa sopstvenim ključem, čišćenje). Nakalemiti ga na ovaj isečak značilo bi jedan PR koji istovremeno menja callback validaciju i uvodi novi platform mehanizam.
- **Status:** `CHALLENGE_NOT_APPLIED` — sledeći M01 isečak, zajedno sa step-up-om (F-22), koji dira isti adapter.

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
16. **M04 §2.6–2.7 — ownership** (migracija `b9e3c05a74d2`):
    - `school_owner_nomination` — namera škole da imenovana osoba postane vlasnik, odvojena od poziva koji je nosi. Parcijalni unique dozvoljava najviše jednu `PENDING INITIAL_PRIMARY_OWNER` po školi; istekao poziv **ne** gasi nominaciju, jer „poziv je istekao" i „pogrešili smo osobu" nisu isti događaj — drugo je `CANCELLED`, sa zatvorenim razlogom.
    - `school_primary_owner_term` — vremenski sled tačno jednog primarnog vlasnika, parcijalni unique `WHERE valid_to IS NULL`; prenos zatvara stari i otvara novi term na isti trenutak i **ne dira role set** (§3.4.8): stari vlasnik ostaje OWNER, jer tiho oduzimanje uloge pretvara prenos u zaključavanje.
    - §3.4.5 kao dva pravila koja se slažu: dodatni vlasnik uvek sme da ode, uloga primarnog ne sme pre prenosa primarnosti — pa nijedan redosled uklanjanja ne dolazi do nule.
17. **M06 §2.5–2.7 — profili aktivnosti i istorija spajanja** (migracija `f3c92d81ab45`): `participant_profile`, `staff_profile` i `person_merge_history_entry`. Ključna stvar je composite FK koji uključuje **tip članstva**: `(school_id, school_membership_id, membership_type)` → `school_membership(school_id, id, membership_type)`. §6 ima kod za nepoklapanje tipa (`M06_PROFILE_TYPE_MISMATCH`); ovo ga čini nedostižnim — profil polaznika na STAFF članstvu se ne može upisati nijednim putem, a ne samo da ga servis odbija. Profili **nemaju sopstveni status** (§5): efektivnost prati članstvo, jer na pitanje „da li je osoba aktivna ovde" postoji jedan odgovor. `specialization_codes` se sortira i dedupira na upisu — dva profila sa istim specijalnostima u različitom redosledu su isti profil. Istorija spajanja je immutable po konstrukciji: bez `updated_at` i bez verzije.
18. **M06 §2.3 — članstvo kao epizoda** (migracija `e6b1d47a2c98`): `member_type` → `membership_type` sa `ATTENDEE` → `PARTICIPANT`, status dobija `DRAFT` i `ENDED` → `TERMINATED`, plus `start_date`/`end_date`, razlozi suspenzije i prekida, `is_first_activation` i `version`. Parcijalni unique je sada `(school_id, person_id, membership_type) WHERE status <> 'TERMINATED'`, a **stari `UNIQUE(school_id, person_id)` je uklonjen** jer je §3.2 izričit da jedna osoba može imati više tipova članstva u istoj školi — roditelj koji je i trener je oboje, a stari constraint je drugo činio nemogućim. `TERMINATED` je terminalan i povratak je **nov red**: oživljavanje starog bi prepisalo kada je osoba ranije bila član, a to je jedino zbog čega škola može da odgovori „da li je porodica otišla pa se vratila". `is_first_activation` se izvodi jednom pri aktivaciji i zamrzava, pa kasnija epizoda ne pretvara raniju u povratak.
    `local_member_code` i `admin_note` **prelaze na profil** kao `local_person_code` i `administrative_note` — oni opisuju osobu kako je škola vodi (§2.4), ne jedno njeno članstvo; ostaviti ih na oba mesta bilo bi isti „dva polja jedno pitanje" problem koji je konsolidacija statusa škole uklonila. Imena polja u API-ju ostaju nepromenjena: to je zatečeni javni ugovor, a M06 ne propisuje oblik API-ja.
    `start_date` se backfiluje iz `created_at` **u zoni škole, ne u UTC-u**: članstvo napravljeno u 23:30 po Beogradu pripada tom danu, a UTC bi ga zaveo pod sledeći (provereno: 22:30 UTC 10.05. je 11.05. u Beogradu).
19. **M06 §2.1, §2.4 — osoba i školski profil** (migracija `d2a95e13c7f4`): `Person` dobija rođendan (nepoznat je dozvoljen i znači „uzrast nije dokazan", ne pretpostavku), kontakt kao ciphertext + **blind index**, `dedupe_status` i `version`. Blind index je indeksiran ali **nije unique** — §3.4 kaže da isti email znači kandidata, nikad vezu, jer dve stvarne osobe dele porodičnu adresu; unique ograničenje bi odbilo drugu od njih. Kontakt osobe nije login ključ: `auth_identifier` ostaje ono kroz šta se prijava razrešava. `school_person_profile` je red koji globalnu osobu čini vidljivom unutar jednog tenanta, jedan po `(school_id, person_id)` bez obzira na broj tipova članstva; `local_person_code` se normalizuje NFKC + outer trim **bez casefold-a**, jer je M20 external reference ugovor case-sensitive i spajanje `AB-1` i `ab-1` bi bilo spajanje dva različita polaznika.
20. **M04 §2.8 — product entitlement** (migracija `c1f4a86d39b7`): jedan red po grantu, parcijalni unique po `(school_id, capability_key) WHERE status='ACTIVE'`. Ključna stvar je da `ACTIVE` **nije dovoljan**: efektivnost se odlučuje na čitanju (§3.8.2–3.8.3) — prozor važenja sa strogim `now < valid_until`, status škole, i da li je organizacija koja je prodala i dalje aktuelna. Čitalac koji veruje koloni `status` daje školi mogućnost koju je prestala da plaća u ponoć, a red i sutra ujutru izgleda ispravno. Zamena granta **terminalizuje** prethodni umesto da ga prepiše, jer je „koja komercijalna referenca je važila kada" jedino pitanje zbog kojeg ova tabela postoji. Bez backfill-a: §2.8 kaže da `CORE_MVP` ne nastaje iz Organization veze, a §9.5 zabranjuje izmišljanje granta.
21. **Composite tenant FK** (M03 §7, zatečeno kao nedostatak): `school_membership` dobija `UNIQUE(school_id, id, person_id)`, `role_assignment` dobija `UNIQUE(school_id, id, person_id, role_code)`. Nijedan ne dodaje garanciju jedinstvenosti — `id` je već PK — nego omogućavaju da strani ključ *imenuje tenanta* kao deo reference. Nominacija zato ne može pokazati na članstvo druge škole, a primary term ne može pokazati na MANAGER dodelu iste osobe. Oba su dokazana testom koji zaobilazi servis.

## 6. Šta NIJE urađeno

- Nijedan v5.7 QA scenario nije implementiran kao takav. Zatečeni testovi pokrivaju zatečeni proizvod; M04 anchor testovi gađaju invarijante iz ugovora, ali nisu numerisani QA scenariji iz `02-M04-QA-I-TRACEABILITY.md`.
- **Nijedan modul nije `IMPLEMENTED`.** Talas 1 jeste završen; od Talasa 2 postoje M04 §2.1–2.8 i M06 §2.1/§2.3–2.7. M04 sam po sebi nije gotov: §2.9–2.10 (usage snapshot i korekcije) su **blokirani** dok M09 ne dobije istoriju statusa upisa (F-15), a nedostaju i §2.12–2.20 (komercijalni sloj) i SCH-01..06 / ORG-01..04 / OWN-01..04 / ENT-01..02 kao stvarne komande sa permisijama i step-up-om. Ovde postoji **domen i njegove invarijante**, ne komandni sloj: ko sme šta da pozove i dalje čeka M05.
- Dead-letter dual control nema HTTP vezivanje dok M05 support access ne postoji (F-09).
- Talasi 3–5 nisu započeti.
- **Cypress se u ovom okruženju ne može pokrenuti** (binarni paket se ne preuzima), pa su korisničke putanje dokazivane pokretanjem stvarnog stack-a i pravim HTTP pozivima, odnosno Playwright-om uz predinstalirani Chromium. Web `typecheck` i `build` **se izvršavaju lokalno i prolaze** (raniji nalaz o suprotnom povučen — vidi F-11).

## 7. Predloženi sledeći korak

Redosled je potvrdio vlasnik proizvoda 2026-09-18:

1. ~~**F-03** — novac na `NUMERIC(18,2)`~~ — urađeno.
2. ~~**F-04** — preimenovanje `Organization` → `School`~~ — urađeno.
3. ~~M04 anchor (§2.1–2.5) i contact protection port~~ — urađeno.
4. ~~Owner nomination i primary term (§2.6–2.7)~~, ~~product entitlement (§2.8)~~ — urađeno. §2.9–2.10 su blokirani na M09 (F-15).
5. Odluka za vlasnika proizvoda: ili **M09 istorija statusa upisa** (otključava §2.9–2.10 i M04 zaokružuje), ili **nastavak Talasa 2** po DCR redosledu (M06 → M01 → M03 → M05 → M07 → M02), koji ionako donosi M05 permission registry bez kojeg M04 komande ne mogu da postoje. Komercijalni sloj (§2.12–2.20) je najveći deo i ide posle njih.
6. M02 i M05 su ujedno uslov da se F-09 i F-12 zatvore.

## 8. Odluke vlasnika proizvoda (2026-09-18)

Dve odluke odstupaju od onoga što bi implementacioni agent sam izabrao. Evidentiraju se ovde da kanon ne bi bio tiho promenjen, kako `DCR-20260903-07` §8 zahteva.

**O-01 — `Organization` se preimenuje u `School`.**
Agent je predložio da se postojeći `Organization` zadrži netaknut, a da v5.7 Organization kasnije uđe pod drugim imenom, jer `DCR-20260903-07` §3 izričito zabranjuje „preimenovanje funkcionalnog koda samo radi podudaranja sa nazivom iz dokumentacije". Vlasnik proizvoda je izabrao preimenovanje. **To je svesno odstupanje od DCR §3**, prihvaćeno radi jednoznačnosti imena pre nego što M04 uvede pravi Organization sloj. Obim: `organization_id` u 42 tabele, svaki guard, OpenAPI i web. Izvodi se kao zaseban PR sa backward-safe migracijom; poslovno ponašanje se ne menja.

**O-02 — F-03 se radi odmah, pre Talasa 2.**
Agent je predložio da migracija novca sačeka M12 u Talasu 3, po redosledu talasa iz DCR-a. Vlasnik proizvoda je izabrao da se uradi odmah, kao zaseban PR. Prihvaćeno; rizik je zabeležen: menja API i web istovremeno, a Cypress se ne može pokrenuti lokalno, pa E2E dokaz zavisi od CI-ja.
