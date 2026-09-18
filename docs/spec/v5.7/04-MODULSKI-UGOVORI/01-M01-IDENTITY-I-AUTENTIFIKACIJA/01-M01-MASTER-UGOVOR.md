---
tip: modulni-implementacioni-ugovor
modul-id: M01
naziv: Identity i autentifikacija
status: SPEC_CANDIDATE
datum: 2026-09-15
revizija: "1.3"
schema-zavisnosti: [M06]
application-korisnici: [M02, M03, M05, M06, M07, M17, M19, M20, M21, M28]
---

# M01 — Identity i autentifikacija

M01 primenjuje Foundation schema redosled i zajednički idempotency ugovor iz [[../00-M00-OBIM-I-ARHITEKTURA/02-M00-ARHITEKTURA-MODULI-I-ZAVISNOSTI|M00 arhitekture]]. Invite-only princip i uslovi kreiranja identiteta potpuno su definisani ovde i u M02. M06 poseduje `Person` i njegov schema anchor; M01 poseduje auth model i referencira `Person`. Invitation lifecycle ostaje M02, tenant context M03, RBAC/support M05, person lifecycle M06, a guardian/payer odnosi M07.

## 1. Svrha, granice i autoritet

M01 bezbedno utvrđuje **ko je prijavljen**, vodi trajnu vezu između spoljnog autentifikovanog subjekta, lokalnog `UserAccount` i globalne `Person`, i obezbeđuje da opoziv pristupa prekine sledeći zahtev. M01 ne odlučuje **šta** prijavljena osoba sme da vidi ili radi u školi.

Normativni rezultat je `Person != UserAccount`; dete/polaznik nema `UserAccount` u MVP-u; SOKOLA ne čuva lozinke, njihove hash-eve, recovery kodove niti OIDC refresh/access/ID tokene u auditu, telemetry-ju ili aplikacionoj bazi. Stvarni repo bira OIDC provider, passwordless ili drugi provider adapter, session format, ORM i transport. Mora, međutim, ostvariti sva ponašanja ovog ugovora.

M01 ne uvodi: javnu registraciju, invitation lifecycle (M02), tenant kontekst (M03), role/permission registry i support access (M05), person deduplikaciju/merge (M06), guardian odnos (M07), pravnu verifikaciju identiteta (M17), niti profilni self-service. M02 može voditi kratkotrajni pokušaj prihvatanja poziva, ali ne sme unapred kreirati prazan `UserAccount`: prvi `UserAccount` i njegov prvi `AuthIdentity` nastaju atomarno tek posle uspešnog provider dokaza i svih M02/M06 guardova.

## 2. Kanonski pojmovi i source of truth

| Pojam | Autoritet i značenje |
|---|---|
| `Person` | Globalna osoba; business/relationship identity. M06 je vlasnik njenog životnog ciklusa. Može postojati bez naloga (svako dete i mnogi uvezeni odrasli). |
| `UserAccount` | SOKOLA lokalni autentifikacioni nalog, tačno jednom vezan za jednu `Person`; vodi lokalni status, revizije autorizacije i sesije. M01 je vlasnik. |
| `AuthIdentity` | Verifikovana veza naloga sa jednim provider subject-om. M01 je vlasnik. Spoljni `issuer + subject` je jedini kanonski ključ spoljnog identiteta. |
| `AuthProviderRegistration` | Fail-closed registar dozvoljenih providera i njihovih tačnih issuer/audience/redirect/verifikacionih pravila; konfiguracioni source of truth, bez client secret-a u poslovnoj bazi. |
| `AuthProviderAdapter` | Tehnička granica prema stvarnom provideru. Provider potvrđuje autentifikaciju; ne dodeljuje SOKOLA pristup. |
| `Session` | Server-side ili kriptografski proverljiv zapis aktivne prijave, vezan za tačno jedan `UserAccount`, authorization version i autentifikacioni trenutak. |
| `AuthenticationEvent` | Bezbednosni audit pokušaja i ishoda prijave/odjave/opoziva/linkovanja; nikad ne sadrži credential ili token. |
| `principal` | Minimalni, provider-verifikovani rezultat: `issuer`, stabilni `subject`, potvrđen status email claim-a ako provider to garantuje, vreme autentifikacije i assurance/AMR kada postoji. |

