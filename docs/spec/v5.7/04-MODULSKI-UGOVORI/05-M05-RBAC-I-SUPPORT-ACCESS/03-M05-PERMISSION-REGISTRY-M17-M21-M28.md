---
tip: permission-registry
modul-id: M05
status: SPEC_CANDIDATE
revizija: "1.0"
datum: 2026-09-09
obuhvat: [M17, M18, M19, M20, M21, M28]
---

# M05 — kanonski permission registry za M17–M21 i M28

Ovaj dokument je normativni nastavak M05 §3.3. Svaki red je zaseban `PermissionDefinition`; liste skraćene kosom crtom nisu runtime ključevi. `A` je default role binding, `S` je binding koji uvek zahteva navedeni subject/resource guard, a `—` znači deny. Unknown ključ, ključ van aktivne policy revizije ili nepoznat scope failuje zatvoreno. Nema wildcard-a, implicitnog OWNER bypass-a ili permission inheritance-a.

Svi ključevi su offline `DENY`, osim što M19 samo transportuje M11 operacije pod M11/M05 `school.attendance.record` lease-om. Permission nikada sam ne aktivira feature: M04 capability/entitlement i M28 pilot allowlist mogu dodatno da odbiju.

## M17 — privatnost i saglasnosti

| Permission key | Risk | OWNER | MANAGER | LIMITED_ADMIN | STAFF | GUARDIAN | PAYER | Scope, guard i delegacija |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `privacy.purposes.view` | HIGH | A | A | — | — | — | — | School policy metadata; direct ka Limited samo uz privacy duty. |
| `privacy.purposes.manage` | CRITICAL | A | A | — | — | — | — | Draft only; ROLE_ONLY. |
| `privacy.purposes.publish` | CRITICAL | A | A | — | — | — | — | Step-up; ROLE_ONLY; exact M17 validation. |
| `privacy.notices.view` | HIGH | A | A | S | S | S | S | Samo notice namenjen actor/subject audience-u. |
| `privacy.notices.manage` | CRITICAL | A | A | — | — | — | — | Draft; ROLE_ONLY. |
| `privacy.notices.publish` | CRITICAL | A | A | — | — | — | — | Step-up; ROLE_ONLY. |
| `privacy.consents.view` | HIGH | A | A | S | S | S | — | Staff samo duty scope; guardian svoje/povezano dete. |
| `privacy.consents.manage` | CRITICAL | A | A | — | — | — | — | Definition draft; ROLE_ONLY. |
| `privacy.consents.publish` | CRITICAL | A | A | — | — | — | — | Step-up; ROLE_ONLY. |
| `privacy.consents.decide_self` | HIGH | S | S | S | S | S | S | Isključivo `ADULT_SELF`; bez direct grant-a u tuđe ime. |
| `privacy.consents.decide_child` | HIGH | — | — | — | — | S | — | Active M07 guardian authority + consent scope; ne school admin u ime guardian-a. |
| `privacy.consents.assist` | CRITICAL | A | A | — | — | — | — | Step-up, prisutan giver, reason; ROLE_ONLY; nikad bulk. |
| `privacy.requests.create_self` | HIGH | S | S | S | S | S | S | Samo actor Person; minimalni compliance allowance. |
| `privacy.requests.create_child` | HIGH | — | — | — | — | S | — | Active M07 guardian request scope. |
| `privacy.requests.view` | CRITICAL | S | S | S | S | S | S | Self/child requester ili explicit privacy duty; sadržaj drugih lica redigovan. |
| `privacy.requests.manage` | CRITICAL | A | A | — | — | — | — | Purpose/duty assignment; ROLE_ONLY. |
| `privacy.requests.decide` | CRITICAL | A | A | — | — | — | — | Step-up + zatvoren reason; ROLE_ONLY. |
| `privacy.retention.view` | HIGH | A | A | — | — | — | — | Policy metadata, ne sadržaj zadržanih zapisa. |
| `privacy.retention.manage` | CRITICAL | A | A | — | — | — | — | Draft; ROLE_ONLY. |
| `privacy.retention.publish` | CRITICAL | A | A | — | — | — | — | Step-up; ROLE_ONLY. |
| `privacy.legal_hold.view` | CRITICAL | A | A | — | — | — | — | Maskirana metadata; nema čitanja target sadržaja. |
| `privacy.legal_hold.manage` | CRITICAL | A | A | — | — | — | — | Request/release; step-up; ROLE_ONLY. |
| `privacy.legal_hold.approve` | CRITICAL | A | A | — | — | — | — | Drugi account, dual control; ROLE_ONLY. |
| `privacy.exports.download` | CRITICAL | S | S | S | S | S | S | Samo autorizovani request/subject i aktivna kratka download sesija; nema tenant export-a. |
| `privacy.audit.view` | CRITICAL | A | A | — | — | — | — | M17 audit allow-list, bez evidence/document sadržaja; ROLE_ONLY. |

