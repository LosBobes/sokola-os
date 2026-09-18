---
tip: qa-traceability
modul-id: M04
status: SPEC_CANDIDATE
datum: 2026-09-16
revizija: 1.5
odlozeni-schema-constraints: [M02, M05, M06]
obavezni-scenariji: 131
---

# M04 — QA i traceability

## 1. Pravilo prijema

M04 se prima samo na stvarnom repozitorijumu i test bazi. Postojanje ekrana ili dokumenta nije dokaz server-side guard-a. Svaki scenario mora proveriti:

- HTTP/application rezultat i stabilni error code;
- committed podatke i odsustvo parcijalnih redova;
- receipt/idempotency ishod;
- audit i outbox broj/payload/redaction;
- tenant i child-PII izolaciju;
- stanje posle transaction rollback-a;
- gde je primenljivo, zahtev koji počinje posle revoke/deactivate commit-a.

Test fixture najmanje sadrži `Organization A/B`, `School A1/A2/B1`, dva platform actor-a, primary owner-a A1, dodatnog owner-a A1, manager-a A1, običnog korisnika B1, jednu Person sa više škola, M02 owner pozive, M03 tenant state/context, M05 role/permissions, M06 membership-e i M09 enrollment istoriju oko vremenske granice.

## 2. Organization i School foundation

| QA ID | Preduslov i radnja | Deterministički očekivani rezultat | Normativni trag |
|---|---|---|---|
| `M04-QA-001` | Platform actor sa permission+step-up poziva ORG-01 validnim payload-om. | Jedan `Organization(ACTIVE)`, version 1, receipt, audit i outbox. | Master §2.1, §8.1 |
| `M04-QA-002` | ORG-01 retry sa istim request ID/payload-om. | Isti Organization/result; nema novog reda/audita/outbox-a. | §7.1 |
| `M04-QA-003` | Isti request ID sa drugim legal_name. | `M04_IDEMPOTENCY_KEY_REUSED` 409; stari rezultat ostaje. | §6, §7.1 |
| `M04-QA-004` | Drugi request koristi isti organization_ref. | `ORGANIZATION_REFERENCE_EXISTS` 409; nema drugog Organization. | §2.1 |
| `M04-QA-005` | Dve organization sa istim legal_name, različitim ref/registration brojem. | Obe dozvoljene; nema auto-merge-a. | §2.1 |
| `M04-QA-006` | Isti RS registration_number na drugom active Organization. | `ORGANIZATION_REGISTRATION_EXISTS` 409. | §2.1 |
| `M04-QA-007` | School actor bez platform permission-a poziva ORG-01/Q platform list. | 403; ne vidi Organization/škole. | §4.2 |
| `M04-QA-008` | SCH-01 sa validnom Organization, Person i profilom. | Atomski nastaju School IN_PREPARATION, active OrganizationSchool, 2 locator-a, status #1, TenantSecurityState=1 i pending initial nomination. Nema account/role/invite/location. | §3.2 |
| `M04-QA-009` | Namerno oboriti insert nominacije unutar SCH-01. | Nijedan School/org-link/locator/status/tenant-state red ne ostaje. | §7.3 |
| `M04-QA-010` | SCH-01 retry posle nepoznatog network ishoda. | Isti School receipt; nema duplikata. | §3.10.1 |
| `M04-QA-011` | Drugi request sa istim provisioning_reference. | `SCHOOL_PROVISIONING_REFERENCE_EXISTS` 409; nema parcijalnih redova. | §3.2.5 |
| `M04-QA-012` | SCH-01 sa archived Organization. | `ORGANIZATION_ARCHIVED` 409. | §3.1 |
| `M04-QA-013` | SCH-01 sa child/account-ineligible target Person. | `OWNER_TARGET_NOT_ELIGIBLE` 422; ništa nije kreirano. | §3.2 |
| `M04-QA-014` | SCH-01 sa nepotvrđenim kontaktom. | `SCHOOL_CONTACT_NOT_VERIFIED` 422. | §2.2, §3.2 |
| `M04-QA-015` | SCH-01 sa EUR ili country != RS. | `SCHOOL_LOCALE_NOT_SUPPORTED` 422. | §2.2 |
| `M04-QA-016` | Proveriti sve `school_kind`; OTHER bez/sa labelom. | Sedam named vrsta prolazi bez labela; OTHER bez labela pada, sa validnim prolazi. | §2.2 |
| `M04-QA-017` | Dve škole iste Organization imaju isti naziv, različit provisioning ref. | Dozvoljeno; nema auto-merge-a. | §3.2.6 |
| `M04-QA-018` | Proveriti da Organization A sa A1/A2 ne daje actoru A1 query A2. | A2 je safe 404/odsutan; Organization veza nije access. | §3.1, §4 |