`AuthIdentity` je `UNIQUE(provider_issuer, provider_subject)` globalno. Svaki `ACTIVE` ili `SUSPENDED` `UserAccount` ima najmanje jedan linkovan aktivni `AuthIdentity`, a jedna `AuthIdentity` pripada tačno jednom nalogu. `DISABLED` i `MERGED_RETIRED` mogu čuvati samo istorijske/unlinked veze i nikad se preko njih ne autentifikuju. Jedan `UserAccount` pripada tačno jednoj `Person`; jedna `Person` ima najviše jedan neredundantni aktivni `UserAccount` u MVP-u. Kontakt email osobe nije login identitet i nije unique auth ključ.

## 3. Minimalni podatkovni ugovor

### 3.1 UserAccount

Obavezna polja: nepredvidivi immutable `id`; `person_id`; `status`; `authorization_version` (pozitivan integer); `created_at`; `updated_at`; `last_authenticated_at` nullable; `disabled_at` nullable; `disabled_reason_code` nullable; `version` ili ekvivalent optimistic-concurrency polja. Zabranjena su polja za lozinku, password hash, raw provider token, session secret i globalni tenant/role.

Statusi: `ACTIVE`, `SUSPENDED`, `DISABLED`, `MERGED_RETIRED`. Samo `ACTIVE` može kreirati ili obnoviti aplikacionu sesiju. `SUSPENDED` je reverzibilan samo komandom `AUTH-10` uz M05 dozvolu; `DISABLED` je terminalan u redovnom toku, a `MERGED_RETIRED` je terminalan bez izuzetka. Ne postoji trajni `PENDING_LINK` nalog: priprema prihvatanja poziva je kratkotrajni M02 zapis sa TTL-om, odvojen od `UserAccount` tabele.

### 3.2 AuthIdentity i Session

`AuthIdentity`: `id`, `user_account_id`, kanonski `issuer`, stabilni neizmenjeni `subject`, `provider_key`, `email_verified_at` samo ako ga provider izričito potvrdi, `linked_at`, `last_verified_at`, `unlinked_at`, `unlink_reason_code`, `created_by_event_id`. Ne čuva se email claim kao autoritativan identitet; po potrebi je minimizovan prikazni snapshot sa rokom čuvanja iz M17. `subject` je opaque i ne trimuje se, ne menja mu se case i ne normalizuje se poslovnim pravilom.

`AuthProviderRegistration`: jedinstveni `provider_key`; tačan kanonski `issuer` dobijen iz odobrenog provider metadata/config izvora; dozvoljeni audience/client identifikatori; dozvoljene redirect rute; dozvoljeni algoritmi i ključ/discovery pravila; `status=ACTIVE|DISABLED`; config revision i auditovana promena. Callback `issuer` mora se poklopiti tačno sa aktivnom registracijom. Alias, display name, request parametar ili email domen nikad ne biraju identitet i ne ulaze u unique ključ. Tajne ostaju u secret store-u/deploy konfiguraciji.

`Session`: nepredvidivi `id`; samo hash/derivat session credential-a ako se koristi server store; `user_account_id`; `auth_identity_id`; `created_at`; `last_seen_at`; `absolute_expires_at`; `idle_expires_at`; `revoked_at`; `revoke_reason_code`; `authorization_version_at_issue`; `auth_time`; `assurance_context` bez sirovog provider payload-a; `device_label` nullable, korisnički razumljiv i minimizovan. Jedan credential ne sme identifikovati drugu sesiju ili nalog.

Vremena trajanja su strukturirana bezbednosna konfiguracija, ne dokumentaciona pretpostavka. Ako repo nema potvrđenu vrednost, runtime default je fail-closed: interaktivna aplikaciona sesija prestaje posle 30 minuta neaktivnosti ili na apsolutnom maksimumu od 12 sati, šta pre nastupi. Provider token expiry obavezno se proverava pri callback-u, ali sam po sebi ne produžava niti proizvoljno skraćuje već izdato server-side SOKOLA trajanje, osim kada potvrđena provider/back-channel politika eksplicitno zahteva raniji opoziv. Konfiguraciju može menjati samo platform owner kroz auditovan deploy/config tok; svaka vrednost mora biti testirana.

## 4. Invarijante i zabranjene veze

