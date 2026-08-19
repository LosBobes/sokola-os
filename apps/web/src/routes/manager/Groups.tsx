import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type {
  Group,
  GroupMember,
  GroupMemberRole,
  LocationSummary,
  Page,
  PersonSummary,
  SessionStatus,
} from "../../api/types";
import { PageHeader } from "../../components/shell";
import {
  Button,
  CapacityBar,
  EmptyState,
  FilterBar,
  FilterChip,
  LoadingState,
  SectionHeader,
  SegmentedControl,
  SplitPane,
  StatTile,
  StatusBadge,
  SystemState,
} from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { formatDateTime, formatDayMonth, formatTime } from "../../lib/format";
import { GROUP_MEMBER_ROLE_LABEL, LOCATION_KIND_LABEL } from "../../lib/labels";
import "./Groups.css";

/*
 * M03 · Grupe.
 *
 * The Group model in schema.d.ts today is minimal (id, name, capacity_mode,
 * capacity), there is no program/ogranak/room/price relation on a group yet
 * (pricing lands with #7). Rather than invent that data, this screen:
 *  - shows real fields from GET /groups + GET /groups/{id}/members,
 *  - derives "Trener" and "Sledeći termin" from the already-shipped
 *    /schedule/sessions and /schedule/series endpoints (real joins, not
 *    fabricated data),
 *  - stubs the fields that genuinely have no backing endpoint yet (monthly
 *    price, editing a group, Program/Ogranak filters) as disabled/"uskoro".
 */

/* --- Local, additive types (schema.d.ts has these fields; api/types.ts's
   curated SessionSummary/Page shapes don't carry trainer_person_id yet) --- */
interface ScheduleSession {
  id: string;
  group_id: string;
  title: string | null;
  starts_at: string;
  ends_at: string;
  status: SessionStatus;
  trainer_person_id?: string | null;
}

interface SeriesSummary {
  id: string;
  group_id: string;
  trainer_person_id: string | null;
  local_time: string;
  frequency: "WEEKLY" | "BIWEEKLY" | "MONTHLY";
}

const FREQ_LABEL: Record<SeriesSummary["frequency"], string> = {
  WEEKLY: "nedeljno",
  BIWEEKLY: "dvonedeljno",
  MONTHLY: "mesečno",
};

const SCHEDULE_WINDOW_DAYS = 120;

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]!;
  const last = parts.length > 1 ? parts[parts.length - 1]! : undefined;
  return last ? ((first[0] ?? "") + (last[0] ?? "")).toUpperCase() : first.slice(0, 2).toUpperCase();
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((startOf(d) - startOf(new Date())) / 86400000);
  const time = formatTime(d);
  if (diffDays === 0) return `danas u ${time}`;
  if (diffDays === 1) return `sutra u ${time}`;
  return `${formatDayMonth(d)} u ${time}`;
}

function groupStatus(group: Group, count: number): { tone: "success" | "error" | "info"; label: string } {
  if (group.capacity_mode === "UNLIMITED") return { tone: "info", label: "Bez ograničenja" };
  const capacity = group.capacity ?? 0;
  if (capacity > 0 && count >= capacity) return { tone: "error", label: "Nema mesta" };
  return { tone: "success", label: "Aktivna" };
}

/** "18 od 20" bar for a limited group, or a full green "bez ograničenja" bar
 *  for an unlimited one (the shared CapacityBar always marks value===max as
 *  "full/red", which is only meaningful when there is an actual cap). */
function CapacityRow({ group, count }: { group: Group; count: number }) {
  if (group.capacity_mode === "LIMITED" && group.capacity != null) {
    return (
      <CapacityBar
        value={count}
        max={group.capacity}
        label={
          <>
            <span>Kapacitet</span>
            <span>
              {count} od {group.capacity}
            </span>
          </>
        }
      />
    );
  }
  return (
    <div className="capacity-bar">
      <div className="capacity-bar__label">
        <span>Kapacitet</span>
        <span>{count} · bez ograničenja</span>
      </div>
      <div className="capacity-bar__track">
        <div className="capacity-bar__fill" style={{ width: "100%" }} />
      </div>
    </div>
  );
}