## 3. Profil, locator i Organization transfer

| QA ID | Preduslov i radnja | Deterministički očekivani rezultat | Trag |
|---|---|---|---|
| `M04-QA-019` | SCH-02 menja name/short_name validnim expected version. | Version+1; samo dozvoljena polja; audit bez plaintext kontakta. | §3.3 |
| `M04-QA-020` | SCH-02 payload sadrži status/organization_id/currency. | `M04_INPUT_INVALID` ili forbidden mass-assignment; ništa od protected polja se ne menja. | §3.3.2 |
| `M04-QA-021` | SCH-02 sa stale version. | `M04_STALE_VERSION` 409; noviji profil ostaje. | §7.2 |
| `M04-QA-022` | SCH-03 pre ijednog time/billing relevantnog reda. | Validan IANA zone ID se menja, reason/audit/version postoje. | §3.3.3 |
| `M04-QA-023` | SCH-03 posle jednog TermOccurrence ili čak otkazanog termina. | `SCHOOL_TIMEZONE_CHANGE_REQUIRES_MIGRATION` 409; stara zona ostaje. | §3.3.4 |
| `M04-QA-024` | SCH-03 sa Windows zonom ili offsetom. | `M04_INPUT_INVALID` 400/422; nema promene. | §2.0 |
| `M04-QA-025` | Logo PNG/JPEG <=2 MiB i validan object tenant ref. | Prihvaćen; audit samo object ref. | §3.3.7 |
| `M04-QA-026` | Logo >2 MiB, SVG/executable polyglot ili ref škole B. | `SCHOOL_LOGO_INVALID` ili safe 404; nema veze/payload leakage-a. | §3.3.7, §4 |
| `M04-QA-027` | LOC-01 rotira slug. | Novi active, stari retired i points-to-new; tačno jedan active. | §3.7 |
| `M04-QA-028` | Dve škole paralelno traže isti slug/code. | Tačno jedna uspeva; druga `SCHOOL_LOCATOR_CONFLICT`. | §7.2.5 |
| `M04-QA-029` | Neautentifikovan user unosi validan school code. | Može dobiti samo neutralni discovery/branding; nema Person/account/membership/role/context. | §3.7.4 |
| `M04-QA-030` | ORG-04 A→B sa punim case/ref/entitlement setom. | Stari link valid_to=T, novi valid_from=T, nema gap/overlap; School ID i tenant podaci isti; entitlement set tačno odobren. | §3.1.6 |
| `M04-QA-031` | Paralelna dva ORG-04 transfera. | Jedan serializovan uspeh; drugi stale/conflict; najviše jedna active veza. | §7.2.2 |
| `M04-QA-032` | ORG-04 bez replacement specifikacije za aktivni CORE_MVP. | `ORGANIZATION_TRANSFER_INCOMPLETE` 422; stari link/entitlement-i ostaju. | §3.1.6 |
| `M04-QA-033` | Posle ORG-04 proveriti owner, roles, Group, Term, Payment, snapshot IDs. | Ništa tenant-scoped nije premešteno/duplicirano; svi School ID-evi isti. | §3.1.5 |
| `M04-QA-034` | ORG-03 dok Organization ima active School. | `ORGANIZATION_HAS_ACTIVE_SCHOOLS` 409. | §3.1.4 |
| `M04-QA-035` | ORG-03 kada nema active School/entitlement. | ARCHIVED terminalno; novi link/grant nije dozvoljen. | §5.1 |

## 4. Owner i School lifecycle