## M18 — izveštaji

| Permission key | Risk | OWNER | MANAGER | LIMITED_ADMIN | INSTRUCTOR/SUBSTITUTE | GUARDIAN | PAYER | Scope, guard i delegacija |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `school.reports.overview.view` | HIGH | A | A | — | — | — | — | School aggregate; direct ka Limited. |
| `school.reports.membership.view` | HIGH | A | A | — | — | — | — | Child-derived suppression; direct ka Limited. |
| `school.reports.schedule.view` | HIGH | A | A | S | S | — | — | Limited/staff samo dodeljeni scope. |
| `school.reports.attendance.view` | HIGH | A | A | S | S | — | — | Dodeljena grupa/termin; nema school-wide child count za staff. |
| `school.reports.finance.view` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY; nikad PAYER school analytics. |
| `school.reports.communication.view` | HIGH | A | A | — | — | — | — | Agregat bez sadržaja/recipient liste; direct ka Limited. |
| `school.reports.events.view` | HIGH | A | A | S | S | — | — | Staff samo assigned event aggregate. |
| `school.reports.drilldown` | CRITICAL | A | A | S | S | — | — | Zahteva i permission osnovne metrike; owner subject resolver. |
| `school.reports.export` | CRITICAL | A | A | — | — | — | — | Step-up, encrypted short-lived export; ROLE_ONLY. |
| `school.reports.manage` | CRITICAL | A | A | — | — | — | — | Shared view/definition school config; ROLE_ONLY. |

## M19 — shell i pretraga

| Permission key | Domain | Risk | Default binding | Scope i guard |
|---|---|---|---|---|
| `school.search.use` | SCHOOL | HIGH | OWNER, MANAGER, LIMITED_ADMIN, INSTRUCTOR, SUBSTITUTE | Tenant + efektivni permission-i owner resursa + assignment/subject filter pre matching/count-a. GUARDIAN koristi samo M28 subject endpoint, ne globalni school search. |
| `school.search.exact_contact` | SCHOOL | CRITICAL | OWNER, MANAGER | Step-up/rate limit/audit; exact HMAC lookup; sirov kontakt nije suggestion. ROLE_ONLY. |
| `platform.shell.configuration.publish` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Objavljuje navigation/composition manifest; unknown route/permission/capability blokira publish. |
| `platform.search.projections.rebuild` | PLATFORM | HIGH | PLATFORM_OPERATIONS_ADMIN | Operativni rebuild bez pristupa plaintext rezultatima; reason/audit/fencing. |

Self preference, install i deep-link capture/consume nisu široke business dozvole: zahtevaju validan M01 account/session i striktni self/tenant/target guard. Ne mogu biti delegirani.

## M20 — onboarding i import

| Permission key | Risk | OWNER | MANAGER | LIMITED_ADMIN | Ostale role | Scope, guard i delegacija |
|---|---|---:|---:|---:|---:|---|
| `school.onboarding.view` | HIGH | A | A | S | — | Current school; direct ka Limited. |
| `school.onboarding.manage` | HIGH | A | A | — | — | Koraci/status, bez owner-table write-a; direct ka Limited. |
| `school.onboarding.review` | CRITICAL | A | A | — | — | Readiness review; ROLE_ONLY. |
| `school.import.manage` | CRITICAL | A | A | — | — | Upload/map/validate/resolve/reject; direct ka Limited samo za batch ≤500 uz explicit grant. |
| `school.import.execute` | CRITICAL | A | A | — | — | Confirm/execute; step-up za >500; ROLE_ONLY. |
| `school.import.recovery` | CRITICAL | A | — | — | — | Controlled recovery, reason+step-up+owner versions; OWNER ROLE_ONLY. |

