import { useMemo, useRef, useState, type FormEvent } from "react";
import { api, newIdempotencyKey } from "../../api/client";
import type { BillingPreview, BillingRun, Charge, Group, Page, Payment, PersonSummary } from "../../api/types";
import { PageHeader } from "../../components/shell";
import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  FilterBar,
  FilterChip,
  LoadingState,
  SectionHeader,
  StatTile,
  StatusBadge,
  SystemState,
  TableContainer,
} from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { formatMinor } from "../../lib/money";
import "./Money.css";

/*
 * M05 · Finansije.
 *
 * schema.d.ts today only exposes: GET /charges (person_id/limit/offset),
 * POST /charges/{id}/payments, POST /billing/runs(/preview). The richer
 * finance surface referenced by #29 — POST /charges/{id}/cancel,
 * POST /payments/{id}/void, and a debts/aggregate endpoint — is not on
 * main yet (tracked in #9). This screen:
 *  - wires the billing-run preview→post and payment-recording flows that
 *    DO exist,
 *  - skips cancel/void UI entirely rather than fabricating buttons for
 *    endpoints that don't exist (re-check schema.d.ts once #9 lands),
 *  - computes the "debts summary" client-side from the loaded charges page
 *    as a best-effort approximation, clearly labelled as such, pending a
 *    real server-computed aggregate,
 *  - and disables the "Period" filter chip (ChargeResponse carries no
 *    period_label yet, so charges can't honestly be filtered by billing
 *    period) — same "uskoro" degradation pattern used on Grupe/Raspored
 *    for fields the backend doesn't expose yet.
 */

type ChargeStatus = Charge["status"];

const STATUS_LABEL: Record<ChargeStatus, string> = {
  OPEN: "Dospelo",
  PARTIALLY_PAID: "Delimično plaćeno",
  PAID: "Plaćeno",
  CANCELLED: "Otkazano",
};

const STATUS_TONE: Record<ChargeStatus, "success" | "warning" | "info" | "neutral"> = {
  OPEN: "info",
  PARTIALLY_PAID: "warning",
  PAID: "success",
  CANCELLED: "neutral",
};

const STATUS_FILTERS: Array<{ value: ChargeStatus | "ALL"; label: string }> = [
  { value: "ALL", label: "Sve" },
  { value: "OPEN", label: STATUS_LABEL.OPEN },
  { value: "PARTIALLY_PAID", label: STATUS_LABEL.PARTIALLY_PAID },
  { value: "PAID", label: STATUS_LABEL.PAID },
];

