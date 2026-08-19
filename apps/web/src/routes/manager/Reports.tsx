import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { AttendanceSheet, Charge, Group, Page, SessionSummary } from "../../api/types";
import { PageHeader } from "../../components/shell";
import {
  Button,
  CapacityBar,
  Card,
  EmptyState,
  FilterBar,
  FilterChip,
  LoadingState,
  SegmentedControl,
  StatTile,
  SystemState,
} from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { formatMinor } from "../../lib/money";
import "./Reports.css";

/*
 * M12 · Izveštaji.
 *
 * The reporting read-model (#12/#13 "Izveštaji" domain) has not landed , 
 * schema.d.ts has no /reports, /dashboard or /aggregate* path, and the
 * issue itself says so ("Blocked on backend: reporting domain does not
 * exist"). Per plan, this screen therefore:
 *
 *  - renders all SIX stat tiles as an honest "Uskoro" pending state, never
 *    an invented number. Each still links to the closest existing real
 *    screen today (Ljudi/Raspored/Finansije), so "poreklo svakog broja"
 *    (the origin of every number) is clear even while the value is pending.
 *  - derives the "Traži pažnju" list and the completion bar from data that
 *    genuinely exists today: GET /schedule/sessions + per-session
 *    GET /schedule/sessions/{id}/attendance (same technique ManagerHome
 *    already uses for "today"), and GET /charges. Real joins, not mock data.
 *  - leaves the "Prisustvo po nedeljama" line chart wired to the dataviz
 *    skill's mark spec (2px line, 8px ringed end-marker, hairline grid,
 *    single-series → no legend box, hover crosshair + tooltip) but fed
 *    `points={null}`, a weekly attendance series would require re-deriving
 *    business logic (what counts as "present") client-side across many
 *    weeks of sessions, which belongs in the read-model backend, not here.
 *    It renders a clear "grafikon uskoro" note instead of fabricating points.
 *  - keeps the Ogranak/Program/Grupa/Trener scope chips and "Izvezi CSV" as
 *    disabled/"Uskoro" stubs (no backend support for those filters/export
 *    yet); the Danas/Ovaj mesec period control IS real, it drives the
 *    session query the "Traži pažnju" + completion numbers use.
 */

type Period = "today" | "month";

function periodRange(period: Period): { from: string; to: string; label: string } {
  const now = new Date();
  if (period === "today") {
    const from = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const to = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    return { from: from.toISOString(), to: to.toISOString(), label: "danas" };
  }
  const from = new Date(now.getFullYear(), now.getMonth(), 1);
  const to = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  return { from: from.toISOString(), to: to.toISOString(), label: "ovog meseca" };
}

interface AttendanceCompletion {
  loading: boolean;
  finished: number;
  recorded: number;
  unconfirmed: SessionSummary[];
}

/** Real, derived (never fabricated) attendance-completion rollup for the
 *  already-finished sessions in the selected period, same technique as
 *  ManagerHome.useAttendanceRollup, generalised beyond "today". */
function useAttendanceCompletion(sessions: SessionSummary[] | null): AttendanceCompletion {
  const [state, setState] = useState<AttendanceCompletion>({
    loading: true,
    finished: 0,
    recorded: 0,
    unconfirmed: [],
  });

  useEffect(() => {
    if (!sessions) {
      setState({ loading: true, finished: 0, recorded: 0, unconfirmed: [] });
      return;
    }
    const now = Date.now();
    const finished = sessions.filter(
      (s) => s.status !== "CANCELLED" && new Date(s.ends_at).getTime() <= now,
    );
    if (finished.length === 0) {
      setState({ loading: false, finished: 0, recorded: 0, unconfirmed: [] });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    Promise.allSettled(
      finished.map((s) => api.get<AttendanceSheet>(`/schedule/sessions/${s.id}/attendance`)),
    ).then((results) => {
      if (cancelled) return;
      let recorded = 0;
      const unconfirmed: SessionSummary[] = [];
      results.forEach((r, i) => {
        if (r.status !== "fulfilled") return;
        const session = finished[i];
        if (!session) return;
        if (r.value.attendance_version > 0) recorded += 1;
        else unconfirmed.push(session);
      });
      setState({ loading: false, finished: finished.length, recorded, unconfirmed });
    });
    return () => {
      cancelled = true;
    };
  }, [sessions]);

  return state;
}

/* --- Small stroke icons for the stat tiles, matching shell.tsx's style -- */
function TileIcon({ name }: { name: "people" | "calendar" | "percent" | "warning" | "wallet" | "debt" }) {
  const p = {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
  };
  switch (name) {
    case "people":
      return (
        <svg {...p}>
          <circle cx="9" cy="8" r="3" />
          <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
          <path d="M16 5.5a3 3 0 0 1 0 6" />
          <path d="M18.5 19a5 5 0 0 0-3-4.6" />
        </svg>
      );
    case "calendar":
      return (
        <svg {...p}>
          <rect x="3.5" y="5" width="17" height="15" rx="2.5" />
          <path d="M3.5 9.5h17M8 3v4M16 3v4" />
          <path d="M8.5 13.5l2.2 2.2L15.5 11" />
        </svg>
      );
    case "percent":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="9" />
          <path d="M9 15l6-6M9.3 9h.01M14.7 15h.01" />
        </svg>
      );
    case "warning":
      return (
        <svg {...p}>
          <path d="M12 4 21 20H3z" />
          <path d="M12 10v4M12 17h.01" />
        </svg>
      );
    case "wallet":
      return (
        <svg {...p}>
          <rect x="3" y="6" width="18" height="13" rx="2.5" />
          <path d="M3 10.5h18" />
          <path d="M15.5 15h2.5" />
        </svg>
      );
    case "debt":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v5M12 16h.01" />
        </svg>
      );
  }
}

