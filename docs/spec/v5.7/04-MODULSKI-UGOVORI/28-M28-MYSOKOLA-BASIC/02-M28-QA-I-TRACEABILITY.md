---
tip: qa-traceability
modul-id: M28
status: SPEC_CANDIDATE
revizija: "1.5"
datum: 2026-09-15
obavezni-scenariji: 124
---

# M28 — QA i traceability

## 1. Izvršni test profil i seed

Svaki scenario je automatizovani contract/integration/E2E test sa determinističkim clock-om, ID generatorom, outbox/inbox transportom i owner-port doubles ili stvarnim modulima. PASS zahteva tačan HTTP/error code, trajno stanje, audit/outbox/receipt rezultat i dokaz da response/log/telemetry ne sadrži zabranjen PII. Skipped, flaky, ručno „izgleda dobro” ili samo UI test nisu PASS.

Seed ima škole A/B/C, Organization O sa A/B, nepovezanu C, isti globalni account G koji je GUARDIAN za A-child-1/A-child-2, PAYER samo za A-family-1 i GUARDIAN u B; account P je samo PAYER u A; account O je OWNER A; account X je drugi guardian samo A-child-2; M28 entitlement ACTIVE za A/B, odsutan za C; pilot ACTIVE A, REQUESTED B, nema C; feature ON A/B, OFF C. M07 sadrži ACTIVE, SUSPENDED, REVOKED i vremenski buduće/istekle basis-e. M12 ima dve valute u odvojenim školama, delimičnu uplatu, kredit, source gap i IPS instrukciju. M15/M17 imaju ugovor, notice, foto/video consent i novu verziju. M16 ima free/fee/full event i poslednje mesto. Browser seed uključuje dve kartice, offline mode, service-worker update i spor odgovor stare škole.

## 2. Pilot, feature i entitlement — 001–010

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-001 | OWNER A šalje dva ista `RequestMySokolaPilot` zahteva sa istim key/hash. | Jedan REQUESTED enrollment/transition/receipt; oba odgovora identična. | §2.1, §2.1.1, §7.2 |
| M28-QA-002 | Isti key, drugačiji reason payload. | 409 `M28_IDEMPOTENCY_CONFLICT`; nema druge tranzicije. | §6, §7.2 |
| M28-QA-003 | MANAGER A traži pilot. | 403 `M28_FORBIDDEN`; nema reda/audit uspeha/outbox-a. | M05 registry, §5.1 |
| M28-QA-004 | Platform Operations aktivira REQUESTED uz entitlement, step-up, ticket i expected version. | ACTIVE; jedna append-only transition; auth/projection invalidation emitovan u istoj transakciji. | §2.1.1, §5.1 |
| M28-QA-005 | Aktivacija bez efektivnog `MYSOKOLA_BASIC`. | 403 `M28_ENTITLEMENT_REQUIRED`; REQUESTED ostaje neizmenjen. | §1, §5.1 |
| M28-QA-006 | Platform Security suspenduje ACTIVE; paralelni Home počinje posle commit-a. | SUSPENDED; novi Home 403 `M28_PILOT_NOT_ACTIVE`; nema stale prozora. | §3.22, §5.1 |
| M28-QA-007 | Operations pokuša suspend samo sa decide permission-om. | 403; security permission nije impliciran. | M05 M28 registry |
| M28-QA-008 | Expiry job i read-time guard vide `effective_until == database_now`. | Read odmah deny; job pravi tačno jednu SYSTEM_CLOCK EXPIRED transition sa null actorom. | §2.1.1, §5.1, M21 katalog |
| M28-QA-009 | Dva worker-a istovremeno aktiviraju isti REQUESTED expected version. | Jedan ACTIVE; drugi isti request dobija receipt ili različit request 409 version conflict; jedan transition_no. | §7.2, §7.4 |
| M28-QA-010 | REVOKED škola ponovo želi pilot. | Stari red je terminalan; novi request pravi novi enrollment, ne oživljava stari. | §5.1 |

