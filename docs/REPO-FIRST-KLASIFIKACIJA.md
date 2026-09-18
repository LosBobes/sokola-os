---
tip: repo-first-klasifikacija
status: TALAS-0-ZAVRSEN
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

## 2. Terminološko mapiranje (bez preimenovanja koda)

`DCR-20260903-07` §3 izričito zabranjuje preimenovanje funkcionalnog koda samo radi
podudaranja sa dokumentacijom. Zato se koristi mapa, ne rename:

| v5.7 pojam | Zatečeni kod | Status |
|---|---|---|
| School (H0 security tenant) | `Organization` / `organization_id` | `ADAPT` — semantički isto (tenant granica), ali ime se sudara sa v5.7 `Organization` |
| Organization (negrupišući, **ne** authorization domen) | ne postoji | `IMPLEMENT` (M04) |
| Person | `identity.Person` | `PRESERVE` |
| UserAccount | `identity.AuthAccount` + `AuthIdentifier` | `PRESERVE` |
| School membership | `organization.OrganizationMembership` | `PRESERVE` |
| Guardian relation | `people.GuardianRelationship` | `PRESERVE` |
| Payer relation | ne postoji kao zaseban autoritet | `IMPLEMENT` (M07/M12) |

⚠️ **Sudar imena.** U repou `Organization` *jeste* tenant; u v5.7 `Organization` je izričito
**ne**-authorization domen iznad School-a. Dok M04 ne uvede pravi Organization sloj, svako
čitanje koda mora znati da `organization_id` znači *School*. Predlog: uvesti v5.7
`Organization` pod drugim imenom u kodu (npr. `OrganizationGroup`) da se sudar nikad ne
materijalizuje. Odluka pripada vlasniku proizvoda — vidi F-04.

## 3. Klasifikacija po modulima

### Zajednički portovi (M00/M21 Talas 1)

| Oblast | Klasifikacija | Putanja / dokaz |
|---|---|---|
| Transakcija (jedan lokalni commit) | `PRESERVE` | `app/db.py`, session-per-request |
| Audit | `ADAPT` | `app/platform/audit/` postoji; M21 immutable seal + append-only verifikacija ne postoje |
| Outbox/inbox | `ADAPT` | `app/platform/outbox/` postoji (transakcioni, poll worker); inbox/dead-letter dual control ne postoji |
| Idempotency receipt | `ADAPT` | `app/platform/idempotency/` postoji; canonical payload hash + expected-version semantika zahtevaju proveru prema M00 |
| **Clock** | **`PRESERVE` (uvedeno u ovom radu)** | `app/platform/clock.py` — UTC-aware, freezable; svih 17 zatečenih `datetime.now` mesta prevedeno |
| Exact decimal | **`REMOVE_CONFLICT`** | `app/common/money.py` — vidi F-03 |
| Storage | `ADAPT` | `app/domains/documents/storage.py` — lokalni FS; nema tenant particije ni signed URL-a |
| PII-free observability | `VERIFY_IN_REPO` | Nema centralnog log/redaction sloja; PII u logovima nije dokazano odsutno |

### Foundation (Talas 2)

| Modul | Klasifikacija | Putanja / dokaz |
|---|---|---|
| M01 Identity | `ADAPT` | `app/domains/identity/`, `app/security/{auth,password,oidc}.py`. Email+password i Google OIDC rade; session revocation i M01 revocation-on-every-request nisu dokazani |
| M02 Pozivnice | `ADAPT` | `identity/invite_tokens.py`, `Invitation` model, `tests/test_invitations.py`. Invite-only postoji; M02 ugovor je znatno širi (55 KB master) |
| M03 Multi-tenancy | `ADAPT` | `app/security/context.py`. Server-derived context postoji i testiran je; **nedostaju composite tenant FK/UNIQUE i RLS** (§7) |
| M04 School/Subscription | `IMPLEMENT` | `Organization` postoji kao tenant, ali nema subscription, entitlement, status ni agreement-shard modela |
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
| M12 Finansije | **`REMOVE_CONFLICT`** | `domains/billing/`, `domains/payments/` — vidi F-03. Nema append-only ledger/credit modela |
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

### F-02 — root `npm run verify` je neispravan

- **Repo dokaz:** `package.json` `workspaces` navodi `packages/contracts`, koji ne postoji; `verify:parity`, `verify:arch` i `verify:migrations` pozivaju `scripts/openapi-parity.mjs`, `scripts/arch-audit.mjs` i `scripts/migration-audit.mjs`, od kojih nijedan ne postoji. `npm run verify:arch` → `MODULE_NOT_FOUND`.
- **Posledica:** nije CI pad (CI pokreće Python komande direktno), ali root harness koji izgleda kao ulazna tačka ne radi. Novi programer koji prvo pokuša `npm run verify` dobija grešku.
- **Minimalni predlog:** obrisati tri mrtva `verify:*` script-a i `packages/contracts` iz `workspaces`, a `verify` preusmeriti na `scripts/check.sh`. **Nije primenjeno** — brisanje deklarisanog workspace-a je odluka o strukturi projekta, ne posledica ovog zadatka.
- **Status:** `CHALLENGE_NOT_APPLIED`.

### F-03 — novac je integer minor-unit master (protivreči §3)

