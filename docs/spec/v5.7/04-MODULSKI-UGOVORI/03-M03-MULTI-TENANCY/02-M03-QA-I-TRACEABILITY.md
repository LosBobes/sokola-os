---
tip: qa-i-traceability
modul-id: M03
status: SPEC_CANDIDATE
datum: 2026-09-08
revizija: "1.2"
schema-zavisnosti: [M01, M04]
obavezni-scenariji: 52
---

# M03 — QA i traceability

## 1. Pravilo dokaza

Dokumentaciono mapiran scenario nije dokaz implementacije. Stvarni PASS zahteva test/evidence vezan za konkretan repo commit i migration head. Svaki test koristi isključivo sintetičke podatke.

Minimalni seed:

- `School A` aktivna i `School B` aktivna, različite Organization veze ili ista Organization za poseban scenario;
- `School C` u pripremi i `School D` deaktivirana;
- OWNER A, MANAGER A, INSTRUCTOR A, GUARDIAN A;
- OWNER B, INSTRUCTOR B, GUARDIAN B;
- korisnik `Multi` sa različitim ulogama u A i B;
- korisnik `ParentTrainer` kao roditelj i trener u A;
- dete `ChildAB` sa odvojenim članstvima u A i B;
- najmanje po jedan tenant-scoped resurs istog tipa u A i B;
- dve aplikacione sesije istog naloga i dva taba iste sesije;
- queued job, cache, realtime subscription, privatni storage objekat i export za oba tenant-a.

## 2. Deterministični acceptance scenariji

### A. Izbor i lifecycle konteksta

| ID | Setup / radnja | Očekivani dokaz |
|---|---|---|
| M03-QA-001 | Validna M01 sesija ima jednu aktivnu školu i jedan workspace. | X03 se može preskočiti; server pravi jedan `SessionTenantContext`; početna ruta odgovara workspace-u. |
| M03-QA-002 | Korisnik ima dve škole i različite role. | TEN-Q01 vraća samo dozvoljene škole sa njihovim workspace opcijama; X03 traži izbor; nema operativnih podataka pre izbora. |
| M03-QA-003 | Korisnik ima GUARDIAN i INSTRUCTOR role u istoj školi. | Jedna School stavka i dve `workspace_key` opcije; izbor menja prikaz, ali M05 računa uniju obe aktivne role; M07 i dalje ograničava konkretno dete/subjekt. |
| M03-QA-004 | Validna sesija nema aktivnu kombinaciju. | Prazan neutralan rezultat i X04/`TENANT_CONTEXT_REQUIRED`; ne otkriva prethodne škole/uloge. |
| M03-QA-005 | Poslednji zapamćeni tenant je u međuvremenu opozvan. | Hint se odbacuje; kontekst se ne otvara; prikazuju se samo preostale dozvoljene kombinacije. |
| M03-QA-006 | Škola je `IN_PREPARATION`, actor ima setup pravo. | Samo `SETUP_ONLY`; redovni Core query/command je 403 `TENANT_SETUP_ONLY`. |
| M03-QA-007 | Škola je `DEACTIVATED`. | Nije aktivan izbor; redovni workspace se ne otvara; istorijski podaci nisu obrisani. |
| M03-QA-008 | TEN-01 switch A→B sa validnim expected version-om. | Jedan novi aktivni kontekst, context version +1, audit/outbox; A cache/subscriptions očišćeni pre B rendera. |
| M03-QA-009 | TEN-02 clear context. | Tenant izbor nestaje bez M01 logout-a; druga sesija istog naloga ostaje nepromenjena. |
| M03-QA-010 | Retry TEN-01 istim request ID-em i payload-om. | Isti poslovni rezultat; nema druge revizije/switch događaja. |
| M03-QA-011 | Isti request ID sa drugim tenant/`workspace_key` payload-om. | 409 `TENANT_IDEMPOTENCY_KEY_REUSED`; prvi izbor ostaje. |
| M03-QA-012 | TEN-Q01 ima više od 100 škola u sintetičkom fixture-u i više workspace opcija po školi. | Bounded paginacija škola, max 100, stabilan cursor/sort; workspace-i su stabilno sortirani; nema preskakanja/duplikata. |

### B. Cross-tenant i object-level zaštita