export function GroupsPage() {
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const people = useAsync(() => api.get<Page<PersonSummary>>("/people"), []);
  const locations = useAsync(() => api.get<Page<LocationSummary>>("/locations?limit=100"), []);

  const scheduleRange = useMemo(() => {
    const from = new Date();
    const to = new Date(Date.now() + SCHEDULE_WINDOW_DAYS * 86400000);
    return { from: from.toISOString(), to: to.toISOString() };
  }, []);
  const sessions = useAsync(
    () =>
      api.get<ScheduleSession[]>(
        `/schedule/sessions?date_from=${encodeURIComponent(scheduleRange.from)}&date_to=${encodeURIComponent(scheduleRange.to)}`,
      ),
    [scheduleRange.from, scheduleRange.to],
  );
  const series = useAsync(() => api.get<SeriesSummary[]>("/schedule/series"), []);

  const groupIds = useMemo(() => (groups.data?.items ?? []).map((g) => g.id), [groups.data]);
  const members = useAsync(async () => {
    const entries = await Promise.all(
      groupIds.map(async (id) => [id, await api.get<GroupMember[]>(`/groups/${id}/members`)] as const),
    );
    return Object.fromEntries(entries) as Record<string, GroupMember[]>;
  }, [groupIds.join(",")]);

  const locationsMap = useMemo(
    () =>
      Object.fromEntries((locations.data?.items ?? []).map((l) => [l.id, l])) as Record<
        string,
        LocationSummary
      >,
    [locations.data],
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [trainerFilter, setTrainerFilter] = useState("");
  const [onlyFree, setOnlyFree] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const peopleMap = useMemo(
    () => Object.fromEntries((people.data?.items ?? []).map((p) => [p.id, p.display_name])),
    [people.data],
  );

  const trainersByGroup = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const s of series.data ?? []) {
      if (!s.trainer_person_id) continue;
      (map[s.group_id] ??= []).push(s.trainer_person_id);
    }
    return map;
  }, [series.data]);

  const nextSessionByGroup = useMemo(() => {
    const map: Record<string, ScheduleSession> = {};
    for (const s of sessions.data ?? []) {
      if (s.status !== "SCHEDULED") continue;
      const existing = map[s.group_id];
      if (!existing || new Date(s.starts_at) < new Date(existing.starts_at)) map[s.group_id] = s;
    }
    return map;
  }, [sessions.data]);

  const allTrainerIds = useMemo(() => {
    const set = new Set<string>();
    Object.values(trainersByGroup).forEach((ids) => ids.forEach((id) => set.add(id)));
    return Array.from(set);
  }, [trainersByGroup]);

  const filteredGroups = useMemo(() => {
    let items = groups.data?.items ?? [];
    const q = search.trim().toLowerCase();
    if (q) items = items.filter((g) => g.name.toLowerCase().includes(q));
    if (trainerFilter) items = items.filter((g) => (trainersByGroup[g.id] ?? []).includes(trainerFilter));
    if (onlyFree) {
      items = items.filter((g) => {
        if (g.capacity_mode === "UNLIMITED") return true;
        const count = members.data?.[g.id]?.length ?? 0;
        return g.capacity == null || count < g.capacity;
      });
    }
    return items;
  }, [groups.data, search, trainerFilter, onlyFree, trainersByGroup, members.data]);

  const selectedGroup = (groups.data?.items ?? []).find((g) => g.id === selectedId) ?? null;

  function afterCreate() {
    setShowCreate(false);
    groups.reload();
  }

  function afterMemberChange() {
    members.reload();
  }

  return (
    <div>
      <PageHeader
        title="Grupe"
        action={
          <Button onClick={() => setShowCreate((v) => !v)} data-cy="group-new">
            Nova grupa
          </Button>
        }
      />
      <p style={{ color: "var(--text-secondary)", marginTop: 0, marginBottom: "var(--space-4)" }}>
        Članovi, treneri, kapaciteti i raspored po grupama.
      </p>

      {showCreate ? (
        <CreateGroupForm
          onCreated={afterCreate}
          onCancel={() => setShowCreate(false)}
          people={people.data?.items ?? []}
          locations={locations.data?.items ?? []}
        />
      ) : null}

      <FilterBar>
        <FilterChip caret disabled title="Uskoro: grupe još nisu povezane sa programom" style={{ opacity: 0.55 }}>
          Program
        </FilterChip>
        <FilterChip caret disabled title="Uskoro: grupe još nisu povezane sa ogrankom" style={{ opacity: 0.55 }}>
          Ogranak
        </FilterChip>
        <div className="field" style={{ margin: 0, minWidth: 160 }}>
          <select
            value={trainerFilter}
            onChange={(e) => setTrainerFilter(e.target.value)}
            aria-label="Filter po treneru"
            data-cy="group-filter-trainer"
          >
            <option value="">Trener</option>
            {allTrainerIds.map((id) => (
              <option key={id} value={id}>
                {peopleMap[id] ?? id}
              </option>
            ))}
          </select>
        </div>
        <FilterChip active={onlyFree} onClick={() => setOnlyFree((v) => !v)} data-cy="group-filter-free">
          Slobodna mesta
        </FilterChip>
        <div className="field" style={{ margin: "0 0 0 auto", minWidth: 220 }}>
          <input
            type="search"
            placeholder="Pronađi grupu"
            aria-label="Pronađi grupu"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-cy="group-search"
          />
        </div>
      </FilterBar>

      {groups.loading ? (
        <LoadingState />
      ) : groups.error ? (
        <SystemState error={groups.error} />
      ) : (groups.data?.items.length ?? 0) === 0 ? (
        <EmptyState>Još nema kreiranih grupa. Napravite prvu grupu iznad.</EmptyState>
      ) : (
        <SplitPane
          list={
            <div
              style={{
                padding: "var(--space-4)",
                display: "grid",
                gap: "var(--space-4)",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
              }}
            >
              {filteredGroups.length === 0 ? (
                <EmptyState>Nema grupa koje odgovaraju filterima.</EmptyState>
              ) : (
                filteredGroups.map((g) => (
                  <GroupCard
                    key={g.id}
                    group={g}
                    members={members.data?.[g.id]}
                    trainerNames={(trainersByGroup[g.id] ?? []).map((id) => peopleMap[id] ?? id)}
                    nextSession={nextSessionByGroup[g.id]}
                    active={g.id === selectedId}
                    onSelect={() => setSelectedId(g.id)}
                  />
                ))
              )}
            </div>
          }
          detail={
            selectedGroup ? (
              <GroupDetail
                group={selectedGroup}
                members={members.data?.[selectedGroup.id] ?? []}
                peopleOptions={people.data?.items ?? []}
                peopleMap={peopleMap}
                sessionsForGroup={(sessions.data ?? []).filter((s) => s.group_id === selectedGroup.id)}
                seriesForGroup={(series.data ?? []).filter((s) => s.group_id === selectedGroup.id)}
                locationsMap={locationsMap}
                onMembersChanged={afterMemberChange}
              />
            ) : (
              <EmptyState>Izaberite grupu sa liste da vidite detalje.</EmptyState>
            )
          }
        />
      )}
    </div>
  );
}

