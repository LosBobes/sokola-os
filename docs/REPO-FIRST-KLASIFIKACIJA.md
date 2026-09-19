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
| M01 Identity | `ADAPT` | §3.1–3.2, §4, §7, §9–13 i **sve AUTH komande** isporučene (migracije `a7e4c2f91b08`, `b8d3f60a51c7`, `c4a71e8b35d2`, `d7b25c48a139`). Bez HTTP rute ostaju AUTH-06/07 (§6: nisu self-service; čekaju §14 `UI-AUTH-04`) i AUTH-09/10/11 (čekaju M05 permission registry) — vidi F-21 |
| M02 Pozivnice | `ADAPT` | `identity/invite_tokens.py`, `Invitation` model, `tests/test_invitations.py`. Invite-only postoji; M02 ugovor je znatno širi (55 KB master) |
| M03 Multi-tenancy | `ADAPT` | §5.2, §5.3, §8 koraci 3–5 i TEN-01/02/04/05 isporučeni (`app/domains/tenancy/`, migracije `e5f83a19d24b`, `f8c21e64b0a7`, 36 testova). Guard sada poredi sve tri verzije i ponovo dokazuje M06 članstvo. §7.2–7.3 composite tenant FK-ovi isporučeni za sve 23 veze (migracije `a1d47f38e6c2`, `b2e59c14d7a3`, `c3f16a80d95e`, 100 testova) — F-26 otklonjen. **Ostaje:** kontekst se bira role assignment-om umesto škola+workspace (F-24, čeka M05), TEN-Q01/Q02 i chooser UI |
| M04 School/Subscription | `IMPLEMENT` (§2.1–2.8 urađeno) | Anchor: `organization`, `organization_school`, `school_locator`, `school_status_transition`, prošireni `school` (migracija `a4d76f2b91c0`, 30 testova). Ownership: `school_owner_nomination`, `school_primary_owner_term` sa composite tenant FK-ovima (`app/domains/school/ownership*.py`, migracija `b9e3c05a74d2`, 31 test). Entitlement: `school_product_entitlement` sa read-time pravilom efektivnosti (`app/domains/school/entitlements.py`, migracija `c1f4a86d39b7`, 23 testa). **Ostaje:** subscription usage (§2.9–2.10, blokirano — vidi F-15), komercijalni sloj (§2.12–2.20), SCH-01..06 / ORG-01..04 / OWN-01..04 / ENT-01..02 kao komande sa permisijama i step-up-om |
| M05 RBAC | `ADAPT` | `app/security/permissions.py` (169 linija) — per-area granted-areas model, restrikcija može samo sužavati. Nema `AuthorizationPolicyRevision`, `PermissionDefinition`, `RoleDefinition`/`RolePermissionBinding`, direct grantova, platform uloga, support ni break-glass pristupa. **Blokira:** TEN-Q01 (workspace opcije se izvode iz `RoleDefinition.workspace_key`), F-24 (izbor konteksta), delove M03/M07. **Prvi isečak:** registry kao referentni podatak, bez dodirivanja `RoleCode` — vidi F-29 |
| M06 Ljudi i članstva | `ADAPT` (§2.1, §2.3–2.7 urađeno) | `Person` §2.1, `school_person_profile` §2.4 (migracija `d2a95e13c7f4`), `school_membership` §2.3 sa MEM-01..05 (`people/membership.py`, migracija `e6b1d47a2c98`), `participant_profile`/`staff_profile`/`person_merge_history_entry` §2.5–2.7 (`people/activity_profiles.py`, migracija `f3c92d81ab45`). 60 testova ukupno. **Ostaje:** §2.2 sensitive identifier (blokiran — vidi F-16), PER/MRG komande i HTTP površina za MEM komande |
| M07 Roditelji/staratelji | `ADAPT` | `people.GuardianRelationship` (globalan) i `people.GuardianSchoolAccess` (tenant-scoped) — **2 od 7 entiteta** koje §2 traži, i oba u obliku koji F-31 menja. **Payer ne postoji odvojeno od staratelja** (F-32). Presuda za F-27: veza je tenant-scoped, podela nije namerna (F-31) |

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

### F-22 — provider step-up i AUTH-06/07 (OTKLONJENO)

- **Ugovor:** §6 AUTH-05 traži „aktivnu sesiju i **svežu ponovnu autentifikaciju** kada je provider podržava"; AUTH-06 i AUTH-07 traže je bezuslovno. §10 dodaje da step-up aktivira „samo provider ili eksplicitno odobrena konfiguracija, nikad ne aplikacioni improvizovani tok".
- **Rešenje (primenjeno, bez migracije — kolone `auth_time` i `assurance_context` postoje od `b8d3f60a51c7`):** `step_up_parameters` šalje Google-u `prompt=login` **i** `max_age`. Oba, jer padaju različito: `prompt=login` traži svežu autentifikaciju, a `max_age` čini rezultujući `auth_time` **tvrdnjom koju možemo proveriti** umesto obećanja kojem moramo verovati. Provajder koji ne poštuje nijedan vrati prestar `auth_time`, i poziv se odbija.
- **Svežina se meri od `auth_time` provajdera**, ne od izdavanja sesije ni od `last_seen_at`. Sesija održavana običnim radom bi inače izgledala sveže dokazana zauvek — a to je upravo svojstvo koje čini ostavljen otključan pregledač opasnim. Test to zakucava: sesija sa `auth_time` od pre dva sata i `last_seen_at` od maločas se odbija.
- **`ReauthenticationRequiredError` (403), a ne `UNAUTHENTICATED`:** sesija *jeste* validna, samo nije skorašnja. Klijent koji to razlikuje može da traži ponovnu prijavu umesto da čoveka izbaci — razlika između bezbednosnog prompta i gubljenja mesta u poslu.
- **AUTH-06 `LinkAuthIdentity`:** subject koji već pripada drugom nalogu je `IDENTITY_ALREADY_LINKED` i drugi nalog se **nikad ne imenuje** (§11) — „koji nalog ima ovu Google adresu" je tačno pitanje koje napadač želi odgovoreno. Ponovljeno linkovanje **istog** subject-a na **isti** nalog nije greška: prekinut tok mora da bude nastavljiv. Odlinkovan subject **nije slobodan** (§7): njegovo vraćanje je odluka kroz migracioni tok, ne nešto što sledeća prijava uradi tiho. Uspeh bumpuje verziju i opoziva sve druge sesije osim one koja je dokazala radnju.
- **AUTH-07 `UnlinkAuthIdentity`:** poslednji identitet je `LAST_IDENTITY_PROTECTED`. To nije uglađenost — ekran bezbednosti koji bi mogao da ukloni poslednji način prijave zaključao bi čoveka iz sopstvenog naloga jednim klikom, a ništa u M01 ne bi moglo da ga vrati. Red se **odlinkuje, ne briše** (§7). Ako je uklonjen baš identitet koji je dokazivao radnju, i acting sesija pada: zadržati je značilo bi zadržati sesiju iza koje ništa ne stoji.
- **Zašto nema HTTP ruta:** §6 izričito kaže da AUTH-06 „nije self-service MVP površina", a AUTH-07 pripada §14 `UI-AUTH-04` ekranu koji ne postoji — komanda koja može da zaključa čoveka treba da stigne sa ekranom koji to objašnjava.
- **Status:** `OTKLONJENO` — 30 testova, uključujući M01-QA-005 (subject na drugom nalogu) i M01-QA-006 (poslednji identitet).