1. Uspešan provider login bez aktivnog `UserAccount` ili aktivnog SOKOLA pristupa nikad ne otvara tenant podatke.
2. Klijent nikad ne šalje `person_id`, `user_account_id`, issuer, subject ili role kao autoritativnu vrednost za kreiranje sesije.
3. Jedan `issuer+subject` ne može biti linkovan na dva naloga; `ACTIVE`/`SUSPENDED` nalog ne može ostati bez aktivnog identiteta.
4. Ne kreira se `Person` na običan login, reset lozinke, email promenu ili neuspešan invitation tok. Kreiranje/povezivanje kroz potvrđeno prihvatanje poziva pripada M02 uz M06 guardove.
5. Email podudaranje samo po sebi nikada ne linkuje nalog niti spaja osobe. Provider subject i eksplicitna, ponovo autentifikovana potvrda su obavezni.
6. Ni provider claim ni session ne sadrži tenant, permission, guardian scope ili finansijski subject kao autoritet. Ti se određuju na svakom server zahtevu od M03/M05/M07 odnosa.
7. Povećanje `authorization_version` trenutno poništava sve postojeće sesije naloga za svaki zahtev koji počne nakon uspešnog commit-a, uključujući cache i websocket/realtime kanale. Bezbednost ne sme zavisiti od eventualnog outbox potrošača.
8. Opoziv jednog school membership-a ne mora odjaviti nalog iz drugih škola, ali mora invalidirati sve session authorization projekcije; M03/M05 vraćaju odluku da li je potrebna potpuna odjava. Disable naloga uvek opoziva sve sesije.
9. Ne postoji local fallback login, magic-link, SMS login ili provider bypass ako za njega nema eksplicitnog adaptera, konfiguracije i testova. Podrazumevano je OFF.

## 5. Lifecycle i dozvoljene tranzicije

| Entitet | Iz | U | Okidač / posledica |
|---|---|---|---|
| UserAccount | ACTIVE | SUSPENDED | `AUTH-09 SuspendAccount`; revoke all sessions, version bump |
| UserAccount | SUSPENDED | ACTIVE | samo eksplicitna auditovana reaktivacija; nova prijava potrebna |
| UserAccount | ACTIVE/SUSPENDED | DISABLED | bezbednosni/pravni platform tok; revoke all sessions |
| UserAccount | ACTIVE/SUSPENDED/DISABLED | MERGED_RETIRED | samo M06 kontrolisani merge; nikad automatski |
| Session | aktivna | REVOKED | logout, account disable, auth-version mismatch, provider invalidation ili sigurnosni događaj |
| Session | aktivna | EXPIRED | idle/absolute istek ili potvrđeni provider/back-channel opoziv; bez produženja posle isteka |
| AuthIdentity | ACTIVE | UNLINKED | samo zahtev iz §7; ako bi ostao bez identiteta, radnja blokirana |

`Session` nema povratak iz `REVOKED` ili `EXPIRED`. Nova prijava pravi novu sesiju. Provider logout greška ne vraća lokalno opozvanu sesiju.

## 6. Komande i query ugovor

### AUTH-01 StartLogin

Javna, enumeration-safe komanda. Generiše jedinstveni state/nonce/PKCE ili semantički ekvivalent, vezan za browser transakciju, povratnu rutu koja prolazi allowlist i kratak rok. Ne otkriva da li email, osoba ili nalog postoji. Rate limit: 5 startova po IP za 10 min i 10 po browser/device signal-u za 24 h; prekoračenje vraća `RATE_LIMITED` bez detalja.

### AUTH-02 CompleteProviderCallback

Prihvata samo provider-potpisan/validiran callback sa nepoklapanim/replay-safe state-om, validnim issuer/audience/nonce/PKCE i vremenom. Adapter mora odbiti unsigned token, pogrešan issuer/audience, istekao `exp`, ponovljen state i callback za neodobren provider. U jednoj transakciji: nalazi `AuthIdentity`, zaključava nalog, proverava `ACTIVE`, evidentira `last_verified_at`, izdaje sesiju sa trenutnim `authorization_version`, zapisuje audit. Ako identitet nema aktivan nalog ili nema aktivni SOKOLA access, prijava završava neutralnim `NO_ACCESS` stanjem bez tenant podataka i bez automatskog kreiranja. Uspeh vraća samo session i neutralni izbor konteksta; M03 zatim razrešava dozvoljene kontekste.