| QA ID | Preduslov i radnja | Deterministički očekivani rezultat | Trag |
|---|---|---|---|
| `M04-QA-036` | SCH-01 završena, M02 initial invite još nije prihvaćen. | 0 active owner role/primary term je privremeno dozvoljeno samo uz jednu pending initial nominaciju; SETUP provisioning je platform-only. | §3.4.1 |
| `M04-QA-037` | M02 initial acceptance validan. | Membership+OWNER role+nominacija FULFILLED+prvi primary term+Invitation ACCEPTED nastaju atomarno. | §3.4.2, §7.3 |
| `M04-QA-038` | Namerno oboriti primary term insert tokom M02 acceptance-a. | Account/identity/membership/role/invitation acceptance se rollback-uju prema M02 ugovoru. | §7.3 |
| `M04-QA-039` | Initial invitation istekne. | School IN_PREPARATION; nomination PENDING; nema owner pristupa. | §3.10.4 |
| `M04-QA-040` | Replacement initial poziv za istu nominaciju. | latest_invitation_id/version se menja; nema nove nominacije/primary term-a. | §2.6 |
| `M04-QA-041` | OWN-01 additional owner za već active OWNER osobu. | `OWNER_NOMINATION_CONFLICT` 409. | §2.6 |
| `M04-QA-042` | Additional owner acceptance. | OWNER role nastaje, nomination FULFILLED; active primary term ostaje isti. | §3.4.4 |
| `M04-QA-043` | M05 pokuša revoke poslednje OWNER role. | `LAST_OWNER_PROTECTED` 409; role ostaje. | §3.4.5 |
| `M04-QA-044` | M05 pokuša revoke role aktuelnog primary, dok postoji drugi owner. | `PRIMARY_OWNER_TRANSFER_REQUIRED` 409; prvo OWN-04. | §3.4.5 |
| `M04-QA-045` | OWN-04 current primary→existing active owner, valid step-up/reason. | Stari term završava i novi počinje na istom T; role set se ne menja. | §3.4.6–8 |
| `M04-QA-046` | OWN-04 ka manager-u bez OWNER role. | `OWNER_ROLE_REQUIRED` 422; stari primary ostaje. | §3.4.6 |
| `M04-QA-047` | Dva OWN-04 sa istom expected version. | Jedan uspeva; drugi tačno `PRIMARY_OWNER_TRANSFER_CONFLICT`. | §3.10.7 |
| `M04-QA-048` | Platform override bez case_reference ili step-up. | 403/422; bez promene. | §3.4.7 |
| `M04-QA-049` | Platform override sa punim dokazom. | Transfer uspeva; audit navodi platform actor, target i case, bez impersonation-a. | §3.4.7 |
| `M04-QA-050` | SCH-04 bez primary term-a. | `SCHOOL_PRIMARY_OWNER_REQUIRED` 422. | §3.5 |
| `M04-QA-051` | SCH-04 bez CORE_MVP entitlement-a. | `SCHOOL_CORE_ENTITLEMENT_REQUIRED` 422. | §3.5 |
| `M04-QA-052` | SCH-04 sa svim osam guardova. | ACTIVE, activated_at set, status history append, audit/outbox; M20 readiness nije automatski „gotov”. | §3.5 |
| `M04-QA-053` | SCH-04 bez lokacije/grupe/člana/rasporeda. | Aktivacija ipak uspeva ako M04 guardovi prolaze; M20 prikazuje nedovršen onboarding. | §3.5 poslednji pasus |
| `M04-QA-054` | Manager pokuša SCH-04/05/06. | Aktivaciju može samo primary owner; de/reactivaciju samo platform; manager dobija 403. | §3.5–6 |
| `M04-QA-055` | SCH-05 validna platform radnja. | DEACTIVATED, status transition, TEN-04 bump, M02 open invites revoked, attempts invalidated; jedan atomic commit. | §3.6.2 |
| `M04-QA-056` | Fault između School status update-a i TEN-04/M02 revoke-a. | Cela transakcija rollback; nema status/access raskoraka. | §7.3 |
| `M04-QA-057` | Request započne posle SCH-05 commita sa starim cache-om. | Odbijen pre poslovnog payload-a/upisa. | §4.4 |
| `M04-QA-058` | Mutacija počne pre SCH-05, commit pokuša posle njega. | Pre-commit recheck je odbija; nema upisa. | §4.4 |
| `M04-QA-059` | Deaktivacija A1 korisnika koji ima B1. | A1 nedostupan; B1 ostaje dostupan. | §3.6.4 |
| `M04-QA-060` | SCH-06 bez active primary/core entitlement. | Reaktivacija odbijena 422; DEACTIVATED ostaje. | §3.6.6 |
| `M04-QA-061` | SCH-06 sa svim guardovima. | ACTIVE + TEN-04; stari SessionTenantContext i invitation ne oživljavaju. | §3.6.6–7 |
| `M04-QA-062` | Reaktiviran School koristi stari pre-deactivation invite. | Generički M02 revoked rezultat; mora se izdati novi poziv. | §3.10.19 |