function currentPeriodLabel(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function MoneyPage() {
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const people = useAsync(() => api.get<Page<PersonSummary>>("/people"), []);
  const charges = useAsync(() => api.get<Page<Charge>>("/charges?limit=200"), []);

  const peopleMap = useMemo(
    () => Object.fromEntries((people.data?.items ?? []).map((p) => [p.id, p.display_name])),
    [people.data],
  );

  const [statusFilter, setStatusFilter] = useState<ChargeStatus | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const formRef = useRef<HTMLDivElement>(null);

  const items = useMemo(() => charges.data?.items ?? [], [charges.data]);

  const filteredItems = useMemo(() => {
    let list = items;
    if (statusFilter !== "ALL") list = list.filter((c) => c.status === statusFilter);
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter((c) => {
        const name = peopleMap[c.person_id] ?? "";
        return name.toLowerCase().includes(q) || c.description.toLowerCase().includes(q);
      });
    }
    return list;
  }, [items, statusFilter, search, peopleMap]);

  // Client-side debts summary — see file header comment. Not a substitute
  // for a real aggregate endpoint (pagination/limit means this only covers
  // the loaded page; today's /charges?limit=200 is a practical ceiling).
  const summary = useMemo(() => {
    let totalDue = 0;
    let totalPaid = 0;
    let outstanding = 0;
    const debtors = new Set<string>();
    for (const c of items) {
      if (c.status === "CANCELLED") continue;
      totalDue += c.amount_due_minor;
      totalPaid += c.amount_paid_minor;
      const rest = c.amount_due_minor - c.amount_paid_minor;
      if (rest > 0) {
        outstanding += rest;
        debtors.add(c.person_id);
      }
    }
    return { totalDue, totalPaid, outstanding, debtorCount: debtors.size };
  }, [items]);

  const currency = items[0]?.currency ?? "RSD";

  function scrollToForm() {
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    formRef.current?.querySelector<HTMLSelectElement>("select")?.focus();
  }

  return (
    <div>
      <PageHeader
        title="Finansije"
        action={
          <Button onClick={scrollToForm} data-cy="money-new-run">
            Novi obračun
          </Button>
        }
      />
      <p style={{ color: "var(--text-secondary)", marginTop: 0, marginBottom: "var(--space-4)" }}>
        Obaveze, evidencija uplata i dugovanja aktivne škole.
      </p>

      <div className="money-summary" aria-label="Pregled dugovanja">
        <StatTile label="Ukupno zaduženo" value={charges.data ? formatMinor(summary.totalDue, currency) : "—"} />
        <StatTile
          label="Evidentirane uplate"
          value={charges.data ? formatMinor(summary.totalPaid, currency) : "—"}
        />
        <StatTile
          label="Otvoreno dugovanje"
          value={charges.data ? formatMinor(summary.outstanding, currency) : "—"}
          delta={{ label: "Približno — čeka agregat iz #9", tone: "neutral" }}
        />
        <StatTile label="Članovi sa dugom" value={charges.data ? summary.debtorCount : "—"} />
      </div>

      <div ref={formRef}>
        <BillingRunForm groups={groups.data?.items ?? []} onPosted={charges.reload} />
      </div>

      <Card title="Zaduženja" subtitle="Pregled po članu, sa statusom uplate.">
        <FilterBar>
          {STATUS_FILTERS.map((f) => (
            <FilterChip
              key={f.value}
              active={statusFilter === f.value}
              onClick={() => setStatusFilter(f.value)}
              data-cy={`charge-filter-${f.value.toLowerCase()}`}
            >
              {f.label}
            </FilterChip>
          ))}
          <FilterChip
            caret
            disabled
            title="Uskoro — zaduženja još ne nose podatak o periodu obračuna (čeka #9)"
            style={{ opacity: 0.55 }}
          >
            Period
          </FilterChip>
          <div className="field" style={{ margin: "0 0 0 auto", minWidth: 220 }}>
            <input
              type="search"
              placeholder="Pronađi člana ili opis"
              aria-label="Pronađi člana ili opis"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-cy="charge-search"
            />
          </div>
        </FilterBar>

        <ChargeList
          loading={charges.loading}
          error={charges.error}
          total={items.length}
          items={filteredItems}
          peopleMap={peopleMap}
          onPaid={charges.reload}
        />
      </Card>
    </div>
  );
}

function BillingRunForm({ groups, onPosted }: { groups: Group[]; onPosted: () => void }) {
  const [groupId, setGroupId] = useState("");
  const [amountMajor, setAmountMajor] = useState(3000);
  const [description, setDescription] = useState("Članarina");
  const [period, setPeriod] = useState(currentPeriodLabel());
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

  async function doPreview(e: FormEvent) {
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
    <Card
      title="Obračun članarina"
      subtitle="Pregledajte obračun pre nego što se knjiže zaduženja."
      data-cy="billing-run-form"
    >
      {error ? <SystemState error={error} /> : null}
      <form onSubmit={doPreview} className="money-form-grid">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="b-group">Grupa</label>
          <select
            id="b-group"
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
            required
            data-cy="billing-group"
          >
            <option value="">Izaberi grupu…</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="b-amount">Iznos po članu (RSD)</label>
          <input
            id="b-amount"
            type="number"
            min={1}
            value={amountMajor}
            onChange={(e) => setAmountMajor(Number(e.target.value))}
            data-cy="billing-amount"
          />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="b-desc">Opis</label>
          <input
            id="b-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            data-cy="billing-desc"
          />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="b-period">Period</label>
          <input id="b-period" value={period} onChange={(e) => setPeriod(e.target.value)} data-cy="billing-period" />
        </div>
        <Button type="submit" variant="secondary" data-cy="billing-preview">
          Pregledaj obračun
        </Button>
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
    </Card>
  );
}

