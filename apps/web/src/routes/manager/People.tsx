import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import type {
  Group,
  GroupMember,
  GuardianContactResponse,
  MembershipResponse,
  Page,
  PersonResponse,
  PersonSummary,
} from "../../api/types";
import { PageHeader } from "../../components/shell";
import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  FilterBar,
  FilterChip,
  LoadingState,
  SegmentedControl,
  SplitPane,
  SplitPaneRow,
  StatusBadge,
  SystemState,
} from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import "./People.css";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

interface Candidate {
  person_id: string;
  display_name: string;
}

interface GroupRef {
  id: string;
  name: string;
}

type BadgeTone = "success" | "warning" | "error" | "info" | "neutral";
type Tab = "ljudi" | "pozivi";

const IDENTITY_LABEL: Record<string, string> = {
  PROVISIONAL: "Privremeno",
  CLAIMED: "Preuzeto",
  VERIFIED: "Proveren",
  MERGED: "Spojeno",
  ARCHIVED: "Arhivirano",
};

const IDENTITY_TONE: Record<string, BadgeTone> = {
  PROVISIONAL: "neutral",
  CLAIMED: "info",
  VERIFIED: "success",
  MERGED: "neutral",
  ARCHIVED: "error",
};

const MEMBERSHIP_LABEL: Record<string, string> = {
  ACTIVE: "Aktivno članstvo",
  SUSPENDED: "Suspendovano",
  ENDED: "Završeno",
};

const MEMBERSHIP_TONE: Record<string, BadgeTone> = {
  ACTIVE: "success",
  SUSPENDED: "warning",
  ENDED: "neutral",
};

const RELATIONSHIP_LABEL: Record<string, string> = {
  PARENT: "Roditelj",
  LEGAL_GUARDIAN: "Staratelj",
  OTHER: "Kontakt",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0];
  if (!first) return "?";
  const last = parts.length > 1 ? parts[parts.length - 1] : undefined;
  if (!last) return first.slice(0, 2).toUpperCase();
  return ((first[0] ?? "") + (last[0] ?? "")).toUpperCase();
}

/** For any given group, fetches its members once and builds a person -> groups
 * reverse index. A per-group fetch failure (e.g. a stale permission edge)
 * degrades that group to "no known members" instead of breaking the roster. */
function usePersonGroupIndex(groups: Group[]): Map<string, GroupRef[]> {
  const [byPerson, setByPerson] = useState<Map<string, GroupRef[]>>(new Map());
  const groupIds = groups.map((g) => g.id).join(",");

  useEffect(() => {
    if (groups.length === 0) {
      setByPerson(new Map());
      return;
    }
    let active = true;
    Promise.all(
      groups.map((g) =>
        api
          .get<GroupMember[]>(`/groups/${g.id}/members`)
          .then((members) => ({ group: g, members }))
          .catch(() => ({ group: g, members: [] as GroupMember[] })),
      ),
    ).then((results) => {
      if (!active) return;
      const next = new Map<string, GroupRef[]>();
      for (const { group, members } of results) {
        for (const m of members) {
          const list = next.get(m.person_id) ?? [];
          list.push({ id: group.id, name: group.name });
          next.set(m.person_id, list);
        }
      }
      setByPerson(next);
    });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupIds]);

  return byPerson;
}

export function PeoplePage() {
  const people = useAsync(() => api.get<Page<PersonSummary>>("/people"), []);
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const [tab, setTab] = useState<Tab>("ljudi");
  const [addOpen, setAddOpen] = useState(true);

  return (
    <div>
      <PageHeader
        title="Ljudi i grupe"
        action={
          <Button data-cy="add-person-toggle" onClick={() => setAddOpen((v) => !v)}>
            + Dodaj osobu
          </Button>
        }
      />

      <SegmentedControl
        ariaLabel="Prikaz ljudi"
        className="people-tabs"
        value={tab}
        onChange={setTab}
        options={[
          { value: "ljudi", label: <span data-cy="tab-ljudi">Ljudi</span> },
          {
            value: "pozivi",
            label: (
              <span data-cy="tab-pozivi" title="Broj poziva nije dostupan — modul za pozivnice je u pripremi">
                Pozivi <StatusBadge tone="neutral">–</StatusBadge>
              </span>
            ),
          },
        ]}
      />

      {tab === "pozivi" ? (
        <EmptyState>
          Pozivi dolaze uskoro. Ova sekcija čeka modul za pozivnice koji je trenutno u razvoju.
        </EmptyState>
      ) : (
        <>
          {addOpen ? <AddPerson onCreated={people.reload} onClose={() => setAddOpen(false)} /> : null}
          <Roster peopleState={people} groupsState={groups} />
          <Groups groupsState={groups} peopleState={people} />
        </>
      )}
    </div>
  );
}

function AddPerson({ onCreated, onClose }: { onCreated: () => void; onClose: () => void }) {
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
    <Card
      title="Nova osoba"
      action={
        <Button variant="secondary" type="button" onClick={onClose} data-cy="add-person-close">
          Zatvori
        </Button>
      }
    >
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
        <Button type="submit" disabled={busy} data-cy="person-save">
          Sačuvaj osobu
        </Button>
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
    </Card>
  );
}