## 5. Entitlement

| QA ID | Preduslov i radnja | Deterministički očekivani rezultat | Trag |
|---|---|---|---|
| `M04-QA-063` | ENT-01 CORE_MVP sa current Organization i validnim ref. | Jedan ACTIVE grant; audit/outbox/cache invalidation. | §3.8 |
| `M04-QA-064` | ENT-01 sa source Organization druge škole. | `ENTITLEMENT_SOURCE_ORGANIZATION_INVALID` 422. | §3.8.2 |
| `M04-QA-065` | Bez MYSOKOLA_BASIC/OPERATIONS granta. | Oba su neefektivna/default absent. | §3.8.6 |
| `M04-QA-066` | Entitlement postoji, user nema M05 permission. | 403 permission; entitlement ne daje pristup. | §2.8 |
| `M04-QA-067` | User ima permission, ali entitlement/allowlist/flag nedostaje. | Feature nije dostupan; nijedan sloj se ne preskače. | §2.8 |
| `M04-QA-068` | ENT-02 revoke. | Odmah REVOKED; zahtev posle commit-a ne prolazi stale cache. | §3.8.5 |
| `M04-QA-069` | `now == valid_until`, expiry job kasni. | Read-time `ENTITLEMENT_NOT_EFFECTIVE`; job status nije autoritet. | §3.8.3 |
| `M04-QA-070` | ENT-01 replacement aktivnog grant-a. | Stari terminalan REVOKED reason REPLACED, jedan novi ACTIVE; nema overlap-a. | §5.5 |
| `M04-QA-071` | CORE_MVP istekne za ACTIVE School. | School status ostaje ACTIVE; Core poslovni feature-i blocked; account security/platform recovery dostupni. | §3.10.17 |
| `M04-QA-072` | Organization veza sama, bez entitlement-a. | Nijedan capability nije automatski dostupan. | §3.8.6 |

## 6. Subscription snapshot i korekcije

