---
tip: screen-command-contract
modul-id: M28
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
---

# M28 — ekrani, komande i migracija P01–P08

## 1. Pravilo površine

Stable `route_key` je deo ugovora; konkretan URL, router i frontend stack su tehnička sloboda. Privatna ruta se ne resolve-uje samo na osnovu URL-a. Pre rendera prolazi M01 session, M03 context, M04 entitlement, ACTIVE M28 pilot, runtime flag, M05 portal permission, M07 basis i owner permission/resource guard. Neautorizovana sekcija se izostavlja bez naziva/count-a; cross-tenant ili skriven resource daje safe 404.

`Primary interaction` je svesni tap/click/keyboard activation koji menja ekran ili šalje poslovnu nameru. Login, izbor škole kada kontekst ne postoji, čitanje/skrolovanje pravnog teksta, OS permission prompt, error recovery i potvrda visokorizične akcije računaju se i ne skrivaju, ali nisu deo quick-flow cilja ako početni uslovi ispod nisu ispunjeni. Nijedna pravna odluka, fee, izbor između više dece ili destructive akcija ne sme se automatski preskočiti radi „tri klika”.

## 2. Kanonske M28 rute i guards

| Route key | Površina | Query/command | Dodatni owner permission/basis | Offline |
|---|---|---|---|---|
| `PORTAL_SCHOOL_SELECT` | izbor škole/workspace-a | `ListMyPortalSchools`, `SelectMyPortalSchool` | M03 eligible context path; bez private count-a | samo javni shell, izbor zahteva mrežu |
| `PORTAL_HOME` | personalizovani single-school Home | `BootstrapMySokola`, `GetMySokolaHome` | svaka sekcija ima svoj owner permission/basis | private DENY |
| `PORTAL_CHILDREN` | Moja deca | `ListMyChildren` | `school.people.basic.view` + ACTIVE guardian link | DENY |
| `PORTAL_CHILD_OVERVIEW` | osnovni profil jednog deteta | `GetMyChildOverview` | isto, exact child basis | DENY |
| `PORTAL_SCHEDULE` | raspored povezanog deteta | `GetMySchedule` | `school.schedule.view` + child basis | DENY |
| `PORTAL_ATTENDANCE` | read-only prisustvo deteta | `GetMyAttendance` | `school.attendance.view` + child basis | DENY |
| `PORTAL_FINANCE` | payer obaveze/uplate/kredit/IPS | `ListMyBillingScopes`, `GetMyFinanceSummary`, owner credit command | `finance.view`/`finance.credit.apply` + exact payer basis | DENY |
| `PORTAL_COMMUNICATIONS` | objavljene poruke | `ListMyCommunications`, M13 mark-read | `school.communications.view` + recipient basis | DENY |
| `PORTAL_NOTIFICATIONS` | sopstvene notifikacije | `ListMyNotifications`, M14 mark-read | `school.notifications.view_own`/`mark_read_own` | DENY |
| `PORTAL_DOCUMENTS` | dokument metadata/download | `ListMyDocuments`, M15 ticket/session | `school.documents.view`/`download` + owner subject | DENY |
| `PORTAL_ONBOARDING` | dokument/notice/consent zadaci | `GetMyOnboardingTasks`, M15/M17 coordinator | tačni M15/M17 view+decision permission-i i giver authority | DENY |
| `PORTAL_EVENTS` | visible Events Light | `ListMyEvents`, M16/M12 coordinator | `school.events.view`/`register_child` + child eligibility | DENY |
| `PORTAL_PROFILE_SECURITY` | sopstveni profil i sesije | `GetMyProfileAndSessions`, M01 revoke | M01 self + M06 `school.people.basic.view`; kontakt samo `school.people.contact.view` | DENY |
| `PORTAL_PREFERENCES` | jezik/display/default dete | M28 set/archive preference | `portal.mysokola.preferences.manage_self` | optimistic pending; server-confirmed final |

Svaka route deklaracija u M19 navigation manifestu navodi exact route key, required capability, portal permission i owner permission set. Unknown route/permission/capability blokira publish manifest-a. Deep link čuva samo opaque bound intent; route/resource se otkriva tek posle svih guardova.

## 3. P01–P08 target mapa

| H0 surface | M28 cilj | Disposition | Nepromenljiv poslovni autoritet | Uslov pre prebacivanja |
|---|---|---|---|---|
| `P01` roditeljski početni pregled | `PORTAL_HOME` | `REPLACE` samo za pilot-enabled školu; H0 fallback ostaje | M03/M05/M07 + owner projekcije | Home, context race, revoke, a11y, NFR i rollback PASS |
| `P02` Moja deca | `PORTAL_CHILDREN` / `PORTAL_CHILD_OVERVIEW` | `REUSE` kroz M28 shell | M06/M07 | child safe-404 i guardian isolation PASS |
| `P03` raspored deteta | `PORTAL_SCHEDULE` | `REUSE` | M10 | timezone/DST, period limit i deep-link PASS |
| `P04` prisustvo deteta | `PORTAL_ATTENDANCE` | `REUSE`, read-only | M11 | no-write i child-subject negativni testovi PASS |
| `P05` moje finansije | `PORTAL_FINANCE` | `REUSE` | M07 payer basis + M12 | source barrier, valuta, IPS i credit concurrency PASS |
| `P06` komunikacije/notifikacije | `PORTAL_COMMUNICATIONS` + `PORTAL_NOTIFICATIONS` | `REUSE` | M13/M14 | published/current-recipient i redacted push PASS |
| `P07` dokumenti/onboarding/privacy | `PORTAL_DOCUMENTS` + `PORTAL_ONBOARDING` | `REUSE` | M15/M17 | download reauth i granular evidence PASS |
| `P08` Events Light | `PORTAL_EVENTS` | `REUSE` | M16; M12 samo fee coordinator/finance barrier | capacity, fee create/cancel atomicity i event-cancel pending-materialization test |

