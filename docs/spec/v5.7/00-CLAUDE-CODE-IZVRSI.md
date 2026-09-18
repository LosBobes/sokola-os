---
tip: implementation-entrypoint
status: PROGRAMMER_CANDIDATE
scope: [M00-M21, M28]
code-status: CODE_REPOSITORY_UNVERIFIED
datum: 2026-09-16
---

# SOKOLA OS v5.7 — izvršna instrukcija za Claude Code

Radi u postojećem SOKOLA repozitorijumu. Ovaj paket je poslovni i acceptance autoritet; stvarni repo određuje stack, framework, ORM, API stil, strukturu foldera, queue/cache/storage adaptere i deployment mehanizam.

## 1. Prvo inspect i baseline

1. Pročitaj `00-START-OVDE-PROGRAMER.md`, aktivne DCR-ove, M00, zatim master+QA/integration dokumenta redosledom iz start fajla.
2. Evidentiraj branch, commit, migration head, runtime/framework, bazu/ORM, auth/OIDC, tenant/RBAC, rute, jobs/outbox, storage/PWA i tačne build/lint/typecheck/test komande u `CURRENT-CODE-BASELINE.md`.
3. Pokreni postojeće proverljive komande pre izmene i sačuvaj rezultat. Ne predstavljaj postojeći pad kao posledicu nove izmene.
4. Mapiraj svaku oblast kao `PRESERVE`, `ADAPT`, `IMPLEMENT`, `REMOVE_CONFLICT` ili `VERIFY_IN_REPO` sa putanjom/dokazom.
5. Sačuvaj validan postojeći kod. Ne radi big-bang rewrite, novi framework ili paralelni auth/tenant/RBAC/finance model samo radi podudaranja imena iz specifikacije.

## 2. Implementacioni talasi

Fizički raspored prilagodi repou, ali ne aktiviraj use-case pre njegovih guardova i schema prerequisites:

1. zajednički M00/M21 portovi: transakcija, receipt, audit, outbox/inbox, clock, exact decimal, storage i observability;
2. Foundation schema/use-case: M04 School anchor → M06 → M01 → M03 → M05 → M07 → M02 → odloženi M04 cross-module constraints;
3. Operational Core: M08 → M09 → M10 → M11 → M16 → M12 → M15 → M13 → M14;
4. završni H0: M17 privacy, M18 report projections, M19 shell/search/PWA, M20 onboarding/import i završne M21 job/DR/release veze;
5. M28 mySOKOLA Basic tek nad stabilnim owner portovima; schema se može pripremiti ranije, ali feature ostaje default OFF i nije H0 PASS uslov.

Svaki talas uključuje backward-safe migraciju, backfill/reconciliation, contract/integration/security testove i definisan rollback ili forward-recovery. Ne ostavljaj period u kome novi kod radi nad nepotpunim constraint-ima bez fail-closed feature stanja.

## 3. Obavezne tehničko-poslovne garancije