| QA ID | Preduslov i radnja | Deterministički očekivani rezultat | Trag |
|---|---|---|---|
| `M04-QA-073` | Europe/Belgrade, billing_month 2026-08. | Reference je 2026-08-31T22:00:00Z (lokalno 2026-09-01 00:00 CEST); vrednost se proverava IANA bibliotekom. | §3.9.1 |
| `M04-QA-074` | Aktivacija School tačno na reference T. | Nema snapshot-a za prethodni mesec. | §3.9.3 |
| `M04-QA-075` | Deaktivacija School tačno na T, prethodno ACTIVE. | Prethodni mesec je eligible; snapshot nastaje. | §3.9.3 |
| `M04-QA-076` | School deaktiviran posle T, `commercial.subscription_usage_snapshot` radi kasnije. | Koristi history as-of T; snapshot nastaje. | §3.9.10 |
| `M04-QA-077` | Active School nema enrollment-e. | Snapshot `billed_child_count=0`. | §3.9.9 |
| `M04-QA-078` | Person ima 2 ACTIVE enrollment-a u A1. | Count A1 raste tačno za 1. | §3.9.7 |
| `M04-QA-079` | Ista Person ima ACTIVE enrollment A1 i B1. | Count +1 u svakoj školi; nema cross-tenant agregata. | §3.9.7 |
| `M04-QA-080` | Enrollment ACTIVE transition tačno na T. | Ne broji se za mesec koji se završava. | §3.9.2 |
| `M04-QA-081` | Enrollment ACTIVE→SUSPENDED tačno na T. | Broji se za završeni mesec. | §3.10.21 |
| `M04-QA-082` | Poslednji status pre T je U pripremi/Suspended/Ended. | Ne broji se. | §3.9.6 |
| `M04-QA-083` | Enrollment nema history pre T, live status je ACTIVE. | Ne broji se; live status nije autoritet. | §3.9.6 |
| `M04-QA-084` | Dve Person merge-ovane pre T. | As-of port ih broji jednom. | §3.9.8 |
| `M04-QA-085` | Merge nastao posle T, snapshot već postoji. | Snapshot se ne menja/recompute-uje. | §3.9.8 |
| `M04-QA-086` | Dva `commercial.subscription_usage_snapshot` workera obrade isti school/month. | Jedan immutable snapshot; oba dobijaju isti business rezultat. | §7.2.6 |
| `M04-QA-087` | Source history corrupt/incomplete. | 503, retry; nema snapshot-a sa 0 ili guessed count-om. | §3.9.10 |
| `M04-QA-088` | Iscrpi 5 retry-a/24h. | Dead-letter/attention + TEL-010; nema lažnog snapshot-a. | §8.4 |
| `M04-QA-089` | Pokušaj UPDATE/DELETE snapshot-a. | DB/application odbija; original ostaje identičan. | §2.9 |
| `M04-QA-090` | Platform billing SUB-02 corrected count 7. | Correction sequence 1, effective count 7; snapshot unchanged. | §2.10 |
| `M04-QA-091` | Druga correction corrected count 6. | Sequence 2, effective count 6; prva ostaje. | §2.10 |
| `M04-QA-092` | Dve correction paralelno. | Parent lock daje distinct monotone sequence; obe ili validno serializovane. | §7.2.7 |
| `M04-QA-093` | Isti correction request retry. | Ista correction/sequence/result; nema novog reda. | §7.1 |
| `M04-QA-094` | Isti key sa drugim count/reason. | `M04_IDEMPOTENCY_KEY_REUSED` 409. | §7.1 |
| `M04-QA-095` | Owner/manager pokuša correction. | 403 čak i sa svim school permissions. | §2.10 |
| `M04-QA-096` | Correction snapshot-a A1 sa school_id B1. | Safe 404/tenant relation failure; nema cross-tenant linka. | §2.10, §4 |
| `M04-QA-097` | Correction note sadrži child ime/email/datum rođenja. | `SUBSCRIPTION_CORRECTION_PII_FORBIDDEN` 422; ništa nije upisano/logovano. | §4.3 |
| `M04-QA-098` | Snapshot/correction commit, proveriti M12 tabele/outbox. | Nema Obligation/Payment/Allocation/Refund/invoice događaja. | §3.9.12 |

## 7. Security, privacy i brownfield

| QA ID | Preduslov i radnja | Deterministički očekivani rezultat | Trag |
|---|---|---|---|
| `M04-QA-099` | A1 user menja/čita School B1 preko ID-a, slug-a i code-a. | Safe 404/403 bez potvrde B1 postojanja; B1 podaci/audit ne menjaju se. | §4.1 |
| `M04-QA-100` | A1 list/count/export sa B1 zapisima u bazi. | Rezultat sadrži samo A1; total/cursor ne odaju B1. | §4.1 |
| `M04-QA-101` | Pregled audit/outbox/telemetry nakon svih komandi. | Nema plaintext email/phone, child ID liste, imena, tokena ili evidence dokumenta. | §8.3 |
| `M04-QA-102` | Support actor bez posebne platform permission poziva SCH-05/ENT-02/SUB-02. | 403; Support Access nije platform admin. | §4.5 |
| `M04-QA-103` | Migracija existing active School sa dokazanim org/primary/tenant state. | School ID očuvan; backfill determinističan; nema duplikata. | §9 |
| `M04-QA-104` | Existing School ima dve moguće primary-owner role bez dokaza. | Exception report; ne bira se nasumično; ownership mutacije fail-closed. | §9.4 |
| `M04-QA-105` | Existing correction nema school_id, parent snapshot postoji. | school_id se backfill-uje samo iz parenta; constraint prolazi. | §9.8 |
| `M04-QA-106` | Existing snapshot ima sequence_no. | Consumer scan prvo dokazuje da se ne koristi; uklanjanje/ignor se ne dira correction sequence. | §9.7 |
| `M04-QA-107` | Existing public registration/school-code backend pravi pristup. | Klasifikovan REMOVE_CONFLICT i onemogućen/migriran; discovery-only može ostati. | §9.10 |
| `M04-QA-108` | Migration script pokrenut dvaput. | Drugo izvršenje je no-op/replay; nema novih org/link/owner/entitlement redova. | §9 |

