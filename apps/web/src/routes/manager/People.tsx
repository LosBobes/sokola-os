import { useState } from "react";
import { ApiError, api } from "../../api/client";
import type { Group, GroupMember, Page, PersonResponse, PersonSummary } from "../../api/types";
import { PageHeader } from "../../components/shell";
import { ConfirmDialog, EmptyState, LoadingState, StatusBadge, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";

interface Candidate {
  person_id: string;
  display_name: string;
}

export function PeoplePage() {
  const people = useAsync(() => api.get<Page<PersonSummary>>("/people"), []);
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);

  return (
    <div>
      <PageHeader title="Ljudi i grupe" />
      <AddPerson onCreated={people.reload} />
      <PeopleList state={people} />
      <Groups groupsState={groups} peopleState={people} />
    </div>
  );
}

function AddPerson({ onCreated }: { onCreated: () => void }) {
  const [given, setGiven] = useState("");
  const [family, setFamily] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [reason, setReason] = useState("");

  function reset() {
    setGiven("");
    setFamily("");
    setReason("");
    setCandidates(null);
  }

  async function create(allowDuplicate: boolean) {
    setBusy(true);
    setError(null);
    try {
      await api.post<PersonResponse>("/people", {
        given_name: given,
        family_name: family,
        allow_possible_duplicate: allowDuplicate,
        duplicate_reason: allowDuplicate ? reason : null,
      });
      reset();
      onCreated();
    } catch (err) {
      if (err instanceof ApiError && err.details?.code === "POSSIBLE_DUPLICATE") {
        setCandidates((err.details.candidates as Candidate[]) ?? []);
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" style={{ marginBottom: "var(--space-4)" }}>
      <h2>Dodaj osobu</h2>
      {error ? <SystemState error={error} /> : null}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void create(false);
        }}
      >
        <div className="field">
          <label htmlFor="p-given">Ime</label>
          <input id="p-given" value={given} onChange={(e) => setGiven(e.target.value)} required data-cy="person-given" />
        </div>
        <div className="field">
          <label htmlFor="p-family">Prezime</label>
          <input id="p-family" value={family} onChange={(e) => setFamily(e.target.value)} required data-cy="person-family" />
        </div>
        <button className="btn btn--primary" type="submit" disabled={busy} data-cy="person-save">
          Sačuvaj osobu
        </button>
      </form>

      <ConfirmDialog
        open={candidates !== null}
        title="Moguć duplikat"
        confirmLabel="Ipak sačuvaj"
        busy={busy}
        onCancel={() => setCandidates(null)}
        onConfirm={() => void create(true)}
      >
        <p>Osoba sa istim imenom već postoji u ovoj školi:</p>
        <ul>
          {candidates?.map((c) => (
            <li key={c.person_id}>{c.display_name}</li>
          ))}
        </ul>
        <div className="field">
          <label htmlFor="dup-reason">Razlog (obavezno)</label>
          <input id="dup-reason" value={reason} onChange={(e) => setReason(e.target.value)} data-cy="dup-reason" />
        </div>
      </ConfirmDialog>
    </section>
  );
}

function PeopleList({ state }: { state: ReturnType<typeof useAsync<Page<PersonSummary>>> }) {
  if (state.loading) return <LoadingState />;
  if (state.error) return <SystemState error={state.error} />;
  const items = state.data?.items ?? [];
  if (items.length === 0) return <EmptyState>Još nema unetih osoba.</EmptyState>;
  return (
    <table className="data" data-cy="people-list">
      <thead>
        <tr>
          <th>Osoba</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {items.map((p) => (
          <tr key={p.id} data-cy="person-row">
            <td>{p.display_name}</td>
            <td>
              <StatusBadge tone="info">{p.identity_status}</StatusBadge>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Groups({
  groupsState,
  peopleState,
}: {
  groupsState: ReturnType<typeof useAsync<Page<Group>>>;
  peopleState: ReturnType<typeof useAsync<Page<PersonSummary>>>;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function createGroup(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post<Group>("/groups", { name });
      setName("");
      groupsState.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="card" style={{ marginTop: "var(--space-4)" }}>
      <h2>Grupe</h2>
      {error ? <SystemState error={error} /> : null}
      <form onSubmit={createGroup} style={{ display: "flex", gap: "var(--space-2)", alignItems: "end" }}>
        <div className="field" style={{ flex: 1, margin: 0 }}>
          <label htmlFor="g-name">Naziv grupe</label>
          <input id="g-name" value={name} onChange={(e) => setName(e.target.value)} required data-cy="group-name" />
        </div>
        <button className="btn btn--primary" type="submit" data-cy="group-save">
          Napravi grupu
        </button>
      </form>
      <ul data-cy="group-list">
        {(groupsState.data?.items ?? []).map((g) => (
          <GroupRow key={g.id} group={g} people={peopleState.data?.items ?? []} />
        ))}
      </ul>
    </section>
  );
}

function GroupRow({ group, people }: { group: Group; people: PersonSummary[] }) {
  const members = useAsync(() => api.get<GroupMember[]>(`/groups/${group.id}/members`), [group.id]);
  const [personId, setPersonId] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post(`/groups/${group.id}/members`, { person_id: personId });
      setPersonId("");
      members.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <li style={{ marginBottom: "var(--space-3)" }} data-cy="group-item">
      <strong>{group.name}</strong> — {members.data?.length ?? 0} članova
      {error ? <SystemState error={error} /> : null}
      <form onSubmit={add} style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
        <select value={personId} onChange={(e) => setPersonId(e.target.value)} required data-cy="member-select">
          <option value="">Izaberi osobu…</option>
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display_name}
            </option>
          ))}
        </select>
        <button className="btn btn--secondary" type="submit" data-cy="member-add">
          Dodaj
        </button>
      </form>
    </li>
  );
}
