import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useSession } from "../../auth/session";
import type {
  AttendanceSheet,
  Charge,
  Group,
  LocationSummary,
  Page,
  PersonSummary,
  SessionSummary,
} from "../../api/types";
import { Card, EmptyState, LoadingState, StatTile, StatusBadge, SystemState, TableContainer } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import "../home.css";

function todayRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
  const to = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0);
  return { from: from.toISOString(), to: to.toISOString() };
}

function dateLabel(): string {
  const s = new Date().toLocaleDateString("sr-Latn-RS", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Best-effort attendance rollup for today's already-finished sessions.
 *  Never fabricated: derived from the real attendance sheets, degrades to
 *  `null`/empty when there is nothing to compute yet or a fetch fails. */
function useAttendanceRollup(sessions: SessionSummary[] | null) {
  const [state, setState] = useState<{ pct: number | null; unconfirmed: SessionSummary[] }>({
    pct: null,
    unconfirmed: [],
  });

  useEffect(() => {
    if (!sessions) return;
    const now = Date.now();
    const finished = sessions.filter(
      (s) => s.status !== "CANCELLED" && new Date(s.ends_at).getTime() <= now,
    );
    if (finished.length === 0) {
      setState({ pct: null, unconfirmed: [] });
      return;
    }
    let cancelled = false;
    Promise.allSettled(
      finished.map((s) => api.get<AttendanceSheet>(`/schedule/sessions/${s.id}/attendance`)),
    ).then((results) => {
      if (cancelled) return;
      let present = 0;
      let total = 0;
      const unconfirmed: SessionSummary[] = [];
      results.forEach((r, i) => {
        if (r.status !== "fulfilled") return;
        const session = finished[i];
        if (!session) return;
        const sheet = r.value;
        if (sheet.attendance_version === 0) unconfirmed.push(session);
        for (const entry of sheet.entries) {
          total += 1;
          if (entry.status === "PRESENT" || entry.status === "LATE") present += 1;
        }
      });
      setState({ pct: total > 0 ? Math.round((present / total) * 100) : null, unconfirmed });
    });
    return () => {
      cancelled = true;
    };
  }, [sessions]);

  return state;
}

export function ManagerHome() {
  const { me, activeContext } = useSession();
  const orgName = activeContext?.organization_name ?? "";
  const firstName = (me?.display_name ?? "").split(/\s+/)[0] ?? "";

  const range = useMemo(todayRange, []);
  const sessions = useAsync(
    () =>
      api.get<SessionSummary[]>(
        `/schedule/sessions?date_from=${encodeURIComponent(range.from)}&date_to=${encodeURIComponent(range.to)}`,
      ),
    [range.from, range.to],
  );
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const people = useAsync(() => api.get<Page<PersonSummary>>("/people"), []);
  const charges = useAsync(() => api.get<Page<Charge>>("/charges?limit=100"), []);
  const locations = useAsync(
    () =>
      activeContext?.scope_type === "BRANCH"
        ? api.get<Page<LocationSummary>>("/locations")
        : Promise.resolve<Page<LocationSummary>>({ items: [], total: 0, limit: 0, offset: 0 }),
    [activeContext?.scope_type],
  );
  const attendance = useAttendanceRollup(sessions.data);

  const groupName = (id: string) => groups.data?.items.find((g) => g.id === id)?.name ?? "—";
  const trainerName = (id: string | null | undefined) =>
    id ? (people.data?.items.find((p) => p.id === id)?.display_name ?? "—") : "—";
  const statusTone = (s: SessionSummary["status"]) =>
    s === "SCHEDULED" ? "success" : s === "COMPLETED" ? "info" : "error";

  const branchName = locations.data?.items.find((l) => l.id === activeContext?.scope_ref_id)?.name;
  const subtitle = branchName ? `${orgName} · ${branchName}` : orgName;

  const todaySessions = (sessions.data ?? []).slice().sort(
    (a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime(),
  );
  const now = Date.now();
  const nextSession = todaySessions.find(
    (s) => s.status === "SCHEDULED" && new Date(s.starts_at).getTime() >= now,
  );
  const openCharges = (charges.data?.items ?? []).filter(
    (c) => c.status === "OPEN" || c.status === "PARTIALLY_PAID",
  );

  return (
    <div>
      <header className="home-header">
        <span className="section-header__eyebrow">{dateLabel()}</span>
        <h1>Šta danas traži vašu pažnju?{firstName ? ` — ${firstName}` : ""}</h1>
        <p className="home-subtitle">{subtitle}</p>
      </header>

      <section className="home-priorities" aria-label="Prioriteti">
        <Card
          className="home-priority-card home-priority-card--lead"
          eyebrow="Termini danas"
          title={todaySessions.length ? `${todaySessions.length} zakazano` : "Nema termina"}
          subtitle={
            nextSession
              ? `Sledeći: ${new Date(nextSession.starts_at).toLocaleTimeString("sr-Latn", { hour: "2-digit", minute: "2-digit" })} · ${groupName(nextSession.group_id)}`
              : "Nema predstojećih termina danas."
          }
        >
          <Link className="btn btn--on-dark home-priority-card__cta" to="/raspored" data-cy="home-priority-schedule">
            Vidi ceo dan
          </Link>
        </Card>

        <Card
          className="home-priority-card"
          eyebrow="Prisustvo"
          title={attendance.unconfirmed.length ? `${attendance.unconfirmed.length} čeka unos` : "Sve uneto"}
          subtitle={
            attendance.unconfirmed.length
              ? "Termini su završeni, prisustvo još nije sačuvano."
              : "Nema neunetih termina koji su već završeni."
          }
        >
          {attendance.unconfirmed[0] ? (
            <Link
              className="btn btn--secondary home-priority-card__cta"
              to={`/raspored/${attendance.unconfirmed[0].id}/prisustvo`}
              data-cy="home-priority-attendance"
            >
              Unesi prisustvo
            </Link>
          ) : null}
        </Card>

        <Card
          className="home-priority-card"
          eyebrow="Finansije"
          title={`${openCharges.length} otvorenih zaduženja`}
          subtitle="Zaduženja koja čekaju uplatu ili delimično su plaćena."
        >
          <Link className="btn btn--secondary home-priority-card__cta" to="/finansije" data-cy="home-priority-money">
            Otvori finansije
          </Link>
        </Card>
      </section>

      <Card
        title="Današnji termini"
        action={
          <Link className="btn btn--secondary" to="/raspored" data-cy="home-schedule">
            Vidi ceo dan
          </Link>
        }
      >
        {sessions.loading || groups.loading ? <LoadingState /> : null}
        {sessions.error ? <SystemState error={sessions.error} /> : null}
        {!sessions.loading && !sessions.error && todaySessions.length === 0 ? (
          <EmptyState>Danas nema zakazanih termina.</EmptyState>
        ) : null}
        {!sessions.loading && !sessions.error && todaySessions.length > 0 ? (
          <TableContainer>
            <table className="data" data-cy="home-session-list">
              <thead>
                <tr>
                  <th>Vreme</th>
                  <th>Grupa</th>
                  <th>Trener</th>
                  <th>Sala</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {todaySessions.map((s) => (
                  <tr key={s.id} data-cy="home-session-row">
                    <td>
                      {new Date(s.starts_at).toLocaleTimeString("sr-Latn", { hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td>{groupName(s.group_id)}</td>
                    <td>{trainerName(s.trainer_person_id)}</td>
                    {/* Sessions have no room assignment in the API yet — degrade honestly. */}
                    <td className="home-room-cell">—</td>
                    <td>
                      <StatusBadge tone={statusTone(s.status)}>{s.status}</StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableContainer>
        ) : null}
      </Card>

      <Card title="Brze radnje">
        <div className="home-quick-grid">
          <Link className="btn btn--secondary home-quick-action" to="/ljudi" data-cy="home-people">
            Dodaj osobu
          </Link>
          <Link className="btn btn--secondary home-quick-action" to="/raspored" data-cy="home-new-session">
            Novi termin
          </Link>
          <Link className="btn btn--secondary home-quick-action" to="/komunikacija" data-cy="home-announcement">
            Novo obaveštenje
          </Link>
          <button
            type="button"
            className="btn btn--secondary home-quick-action"
            disabled
            title="Uskoro"
            data-cy="home-import"
          >
            Uvezi podatke
          </button>
        </div>
      </Card>

      <section className="home-stats" aria-label="Pregled">
        <StatTile label="Aktivni članovi" value={people.data ? people.data.total : "—"} />
        <StatTile
          label="Završeno prisustvo %"
          value={attendance.pct !== null ? `${attendance.pct}%` : "—"}
        />
        <StatTile label="Dospele obaveze" value={charges.data ? openCharges.length : "—"} />
      </section>
    </div>
  );
}
