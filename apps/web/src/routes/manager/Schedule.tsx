import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, newIdempotencyKey } from "../../api/client";
import type { ConflictCheck, Group, Page, SessionSummary } from "../../api/types";
import { PageHeader } from "../../components/shell";
import { EmptyState, InlineNotice, LoadingState, StatusBadge, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";

const RANGE_DAYS = 90;

export function SchedulePage() {
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const range = useMemo(() => {
    const from = new Date();
    const to = new Date(Date.now() + RANGE_DAYS * 86400000);
    return { from: from.toISOString(), to: to.toISOString() };
  }, []);
  const sessions = useAsync(
    () =>
      api.get<SessionSummary[]>(
        `/schedule/sessions?date_from=${encodeURIComponent(range.from)}&date_to=${encodeURIComponent(range.to)}`,
      ),
    [range.from, range.to],
  );

  return (
    <div>
      <PageHeader title="Raspored" />
      <NewSession groups={groups.data?.items ?? []} onCreated={sessions.reload} />
      <SessionList state={sessions} />
    </div>
  );
}

function NewSession({ groups, onCreated }: { groups: Group[]; onCreated: () => void }) {
  const [groupId, setGroupId] = useState("");
  const [startsLocal, setStartsLocal] = useState("");
  const [duration, setDuration] = useState(60);
  const [title, setTitle] = useState("");
  const [conflict, setConflict] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setConflict(null);
    const startsAt = new Date(startsLocal).toISOString();
    const endsAt = new Date(new Date(startsLocal).getTime() + duration * 60000).toISOString();
    const draft = { group_id: groupId, starts_at: startsAt, ends_at: endsAt, title: title || null };
    try {
      // Adapter auto-checks conflicts before the idempotent create.
      const check = await api.post<ConflictCheck>("/schedule/conflict-check", draft);
      if (check.has_conflict) {
        setConflict(check.conflicts); // keep the draft; do not create
        return;
      }
      await api.post<SessionSummary>("/schedule/sessions", draft, newIdempotencyKey());
      setStartsLocal("");
      setTitle("");
      onCreated();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" style={{ marginBottom: "var(--space-4)" }}>
      <h2>Novi termin</h2>
      {error ? <SystemState error={error} /> : null}
      {conflict ? (
        <InlineNotice tone="warning">
          Termin se preklapa sa postojećim ({conflict.length}). Izmenite vreme i pokušajte ponovo.
        </InlineNotice>
      ) : null}
      <form onSubmit={save}>
        <div className="field">
          <label htmlFor="s-group">Grupa</label>
          <select id="s-group" value={groupId} onChange={(e) => setGroupId(e.target.value)} required data-cy="session-group">
            <option value="">Izaberi grupu…</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="s-start">Početak</label>
          <input
            id="s-start"
            type="datetime-local"
            value={startsLocal}
            onChange={(e) => setStartsLocal(e.target.value)}
            required
            data-cy="session-start"
          />
        </div>
        <div className="field">
          <label htmlFor="s-dur">Trajanje (min)</label>
          <input
            id="s-dur"
            type="number"
            min={15}
            step={15}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
            data-cy="session-duration"
          />
        </div>
        <div className="field">
          <label htmlFor="s-title">Naziv (opciono)</label>
          <input id="s-title" value={title} onChange={(e) => setTitle(e.target.value)} data-cy="session-title" />
        </div>
        <button className="btn btn--primary" type="submit" disabled={busy} data-cy="session-save">
          Sačuvaj termin
        </button>
      </form>
    </section>
  );
}

function SessionList({ state }: { state: ReturnType<typeof useAsync<SessionSummary[]>> }) {
  if (state.loading) return <LoadingState />;
  if (state.error) return <SystemState error={state.error} />;
  const items = state.data ?? [];
  if (items.length === 0) return <EmptyState>Još nema zakazanih termina.</EmptyState>;
  return (
    <table className="data" data-cy="session-list">
      <thead>
        <tr>
          <th>Početak</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {items.map((s) => (
          <tr key={s.id} data-cy="session-row">
            <td>{new Date(s.starts_at).toLocaleString("sr-Latn")}</td>
            <td>
              <StatusBadge tone={s.status === "SCHEDULED" ? "success" : "info"}>{s.status}</StatusBadge>
            </td>
            <td>
              <Link className="btn btn--secondary" to={`/raspored/${s.id}/prisustvo`} data-cy="session-attendance">
                Prisustvo
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
