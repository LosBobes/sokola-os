---
tip: integration-continuity-map
modul-id: M28
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
---

# M28 — mapa integracije i kontinuiteta

## 1. Autoritet i pozicija modula

M28 je H1 presentation/application modul nad aktivnim M00–M21 ugovorima. Njegovi jedini poslovni master podaci su pilot rollout, portal preference, replaceable projection metadata i sopstveni command receipt. Svaki child, payer, raspored, attendance, finansija, komunikacija, notifikacija, dokument, dokaz, privacy odluka i događaj ostaje u vlasničkom modulu.

Ako se M28 tekst sukobi sa vlasničkim modulom, vlasnički ugovor određuje business lifecycle i podatak, M05 određuje permission, M03 tenant context, M01 session, M04 entitlement, M07 subject basis, a M21 transport/operativnu semantiku. M28 određuje samo portal composition, pilot lifecycle i UX envelope. Konflikt se ne rešava kopiranjem owner pravila u novu tabelu.

## 2. Dozvoljene veze

| Veza | Vrsta | Smer | Dozvoljeno | Zabranjeno |
|---|---|---|---|---|
| M28→M01 | schema/read/command | jednosmerno | account FK, session/self-session port | credential/token kopija |
| M28→M03 | request guard/command | jednosmerno | exact context/version, SelectTenantContext | client-selected tenant kao autoritet |
| M28→M04 | schema/read guard | jednosmerno | School FK, entitlement/current status | Organization kao access grant |
| M28→M05 | authorization guard | jednosmerno | exact portal+owner permission | UI-only ili wildcard allow |
| M28→M06/M07 | read/subject guard | jednosmerno | minimal Person display, guardian/payer basis | kopija Person/Family grafa |
| M28→M08/M09 | nema direktne zavisnosti | — | njihove minimalne label-e dobija kroz verzionisane M10/M16 owner projekcije | direktan port/table join ili write |
| M28→M10/M11 | read composition | jednosmerno | schedule/attendance linked-child read, uključujući potrebne neutralne label-e | parent attendance write/offline queue |
| M28→M12 | read/command port | jednosmerno | payer summary, IPS, apply credit, fee coordinator | client total, card/Stripe, direct ledger write |
| M28→M13/M14 | read/command port | jednosmerno | current-recipient published items/mark read | draft/recipient list/direct notification create |
| M28→M15/M17 | read/coordinator | jednosmerno | task, download, exact evidence/consent decision | bundled consent ili M28 evidence |
| M28→M16 | read/coordinator | jednosmerno | visible event/register/cancel linked child | capacity/status table write |
| M28→M18 | nema Basic zavisnosti | — | buduća personal analytics površina zahteva novu reviziju | school analytics/unsuppressed aggregate |
| M28→M19 | shell/deep-link contract | jednosmerno | route manifest, bound intent, public app shell | private service-worker cache |
| M28→M21 platform interface | jednosmerni infrastrukturni poziv | M28 publish/consume kroz M21 ugovor | outbox/inbox, job, audit, projection invalidation; isporuka M28 događaja ne uvodi M21→M28 domain dependency | M21 business decision ili plaintext access |

M01–M21 ne zavise od M28 za svoju H0 korektnost. Owner modul ne poziva M28 komandu. Owner outbox može imati M28 consumer, ali publish ne zna za M28. Time nema reverse dependency ni ciklusa.

## 3. Portovi i verzionisanje

Svaki owner read port vraća `schema_version`, `school_id`, `authorization_subject_ref`, `owner_version` ili source position, `generated_at` i zatvoreni result/error union. M28 odbija unknown schema i ne pokušava tolerantno da protumači child/finance/legal podatak. Port promena koja menja semantiku je nova verzija sa compatibility prozorom; nema in-place reinterpretacije istorijskog payload-a.

Application coordinator za jednu poslovnu nameru je neutralan sloj iznad owner application servisa, ne novi domen:

| Namera | Učesnici | Transakciona garancija |
|---|---|---|
| fee event registration | M16 + M12 | jedan idempotency key, stabilan lock order, all-or-nothing registracija+obaveza |
| fee event registration cancellation | M16 + M12 | jedan local commit: registracija CANCELLED + svi assessment obligations/credit efekti; bez auto-refund iz M28 |
| whole event cancellation | M16 → `EventCancelledV1` → M12 | M16 commit je trenutni finance barrier; M12 paginirano/idempotentno materijalizuje sve assessment cancellation-e; nema reverse dependency-ja |
| document/privacy decision | M15 + M17 | jedan giver/subject/document hash context, odvojena decision vrsta, evidence u istom commit-u |

