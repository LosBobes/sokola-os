import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { Charge, ChargeStatus, Page } from "../../api/types";
import { useSession } from "../../auth/session";
import { BrandMark } from "../../components/shell";
import {
  Card,
  EmptyState,
  InlineNotice,
  LoadingState,
  SegmentedControl,
  StatusBadge,
  SystemState,
} from "../../components/ui";
import { PaymentSlipDialog } from "../../components/PaymentSlipDialog";
import { useAsync } from "../../hooks/useAsync";
import { formatDate, isPastDue } from "../../lib/format";
import { formatMinor } from "../../lib/money";
import "./money.css";

interface Child {
  person_id: string;
  display_name: string;
}

type Tab = "obaveze" | "uplate";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * P03, Roditelj Finansije. Read-only: no "platio sam" action, no editing.
 * The parent only sees totals and status; recording a payment stays a
 * manager-side action (apps/web/src/routes/manager/Money.tsx).
 */
export function ParentMoneyPage() {
  const { activeContext } = useSession();
  const orgName = activeContext?.organization_name ?? "";

  const children = useAsync(() => api.get<Child[]>("/parent/children"), []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("obaveze");

  const list = children.data ?? [];
  const activeId = list.some((c) => c.person_id === selectedId) ? selectedId : (list[0]?.person_id ?? null);
  const activeChild = list.find((c) => c.person_id === activeId) ?? null;

  // GET /charges supports a `person_id` filter (see schema.d.ts →
  // operations.listCharges.parameters.query), so obligations are scoped to
  // the selected child from the parent side already.
  const charges = useAsync(
    () =>
      activeId
        ? api.get<Page<Charge>>(`/charges?person_id=${encodeURIComponent(activeId)}&limit=100`)
        : Promise.resolve<Page<Charge>>({ items: [], total: 0, limit: 0, offset: 0 }),
    [activeId],
  );

  if (children.loading) return <LoadingState label="Učitavanje…" />;

  return (
    <div>
      <div className="money-topbar">
        <BrandMark />
        <div className="money-topbar__text">
          <h1 className="money-topbar__title">Finansije</h1>
          <span className="money-topbar__org">{orgName}</span>
        </div>
      </div>

      {children.error ? <SystemState error={children.error} /> : null}

      {!children.error && list.length === 0 ? (
        <EmptyState>Nema dece povezane sa vašim nalogom u ovoj školi.</EmptyState>
      ) : null}

      {list.length > 0 ? (
        <>
          <ChildSelector
            children={list}
            active={activeChild}
            onPick={setSelectedId}
          />

          <BalanceHero state={charges} />

          <SegmentedControl
            ariaLabel="Prikaz finansija"
            value={tab}
            onChange={setTab}
            className="money-tabs"
            options={[
              { value: "obaveze", label: "Obaveze" },
              { value: "uplate", label: "Uplate" },
            ]}
          />

          {tab === "obaveze" ? <ObligationsList state={charges} /> : <PaymentsTab />}
        </>
      ) : null}
    </div>
  );
}

function ChildSelector({
  children,
  active,
  onPick,
}: {
  children: Child[];
  active: Child | null;
  onPick: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const name = active?.display_name ?? "-";

  return (
    <div className="money-childpicker" ref={ref} data-cy="child-selector">
      <div className="money-childpicker__current">
        <span className="money-childpicker__avatar" aria-hidden="true">
          {name.trim().charAt(0).toUpperCase() || "?"}
        </span>
        <span className="money-childpicker__name">{name}</span>
      </div>
      {children.length > 1 ? (
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          data-cy="child-selector-toggle"
        >
          Promeni
        </button>
      ) : null}
      {open && children.length > 1 ? (
        <div className="money-childpicker__pop" role="menu">
          {children.map((c) => (
            <button
              key={c.person_id}
              type="button"
              role="menuitem"
              className={cx("money-childpicker__item", c.person_id === active?.person_id && "is-active")}
              onClick={() => {
                onPick(c.person_id);
                setOpen(false);
              }}
              data-cy={`child-selector-option-${c.person_id}`}
            >
              {c.display_name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function BalanceHero({ state }: { state: ReturnType<typeof useAsync<Page<Charge>>> }) {
  const items = state.data?.items ?? [];
  const currency = items[0]?.currency ?? "RSD";
  const remainingMinor = items
    .filter((c) => c.status !== "CANCELLED")
    .reduce((sum, c) => sum + (c.amount_due_minor - c.amount_paid_minor), 0);
  const outstanding = items.filter(
    (c) => c.status === "OPEN" || c.status === "PARTIALLY_PAID",
  );
  const openCount = outstanding.length;
  // The earliest deadline still ahead of the family, across everything unpaid.
  // Charges with no due date simply do not compete for the slot.
  const nextDue = outstanding
    .map((c) => c.due_date)
    .filter((d): d is string => Boolean(d))
    .sort()[0];

  return (
    <div className="money-hero" data-cy="money-hero">
      <div className="money-hero__eyebrow">Ukupno preostalo</div>
      <div className="money-hero__amount" data-cy="money-hero-amount">
        {state.loading ? "…" : formatMinor(remainingMinor, currency)}
      </div>
      {state.error ? (
        <InlineNotice tone="error">Zaduženja trenutno nije moguće učitati.</InlineNotice>
      ) : (
        <div className="money-hero__stats">
          <div className="money-hero__stat">
            <span className="money-hero__stat-label">Otvorene obaveze</span>
            <span className="money-hero__stat-value" data-cy="money-hero-open-count">
              {state.loading ? "-" : openCount}
            </span>
          </div>
          <div className="money-hero__stat">
            <span className="money-hero__stat-label">Sledeći rok</span>
            <span className="money-hero__stat-value" data-cy="money-hero-next-due">
              {nextDue ? formatDate(nextDue) : "Nije određen"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

type ChargeTone = "success" | "warning" | "error" | "neutral";

const STATUS_META: Record<ChargeStatus, { label: string; tone: ChargeTone }> = {
  OPEN: { label: "Neplaćeno", tone: "warning" },
  PARTIALLY_PAID: { label: "Delimično", tone: "warning" },
  PAID: { label: "Plaćeno", tone: "success" },
  CANCELLED: { label: "Otkazano", tone: "neutral" },
};

/*
 * "Dospelo" is a claim about time, not about payment state: an unpaid charge
 * whose deadline is next month has not fallen due. It is shown only when a due
 * date exists and has passed , and the row prints that date right beside it.
 */
function chargeStatusView(charge: Charge): { label: string; tone: ChargeTone } {
  const outstanding = charge.status === "OPEN" || charge.status === "PARTIALLY_PAID";
  if (outstanding && isPastDue(charge.due_date)) return { label: "Dospelo", tone: "error" };
  return STATUS_META[charge.status];
}

function ObligationsList({ state }: { state: ReturnType<typeof useAsync<Page<Charge>>> }) {
  /*
   * The uplatnica belongs on the parent surface most of all: they are the ones
   * who scan the code. It only pre-fills their banking app , the school still
   * confirms the payment by hand after checking its account.
   */
  const [slipFor, setSlipFor] = useState<Charge | null>(null);

  if (state.loading) return <LoadingState />;
  if (state.error) return <SystemState error={state.error} />;

  const items = (state.data?.items ?? []).slice().sort((a, b) => {
    const rank = (s: ChargeStatus) => (s === "OPEN" || s === "PARTIALLY_PAID" ? 0 : s === "PAID" ? 1 : 2);
    return rank(a.status) - rank(b.status);
  });

  if (items.length === 0) return <EmptyState>Nema zaduženja za izabrano dete.</EmptyState>;

  return (
    <div className="money-oblig-list" data-cy="obligation-list">
      {items.map((c) => {
        const meta = chargeStatusView(c);
        const remaining = c.amount_due_minor - c.amount_paid_minor;
        const settled = c.status === "PAID" || c.status === "CANCELLED";
        return (
          <section className="money-oblig-row" key={c.id} data-cy="obligation-row">
            <div className="money-oblig-row__top">
              {/* Charges carry only `description`, no separate period field
                  in the API yet, shown as the row title. */}
              <span className="money-oblig-row__title">{c.description}</span>
              <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>
            </div>
            <div className="money-oblig-row__grid">
              <div>
                <span className="money-oblig-row__field-label">Ukupno</span>
                <span className="money-oblig-row__field-value">{formatMinor(c.amount_due_minor, c.currency)}</span>
              </div>
              <div>
                <span className="money-oblig-row__field-label">Evidentirano</span>
                <span className="money-oblig-row__field-value">{formatMinor(c.amount_paid_minor, c.currency)}</span>
              </div>
              <div>
                <span className="money-oblig-row__field-label">Preostalo</span>
                <span className="money-oblig-row__field-value">{formatMinor(remaining, c.currency)}</span>
              </div>
              <div>
                <span className="money-oblig-row__field-label">Rok</span>
                <span className="money-oblig-row__field-value">
                  {c.due_date ? formatDate(c.due_date) : "-"}
                </span>
              </div>
            </div>
            {!settled ? (
              <button
                type="button"
                className="btn btn--secondary money-oblig-row__slip"
                onClick={() => setSlipFor(c)}
                data-cy="obligation-slip"
              >
                Uplatnica sa QR kodom
              </button>
            ) : null}
          </section>
        );
      })}
      {slipFor ? (
        <PaymentSlipDialog chargeId={slipFor.id} onClose={() => setSlipFor(null)} />
      ) : null}
    </div>
  );
}

function PaymentsTab() {
  return (
    <Card title="Uplate">
      {/* The API only exposes POST /charges/{id}/payments (recording a
          payment): there is no GET endpoint to list payments yet, so a
          parent-facing payment history can't be built honestly today.
          Documented as a known gap in the PR description. */}
      <InlineNotice tone="info">
        Istorija uplata još nije dostupna: API trenutno nema način da se povuče spisak uplata po detetu ili
        zaduženju. Iznos „Evidentirano" po obavezi je vidljiv u kartici Obaveze.
      </InlineNotice>
    </Card>
  );
}
