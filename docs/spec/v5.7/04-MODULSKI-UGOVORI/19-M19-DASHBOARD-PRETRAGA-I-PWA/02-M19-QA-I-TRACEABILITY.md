---
modul-id: M19
tip: qa-traceability
status: SPEC_CANDIDATE
revizija: "1.7"
datum: 2026-09-15
obavezni-scenariji: 132
---

# M19 — QA, seed i traceability

## 1. Deterministički seed

Clock=`2026-11-02T09:00:00Z`. School A/B imaju iste nazive grupa/lokacija i različite UUID-eve. Account U1: MANAGER+INSTRUCTOR u A, GUARDIAN u B; U2 instructor samo G1; U3 finance; U4 opozvan guardian. Search sadrži latinicu/ćirilicu/đ-dj, 120 dozvoljenih i skrivene B rezultate. Browser fixture ima dva taba, stale responses, service-worker v1/v2, M11 pending/conflict queue, quota/purge failure i slow-4G/mid-range profile. Nema realnih PII.

## 2. Scenariji

| ID | Scenario | Očekivanje |
|---|---|---|
| M19-QA-001 | Validan bootstrap A. | Jedan hashed envelope, A context/version, samo dozvoljena navigacija. |
| M19-QA-002 | Bootstrap bez sesije. | 401; nema privatnog shell-a/cache-a. |
| M19-QA-003 | School deaktivirana između session i query. | Fail-closed; privatni UI zatvoren. |
| M19-QA-004 | Manifest s unknown permission. | Publish 422. |
| M19-QA-005 | Manifest edit posle publish. | Odbijeno; nova verzija. |
| M19-QA-006 | Capability OFF. | Item/widget nije ponuđen; endpoint ipak guardovan. |
| M19-QA-007 | Sakriven item, direktna ruta. | Server 403/404 prema visibility ugovoru. |
| M19-QA-008 | Widget owner query failuje. | Izolovan safe error, drugi widget-i rade. |
| M19-QA-009 | Session guard failuje. | Ceo privatni shell zamrznut/purge. |
| M19-QA-010 | Nedostaje obavezna M18 finance source barijera. | Finance widget je UNAVAILABLE; nema headline ili partial iznosa. |
| M19-QA-011 | U1 bira INSTRUCTOR workspace uz MANAGER role. | Instructor-first UI; M05 unija nepromenjena. |
| M19-QA-012 | Workspace preference više nije dostupna. | 409/bezbedni fallback na izbor. |
| M19-QA-013 | Global Home U1. | Samo škole/workspace-i; bez child/count/finance cross-school. |
| M19-QA-014 | Jedna škola/jedan workspace. | Izbor se preskače bez slabljenja guard-a. |
| M19-QA-015 | Organization membership bez School prava. | School nije ponuđen. |
| M19-QA-016 | Switch A→B uspe. | Nova context_version; A requests/subscriptions/cache očišćeni pre B rendera. |
| M19-QA-017 | A response stigne posle switch-a. | Odbacen; nema jednog frame-a A podatka u B. |
| M19-QA-018 | Dvostruki switch click isti key. | Jedan rezultat/receipt. |
| M19-QA-019 | Isti key, drugi target school. | 409; prvi context ostaje. |
| M19-QA-020 | Dirty domain forma pri switch-u. | Eksplicitna confirm/cancel; nema tihog gubitka. |
| M19-QA-021 | Dva taba koriste staru/novu context_version. | Svaki request revalidira; stale tab ne čita privatne podatke. |
| M19-QA-022 | Browser Back posle switch-a. | Route ponovo resolve; A cache nije vraćen. |
| M19-QA-023 | Parallel permission revoke tokom bootstrap-a. | Response version mismatch; privatni render odbijen. |
| M19-QA-024 | Preference optimistic update failuje. | UI rollback + safe error; nema domain posledice. |
| M19-QA-025 | Meta+K van inputa. | Command bar se otvara, focus u search. |
| M19-QA-026 | Ctrl+K. | Isti tok na podržanoj platformi. |
| M19-QA-027 | Meta/Ctrl+K unutar textarea. | Ne presreće unos. |
| M19-QA-028 | Mobilna Search akcija. | Otvara isti autorizovani ugovor. |
| M19-QA-029 | Query dužine 0/1. | Nema server search-a; hint. |
| M19-QA-030 | Query >80 scalars ili >8 tokena. | 422. |
| M19-QA-031 | NFKC/whitespace/case varijante. | Isti canonical query/hash. |
| M19-QA-032 | `Đorđe`, `Djordje`, `Ђорђе`. | Definisana transliteracija matchuje; original display. |
| M19-QA-033 | Exact prefix vs fuzzy. | Exact prvi; stable UUID tie-break. |
| M19-QA-034 | Dva identična labela. | Determinističan type/display/UUID red. |
| M19-QA-035 | Brzo kucanje tri query-ja. | Prethodni abort; samo poslednji sequence render. |
| M19-QA-036 | Stari search response kasni. | Odbačen po sequence+context. |
| M19-QA-037 | 300 pogodaka. | 20 response, max50 command-bar; nema truncation laži. |
| M19-QA-038 | Cursor promenjen query. | Invalid/safe error. |
| M19-QA-039 | Cursor iz B korišćen u A. | Safe 404; nema result/count. |
| M19-QA-040 | A/B isti naziv. | Samo A projection ulazi u matching. |
| M19-QA-041 | U2 G1 traži G2 participant-a. | Nema result/suggestion/count/timing oracle-a. |
| M19-QA-042 | U2 traži dozvoljenog G1 participant-a. | Minimalni child label/context. |
| M19-QA-043 | Child search result payload. | Nema DOB/avatar/guardian/health/balance. |
| M19-QA-044 | Email query bez exact-contact permission. | Nema lookup/existence indikatora. |
| M19-QA-045 | Admin exact-contact search. | Tenant HMAC lookup koristi registry key verziju, audit use; display je maskovan. |
| M19-QA-046 | Search query u access/app logu. | Redacted/odsutan. |
| M19-QA-047 | Search telemetry s entity ID-em. | Test pada/redaction. |
| M19-QA-048 | Search index s finance/document/health fieldom. | Schema test pada. |
| M19-QA-049 | Duplicate source event. | Jedan SearchDocument. |
| M19-QA-050 | Source v3 pa v2. | v2 ignored; v3 ostaje. |
| M19-QA-051 | Tombstone pa stari update. | Ne oživljava. |
| M19-QA-052 | Validna novija reactivation. | ACTIVE na novoj source verziji. |
| M19-QA-053 | Rebuild dva worker-a. | Samo najnoviji fencing publish. |
| M19-QA-054 | Search projection FAILED. | 503; nema fallback global query-ja. |
| M19-QA-055 | Rate limit A actor. | 429 samo njegov scope; B nije pogođen. |
| M19-QA-056 | Command bar destructive quick action. | Ne postoji; samo navigacija. |
| M19-QA-057 | Deep link bez login-a. | PRE_AUTH_PENDING s nonce hash-om; nema session/account niti target resolution/existence indikatora. |
| M19-QA-058 | Valid deep link posle login/context. | Atomski bind u AUTH_BOUND_PENDING, pa puni guard i jednokratna dozvoljena ruta. |
| M19-QA-059 | Cross-tenant target ID. | Neutralan safe fallback/404. |
| M19-QA-060 | Guardian revoke pre resolve-a. | Safe fallback; nema child labela. |
| M19-QA-061 | Intent consume replay. | Isti idempotentni retry vraća isti receipt; novi consume pokušaj dobija 410; nema drugog resolve-a. |
| M19-QA-062 PAR | Intent je tačno na `expires_at`; cleanup se trka sa bind/consume zahtevom. | Request-time provera više ne dozvoljava bind/resolve; jedan CAS prelaz daje EXPIRED, target ciphertext/hint/nonce i key-version parovi su null, retry job-a je bez dodatnog efekta. |
| M19-QA-063 | Bind/consume iz druge sesije ili sa drugim nonce-om. | Safe REJECTED/409; target se ne proverava niti otkriva. |
| M19-QA-064 | `javascript:`/external redirect/path traversal. | 422; allow-list route key. |
| M19-QA-065 | Route param mass assignment. | Unknown param odbačen; nema guard bypass-a. |
| M19-QA-066 | Back/forward ka hidden target. | Ponovni guard; safe fallback. |
| M19-QA-067 | Service worker install. | Samo versioned public shell asseti. |
| M19-QA-068 | Auth callback/invite URL fetch. | Nikad cache. |
| M19-QA-069 | Document/download/signed URL. | Nikad cache. |
| M19-QA-070 | Finance/consent/search response. | `no-store`, nije IndexedDB/Cache Storage. |
| M19-QA-071 | Allowed dashboard aggregate. | Namespace s installation/account/school/context/auth/schema + hard TTL. |
| M19-QA-072 | Generic URL cache key za private API. | Security test pada. |
| M19-QA-073 | Logout online. | Requests/realtime stop, cache/DB purge, installation rotation/revoke. |
| M19-QA-074 | Lokalno poznat session/cache hard expiry dok je uređaj offline. | Privatni prikaz se zaključava bez čekanja servera i lokalni privatni sadržaj se purge-uje. |
| M19-QA-075 | Account switch. | Stari namespace purge pre novog rendera. |
| M19-QA-076 | Online access revoke signal. | Immediate freeze/purge; svaki sledeći request fail-closed. |
| M19-QA-077 | Purge browser/quota failure. | Novi privatni shell blokiran do potvrđenog purge-a. |
| M19-QA-078 | Cache schema mismatch. | Idempotent migration ili purge; ne čita staro. |
| M19-QA-079 | Inspect IndexedDB. | Samo M11 allow-list; nema drugih privatnih domena/tokena. |
| M19-QA-080 | Offline M11 draft. | PENDING_SYNC prema M11, ne final success. |
| M19-QA-081 | Offline finance write. | Deny; nema queue-a/„plaćeno”. |
| M19-QA-082 | Offline document/consent/event registration. | Deny; nema queue-a/final statusa. |
| M19-QA-083 | Offline RBAC/guardian write. | Deny. |
| M19-QA-084 | M11 sync auth/revoke conflict. | SYNC_FAILED; no overwrite; purge po ugovoru. |
| M19-QA-085 | App update bez pending drafta. | Aktivira kontrolisano; reload state bez PII leak-a. |
| M19-QA-086 | Update dok M11 PENDING_SYNC. | Blokiran do sync/resolve/kompatibilne migracije. |
| M19-QA-087 | Critical update + kompatibilna queue migration. | Idempotent migration, digest očuvan, zatim activate. |
| M19-QA-088 | Critical update bez kompatibilne migracije. | Shell blokira i traži online resolution; queue se ne briše tiho. |
| M19-QA-089 | Push permission pri prvom renderu. | Ne traži se. |
| M19-QA-090 | PWA nije instalirana. | Browser web ima iste core funkcije. |
| M19-QA-091 | Keyboard kroz shell/search/results. | Logičan focus, Escape zatvara/vrati focus. |
| M19-QA-092 | Screen reader sync/error. | Live status bez ponavljanja/PII. |
| M19-QA-093 | Reduced motion. | Animacije nisu obavezne za razumevanje. |
| M19-QA-094 | Primarne mobile akcije. | Target ≥44×44 CSS px; nema preklapanja 320px width. |
| M19-QA-095 | Coach Home, jedan današnji termin, svi PRESENT. | Otvori+potvrdi = 2; server receipt je kraj; confirm nije izostavljen. |
| M19-QA-096 | Raspored/finansije/komunikacija/događaj sa tačno definisanim standardnim seed-om. | Svaki prati master §3.1 i završava u ≤3; svaki dodatni obavezni izbor je evidentiran kao izuzetak, ne sakriven. |
| M19-QA-097 | Slow-4G/mid-range lab budget. | Warm≤2.5s, cold≤4s, search visible≤500ms. |
| M19-QA-098 | Field RUM p75. | LCP≤2.5s, INP≤200ms, CLS≤0.1, bez PII telemetry-ja. |
| M19-QA-099 | Bundle CI i H0 route-catalog contract. | Initial JS≤250KiB gzip, CSS≤60KiB, route≤180KiB; svih 42 kanonskih UI ID/`surface_key` vrednosti imaju bar jednu allow-listed rutu, svaka ruta pripada tačno jednoj površini i nema siročeta ili dodatne neodobrene površine. |
| M19-QA-100 | Brownfield migration/rollback. | Nema localStorage token/private generic cache; M11 queue očuvan. |
| M19-QA-101 | Pre-auth intent DB/crypto constraint sa validnim, nepostojećim i tuđim school hint-om. | PRE_AUTH zahteva nonce hash i zabranjuje account/session; target ciphertext i school hint su svaki null/non-null zajedno sa svojom key verzijom. Capture koristi samo platform deep-link key, daje ekvivalentan odgovor i ne bira tenant key/ne potvrđuje School; tek posle bind-a poredi hint sa eligible M03 context-om. |
| M19-QA-102 | Auth-bound intent DB constraint. | AUTHENTICATED_SESSION zahteva account+session i zabranjuje nonce; nevažeća kombinacija pada. |
| M19-QA-103 | Dva paralelna bind zahteva istog pre-auth intenta. | Jedan CAS prelaz uspeva; drugi nema novu vezu niti target oracle. |
| M19-QA-104 | Isti bind Idempotency-Key sa drugim session/request hash-om. | 409 bez promene prvog binding-a. |
| M19-QA-105 | Postojeći, nepostojeći i cross-tenant target pre login-a. | Potpuno isti status/body klasa i tolerancija vremena; nema resolve-a pre auth-a. |
| M19-QA-106 | Uređaj ostane offline duže od 15 min nakon poslednje reautorizacije, a pristup je server-side opozvan. | Nije moguć remote wipe, ali privatni aggregate se ne otvara posle lokalnog hard-expiry-ja; reconnect purge prethodi renderu. |
| M19-QA-107 | Remote revoke bez signala, uređaj reconnectuje pre isteka cache-a. | Prvi revalidation failuje, shell freeze/purge; cache se ne prikaže. |
| M19-QA-108 | Tri-click test pokrenut bez aktivne škole. | Scenario se ne proglašava prolaznim; context izbor se meri odvojeno i dokumentuje kao preduslov. |
| M19-QA-109 | `SOKOLA-NFR-PWA-V1` na drugom datasetu ili bez raw percentila. | Dokaz je nevažeći; budžet nije označen kao dostignut. |
| M19-QA-110 | Manifest item koristi spoljni/protocol-relative URL ili internu rutu koja nije u versioned route allow-listi. | Publish 422 `SHELL_MANIFEST_INVALID`; nema otvorenog redirect-a ni delimičnog publish-a, a prethodna PUBLISHED manifest verzija ostaje izvršiva. |
| M19-QA-111 | Manifest DRAFT sa item-ima. | Nije izvršiv; publish atomarno validira sve item ključeve/rute/permission-e i zamrzava celu verziju. |
| M19-QA-112 | Dva item-a imaju isti key ili order. | Publish 409/422; nema parcijalno objavljenog manifesta. |
| M19-QA-113 | Composition widget referencira unknown query/capability. | Publish 422; prethodna PUBLISHED verzija ostaje aktivna. |
| M19-QA-114 | Source delete/tombstone participant-a. | Current SearchDocument label/token/contact/key-version polja i svi scope binding redovi obrisani su u istom commit-u sa APPLIED receipt-om. |
| M19-QA-115 | Search nad tombstone tokenom neposredno posle commit-a. | Nema rezultata, count-a, suggestion-a ni timing indikatora. |
| M19-QA-116 | Stari source event stigne posle tombstone-a. | IGNORED_STALE receipt; PII i ACTIVE status se ne vraćaju. |
| M19-QA-117 | Validna source reaktivacija. | Samo strogo veća source version + novi receipt vraća ACTIVE minimalnu projekciju. |
| M19-QA-118 | Isti source event/version sa drugim hash-em. | Quarantine/integrity incident; current index se ne menja. |
| M19-QA-119 | Search rebuild lease istekne, stari worker pokušava publish. | Fencing odbija promenu; novi checkpoint ostaje autoritet. |
| M19-QA-120 | PRE_AUTH_PENDING intent ima account/session/bound_at. | DB CHECK odbija; postojanje targeta se ne proverava. |
| M19-QA-121 | BindAfterLogin uspe. | Nonce se atomarno uklanja, session/account/bound_at postavljaju; drugi browser/nonce ne može bindovati. |
| M19-QA-122 | REJECTED/CONSUMED intent sa kontradiktornim actor-time poljima. | DB CHECK odbija kombinaciju; terminalno stanje se ne oživljava. |
| M19-QA-123 PAR | ACTIVE installation dostigne tačno 90 dana od `last_seen_at`; cleanup se trka sa kasnim heartbeat-om, a zatim se isti job ponovi. | Privatni shell je request-time odbijen; CAS daje ili ranije validno committed heartbeat produženje ili EXPIRED sa tačno `expired_at`, nikad oba. Retry je no-op, terminalni red se ne reaktivira i novi pristup dobija nov random public ID. |
| M19-QA-124 | ShellPreference arhivirana pri school/account disposition-u. | ARCHIVED+archived_at; nema read/update ni prenosa preference u drugi tenant. |
| M19-QA-125 | `ShellCommandReceipt` je `SUCCEEDED` bez `result_ref/response_hash`, ili `REJECTED` sa rezultatom. | DB conditional CHECK odbija oba reda; uspešan replay uvek ima dokaziv rezultat, a odbijeni receipt ne izlaže niti glumi resurs. |
| M19-QA-126 | Dva anonimna browser zahteva koriste isti pre-auth nonce/idempotency key. | Isti nenull BROWSER actor scope i GLOBAL tenant scope daju jedan intent/receipt; promenjen payload je 409, bez target oracle-a. |
| M19-QA-127 | Dva system worker-a sa null account/school pokušaju isti config command receipt. | Nenull SYSTEM/GLOBAL ključevi daju tačno jedan receipt/efekat. |
| M19-QA-128 | Manifest/composition expression sadrži unknown/wildcard/NOT/script, dubinu 5 ili 33 node-a; capability je null/unknown. | Publish 422 bez parcijalne konfiguracije; validan canonical AST ima stabilan hash, ali endpoint i dalje ponavlja M05/M04 guard. |
| M19-QA-129 PAR | Dve PUBLISHED manifest ili composition verzije istog key/workspace-a nastaju istovremeno. | Tačno jedna nova PUBLISHED; prethodna se atomski RETIRED, loser dobija 409 i nikad nema dve current konfiguracije. |
| M19-QA-130 | Matrica `Ђорђе`, `Đorđe`, `Djordje`, `Љиљана`, `LJILJANA`, token 3/4/8 znakova i fuzzy greške. | Kanonska tri token sloja i tačan fuzzy prag daju determinističan redosled; originalni display ostaje; nijedan match ne služi identity linking-u. |
| M19-QA-131 | Cache allow-list pokuša child label/ID, finance, message/document/consent/event-registration ili search response. | Build/response cache policy odbija svako privatno polje; dozvoljeni aggregate/status/navigation hard-expire ≤15 min. |
| M19-QA-132 PAR | Search key prolazi STABLE→PREPARING→DUAL_READ→CUTOVER→STABLE dok isti source dobija noviju verziju; posebno se testiraju abort pre cutover-a, direktan nedozvoljen prelaz, cross-tenant scope binding i missing key. | Conditional key-state polja, CAS/backfill i source projection ostavljaju samo najnoviju owner verziju; oba read ključa daju isti dozvoljeni rezultat do verifikovanog CUTOVER-a; abort zahteva reverse reconciliation, posle CUTOVER-a nema tajnog rollback-a; cross-tenant binding je QUARANTINED, a missing key vraća 503 bez plaintext/global fallback-a. Prolaz zahteva 132/132, 0 failed/skipped/flaky. |

## 3. Obavezni suite i traceability

Suite: `m19-shell`, `m19-context-race`, `m19-search-ranking`, `m19-tenant-negative`, `m19-subject-negative`, `m19-deeplink`, `m19-pwa-cache`, `m19-offline-policy`, `m19-update-migration`, `m19-accessibility`, `m19-security`, `m19-performance`, `m19-observability`, `m19-brownfield`.

QA 001–024 → master §§2–3; 025–056 → §§2.4–2.5,3; 057–066 i 101–105 → §2.6/§§3–7; 067–090 i 106–107 → §§2.7–2.10,3; 091–099 i 108–109 → §§3,7; 100 → §8; 110–124 → §§2.2–2.10,5–8; 125–127 → §2.8; 128–132 → permission AST, single-current config, search normalizacija, cache privacy, typed scope i key rotation. Acceptance pada na jednom skipped/flaky testu, jednom frame-u cross-context podatka, search count/timing leak-u, tombstone PII ostatku, prikazu posle lokalnog hard-expiry-ja, nullable-scope receipt duplikatu, drugom offline write-u ili nedokazanom performance budžetu.