function ChargeList({
  loading,
  error,
  total,
  items,
  peopleMap,
  onPaid,
}: {
  loading: boolean;
  error: unknown;
  total: number;
  items: Charge[];
  peopleMap: Record<string, string>;
  onPaid: () => void;
}) {
  const [payFor, setPayFor] = useState<Charge | null>(null);

  if (loading) return <LoadingState />;
  if (error) return <SystemState error={error} />;
  if (total === 0) return <EmptyState>Još nema zaduženja. Pokrenite obračun članarina iznad.</EmptyState>;
  if (items.length === 0) return <EmptyState>Nema zaduženja koja odgovaraju filterima.</EmptyState>;

  return (
    <>
      <TableContainer>
        <table className="data" data-cy="charge-list">
          <thead>
            <tr>
              <th>Član</th>
              <th>Opis</th>
              <th>Dug</th>
              <th>Plaćeno</th>
              <th>Preostalo</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => {
              const remaining = c.amount_due_minor - c.amount_paid_minor;
              return (
                <tr key={c.id} data-cy="charge-row">
                  <td>
                    <div className="money-person">
                      <span className="money-person__name">{peopleMap[c.person_id] ?? "Nepoznat član"}</span>
                    </div>
                  </td>
                  <td>{c.description}</td>
                  <td className="money-amount">{formatMinor(c.amount_due_minor, c.currency)}</td>
                  <td className="money-amount">{formatMinor(c.amount_paid_minor, c.currency)}</td>
                  <td className={`money-amount ${remaining > 0 ? "money-amount--debt" : "money-amount--clear"}`}>
                    {formatMinor(remaining, c.currency)}
                  </td>
                  <td>
                    <StatusBadge tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</StatusBadge>
                  </td>
                  <td className="money-cell-actions">
                    {c.status !== "PAID" && c.status !== "CANCELLED" ? (
                      <Button variant="secondary" onClick={() => setPayFor(c)} data-cy="charge-pay">
                        Uplata
                      </Button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableContainer>
      {payFor ? (
        <PaymentDialog
          charge={payFor}
          personName={peopleMap[payFor.person_id] ?? "Nepoznat član"}
          onClose={() => setPayFor(null)}
          onPaid={() => {
            setPayFor(null);
            onPaid();
          }}
        />
      ) : null}
    </>
  );
}

function PaymentDialog({
  charge,
  personName,
  onClose,
  onPaid,
}: {
  charge: Charge;
  personName: string;
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
      <SectionHeader
        title={personName}
        subtitle={charge.description}
        action={<StatusBadge tone={STATUS_TONE[charge.status]}>{STATUS_LABEL[charge.status]}</StatusBadge>}
      />
      <p>Preostali dug: {formatMinor(outstanding, charge.currency)}</p>
      <div className="field">
        <label htmlFor="pay-amount">Iznos (RSD)</label>
        <input
          id="pay-amount"
          type="number"
          min={1}
          value={amountMajor}
          onChange={(e) => setAmountMajor(Number(e.target.value))}
          data-cy="pay-amount"
        />
      </div>
      <div className="field">
        <label htmlFor="pay-method">Način</label>
        <select id="pay-method" value={method} onChange={(e) => setMethod(e.target.value)} data-cy="pay-method">
          <option value="CASH">Gotovina</option>
          <option value="BANK_TRANSFER">Uplatnica / transfer</option>
          <option value="CARD_EXTERNAL">Kartica</option>
          <option value="OTHER">Ostalo</option>
        </select>
      </div>
      {/* Payment cancellation/void has no backing endpoint yet
          (POST /payments/{id}/void — see #9); once it lands this dialog's
          history view is the natural place to wire it. */}
    </ConfirmDialog>
  );
}