### AUTH-03 ValidateSession

Izvršava se pre svake zaštićene komande, query-ja, download-a, export-a, realtime subscribe-a i background callback-a koji deluje u ime korisnika. Proverava signature/hash, revocation, expiry, `UserAccount.status=ACTIVE` i tačno poklapanje authorization version-a. Ne oslanja se samo na JWT expiry ili UI cache. Failure briše lokalni credential, vraća `UNAUTHENTICATED` i ne otkriva tenant stanje.

### AUTH-04 LogoutCurrentSession / AUTH-05 LogoutAllSessions

Prva opoziva samo prezentovanu sesiju; druga za prvi poziv zahteva aktivnu sesiju i svežu ponovnu autentifikaciju kada je provider podržava. Pre version bump-a server u istoj transakciji čuva minimalni `AuthCommandReceipt` za `(user_account_id, AUTH-05, request_id, canonical_payload_hash)`. Nakon što je trenutna sesija opozvana, identičan retry sme koristiti hash prezentovanog opozvanog credential-a isključivo da pronađe isti receipt i vrati minimalni prethodni uspeh; to nije autorizacija ni za jednu drugu radnju. Retry sa drugim payload-om je `IDEMPOTENCY_KEY_REUSED`. Bez credential-a klijent lokalno čisti stanje i endpoint može vratiti bezbedan prazan uspeh, ali ne tvrdi da je nova server-side revokacija izvršena. `LogoutAll` povećava authorization version i opoziva sve sesije, uključujući realtime konekcije. Lokalni logout je obavezan čak i kada provider global logout zakaže; provider failure se evidentira kao retryable bez vraćanja sesije.

### AUTH-06 LinkAuthIdentity

Nije self-service MVP površina; servisni port za M02 i budući potvrđeni account-security tok. Zahteva aktivan nalog, svežu ponovnu autentifikaciju postojećeg naloga i dokaz kontrole novog provider subject-a u istoj atomicnoj operaciji. Zaključava nalog i identitet; odbija subject linkovan drugom nalogu (`CONFLICT`), nezabeležen provider ili neusklađen proof. Uspeli link bumpuje authorization version, auditira oba identity reference-a pseudonimizovano i opoziva druge sesije osim one koja je završila radnju.

### AUTH-07 UnlinkAuthIdentity

Zahteva svežu ponovnu autentifikaciju, `expected_version`, razlog i najmanje još jedan aktivni identitet. Zabranjeno je unlinkovati poslednji identitet, identitet kojim se trenutno potvrđuje radnja ako nema drugi dokaz, ili identitet dok je nalog suspendovan/disabled. U istoj transakciji unlink, authorization-version bump, revoke all sessions osim bezbedno ponovo izdate sesije kroz preostali identitet, audit. Nema fizičkog brisanja istorije.

### AUTH-08 RevokeAccountSessions

Interni port za M02/M03/M05/M06/M07/M17. Input: `user_account_id`, strogo definisan `reason_code`, `correlation_id`, opcioni `keep_session_id` samo za dokazano bezbedan scenario. U jednoj DB transakciji zaključava nalog, bumpuje version, opoziva odgovarajuće server-side sesije, zapisuje audit i outbox. Komanda sme vratiti uspeh tek posle durable commit-a. Svaki novi protected request proverava revocation/status/version iz autoritativnog store-a ili iz monotonic revocation store-a sa sinhronom write-through potvrdom; ako je svežina cache-a nepoznata, zahtev fail-closed ponovo čita autoritativni store. Outbox ubrzava gašenje realtime kanala i sekundarnih projekcija, ali nije bezbednosni autoritet. Visokorizična mutacija koja je počela pre revoke commit-a ponovo proverava version neposredno pre sopstvenog commit-a. Pozivalac ne može preskočiti audit.

### AUTH-09 SuspendAccount

Interna administratorska komanda. Zahteva M05 `platform.accounts.suspend`, `target_user_account_id`, `expected_version`, obavezni dozvoljeni `reason_code`, `request_id` i `correlation_id`; slobodan tekst je opcion i minimizovan. Dozvoljena je samo `ACTIVE→SUSPENDED`. U jednoj transakciji menja status, bumpuje authorization version, opoziva sve sesije, upisuje audit/outbox i čuva idempotency rezultat. Ponovljen identičan zahtev vraća prvi rezultat; drugačiji payload sa istim ključem je konflikt.