## 3. Session, tenant i authorization — 011–020

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-011 | Bez M01 session poziv Home. | 401 `M28_UNAUTHENTICATED`; body/log bez school/child podataka. | §4, §6 |
| M28-QA-012 | Session postoji, aktivna škola nije izabrana. | 409 `M28_CONTEXT_REQUIRED`; samo neutralne school opcije kroz bootstrap. | §3.5, §7.1 |
| M28-QA-013 | Body school B uz server context A. | 409 `M28_CONTEXT_STALE`; B se ne čita. | §4 |
| M28-QA-014 | Resource ID postoji u B, request context A. | 404 `M28_NOT_FOUND_SAFE`, isti schema/cache/timing bucket kao nasumičan ID. | §4, §6 |
| M28-QA-015 | Account ima Organization vezu O, ali nema membership/basis u A. | A se ne pojavljuje u ListMyPortalSchools; organization nije grant. | §4 |
| M28-QA-016 | Portal permission postoji, owner document permission ne postoji. | Shell radi; Documents sekcija se potpuno izostavlja bez count/existence indikatora. | §3.4, M05 registry |
| M28-QA-017 | Unknown/retired permission key u policy reviziji. | Fail-closed 503 owner/authorization-safe stanje; nikakav wildcard fallback. | M05 registry, §3.3 |
| M28-QA-018 | Authorization version se promeni tokom Home build-a. | Pre serialization mismatch; projection INVALIDATED; nema starog payload-a. | §3.19, §7.4 |
| M28-QA-019 | Support grant pokriva dijagnostiku M28. | Maskirani tehnički status bez impersonation-a, child/finance/document/message sadržaja ili pravne akcije. | §4 |
| M28-QA-020 | Break-glass actor pokuša consent ili event registration u ime guardian-a. | Deny; break-glass ne stvara guardian/payer basis niti pravni autoritet. | §4, M05 registry |

## 4. Guardian, payer i child isolation — 021–030

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-021 | G lista decu u A. | Tačno A-child-1/A-child-2; nema B-child ili podataka drugog guardian-a. | §3.7 |
| M28-QA-022 | Payer-only P otvara Child Overview preko obligation child ref-a. | 404 safe; finance scope ostaje dostupan bez child profila. | §3.8 |
| M28-QA-023 | Guardian-only G bez PAYER assignment-a otvara finance scope. | Sekcija izostavljena/safe 404; GUARDIAN ne implicira PAYER. | §3.4, §3.8 |
| M28-QA-024 | G ima obe role, ali payer basis samo family-1. | Finance vraća samo family-1; guardian child set ne širi finansije. | §3.4, §3.8 |
| M28-QA-025 | M07 guardian link opozvan dok je Child Overview otvoren. | Sledeći request safe 404; signal freeze/purge; telemetry bez child ID/name. | §3.22, edge 3 |
| M28-QA-026 | Revoked link je u preference default-u. | ID se ne resolve-uje u label; preference se ignoriše, bira aktuelni link ili empty. | §2.2, edge 14 |
| M28-QA-027 | Dva guardians dele dete; G čita X kontakt. | Kontakt/guardian graph nije u response-u; safe 404 za direktan ref. | §2.6, §4 |
| M28-QA-028 | Guardian basis počinje u budućnosti/istekao je. | Nije efektivan prema database time-u; child nije u list/count-u. | §3.3, §4 |
| M28-QA-029 | Child premešten u drugu školu, stale composite FK pokušava projection. | DB/API odbija cross-school join; nema projection publish-a. | §2, §4 |
| M28-QA-030 | Isti account menja A→B. | B payload sadrži samo B basis; A response iz paralelne kartice se odbacuje po context_version. | §3.5–6, §7.4 |