| ID | Setup / radnja | Očekivani dokaz |
|---|---|---|
| M03-QA-013 | Aktivna A sesija traži B resurs po direktnom ID-u. | 404 `TENANT_RESOURCE_NOT_FOUND_SAFE`, istog oblika kao nepostojeći ID. |
| M03-QA-014 | Aktivna A sesija šalje validan `school_id=B` u body/header/query poslovnog endpoint-a. | Parametar nije autoritet; tenant-scoped lookup koristi A i vraća 404 `TENANT_RESOURCE_NOT_FOUND_SAFE`; nema B podataka ni promene. |
| M03-QA-015 | A list endpoint ima 3 reda, B ima 7. | A dobija samo 3; total/page metadata ne odaje B. |
| M03-QA-016 | A count/report endpoint nad istim filterom. | Rezultat računa samo A iz izvora, ne globalno pa UI-filter. |
| M03-QA-017 | A search koristi ime osobe koja postoji samo u B. | Prazan rezultat jednak nepostojećoj osobi; nema hint-a da B ili osoba postoje. |
| M03-QA-018 | A export zahtev prosleđuje B resource/filter/cursor. | Export se ne kreira; B storage/job/audit nije dotaknut. |
| M03-QA-019 | A update pokušava povezati A child sa B parent entitetom. | Cela transakcija odbijena; composite DB/application guard; nema parcijalnog reda. |
| M03-QA-020 | A create/update pokušava mass-assign `school_id=B`. | DTO ignoriše/odbija polje; server koristi A context; test mass assignment prolazi. |
| M03-QA-021 | Tenant-scoped unique naziv postoji u A i kreira se isti u B. | Dozvoljeno; isti naziv drugi put u istoj školi je konflikt. |
| M03-QA-022 | Globalni `Person` ima membership u A i B; admin A otvara profil. | Vidi samo A školski profil/odnose; nema naziva/statusa B. |
| M03-QA-023 | A i B pripadaju istoj Organization. | Organization veza ne omogućava A actoru B query/command. |
| M03-QA-024 | Platform administrator bez `SupportAccessGrant` traži tenant operativni resurs. | Odbijeno; platform role nije globalni bypass. |
| M03-QA-025 | Privatni storage key/URL iz B koristi se u A. | Signed/download guard daje safe 404; objekat nije stream-ovan niti logovan. |
| M03-QA-026 | Cache je prethodno zagrejan B rezultatom, zatim isti resource ID traži A. | Nema cache hit-a za B; tenant/viewer/context dimenzije dokazive u key policy/testu. |
| M03-QA-027 | Tenant-scoped query se pozove bez `TenantExecutionContext`. | Fail-closed `TENANT_ISOLATION_FAILURE`; nema SQL/business upisa; security alert sa correlation ID-em. |

### C. Switch, revoke, concurrency i client/PWA

| ID | Setup / radnja | Očekivani dokaz |
|---|---|---|
| M03-QA-028 | Dva taba iste sesije istovremeno switch-uju A→B i A→C sa istim expected version-om. | Tačno jedan uspeh; drugi 409 stale/conflict; server ima jedan aktivni kontekst. |
| M03-QA-029 | Spori A response stigne nakon uspešnog switch-a na B. | Client odbacuje response po context version-u; A podatak ne ulazi u store/DOM. |
| M03-QA-030 | A mutacija prođe početni guard; drugi tab switch-uje na B pre commit-a. | Visokorizični commit recheck odbija A mutaciju ili je završava samo ako je već commitovana pre switch-a; nema B posledice. |
| M03-QA-031 | M06 suspenduje A membership dok A ekran radi; B membership ostaje aktivan. | Sledeći A request odbijen i A context invalidiran; korisnik može izabrati B bez brisanja globalnog naloga. |
| M03-QA-032 | M05 opozove poslednju role koja je nudila trenutno izabrani `workspace_key`, dok druga aktivna uloga osobe u A ostane. | Coordinator više ne nudi stari key; preference se invalidira ili korisnik bira drugi dozvoljeni workspace. Opozvana prava odmah nestaju, preostala M05 prava ostaju. |
| M03-QA-033 | M07 opozove guardian vezu za dete dok je GUARDIAN ekran otvoren. | Naredni child query/download vraća 404 safe; child cache/projection invalidiran; druge dozvoljene veze ostaju. |
| M03-QA-034 | M04 deaktivira A dok postoje session, websocket i queued job. | Tenant access version/status odmah blokira nove requestove; socket se zatvara; job ne pravi novi upis; outbox recovery postoji. |
| M03-QA-035 | Membership revoke commitovan na čvoru A, sledeći request ide na čvor B pre outbox consumer-a. | Autoritativni/version read-through odbija; nema stale-cache prozora. |
| M03-QA-036 | PWA je prikazala A, korisnik switch-uje na B pa izgubi mrežu. | Ne prikazuje A privatni response kao B niti dozvoljava offline mutaciju; jasno offline/read-only stanje. |
| M03-QA-037 | Back dugme posle A→B switch-a otvara staru A rutu. | Ponovna tenant provera; nema A sadržaja bez potvrđenog switch-a nazad. |
| M03-QA-038 | Nesačuvana A forma i izbor switch-a. | UI upozorava pre switch-a; nakon potvrde A draft se ne prenosi u B; nakon odustajanja context ostaje A. |
| M03-QA-039 | Realtime event za A stigne nakon switch-a na B. | Event je odbačen/kanal zatvoren po tenant/context version-u; B store ne menja A payload. |
| M03-QA-040 | Deep-link za dozvoljeni B resurs dok je A aktivna. | Pre sadržaja se prikazuje/traži potvrda B context-a; uspešan switch pa novi fetch; bez prefetch curenja. |

