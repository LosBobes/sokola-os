---
tip: kodni-baseline-ugovor
status: REPOSITORY_DISCOVERY_REQUIRED
datum: 2026-09-16
---

# Stvarni kodni baseline

Ovo je **ugovor o obliku**, ne popunjen izveštaj. Svako polje ispod ima `resolution_status=UNRESOLVED` dok Claude Code ne pročita stvarni repo — nijedna vrednost nije izmišljena niti služi kao literalni runtime placeholder.

**Claude Code popunjava ovo automatski iz stvarnog repoa** kao deo prve stavke iz [[00-START-OVDE-PROGRAMER|redosleda]]. Ovo nije ručni zadatak van tehničke izrade i ne blokira dokumentacionu korekciju niti početak tehničke izrade drugih stavki.

## Polja (svako sa istim strukturiranim modelom dok nije popunjeno)

| Polje | `resolution_status` | `source` | `runtime_value` | Fallback dok nije popunjeno | Šta blokira |
|---|---|---|---|---|---|
| Repository | `UNRESOLVED` | `REPOSITORY` | `null` | Dokumentacioni kandidat ostaje važeći; kod se ne pretpostavlja | Blokira samo repo-specifične tvrdnje, migracije i izvršne test dokaze |
| Branch | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Commit SHA | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Datum provere | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Migration head | `UNRESOLVED` | `REPOSITORY` | `null` | Migracije se ne pretpostavljaju — prvo se čita stvarno stanje | Blokira samo migracije koje zavise od nepoznatog head-a, ne čitanje/analizu repoa |
| Framework/runtime | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Baza i ORM | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Auth/OIDC | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Tenant topologija — fizička šema (M03 §4) | `UNRESOLVED` | `REPOSITORY` | `null` | Zajednička šema/schema-per-tenant/DB-per-tenant — zadržati postojeću samo ako dokazivo sprovodi §7 | Blokira samo tvrdnju o topologiji, ne analizu |
| Tenant context store/resolver (M03 §5.3/§12 TEN-PORT-01) | `UNRESOLVED` | `REPOSITORY` | `null` | `SessionTenantContext` implementacija i `ResolveTenantExecutionContext` port moraju postojati pre tvrdnje o guard pipeline-u | Blokira samo tvrdnju o context resolveru |
| DB FK/UNIQUE/RLS/BYPASSRLS stanje (M03 §7) | `UNRESOLVED` | `REPOSITORY` | `null` | Composite tenant FK/UNIQUE; ako RLS postoji, `BYPASSRLS` ne sme biti na app konekciji | Blokira samo tvrdnju o DB-nivo zaštiti |
| Cache tenant izolacija (M03 §11) | `UNRESOLVED` | `REPOSITORY` | `null` | Cache ključ mora uključivati school/viewer/context/security verziju | Blokira samo tvrdnju o cache izolaciji |
| Jobs/outbox tenant izolacija (M03 §11) | `UNRESOLVED` | `REPOSITORY` | `null` | Payload nosi school ID; worker ne koristi "trenutni globalni tenant" | Blokira samo tvrdnju o job/outbox izolaciji |
| Object-storage tenant izolacija (M03 §11) | `UNRESOLVED` | `REPOSITORY` | `null` | Privatni objekat ima tenant partition/reference; signed URL kratko važi | Blokira samo tvrdnju o storage izolaciji |
| Realtime tenant izolacija (M03 §11) | `UNRESOLVED` | `REPOSITORY` | `null` | Subscription iz `TenantExecutionContext`; switch/revoke zatvara kanal | Blokira samo tvrdnju o realtime izolaciji |
| Export/report tenant izolacija (M03 §11) | `UNRESOLVED` | `REPOSITORY` | `null` | Export batch pripada jednoj školi; report filter je deo izvora metrike | Blokira samo tvrdnju o export/report izolaciji |
| Lokacije tenant testova (M03 §20/22) | `UNRESOLVED` | `REPOSITORY` | `null` | Automatizovan cross-tenant test sa najmanje dve škole, po deploy-u | Blokira samo tvrdnju da testovi postoje |
| Storage | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Email provider/adapter | `UNRESOLVED` | `REPOSITORY` | `null` | Funkcije koje šalju email vraćaju jasnu grešku dok adapter nije poznat | Blokira samo slanje email-a, ne ostatak sistema |
| Jobs/queue/cron | `UNRESOLVED` | `REPOSITORY` | `null` | Isto kao migration head | Blokira samo konfiguraciju konkretnog job runner-a |
| Test runner | `UNRESOLVED` | `REPOSITORY` | `null` | Ne blokira ništa — čita se pri prvom pokretanju testova | Ništa |
| Build/deploy target | `UNRESOLVED` | `REPOSITORY` | `null` | Ne blokira kodiranje ni sintetički staging | Blokira samo stvarni deploy |
| Staging URL/build ID | `UNRESOLVED` | `REPOSITORY` | `null` | Isto | Isto |
| Napomena o dostupnosti | `UNRESOLVED` | `REPOSITORY` | `null` | Ne blokira ništa | Ništa |

**Ko sme da promeni:** Claude Code, automatski, čitanjem repoa — nije ručno polje za popunjavanje od strane bilo koje osobe. **Audit:** promena ovog dokumenta se evidentira u istoriji koda (commit koji ga ažurira). **OFF/ON test:** N/P — ovo je deskriptivni dokument, ne runtime prekidač.

## Pravilo aktuelnosti

Ovaj dokument postaje jedini aktuelni tehnički baseline kada implementacioni agent popuni polja dokazima iz stvarnog repozitorijuma, migracija i test komandi. Dok se to ne desi, sva polja ostaju `UNRESOLVED` i ne predstavljaju pretpostavljeno stanje.
