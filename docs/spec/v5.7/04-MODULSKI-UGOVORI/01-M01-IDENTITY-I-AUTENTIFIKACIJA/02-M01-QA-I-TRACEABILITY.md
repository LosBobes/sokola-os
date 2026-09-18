---
tip: qa-i-traceability
modul-id: M01
status: SPEC_CANDIDATE
datum: 2026-09-15
revizija: "1.3"
obavezni-scenariji: 28
---

# M01 — QA i traceability

## Deterministični acceptance scenariji

| ID | Setup / radnja | Očekivani dokaz |
|---|---|---|
| M01-QA-001 | Validan aktivan `AuthIdentity` završi provider callback. | Jedna nova sesija; audit success; nema tenant podataka dok M03 ne odredi kontekst. |
| M01-QA-002 | Validan provider subject nema lokalni aktivni nalog. | `NO_ACCESS`; nema Person/UserAccount kreiranja, nema enumeration curenja. |
| M01-QA-003 | Replay istog callback state-a. | Drugi zahtev odbijen; ne nastaje druga sesija ni audit success. |
| M01-QA-004 | Token ima pogrešan issuer/audience/nonce ili je istekao. | Bez sesije; `AUTH_CALLBACK_INVALID`; raw token nije u logu. |
| M01-QA-005 | Pokušaj linkovanja subject-a već vezanog za drugi nalog. | 409 bez identiteta drugog naloga; bez izmene oba naloga. |
| M01-QA-006 | Pokušaj unlink poslednjeg aktivnog identiteta. | 409 `LAST_IDENTITY_PROTECTED`; stanje ostaje isto. |
| M01-QA-007 | Dva paralelna linka istog subject-a na različite naloge. | Tačno jedan može uspeti; unique i audit pokazuju deterministični ishod. |
| M01-QA-008 | `LogoutCurrentSession`, zatim back/refresh/direct protected URL. | 401 i bez čitljivih cache podataka; druga sesija ostaje aktivna. |
| M01-QA-009 | `LogoutAll` sa dve sesije i otvorenim realtime kanalom. | Sve sesije/realtime kanali opozvani na sledećoj proveri; version bump i outbox. |
| M01-QA-010 | M03/M05 opozove membership/permission u drugom tabu. | Sledeći request stare sesije ponovo čita version/guard; nema pristupa opozvanom resursu. |
| M01-QA-011 | Account `DISABLED` dok postoji aktivna sesija. | Sve buduće komande/query/download/realtime su 401; audit i cache invalidation postoje. |
| M01-QA-012 | Dva naloga imaju isti email claim, različit subject. | Ne linkuju se/merge-u automatski; nema curenja ni promene `Person`. |
| M01-QA-013 | 6 `StartLogin` zahteva sa istog IP u 10 min. | Šesti je 429; poruka ne potvrđuje email/nalog. |
| M01-QA-014 | Provider timeout tokom callback-a. | 503 retryable, bez lokalne sesije i bez lažnog success-a. |
| M01-QA-015 | Zaštićeni endpoint dobije validan session cookie uz client `school_id` druge škole. | M01 validira session, M03 vraća safe not-found; parametar nije autoritet. |
| M01-QA-016 | Inspect audit/telemetry/error logs za login failure. | Nema raw tokena, credential-a, email-a, child/tenant detalja. |
| M01-QA-017 | Migracija nad legacy duplim/ambiguous mappingom. | Determinističan exception report; nijedan automatski merge; aktivne neproverene sesije opozvane. |
| M01-QA-018 | M02 aktivacija padne između provider dokaza i upisa lokalnog naloga. | Transakcija ne ostavlja `UserAccount` bez prvog aktivnog `AuthIdentity`; retry daje jedan nalog i jednu vezu. |
| M01-QA-019 | Callback šalje neodobren issuer alias, drugačiji case/path ili isti subject preko drugog registrovanog issuer-a. | Alias/neodobren issuer je `PROVIDER_NOT_ALLOWED`; subject je opaque; validna dva issuer-a nemaju koliziju. |
| M01-QA-020 | `LogoutAll` uspe, ista sesija ponovi isti `request_id`, zatim ponovi isti key sa drugim payload-om. | Prvi retry vraća minimalni prethodni uspeh preko receipt-a bez ponovne autorizacije; promenjen payload je 409; nijedna sesija ne oživljava. |
| M01-QA-021 | Čvor B ima star auth cache; čvor A commit-uje suspend/revoke; sledeći zahtev ide na B pre outbox potrošača. | B odbija zahtev autoritativnom/monotonic version proverom ili fail-closed read-through; nema stale-cache prozora. |
| M01-QA-022 | Visokorizična mutacija prođe početni auth check, zatim drugi tok opozove pristup pre commit-a. | Mutacija ponovo proverava authorization version pre commit-a i ne upisuje promenu pod opozvanim pravom. |
| M01-QA-023 | Ovlašćeni admin izvrši `ACTIVE→SUSPENDED→ACTIVE`. | Oba prelaza traže expected version/razlog/audit; suspend opoziva sve sesije; reaktivacija ne vraća nijednu staru sesiju. |
| M01-QA-024 | Pokušaj `DISABLED→ACTIVE` kroz `ReactivateAccount` ili status patch. | 409 `INVALID_ACCOUNT_TRANSITION`; nema session-a, version/audit istorija ostaje konzistentna. |
| M01-QA-025 | Validan callback izdaje server-side sesiju, a callback token kasnije istekne pre lokalnog idle/absolute roka bez provider revoke događaja. | Lokalna sesija prati sopstveni dokumentovani rok; token se ne koristi kao refresh credential; potvrđeni provider revoke i dalje odmah prekida pristup. |
| M01-QA-026 | Dve stvarno paralelne transakcije šalju istu write komandu sa istim `request_id` i kanonskim payload-om; prva ne završava pre kratkog command timeout-a druge. | Druga ne izvršava side effect; vraća prvi durable rezultat ako je dostupan, inače 409 `IDEMPOTENCY_IN_PROGRESS` i `Retry-After: 1`; konačno postoje jedan state change, jedan receipt, jedan audit i jedan outbox zapis. |
| M01-QA-027 | HTTP write nema `Idempotency-Key`, ključ nije UUID ili se razlikuje od body `request_id`. | 400 `IDEMPOTENCY_KEY_INVALID`; nema poslovnog upisa, success audita, receipt-a ili outbox-a. |
| M01-QA-028 | Jedan account ima aktivne odnose u školama A i B; version bump emituje invalidation, dispatcher dobije duplicate i privremeno zakaže za B. | Nastaje jedan PLATFORM outbox događaj bez school/PII sadržaja; M01 ne čita membership-e. Svaki novi A/B request je odmah odbijen starom authorization verzijom, a idempotentni platform dispatcher na retry-u invalidira obe projekcije bez kreiranja prava ili duplog efekta. |

