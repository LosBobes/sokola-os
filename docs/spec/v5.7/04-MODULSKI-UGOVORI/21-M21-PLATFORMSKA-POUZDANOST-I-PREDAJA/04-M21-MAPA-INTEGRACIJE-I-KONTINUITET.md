---
modul-id: M21
tip: mapa-integracije-kontinuitet
status: SPEC_CANDIDATE
---

# M21 — Mapa integracije i kontinuitet

Svaki M01–M20 owner modul poseduje poslovnu komandu, event schema i poslovnu retry semantiku. U svojoj transakciji upisuje audit/outbox/receipt kroz M21 standard. M21 publisher/job runner/storage/telemetry ne poziva nazad owner command radi „potvrde” i ne postaje business source of truth. Consumer poseduje inbox i efekat svog modula.

M17 određuje retention/legal hold kroz versioned policy snapshot koji application coordinator predaje M21 disposition portu; M21 domen ne uvozi M17 šemu niti poziva M17 nazad. M21 izvršava tehničko zadržavanje/disposition nad svojim zapisima bez davanja read pristupa. M05 određuje audit/operations permissions. M03 tenant context ostaje autoritet; platform-null scope je registry izuzetak. M28 i budući moduli ponovo koriste isti standard, ne prave paralelni audit/job sistem.

Aktivni M00–M20 i M28 ugovori ostaju zasebni domain autoriteti. M21 zaključava 40 konkretnih job ključeva (39 H0 + jedan M28 pre-pilot default-disabled), audit/telemetry razdvajanje, at-least-once transport sa monotonim producer stream-om, logical execution/immutable attempt model, lease/fencing, PII-free operacije, dokazivi RPO/RTO pilot cilj, immutable release evidence i clean handover bez ličnih imena. `SPEC_CANDIDATE` nije implementacioni PASS.