- Svaki protected request: M01 session/revocation → M03 exact School/context version → M04 status/entitlement gde je primenljivo → M05 exact permission → owner resource guard → M07/owner subject guard → pre-commit recheck za HIGH/CRITICAL write.
- Cross-tenant/skriven subject i nepostojeći target imaju safe-404 ekvivalenciju pre count/search/page/cache-a. UI, Organization, role label, URL/header/JWT claim ili cache nisu authorization dokaz.
- Tenant zapis/veza koristi dokazivu school izolaciju kroz query i composite FK/UNIQUE gde target pripada tenant-u; isti scope važi za cache, job, outbox/inbox, object storage, realtime i export.
- Svaki write ima canonical payload hash, idempotency receipt, expected version gde menja red, determinističan lock redosled i jednu lokalnu transakciju za business upise+audit+outbox+receipt. Timeout/retry ne pravi drugi poslovni efekat.
- Novac je `NUMERIC(18,2)` ili dokazivo ekvivalentan exact decimal, API/import/export/event decimal string + ISO 4217; nema float/double, skrivene FX konverzije ni paralelnog minor-unit mastera. M12 ledger/credit/korekcije su append-only.
- Trenuci su UTC/TIMESTAMPTZ; tenant ima IANA zonu; recurrence čuva lokalnu nameru i determinističan DST resolver.
- M11 jedini ima offline mutation queue. Lease/session/context/access expiry i reconnect moraju fail-closed odbiti stale sync i ukloniti lokalni privatni podatak najkasnije na lokalno proverljivom roku.
- M13 poseduje ručnu komunikaciju; M14 je idempotentni outbox consumer automatskih notifikacija. Producer ne zove M14 direktno.
- M15 document version/evidence su immutable/append-only; M15/M17 consent evidence nastaje atomarno; svaki download range ponovo autorizuje kratku session-bound sesiju.
- M16 poseduje Event lifecycle, ne cenu; fee registration koristi neutralni M16+M12 coordinator u jednom local commit-u. M16 ne poziva M12/M14/M15 domain handler niti upisuje njihove tabele.
- M18 ne izmišlja broj: source gap daje `PARTIAL|UNAVAILABLE`; effective/recorded cutoff i version hash su dokazivi; child-derived cohort <5 koristi suppression+complementary suppression.
- M19 search filteriše permission/subject pre matching, suggestion, count i rank. Private PWA payload nije offline cache. Tri klika važe samo za dokumentovano početno stanje i nikad ne uklanjaju pravnu/sigurnosnu potvrdu.
- M20 import schema je samo v1 iz paketa, create/link only, bez formula/makroa/email auto-linka; staging row i trajni business-key receipt su odvojeni; partial batch ima tačan zbir svih ishoda.
- M21 koristi tačno 40 job definicija iz kataloga v1: 39 H0 i jednu M28 expiry definiciju koja je default-disabled. Lease/fencing, producer stream gap, M04 agreement-shard transition, M20 issue-report generation, immutable audit seal+append-only verification, dead-letter dual control, `FULL_SERVICE` backup/isolated restore i release evidence moraju biti stvarno testirani.
- M28 zahteva entitlement + ACTIVE pilot + runtime flag + portal permission + aktuelni guardian/payer basis. Payer ne postaje guardian; jedna private response projekcija nikad ne sadrži više škola; critical action čeka owner server receipt.
- Runtime identifikatori/kod/schema su English ASCII; UI stringovi su i18n; korisnički podaci ostaju UTF-8. Log/metric/event/dead-letter ne sadrže token, credential, raw kontakt, child ime, dokument/poruku, bank reference ili iznos osim kada owner audit ugovor izričito zahteva zaštićen dokaz.

## 4. UX i aplikacioni API

Implementiraj manager, instructor/coach i guardian/payer dashboard prema M19/M28 screen ugovorima. Standardne dnevne akcije ciljaju najviše tri primarne interakcije samo iz navedenog autentifikovanog/tenant-selected početnog stanja. Jedna korisnička poslovna namera koristi jedan application endpoint; frontend ne orkestrira per-row attendance, fee registration, evidence ili multi-owner transakciju.

Optimistic UI je dozvoljen samo gde owner ugovor dozvoli i mora imati vidljiv pending/error recovery. Finansija, document/evidence, event registration, access/security i drugi kritični write ne smeju izgledati konačno uspešno pre server receipt-a.

## 5. Test i migracioni dokaz

Implementiraj sve QA scenarije u paketu. Kritični minimum uključuje dve škole i iste opaque ID oblike; allowed/denied/safe-404; guardian-vs-payer; support/break-glass; stvarne paralelne transakcije; idempotency replay/mismatch/in-progress; failure injection posle svakog planiranog upisa; FK/UNIQUE/CHECK; decimal property/reconciliation; DST gap/overlap; offline revoke/expiry; duplicate/out-of-order/gap event; storage ticket/range race; parser security; report bitemporalnost/suppression; job lease/fencing; backup+isolated restore; browser multi-tab/context/a11y/performance profil.

Ne označavaj QA kao PASS zato što scenario postoji u Markdown-u. Za svaki izvršeni skup navedi komandu, exit code, passed/failed/skipped/flaky, commit, migration head, seed/config hash i dokazni artifact. Jedan skipped CRITICAL test je neuspeh acceptance-a.

## 6. Konflikt ili bezbednosni nalaz

Ako repo otkrije novu stvarnu kontradikciju, ne menjaj kanon tiho. Zapiši `CHALLENGE_NOT_APPLIED` sa: fajlom/paragrafom, repo putanjom i reprodukcijom, posledicom, minimalnim predlogom i stavkama koje možeš bezbedno nastaviti. Zaustavi samo zavisnu opasnu mutaciju; završi sve nezavisno.

## 7. Završni izlaz

Vrati jedan tehnički izveštaj sa: popunjenim baseline-om; klasifikacijom i putanjama; promenjenim fajlovima; svim migracijama, backfill/reconciliation i deploy/rollback/forward-recovery redosledom; rezultatima komandi/testova; tenant/security/privacy dokazom; M28 flag/pilot stanjem; preostalim blockerima i `CHALLENGE_NOT_APPLIED` listom. Ne proglašavaj `IMPLEMENTED`, `COMPLETE`, production ili pilot `GO` bez svih pripadajućih stvarnih dokaza.