### F-23 — §10 rate limiti (OTKLONJENO)

- **Ugovor:** M01 §6 AUTH-01 traži 5 startova po IP za 10 min i 10 po browser/device signalu za 24 h; §10 dodaje 20 callback neuspeha po IP za 10 min. Limiti su **keyed hash** IP/device signala, kratko se čuvaju po M17 i ne koriste se za profilisanje. Prekoračenje je `RATE_LIMITED` bez detalja (M01-QA-013).
- **Rešenje (primenjeno, migracija `d7b25c48a139`):** `rate_limit_counter` je fixed-window brojač u Postgresu — repo nema Redis, a limit koji postoji vredi više od glatkijeg koji ne postoji. Granica prozora je poštena slabost i zapisana je u migraciji: burst tempiran preko dva susedna prozora dobija do dvostrukog budžeta u kratkom roku. To je prihvatljivo jer ovi limiti tupe automatizovani obim; ono što stoji između napadača i naloga su provere credential-a.
- **Signal se ne čuva:** u red ide **keyed HMAC-SHA-256** adrese ili device id-a. Keyed, ne plain, jer se ceo IPv4 prostor heš-ira za nekoliko minuta — nekeyed digest adrese *jeste* adresa. Ključ se izvodi iz `session_secret` domenskom separacijom (`sokola/rate-limit/v1`), a ne kao nova deploy promenljiva: novi obavezni secret je novi način da deploy padne, a traženo svojstvo („ko ukrade ovu tabelu ne može da nabroji adrese") u potpunosti pokriva ključ koji je ionako obavezan u produkciji.
- **Device signal:** `sokola_device`, HttpOnly kolačić sa slučajnom vrednošću koju mi izdajemo. §6 AUTH-01 traži „browser/device signal", a ovo je poštena verzija toga — nešto što smo izdali i možemo zaboraviti, umesto fingerprint-a sastavljenog od svojstava pregledača. §10 zabranjuje profilisanje, a vrednost bez značenja van brojača se za to ne može upotrebiti.
- **Dva budžeta se ne dele:** iscrpljen per-IP budžet ne iscrpljuje per-device i obrnuto. Inače bi deljeni kancelarijski NAT zaključao celu zgradu čim jedan čovek promaši lozinku — zbog toga ugovor i imenuje dva signala.
- **Status:** `OTKLONJENO` — 18 testova, uključujući M01-QA-013 doslovno (šesti start u 10 min) i proveru da odbijanje ne otkriva ni adresu ni preostali broj.

### F-24 — aktivni kontekst bira **role assignment**, a ne škola + workspace

- **Ugovor:** M03 §3 i §6.4: jedna sesija ima **jednu aktivnu školu i jedan prikazni `workspace_key`**, pri čemu „`workspace_key` ne sužava i ne proširuje efektivna prava; M05 ih računa iz **svih** aktivnih dodela uloga/dozvola iste osobe u aktivnoj školi". §6.4 je eksplicitan: „ista osoba sa dve uloge u istoj školi dobija **jedan** tenant kontekst sa dve workspace opcije".
- **Repo dokaz:** `app/security/deps.py:30` → `CONTEXT_HEADER = "x-sokola-role-assignment-id"`, a `get_context` učitava **tačno jednu** `RoleAssignment` i iz nje izvodi `school_id`, `role_code`, `scope_type`, `scope_ref_id` i `granted_areas`. Kontekst *jeste* dodela uloge.
- **Posledica, i zašto je ovo više od imenovanja:** osoba koja je u istoj školi i TRAINER i ADMIN mora da **izabere jednu**, i time sebi **suzi prava** na tu dodelu. §6.4 traži suprotno — uniju. Trener koji je i administrator danas ne može da uradi radnju druge uloge dok ne promeni „kontekst", a taj izbor je klijentski header. To nije prikazni fokus; to je autorizaciona odluka koju pravi klijent.
- **Šta je u repou ipak ispravno:** server **ne veruje** headeru — ponovo izvodi školu i ulogu iz baze i proverava da dodela pripada prijavljenoj osobi (§1: „klijentski `school_id` ... samo su predlog, nikad autoritet"). Taj deo ugovora stoji i testiran je.
- **Minimalni predlog:** `SessionTenantContext` (§5.3) čuva `school_id` + `workspace_key`; `TenantExecutionContext` (§5.5) nosi školu, a M05 odvojeno računa uniju svih aktivnih dodela te osobe u toj školi. `granted_areas` prelazi iz „šta je izabrano" u „šta je unija dozvoljenog".
- **Status:** `CHALLENGE_NOT_APPLIED` — ovo je M03 ⟂ M05 promena. Union dozvola nema gde da se izračuna dok M05 permission registry ne postoji, a menjanje konteksta pre toga značilo bi zameniti jedan pogrešan model drugim.

### F-25 — `TenantSecurityState`, `SessionTenantContext` i §8 verzione provere (OTKLONJENO)

- **Ugovor:** M03 §5.2 traži `TenantSecurityState(school_id, tenant_access_version, ...)` — po jedan red za svaku školu; §5.3 traži `SessionTenantContext` sa `context_version`, `tenant_access_version_at_selection` i `authorization_version_at_selection`; §8 traži da svaki zaštićeni tok poredi sve tri verzije pre rada.
- **Repo dokaz:** `grep -rn "tenant_access_version\|SessionTenantContext\|workspace_key\|context_version" app/` vraća **nula pogodaka**. Kontekst se izvodi iz headera po zahtevu i nigde se ne pamti, pa nema šta da zastari — ali ni šta da se **obori**.
- **Posledica:** §8 korak 3 se ne može izvršiti. Deaktivacija škole danas deluje samo zato što `get_context` čita `School.status` na svakom zahtevu (što jeste fail-closed i jeste dobro), ali ne postoji mehanizam za „tenant-wide invalidaciju **odmah**" iz §5.2, ni zaštita od sporog odgovora iz škole A koji stigne posle prelaska na B (§10).
- **Minimalni predlog:** `tenant_security_state` sa `TEN-05 InitializeTenantSecurityState` iz M04 provisioninga, pa `auth_session`-vezan `session_tenant_context`. M01 `auth_session` već postoji (migracija `b8d3f60a51c7`) i ima `authorization_version_at_issue` — isti obrazac, sada za tenant.
- **Šta je isporučeno (migracija `e5f83a19d24b`):** `tenant_security_state` sa `tenant_access_version`, `TEN-05 InitializeTenantSecurityState` okačen na `record_creation` (svaka škola dobija stanje u **istoj transakciji** sa nastankom), i `TEN-04 InvalidateSchoolAccess` sa zaključavanjem reda, monotonim bump-om, zatvorenim reason registrom i `tenancy.school_access_invalidated` outbox događajem. Deaktivacija **i reaktivacija** škole bumpuju verziju u istoj transakciji sa M04 statusnom promenom (§5.2, §14) — povratak je jednaka bezbednosna granica kao odlazak, jer su konteksti građeni dok je škola bila ugašena građeni po drugim pravilima.
- **Outbox nije guard:** test briše događaj i pokazuje da verzija stoji. §14 traži da sledeći zahtev odbije autoritativno čitanje, i TEN-04 baš zato sme da kaže da „ne mora sinhrono update-ovati svaki session red".
- **Drugi deo (migracija `f8c21e64b0a7`):** `session_tenant_context` — najviše jedan red po M01 sesiji (`UNIQUE(session_id)`), sa **tri snapshot verzije** uzete pri izboru. §8 korak 3 svaku poredi sa živim autoritetom pre bilo kog zaštićenog rada: `context_version` (sopstveni brojač sesije, pa spor odgovor iz škole A ne može da se commit-uje posle prelaska na B, §10), `tenant_access_version_at_selection` (M03) i `authorization_version_at_selection` (M01).
- **Nijedna od tri ništa ne daje.** §5.3: „nije trajni allow dokaz". Mogu da učine kontekst **zastarelim**, nikad dovoljnim — zato se nesaglasan kontekst *invalidira* i zahtev odbija, a ne tiho osvežava.
- **Uz to, §8 korak 5:** request guard sada **ponovo dokazuje M06 `ACTIVE` članstvo**. Ranije je aktivna dodela uloge bila dovoljna, a §6.1 traži i jedno i drugo — `DRAFT`, `SUSPENDED` i `TERMINATED` članstvo ne daju redovan pristup kako god uloga glasila. To je bila stvarna rupa: dodelu uloge ukida admin ekran, a članstvo završava odlazak osobe, i to dvoje se ne radi uvek zajedno. Jedan postojeći test je to i dokazivao (dodeljivao ulogu bez članstva i prolazio); sada je ispravljen i dopunjen testom koji zakucava odbijanje.
- **Šta *nije* promenjeno:** kako se kontekst **bira**. To je F-24 i čeka M05 — sužavanje osobe na jednu njenu ulogu prestaje da bude autorizaciona odluka tek kad M05 može da izračuna uniju svih. `workspace_key` se za sada izvodi iz uloga i **samo upisuje**, nikad ne čita pri odlučivanju, pa ta privremena veza ne postaje autorizaciona putanja.
- **Status:** `OTKLONJENO` — §5.2, §5.3, §8 koraci 3–5, TEN-01, TEN-02, TEN-04, TEN-05. 36 testova.

### F-26 — samo 4 od 46 tenant tabela koristi composite tenant FK

- **Ugovor:** M03 §7.2–7.3: tenant parent izlaže `UNIQUE(school_id, id)`, a veza dva tenant entiteta koristi `(school_id, related_id) → (school_id, id)` composite FK „ili ekvivalent koji baza i integration test **dokazivo sprovode**".
- **Repo dokaz (prvo merenje, nad `Base.metadata`):** 61 tabela ukupno, 46 sa `school_id`, i **4** composite tenant FK ograničenja — `participant_profile`, `staff_profile` (oba `(school_id, school_membership_id, membership_type)`), `school_owner_nomination` i `school_primary_owner_term`. Sve starije veze koristile su običan FK na `id`.
- **Prebrojano tačno šta nedostaje (nad `pg_constraint`, ne nad modelima):** **23** jednokolonska FK veze između dve tenant tabele. Prva procena je govorila o „42 tabele", što je bilo merenje pogrešne stvari — tabela, a ne relacija. Planirani prvi korak (`school_membership`, `role_assignment`, `school_person_profile`) pokazao se kao promašaj: **nijedna** od 23 veze ne cilja te tri tabele. Stvarni klasteri su struktura, raspored i zapisi.
- **Posledica:** za te 23 veze cross-tenant referenca bila je sprečena **samo aplikacionim guardom**. To nije ništa — guard postoji i testiran je — ali §7.3 traži da to sprovodi baza, jer aplikacioni guard koji neko jednom zaboravi ne ostavlja trag.
- **Kako je urađeno — tri isečka, po klasteru, svaki sa sopstvenim PR-om i sopstvenim probama:**
  1. **Struktura (8 veza, migracija `a1d47f38e6c2`, PR #93):** `structure_program.category_id`, `structure_room.location_id`, `group.program_id`/`location_id`/`default_location_id`, `session.location_id`, `session_series.location_id`, `event.location_id`.
  2. **Raspored i spisak (7 veza, migracija `b2e59c14d7a3`, PR #94):** `session.group_id`/`series_id`, `session_series.group_id`, `group_membership.group_id`, `attendance_record.session_id`, `progress_note.group_id`/`session_id`.
  3. **Zapisi (8 veza, migracija `c3f16a80d95e`, PR #95):** `announcement_recipient.announcement_id`, `event_registration.event_id`, `charge.billing_run_id`, `payment_record.charge_id`, `import_row.batch_id`, `school_locator.replaced_by_locator_id` (samoreferentna), `school_primary_owner_term.source_nomination_id`, `outbox_dead_letter_review.message_id`.
- **`ON DELETE SET NULL (column)`:** obična forma bi pokušala da postavi `school_id` na NULL, a ta kolona je NOT NULL. Postgres 15+ prima listu kolona; repo vozi 16. SQLAlchemy to ne prima kroz `create_foreign_key`, pa te veze ulaze kao eksplicitan DDL.
- **Jedan izuzetak, namerno:** kod `outbox_dead_letter_review.message_id` composite FK je **dodat pored** jednokolonskog, a ne umesto njega. `school_id` je nullable na obe strane (outbox nosi i platformske poruke bez škole), a Postgres pri `MATCH SIMPLE` **uopšte ne proverava** composite FK kad je bilo koja kolona NULL — pa bi sam composite prestao da proverava baš te redove. To bi bilo slabije nego pre, ne jače. Oba ključa zato ostaju: jednokolonski i dalje garantuje da poruka postoji, composite dodatno odbija školski pregled tuđe poruke. Test pada ako neko kasnije „počisti" jednokolonski ključ.
- **Migracije odbijaju da se izvrše nad podacima koji već prelaze tenant** (§7.10): broje prekršioce po relaciji i prekidaju sa brojevima, umesto da bilo šta poprave. Cross-tenant referenca je incident koji operater treba da vidi, a ne da mu bude tiho ispravljen.
- **Testovi zaobilaze servisni sloj** — tamo je stara provera i živela; dokazuje se da **baza** odbija. Jedan test čita ograničenje iz `pg_constraint`, jer bihevioralni test sam ne razlikuje composite ključ od jednokolonskog koji je zamenio: oba odbijaju nepoznat `id`. Poslednji test tvrdi da **nijedna** jednokolonska FK veza između dve tenant tabele više ne postoji, sa tim jednim imenovanim izuzetkom — pa sledeća takva veza ne može da se doda tiho.
- **Status:** `OTKLONJENO` — mereno nad `pg_constraint` posle sva tri isečka: **27** composite tenant FK ograničenja (4 zatečena + 23 nova), **1** preostala jednokolonska veza, i to ona dokumentovana outbox. 48 tenant tabela. 100 testova.

### F-27 — tri globalne tabele nose tenant odluke

- **Ugovor:** M03 §4.4–4.5: globalni su samo `Person`, `UserAccount`, `AuthIdentity` i `Organization`. `SchoolMembership`, `SchoolPersonProfile`, `RoleAssignment`, **`GuardianChildLink`** i svi operativni Core zapisi su tenant-scoped. §7.5 dodaje da globalne tabele „ne dobijaju lažni `school_id`" — ali onda tenant pripadnost mora da dokaže **zaseban membership/relationship guard**.
- **Repo dokaz:** tri tabele nemaju `school_id` a nose odluku koja pripada školi:
  - `guardian_relationship` (`guardian_person_id`, `child_person_id`, `relationship_type`) — §4.5 izričito imenuje `GuardianChildLink` kao tenant-scoped. Repo **ima** i tenant-scoped `guardian_school_access`, pa je moguće da je podela namerna (globalna činjenica „ko je čije dete" + školski pristup), ali ugovor to ne kaže tako.
  - `student_login_authorization` (`student_person_id`, `login_enabled`, `authorized_by_person_id`) — „sme li ovo dete da se prijavljuje" je odluka **jedne** škole, a red je globalan. Škola A je danas donosi za dete koje je i u školi B.
  - `workspace` (`id`, `name`, `owner_person_id`) — **provereno mrtva tabela**: sopstveni docstring kaže „Reserved commercial/ownership container... present so the model is future-shaped, not future-built"; nema nijedan ulazni strani ključ, nijedan pogodak u `app/`, `tests/`, `scripts/` ni u `apps/web/src`. Uz to je **prevaziđena** — M04 `organization` i `school_product_entitlement` (migracije `a4d76f2b91c0`, `c1f4a86d39b7`) zauzimaju tačno ulogu koju je rezervisala. Ime se pritom sudara sa M03 §3 `workspace_key`, koji je **prikazni fokus bez tabele**: dva različita pojma pod istim imenom.
- **Posledica:** `student_login_authorization` je stvarna cross-tenant odluka i najoštriji od tri — škola A je danas donosi za dete koje je i u školi B. `guardian_relationship` traži M07 presudu, jer repo **ima** tenant-scoped `guardian_school_access` pa je podela možda namerna. `workspace` nije rizik, nego šum koji će sledeći čitalac pomešati sa `workspace_key`.
- **Status:** `DELIMIČNO OTKLONJENO` — dve od tri rešene.
  - `workspace` je **obrisan** (migracija `e5f83a19d24b`; dokazano bez čitalaca, pa `DROP TABLE`, ne migracija podataka).
  - `student_login_authorization` je **tenant-scoped** (migracija `d4b83c17e5f9`): dodat `school_id NOT NULL` sa `ON DELETE CASCADE`, a globalni `UNIQUE(student_person_id)` zamenjen sa `UNIQUE(school_id, student_person_id)`. Dete ostaje globalno — §7.5 zabranjuje lažni `school_id` na globalnoj tabeli; tenant-scoped je **odluka**, ne osoba. Migracija **odbija da se izvrši ako tabela ima ijedan red**: globalni red ne kaže koja ga je škola donela, a §7.10 zabranjuje da se dodeli prvoj ili jedinoj školi. U ovom repou je tabela dokazano neispisana (nema servis, router, test ni web referencu, niti ijedan ulazni strani ključ), pa guard ne bi trebalo da opali — postoji jer „ne bi trebalo" nije „ne može", a deployment koji *ima* redove traži operatera, ne pogađanje. Downgrade isto odbija ako ijedno dete drži odluku u više od jedne škole, jer globalni ključ ne može da primi obe. 6 testova.
  - `guardian_relationship` **više ne čeka presudu** — M07 ju je dao, vidi F-31. Podela („ko je čije dete" globalno + školski pristup) **nije** namerna: M07 §2.3 čini samu vezu tenant-scoped, jer je to školska provera, ne globalna činjenica. Ostaje implementacija, ne odluka.

### F-28 — `SETUP_ONLY` ima ispravan ugovor, ali nema površinu

- **Ugovor:** M03 §6.2: `School.status=IN_PREPARATION` daje samo `SETUP_ONLY` kontekst ovlašćenom prvom vlasniku, i taj kontekst otvara „samo O01–O07 i eksplicitne M20/M04 setup komande".
- **Repo dokaz:** posle TEN-Q02 (`app/application/tenant_context.py`) `school_mode` se računa ispravno i `allowed_start_route` za `SETUP_ONLY` imenuje setup površinu. Ta ruta **ne postoji** u `apps/web/src/App.tsx` — tamo su `/`, `/ljudi`, `/grupe`, `/raspored`, `/finansije`, `/komunikacija`, `/dokumenti`, `/dogadjaji`, `/roditelj/finansije`, `/obavestenja`, `/vise`, `/izvestaji` i ništa za onboarding.
- **Posledica:** škola u pripremi se razrešava u rutu koju web app ne ume da prikaže. **Ovo nije regresija** — pre TEN-Q02 je isti akter dobijao *redovan* kontekst, što je bilo gore (§6.2 to izričito zabranjuje). Ali onboarding i dalje nema ekran.
- **Zašto nije urađeno ovde:** setup površina je M20/M04 §14 posao, ne M03. Slati `SETUP_ONLY` aktera na redovan home bilo bi tačno ono što §6.2 zabranjuje, pa ugovor kaže istinu i kad UI zaostaje.
- **Status:** `CHALLENGE_NOT_APPLIED` — zabeleženo kao poznat jaz sa imenovanim vlasnikom (M20/M04 §14).

### F-29 — M05 kanonski role ključevi se ne poklapaju sa repo ulogama, i jedno preslikavanje **oduzima prava**

- **Ugovor:** M05 §2.4 daje kanonske school role ključeve: `OWNER`, `MANAGER`, `LIMITED_ADMIN`, `INSTRUCTOR`, `SUBSTITUTE_INSTRUCTOR`, `GUARDIAN`, `PAYER`. Izričito kaže i da se legacy `TRAINER` deterministički migrira u `INSTRUCTOR`, a `SUBSTITUTE_TRAINER` u `SUBSTITUTE_INSTRUCTOR`, bez paralelnog aktivnog para.
- **Repo dokaz (`app/domains/identity/enums.py:33`):** `RoleCode` ima `OWNER`, `MANAGER`, `ADMIN`, `TRAINER`, `PARENT`, `STUDENT`.
- **Preslikavanje koje je jasno:**
  - `OWNER` → `OWNER`, `MANAGER` → `MANAGER` — isto.
  - `TRAINER` → `INSTRUCTOR` — ugovor to imenuje.
  - `PARENT` → `GUARDIAN` — jedina uloga sa istim značenjem.
- **Preslikavanje koje NIJE jasno, i zato nije primenjeno:**
  - **`ADMIN` → `LIMITED_ADMIN` oduzima prava.** U repou `ROLE_DEFAULT_AREAS` daje `ADMIN` **ceo** `_STAFF_AREAS` skup — identično kao `OWNER` i `MANAGER` (`app/security/permissions.py:100`). M05 §2.4 opisuje `LIMITED_ADMIN` kao „Administrator **bez implicitnih poslovnih prava**; konkretna prava preko eksplicitnih grantova". Mehaničko preslikavanje bi svakom postojećem administratoru u produkciji oduzelo pristup ljudima, grupama, rasporedu, finansijama, događajima, komunikaciji i dokumentima — u jednom deploy-u, bez ijednog grant-a koji bi to nadoknadio.
  - **`STUDENT` nema kanonski parnjak.** M05 ne poznaje učeničku ulogu. U repou `STUDENT` već ima prazan skup oblasti, pa ne nosi prava — ali i dalje postoji kao dodeljiva uloga i ima redove.
  - `SUBSTITUTE_INSTRUCTOR` i `PAYER` nemaju repo parnjaka; oni su nov posao, ne migracija.
- **Posledica:** M05 registry se može uvesti kao referentni podatak bez dodirivanja `RoleCode`, i to je ono što treba prvo. Sama migracija uloga je odvojena odluka sa produkcijskom posledicom, i traži ili (a) da `ADMIN` postane `MANAGER` umesto `LIMITED_ADMIN`, ili (b) da se svakom postojećem `ADMIN`-u u istoj migraciji izda eksplicitan grant set koji čuva današnji pristup, ili (c) svestan pristanak da administratori izgube prava. §7.10 zabranjuje da migracija sama pogađa u ovakvom slučaju.
- **Šta F-29 *ne* blokira (provereno nad zasejanom revizijom 1.3):** workspace izbor. §2.4 mapira `OWNER`, `MANAGER` **i** `LIMITED_ADMIN` na isti `ADMIN` workspace — pa kako god se `ADMIN` razreši, njegov workspace je `ADMIN` u oba slučaja. Preslikavanje repo uloge → workspace je zato potpuno određeno za pet od šest uloga:

  | repo uloga | workspace | osnov |
  |---|---|---|
  | `OWNER` | `ADMIN` | isti ključ |
  | `MANAGER` | `ADMIN` | isti ključ |
  | `ADMIN` | `ADMIN` | **obe kandidat-opcije (MANAGER, LIMITED_ADMIN) daju isti workspace** |
  | `TRAINER` | `INSTRUCTOR` | §2.4 imenuje migraciju |
  | `PARENT` | `GUARDIAN` | jedina uloga istog značenja |
  | `STUDENT` | — | nema kanonskog parnjaka; ionako danas nosi prazan skup oblasti |

  **Posledica: TEN-Q01 nije blokiran.** Blokirani su efektivni permission-i, ne izbor škole i workspace-a.
- **Status:** `CHALLENGE_NOT_APPLIED` — preslikavanje uloga nije primenjeno. Traži odluku vlasnika proizvoda (vidi §8), jer sve tri opcije menjaju nečiji pristup.

### F-30 — M05 registry revizije 1.3 nije u §3.3; 39 redova nosi nedefinisanu grupu uloga

- **Ugovor:** M05 §3.3 daje tabelu permission ključeva. Dva dokumenta u istoj fascikli — `03-M05-PERMISSION-REGISTRY-M17-M21-M28.md` i `04-M05-PERMISSION-REGISTRY-M06-M07.md` — svaki se otvara rečenicom da su „normativni nastavak M05 §3.3". Dakle registry revizije 1.3 su sva tri dokumenta zajedno, ne samo §3.3.
- **Repo dokaz (prebrojano nad spec fajlovima):** §3.3 ima **38** ključeva, fajl 04 ima **16**, fajl 03 ima **59** — ukupno **113**. Prvi isečak (PR #100) je zasejao samo §3.3, pa pet uloga (`LIMITED_ADMIN`, `INSTRUCTOR`, `SUBSTITUTE_INSTRUCTOR`, `GUARDIAN`, `PAYER`) nema **nijedan** binding: njihova prava su tačno ono što živi u ta dva nastavka.
- **Stvarna prepreka:** oba nastavka koriste više oblika tabele, a dva zaglavlja imenuju grupu uloga koju **nijedan dokument ne definiše**:

  | fajl | kolona za ulogu | redova | jednoznačno? |
  |---|---|---:|---|
  | 03 | `Default binding` | 18 | da (isti oblik kao §3.3) |
  | 03 | `INSTRUCTOR/SUBSTITUTE` | 10 | da (kosa crta = dve uloge, po napomeni u istom fajlu) |
  | 03 | `STAFF` | 25 | **ne** |
  | 03 | `Ostale role` | 6 | **ne** |
  | 04 | `INSTRUCTOR/SUBSTITUTE` | 8 | da |
  | 04 | `STAFF` | 8 | **ne** |

  `STAFF` bi moglo da znači `INSTRUCTOR` + `SUBSTITUTE_INSTRUCTOR` (jer `LIMITED_ADMIN`, `GUARDIAN` i `PAYER` imaju sopstvene kolone u istoj tabeli), ali to je zaključivanje, ne ugovor. `Ostale role` se ne da pogoditi uopšte.
- **Posledica:** **74 od 113** ključeva se mogu zasejati direktno iz ugovora (38 iz §3.3 + 36 iz nastavaka). Preostalih **39** traži presudu vlasnika ugovora — pogađanje bi upisalo binding koji niko nije odobrio, u tabelu koja je autoritet za autorizaciju. `STAFF` pogađa i M07 (staratelji i platioci), ne samo M17–M28.
- **Ispravka ranijeg stava (dva puta):**
  1. Prvo sam zapisao da revizija 1.3 ne sme da se objavi dok nije potpuna. Tačniji stav je: ne sme da se objavi **nepotpuna iz nepažnje**. Pošto 39 redova *nije određeno ugovorom*, revizija 1.3 se objavljuje sa 74 ključa i zapisanim jazom; §2.2 ionako predviđa da dopune stižu kao nova revizija. Držati ceo registry (a sa njim TEN-Q01 i resolver) taocem nejasnih redova bilo bi gore od zapisanog jaza.
  2. Zatim sam u prvoj verziji ovog nalaza napisao **82 zasejiva / 31 nejasan**. To je bilo pogrešno: gledao sam samo fajl 03 kad sam tražio nedefinisana zaglavlja, a `STAFF` se pojavljuje i u fajlu 04. Tačno je **74 / 39**.
- **Još dva nedostajuća obavezna polja (nađeno pri pisanju seed generatora):** §2.3 traži `delegation_class` i `child_data_class` kao **obavezna** polja svakog `PermissionDefinition`-a. Nastavci ih uglavnom ne daju:
  - `delegation_class` je naveden u prozi za **12 od 36** odredivih redova; za preostala 24 ga nema.
  - `child_data_class` se **ne pominje nijednom** ni u jednom od dva nastavka.
- **Zašto to nije „stavi default":**
  - Za `delegation_class` fail-closed default **jeste** branjiv: `ROLE_ONLY` znači da se pravo ne može delegirati direct grantom. Kasnija revizija ga može olabaviti; nikad se ne širi tiho. To je preporuka.
  - Za `child_data_class` default **nije** bezbedan. §2.3 formalno daje `NONE`, ali `school.people.basic.view` i `school.participant.safety.view` očigledno dodiruju podatke dece, a `NONE` bi slagao svakoj masking/retention logici koja to polje čita. Suprotno — sve proglasiti `SPECIAL_CATEGORY` — učinilo bi polje beskorisnim. Ovo polje postoji baš da bi maskiranje znalo šta drži, pa pogrešna vrednost nije konzervativna, nego netačna.
- **Ukupno stanje odredivosti nastavaka:** 36 redova ima jasne role binding-e, ali čak i za njih 24 nema `delegation_class`, a svih 36 nema `child_data_class`. Registry nastavaka je, dakle, bitno nedodefinisan — ne samo u dve kolone uloga.
- **Status:** `CHALLENGE_NOT_APPLIED` za 39 redova (nedefinisana grupa uloga) i dodatno za `delegation_class`/`child_data_class`. Traži se: definicija `STAFF` i `Ostale role`; potvrda da je `ROLE_ONLY` ispravan fail-closed default za nenavedeni `delegation_class`; i `child_data_class` po ključu (ili pravilo po kome se izvodi). Do tada ti ključevi nisu u nijednoj reviziji i zato su fail-closed deny, što je ispravno ponašanje.

### F-31 — M07 presuda za `guardian_relationship`: podela nije namerna, ugovor traži tenant-scoped vezu

- **Ugovor:** M07 §2.3 `GuardianChildLink` ima `school_id` kao **obavezno** polje, tenant-safe triple FK-ove ka oba članstva, status lifecycle (`PENDING_VERIFICATION`/`ACTIVE`/`REJECTED`/`REVOKED`), `decision_by_account_id`, `decision_reason_code` i `version`. §2.0 dodaje da „svi tenant entiteti imaju `school_id` i `UNIQUE(school_id,id)`". §1.1 kaže da M07 „vodi **dokazanu** vezu odrasla osoba–dete" i da „trenutno opoziva pristup kada se veza opozove".
- **Repo dokaz (`app/domains/people/models.py:12`):**
  - `guardian_relationship` je globalan: `guardian_person_id`, `child_person_id`, `relationship_type`, i `UNIQUE(guardian_person_id, child_person_id)`. Nema `school_id`, nema statusa, nema provere, nema ko je i kada odlučio.
  - `guardian_school_access` je tenant-scoped pristupni red sa `is_primary_contact`.
- **Presuda (ovo je bilo otvoreno pitanje u F-27):** podela „globalna činjenica + školski pristup" **nije** ono što ugovor traži. §2.3 čini **samu vezu** tenant-scoped, jer „da li je ova odrasla osoba staratelj ovog deteta **u ovoj školi**" je školska *provera*, ne globalna činjenica. Dve škole mogu doći do različitog zaključka o istom paru, i H0 §1.2 izričito kaže da roditelj ne sme sam aktivirati drugog staratelja — što globalni red bez statusa i odlučioca ne može da izrazi.
- **Posledica:** `GuardianChildLink` zamenjuje **oba** postojeća reda, ne dopunjuje ih. Globalni `UNIQUE(guardian_person_id, child_person_id)` je konkretno pogrešan: on tvrdi da par odrasla osoba–dete ima jedan odnos u celoj platformi, pa škola B ne može da zabeleži svoju proveru ako je škola A već zabeležila svoju.
- **Zašto nije urađeno ovde:** to je M07 isečak sa sopstvenom migracijom i sopstvenim testovima, a ne usputna izmena u repo-first prolazu. Migracija mora i da odluči šta sa postojećim globalnim redovima — §7.10 zabranjuje da ih sama pridruži prvoj ili jedinoj školi, pa i tu važi „prijavi, ne pogađaj".
- **Koliko je to posla (prebrojano):** `GuardianRelationship` ima **42**, a `GuardianSchoolAccess` **65** referenci izvan svog model fajla — ukupno 107, raspoređenih po `identity/service.py`, `identity/repository.py`, `parent/router.py`, `communications/outbox.py` i `events/repository.py`. Zamena nije jedna migracija nego **postupna**: `GuardianChildLink` se uvodi pored postojećih redova, čitaoci se prebacuju domen po domen, i tek kad nijedan ne gleda stare tabele one se uklanjaju. Isti obrazac koji je M01 koristio za sesije, i iz istog razloga — 107 poziva prepisanih u jednom commit-u nije promena koju iko može da pregleda.
- **Status:** `CHALLENGE_NOT_APPLIED`, ali **pitanje iz F-27 je razrešeno**: veza je tenant-scoped, podela nije namerna. F-27 time više ne čeka presudu, nego implementaciju.
- **Ispravka (F-33, F-34):** brojka 107 i spisak domena iz prethodnog pasusa su pogrešni. Tačno prebrojavanje je u F-33, a F-34 povlači tvrdnju da svaki čitalac mora da odluči „koja škola" — to važi samo za globalni `guardian_relationship`, ne i za `guardian_school_access`.

### F-32 — M07 je uglavnom neizgrađen; postoje dva reda od sedam entiteta

- **Ugovor:** M07 §2 traži `Family`, `FamilyMembership`, `GuardianChildLink`, `RelationshipVerificationRecord`, `PayerChildLink`, `PrimaryGuardianContactDesignation`, `PrimaryPayerDesignation`.
- **Repo dokaz:** postoje `guardian_relationship` i `guardian_school_access` (oba u `domains/people/`), plus `domains/parent/router.py`. Nijedan `Family`, `PayerChildLink` ni `PrimaryGuardian*` ne postoji nigde u `app/`.
- **Najoštriji jaz:** **payer ne postoji odvojeno od staratelja.** §2.5 `PayerChildLink` i §1.1 („više aktivnih payer veza koje aktivni M12 koristi za capability-gated model podeljene odgovornosti") traže finansijsku vezu koja **ne** daje guardian prava. M05 §3.2 tačka 9 to ponavlja: `PAYER` ima samo finance binding-e sa `subject_basis_kind=PAYER_CHILD_LINK`, i taj basis „nikad ne daje attendance/document/health/profile/guardian pravo". Danas u repou ne postoji način da se neko označi kao platilac a da ne bude staratelj.
- **Status:** `CHALLENGE_NOT_APPLIED` — zabeleženo kao poznat obim: 2 od 7 entiteta, i to oba u obliku koji F-31 menja.


### F-33 — ispravka: 85 referenci, ne 107, i spisak domena iz F-31 je bio nepotpun

- **Kako je prebrojano:** `grep -rn "GuardianRelationship\|GuardianSchoolAccess" app/ --include=*.py`, pa grupisano po domenu.
- **Stvarno stanje (2026-09-19, posle M07 šeme):** **85** linija sa referencom, raspoređeno: `people` **39**, `identity` 15, `parent` 6, `events` 6, `documents` 6, `billing` 6, `communications` 5, `family` 2.
- **Šta je F-31 propustio:** `people` (ubedljivo najveći čitalac), `documents` i `billing` se u F-31 ne pominju uopšte. Propust `documents`-a je onaj koji nosi težinu — to je domen sa podacima o detetu, pa bi migracija koja ga previdi ostavila najosetljiviji čitalac na staroj tabeli.
- **Od 85 referenci, samo 10 su stvarni upiti** (`select`/`join`/`where` izvan `models.py`/`enums.py`/`schemas.py`): `people/repository.py` 4, `identity/repository.py` 2, i po jedan u `people/service.py`, `documents/repository.py`, `communications/outbox.py`, `billing/repository.py`. Ostalo su import-i, anotacije i relationship deklaracije. Posao je znatno manji nego što „107 poziva" sugeriše — ali je raspoređen na više domena nego što je F-31 rekao.
- **Status:** `INFO` — ispravka objavljene brojke i spiska. Ne menja presudu iz F-31, menja plan migracije.

### F-34 — „koja škola?" je problem samo za `guardian_relationship`, ne za `guardian_school_access`

- **Šta je F-31 tvrdio:** da migracija mora da odluči šta sa postojećim redovima jer stara tabela nema `school_id`, i da §7.10 zabranjuje pogađanje.
- **Repo dokaz:** to važi za `guardian_relationship`. Ali **svi čitaoci koji stvarno rade autorizacione upite gledaju `guardian_school_access`**, koji `school_id` ima i filtrira po njemu u svakom `where`. Primeri: `billing/repository.py::is_guardian_of(db, school_id, guardian, child)`, `documents/repository.py::guardian_child_ids(db, school_id, guardian)`, `communications/outbox.py::_guardians_of(db, school_id, child_ids)`.
- **Posledica:** preslikavanje `guardian_school_access` → `guardian_child_link` je **jednoznačno**; §7.10 ga ne blokira. Nejednoznačan je samo globalni `guardian_relationship`, a on nema nijednog autorizacionog čitaoca — koristi se za prikaz odnosa, ne za odluku o pristupu.
- **Status:** `INFO` — povlači deo F-31 koji je migraciju prikazao težom nego što jeste.

### F-35 — čitaoci se ne smeju prebaciti pre backfill-a; `guardian_child_link` je prazan

- **Nalaz:** `guardian_child_link` nema nijedan red i ništa ga ne puni osim M07 komandi, koje niko još ne poziva. Prebacivanje bilo kog čitaoca na njega **danas** znači da `is_guardian_of` vraća `False` za svakog postojećeg staratelja — tiho uskraćivanje pristupa celoj populaciji roditelja, bez ijedne greške u logu.
- **Zato redosled iz F-31 nije ispravan.** Prvo backfill, pa čitaoci. Suprotan redosled nije „postupna migracija" nego prekid usluge u ratama.
- **Ugovor to predviđa:** §2.4 `verification_method` ima vrednost **`MIGRATION_VERIFIED`**, koja postoji upravo zato da se veza prenesena iz ranijeg stanja može zabeležiti kao takva, a ne kao provera koju je neko obavio. Backfill dakle nije zaobilaženje §3.5 (aktivacija + dokaz atomarno) nego njegov predviđeni oblik.
- **Šta backfill mora da reši, a ugovor ne rešava:** `GuardianChildLink` traži `requested_by_account_id` i, za `ACTIVE`, `decision_by_account_id`. Za redove prenete iz `guardian_school_access` ne postoji nalog koji je odlučio — odluka je prethodila ovom modelu. To je **odluka za vlasnika proizvoda**: koji akter se upisuje (sistemski migracioni identitet vs. vlasnik škole), pošto §5.3 traži da odlučilac bude stvaran nalog. Ne izmišlja se ovde.
- **Dodatno:** portovi iz §7.2 traže **ACTIVE** M06 članstvo sa obe strane (§12, M03 §6.1), što stara tabela nije proveravala. Svaki prebačeni čitalac zato može početi da odbija slučajeve koje je ranije propuštao — namerno, ali mora biti prijavljeno po domenu, ne otkriveno u produkciji.
- **Status:** `CHALLENGE_NOT_APPLIED` — backfill je zaseban, operatorski vođen isečak; čeka odluku o akteru.

### F-36 — `TENANT_RESOURCE_NOT_FOUND_SAFE` kao poseban kod **ruši** nerazlučivost koju ista rečenica traži

- **Šta ugovor traži:** M03-QA-013 kaže „404 `TENANT_RESOURCE_NOT_FOUND_SAFE`, **istog oblika kao nepostojeći ID**". Dve polovine, i one se međusobno isključuju ako se prva čita kao „poseban kod za cross-tenant slučaj".
- **Zašto:** ako tuđi resurs vrati `TENANT_RESOURCE_NOT_FOUND_SAFE`, a izmišljeni ID `NOT_FOUND`, onda klijent koji pogađa ID-eve može da ih razvrsta na „postoji u nekoj drugoj školi" i „ne postoji" — a to je tačno potvrda koju §8 postoji da uskrati. Poseban kod je oracle.
- **Repo dokaz:** `TenantResourceNotFoundError` je **definisan u `app/common/errors.py:275` i nigde se ne koristi**. Svi tenant-scoped čitaoci dižu obični `NotFoundError`, pa su oba slučaja bajt-identična — što je proverено u `test_m03_qa_013_another_tenants_id_is_indistinguishable_from_no_id` poređenjem celog tela odgovora, ne statusa.
- **Posledica:** bezbednosna osobina iz druge polovine rečenice **važi**; ime koda iz prve **ne postoji na žici**. Ako se ime ikada uvede, mora da zameni `NOT_FOUND` na *svim* tenant-scoped putanjama, uključujući i nepostojeći ID — nikad samo na cross-tenant grani.
- **Status:** `CHALLENGE_NOT_APPLIED` — ne odlučuje se ovde; test tvrdi osobinu, ne ime.

### F-37 — aplikacija se povezuje na bazu kao **Postgres superuser**

- **Nalaz:** `compose.prod.yml:31`, `compose.m0.yml:7` i `.github/workflows/ci.yml:25` svi prave bazu preko `POSTGRES_USER: sokola`, što je uloga koju Postgres image pravi kao **vlasnika klastera**, dakle superuser. Aplikacija se tom istom ulogom i povezuje (`SOKOLA_DATABASE_URL`).
- **Merenje, ne pretpostavka:** `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user` vraća `rolsuper = true`.
- **Neposredna posledica za M03:** superuser zaobilazi **svaku** RLS politiku bez obzira na `rolbypassrls`. Prva row-level politika koju bilo ko napiše bila bi mrtva na dolasku, a ništa ne bi otkazalo — izolacija bi izgledala pooštrena, a ne bi bila. Danas to nikoga ne ugrožava jer repo RLS ne koristi (`relrowsecurity` je prazan skup), pa je M03-QA-050 vakuozan sa te strane.
- **Šira posledica:** aplikaciona konekcija može da `DROP`-uje tabele, da menja constraint-e i da čita `pg_authid`. Ceo tenant model u §7.2 počiva na constraint-ima koje ta ista konekcija sme da ukloni.
- **Šta bi bilo ispravno:** zasebna, ne-superuser aplikaciona uloga sa `GRANT`-ovima na `public`, dok migracije idu vlasničkom ulogom. To je izmena deploy-a (compose, CI, ops/hetzner), ne test-a, pa **nije rađena u ovom isečku**.
- **Test koji ovo čuva:** `test_m03_qa_050_no_row_level_security_is_relied_on_or_silently_bypassed` tvrdi konjunkciju — *ili* nijedna tabela ne koristi RLS, *ili* uloga ne može da je zaobiđe. Danas prolazi zbog leve strane; pada onog dana kad neko doda politiku pre nego što je uloga razdvojena.
- **Status:** `ODLUKA ZA OPERATORA`.

### F-38 — M03 write komande postoje kao servisne funkcije, bez §12 command omotača

- **Nalaz:** TEN-01 (`select_context`) i TEN-02 (`clear_context`) nemaju HTTP rutu. Ceo `app/domains/tenancy/` nema router; jedini M03 endpoint je `GET /tenant/context` (TEN-Q02) u `app/application/tenant_router.py`. Jedini pozivalac `select_context` je `app/security/deps.py:136`, koji bira kontekst kao *sporednu posledicu* role-assignment header-a (to je F-24).
- **Tri stvari koje zbog toga ne postoje:**
  1. **idempotencija** — nema `request_id`, nema idempotency store ispred TEN-01, pa M03-QA-010 (retry istim ID-em) i M03-QA-011 (`TENANT_IDEMPOTENCY_KEY_REUSED`, kod koji nijedan modul ne definiše) nemaju šta da provere;
  2. **audit/outbox na switch-u** — `select_context` ne `enqueue`-uje ništa i ne piše audit red, pa M03-QA-008 ima tačnu verziju konteksta i nikakav trag;
  3. **idempotencija TEN-04** — `tenant_security.invalidate` ne prima `request_id` i **nije** idempotentan: dva poziva dižu `tenant_access_version` dvaput, što je suprotno od M03-QA-051.
- **Zašto je ovo jedan nalaz, a ne tri:** sve tri rupe imaju isti koren — M03-ove write operacije su napisane kao funkcije koje pozivalac orkestrira, a §12 ih opisuje kao komande sa kovertom (request ID, receipt, audit, event). Popravka je ista koverta na sva tri mesta.
- **Status:** `NALAZ` — četiri M03 QA scenarija (008, 010, 011, 051) blokirana su na njega.

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