## 5. Home i onboarding projekcije — 031–040

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-031 | Svi izvori sveži i guardovi prolaze. | Jedan FRESH current projection sa generation 1, encrypted payload/hash, expiry ≤5m. | §2.3 |
| M28-QA-032 | Obavezan M12 source ima gap. | Finance descriptor UNAVAILABLE i bez iznosa; ostale bezbedne sekcije rade. | §3.9, §3.24 |
| M28-QA-033 | M07/source version mismatch pre dekripcije. | Stari projection INVALIDATED i nije serialize-ovan; rebuild ili safe recovery. | §2.3, §3.19 |
| M28-QA-034 | Dva builder-a publish-uju istu tuple/generaciju. | Lease/fencing + unique daju jednog current; loser ne može overwrite. | §2.3, §7.4 |
| M28-QA-035 | Rebuild posle STALE. | Stari current atomarno INVALIDATED; generation+1 postaje FRESH/UNAVAILABLE. | §5.2 |
| M28-QA-036 | Build je UNAVAILABLE. | `payload_ciphertext/hash` null, `missing_source_codes` non-empty i invalidation lista prazna; nema placeholder nule. | §2.3 |
| M28-QA-037 | Section nije autorizovan. | Descriptor nije `FORBIDDEN`; sekcija je potpuno izostavljena pre count-a. | §7.1 |
| M28-QA-038 | Nova mandatory document/notice verzija. | Onboarding source hash se menja i status ACTION_REQUIRED prema M15/M17 applicability. | §2.4, §3.14 |
| M28-QA-039 | Optional photo/video consent DECLINED. | Task je resolved, ne blokira portal; owner processing deny ostaje. | §3.13 |
| M28-QA-040 | Task owner source nije dokaziv. | Onboarding BLOCKED sa safe code/route, nikad lažno COMPLETE. | §2.4, §3.24 |

## 6. Raspored, prisustvo i komunikacija — 041–050

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-041 | Guardian čita raspored za 62 dana. | Dozvoljen child-scoped rezultat u school IANA zoni sa UTC instants. | §7.1 |
| M28-QA-042 | Period je 63 dana ili inverted. | 422 `M28_VALIDATION_FAILED`; nema širokog query-ja. | §7.1 |
| M28-QA-043 | DST gap/fold termin. | Prikaz prati M10 local-intent/offset ugovor; nema duplog ili nestalog occurrence ID-a. | owner M10, §2.6 |
| M28-QA-044 | Guardian pokušava attendance write/correction endpoint. | 403/safe 404 prema visibility; nema M11 reda/receipt-a. | §3.16 |
| M28-QA-045 | Attendance read za tuđe dete kroz poznat occurrence. | Safe 404, bez roster/count/status leak-a. | §4 |
| M28-QA-046 | M13 draft poruka je adresirana grupi deteta. | Nije u listi/count-u; nema naslova/snippeta. | §3.10 |
| M28-QA-047 | M13 published poruka actor-u, zatim owner withdraw po ugovoru. | Vidljivost prati current-recipient/withdraw rule; nema stale cache rendera. | §3.10 |
| M28-QA-048 | Mark read request timeout posle M13 commit-a. | Retry istim owner key-em vraća isti receipt; jedan read marker. | §7.3–4 |
| M28-QA-049 | Push payload se generiše za child/finance dokument. | Payload nema child ime, iznos, naslov/sadržaj ili URL ID; samo opaque bound intent. | §3.11, §4 |
| M28-QA-050 | Notification delivery je DELIVERED. | UI ne prikazuje READ dok M14 read receipt nije commit-ovan. | §3.11 |

## 7. Finansije — 051–060

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-051 | Payer otvara finance summary. | Odvojeno amount due, payments, allocations, available credit i currency; bez float-a. | §3.9 |
| M28-QA-052 | Dve škole koriste RSD/EUR. | Nikakav zbir/FX; rezultat je samo aktivna škola i njena valuta. | §3.6, §3.9 |
| M28-QA-053 | Delimična uplata postoji. | UI prikazuje evidentirano i preostalo prema M12, ne PAID. | §3.9 |
| M28-QA-054 | IPS QR otvoren bez PaymentRecord-a. | Status ostaje instrukcija/pending payment, nikad server-confirmed paid. | §3.9 |
| M28-QA-055 | Payer primeni kredit dvaput istim key-em. | Jedno M12 append-only knjiženje; isti receipt/result. | §7.3–4 |
| M28-QA-056 | Isti credit key sa drugim iznosom. | Owner 409 idempotency conflict; M28 ne mapira u success. | §6, §7.4 |
| M28-QA-057 | Dva payer request-a troše poslednji kredit. | M12 lock/CAS prihvata samo dozvoljen iznos; nema negativnog kreditnog stanja. | §7.4 |
| M28-QA-058 | Finance source gap ili currency mismatch. | Cela finance sekcija UNAVAILABLE; nema partial headline total-a. | §3.9, edge 10 |
| M28-QA-059 | Actor pokušava kartični checkout endpoint. | Ruta/komanda ne postoji u Basic H1; fail closed, bez provider poziva. | Non-goals |
| M28-QA-060 | Cancel event sa fee-om. | M16/M12 coordinator prati owner cancellation; nema automatskog cash/bank refund-a. | §7.3 |