function Roster({
  peopleState,
  groupsState,
}: {
  peopleState: ReturnType<typeof useAsync<Page<PersonSummary>>>;
  groupsState: ReturnType<typeof useAsync<Page<Group>>>;
}) {
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const groups = groupsState.data?.items ?? [];
  const groupIndex = usePersonGroupIndex(groups);
  const items = peopleState.data?.items ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((p) => {
      if (q && !p.display_name.toLowerCase().includes(q)) return false;
      if (activeOnly && (p.identity_status === "ARCHIVED" || p.identity_status === "MERGED")) return false;
      if (groupFilter && !(groupIndex.get(p.id) ?? []).some((g) => g.id === groupFilter)) return false;
      return true;
    });
  }, [items, search, activeOnly, groupFilter, groupIndex]);

  useEffect(() => {
    if (selectedId && !items.some((p) => p.id === selectedId)) setSelectedId(null);
  }, [items, selectedId]);

  if (peopleState.loading) return <LoadingState />;
  if (peopleState.error) return <SystemState error={peopleState.error} />;

  return (
    <div className="people-roster">
      <FilterBar>
        <input
          type="search"
          className="people-search"
          placeholder="Pretraga po imenu…"
          aria-label="Pretraga osoba"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-cy="people-search"
        />
        <FilterChip disabled title="Tip osobe uskoro dostupan" data-cy="filter-type">
          Tip osobe
        </FilterChip>
        <FilterChip active={activeOnly} onClick={() => setActiveOnly((v) => !v)} data-cy="filter-active">
          Aktivni
        </FilterChip>
        <FilterChip caret disabled title="Ogranci uskoro dostupni" data-cy="filter-branch">
          Ogranak
        </FilterChip>
        <GroupFilterChip groups={groups} value={groupFilter} onChange={setGroupFilter} />
      </FilterBar>

      {items.length === 0 ? (
        <EmptyState>Još nema unetih osoba.</EmptyState>
      ) : (
        <SplitPane
          list={
            filtered.length === 0 ? (
              <EmptyState>Nema osoba za izabrane filtere.</EmptyState>
            ) : (
              <div data-cy="people-list">
                {filtered.map((p) => (
                  <SplitPaneRow key={p.id} active={p.id === selectedId} onClick={() => setSelectedId(p.id)}>
                    <PersonRow person={p} groups={groupIndex.get(p.id) ?? []} />
                  </SplitPaneRow>
                ))}
              </div>
            )
          }
          detail={
            selectedId ? (
              <PersonDetail personId={selectedId} groups={groupIndex.get(selectedId) ?? []} />
            ) : (
              <EmptyState>Izaberite osobu sa spiska za detalje.</EmptyState>
            )
          }
        />
      )}
    </div>
  );
}

function PersonRow({ person, groups }: { person: PersonSummary; groups: GroupRef[] }) {
  return (
    <div className="people-row" data-cy="person-row">
      <span className="avatar avatar--gold people-row__avatar" aria-hidden="true">
        {initials(person.display_name)}
      </span>
      <span className="people-row__body">
        <span className="people-row__name">{person.display_name}</span>
        <span className="people-row__meta">
          <span>{groups.length > 0 ? groups.map((g) => g.name).join(", ") : "Bez grupe"}</span>
          <span className="people-row__stub" title="Ogranak još nije dostupan u profilu">
            Ogranak: —
          </span>
        </span>
      </span>
      <span className="people-row__status">
        <StatusBadge tone={IDENTITY_TONE[person.identity_status] ?? "neutral"}>
          {IDENTITY_LABEL[person.identity_status] ?? person.identity_status}
        </StatusBadge>
      </span>
    </div>
  );
}

