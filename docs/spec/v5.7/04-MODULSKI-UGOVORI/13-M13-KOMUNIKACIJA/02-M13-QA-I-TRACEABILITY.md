---
tip: qa-traceability
modul-id: M13
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
obavezni-scenariji: 68
---

# M13 — QA i traceability

Svaki scenario je determinističan automatizovani acceptance ugovor; koristi škole A/B, actor-e po ulozi, dva guardian basis-a iste osobe, aktivan/opozvan link, M15 verzije i controllable delivery provider.

| QA ID | Scenario | Očekivano |
|---|---|---|
| M13-QA-001 | OWNER kreira validan draft. | 201 DRAFT. |
| M13-QA-002 | Prazan/blank subject. | 422; nema reda. |
| M13-QA-003 | Body 10001 znak. | 422. |
| M13-QA-004 | Body sadrži script/HTML. | Odbijeno ili bezbedno plain-text; nema izvršenja. |
| M13-QA-005 | Dva drafta istog autora. | Oba dozvoljena, različiti ID-evi. |
| M13-QA-006 | Update sa stale version. | 409; sadržaj prvog commit-a ostaje. |
| M13-QA-007 | Audience ALL_ACTIVE_GUARDIANS sa scope_id. | 422. |
| M13-QA-008 | GROUP_GUARDIANS bez scope_id. | 422. |
| M13-QA-009 | Group iz škole B u A. | Safe 404, bez count-a. |
| M13-QA-010 | INSTRUCTOR preview nedodeljene grupe. | Safe 404/deny. |
| M13-QA-011 | Preview validne dodeljene grupe. | Tačan recipient hash/count. |
| M13-QA-012 | Nula primalaca. | Preview upozorenje; publish 422. |
| M13-QA-013 | Ista osoba guardian dvoje target dece. | Jedan recipient delivery, dva basis snapshot-a. |
| M13-QA-014 | Neaktivan guardian link. | Nije primalac. |
| M13-QA-015 | Staff i guardian osnova istog account-a. | Jedan delivery po kanalu; oba basis-a. |
| M13-QA-016 | Preview stariji od 15 min. | 409 expired. |
| M13-QA-017 | Draft promenjen posle preview-a. | 409 stale. |
| M13-QA-018 | Audience promenjen posle preview-a. | 409 stale. |
| M13-QA-019 | Guardian opozvan posle preview-a. | 409 stale. |
| M13-QA-020 | Guardian dodat posle preview-a. | 409 stale. |
| M13-QA-021 | M15 dokument AVAILABLE svim primaocima. | Publish dozvoljen sa immutable version ID-em. |
| M13-QA-022 | Dokument nije dostupan jednom primaocu. | 409, ništa objavljeno. |
| M13-QA-023 | Dokument verzija promenjena. | 409; novi preview. |
| M13-QA-024 | REJECTED/WITHDRAWN dokument verzija. | 409. |
| M13-QA-025 | Dokument pokušava email attachment. | Nema attachment-a; build/test pada ako postoji. |
| M13-QA-026 | Validan publish. | Business+snapshots+deliveries+audit+outbox+receipt jedan commit. |
| M13-QA-027 | DB fail usred snapshot-a. | Potpun rollback. |
| M13-QA-028 | Dva taba različiti key, isti draft. | Tačno jedan publish. |
| M13-QA-029 | Retry isti key/payload. | Isti rezultat/ID. |
| M13-QA-030 | Isti key drugi body. | 409 key reused. |
| M13-QA-031 | Publish archived draft. | 409 already published/invalid state. |
| M13-QA-032 | Published body update. | Komanda ne postoji/405. |
| M13-QA-033 | Ispravka poruke. | Nova PublishedCommunication + acikličan link. |
| M13-QA-034 | Correction link cross-tenant. | FK/guard odbija. |
| M13-QA-035 | Correction ciklus. | 409. |
| M13-QA-036 | Withdraw sa expected version/reason. | WITHDRAWN + audit/outbox. |
| M13-QA-037 | Parallel withdraw. | Jedan commit, drugi equivalent/stale. |
| M13-QA-038 | Read sa aktivnim recipient basis-om. | Receipt upsert; read_count determinističan. |
| M13-QA-039 | Read retry isti key. | Bez lažnog duplog first_read. |
| M13-QA-040 | Guardian link opozvan pre read-a. | Safe 404; snapshot ne daje pristup. |
| M13-QA-041 | PAYER bez guardian/staff basis-a. | Nema komunikacioni pristup. |
| M13-QA-042 | Cross-tenant communication ID. | Safe 404. |
| M13-QA-043 | Email payload inspekcija. | Nema subject/body/child/finance/attendance/attachment. |
| M13-QA-044 | `communication.delivery_dispatch` claim-uje EMAIL red, provider transientno failuje. | QUEUED/RETRY_SCHEDULED→SUBMITTING sa lease/fence/attempt+1, zatim RETRY_SCHEDULED sa backoff+jitter; IN_APP ostaje DELIVERED. |
| M13-QA-045 | Osmi provider pokušaj ili 48h prozor je dostignut; kontrolni M21 execution retry ponavlja infrastrukturni korak. | PERMANENTLY_FAILED bez devetog provider pokušaja; M21 retry ne resetuje business count/prozor. |
| M13-QA-046 | Permanent bounce. | Bez retry-ja. |
| M13-QA-047 | Duplicate provider callback. | Jedna tranzicija. |
| M13-QA-048 | Email fail, in-app success. | Nezavisni statusi. |
| M13-QA-049 | Provider accepted bez delivered dokaza; IN_APP red je nastao u publish commit-u. | EMAIL je DISPATCHED, ne DELIVERED; IN_APP je DELIVERED bez spoljnog provider poziva. |
| M13-QA-050 | Dva workera uzmu isti EMAIL delivery, prvom istekne lease i kasno vrati success. | Jedan važeći fence/status commit; stale worker nema DB side effect. Stabilan provider ključ sprečava dupli submission gde provider podržava dedupe. |
| M13-QA-051 | Offline Create/Publish/Read write. | DENY; nema durable lokalnog child podatka. |
| M13-QA-052 | Logout/session expiry/switch. | Memorijski draft i sensitive cache očišćeni. |
| M13-QA-053 | School SUSPENDED pre publish-a. | Fail closed; nema partial write-a. |
| M13-QA-054 | M07/M09/M15 port unavailable. | 503; ne koristi stale guess. |
| M13-QA-055 | Preview rate >30/min. | 429 bez PII. |
| M13-QA-056 | Publish >5000 recipients. | 422 limit; nema parcijalne publike. |
| M13-QA-057 | List pagination 101. | Max100/cursor stabilan. |
| M13-QA-058 | Log/audit scan. | Nema body, subject, email, child imena/raw ID-a u metric labels. |
| M13-QA-059 | Permission matrix. | Owner/Manager; Limited/Instructor samo eksplicitni scope; Guardian read-only subject; Payer none. |
| M13-QA-060 | Negative dependency scan. | Nema automatskog triggera, M14 call-a, SMS/Viber/WhatsApp ni sistemske notifikacije u M13. |
| M13-QA-061 | Draft neaktivan tačno 83 dana. | Tačno jedan redaktovan warning outbox događaj; retry ne duplira događaj. |
| M13-QA-062 | Draft neaktivan 89d23h59m59s. | Nema purge-a. |
| M13-QA-063 | Draft neaktivan tačno 90 dana bez hold-a. | Draft+audience obrisani; jedan content-free disposition, audit, outbox i receipt u istom commit-u. |
| M13-QA-064 PAR | Retention worker i UpdateDraft se trkaju. | Ako update commit prvi: nema purge-a i rok resetovan; ako purge prvi: update dobija safe not-found/invalid state; nikad izgubljena uspešna izmena. |
| M13-QA-065 | Precizan ACTIVE M17 legal hold na eligible draftu. | Nema purge-a ni content leak-a; posle release-a sledeći run purge-uje jednom. |
| M13-QA-066 | Publish-source draft je purge-ovan. | PublishedCommunication/snapshot/delivery ostaju immutable i dostupni po svojim guardovima. |
| M13-QA-067 | Retention failure između tombstone-a i delete-a. | Potpun rollback; retry daje jedan disposition i jedan purge, bez orphan stanja. |
| M13-QA-068 PAR | Dva taba dodaju isti široki `ALL_ACTIVE_GUARDIANS` ili `ACTIVE_STAFF` audience sa null scope ID-em. | Nenull izvedeni `scope_key` i unique constraint daju tačno jedan selector; drugi zahtev je idempotentni rezultat ili 409 za različit payload. Acceptance zahteva 68/68 stvarno izvršenih testova bez failed/skipped/flaky. |

Seed koristi sintetičke osobe i `example.invalid`; nikad realne podatke dece. Obavezni suite: unit, property audience hash, DB FK/CAS, dva stvarno paralelna publish testa, two-tenant API, provider contract, offline/security i log-redaction.