`REUSE` znači ista owner semantika i isti command/query port, ne obećanje da će postojeća frontend komponenta bez pregleda repoa biti fizički ponovo upotrebljena. Repo-first implementacija može sačuvati ispravan UI kod ili ga prilagoditi, ali ne pravi paralelni owner endpoint, tabelu, status, permission ili write putanju.

## 4. Quick-flow ugovori

Početno stanje za svaki standardni flow je: korisnik je autentifikovan, jedna škola je aktivna, portal je omogućen, Home je učitan, ciljna kartica je vidljiva i postoji tačno jedno očigledno ciljno dete/billing scope gde je navedeno.

| Flow | Interakcije od početnog stanja | Server potvrda | Cilj |
|---|---|---|---:|
| Pregled sledeće aktivnosti | Home kartica „Sledeće” → detalj/raspored | read envelope | 1 |
| Pregled kompletnog rasporeda | „Raspored” → opciono period/filter | read envelope | ≤2 |
| Pregled prisustva | child quick action „Prisustvo” | read envelope | 1 |
| Pregled duga i evidentirane uplate | finance kartica → detalj | M12 fresh barrier | 1 |
| Prikaži IPS instrukciju | finance detalj → „IPS QR” | server-generated M12 instruction | ≤2 |
| Otvori objavljenu poruku | unread communication kartica → poruka | M13 recipient guard | 1 |
| Označi notifikaciju pročitano | notification → mark read | M14 receipt, tek onda final | ≤2 |
| Otvori dokument | document kartica → metadata → download/open | M15 ticket/session/range guard | ≤3 |
| Elektronski prihvati jedan obavezan dokument | onboarding task → pregled → eksplicitna odluka | M15 receipt | 3 |
| Donesi jednu granular consent odluku | consent task → pregled → GRANT ili DECLINE | M17/M15 receipt | 3 |
| Prijavi jedino eligible dete na besplatan događaj | event kartica → detalj → potvrdi | M16 receipt | 3 |
| Revoke druge sopstvene sesije | profile/security → session → potvrdi revoke | M01 receipt | 3 |

Obavezni izuzeci bez lažnog „tri klika”: izbor škole; više eligible dece; izbor payer scope-a; događaj sa fee review-om; obavezno čitanje nove pravne verzije; capacity/waitlist konflikt; step-up; destructive/revoke potvrda; browser/OS permission; greška ili stale-source recovery. Telemetry beleži samo route key, interaction count, completion/error code i bucket trajanja, bez resource/child ID-ja, iznosa ili sadržaja.

## 5. Atomske UI namere i response envelope

- Home koristi jedan BFF envelope sa nezavisnim section statusima; frontend ne radi nezaštićen fan-out koji bi prikazao deo stare škole.
- Fee event registration i pojedinačno otkazivanje su po jedan endpoint i jedna lokalna transakcija neutralnog M16/M12 coordinator-a. Otkazivanje celog event-a ostaje bounded M16 write, dok M12 barrier važi odmah i katalogizovani consumer materijalizuje finansijske posledice.
- Document/consent onboarding prikazuje owner zadatke kroz jednu projekciju, ali svaka odluka ostaje zasebna komanda/receipt.
- Finance summary vraća jedan dokaziv M12 presek; client ne sabira sirove payment/obligation/credit liste u „istinu”.
- Svaki envelope nosi `school_id`, `context_version`, `authorization_version`, subject/source hash, `generated_at` i section status. Client proverava binding pre rendera.
- `AVAILABLE` sadrži podatak; `EMPTY` je dokazivo prazan autorizovani skup; `STALE` je dozvoljen samo za nekritičan owner read koji owner ugovor dopušta i jasno se označava; `UNAVAILABLE` nema izmišljenu vrednost. Neautorizovan section se izostavlja.

## 6. Rollout, rollback i zabrana duplog UI autoriteta

1. M28 rute se deploy-uju iza entitlement+pilot+flag uslova; flag default OFF.
2. Canary obuhvata tačno allowlisted school ID-jeve, nikad Organization wildcard.
3. Za pilot školu P01 ulaz može preći na `PORTAL_HOME`; P02–P08 koriste iste owner portove. Za ostale škole H0 ulaz ostaje.
4. Legacy i M28 ruta u tranziciji smeju pozivati isti owner command, ali ne smeju dual-write ili imati različite statuse/error mapiranje.
5. Stara ruta se ne uklanja dok deep-link, back, browser refresh, multi-tab context, permission/revoke, a11y, analytics redaction, NFR i rollback testovi nisu PASS.
6. Kill switch odmah sprečava nove M28 private request-e, invalidira projekcije i vraća H0 fallback gde postoji; ne briše owner podatke niti menja owner lifecycle.
7. Tek posle stabilnog pilot perioda i formalno odobrenog migration dokaza pojedina H0 frontend ruta može dobiti `RETIRE_AFTER_MIGRATION`. Surface ID i owner ugovor ostaju istorijski sledljivi.