## 8. Dokumenti, prihvatanje i privatnost — 061–070

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-061 | Guardian lista child dokumente. | Samo M15 authorized metadata za linked child; bez body/blob/other child. | §2.6, §7.1 |
| M28-QA-062 | Payer lista PAYMENT_PROOF. | Samo M12-authorized payer proof scope; nema ostalih child dokumenata. | M05 registry, §3.8 |
| M28-QA-063 | Download ticket se iskoristi dvaput. | Prva razmena uspe ili izdaje session; drugi exchange odbijen; ticket nije trajni bearer. | §3.12 |
| M28-QA-064 | Guardian link se opozove između dva range zahteva. | Sledeći range safe deny; prethodno preuzet bajt se ne produžava novim pristupom. | §3.12, §4 |
| M28-QA-065 | Browser/service worker pokuša keširati dokument response. | `no-store`, SW policy i test potvrđuju nula private cache entry-ja. | §4 |
| M28-QA-066 | Jedno dugme pokušava prihvatiti ugovor+notice+foto+video. | 422; odluke su odvojene po vrsti/verziji/subjectu. | §3.13–14 |
| M28-QA-067 | Guardian prihvati ugovor. | M15 evidence `ACCEPTED` sa actor/tenant/child/version/hash/channel/audit; M28 ne pravi evidence red. | §3.14 |
| M28-QA-068 | Guardian potvrdi privacy notice. | M15/M17 tačno `ACKNOWLEDGED`; nije „GDPR consent”. | §3.13–14 |
| M28-QA-069 | Guardian povuče foto consent. | Append-only M17/M15 evidence, effective result WITHDRAWN; portal pristup ostaje. | §3.13–14 |
| M28-QA-070 | Dva guardian-a odlučuju uz ANY_DECLINE_BLOCKS. | Priority DECLINED > WITHDRAWN > GRANTED > NOT_ASKED; nema last-write-wins. | edge 8, M17 |

## 9. Events Light — 071–080

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-071 | Guardian lista događaje za A-child-1. | Samo M16 visible+eligible događaji tog deteta; PAYER-only nema listu. | §7.1 |
| M28-QA-072 | Event je vidljiv za child-1, ne za child-2. | Child selector nudi samo child-1; skriveno dete nije u count-u. | edge 2 |
| M28-QA-073 | Free event registration. | Jedan M16 owner command/receipt; success tek posle server commit-a. | §3.15 |
| M28-QA-074 | Fee event registration. | Jedan BFF/coordinator request; M16 registracija i M12 obaveza all-or-nothing. | §3.15, §7.3 |
| M28-QA-075 | M12 padne pre commit-a fee eventa. | Rollback obe promene; nema registracije ni orphan obaveze. | §3.15 |
| M28-QA-076 | Poslednje mesto, dva guardians paralelno. | Jedan CONFIRMED; drugi tačan M16 conflict; jedna/no orphan obaveza. | edge 9 |
| M28-QA-077 | Duplicate registration key/hash. | Isti owner receipt; nema duple registracije ili obaveze. | §7.4 |
| M28-QA-078 | Event deadline prođe između preview-a i commit-a. | Pre-commit recheck odbija/rollback; UI ne prikazuje final success. | §3.15, §7.4 |
| M28-QA-079 | External-organizer event. | M16 canonical `origin_type=EXTERNAL_ORGANIZER`; M28 ne koristi superseded alias. | M16 owner contract |
| M28-QA-080 | Guardian canceluje fee registration. | Owner coordinator daje tačan status; refund samo manual/review M12 ugovorom. | §7.3 |

