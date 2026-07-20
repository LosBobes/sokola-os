import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, newIdempotencyKey } from "../../api/client";
import type {
  ConflictCheck,
  Group,
  Organization,
  Page,
  PersonSummary,
  SessionCancellationReasonCode,
  SessionChangeReasonCode,
  SessionEditScope,
  SessionStatus,
  SessionSummary,
} from "../../api/types";
import { useSession } from "../../auth/session";
import { PageHeader } from "../../components/shell";
import {
  EmptyState,
  FilterBar,
  FilterChip,
  InlineNotice,
  LoadingState,
  SegmentedControl,
  StatusBadge,
  SystemState,
  TableContainer,
} from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import "./Schedule.css";

/* ===================================================================== */
/* Date helpers — plain Date math, browser-local time (matches the rest  */
/* of the app: existing routes format timestamps with toLocaleString and */
/* never convert to the organization's declared timezone explicitly).    */
/* ===================================================================== */

const RANGE_DAYS = 90; // "Spisak" rolling window — same horizon the page used before.
const HOUR_PX = 56;
const DEFAULT_START_HOUR = 8;
const DEFAULT_END_HOUR = 20;

function startOfDay(d: Date): Date {
  const c = new Date(d);
  c.setHours(0, 0, 0, 0);
  return c;
}
function addDays(d: Date, n: number): Date {
  const c = new Date(d);
  c.setDate(c.getDate() + n);
  return c;
}
function startOfWeek(d: Date): Date {
  const c = startOfDay(d);
  const day = c.getDay(); // 0 = Sun .. 6 = Sat
  const diff = day === 0 ? -6 : 1 - day;
  return addDays(c, diff);
}
function sameDay(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}
function fmtWeekday(d: Date): string {
  return d.toLocaleDateString("sr-Latn", { weekday: "short" }).toUpperCase();
}
function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("sr-Latn", { hour: "2-digit", minute: "2-digit" });
}
function fmtDayLabel(d: Date): string {
  return d.toLocaleDateString("sr-Latn", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
}
function fmtWeekLabel(from: Date, toInclusive: Date): string {
  const sameMonth = from.getMonth() === toInclusive.getMonth() && from.getFullYear() === toInclusive.getFullYear();
  const year = toInclusive.getFullYear();
  if (sameMonth) {
    const month = toInclusive.toLocaleDateString("sr-Latn", { month: "long" });
    return `${from.getDate()}–${toInclusive.getDate()}. ${month} ${year}.`;
  }
  const fromLabel = from.toLocaleDateString("sr-Latn", { day: "2-digit", month: "short" });
  const toLabel = toInclusive.toLocaleDateString("sr-Latn", { day: "2-digit", month: "short" });
  return `${fromLabel} – ${toLabel} ${year}.`;
}

function gridBounds(sessions: SessionSummary[]): { startHour: number; endHour: number } {
  let minH = DEFAULT_START_HOUR;
  let maxH = DEFAULT_END_HOUR;
  for (const s of sessions) {
    const start = new Date(s.starts_at);
    const end = new Date(s.ends_at);
    minH = Math.min(minH, start.getHours());
    maxH = Math.max(maxH, end.getMinutes() > 0 ? end.getHours() + 1 : end.getHours());
  }
  return { startHour: Math.max(0, minH), endHour: Math.min(24, Math.max(maxH, minH + 1)) };
}

const BLOCK_HUES = ["primary", "gold", "info", "warning"] as const;
function hueForGroup(groupId: string): (typeof BLOCK_HUES)[number] {
  let h = 0;
  for (let i = 0; i < groupId.length; i++) h = (h * 31 + groupId.charCodeAt(i)) >>> 0;
  return BLOCK_HUES[h % BLOCK_HUES.length] ?? "primary";
}

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

const STATUS_LABEL: Record<SessionStatus, string> = {
  SCHEDULED: "Zakazano",
  CANCELLED: "Otkazano",
  COMPLETED: "Završeno",
};
function statusTone(status: SessionStatus): "success" | "error" | "info" {
  if (status === "SCHEDULED") return "success";
  if (status === "CANCELLED") return "error";
  return "info";
}

const CANCEL_REASON_LABEL: Record<SessionCancellationReasonCode, string> = {
  WEATHER: "Vremenski uslovi",
  TRAINER_UNAVAILABLE: "Trener nije dostupan",
  HOLIDAY: "Praznik",
  LOW_ATTENDANCE: "Slabo prisustvo",
  OTHER: "Ostalo",
};
const CHANGE_REASON_LABEL: Record<SessionChangeReasonCode, string> = {
  TIME_CHANGE: "Promena vremena",
  LOCATION_CHANGE: "Promena lokacije",
  TRAINER_CHANGE: "Promena trenera",
  OTHER: "Ostalo",
};

type ViewMode = "day" | "week" | "list";

/* ===================================================================== */
/* Page                                                                   */
/* ===================================================================== */

export function SchedulePage() {
  const { activeContext } = useSession();
  const org = useAsync(() => api.get<Organization>("/organizations/current"), []);
  const groups = useAsync(() => api.get<Page<Group>>("/groups?limit=200"), []);
  const people = useAsync(() => api.get<Page<PersonSummary>>("/people?limit=500"), []);

  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [anchor, setAnchor] = useState(() => new Date());
  const [groupFilter, setGroupFilter] = useState("");
  const [trainerFilter, setTrainerFilter] = useState("");
  const [scheduledOnly, setScheduledOnly] = useState(false);
  const [selected, setSelected] = useState<SessionSummary | null>(null);

  const newSessionRef = useRef<HTMLDivElement>(null);
  const groupSelectRef = useRef<HTMLSelectElement>(null);

  const today = useMemo(() => new Date(), []);
  const weekStart = useMemo(() => startOfWeek(anchor), [anchor]);
  const weekDays = useMemo(() => [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(weekStart, i)), [weekStart]);
  const gridDays = viewMode === "day" ? [startOfDay(anchor)] : weekDays;

  const range = useMemo(() => {
    if (viewMode === "day") {
      const from = startOfDay(anchor);
      return { from, to: addDays(from, 1) };
    }
    if (viewMode === "week") {
      return { from: weekStart, to: addDays(weekStart, 7) };
    }
    const from = startOfDay(today);
    return { from, to: addDays(from, RANGE_DAYS) };
  }, [viewMode, anchor, weekStart, today]);

  const sessions = useAsync(
    () =>
      api.get<SessionSummary[]>(
        `/schedule/sessions?date_from=${encodeURIComponent(range.from.toISOString())}&date_to=${encodeURIComponent(range.to.toISOString())}`,
      ),
    [range.from.getTime(), range.to.getTime()],
  );

  const groupsMap = useMemo(
    () => new Map((groups.data?.items ?? []).map((g) => [g.id, g])),
    [groups.data],
  );
  const peopleMap = useMemo(
    () => new Map((people.data?.items ?? []).map((p) => [p.id, p.display_name])),
    [people.data],
  );

  const trainerOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const s of sessions.data ?? []) if (s.trainer_person_id) ids.add(s.trainer_person_id);
    return Array.from(ids)
      .map((id) => ({ value: id, label: peopleMap.get(id) ?? "Nepoznat trener" }))
      .sort((a, b) => a.label.localeCompare(b.label, "sr"));
  }, [sessions.data, peopleMap]);

  const filtered = useMemo(() => {
    let list = sessions.data ?? [];
    if (groupFilter) list = list.filter((s) => s.group_id === groupFilter);
    if (trainerFilter) list = list.filter((s) => s.trainer_person_id === trainerFilter);
    if (scheduledOnly) list = list.filter((s) => s.status === "SCHEDULED");
    return list;
  }, [sessions.data, groupFilter, trainerFilter, scheduledOnly]);

  const sortedForList = useMemo(
    () => [...filtered].sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    [filtered],
  );

  function focusNewSession() {
    newSessionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    groupSelectRef.current?.focus();
  }

  function reloadAll() {
    sessions.reload();
  }

  const orgName = org.data?.name ?? activeContext?.organization_name ?? "";
  const timezone = org.data?.timezone ?? "Europe/Belgrade";

  return (
    <div>
      <PageHeader
        title="Raspored"
        action={
          <button
            type="button"
            className="btn btn--primary"
            onClick={focusNewSession}
            data-cy="schedule-new-session"
          >
            <PlusIcon /> Novi termin
          </button>
        }
      />
      {orgName ? (
        <p className="schedule-subtitle">
          {orgName} · {timezone}
        </p>
      ) : null}

      <FilterBar>
        <FilterChip caret disabled title="Programi još nisu povezani sa terminima">
          Svi programi
        </FilterChip>
        <FilterMenu
          triggerLabel="Sve grupe"
          value={groupFilter}
          onChange={setGroupFilter}
          options={(groups.data?.items ?? []).map((g) => ({ value: g.id, label: g.name }))}
        />
        <FilterMenu
          triggerLabel="Svi treneri"
          value={trainerFilter}
          onChange={setTrainerFilter}
          options={trainerOptions}
        />
        <FilterChip caret disabled title="Sale još nisu povezane sa terminima">
          Sve sale
        </FilterChip>
        <FilterChip active={scheduledOnly} onClick={() => setScheduledOnly((v) => !v)}>
          Zakazani termini
        </FilterChip>
      </FilterBar>

      <div className="schedule-nav">
        {viewMode === "list" ? (
          <span className="schedule-nav__label schedule-nav__label--muted">
            Svi termini u narednih {RANGE_DAYS} dana
          </span>
        ) : (
          <div className="schedule-nav__range">
            <button
              type="button"
              className="btn btn--secondary btn--icon"
              aria-label="Prethodni period"
              title="Prethodni period"
              onClick={() => setAnchor((a) => addDays(a, viewMode === "day" ? -1 : -7))}
            >
              <ChevronIcon dir="left" />
            </button>
            <span className="schedule-nav__label" data-cy="schedule-range-label">
              {viewMode === "day" ? fmtDayLabel(anchor) : fmtWeekLabel(weekStart, addDays(weekStart, 6))}
            </span>
            <button
              type="button"
              className="btn btn--secondary btn--icon"
              aria-label="Sledeći period"
              title="Sledeći period"
              onClick={() => setAnchor((a) => addDays(a, viewMode === "day" ? 1 : 7))}
            >
              <ChevronIcon dir="right" />
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setAnchor(new Date())}
              data-cy="schedule-today"
            >
              Danas
            </button>
          </div>
        )}
        <SegmentedControl
          ariaLabel="Prikaz rasporeda"
          value={viewMode}
          onChange={setViewMode}
          options={[
            { value: "day", label: "Dan" },
            { value: "week", label: "Nedelja" },
            { value: "list", label: "Spisak" },
          ]}
        />
      </div>

      {sessions.loading ? (
        <LoadingState />
      ) : sessions.error ? (
        <SystemState error={sessions.error} />
      ) : viewMode === "list" ? (
        sortedForList.length === 0 ? (
          <EmptyState>Još nema zakazanih termina.</EmptyState>
        ) : (
          <SessionListView
            sessions={sortedForList}
            groupsMap={groupsMap}
            peopleMap={peopleMap}
            onSelect={setSelected}
          />
        )
      ) : (
        <ScheduleGrid days={gridDays} sessions={filtered} today={today} groupsMap={groupsMap} onSelect={setSelected} />
      )}

      <div ref={newSessionRef}>
        <NewSessionCard
          groups={groups.data?.items ?? []}
          groupSelectRef={groupSelectRef}
          onCreated={reloadAll}
        />
      </div>

      <SessionDetailDialog
        session={selected}
        groupsMap={groupsMap}
        people={people.data?.items ?? []}
        onClose={() => setSelected(null)}
        onChanged={reloadAll}
      />
    </div>
  );
}