## Obavezne automatizovane grupe

- unit: state/expiry/version, status transition matrica, provider registry canonical match, idempotency payload mismatch, unique/link guard;
- integration: atomarno account+first-identity kreiranje, callback validation, command receipt, session store, revocation, fail-closed stale-cache read-through, outbox/cache invalidation, database constraints;
- security: CSRF/cookie flags, replay, fixation, IDOR context parameter, log redaction, brute-force rate limit;
- e2e: prijava, provider cancel/failure, logout/back navigation, revoked membership na otvorenom tabu;
- migration: upgrade, backfill report, forward recovery i fresh seed.

## Scenario-po-paragraf normativna mapa

| QA ID | M01 master normativni oslonac |
|---|---|
| M01-QA-001 | §§2 (`AuthIdentity`), 6 AUTH-02, 8 |
| M01-QA-002 | §§4.4, 6 AUTH-02 ("NO_ACCESS" pasus) |
| M01-QA-003 | §§6 AUTH-02 (replay-safe state), 12 (jednokratni state kao replay guard) |
| M01-QA-004 | §§6 AUTH-02 (odbija pogrešan issuer/audience/nonce/exp), 11 (`AUTH_CALLBACK_INVALID`), 13 (bez raw tokena) |
| M01-QA-005 | §§4.3, 6 AUTH-06 (odbija subject linkovan drugom nalogu), 11 (`IDENTITY_ALREADY_LINKED`) |
| M01-QA-006 | §§5 (AuthIdentity lifecycle), 6 AUTH-07 (poslednji identitet), 11 (`LAST_IDENTITY_PROTECTED`) |
| M01-QA-007 | §§2 (`UNIQUE(provider_issuer, provider_subject)`), 6 AUTH-06 (zaključava nalog i identitet) |
| M01-QA-008 | §§6 AUTH-04, 9 (server session/cache/context cleanup) |
| M01-QA-009 | §§4.7, 6 AUTH-05, 13 (outbox `identity.authorization_invalidated`) |
| M01-QA-010 | §§4.7 ("za svaki zahtev koji počne nakon uspešnog commit-a"), 6 AUTH-08 (fail-closed autoritativni store) |
| M01-QA-011 | §§3.1 (statusi), 5 (`DISABLED` opoziva sve sesije), 6 AUTH-11 |
| M01-QA-012 | §§4.5 (email podudaranje samo po sebi nikad ne linkuje), 7 |
| M01-QA-013 | §§6 AUTH-01 (rate limit 5/10min), 10, 11 (`RATE_LIMITED`) |
| M01-QA-014 | §§6 AUTH-02, 10 (provider timeout, circuit breaker), 11 (`PROVIDER_RETRYABLE`) |
| M01-QA-015 | §§8 (tenant-neutralna autentifikacija, `school_id` nije autoritet) |
| M01-QA-016 | §13 (audit/telemetry bez raw email/tokena/PII) |
| M01-QA-017 | §§15 (migracija, exception report, bez automatskog merge-a) |
| M01-QA-018 | §§1 (M02 atomarno kreiranje), 3.1 (nema trajnog PENDING_LINK), 15 (legacy orphan mapiranje) |
| M01-QA-019 | §§3.2 (`AuthProviderRegistration`, tačan issuer, subject opaque), 11 (`PROVIDER_NOT_ALLOWED`) |
| M01-QA-020 | §6 AUTH-05 (`AuthCommandReceipt`, retry hash, `IDEMPOTENCY_KEY_REUSED`) |
| M01-QA-021 | §§4.7, 6 AUTH-03/AUTH-08 (fail-closed read-through, nema stale-cache prozora) |
| M01-QA-022 | §§6 AUTH-08 ("visokorizična mutacija... ponovo proverava version neposredno pre sopstvenog commit-a") |
| M01-QA-023 | §§5 (lifecycle tabela `SUSPENDED`↔`ACTIVE`), 6 AUTH-09/AUTH-10 |
| M01-QA-024 | §§5 (nema povratka iz `DISABLED`), 6 AUTH-10/AUTH-11, 11 (`INVALID_ACCOUNT_TRANSITION`) |
| M01-QA-025 | §3.2 (poslednji pasus — provider token expiry nije proizvoljni lokalni lifetime) |
| M01-QA-026 | §12 (identičan zahtev u toku, bounded wait, receipt i `IDEMPOTENCY_IN_PROGRESS`) |
| M01-QA-027 | §§11–12 (`IDEMPOTENCY_KEY_INVALID`, obavezno poklapanje header/body UUID-a) |
| M01-QA-028 | §§4.7, 6 AUTH-08 i 13 (PLATFORM invalidation, bez M01→membership zavisnosti, read-time revoke ostaje autoritet) |