- **Dokument:** `00-CLAUDE-CODE-IZVRSI.md` §3: „Novac je `NUMERIC(18,2)` ili dokazivo ekvivalentan exact decimal […] nema float/double, skrivene FX konverzije **ni paralelnog minor-unit mastera**."
- **Repo dokaz:** `app/common/money.py` definiše `Money(amount_minor: int, currency: str)`. Šest kolona u bazi su `integer` minor units: `billing_run.total_minor`, `charge.amount_due_minor`, `charge.amount_paid_minor`, `group.base_monthly_price_minor`, `group_membership.discount_minor`, `payment_record.amount_minor`.
- **Posledica:** ovo *jeste* exact (nema float), pa ne gubi tačnost, ali je tačno onaj „paralelni minor-unit master" koji ugovor zabranjuje. Utiče na M12 API/import/export decimal-string ugovor i na budući M12 append-only ledger.
- **Minimalni predlog:** migracija `integer → NUMERIC(18,2)` je backward-safe u jednom smeru (deljenje sa 100), uz decimal-string na API granici. To je M12 (Talas 3) posao sa sopstvenom reconciliation obavezom — **ne** usputna izmena.
- **Status:** `CHALLENGE_NOT_APPLIED` — evidentirano, čeka Talas 3. Nije bezbednosni problem, pa ne zaustavlja nijednu nezavisnu stavku.

### F-04 — `Organization` znači dve različite stvari

- **Dokument:** `00-START-OVDE-PROGRAMER.md` §4: „Jedna škola je jedan H0 security tenant; Organization […] nije authorization domen."
- **Repo dokaz:** `app/domains/organization/models.py` — `Organization` *jeste* authorization tenant kroz ceo kod (`organization_id` u 42 tabele i u svakom guard-u).
- **Posledica:** kada M04 uvede pravi v5.7 `Organization`, isto ime će u istom kodu značiti i „tenant" i „ne-tenant grupisanje" — klasa greške koja proizvodi tiho cross-tenant curenje.
- **Minimalni predlog:** rezervisati ime pre M04: v5.7 Organization ulazi u kod kao `OrganizationGroup` (ili slično), a zatečeni `Organization` ostaje netaknut. Preimenovanje zatečenog `Organization → School` je zabranjeno DCR-om §3 kao kozmetički rewrite.
- **Status:** `CHALLENGE_NOT_APPLIED` — odluka o imenovanju pripada vlasniku proizvoda, potrebna pre Talasa 2 (M04).

### F-05 — `CURRENT-CODE-BASELINE.md` je istovremeno „popuni me" i hash-pokriven

- **Dokument:** `CURRENT-CODE-BASELINE.md` („Claude Code popunjava ovo automatski") naspram `MANIFEST-SHA256.md`, koji taj isti fajl pokriva među 72 hash-ovana fajla.
- **Posledica:** popunjavanje fajla na njegovom mestu trajno obara proveru integriteta transporta.
- **Primenjeno rešenje:** `docs/spec/v5.7/` ostaje bajt-identičan primljenom paketu (manifest prolazi, 72/72), a popunjeni baseline živi na `docs/CURRENT-CODE-BASELINE.md`. Nijedan dokaz nije izgubljen; razdvojeni su „šta je primljeno" i „šta je zatečeno".
- **Status:** `APPLIED` (proceduralno, bez izmene kanona).

### F-06 — nema nijedne od 40 M21 job definicija

- **Repo dokaz:** `app/worker.py` + `app/platform/outbox/worker.py` su jedini pozadinski proces; nema registra job-ova, lease/fencing-a ni dead-letter dual control-a.
- **Posledica:** M21 acceptance (39 H0 job-ova + 1 default-disabled M28) je u celini `IMPLEMENT`, što je najveći pojedinačni preostali obim u H0.
- **Status:** evidentirano kao obim, ne kao kontradikcija.

## 5. Šta je u ovom radu stvarno urađeno

1. Paket verifikovan (72/72 SHA-256) i ugrađen u repo kao `docs/spec/v5.7/`, bajt-identičan.
2. `scripts/verify-spec-manifest.sh` — gate koji hvata tihu izmenu kanona (testiran i pozitivno i negativno).
3. Baseline popunjen stvarnim vrednostima i stvarnim exit kodovima → `docs/CURRENT-CODE-BASELINE.md`.
4. Klasifikacija svih M00–M21 + M28 oblasti (ovaj dokument).
5. Talas 1, prvi port: `app/platform/clock.py` + prelazak svih 17 zatečenih mesta + 7 novih testova; usput otklonjen zatečeni pad (F-01).

## 6. Šta NIJE urađeno

- Nijedan v5.7 QA scenario nije implementiran. Zatečenih 293 testova pokriva zatečeni proizvod.
- Nijedna migracija nije dodata (`alembic check` čist, head i dalje `a1c4f2d80b37`).
- Talasi 2–5 nisu započeti. Nijedan modul nije `IMPLEMENTED`.
- Web build/typecheck i Cypress E2E nisu izvršeni u ovoj sesiji.
- F-02, F-03, F-04 čekaju odluku vlasnika proizvoda.

## 7. Predloženi sledeći korak

Dovršiti Talas 1 pre otvaranja Talasa 2: preostali zajednički portovi su `audit` seal,
`outbox` inbox/dead-letter i `idempotency` canonical payload hash. Paralelno je potrebna
odluka o F-04 (imenovanje), jer blokira M04, koji je prvi korak Talasa 2.
