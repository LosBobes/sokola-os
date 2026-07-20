# Alignment: Članarine, uplate i dugovanja

**oblast:** `finansije` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

## Summary

**~5 implemented · 2 partial · ~3 missing.** The strongest backend domain after
events. Real double-entry-flavoured money: billing runs (with preview), charges
carrying due/paid minor-units, and payment recording. The gaps are the
correction paths (charge cancel, payment void) whose reason enums already exist,
a debts view, and the **pricing source** — charges have amounts but nothing
derives them from group pricing (which PRD 04 hasn't modeled).

## Implemented (verified)

- **I1 — Billing run + preview (§ generate fees).** `POST /billing/runs` and
  `POST /billing/runs/preview` → `post_run` / `preview`
  (`apps/api/app/domains/billing/service.py:65,56`); `_compute` shared
  (`service.py:29`). `BillingRun` with `total_minor`, `charge_count`, status
  (`billing/models.py`). Tests `tests/test_billing.py` (3).
- **I2 — Charges with money (§ obligation).** `Charge.amount_due_minor`,
  `amount_paid_minor`, `currency`, `status`, `source_type`, `cancellation_reason`
  (`billing/models.py:43-66`). `GET /charges` → `list_charges` (`service.py:138`).
- **I3 — Record payment (§ uplata).** `POST /charges/{id}/payments` →
  `record_payment` (`apps/api/app/domains/payments/service.py:17`);
  `PaymentRecord`, `PaymentMethod`, `PaymentRecordStatus`, `PaymentVoidReasonCode`
  (`payments/models.py`, `enums.py`). Tests `tests/test_payments.py` (3).
- **I4 — Minor-units + explicit currency discipline (§ finansijski uticaj).**
  `app/common/money.py`, `apps/web/src/lib/money.ts`; default RSD (`config.py:32`).
- **I5 — Idempotent, non-destructive money.** Idempotency spine
  (`tests/test_idempotency.py`); charges carry cancellation reasons rather than
  being deleted (append-only correction posture).

## Partial

- **P1 — Charge cancellation (§ korekcija/otkazivanje).** `ChargeCancellationReasonCode`
  and `ChargeStatus` exist, but no cancel endpoint sets them.
- **P2 — Payment void/refund.** `PaymentVoidReasonCode` exists (`payments/enums.py`),
  no void endpoint.

## Missing (in-scope, not built)

- **M1 — Pricing source.** Billing runs compute charges, but there is no group
  base price / member discount to derive from (PRD 04 M1). Confirm how `_compute`
  currently sources amounts and wire real pricing.
- **M2 — Debts / dugovanja view.** No per-person outstanding-balance endpoint;
  `GET /charges` lists charges but not an aggregated debt view.
- **M3 — Money screen depth (§ ekrani).** Web has `manager/Money.tsx`; parent-facing
  balance and partial-payment flows not verified.

## Open questions

1. Wave 2: charge-cancel + payment-void are low-risk endpoints over existing
   reason enums — quick wins.
2. Pricing (M1) is the real dependency: sequence after PRD 04 pricing lands.