### AUTH-10 ReactivateAccount

Interna administratorska komanda uz M05 `platform.accounts.reactivate`, `expected_version`, reason/request/correlation podatke. Dozvoljena je samo `SUSPENDED→ACTIVE` i samo ako postoji najmanje jedan aktivni `AuthIdentity`. Bumpuje authorization version i auditira promenu; ne vraća stare sesije i ne prijavljuje korisnika automatski. `DISABLED` i `MERGED_RETIRED` se ovom komandom nikad ne reaktiviraju.

### AUTH-11 DisableAccount

Interna platform-security/legal komanda koja zahteva M05 `platform.accounts.disable` + M17 legal/security guard, sa obaveznim razlogom. Dozvoljena je `ACTIVE|SUSPENDED→DISABLED`; u jednoj transakciji bumpuje version, opoziva sve sesije, uklanja aktivnu mogućnost login-a bez brisanja audit istorije i emituje outbox. Redovni UI/API nema `DISABLED→ACTIVE`; izuzetak zahteva poseban budući pravni/security recovery ugovor, ne ovu komandu.

### AUTH-Q01 GetMyAuthenticationState

Vraća samo prijavljenom korisniku: status trenutne sesije, preostalo trajanje bez preciznog server internog detalja, last auth time i minimum za bezbednosni UI. Ne vraća druge identitete, druge škole, raw provider claim ili token.

## 7. Account linking, provider promene i recovery granice

Provider promenu email-a SOKOLA ne tretira kao novi identitet: `issuer+subject` ostaje veza, a email claim je samo ponovo provereni atribut. Ako provider reciklira/menja subject ili migracija provider-a zahteva mapiranje, radi se jednokratni, idempotentan, auditovan migracioni tok sa dokazom starog i novog identiteta; bez dokaza se login prekida `NO_ACCESS` i slučaj je za kontrolisani support/M17 proces.

Nije dozvoljeno automatsko linkovanje preko jednakog email-a, telefona, imena, datuma rođenja, referral tokena ili invitation URL-a. Password reset i provider recovery ostaju kod providera; nakon povratka `CompleteProviderCallback` i dalje zahteva aktivnu lokalnu vezu. SOKOLA support nikad ne prima niti resetuje lozinku i ne koristi nalog korisnika.

## 8. Tenant-neutralna autentifikacija i autorizacija

**Vidi [[../03-M03-MULTI-TENANCY/01-M03-MASTER-UGOVOR|M03 master ugovor]] za pun tenant context model.** Login rezultat je tenant-neutralan. Tek nakon `ValidateSession`, M03 rešava aktivne school membership-e, a M05 permission i M07 subject guard. Klijent može predložiti izbor konteksta, ali server ga ponovo proverava pri svakoj radnji. `school_id` u URL-u, localStorage-u, cookie-u ili body-ju nije dokaz pristupa.

Ako prijavljena osoba nema aktivni kontekst, prikazuje se neutralno stanje „Prijavljeni ste, ali trenutno nemate aktivan pristup.“ Ne navodi se razlog, škola, poziv ili drugi račun. Tuđi tenant resurs je `NOT_FOUND_SAFE`/404; poznat resurs u već dozvoljenom tenantu bez permission-a je `FORBIDDEN`/403, po M03/M05.

## 9. Session, cache i client ponašanje

Credential mora biti `Secure`, `HttpOnly`, `SameSite=Lax` ili stroži, uz CSRF zaštitu za cookie-based mutacije; nikad localStorage/sessionStorage. Ako arhitektura koristi bearer token, ne sme biti dostupan nepoverljivom JavaScript-u i mora imati ekvivalentnu XSS/CSRF zaštitu, kratko trajanje i revocation proveru.

Odjava, authorization-version događaj i revocation moraju ukloniti server session, auth cache, context cache, query cache, izabrani tenant kontekst i otvorene realtime subscription-e. Back/forward navigacija posle odjave ne sme prikazati čitljive zaštićene podatke; na focus/restore aplikacija revalidira sesiju pre prikaza. Shared device UI ima „odjavite se“ kontrolu i ne pamti prethodni profil.

## 10. Abuse, rate limit i provider otpornost

