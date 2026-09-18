---
modul-id: M18
tip: mapa-integracije
status: SPEC_CANDIDATE
---

# M18 — Mapa integracije

## Ulazni portovi

| Vlasnik | Činjenice koje M18 sme da projektuje | Zabranjeno |
|---|---|---|
| M03/M04/M05 | tenant context, school zone/currency/status, permission/authorization version | client school kao autoritet; Organization-wide school merge |
| M06/M07 | opaque participant/guardian subject facts za guard | kontakt, health, automatsko spajanje porodica |
| M08/M09 | branch/program/location/space/group/enrollment/capacity facts | paralelni master nazivi/objekti |
| M10 | occurrence status/instant/resource fact | M18 menja termin |
| M11 | roster/session/effective attendance status/version | UNRECORDED=ABSENT; event attendance |
| M12 | assessment/obligation/effective allocation/credit ledger projection | float, FX, PaymentRecord=prihod, menjanje ledgera |
| M13/M14 | published communication root i terminal delivery outcome | raw body, delivered=read |
| M16 | event origin/registration/event-attendance facts | INTERESTED=participant; M11 mešanje |
| M17 | purpose, retention, suppression/deletion policy | analytics kao novi pravni osnov |
| M21 | audit/outbox/job/telemetry platform | M18 paralelna infrastruktura |

Owner modul emituje outbox; M18 asinhrono i idempotentno gradi projection. Interaktivni query ne radi N+1 pozive ka owner modulima. Drill-down radi jedan batch-resolve dozvoljenih opaque ID-jeva posle guard-a. Nema owner→M18 tvrde zavisnosti i nema M18→owner write-a, zato nema ciklusa.

## Potrošači i platforma

M19 je jedini H0 poslovni potrošač M18 i koristi samo agregatne dashboard/query ugovore. M20 ne čita M18 i ne koristi report kao import odluku: M18 nezavisno projektuje owner događaje tek posle owner commit-a, dok preview candidate nikad nije M18 fact. M28 Basic nema M18 dependency; buduća personal-analytics površina zahteva novu M28/M18 reviziju i feature flag. M21 pruža outbox/inbox/job/audit/telemetry infrastrukturu M18-u, ali ne čita M18 business rezultat i ne zavisi od njega. Nijedan potrošač ne koristi M18 rezultat kao poslovni command input.

## Refresh i konzistentnost

Standard: near-real-time projection target ≤60s za schedule/attendance/events/communication i ≤120s finance; to je SLO, ne lažna garancija. Ako watermark ne dokazuje kompletnost, freshness se menja. `GetSchoolOverview` može vratiti sekcije sa odvojenim watermark-ima, ali ne sme izračunati cross-section KPI iz različitih as-of instanata bez `PARTIAL` oznake.

## UX ugovor

Početni ekran: period + sedam kartica/sekcija, najviše tri interakcije do standardnog drill-down-a. Svaka kartica prikazuje vrednost, jedinicu, period, freshness i „Kako se računa”. Nema zeleno/crveno rangiranje deteta ili trenera. Empty, unavailable, suppressed i zero su različita stanja. Kritičan finance broj zahteva serversku potvrdu i ne koristi optimistic final success.