## Traceability ka aktivnim ugovorima

| Aktivni autoritet | M01 granica |
|---|---|
| M00 arhitektura i DCR-20260907-01 rev. 2.3 | Modularni monolit, repo-first rad, receipt/audit/outbox i globalni security standard. |
| M02 master | Invitation status/token/expiry/resend/replay nisu M01 podaci; M01 pruža provider proof i account/identity create-or-reuse port. |
| M03 master | Aktivna škola i tenant context nisu M01 session claim niti client authority. |
| M05 master/registry | Role, permission, step-up policy i Support Access nisu M01 ownership. |
| M06 master | `Person` je M06; M01 samo ima obavezni FK `UserAccount.person_id`. |
| M07 master | Guardian/payer basis nije auth identity niti account linking dokaz. |
| M01 QA 001–028 | Dokazuje input/guard/transakciju/idempotenciju/audit/error i happy/forbidden/replay/race/multi-school invalidation ugovore. |

## Otvoreno, ali neblokirajuće za kod

Konkretan provider, domen/redirect allowlist vrednosti, MFA/step-up politika, finalna retention vrednost security logova, produkcioni SSO i odobrena produkciona session konfiguracija moraju biti uneti sa fail-closed defaultima i dokazima pre realnog pilota. Ako nema odobrene session konfiguracije, obavezni default ostaje 30 minuta idle i 12 sati absolute; konfiguracija ne sme proizvesti alternativnu poslovnu semantiku niti slabiji revoke ugovor.