Pored AUTH-01 limita: callback failure limit je 20/IP/10 min; logout i session validate se ne rate-limituju tako da blokiraju bezbedno odjavljivanje, ali se anomalični volumeni telemetrijski beleže. Limiti su keyed hash IP/device signal-a i kratko se čuvaju prema M17; ne koriste se za profilisanje. CAPTCHA/MFA step-up aktivira samo provider ili eksplicitno odobrena konfiguracija, nikad ne aplikacioni improvizovani tok.

Provider adapter ima timeout (default 10 s), validaciju odgovora, retry samo za tehnički retryable poziv pre nepovratnog lokalnog commit-a, circuit breaker/equivalent i sandbox/mock test. Timeout/nevalidan odgovor ne izdaje sesiju i vraća `PROVIDER_RETRYABLE` ili `PROVIDER_TERMINAL`; nema lokalnog „pretpostavi uspeh“ ponašanja.

## 11. Greške

| Kod | Transport | Bezbedno ponašanje |
|---|---|---|
| `UNAUTHENTICATED` | 401 | Prijava ili sesija ne važi; bez tenant detalja. |
| `NO_ACCESS` | 403 nakon uspešne autentifikacije ili neutralni UI | Ne otkriva koji odnos nedostaje. |
| `AUTH_CALLBACK_INVALID` | 400 | Generička neuspešna prijava; state/token detalji samo correlation log. |
| `ACCOUNT_INACTIVE` | 403 | Generička poruka bez razloga i bez istorije. |
| `IDENTITY_ALREADY_LINKED` | 409 | Samo ovlašćenom potvrđenom akteru; ne otkriva drugi nalog. |
| `LAST_IDENTITY_PROTECTED` | 409 | Ne može se ukloniti poslednji način prijave. |
| `PROVIDER_NOT_ALLOWED` | 400 | Provider/issuer nije u aktivnom fail-closed registru; bez detalja konfiguracije. |
| `INVALID_ACCOUNT_TRANSITION` | 409 | Tražena promena statusa nije dozvoljena iz trenutnog stanja. |
| `STALE_VERSION` | 409 | Osvežite bezbednosno stanje i pokušajte ponovo. |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Isti key sa drugim payload-om nije prihvaćen. |
| `IDEMPOTENCY_IN_PROGRESS` | 409 | Identična komanda sa istim ključem još nema durable rezultat; `Retry-After: 1`. |
| `IDEMPOTENCY_KEY_INVALID` | 400 | Write zahtev nema validan UUID ključ ili se HTTP `Idempotency-Key` ne poklapa sa body `request_id`. |
| `RATE_LIMITED` | 429 | Generičko sačekajte; `Retry-After` gde transport podržava. |
| `PROVIDER_RETRYABLE` | 503 | Bez sesije; bez provider internog detalja. |
| `INTERNAL_SAFE` | 500 | Correlation ID, bez tokena/PII. |

## 12. Idempotency, concurrency i transakcije

Sve mutation komande nose stabilni `request_id: UUID`; na HTTP transportu isti UUID je obavezan u `Idempotency-Key` header-u i mora se tačno poklopiti sa body vrednošću. Nedostajući/nevalidan ključ ili nepoklapanje je `IDEMPOTENCY_KEY_INVALID`, bez poslovnog upisa. Server pamti rezultat po `(account ili javni auth-transaction scope, command, request_id)` najmanje do isteka maksimalne session+retry granice. Idempotency scope za security komandu ne sme nestati samo zato što je komanda opozvala sesiju aktera. Isti key i drugačiji kanonski payload je `IDEMPOTENCY_KEY_REUSED`. Ako identičan zahtev stigne dok prvi još traje, čeka samo do kratkog command timeout-a: vraća isti durable rezultat ako je postao dostupan, a inače `IDEMPOTENCY_IN_PROGRESS` sa `Retry-After: 1`; ne izvršava drugi side effect. `CompleteProviderCallback` koristi jednokratni state kao replay guard, ne samo request id. Link/unlink/revoke/status komande zaključavaju `UserAccount` i relevantne `AuthIdentity` redove ili daju ekvivalentan serializable rezultat; `expected_version` važi za unlink i administratorske promene statusa. Audit, state change, durable session revocation i outbox zapis su jedna poslovna DB transakcija; udaljena cache/realtime propagacija nije deo atomske tvrdnje i ne sme biti jedini security guard. Provider side-effect se nikad ne predstavlja kao lokalni uspeh pre potvrde.