### D. Job, outbox, migracija i topologija

| ID | Setup / radnja | Očekivani dokaz |
|---|---|---|
| M03-QA-041 | Platform cron obrađuje A i B; B posao pada. | Izolovan fan-out; A commit ostaje validan, B ide u svoj retry/dead-letter; nijedan shared transaction/context. |
| M03-QA-042 | User-initiated A export čeka u redu, zatim actor izgubi A pristup pre izvršenja. | Job ponovo proverava pristup i ne proizvodi novi dostupan export; kontrolisan failure/audit. |
| M03-QA-043 | Tenant outbox događaj nema `tenant_id` ili ima mismatch sa aggregate-om. | Producer/contract test odbija commit ili event; ne šalje se neodređenom consumer-u. |
| M03-QA-044 | Worker dobije job bez school scope-a. | `TENANT_ISOLATION_FAILURE`; nema default/poslednje korišćene škole. |
| M03-QA-045 | Migracija nalazi legacy red sa jednoznačnom FK putanjom do A. | Determinističan A backfill, kontrolni count/hash i tenant constraint. |
| M03-QA-046 | Migracija nalazi orphan ili dve moguće škole. | Exception report; red nije automatski pridružen; aktivni tok ga ne čita. |
| M03-QA-047 | Fresh install i upgrade sa podržane prethodne baze. | Ista schema pravila; tenant constraints i seed dve škole prolaze. |
| M03-QA-048 | Composite FK pokušava povezati A child i B parent direktnim SQL/integration upisom. | DB odbija i kada se application service zaobiđe. |
| M03-QA-049 | FK ka globalnom Person/UserAccount. | Obična globalna FK postoji; tenant pristup se dokazuje membership/subject guardom, bez lažnog global-table `school_id`. |
| M03-QA-050 | Ako repo koristi RLS: pooled connection nakon A transakcije obrađuje B. | Tenant setting ne curi; A redovi nisu vidljivi; app role nema nekontrolisan owner/`BYPASSRLS` bypass. |
| M03-QA-051 | TEN-04 isti request ponovljen posle network timeout-a. | Jedan tenant access version bump/receipt; isti rezultat; drugačiji payload konflikt. |
| M03-QA-052 | Restore sintetičkog backup-a. | School ID-evi, tenant veze i constraints ostaju; cross-tenant matrica ponovo prolazi. |

## 2.1. Scenario-po-paragraf normativna mapa