## 7a. Komercijalni model — M04-QA-109..126

| QA ID | Preduslov/radnja | Deterministički očekivani rezultat | Trag |
|---|---|---|---|
| `M04-QA-109` | Objaviti validan plan, zatim pokušati update rule/tier/disclosure. | Publish uspeva sa hash-em; svaka kasnija izmena 409 `COMMERCIAL_PLAN_IMMUTABLE`; nova cena zahteva novu version_no. | §2.14–2.16, §5.8 |
| `M04-QA-110` | Agreement item nema PUBLISHED effective plan ili se u kodu/seed-u pokuša fallback cena. | Aktivacija/resolve daje `COMMERCIAL_PRICE_NOT_CONFIGURED`/`COMMERCIAL_PLAN_NOT_PUBLISHED`; nema entitlement-a, charge-a ni guessed iznosa. Static test ne nalazi runtime business price constants. | §3.11 (1–4), §6 |
| `M04-QA-111` | Organization A ima School A1/A2; jedan agreement ima dva SCHOOL item-a i koristi njihove mesečne snapshot-e. | Svaki School usage ostaje zaseban/evidence-linked; contract output može biti konsolidovan po Organization, bez menjanja count-a. | §1.2, §2.21 (SubscriptionBillingSnapshot izmena) |
| `M04-QA-112` | Actor sa pravom u A1 čita agreement/consolidated summary i pokuša drill-down A2. | Organization/agreement nije access grant; A2 business data safe denied; summary nema child PII/existence hint van ovlašćenog commercial view-a. | §4.6 |
| `M04-QA-113` | Event-only Organization ugovara EVENTS bez School. | Valid `EVENT_ORGANIZER_WORKSPACE` item prolazi tek sa M30 resolverom/flagom; ne nastaje School/OrganizationSchool/SchoolMembership. Dok M30 nije active, 503/409 fail-closed. | §1.2 (non-goals), §2.18 |
| `M04-QA-114` | Venue-only Organization ugovara VENUE. | Analogno koristi `VENUE_OPERATOR_WORKSPACE`; nema lažne škole; M33 resolver/flag je uslov. | §1.2 (non-goals), §2.18 |
| `M04-QA-115` | Usage prelazi threshold; testirati sva tri behavior-a. | BLOCK odbija; REQUIRE_ACCEPTANCE ne obračunava i traži novi evidence; CONTRACTED_OVERAGE vraća tačnu objavljenu formulu. Null/unknown behavior 422 pri publish-u. | §2.15, §3.11 (9) |
| `M04-QA-116` | Isti realizovani transaction ref ispunjava direct i marketplace SOKOLA fee pravilo iste exclusivity grupe. | Resolve bira tačno jedno po priority; drugi pokušaj 409 `COMMERCIAL_DUPLICATE_PLATFORM_FEE_FORBIDDEN`; provider fee ostaje odvojeno označen. | §3.11 (10), §2.15 |
| `M04-QA-117` | Nova plan cena važi od T2; usage period/assessment dokaz pre T2 koristi staru verziju. | Nema retroaktivne promene; staro ostaje na V1, novo od T2 na V2; backdate command 409 `COMMERCIAL_RETROACTIVE_CHANGE_FORBIDDEN`. | §2.14, §3.11 (11) |
| `M04-QA-118` | Metric resolver timeout/corrupt evidence za jednu školu. | 503 `COMMERCIAL_USAGE_SOURCE_UNAVAILABLE` retry/attention; nema snapshot/zero/charge za taj scope; drugi tenant se može obrađivati nezavisno. | §3.11 (12), §6 |
| `M04-QA-119` | Hibridni agreement ima SCHOOL_OS+EVENTS/VENUE item-e i preklapajuću exclusivity grupu. | Svaki legitimni product item ima svoj scope/entitlement; isti chargeable ref ne dobija duplu SOKOLA stavku; identity/Organization se ne dupliraju. | §3.11 (8, 10), §2.18 |
| `M04-QA-120` | Migrirati postojeće škole/entitlement-e bez ugovornog/pricing dokaza; pokrenuti dvaput. | School ID/entitlement ostaju; commercial link je null `PILOT_OR_LEGACY` + exception; ne nastaju plan/agreement/cena/dug; drugi run no-op. | §2.21 (SchoolProductEntitlement izmena), §3.11 (16) |
| `M04-QA-121` | API primi `10.005` za vrednost koja mora biti skladištena na RSD scale 2. | Rezultat je decimalni string `10.01` po `ROUND_HALF_UP`; ista vrednost je u DB, response-u i hash input-u. | Master §2.0 |
| `M04-QA-122` | API primi JSON number/float umesto decimalnog stringa za money input. | 422 `COMMERCIAL_AMOUNT_INVALID`; nema normalizacije binary float-a, upisa, audita uspeha ili outbox-a. | Master §2.0, §6 |
| `M04-QA-123` | Plan pokuša da koristi `amount_minor`, `cap_minor`, `flat_amount_minor` ili `per_unit_amount_minor`. | Schema/contract test odbija nepoznato polje; runtime i migracija nemaju paralelni minor-unit source of truth. | Master §2.0, §2.15-2.19 |
| `M04-QA-124` | `base_amount=100.05`, `percentage_bps=1500`. | Exact-decimal formula daje `15.01`; rezultat je isti na svim podržanim adapterima. | Master §2.19 |
| `M04-QA-125` | Postojeći minor-unit redovi se migriraju, uključujući 0, vrednost sa najmanjom nenultom jedinicom valute i maksimalnu dozvoljenu nenegativnu vrednost. | Svaka vrednost se jednom konvertuje u decimal prema istorijskoj valuti/scale-u; reconciliation zbir pre/posle je identičan; drugi run je no-op. | Master §9 |
| `M04-QA-126` | Currency jednog plana/agreement-a ne odgovara amount kontekstu. | 422 `COMMERCIAL_CURRENCY_MISMATCH`; nema implicitne konverzije niti mešanja valuta. | Master §2.14-2.19, §6 |

