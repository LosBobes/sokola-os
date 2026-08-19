import { useState } from "react";
import { api, newIdempotencyKey } from "../../api/client";
import type { EventItem, Registration } from "../../api/types";
import { PageHeader } from "../../components/shell";
import { EmptyState, InlineNotice, LoadingState, StatusBadge, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { formatDateTime } from "../../lib/format";

interface Child {
  person_id: string;
  display_name: string;
}

export function EventsPage() {
  const events = useAsync(() => api.get<EventItem[]>("/events"), []);
  const children = useAsync(() => api.get<Child[]>("/parent/children"), []);

  if (events.loading || children.loading) return <LoadingState />;

  return (
    <div>
      <PageHeader title="Događaji" />
      {events.error ? <SystemState error={events.error} /> : null}
      {(events.data ?? []).length === 0 ? <EmptyState>Trenutno nema događaja.</EmptyState> : null}
      {(events.data ?? []).map((ev) => (
        <EventCard key={ev.id} event={ev} children={children.data ?? []} />
      ))}
    </div>
  );
}

function EventCard({ event, children }: { event: EventItem; children: Child[] }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function register() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<Registration[]>(
        `/events/${event.id}/registrations`,
        { child_person_ids: selected },
        newIdempotencyKey(),
      );
      setRegistrations(result);
      setSelected([]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function cancel(reg: Registration) {
    setError(null);
    try {
      const updated = await api.post<Registration>(
        `/events/${event.id}/registrations/${reg.registration_id}/cancel`,
      );
      setRegistrations((rs) =>
        rs.map((r) => (r.registration_id === updated.registration_id ? updated : r)),
      );
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="card" style={{ marginBottom: "var(--space-4)" }} data-cy="event-card">
      <h2>{event.title}</h2>
      <p>{formatDateTime(event.starts_at)}</p>
      {error ? <SystemState error={error} /> : null}

      {registrations.length === 0 ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void register();
          }}
        >
          <fieldset style={{ border: "none", padding: 0 }}>
            <legend>Izaberi dete/decu</legend>
            {children.length === 0 ? (
              <InlineNotice tone="info">Nema dece povezane sa vašim nalogom u ovoj školi.</InlineNotice>
            ) : (
              children.map((c) => (
                <label key={c.person_id} style={{ display: "block" }}>
                  <input
                    type="checkbox"
                    checked={selected.includes(c.person_id)}
                    onChange={() => toggle(c.person_id)}
                    data-cy={`child-${c.person_id}`}
                  />{" "}
                  {c.display_name}
                </label>
              ))
            )}
          </fieldset>
          <button
            className="btn btn--primary"
            type="submit"
            disabled={busy || selected.length === 0}
            data-cy="event-register"
          >
            Potvrdi prijavu
          </button>
        </form>
      ) : (
        <div data-cy="event-registrations">
          <h3>Prijave</h3>
          <ul>
            {registrations.map((r) => (
              <li key={r.registration_id} style={{ marginBottom: "var(--space-2)" }}>
                {r.display_name}{" "}
                <StatusBadge tone={r.status === "REGISTERED" ? "success" : "info"}>{r.status}</StatusBadge>{" "}
                {r.status === "REGISTERED" ? (
                  <button className="btn btn--secondary" onClick={() => void cancel(r)} data-cy="event-cancel">
                    Otkaži prijavu
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
