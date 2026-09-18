---
modul-id: M20
tip: mapa-integracije
status: SPEC_CANDIDATE
---

# M20 — Mapa integracije

M20 čuva samo staging/progress i trajni cross-batch business-key receipt. Onboarding kompozicija čita M04 School, M02 initial invitation, M01 account, M06 membership, M05 owner role, M08 structure, M09 assignments/enrollments, M10 schedule, M12 finance config i M15/M17 readiness činjenice. Import execute poziva M06→M07→M09 owner portove u lokalnoj row transakciji; nijedan owner modul ne zavisi od M20 kandidata. Owner moduli zadržavaju svoje entitete, validacije, permission-e, audit i događaje; M20 receipt samo sprečava ponavljanje iste poslovne namere. M21 pruža scan/job/audit/outbox/storage lifecycle, ali M20 poseduje batch/row semantiku.

M18 dobija činjenice samo iz owner događaja posle commit-a. M19 prikazuje progress, ali ne parsira fajl niti čuva PII. M28 ne menja import scope.

Zvanični CSV/XLSX header, tipovi, normalizacija, hash, guardian verification i owner permission skup nalaze se samo u [[05-M20-IMPORT-SCHEMA-V1]].