## 7b. Foundation reference i atomicity — M04-QA-127..131

| QA ID | Preduslov/radnja | Deterministički očekivani rezultat | Trag |
|---|---|---|---|
| `M04-QA-127` | SCH-01 kreira novu školu za postojeću account-eligible Person, pa se fault ubrizga posle M06 SchoolPersonProfile insert-a a pre owner nomination-a. | School, profil, nominacija, TEN-05, audit, outbox i receipt se svi rollback-uju; ponovljen isti request može bezbedno uspeti jednom. | Master §2.6, §3.2, §7.3 |
| `M04-QA-128` | OWN-01 u školi A dobije target Person i SchoolPersonProfile koji pripada školi B ili drugoj Person. | Tenant-safe composite constraint/application guard odbija sa safe 404; nema nominacije, invite-a ili existence hint-a. | Master §2.6, §4.1–4.2 |
| `M04-QA-129` | Posle Foundation migracija pokušati validaciju M04 deferred FK-ova nad pogrešnim `latest_invitation_id` ili OWNER role druge škole/osobe. | Constraint validation pada pre aktivacije use-case-a; validni fixture prolazi; nema perioda sa aktivnim nekontrolisanim referencama. | Master §2.6–2.7, §9 |
| `M04-QA-130` | Published plan sadrži fixed i percentage discount: validan target od `100.05`, zatim self-target, target drugog popusta, cross-plan target, ciklus i zbir popusta veći od target-a; negotiated override se ponovi sa nedostupnim, schema-nevalidnim i hash-mismatch payload-om. | Validan percentage daje `15.01` za 1500 bps i validan fixed je ograničen target iznosom; svaka nevalidna veza ili neproverljiv override daje 422 `COMMERCIAL_PLAN_CONTENT_INVALID` pre publish/obračuna; hash sam ne postaje formula, nijedan rezultat nije negativan niti target/cena izabran implicitno. | Master §2.15, §2.19, §3.11.17 |
| `M04-QA-131` PAR | Jedan ACCEPTED agreement sadrži School A1 i A2, `starts_at` je dostignut; dva različita PLATFORM shard worker-a i request-time resolver rade paralelno, zatim se test ponovi na `ends_at`; zasebno se koristi odsutan/stale fencing dokaz i pokušaj job principal-a da pozove COM-19. | Tačno jedan aggregate CAS aktivira/ističe parent, oba item-a i pripadajuće entitlement efekte bez parcijalne škole; drugi worker vraća receipt/no-op. Pre job-a read-time guard dozvoljava tek od start-a i odbija od end-a; job kašnjenje ne menja rezultat. Odsutan/stale dokaz i komanda van `commercial.effective_transition.execute` opsega failuju pre write-a; audit nosi SYSTEM/job definition/execution/fencing dokaz. | Master §5.12; M21 job katalog |