function GroupFilterChip({
  groups,
  value,
  onChange,
}: {
  groups: Group[];
  value: string | null;
  onChange: (value: string | null) => void;
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

  const label = value ? (groups.find((g) => g.id === value)?.name ?? "Grupa") : "Grupa";

  return (
    <div className="people-popover" ref={ref}>
      <FilterChip caret active={!!value} onClick={() => setOpen((v) => !v)} data-cy="filter-group">
        {label}
      </FilterChip>
      {open ? (
        <div className="people-popover__menu" role="menu">
          <button
            type="button"
            className="people-popover__item"
            onClick={() => {
              onChange(null);
              setOpen(false);
            }}
          >
            Sve grupe
          </button>
          {groups.length === 0 ? (
            <span className="people-popover__item">Još nema grupa</span>
          ) : (
            groups.map((g) => (
              <button
                key={g.id}
                type="button"
                className={cx("people-popover__item", g.id === value && "people-popover__item--active")}
                onClick={() => {
                  onChange(g.id);
                  setOpen(false);
                }}
              >
                {g.name}
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  loading,
  stubHint,
}: {
  label: string;
  value?: string | null;
  loading?: boolean;
  stubHint?: string;
}) {
  return (
    <div className={cx("people-detail__field", !value && "people-detail__field--muted")}>
      <span className="people-field-label">{label}</span>
      <span className="people-field-value" title={stubHint}>
        {loading ? "…" : value ? value : stubHint ? "Uskoro dostupno" : "—"}
      </span>
    </div>
  );
}

/** Right pane of the split view. Composite profile fields the backend does
 * not expose yet (branch, start date) are stubbed with an explanatory hint —
 * never fabricated. Membership + guardians are real data from the merged
 * membership (#6) and guardian endpoints. */
function PersonDetail({ personId, groups }: { personId: string; groups: GroupRef[] }) {
  const person = useAsync(() => api.get<PersonResponse>(`/people/${personId}`), [personId]);
  const membership = useAsync(() => api.get<MembershipResponse>(`/people/${personId}/membership`), [personId]);
  const guardians = useAsync(() => api.get<GuardianContactResponse[]>(`/people/${personId}/guardians`), [personId]);

  if (person.loading) return <LoadingState />;
  if (person.error) return <SystemState error={person.error} />;
  if (!person.data) return null;
  const p = person.data;

  return (
    <div data-cy="person-detail">
      <div className="people-detail__header">
        <span className="avatar avatar--gold people-detail__avatar" aria-hidden="true">
          {initials(p.display_name)}
        </span>
        <div>
          <h3 className="people-detail__name">{p.display_name}</h3>
          <div className="people-detail__badges">
            <StatusBadge tone={IDENTITY_TONE[p.identity_status] ?? "neutral"}>
              {IDENTITY_LABEL[p.identity_status] ?? p.identity_status}
            </StatusBadge>
            {membership.data ? (
              <StatusBadge tone={MEMBERSHIP_TONE[membership.data.status] ?? "neutral"}>
                {MEMBERSHIP_LABEL[membership.data.status] ?? membership.data.status}
              </StatusBadge>
            ) : null}
          </div>
        </div>
      </div>

      {membership.error ? <SystemState error={membership.error} /> : null}

      <div className="people-detail__grid">
        <Field
          label="Lokalna šifra"
          value={membership.data?.local_member_code ?? undefined}
          loading={membership.loading}
        />
        <Field label="Ogranak" stubHint="Ogranci još nisu povezani sa profilom osobe" />
        <Field label="Datum učlanjenja" stubHint="Datum učlanjenja još nije izložen u profilu" />
        <Field label="Napomena" value={membership.data?.admin_note ?? undefined} loading={membership.loading} />
      </div>

      <div className="people-detail__section">
        <h4>Roditeljska veza</h4>
        {guardians.loading ? (
          <LoadingState />
        ) : guardians.error ? (
          <SystemState error={guardians.error} />
        ) : (guardians.data ?? []).length === 0 ? (
          <EmptyState>Nema povezanih roditelja/staratelja.</EmptyState>
        ) : (
          (guardians.data ?? []).map((g) => (
            <div className="people-guardian" key={g.guardian_person_id}>
              <span>
                {g.display_name}{" "}
                <span className="people-row__stub">
                  ({RELATIONSHIP_LABEL[g.relationship_type] ?? g.relationship_type})
                </span>
              </span>
              {g.is_primary_contact ? <StatusBadge tone="info">Primarni kontakt</StatusBadge> : null}
            </div>
          ))
        )}
      </div>

      <div className="people-detail__section">
        <h4>Članstvo u grupama</h4>
        {groups.length === 0 ? (
          <EmptyState>Nije član nijedne grupe.</EmptyState>
        ) : (
          <div className="people-chiplist">
            {groups.map((g) => (
              <span className="badge badge--neutral" key={g.id}>
                {g.name}
              </span>
            ))}
          </div>
        )}
      </div>

      <Button variant="secondary" disabled title="Ceo profil dolazi uskoro" data-cy="open-profile">
        Otvori ceo profil
      </Button>
    </div>
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
    <Card title="Grupe">
      {error ? <SystemState error={error} /> : null}
      <form onSubmit={createGroup} style={{ display: "flex", gap: "var(--space-2)", alignItems: "end" }}>
        <div className="field" style={{ flex: 1, margin: 0 }}>
          <label htmlFor="g-name">Naziv grupe</label>
          <input id="g-name" value={name} onChange={(e) => setName(e.target.value)} required data-cy="group-name" />
        </div>
        <Button type="submit" data-cy="group-save">
          Napravi grupu
        </Button>
      </form>
      {groupsState.loading ? (
        <LoadingState />
      ) : groupsState.error ? (
        <SystemState error={groupsState.error} />
      ) : (groupsState.data?.items ?? []).length === 0 ? (
        <EmptyState>Još nema grupa.</EmptyState>
      ) : (
        <ul data-cy="group-list" className="people-grouplist">
          {(groupsState.data?.items ?? []).map((g) => (
            <GroupRow key={g.id} group={g} people={peopleState.data?.items ?? []} />
          ))}
        </ul>
      )}
    </Card>
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
    <li className="people-group-item" data-cy="group-item">
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
        <Button variant="secondary" type="submit" data-cy="member-add">
          Dodaj
        </Button>
      </form>
    </li>
  );
}