function CreateGroupForm({
  onCreated,
  onCancel,
  people,
  locations,
}: {
  onCreated: () => void;
  onCancel: () => void;
  people: PersonSummary[];
  locations: LocationSummary[];
}) {
  const [name, setName] = useState("");
  const [capacityMode, setCapacityMode] = useState<Group["capacity_mode"]>("UNLIMITED");
  const [capacity, setCapacity] = useState(20);
  /*
   * The group is the default source for a new session's trainer and location.
   * Setting them here means "svake srede u 18:00" can be scheduled without
   * re-picking both every time; whoever creates a session may still override
   * either for that one occurrence.
   */
  const [defaultTrainer, setDefaultTrainer] = useState("");
  const [defaultLocation, setDefaultLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post<Group>("/groups", {
        name,
        capacity_mode: capacityMode,
        capacity: capacityMode === "LIMITED" ? capacity : null,
        default_trainer_person_id: defaultTrainer || null,
        default_location_id: defaultLocation || null,
      });
      setName("");
      setCapacityMode("UNLIMITED");
      setDefaultTrainer("");
      setDefaultLocation("");
      onCreated();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" data-cy="group-create-form" style={{ marginBottom: "var(--space-4)" }}>
      <SectionHeader title="Nova grupa" />
      {error ? <SystemState error={error} /> : null}
      <form onSubmit={save} className="group-create-grid">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="g-name">Naziv grupe</label>
          <input id="g-name" value={name} onChange={(e) => setName(e.target.value)} required data-cy="group-name" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="g-capmode">Kapacitet</label>
          <select
            id="g-capmode"
            value={capacityMode}
            onChange={(e) => setCapacityMode(e.target.value as Group["capacity_mode"])}
            data-cy="group-capacity-mode"
          >
            <option value="UNLIMITED">Bez ograničenja</option>
            <option value="LIMITED">Ograničen broj mesta</option>
          </select>
        </div>
        {capacityMode === "LIMITED" ? (
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="g-cap">Broj mesta</label>
            <input
              id="g-cap"
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(Number(e.target.value))}
              required
              data-cy="group-capacity"
            />
          </div>
        ) : (
          <div />
        )}
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="g-trainer">Podrazumevani trener</label>
          <select
            id="g-trainer"
            value={defaultTrainer}
            onChange={(e) => setDefaultTrainer(e.target.value)}
            data-cy="group-default-trainer"
          >
            <option value="">Bez podrazumevanog</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="g-location">Podrazumevana lokacija</label>
          <select
            id="g-location"
            value={defaultLocation}
            onChange={(e) => setDefaultLocation(e.target.value)}
            data-cy="group-default-location"
          >
            <option value="">Bez podrazumevane</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} · {LOCATION_KIND_LABEL[l.kind]}
              </option>
            ))}
          </select>
        </div>
        <p className="field__hint group-create-grid__note">
          Podrazumevani trener i lokacija se prenose na svaki novi termin ove grupe. Za
          pojedinačni termin mogu se promeniti bez izmene grupe.
        </p>
        <div className="group-create-grid__actions">
          <Button type="submit" disabled={busy} data-cy="group-save">
            Sačuvaj grupu
          </Button>
          <Button type="button" variant="secondary" onClick={onCancel}>
            Odustani
          </Button>
        </div>
      </form>
    </section>
  );
}

