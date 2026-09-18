---
modul-id: M19
tip: mapa-integracije
status: SPEC_CANDIDATE
---

# M19 — Mapa integracije

| Ugovor | Vlasnik | M19 upotreba | Zabranjeno |
|---|---|---|---|
| Session/logout/revoke | M01 | bootstrap i purge signal | token u localStorage/IndexedDB |
| School context/workspace options | M03 | selection/switch/`context_version` | workspace kao permission ili paralelna `session_generation` |
| School/capability | M04 | navigation eligibility | UI entitlement kao server guard |
| Permission/support | M05 | manifest/search/action filtering | client-only authorization/support bypass |
| Person/guardian | M06/M07 | minimalni display + subject resolver | family graph/search globalno |
| Struktura i operativa | M08–M16 | route/search/dashboard projections | M19 write u owner tabelu |
| Privacy | M17 | index/cache/telemetry policy | novi purpose kroz UI |
| Reports | M18 | dashboard KPI envelope | frontend formula/partial headline |
| Audit/jobs/telemetry | M21 | zajednička infrastruktura | M19 paralelni audit/outbox |
| mySOKOLA | M28 | ponovna upotreba shell principa | M19 kao portal owner |

M19 nema schema FK ka poslovnim modulima osim School tenant reference. Owner događaji asinhrono hrane minimalni SearchDocument; nema reverse domain dependency-ja. Dashboard server composition poziva versioned read portove/batch queries. M19 nikada ne orkestrira poslovnu transakciju.

## Tri klika — merljivi standardni tokovi

| Tok | Početno stanje | Brojane interakcije | Server-confirmed kraj |
|---|---|---|---|
| Današnje prisustvo | Coach Home, aktivna škola, jedan sledeći termin | otvori termin (1), potvrdi predlog (2); grupisana izmena statusa je (3) | M11 receipt |
| Raspored | odgovarajući Home, aktivna škola | otvori Danas/Raspored (1) | autorizovana dnevna lista |
| Finansije | Manager Home, aktivna škola | otvori Finansije (1), opciono detalj jedne obaveze (2) | M12/M18 read sa freshness stanjem |
| Komunikacija | Manager Home sa quick action | Nova poruka (1), unos sadržaja (2), publish confirm (3) | M13 receipt |
| Događaj | Home sa Events karticom | detalj (1), akcija/subjekt na istoj strani (2), confirm (3) | M16 receipt |

Login i izbor škole nisu deo ovih već autentifikovanih standardnih seed-ova, ali se mere kao odvojeni onboarding/context tokovi. Unos složene publike, višestruki eligible subjekti, fee/payment, conflict resolution ili pravna odluka su eksplicitni izuzeci; nisu lažno proglašeni troklik tokovima. Merenje uvek navodi početno stanje, obavezne podatke i confirmation.