## 10. PWA, deep link, UX i accessibility — 081–090

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-081 | Offline browser otvara instaliran portal. | Samo public versioned shell + online-required stanje; IndexedDB/Cache nema private payload. | §3.18 |
| M28-QA-082 | Mreža nestane tokom preference update-a. | Dozvoljen optimistic pending samo lokalno; konačan state tek receipt ili rollback. | §3.17 |
| M28-QA-083 | Mreža nestane tokom consent/event/credit akcije. | Nema offline enqueue/final success; `M28_ONLINE_REQUIRED`/jasan retry. | §3.17–18 |
| M28-QA-084 | Logout/session expiry/access revoke. | Online client freeze/purge; svi private stores prazni; server svakako deny. | §3.22 |
| M28-QA-085 | Push deep link je otvoren pre login-a. | M19 PRE_AUTH_BROWSER intent bez target disclosure; resolve tek nakon login/context/guards. | §3.11, M19 |
| M28-QA-086 | Deep link target je cross-tenant ili opozvan. | Neutralan safe fallback; URL/log/analytics ne otkrivaju ID ili postojanje. | edge 11 |
| M28-QA-087 | Standard Home→child schedule flow iz definisanog starta. | Najviše tri primary interactions; test broji tap/click, ne automatski render. | §3.21, screen contract |
| M28-QA-088 | Event zahteva child izbor, fee review i pravni acceptance. | Flow je deklarisani izuzetak; svaki dodatni korak je prikazan, nema skrivenog auto-accept-a. | §3.21 |
| M28-QA-089 | Keyboard/screen reader/200% zoom/mobile 360×800. | WCAG 2.2 AA acceptance: focus, labels, errors, status announcement i bez horizontalnog gubitka akcije. | §8 |
| M28-QA-090 | Dve kartice: A spor Home, druga prebaci na B. | A response odbačen pre rendera; nula stale A frame-a u B context-u. | edge 15, §7.4 |

## 11. Concurrency, NFR, migracija i završna regresija — 091–100

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-091 | Parallel SetPreference sa istim expected version, različiti payload. | Jedan commit; drugi 409 `M28_VERSION_CONFLICT`; nema last-write-wins. | §7.2–4 |
| M28-QA-092 | Owner command commit uspe, HTTP response nestane. | Retry istim key-em vraća owner receipt; M28 ne proizvodi duplikat. | §7.4 |
| M28-QA-093 | Duplicate/out-of-order owner outbox event. | M21 InboxReceipt dedupe; source version sprečava regresiju projection-a. | §7.4 |
| M28-QA-094 | SQL/Redis/object-store/telemetry outage fuzz. | Fail closed po sensitivity; bez stack trace/SQL/PII; bez partial critical success. | §3.24, §6 |
| M28-QA-095 | Rate limit se prelazi za known i hidden target. | 429 neutralan oblik/bucket bez existence oracle-a. | §4, §6 |
| M28-QA-096 | NFR profil se izvrši. | Raw evidence dokazuje ili ne dokazuje svaki p95/bundle cilj; tekst specifikacije nije PASS dokaz. | §8 |
| M28-QA-097 | P01–P08 dual-route migration sa jednom write semantikom. | Stara/nova ruta koriste isti owner command/receipt; nema dual-write drift-a. | §8, screen contract |
| M28-QA-098 | Rollback tokom canary migracije. | Feature OFF vraća H0 rutu, ne briše owner podatke i ne ostavlja M28 private cache. | §3.25, §8 |
| M28-QA-099 | Static/schema/security scan celog M28. | UTF-8/YAML/link/heading/ID/permission/error/event/job checks 0 grešaka; runtime identifiers English ASCII; no secrets/names/history. | M00/M21 + ovaj paket |
| M28-QA-100 | M28 enrollment/preference/home/onboarding red za školu A referencira account, subject basis ili owner source iz škole B. | Composite tenant FK/owner guard odbija upis ili build; nema privatne projekcije, cache-a, audit metadata leak-a niti foreign ID-ja u odgovoru. | Master §§2–3,6 |

