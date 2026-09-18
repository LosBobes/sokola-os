---
modul-id: M21
tip: handover-checklist
status: SPEC_CANDIDATE
---

# M21 — Handover checklist

Programerski paket mora sadržati: clean source/commit; dependency lock; setup/build/test komande; config schema i `.env.example` bez secrets; module/dependency map; DB schema/migration head/backfill/forward recovery; synthetic two-tenant seed; QA manifest; audit/outbox/jobs katalog; storage/retention; observability alerts/runbooks; backup i restore rehearsal; deploy/rollback/kill-switch; SBOM/licenses/security scan; known risks; changed files/migrations/test results generisane iz stvarnog rada.

Zabranjeno: lična imena, interni razgovori, recovery promptovi, istorijski deltas, realni PII, credentials, lažni test rezultat, `IMPLEMENTED` bez repo dokaza, zahtev da vlasnik ručno piše tehnički izveštaj.

Pilot verdict je deterministički `GO|NO_GO`. `GO` zahteva sve H0 testove, M28 zaseban pre-pilot acceptance ako se pilotira, pravne/privacy potvrde, restore rehearsal, tenant/auth/security PASS, monitoring/runbooks/kill switch i allowlist. Nedostajući dokaz je `NO_GO`, ali ne blokira nastavak kodiranja na sintetičkim podacima.