interface ReportStat {
  key: string;
  label: string;
  icon: "people" | "calendar" | "percent" | "warning" | "wallet" | "debt";
  to: string;
  note: string;
}

const STAT_TILES: ReportStat[] = [
  { key: "members", label: "Aktivni članovi", icon: "people", to: "/ljudi", note: "Uskoro · vidi u Ljudima" },
  { key: "sessions", label: "Održani termini", icon: "calendar", to: "/raspored", note: "Uskoro · vidi u Rasporedu" },
  {
    key: "attendance",
    label: "Prisutnih od evidentiranih",
    icon: "percent",
    to: "/raspored",
    note: "Uskoro · vidi u Rasporedu",
  },
  {
    key: "unrecorded",
    label: "Termini bez evidencije",
    icon: "warning",
    to: "/raspored",
    note: "Uskoro · vidi u Rasporedu",
  },
  { key: "payments", label: "Evidentirane uplate", icon: "wallet", to: "/finansije", note: "Uskoro · vidi u Finansijama" },
  { key: "debts", label: "Dospela dugovanja", icon: "debt", to: "/finansije", note: "Uskoro · vidi u Finansijama" },
];

export function ReportsPage() {
  const [period, setPeriod] = useState<Period>("month");
  const range = useMemo(() => periodRange(period), [period]);

  const sessions = useAsync(
    () =>
      api.get<SessionSummary[]>(
        `/schedule/sessions?date_from=${encodeURIComponent(range.from)}&date_to=${encodeURIComponent(range.to)}`,
      ),
    [range.from, range.to],
  );
  const groups = useAsync(() => api.get<Page<Group>>("/groups?limit=100"), []);
  const charges = useAsync(() => api.get<Page<Charge>>("/charges?limit=100"), []);
  const completion = useAttendanceCompletion(sessions.data);

  const groupName = (id: string) => groups.data?.items.find((g) => g.id === id)?.name ?? "-";
  const distinctGroups = new Set(completion.unconfirmed.map((s) => s.group_id)).size;
  const firstUnconfirmed = completion.unconfirmed[0];

  const openCharges = (charges.data?.items ?? []).filter(
    (c) => c.status === "OPEN" || c.status === "PARTIALLY_PAID",
  );
  const outstandingMinor = openCharges.reduce(
    (sum, c) => sum + (c.amount_due_minor - c.amount_paid_minor),
    0,
  );
  const outstandingCurrency = openCharges[0]?.currency ?? "RSD";

  const completionPct = completion.finished > 0 ? Math.round((completion.recorded / completion.finished) * 100) : null;

  return (
    <div>
      <PageHeader
        eyebrow="Operativni uvid"
        title="Izveštaji"
        action={
          <Button
            disabled
            title="Uskoro: izvoz dolazi sa izveštajnim modelom (#12)"
            data-cy="reports-export-csv"
          >
            Izvezi CSV
          </Button>
        }
      />
      <p className="reports-subtitle">Šest pokazatelja za odluke, sa jasnim poreklom svakog broja.</p>

      <FilterBar>
        <SegmentedControl
          ariaLabel="Period izveštaja"
          value={period}
          onChange={setPeriod}
          options={[
            { value: "today", label: "Danas" },
            { value: "month", label: "Ovaj mesec" },
          ]}
        />
        <FilterChip caret disabled title="Uskoro: filter po ogranku (izveštajni backend #12)" style={{ opacity: 0.55 }}>
          Centralni ogranak
        </FilterChip>
        <FilterChip caret disabled title="Uskoro: filter po programu (izveštajni backend #12)" style={{ opacity: 0.55 }}>
          Svi programi
        </FilterChip>
        <FilterChip caret disabled title="Uskoro: filter po grupi (izveštajni backend #12)" style={{ opacity: 0.55 }}>
          Sve grupe
        </FilterChip>
        <FilterChip caret disabled title="Uskoro: filter po treneru (izveštajni backend #12)" style={{ opacity: 0.55 }}>
          Svi treneri
        </FilterChip>
      </FilterBar>

      <EmptyState>
        Izveštajni backend (#12 Izveštaji) još ne postoji. Šest pokazatelja ispod čeka prave agregate i
        prikazano je bez izmišljenih brojeva. Lista „Traži pažnju“ i traka evidencije već koriste stvarne
        podatke iz Rasporeda i Finansija za izabrani period.
      </EmptyState>

      <section className="reports-stats" aria-label="Šest pokazatelja">
        {STAT_TILES.map((stat) => (
          <Link key={stat.key} className="reports-stat-link" to={stat.to} data-cy={`report-stat-${stat.key}`}>
            <StatTile
              icon={<TileIcon name={stat.icon} />}
              label={stat.label}
              value="Uskoro"
              delta={{ label: stat.note, tone: "neutral" }}
            />
          </Link>
        ))}
      </section>

      <div className="reports-main">
        <Card
          className="reports-chart-card"
          title="Prisustvo po nedeljama"
          subtitle="Prisutan / (prisutan + opravdano + neopravdano)"
        >
          <AttendanceTrendChart points={null} />
        </Card>

        <Card className="reports-attention-card" title="Traži pažnju">
          {sessions.loading || charges.loading || completion.loading ? (
            <LoadingState />
          ) : (
            <ul className="reports-attention-list">
              <AttentionRow
                icon="warning"
                title={
                  completion.unconfirmed.length > 0
                    ? `${completion.unconfirmed.length} ${completion.unconfirmed.length === 1 ? "termin" : "termina"} bez evidencije`
                    : "Sve prisustvo evidentirano"
                }
                subtitle={
                  completion.unconfirmed.length > 0
                    ? `${range.label === "danas" ? "Danas" : "Ovaj mesec"} · ${distinctGroups} ${distinctGroups === 1 ? "grupa" : "grupe"} · ${groupName(firstUnconfirmed?.group_id ?? "")}`
                    : "Nema završenih termina bez unetog prisustva u ovom periodu."
                }
                to={firstUnconfirmed ? `/raspored/${firstUnconfirmed.id}/prisustvo` : "/raspored"}
                dataCy="attention-unrecorded"
              />
              {charges.error ? null : (
                <AttentionRow
                  icon="wallet"
                  title={
                    openCharges.length > 0
                      ? `${openCharges.length} ${openCharges.length === 1 ? "otvoreno zaduženje" : "otvorenih zaduženja"}`
                      : "Nema otvorenih zaduženja"
                  }
                  subtitle={
                    openCharges.length > 0
                      ? `${formatMinor(outstandingMinor, outstandingCurrency)} ukupno`
                      : "Sve uplate su evidentirane."
                  }
                  to="/finansije"
                  dataCy="attention-charges"
                />
              )}
            </ul>
          )}

          {sessions.error ? <SystemState error={sessions.error} /> : null}
          {charges.error ? <SystemState error={charges.error} /> : null}

          <div className="reports-attention-progress">
            {completion.loading ? (
              <LoadingState label="Računanje evidencije…" />
            ) : completion.finished === 0 ? (
              <EmptyState>Nema završenih termina {range.label} da bi se izračunala evidencija.</EmptyState>
            ) : (
              <CapacityBar
                meaning="completion"
                value={completion.recorded}
                max={completion.finished}
                label={
                  <>
                    <span>Završena evidencija prisustva</span>
                    <span>{completionPct}%</span>
                  </>
                }
              />
            )}
          </div>
        </Card>
      </div>

      <p className="reports-footnote">
        Klik na pokazatelj otvara odgovarajuću listu u aplikaciji. Šest gornjih pokazatelja i grafikon
        prisustva čekaju izveštajni backend (#12); lista „Traži pažnju“ i traka evidencije već računaju iz
        stvarnih podataka Rasporeda i Finansija.
      </p>
    </div>
  );
}

function AttentionRow({
  icon,
  title,
  subtitle,
  to,
  dataCy,
}: {
  icon: "warning" | "wallet";
  title: ReactNode;
  subtitle: ReactNode;
  to: string;
  dataCy: string;
}) {
  return (
    <li className="reports-attention-row">
      <Link className="reports-attention-link" to={to} data-cy={dataCy}>
        <span className="reports-attention-row__icon" aria-hidden="true">
          <TileIcon name={icon} />
        </span>
        <span className="reports-attention-row__body">
          <span className="reports-attention-row__title">{title}</span>
          <span className="reports-attention-row__subtitle">{subtitle}</span>
        </span>
        <span className="reports-attention-row__arrow" aria-hidden="true">
          →
        </span>
      </Link>
    </li>
  );
}

/* ===================================================================== */
/* Line chart, "Prisustvo po nedeljama"                                 */
/*                                                                       */
/* Built to the dataviz skill's spec (2px line, ≥8px ringed end-marker,  */
/* hairline recessive grid, single series → no legend box, hover         */
/* crosshair + tooltip, direct end-label only, never a number on every  */
/* point), recolored to this app's green/gold semantic tokens instead of */
/* the skill's default placeholder palette. `points` is intentionally    */
/* `null` today (see file header), this component is ready to receive  */
/* real weekly {label, pct} points the moment the reports backend ships. */
/* ===================================================================== */

interface WeekPoint {
  label: string;
  pct: number;
}

function AttendanceTrendChart({ points }: { points: WeekPoint[] | null }) {
  const [hover, setHover] = useState<number | null>(null);

  if (!points || points.length < 2) {
    return (
      <div className="reports-chart-pending" data-cy="reports-chart-pending">
        <svg className="reports-chart-pending__ghost" viewBox="0 0 600 160" preserveAspectRatio="none" aria-hidden="true">
          <line x1="0" y1="20" x2="600" y2="20" />
          <line x1="0" y1="80" x2="600" y2="80" />
          <line x1="0" y1="140" x2="600" y2="140" />
        </svg>
        <p>
          Grafikon uskoro: čeka nedeljne agregate prisustva iz izveštajnog backenda (#12). Prikazujemo
          prazno stanje umesto izmišljenih tačaka.
        </p>
      </div>
    );
  }

  const width = 640;
  const height = 220;
  const padTop = 16;
  const padRight = 12;
  const padBottom = 28;
  const padLeft = 34;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const yFor = (pct: number) => padTop + plotH * (1 - pct / 100);
  const xFor = (i: number) => padLeft + (plotW * i) / (points.length - 1);
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i)},${yFor(p.pct)}`).join(" ");
  const areaPath = `${linePath} L${xFor(points.length - 1)},${padTop + plotH} L${xFor(0)},${padTop + plotH} Z`;
  const gridPcts = [0, 25, 50, 75, 100];
  const avg = points.reduce((sum, p) => sum + p.pct, 0) / points.length;
  const last = points[points.length - 1]!;
  const hovered = hover !== null ? points[hover] : undefined;

  return (
    <div className="reports-chart" data-cy="reports-attendance-chart">
      <div className="reports-chart__head">
        <span className="badge badge--success">{avg.toFixed(1)}% prosek</span>
      </div>
      <svg
        className="reports-chart__svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Prisustvo po nedeljama, prosek ${avg.toFixed(1)} procenata`}
        onMouseLeave={() => setHover(null)}
      >
        {gridPcts.map((g) => (
          <g key={g}>
            <line className="reports-chart__grid" x1={padLeft} x2={width - padRight} y1={yFor(g)} y2={yFor(g)} />
            <text className="reports-chart__tick" x={padLeft - 8} y={yFor(g)} textAnchor="end" dominantBaseline="middle">
              {g}%
            </text>
          </g>
        ))}
        <path className="reports-chart__area" d={areaPath} />
        <path className="reports-chart__line" d={linePath} />
        {points.map((p, i) => (
          <g
            key={p.label}
            tabIndex={0}
            role="img"
            aria-label={`${p.label}: ${p.pct}%`}
            onMouseEnter={() => setHover(i)}
            onFocus={() => setHover(i)}
          >
            <circle className="reports-chart__hit" cx={xFor(i)} cy={yFor(p.pct)} r={12} />
            {/* The latest week is the single gold data point on this screen:
                bigger, gold-filled, navy-stroked. Every earlier week is a
                plain white dot, so the eye lands on "where we are now". */}
            <circle
              className={
                i === points.length - 1
                  ? "reports-chart__dot reports-chart__dot--latest"
                  : "reports-chart__dot"
              }
              cx={xFor(i)}
              cy={yFor(p.pct)}
              r={i === points.length - 1 ? 5.5 : 4}
            />
          </g>
        ))}
        <text className="reports-chart__endlabel" x={xFor(points.length - 1)} y={yFor(last.pct) - 10} textAnchor="end">
          {last.pct}%
        </text>
        {hover !== null ? (
          <line className="reports-chart__crosshair" x1={xFor(hover)} x2={xFor(hover)} y1={padTop} y2={padTop + plotH} />
        ) : null}
      </svg>
      <div className="reports-chart__axis">
        {points.map((p) => (
          <span key={p.label}>{p.label}</span>
        ))}
      </div>
      {hovered ? (
        <div className="reports-chart__tooltip" role="status">
          <strong>{hovered.pct}%</strong> · {hovered.label}
        </div>
      ) : null}
    </div>
  );
}