M04 QA kontinuitet posle integracije je tačno `M04-QA-001..131`, bez rupa/duplikata.

## 8. Traceability ka obaveznih osam tačaka

| Obavezna tačka | Normativni izvor | QA dokaz |
|---|---|---|
| 1. Cilj i granice | Master §0–1 | 008, 018, 053, 098, 107 |
| 2. Entiteti i polja | Master §2 | 001–018, 027–035, 036–049, 063–072, 073–097 |
| 3. Pravila/invarijante/edge | Master §3 | 010–018, 030–033, 036–062, 068–097 |
| 4. Tenant & Security Guard | Master §4 | 018, 026, 029, 055–059, 066–069, 096, 099–102 |
| 5. Lifecycle & transitions | Master §5 | 034–062, 068–071, state-machine generated tests |
| 6. Error catalog | Master §6 | Svaki negativni test proverava tačan code/HTTP |
| 7. Idempotency & concurrency | Master §7 | 002–003, 009–011, 021, 028, 031, 038, 047, 056–058, 068, 086, 092–094, 108 |
| 8. Acceptance kriterijumi | Master §8.5 + ovaj dokument | 001–131 |

## 9. Automatizovani test slojevi

1. Schema/property test generiše validne/nevalidne vrednosti za svako polje i proverava CHECK/UNIQUE/FK/interval pravila.
2. State-machine test generiše svaki par `from × command` i poredi sa tabelama §5; nema neimenovanih prelaza.
3. Transaction fault-injection prekida svaki korak SCH-01, SCH-05/06, OWN-03/04, ORG-04, `commercial.subscription_usage_snapshot` i correction transakcije.
4. Concurrency test koristi stvarne paralelne DB transakcije, ne samo mock threadove.
5. Tenant test fixture u svaki query ubacuje drugi tenant i proverava rows, counts, cursors, caches, exports, storage i outbox.
6. Time test koristi fiksni clock i IANA tzdb; obuhvata letnje/zimsko vreme i strogu `< billing_reference_at` granicu.
7. Security test proverava IDOR/BOLA, mass assignment, CSRF/session, stale cache, log redaction i platform/support razdvajanje.
8. Migration test radi na kopiji brownfield sheme, dvaput, i poredi business invariants pre/posle.

## 10. Definition of Done za M04 dokumentacionu integraciju

- postoji jedan kanonski M04 folder i jedan aktivni master;
- M00 registry i source-of-truth matrica navode M04 kao vlasnika Organization/School/subscription foundation-a;
- M02 dobija interni bulk revoke port i owner nomination reference bez paralelnog ownership mastera;
- M03 status/TEN-04/TEN-05 reference su identične;
- stari foundational dokument je usklađen ili označen kao supersedovan, ne ostaje paralelni autoritet;
- duplirani naslov `4.7 Automatska naplata` je uklonjen;
- `SubscriptionBillingCorrection.school_id` postoji, snapshot nema redundantni sequence, correction ga ima;
- link/YAML/Markdown/UTF-8/duplicate/source-of-truth provere prolaze;
- nema tvrdnje da je stvarni repo implementiran/testiran dok nije pregledan;
- nema tvrdnje da je stvarni repo implementiran ili testiran dok nije pregledan.
