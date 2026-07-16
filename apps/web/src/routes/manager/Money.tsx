import { useState } from "react";
import { api, newIdempotencyKey } from "../../api/client";
import type { BillingPreview, BillingRun, Charge, Group, Page, Payment } from "../../api/types";
import { PageHeader } from "../../components/shell";
import { ConfirmDialog, EmptyState, LoadingState, StatusBadge, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { formatMinor } from "../../lib/money";

export function MoneyPage() {
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const charges = useAsync(() => api.get<Page<Charge>>("/charges"), []);
  return (
    <div>
      <PageHeader title="Finansije" />
      <BillingRunForm groups={groups.data?.items ?? []} onPosted={charges.reload} />
      <ChargeList state={charges} onPaid={charges.reload} />
    </div>
  );
}

function BillingRunForm({ groups, onPosted }: { groups: Group[]; onPosted: () => void }) {
  const [groupId, setGroupId] = useState("");
  const [amountMajor, setAmountMajor] = useState(3000);
  const [description, setDescription] = useState("Članarina");
  const [period, setPeriod] = useState("2026-09");
  const [preview, setPreview] = useState<BillingPreview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function body() {
    return {
      group_id: groupId,
      amount_minor: Math.round(amountMajor * 100),
      description,
      period_label: period,
    };
  }

  async function doPreview(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setPreview(await api.post<BillingPreview>("/billing/runs/preview", body()));
    } catch (err) {
      setError(err);
    }
  }

  async function post() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      await api.post<BillingRun>(
        "/billing/runs",
        { ...body(), preview_hash: preview.preview_hash },
        newIdempotencyKey(),
      );
      setPreview(null);
      onPosted();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" style={{ marginBottom: "var(--space-4)" }}>
      <h2>Obračun članarina</h2>
      {error ? <SystemState error={error} /> : null}
      <form onSubmit={doPreview}>
        <div className="field">
          <label htmlFor="b-group">Grupa</label>
          <select id="b-group" value={groupId} onChange={(e) => setGroupId(e.target.value)} required data-cy="billing-group">
            <option value="">Izaberi grupu…</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="b-amount">Iznos po članu (RSD)</label>
          <input id="b-amount" type="number" min={1} value={amountMajor} onChange={(e) => setAmountMajor(Number(e.target.value))} data-cy="billing-amount" />
        </div>
        <div className="field">
          <label htmlFor="b-desc">Opis</label>
          <input id="b-desc" value={description} onChange={(e) => setDescription(e.target.value)} data-cy="billing-desc" />
        </div>
        <div className="field">
          <label htmlFor="b-period">Period</label>
          <input id="b-period" value={period} onChange={(e) => setPeriod(e.target.value)} data-cy="billing-period" />
        </div>
        <button className="btn btn--secondary" type="submit" data-cy="billing-preview">
          Pregledaj obračun
        </button>
      </form>

      <ConfirmDialog
        open={preview !== null}
        title="Proknjiži obaveze"
        confirmLabel="Proknjiži"
        busy={busy}
        onCancel={() => setPreview(null)}
        onConfirm={() => void post()}
      >
        <p data-cy="billing-preview-summary">
          Biće kreirano <strong>{preview?.items.length ?? 0}</strong> zaduženja, ukupno{" "}
          <strong>{preview ? formatMinor(preview.total_minor, preview.currency) : ""}</strong>.
        </p>
      </ConfirmDialog>
    </section>
  );
}

function ChargeList({
  state,
  onPaid,
}: {
  state: ReturnType<typeof useAsync<Page<Charge>>>;
  onPaid: () => void;
}) {
  const [payFor, setPayFor] = useState<Charge | null>(null);
  if (state.loading) return <LoadingState />;
  if (state.error) return <SystemState error={state.error} />;
  const items = state.data?.items ?? [];
  if (items.length === 0) return <EmptyState>Nema zaduženja.</EmptyState>;

  const tone = (s: Charge["status"]) =>
    s === "PAID" ? "success" : s === "PARTIALLY_PAID" ? "warning" : "info";

  return (
    <section className="card">
      <h2>Zaduženja</h2>
      <table className="data" data-cy="charge-list">
        <thead>
          <tr>
            <th>Opis</th>
            <th>Dug</th>
            <th>Plaćeno</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id} data-cy="charge-row">
              <td>{c.description}</td>
              <td>{formatMinor(c.amount_due_minor, c.currency)}</td>
              <td>{formatMinor(c.amount_paid_minor, c.currency)}</td>
              <td>
                <StatusBadge tone={tone(c.status)}>{c.status}</StatusBadge>
              </td>
              <td>
                {c.status !== "PAID" && c.status !== "CANCELLED" ? (
                  <button className="btn btn--secondary" onClick={() => setPayFor(c)} data-cy="charge-pay">
                    Uplata
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {payFor ? (
        <PaymentDialog
          charge={payFor}
          onClose={() => setPayFor(null)}
          onPaid={() => {
            setPayFor(null);
            onPaid();
          }}
        />
      ) : null}
    </section>
  );
}

function PaymentDialog({
  charge,
  onClose,
  onPaid,
}: {
  charge: Charge;
  onClose: () => void;
  onPaid: () => void;
}) {
  const outstanding = charge.amount_due_minor - charge.amount_paid_minor;
  const [amountMajor, setAmountMajor] = useState(outstanding / 100);
  const [method, setMethod] = useState("CASH");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function pay() {
    setBusy(true);
    setError(null);
    try {
      await api.post<Payment>(
        `/charges/${charge.id}/payments`,
        { amount_minor: Math.round(amountMajor * 100), method },
        newIdempotencyKey(),
      );
      onPaid();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      title="Evidentiraj uplatu"
      confirmLabel="Sačuvaj uplatu"
      busy={busy}
      onCancel={onClose}
      onConfirm={() => void pay()}
    >
      {error ? <SystemState error={error} /> : null}
      <p>Preostali dug: {formatMinor(outstanding, charge.currency)}</p>
      <div className="field">
        <label htmlFor="pay-amount">Iznos (RSD)</label>
        <input id="pay-amount" type="number" min={1} value={amountMajor} onChange={(e) => setAmountMajor(Number(e.target.value))} data-cy="pay-amount" />
      </div>
      <div className="field">
        <label htmlFor="pay-method">Način</label>
        <select id="pay-method" value={method} onChange={(e) => setMethod(e.target.value)} data-cy="pay-method">
          <option value="CASH">Gotovina</option>
          <option value="BANK_TRANSFER">Uplatnica / transfer</option>
          <option value="CARD_EXTERNAL">Kartica</option>
        </select>
      </div>
    </ConfirmDialog>
  );
}