function GroupCard({
  group,
  members,
  trainerNames,
  nextSession,
  active,
  onSelect,
}: {
  group: Group;
  members: GroupMember[] | undefined;
  trainerNames: string[];
  nextSession: ScheduleSession | undefined;
  active: boolean;
  onSelect: () => void;
}) {
  const count = members?.length ?? 0;
  const status = groupStatus(group, count);
  const trainerLabel = trainerNames.length > 0 ? trainerNames.join(", ") : "-";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cx("card", "card--interactive", active && "is-active")}
      data-cy="group-card"
      aria-pressed={active}
    >
      <SectionHeader
        title={group.name}
        subtitle={`Trener: ${trainerLabel}`}
        action={<StatusBadge tone={status.tone}>{status.label}</StatusBadge>}
      />
      <CapacityRow group={group} count={count} />
      <p
        style={{
          marginTop: "var(--space-3)",
          marginBottom: 0,
          color: "var(--text-secondary)",
          fontSize: "var(--text-sm)",
        }}
      >
        Sledeći termin · {nextSession ? formatWhen(nextSession.starts_at) : "nema zakazanih"}
      </p>
    </div>
  );
}

type DetailTab = "clanovi" | "raspored" | "treneri" | "osnovno";

function GroupDetail({
  group,
  members,
  peopleOptions,
  peopleMap,
  sessionsForGroup,
  seriesForGroup,
  locationsMap,
  onMembersChanged,
}: {
  group: Group;
  members: GroupMember[];
  peopleOptions: PersonSummary[];
  peopleMap: Record<string, string>;
  sessionsForGroup: ScheduleSession[];
  seriesForGroup: SeriesSummary[];
  locationsMap: Record<string, LocationSummary>;
  onMembersChanged: () => void;
}) {
  const [tab, setTab] = useState<DetailTab>("clanovi");
  const [addOpen, setAddOpen] = useState(false);
  const [personId, setPersonId] = useState("");
  const [role, setRole] = useState<GroupMemberRole>("MEMBER");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const memberIds = useMemo(() => new Set(members.map((m) => m.person_id)), [members]);
  // Capacity, counts and the roster are about participants; staff attached to
  // the group are running it, not occupying one of its places.
  const participants = useMemo(
    () => members.filter((m) => (m.role ?? "MEMBER") === "MEMBER"),
    [members],
  );
  const availablePeople = useMemo(
    () => peopleOptions.filter((p) => !memberIds.has(p.id)),
    [peopleOptions, memberIds],
  );

  async function addMember(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/groups/${group.id}/members`, { person_id: personId, role });
      setPersonId("");
      setRole("MEMBER");
      setAddOpen(false);
      onMembersChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const trainerIds = useMemo(() => {
    const set = new Set<string>();
    seriesForGroup.forEach((s) => s.trainer_person_id && set.add(s.trainer_person_id));
    return Array.from(set);
  }, [seriesForGroup]);
  const trainerLabel = trainerIds.length > 0 ? trainerIds.map((id) => peopleMap[id] ?? id).join(", ") : "-";

  const sortedSessions = useMemo(
    () => [...sessionsForGroup].sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    [sessionsForGroup],
  );

  return (
    <div data-cy="group-detail">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-3)" }}>
        <div>
          <h2 style={{ margin: 0 }}>{group.name}</h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
            Trener: {trainerLabel} · {participants.length}{" "}
            {participants.length === 1 ? "polaznik" : "polaznika"}
          </p>
        </div>
        <Button onClick={() => setAddOpen((v) => !v)} data-cy="group-add-member">
          Dodaj člana
        </Button>
      </div>

      {addOpen ? (
        <form
          onSubmit={addMember}
          style={{ display: "flex", gap: "var(--space-2)", alignItems: "end", margin: "var(--space-4) 0" }}
        >
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label htmlFor="dm-person">Osoba</label>
            <select
              id="dm-person"
              value={personId}
              onChange={(e) => setPersonId(e.target.value)}
              required
              data-cy="member-select"
            >
              <option value="">Izaberi osobu…</option>
              {availablePeople.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label htmlFor="dm-role">Uloga u grupi</label>
            <select
              id="dm-role"
              value={role}
              onChange={(e) => setRole(e.target.value as GroupMemberRole)}
              data-cy="member-role"
            >
              {(Object.keys(GROUP_MEMBER_ROLE_LABEL) as GroupMemberRole[]).map((r) => (
                <option key={r} value={r}>
                  {GROUP_MEMBER_ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" variant="secondary" disabled={busy} data-cy="member-add">
            Dodaj
          </Button>
        </form>
      ) : null}
      {error ? <SystemState error={error} /> : null}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)", margin: "var(--space-4) 0" }}>
        <StatTile
          label="Kapacitet"
          value={
            group.capacity_mode === "LIMITED" && group.capacity != null
              ? `${participants.length} od ${group.capacity}`
              : `${participants.length} · bez ograničenja`
          }
        />
        <StatTile label="Mesečna cena" value="Uskoro" delta={{ label: "Cenovnik dolazi (#7)", tone: "neutral" }} />
      </div>

      <SegmentedControl
        ariaLabel="Detalji grupe"
        value={tab}
        onChange={setTab}
        options={[
          { value: "clanovi", label: "Članovi" },
          { value: "raspored", label: "Raspored" },
          { value: "treneri", label: "Treneri" },
          { value: "osnovno", label: "Osnovni podaci" },
        ]}
      />

      <div style={{ marginTop: "var(--space-4)" }}>
        {tab === "clanovi" ? <MembersTab members={members} /> : null}
        {tab === "raspored" ? <ScheduleTab sessions={sortedSessions} /> : null}
        {tab === "treneri" ? (
          <TrainersTab trainerIds={trainerIds} peopleMap={peopleMap} seriesForGroup={seriesForGroup} />
        ) : null}
        {tab === "osnovno" ? (
          <BasicsTab group={group} peopleMap={peopleMap} locationsMap={locationsMap} />
        ) : null}
      </div>
    </div>
  );
}

function MembersTab({ members }: { members: GroupMember[] }) {
  if (members.length === 0) return <EmptyState>Još nema članova u ovoj grupi.</EmptyState>;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-1)" }}>
      {members.map((m) => (
        <li
          key={m.membership_id}
          data-cy="group-member-row"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "var(--space-2) 0",
            borderBottom: "1px solid var(--border-default)",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            <span
              aria-hidden
              style={{
                width: 36,
                height: 36,
                borderRadius: "50%",
                background: "var(--action-surface)",
                color: "var(--action-primary-hover)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 700,
                fontSize: "var(--text-sm)",
                flex: "none",
              }}
            >
              {initials(m.display_name)}
            </span>
            {m.display_name}
          </span>
          {/* Says what this person IS here, rather than labelling everyone
              "Član": a trainer on a group's list is not one of its members. */}
          <StatusBadge tone={(m.role ?? "MEMBER") === "MEMBER" ? "info" : "neutral"}>
            {GROUP_MEMBER_ROLE_LABEL[m.role ?? "MEMBER"]}
          </StatusBadge>
        </li>
      ))}
    </ul>
  );
}

function ScheduleTab({ sessions }: { sessions: ScheduleSession[] }) {
  if (sessions.length === 0) return <EmptyState>Nema zakazanih termina za ovu grupu.</EmptyState>;
  return (
    <table className="data" data-cy="group-session-list">
      <thead>
        <tr>
          <th>Početak</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {sessions.map((s) => (
          <tr key={s.id} data-cy="group-session-row">
            <td>{formatDateTime(s.starts_at)}</td>
            <td>
              <StatusBadge tone={s.status === "SCHEDULED" ? "success" : "info"}>{s.status}</StatusBadge>
            </td>
            <td>
              <Link className="btn btn--secondary btn--sm" to={`/raspored/${s.id}/prisustvo`}>
                Prisustvo
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TrainersTab({
  trainerIds,
  peopleMap,
  seriesForGroup,
}: {
  trainerIds: string[];
  peopleMap: Record<string, string>;
  seriesForGroup: SeriesSummary[];
}) {
  return (
    <div>
      {trainerIds.length === 0 ? (
        <EmptyState>Nema dodeljenih trenera. Trener se dodeljuje kroz seriju termina u Rasporedu.</EmptyState>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
          {trainerIds.map((id) => (
            <li
              key={id}
              data-cy="group-trainer-row"
              style={{ padding: "var(--space-2) 0", borderBottom: "1px solid var(--border-default)" }}
            >
              <strong>{peopleMap[id] ?? "Nepoznat trener"}</strong>
              <div style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                {seriesForGroup
                  .filter((s) => s.trainer_person_id === id)
                  .map((s) => `${FREQ_LABEL[s.frequency]} u ${s.local_time}`)
                  .join(", ")}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Link className="btn btn--secondary" to="/raspored" style={{ marginTop: "var(--space-4)" }}>
        Otvori raspored
      </Link>
    </div>
  );
}

function BasicsTab({
  group,
  peopleMap,
  locationsMap,
}: {
  group: Group;
  peopleMap: Record<string, string>;
  locationsMap: Record<string, LocationSummary>;
}) {
  const defaultLocation = group.default_location_id
    ? locationsMap[group.default_location_id]
    : undefined;
  const rows: Array<[string, ReactNode]> = [
    ["Naziv", group.name],
    [
      "Kapacitet",
      group.capacity_mode === "LIMITED" && group.capacity != null
        ? `${group.capacity} mesta`
        : "Bez ograničenja",
    ],
    [
      "Podrazumevani trener",
      group.default_trainer_person_id
        ? (peopleMap[group.default_trainer_person_id] ?? "Nepoznata osoba")
        : "Nije određen",
    ],
    [
      "Podrazumevana lokacija",
      defaultLocation
        ? `${defaultLocation.name} · ${LOCATION_KIND_LABEL[defaultLocation.kind]}`
        : "Nije određena",
    ],
    ["Mesečna cena", "Uskoro: cenovnik grupa dolazi u narednoj fazi (#7)."],
  ];
  return (
    <div>
      <dl style={{ display: "grid", gridTemplateColumns: "160px 1fr", rowGap: "var(--space-2)", columnGap: "var(--space-3)", margin: 0 }}>
        {rows.map(([label, value]) => (
          <div key={label} style={{ display: "contents" }}>
            <dt style={{ color: "var(--text-secondary)", fontWeight: 600, fontSize: "var(--text-sm)" }}>{label}</dt>
            <dd style={{ margin: 0 }}>{value}</dd>
          </div>
        ))}
      </dl>
      <Button variant="secondary" disabled title="Uskoro" style={{ marginTop: "var(--space-4)" }}>
        Izmeni osnovne podatke
      </Button>
    </div>
  );
}