/* ===================================================================== */
/* Filter dropdown (FilterChip trigger + popover of options)             */
/* ===================================================================== */

function FilterMenu({
  triggerLabel,
  value,
  onChange,
  options,
}: {
  triggerLabel: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.value === value);

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

  return (
    <div className="filter-menu" ref={ref}>
      <FilterChip
        caret
        active={Boolean(value)}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {current ? current.label : triggerLabel}
      </FilterChip>
      {open ? (
        <div className="filter-menu__pop" role="menu">
          <button
            type="button"
            role="menuitem"
            className={cx("filter-menu__item", value === "" && "filter-menu__item--active")}
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
          >
            {triggerLabel}
          </button>
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="menuitem"
              className={cx("filter-menu__item", value === o.value && "filter-menu__item--active")}
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ===================================================================== */
/* Week / day calendar grid                                              */
/* ===================================================================== */

function ScheduleGrid({
  days,
  sessions,
  today,
  groupsMap,
  onSelect,
}: {
  days: Date[];
  sessions: SessionSummary[];
  today: Date;
  groupsMap: Map<string, Group>;
  onSelect: (s: SessionSummary) => void;
}) {
  const { startHour, endHour } = useMemo(() => gridBounds(sessions), [sessions]);
  const hours = useMemo(() => {
    const arr: number[] = [];
    for (let h = startHour; h < endHour; h++) arr.push(h);
    return arr;
  }, [startHour, endHour]);
  const totalHeight = hours.length * HOUR_PX;

  const byDay = useMemo(() => {
    const map = new Map<string, SessionSummary[]>();
    for (const day of days) map.set(day.toDateString(), []);
    for (const s of sessions) {
      const key = new Date(s.starts_at).toDateString();
      if (map.has(key)) map.get(key)!.push(s);
    }
    return map;
  }, [days, sessions]);

  function blockStyle(s: SessionSummary): React.CSSProperties {
    const start = new Date(s.starts_at);
    const end = new Date(s.ends_at);
    const top = (((start.getHours() - startHour) * 60 + start.getMinutes()) / 60) * HOUR_PX;
    const rawHeight = ((end.getTime() - start.getTime()) / 60000 / 60) * HOUR_PX;
    return { top: `${Math.max(0, top)}px`, height: `${Math.max(28, rawHeight)}px` };
  }

  return (
    <div className="schedule-scroll">
      <div className="schedule-grid">
        <div className="schedule-grid__header">
          <div className="schedule-grid__gutter" />
          {days.map((day) => (
            <div
              key={day.toISOString()}
              className={cx("schedule-grid__daylabel", sameDay(day, today) && "schedule-grid__daylabel--today")}
            >
              <span className="schedule-grid__weekday">{fmtWeekday(day)}</span>
              <span className="schedule-grid__daynum">{day.getDate()}</span>
            </div>
          ))}
        </div>
        <div className="schedule-grid__body" style={{ height: `${totalHeight}px` }}>
          <div className="schedule-grid__gutter">
            {hours.map((h) => (
              <div key={h} className="schedule-grid__hourlabel" style={{ height: `${HOUR_PX}px` }}>
                {String(h).padStart(2, "0")}.00
              </div>
            ))}
          </div>
          {days.map((day) => {
            const daySessions = byDay.get(day.toDateString()) ?? [];
            return (
              <div
                key={day.toISOString()}
                className={cx("schedule-grid__daycol", sameDay(day, today) && "schedule-grid__daycol--today")}
              >
                {hours.map((h) => (
                  <div key={h} className="schedule-grid__hourrow" style={{ height: `${HOUR_PX}px` }} />
                ))}
                <div className="schedule-grid__blocks">
                  {daySessions.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      className={cx(
                        "session-block",
                        `session-block--${hueForGroup(s.group_id)}`,
                        s.status === "CANCELLED" && "session-block--cancelled",
                      )}
                      style={blockStyle(s)}
                      onClick={() => onSelect(s)}
                      data-cy="calendar-session"
                    >
                      <span className="session-block__title">
                        {s.title || groupsMap.get(s.group_id)?.name || "Termin"}
                      </span>
                      <span className="session-block__time">
                        {fmtTime(s.starts_at)}–{fmtTime(s.ends_at)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ===================================================================== */
/* Spisak (flat list) view                                               */
/* ===================================================================== */

function SessionListView({
  sessions,
  groupsMap,
  peopleMap,
  onSelect,
}: {
  sessions: SessionSummary[];
  groupsMap: Map<string, Group>;
  peopleMap: Map<string, string>;
  onSelect: (s: SessionSummary) => void;
}) {
  return (
    <TableContainer>
      <table className="data" data-cy="session-list">
        <thead>
          <tr>
            <th>Termin</th>
            <th>Vreme</th>
            <th>Trener</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.id} data-cy="session-row">
              <td>{s.title || groupsMap.get(s.group_id)?.name || "Termin"}</td>
              <td>
                {fmtDayLabel(new Date(s.starts_at))}, {fmtTime(s.starts_at)}–{fmtTime(s.ends_at)}
              </td>
              <td>{s.trainer_person_id ? (peopleMap.get(s.trainer_person_id) ?? "Nepoznat") : "—"}</td>
              <td>
                <StatusBadge tone={statusTone(s.status)}>{STATUS_LABEL[s.status]}</StatusBadge>
              </td>
              <td style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
                <button
                  className="btn btn--secondary btn--sm"
                  type="button"
                  onClick={() => onSelect(s)}
                  data-cy="session-detail-open"
                >
                  Detalji
                </button>
                <Link
                  className="btn btn--secondary btn--sm"
                  to={`/raspored/${s.id}/prisustvo`}
                  data-cy="session-attendance"
                >
                  Prisustvo
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableContainer>
  );
}

/* ===================================================================== */
/* Novi termin — create form (data-cy hooks preserved from the prior UI) */
/* ===================================================================== */

function NewSessionCard({
  groups,
  groupSelectRef,
  onCreated,
}: {
  groups: Group[];
  groupSelectRef: React.RefObject<HTMLSelectElement | null>;
  onCreated: () => void;
}) {
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
    <section className="card" data-cy="new-session-card">
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
          <select
            id="s-group"
            ref={groupSelectRef}
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
            required
            data-cy="session-group"
          >
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

/* ===================================================================== */
/* Session detail / edit / cancel dialog                                 */
/* ===================================================================== */

function SessionDetailDialog({
  session,
  groupsMap,
  people,
  onClose,
  onChanged,
}: {
  session: SessionSummary | null;
  groupsMap: Map<string, Group>;
  people: PersonSummary[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"view" | "edit" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const [editTime, setEditTime] = useState("");
  const [editDuration, setEditDuration] = useState(60);
  const [editTitle, setEditTitle] = useState("");
  const [editTrainer, setEditTrainer] = useState("");
  const [editReason, setEditReason] = useState<SessionChangeReasonCode>("OTHER");
  const [editScope, setEditScope] = useState<SessionEditScope>("SINGLE");

  const [cancelReason, setCancelReason] = useState<SessionCancellationReasonCode>("OTHER");
  const [cancelNote, setCancelNote] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (session && !dialog.open) dialog.showModal();
    else if (!session && dialog.open) dialog.close();
  }, [session]);

  useEffect(() => {
    if (!session) return;
    setMode("view");
    setError(null);
    const start = new Date(session.starts_at);
    setEditTime(`${String(start.getHours()).padStart(2, "0")}:${String(start.getMinutes()).padStart(2, "0")}`);
    setEditDuration(Math.round((new Date(session.ends_at).getTime() - start.getTime()) / 60000));
    setEditTitle(session.title ?? "");
    setEditTrainer(session.trainer_person_id ?? "");
    setEditReason("OTHER");
    setEditScope("SINGLE");
    setCancelReason("OTHER");
    setCancelNote("");
  }, [session]);

  if (!session) {
    return <dialog ref={dialogRef} className="card session-dialog" onCancel={onClose} data-cy="session-detail" />;
  }

  const group = groupsMap.get(session.group_id);
  const trainerName = session.trainer_person_id
    ? (people.find((p) => p.id === session.trainer_person_id)?.display_name ?? "Nepoznat trener")
    : "Nije dodeljen";

  async function submitEdit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch<SessionSummary[]>(`/schedule/sessions/${session!.id}`, {
        local_time: editTime,
        duration_minutes: editDuration,
        title: editTitle || null,
        trainer_person_id: editTrainer || null,
        reason: editReason,
        scope: editScope,
      });
      onChanged();
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function submitCancel(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post<SessionSummary>(`/schedule/sessions/${session!.id}/cancel`, {
        reason: cancelReason,
        note: cancelNote || null,
      });
      onChanged();
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function reactivate() {
    setBusy(true);
    setError(null);
    try {
      await api.post<SessionSummary>(`/schedule/sessions/${session!.id}/reactivate`);
      onChanged();
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="card session-dialog"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose();
      }}
      data-cy="session-detail"
    >
      <div className="session-dialog__head">
        <div>
          <h2>{session.title || group?.name || "Termin"}</h2>
          <p className="session-dialog__meta">
            {fmtDayLabel(new Date(session.starts_at))} · {fmtTime(session.starts_at)}–{fmtTime(session.ends_at)}
          </p>
        </div>
        <button
          type="button"
          className="btn btn--secondary btn--icon"
          aria-label="Zatvori"
          title="Zatvori"
          onClick={onClose}
        >
          <CloseIcon />
        </button>
      </div>

      {error ? <SystemState error={error} /> : null}

      {mode === "view" ? (
        <>
          <StatusBadge tone={statusTone(session.status)}>{STATUS_LABEL[session.status]}</StatusBadge>
          <dl className="session-dialog__facts">
            <div>
              <dt>Grupa</dt>
              <dd>{group?.name ?? "—"}</dd>
            </div>
            <div>
              <dt>Trener</dt>
              <dd>{trainerName}</dd>
            </div>
            {session.status === "CANCELLED" && session.cancellation_reason ? (
              <div>
                <dt>Razlog otkazivanja</dt>
                <dd>{CANCEL_REASON_LABEL[session.cancellation_reason]}</dd>
              </div>
            ) : null}
          </dl>
          <div className="session-dialog__actions">
            <button
              className="btn btn--secondary"
              type="button"
              onClick={() => setMode("edit")}
              data-cy="session-edit-open"
            >
              Izmeni
            </button>
            {session.status === "SCHEDULED" ? (
              <>
                <Link
                  className="btn btn--secondary"
                  to={`/raspored/${session.id}/prisustvo`}
                  data-cy="session-attendance"
                >
                  Prisustvo
                </Link>
                <button
                  className="btn btn--secondary"
                  type="button"
                  onClick={() => setMode("cancel")}
                  data-cy="session-cancel-open"
                >
                  Otkaži termin
                </button>
              </>
            ) : null}
            {session.status === "CANCELLED" ? (
              <button
                className="btn btn--primary"
                type="button"
                onClick={reactivate}
                disabled={busy}
                data-cy="session-reactivate"
              >
                Vrati u zakazano
              </button>
            ) : null}
          </div>
        </>
      ) : null}

      {mode === "edit" ? (
        <form onSubmit={submitEdit} data-cy="session-edit-form">
          <div className="field">
            <label htmlFor="e-time">Vreme početka</label>
            <input
              id="e-time"
              type="time"
              value={editTime}
              onChange={(e) => setEditTime(e.target.value)}
              required
              data-cy="session-edit-time"
            />
          </div>
          <div className="field">
            <label htmlFor="e-dur">Trajanje (min)</label>
            <input
              id="e-dur"
              type="number"
              min={15}
              step={15}
              value={editDuration}
              onChange={(e) => setEditDuration(Number(e.target.value))}
              data-cy="session-edit-duration"
            />
          </div>
          <div className="field">
            <label htmlFor="e-title">Naziv</label>
            <input
              id="e-title"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              data-cy="session-edit-title"
            />
          </div>
          <div className="field">
            <label htmlFor="e-trainer">Trener</label>
            <select
              id="e-trainer"
              value={editTrainer}
              onChange={(e) => setEditTrainer(e.target.value)}
              data-cy="session-edit-trainer"
            >
              <option value="">Nije dodeljen</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>
          {session.series_id ? (
            <div className="field">
              <label htmlFor="e-scope">Primeni na</label>
              <select
                id="e-scope"
                value={editScope}
                onChange={(e) => setEditScope(e.target.value as SessionEditScope)}
                data-cy="session-edit-scope"
              >
                <option value="SINGLE">Samo ovaj termin</option>
                <option value="THIS_AND_FUTURE">Ovaj i budući termini</option>
                <option value="ALL_FUTURE">Svi budući termini</option>
              </select>
            </div>
          ) : null}
          <div className="field">
            <label htmlFor="e-reason">Razlog izmene</label>
            <select
              id="e-reason"
              value={editReason}
              onChange={(e) => setEditReason(e.target.value as SessionChangeReasonCode)}
              data-cy="session-edit-reason"
            >
              {(Object.keys(CHANGE_REASON_LABEL) as SessionChangeReasonCode[]).map((code) => (
                <option key={code} value={code}>
                  {CHANGE_REASON_LABEL[code]}
                </option>
              ))}
            </select>
          </div>
          <div className="session-dialog__actions">
            <button className="btn btn--primary" type="submit" disabled={busy} data-cy="session-edit-save">
              Sačuvaj izmene
            </button>
            <button className="btn btn--secondary" type="button" onClick={() => setMode("view")}>
              Nazad
            </button>
          </div>
        </form>
      ) : null}

      {mode === "cancel" ? (
        <form onSubmit={submitCancel} data-cy="session-cancel-form">
          <div className="field">
            <label htmlFor="c-reason">Razlog otkazivanja</label>
            <select
              id="c-reason"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value as SessionCancellationReasonCode)}
              required
              data-cy="session-cancel-reason"
            >
              {(Object.keys(CANCEL_REASON_LABEL) as SessionCancellationReasonCode[]).map((code) => (
                <option key={code} value={code}>
                  {CANCEL_REASON_LABEL[code]}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-note">Napomena (opciono)</label>
            <input id="c-note" value={cancelNote} onChange={(e) => setCancelNote(e.target.value)} data-cy="session-cancel-note" />
          </div>
          <div className="session-dialog__actions">
            <button className="btn btn--primary" type="submit" disabled={busy} data-cy="session-cancel-confirm">
              Otkaži termin
            </button>
            <button className="btn btn--secondary" type="button" onClick={() => setMode("view")}>
              Nazad
            </button>
          </div>
        </form>
      ) : null}
    </dialog>
  );
}

/* ===================================================================== */
/* Small inline icons (stroke, currentColor — matches shell.tsx style)   */
/* ===================================================================== */

function PlusIcon(): ReactNode {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
function ChevronIcon({ dir }: { dir: "left" | "right" }): ReactNode {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={dir === "left" ? "M15 5l-7 7 7 7" : "M9 5l7 7-7 7"} />
    </svg>
  );
}
function CloseIcon(): ReactNode {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}