## 12. Conditional state, projection i system lifecycle — 101–124

| ID | Arrange / Act | Deterministički očekivani rezultat | Ugovor |
|---|---|---|---|
| M28-QA-101 | Pokušaj REQUESTED reda sa bilo kojim decision, activation, effectivity ili end poljem. | DB CHECK odbija ceo upis; nema transition/audit/outbox parcijale. | Master §2.1 |
| M28-QA-102 | Prva aktivacija postavi `activated_at != effective_from` ili izostavi entitlement version. | 422/DB CHECK; enrollment ostaje REQUESTED. | Master §2.1, §5.1 |
| M28-QA-103 | SUSPENDED red nema `ended_at`/reason ili nema dokaz prethodne aktivacije. | DB CHECK odbija; ACTIVE red i istorija ostaju nepromenjeni. | Master §2.1 |
| M28-QA-104 | Reactivate SUSPENDED uz novi `effective_from`. | ACTIVE; `ended_at/end_reason_code` očišćeni, prvi `activated_at` nepromenjen, nova transition generacija. | Master §2.1, §5.1 |
| M28-QA-105 | REJECTED red sadrži activation/entitlement polja ili nema platform actor/time/ticket/end trio. | DB CHECK odbija; nema implicitnog pilota. | Master §2.1 |
| M28-QA-106 | REVOKED enrollment koji nikad nije bio ACTIVE naspram ranije aktiviranog. | Oba su validna samo sa security actor/time/ticket/end poljima; activation polja su null u prvom, očuvana u drugom. | Master §2.1 |
| M28-QA-107 | SYSTEM_CLOCK pokušava EXPIRED transition iz REQUESTED ili sa actor/ticket poljem. | 409/DB CHECK; samo ACTIVE/SUSPENDED i null actor/ticket su dozvoljeni. | Master §2.1.1, §5.1 |
| M28-QA-108 | Dva expiry worker-a koriste isti deterministički system request ID. | Tačno jedan EXPIRED transition/receipt; drugi vraća isti rezultat. | Master §2.5, §7.2 |
| M28-QA-109 | ACTIVE preference se arhivira pa isti account postavlja novu. | Stari red ostaje ARCHIVED sa `archived_at`; nastaje najviše jedan novi ACTIVE red. | Master §2.2, §5.2 |
| M28-QA-110 | FRESH/STALE HomeProjection nema payload/hash, ima missing-source kod ili ciphertext/hash/AAD nisu vezani za isti row/account/context/generation. | DB CHECK/AEAD provera odbija; UNAVAILABLE je jedino current stanje bez payload-a i zahteva missing-source kod; kopirani ili promenjeni envelope ne renderuje podatak. | Master §2.3 |
| M28-QA-111 | HomeProjection se invalidira zbog basis-version promene ili hard expiry-ja. | Payload/hash bezbedno uklonjeni u istoj fenced tranziciji; `invalidated_at`+`invalidation_reason_codes` postoje, missing-source lista je prazna; stari sadržaj se ne može dekriptovati/renderovati. | Master §2.3, §3.19, §5.2 |
| M28-QA-112 | Dva rebuild worker-a objavljuju isti version tuple/generation. | Lease/fencing+partial unique daju jednog current pobednika; gubitnik ne menja projekciju. | Master §2.3, §7.4 |
| M28-QA-113 | Onboarding CURRENT tvrdi COMPLETE uz nerešen primenljiv owner task ili stari source hash. | Derivation/pre-serialization guard odbija COMPLETE, invalidira red i vraća ACTION_REQUIRED/UNAVAILABLE prema owner rezultatu. | Master §2.4, §3.14 |
| M28-QA-114 | Onboarding INVALIDATED zadrži task ciphertext/hash, nema invalidation code/time ili CURRENT envelope ima drugi subject/task-set/generation AAD. | DB CHECK/AEAD odbija; invalidacija ne ostavlja privatni payload i ciphertext se ne može prebaciti na drugi subject/generation. | Master §2.4, §5.2 |
| M28-QA-115 | Private owner/M28 response izostavi ili pogrešno navede `school_id`, `context_version`, `authorization_version` ili relevantni subject/source hash. | Klijent odbacuje response pre prvog rendera, zamrzava/purge-uje privatni view i radi online revalidaciju; nijedan stale/cross-context frame nije prikazan. | Master §§3.4,3.24,7.4 |
| M28-QA-116 | Home/Onboarding projekcije se enkriptuju starom key verzijom, tenant key se rotira, zatim se stari envelope kopira u drugi school/account/red; posebno nedostaje stari key. | Fenced rebuild pod novim ključem postaje current tek uz validan hash/AAD, prethodni payload se invalidira i key ostaje dok postoje reference; cross-tenant/account/row kopija i missing key failuju zatvoreno bez plaintext/global fallback-a. | Master §§2.3–2.4,3.19 |
| M28-QA-117 | CURRENT onboarding business status BLOCKED nema blocker code ili drugi status ima blocker. | DB CHECK odbija obe kombinacije. | Master §2.4 |
| M28-QA-118 | INVALIDATED onboarding red zadržava task payload ili meša blocker i invalidation reason. | DB CHECK odbija; payload/hash su null, blocker lista prazna i zatvoren invalidation reason obavezan. | Master §2.4, §5.2 |
| M28-QA-119 | Finance ili legal owner stream isporuči `N+2` pre `N+1`, ili isti event ponovi sa drugim payload hash-em. | Pogođena portal sekcija je `UNAVAILABLE`, ne prikazuje staru vrednost/placeholder nulu; M21 barrier/quarantine čuva incident, a rebuild je moguć tek po zatvaranju gap-a ili odobrenom terminalnom disposition-u. | Master §§2.3–2.4,3.24,7.4; M21 |
| M28-QA-120 | Guardian otkazuje fee registration pre M16 cutoff-a; split assessment postoji. | Jedan portal request; M16 registration i svi M12 obligations/credit efekti commit-uju zajedno uz owner receipts. | Master §3.15, §7.3; M12/M16 |
| M28-QA-121 | M12 korak fee cancellation-a failuje posle simuliranog write-a. | Ceo coordinator rollback; portal prikazuje neuspeh, registration i finance owner stanje ostaju nepromenjeni. | Master §3.15, §7.3 |
| M28-QA-122 | Guardian je otvorio event pre deadline-a, ali cancel commit stiže posle cutoff-a. | Owner 409 se ne mapira u success; nema optimistic CANCELLED, obaveza ostaje prema owner pravilima. | Master §3.15, §7.4; M16 |
| M28-QA-123 | Event je CANCELLED, M12 cancellation batch još nije završio. | Event više nije actionable; finance sekcija ne prikazuje collectible dug/instruction/reminder i pokazuje neutralno pending-materialization stanje bez obećanja refund-a. | Master §3.9, §3.15; M12/M16 |
| M28-QA-124 | Kompletan M28 acceptance na A/B/C seedu. | Zahteva 124/124 stvarno izvršena testa, 0 failed/skipped/flaky, pilot default OFF bez allowlist-a i punu M00–M21 regresiju bez cross-tenant/child/finance curenja. | sva poglavlja |

## 13. Traceability i dokaz

Svaka M28 komanda/query, svaka state transition, svih 19 M28 error kodova, pet M28 permission-a i M21 `portal.pilot_enrollment_expiry` moraju biti pokriveni najmanje jednim scenarijem iznad i mašinski mapirani u test manifestu. Dokazni zapis sadrži `scenario_id`, commit SHA, schema/migration version, policy/feature configuration hash, seed hash, test start/end UTC, rezultat i artifact hash. Ne sadrži PII, token, dokument/poruku ili bank reference. M28 nema pilot `GO` dok M28-QA-001..124 nisu stvarno prošli i full-suite M00–M21 regresija nije ostala zelena.