| QA ID | M03 master normativni oslonac |
|---|---|
| M03-QA-001 | §§5.3–5.5, 6.4, 12 TEN-Q01/TEN-01, 16 |
| M03-QA-002 | §§5.4, 6.4, 12 TEN-Q01, 16 |
| M03-QA-003 | §§3, 5.3–5.5, 6.4, 8, 16 |
| M03-QA-004 | §§6.4, 12 TEN-Q01/TEN-Q02, 13 |
| M03-QA-005 | §§6.4, 8–9, 12 TEN-Q01 |
| M03-QA-006 | §§5.1, 6.2, 13, 16 |
| M03-QA-007 | §§5.1, 6.3, 9 |
| M03-QA-008 | §§9–10, 12 TEN-01, 14–15 |
| M03-QA-009 | §§9, 12 TEN-02, 14–15 |
| M03-QA-010 | §§12 TEN-01, 14 |
| M03-QA-011 | §§12 TEN-01, 13–14 |
| M03-QA-012 | §§12 TEN-Q01, 20 |
| M03-QA-013 | §§7–8, 13 |
| M03-QA-014 | §§1, 7–8, 13 |
| M03-QA-015 | §§7–8, 11 list/count/search |
| M03-QA-016 | §§8, 11 reporting |
| M03-QA-017 | §§4, 7–8, 13 |
| M03-QA-018 | §§8, 11 export/storage/job, 12 TEN-PORT-02/03 |
| M03-QA-019 | §§7, 12 TEN-PORT-02, 14 |
| M03-QA-020 | §7.8 i §8 |
| M03-QA-021 | §7.4 |
| M03-QA-022 | §§4.4–4.5, 7.5, 8, 17 |
| M03-QA-023 | §§4.1–4.2, 17 |
| M03-QA-024 | §§3 `PLATFORM`, 4, 6.3, 17, 19 |
| M03-QA-025 | §§8, 11 storage |
| M03-QA-026 | §§10–11 cache |
| M03-QA-027 | §§8, 12 TEN-PORT-01, 13 |
| M03-QA-028 | §§9–10, 12 TEN-01, 14 |
| M03-QA-029 | §§9–11, 16 |
| M03-QA-030 | §§8.9, 10, 14 |
| M03-QA-031 | §§6.1, 9, 12 TEN-03, 14 |
| M03-QA-032 | §§3, 5.3–5.5, 8–9, 12 TEN-03, 14 |
| M03-QA-033 | §§8–9, 11, 12 TEN-03, 14 |
| M03-QA-034 | §§5.1–5.2, 6.3, 9, 12 TEN-04/TEN-PORT-03, 14 |
| M03-QA-035 | §§8, 12 TEN-03, 14, 20 |
| M03-QA-036 | §§10–11 browser/PWA, 16, 19 |
| M03-QA-037 | §§8, 10, 16 |
| M03-QA-038 | §§10, 16 |
| M03-QA-039 | §§10–11 realtime, 15 |
| M03-QA-040 | §§8, 10, 16 |
| M03-QA-041 | §§11 cron, 12 TEN-PORT-03, 14–15 |
| M03-QA-042 | §§11 job/queue, 12 TEN-PORT-03 |
| M03-QA-043 | §§7, 11 outbox/event, 15 |
| M03-QA-044 | §§11 job/queue, 12 TEN-PORT-03, 13 |
| M03-QA-045 | §§7, 18 |
| M03-QA-046 | §§7.10, 18 |
| M03-QA-047 | §§18, 22 |
| M03-QA-048 | §7.2–7.3 |
| M03-QA-049 | §§4.4–4.5, 7.5 |
| M03-QA-050 | §§4, 7 RLS pasus, 18, 21 |
| M03-QA-051 | §§12 TEN-04, 14 |
| M03-QA-052 | §§18, 22 i M21 restore dokaz |

## 3. Obavezne automatizovane grupe

| Grupa | Minimalni sadržaj |
|---|---|
| unit | eligibility matrica, context lifecycle, status/setup mode, context/version compare, error mapping |
| integration | `SessionTenantContext`, composite FK/unique/check, tenant repository, idempotency receipts, access-version bump |
| contract | TEN command/query input-output, error kodovi, outbox schema version, bounded pagination |
| security | IDOR/BOLA, mass assignment, list/count/search/export, platform bypass, storage/cache/realtime isolation |
| e2e | jedna/više škola, više uloga, X03, switch, deep-link, back, dirty form, mobile/keyboard |
| concurrency | dva taba, slow response, in-flight mutation, revoke/deactivate race, same idempotency key |
| jobs/resilience | fan-out, job bez tenant-a, revoke pre execute-a, consumer replay, dead-letter/recovery |
| migration | fresh install, supported upgrade, deterministic backfill, orphan exception, forward recovery |
| PWA | stale response, cache partition, switch/logout/revoke, bez offline mutation success-a |
| restore | obnovljene dve škole i ponovljena cross-tenant matrica |

## 4. Traceability ka aktivnim ugovorima