M28 BFF sme pozvati read portove paralelno samo posle zajedničkih guardova i mora vezati rezultate za isti context/auth/subject version snapshot. Kritičan mismatch ruši private envelope; nekritičan owner outage daje samo `UNAVAILABLE` section.

## 4. Događaji koje M28 konzumira ili emituje

Payload je English ASCII schema sa opaque ID-jima, verzijama i reason code-om; nema imena, kontakta, iznosa, naslova/sadržaja ili raw tokena.

| Event family | Owner | M28 reakcija |
|---|---|---|
| session/account/authorization/context invalidated | M01/M03/M05 | odmah invalidiraj relevantni projection/client channel; novi request fail closed |
| school/entitlement changed | M04 | recheck pilot effectiveness; invalidate school projections |
| person/school-profile display fact changed | M06 | invalidate exact account/subject projection; event ne nosi kontakt, health ili child payload |
| guardian/payer basis changed | M07 | invalidate exact account/subject projection i preference target; nije grant preko cache-a |
| schedule/attendance changed | M10/M11 | označi relevantan Home section stale/invalid; owner read ostaje autoritet |
| finance changed/barrier gap | M12 | invalidate finance; gap daje UNAVAILABLE, ne nulu |
| communication/notification changed | M13/M14 | invalidate recipient section bez body/recipient payload-a |
| document/evidence/privacy changed | M15/M17 | recompute onboarding task set; optional decline ne blokira portal |
| event/registration changed | M16 | invalidate exact eligible subject section |
| `mysokola.pilot_requested`/`activated`/`suspended`/`reactivated`/`revoked`/`expired` | M28 | audit/operations consumer; revoke-like događaj prekida M28 surface |
| `mysokola.preference_changed`/`archived` | M28 | self projection invalidation; bez preference vrednosti u eventu |

M28 consumer koristi M21 InboxReceipt `(consumer_name,message_id)` i source version. Duplicate je no-op; out-of-order starija verzija ne vraća projection unazad. Gap koji može promeniti authorization/subject/finance/legal istinu blokira pogođenu sekciju do recovery-ja.

## 5. Migracija i brownfield odluke

Claude Code prvo mapira postojeći repo, a zatim svaki nalaz klasifikuje:

| Klasa | Akcija |
|---|---|
| `PRESERVE` | ponašanje i server guard već tačno odgovaraju ugovoru; dodati samo dokaz/test ako nedostaje |
| `ADAPT` | postojeći kod je koristan, ali menja se guard/schema/error/idempotency/UX binding |
| `IMPLEMENT` | nema ekvivalenta; dodaje se u postojeći stack i modularne granice |
| `REMOVE_CONFLICT` | otvorena registracija, email auto-link, child account, cross-tenant aggregation, private offline cache, optimistic finance success ili paralelni master se gasi/migrira |

Nema big-bang rewrite-a, novog framework-a bez potrebe ili duplog auth/tenant/RBAC/finance sistema. Repo određuje tehničke adaptere, naming conventions i migration alat; specifikacija određuje poslovne garancije. Svaka destructive schema promena ima expand/backfill/verify/switch/contract redosled i rollback granicu.

## 6. Uslovi za integraciju u aktivni v5.7 vault

1. M28 folder sadrži tačno jedan master, QA, screen/command mapu i integration mapu; linkovi su relativni i resolve-uju se.
2. M00 registry/dependency/scope označavaju M28 kao H1 `POST_MVP_PRE_PILOT_REQUIRED` i default OFF; M28 ne dodaje nove surface ID-jeve, već proširuje postojeće `P01`–`P08` iz tačnog kataloga 42 H0 površine uz očuvan H0 fallback.
3. M04 registruje `MYSOKOLA_BASIC` capability/entitlement bez automatske aktivacije.
4. M05 registruje svih pet M28 permission-a bez Support/wildcard binding-a.
5. M21 katalog sadrži `portal.pilot_enrollment_expiry`, default-disabled pre M28 rollout-a.
6. P01–P08 mapa nema drugi owner endpoint/status/tabelu i čuva H0 fallback do dokazanog cutover-a.
7. Full validator potvrđuje: UTF-8, YAML, linkove, duplicate heading/ID, runtime ASCII identifiers, schema/FK/unique/status/error/permission/job reference, dependency DAG, no-name/no-secret/no-history i negative security termine.
8. Status ostaje `SPEC_CANDIDATE` dok stvarni repo, migracije i svih 124 M28 + full M00–M21 regresija ne prođu. Dokumentacija sama ne tvrdi IMPLEMENTED/PASS/GO.