## M21 — platformska pouzdanost

| Permission key | Domain | Risk | Default binding | Scope i guard |
|---|---|---|---|---|
| `platform.operations.view` | PLATFORM | HIGH | PLATFORM_OPERATIONS_ADMIN, PLATFORM_SECURITY_ADMIN | Tehnički health bez tenant business vrednosti/PII. |
| `platform.jobs.manage` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | Published job definition, reason, bounded tenant scope; nema menjanja business zapisa. |
| `platform.deadletters.replay` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Step-up, dual control i owner replay policy. |
| `platform.audit.verify` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Verifikacija hash/segment kompletnosti; nema bulk tenant sadržaja. |
| `platform.backup.manage` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | Backup metadata/verify, bez plaintext podataka. |
| `platform.restore.execute` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Step-up + dual control; isključivo izolovano okruženje. |
| `platform.release.manage` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | Immutable artifact/evidence; deploy/rollback compatibility. |
| `school.audit.view` | SCHOOL | CRITICAL | OWNER, MANAGER | Samo tenant allow-list događaji; MANAGER bez support/security restricted payload-a. |
| `school.audit.export` | SCHOOL | CRITICAL | OWNER | Step-up, encrypted/TTL/single-use; ROLE_ONLY. |

Support role nema nijedan default red iz ovog registra. Standardni SupportAccessGrant može dati samo M05 eksplicitno dozvoljenu, maskiranu dijagnostičku akciju; ne dobija privacy decision, report export, import execute/recovery, audit export, backup, restore ili release pristup. Break-glass ne preskače owner invariant, child/subject guard niti immutable audit.

## M28 — mySOKOLA Basic

Svih pet M28 permission-a su offline `DENY`. Portal permission ne zamenjuje M04 entitlement, ACTIVE M28 pilot enrollment, runtime feature flag, M07 guardian/payer basis niti vlasnički permission za konkretnu sekciju ili akciju.

| Permission key | Domain | Risk | Default binding | Scope, guard i delegacija |
|---|---|---|---|---|
| `portal.mysokola.access` | SCHOOL | HIGH | GUARDIAN, PAYER | Otvara samo single-school portal shell; zahteva aktuelni M07 guardian ili payer basis. Nema direct grant-a, child/Payer scope se ne ujedinjuju. |
| `portal.mysokola.preferences.manage_self` | SCHOOL | LOW | GUARDIAN, PAYER | Isključivo preference aktuelnog account-a u aktivnoj školi; nema direct grant-a niti pristupa owner podacima. |
| `school.portal.pilot.request` | SCHOOL | HIGH | OWNER | Samo request; ne aktivira entitlement, feature flag ili enrollment. ROLE_ONLY, reason obavezan. |
| `platform.portal.pilot.decide` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | Activate/reject/reactivate uz step-up, ticket, current M04 entitlement i exact expected version; ne daje school business pristup. |
| `platform.portal.pilot.security_manage` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Suspend/revoke uz step-up, security reason, ticket i immediate authorization invalidation; ne daje school business pristup. |

Owner sekcija/komanda iz M28 zahteva i svoj originalni M01/M03/M06–M17 permission i resource/subject guard. Na primer, `portal.mysokola.access` + GUARDIAN basis bez `school.documents.view` ne daje document metadata, a PAYER basis + `finance.view` ne daje child overview. Support, Organization pripadnost, feature flag ili pilot status nemaju nijedan default M28 binding.

## Validacija policy revizije

Publish nove `AuthorizationPolicyRevision` mora odbiti:

1. ključ koji se pojavljuje više puta ili nema tačan authorization domain;
2. binding na reserved/unknown role ili wildcard;
3. CHILD/FINANCIAL/PRIVACY permission bez subject/purpose guarda;
4. offline vrednost različitu od ovog ugovora;
5. direct delegaciju širu od poslednje kolone;
6. route/command iz M17–M21/M28 bez registrovanog ključa ili internal/self ugovora;
7. permission koji sam aktivira entitlement/feature flag;
8. Support default binding;
9. M28 portal binding koji nema obavezan M04 entitlement + pilot + feature + M07 basis i owner-permission composition guard.