## 13. Audit, outbox, telemetry i privatnost

Audit eventovi: `auth.login_started`, `auth.login_succeeded`, `auth.login_failed`, `auth.session_revoked`, `auth.logout_all`, `auth.identity_linked`, `auth.identity_unlinked`, `auth.account_suspended`, `auth.account_disabled`, `auth.authorization_version_bumped`. Svaki ima actor/account pseudoreferencu, rezultat, reason code, correlation ID, vreme i relevantan aggregate; nema raw email, IP, token, cookie, authorization header, provider payload ni child podatak.

Outbox: `identity.authorization_invalidated` obavezno se upisuje u istoj DB transakciji sa version bump-om; potrošači su cache/realtime invalidator i M03/M05/M07 projekcije. To je registry-allow-listed PLATFORM događaj jer jedan globalni account može imati pristup većem broju škola: `scope_kind=PLATFORM`, `school_id=NULL`, aggregate je `UserAccount`, a payload sadrži samo opaque `user_account_id`, novu `authorization_version`, zatvoren reason i correlation/causation reference. M01 ne čita membership-e i ne emituje po jedan school event. Događaj ima dedupe key `user_account_id:authorization_version`, retry/backoff i dead-letter/recovery iz M21; platform consumer kroz autorizovan application coordinator pronalazi i invalidira sve pogođene tenant projekcije, bez kreiranja pristupa. Outbox je propagation/recovery mehanizam, ne dokaz da je budući request bezbedno odbijen; taj dokaz daje autoritativna version/revocation provera iz AUTH-03/08. Telemetry agregira uspeh/neuspeh/latenciju/provider kategoriju bez PII; security log sa minimalnim hash signalima ima retention M17. Nema email-a u URL-u, logovima ili error body-ju.

## 14. UI i tri klika

M01 površine: `UI-AUTH-01` prijava, `UI-AUTH-02` provider povratak, `UI-AUTH-03` neutralan no-access, `UI-AUTH-04` session/security meni. Prijava → provider → provereni povratak mora korisnika dovesti do sledećeg dozvoljenog koraka u najviše tri korisničke akcije, ne računajući provider interakcije van SOKOLA. Obavezna stanja: loading, cancel, invalid/replayed callback, provider unavailable, expired session, rate-limit, no-access, account inactive, success i safe return-route fallback. Fokus se vraća na naslov poruke; greška je čitljiva screen-reader-u. Nikad se ne prikazuje „nalog ne postoji“.

## 15. Migracija, backfill i rollback

Claude Code prvo mapira postojeći repo na ovaj model. Migracija mora: odvojiti `Person` od `UserAccount` gde nisu odvojeni; uvesti globalni issuer+subject unique; zabraniti više aktivnih naloga za istu Person; version/revocation podatke i audit/outbox; backfill raditi idempotentno, sa izveštajem neusklađenih/red flag slučajeva bez automatskog merge-a. Legacy `PENDING_LINK`/orphan account redovi ne aktiviraju se automatski: mapiraju se na M02 kratkotrajni pokušaj samo uz dokaz i neistekao TTL, inače se stavljaju u exception report i bezbedno onemogućavaju. Aktivne stare sesije bez dokazane identity veze se revoke-u pri cutover-u. Pre irreversible promene postoji backup i forward-recovery plan; rollback ne sme oživeti opozvanu sesiju ili vratiti duplu vezu. Stvarni ORM/migration alat nije propisan.

## 16. Definition of Done

M01 je gotov tek kada schema/guards/testovi dokazuju sve invarijante, atomarno nastajanje naloga i prvog identiteta bez orphan `PENDING_LINK` naloga, kanonski provider registry, kompletne status komande, `LogoutAll` retry posle self-revocation-a, provider mock i negative callback testove, trenutni revoke bez stale-cache prozora, cache/realtime invalidaciju, no-email-linking, cross-tenant-neutral login, rate limit i token redaction. Programer vraća repo/commit/migration head, mapu postojećeg rešenja prema M01, test komande i rezultate, changed-file listu, configuration defaults i poznata provider/legal ograničenja. Realni podaci dece se ne koriste.