| Aktivni autoritet | M03 odluka |
|---|---|
| M00 scope/arhitektura i DCR-20260907-01 rev. 2.3 | School je jedini H0 security tenant; svi transportni/asinhroni slojevi nose isti tenant guard. |
| M01 master | Login je tenant-neutralan; M03 rešava school context; session claim/client school ID nisu pravo. |
| M04 master | Organization ne daje cross-school pristup; School lifecycle i entitlement nisu zamena za authorization. |
| M05 master | Prikazni workspace nije permission; više aktivnih uloga se računa server-side u jednom school context-u. |
| M06/M07 master | Membership i guardian/payer subject basis su odvojeni dokazi; globalni Person/account nisu tenant grant. |
| M19/M28 ugovori | Multi-tab, slow response, deep-link, PWA cleanup i explicit school switch vezuju svaki private response za `context_version`. |
| CURRENT-CODE-BASELINE | Javni ekran nije dokaz server tenant izolacije; kodni status ostaje `CODE_REPOSITORY_UNVERIFIED` do repo/test pregleda. |

## 5. Međumodulski portovi koje sledeći ugovori moraju koristiti

| Modul | Obaveza prema M03 |
|---|---|
| M02 | Invitation nosi target school, ali acceptance pre commit-a proverava M03 School status/tenant boundary; invitation token ne postaje tenant authority. |
| M04 | School lifecycle i tenant-wide security promena atomarno pozivaju TEN-04; Organization nikad ne daje operativni access. |
| M05 | Role/permission evaluation koristi isti `TenantExecutionContext`; platform/support nema implicitni bypass. |
| M06 | SchoolMembership promena koja utiče na pristup poziva TEN-03 bez stale prozora; membership nema role polje. |
| M07 | Guardian revoke i subject scope invalidiraju relevantne tenant projekcije/context; globalna porodična veza nije pristup. |
| M08/M09 | Sve školske strukture i njihove reference koriste tenant-safe FK/application guard. |
| M10–M18 | Svaki command/query/report/export prima provereni context; nijedan ne prihvata client school ID kao autoritet. |
| M19 | Shell/X03/deep-link/PWA sprovode switch cleanup i response context-version check. |
| M20 | School provisioning poziva TEN-05; svaki import fajl/job/candidate/result pripada jednoj školi. |
| M21 | Audit/outbox/jobs/telemetry/backup/restore i security suite proveravaju tenant dimenzije i failure ponašanje. |
| M28 | Portal reuse M03 context, ali dodaje guardian child context/projekcije; ne pravi drugi tenant resolver. |

## 6. Otvoreno, ali neblokirajuće za kodiranje

| Stavka | Source | Bezbedni ugovor dok nije potvrđeno | Blokira |
|---|---|---|---|
| fizička tenant topologija baze | `REPOSITORY` | zadržati postojeću samo uz sve M03 testove; zajednička šema koristi tenant kolone/veze | samo izbor migracione implementacije |
| RLS | `REPOSITORY/PROGRAMMER_DECISION` | nije obavezan; ako postoji, defense-in-depth bez bypass-a/pool curenja | ne blokira application/DB guardove |
| cache/job/realtime tehnologija | `REPOSITORY` | adapter mora nositi tenant/context/security verzije i fail-closed | samo konkretan adapter test |
| performance SLO context resolvera | `REPOSITORY/PRODUCTION_DECISION` | meriti u postojećem stacku; bez oslabljenog freshness pravila | produkcioni tuning |
| retention context/audit istorije | M17 legal/production | čuvati minimalno i ne brisati pre aktivnog pravila; bez PII payload-a | realni pilot |
| data residency/RPO/RTO | M17/M21 | konfigurabilna struktura, sintetički staging | realni pilot/produkciju |

Ništa iz ove tabele ne dozvoljava privremeno isključivanje tenant izolacije.

## 7. Dokumentacioni acceptance M03

M03 dokumentaciona integracija prolazi kada:

1. postoji jedan aktivni autoritet da je `School` tenant;
2. nema aktivnog teksta koji Organization, school code, role claim ili globalni Person tretira kao access;
3. `SessionTenantContext` i `TenantExecutionContext` su jednoznačni i ne dupliraju M01/M05/M06;
4. context switch, parallel tabs, slow response i in-flight commit imaju determinističan rezultat;
5. globalni FK i tenant composite FK pravila nisu pomešana;
6. list/count/search/export/cache/job/storage/realtime izolacija je eksplicitna;
7. svih 52 scenarija je mapirano na master ugovor;
8. status stvarnog koda ostaje `UNVERIFIED/REPOSITORY` dok Claude Code ne pregleda repo;
9. M03 nije predstavljen kao finalni developer release ili pilot odobrenje.
