import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, newIdempotencyKey } from "../../api/client";
import type {
  ConflictCheck,
  EventItem,
  Group,
  LocationSummary,
  School,
  Page,
  PersonSummary,
  SeriesGenerateResult,
  SessionCancellationReasonCode,
  SessionChangeReasonCode,
  SessionEditScope,
  SessionSeriesSummary,
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
import {
  formatDate,
  formatDateRange,
  formatTime,
  formatWeekdayDate,
  formatWeekdayShort,
} from "../../lib/format";
import { EVENT_TYPE_LABEL, LOCATION_KIND_LABEL, timezoneCity } from "../../lib/labels";
import "./Schedule.css";

/* ===================================================================== */
/* Date helpers. Plain Date math in browser-local time; every user-facing */
/* string goes through lib/format so dates read DD.MM.YYYY everywhere.   */
/* ===================================================================== */

const RANGE_DAYS = 90; // "Spisak" rolling window, same horizon the page used before.
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

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* ===================================================================== */
/* Activities: one calendar carrying two different things                */
/*                                                                       */
/* Termini and Događaji live on the same Raspored, so the views work on a */
/* single normalized shape rather than branching on the source everywhere.*/
/* The `kind` is kept so a block can still LOOK different and open its    */
/* own detail dialog, which is the point of merging them: one calendar,   */
/* two clearly distinguishable things.                                    */
/* ===================================================================== */

type Activity =
  | { kind: "session"; id: string; start: Date; end: Date; session: SessionSummary }
  | { kind: "event"; id: string; start: Date; end: Date; event: EventItem };

/** Events may have no end time; give them a nominal hour so they can be drawn. */
const EVENT_FALLBACK_MINUTES = 60;

function toActivities(sessions: SessionSummary[], events: EventItem[]): Activity[] {
  const fromSessions: Activity[] = sessions.map((s) => ({
    kind: "session",
    id: s.id,
    start: new Date(s.starts_at),
    end: new Date(s.ends_at),
    session: s,
  }));
  const fromEvents: Activity[] = events.map((e) => {
    const start = new Date(e.starts_at);
    const end = e.ends_at
      ? new Date(e.ends_at)
      : new Date(start.getTime() + EVENT_FALLBACK_MINUTES * 60000);
    return { kind: "event", id: e.id, start, end, event: e };
  });
  return [...fromSessions, ...fromEvents];
}

function activityTitle(a: Activity, groupsMap: Map<string, Group>): string {
  if (a.kind === "event") return a.event.title;
  return a.session.title || groupsMap.get(a.session.group_id)?.name || "Termin";
}

function activityLocationId(a: Activity): string | null {
  return (a.kind === "session" ? a.session.location_id : a.event.location_id) ?? null;
}

function activityPersonId(a: Activity): string | null {
  return (
    (a.kind === "session" ? a.session.trainer_person_id : a.event.responsible_person_id) ?? null
  );
}

/**
 * When an activity happens, in words.
 *
 * A training slot is an hour on one day, so it reads as a date and a time
 * range. A camp runs for a week, and printing that as "10:57–10:57" (the same
 * clock time at both ends) is worse than useless , it looks like a bug and
 * hides the only thing that matters, which days it covers. Anything spanning
 * more than one day therefore reads as a date range.
 */
function activityWhen(a: Activity, { long = false } = {}): string {
  const sameDate = a.start.toDateString() === a.end.toDateString();
  if (!sameDate) return formatDateRange(a.start, a.end);
  const date = long ? formatWeekdayDate(a.start) : formatDate(a.start);
  return `${date} ${formatTime(a.start)}–${formatTime(a.end)}`;
}

function isCancelled(a: Activity): boolean {
  return a.kind === "session"
    ? a.session.status === "CANCELLED"
    : a.event.status === "CANCELLED";
}

function gridBounds(activities: Activity[]): { startHour: number; endHour: number } {
  let minH = DEFAULT_START_HOUR;
  let maxH = DEFAULT_END_HOUR;
  for (const a of activities) {
    minH = Math.min(minH, a.start.getHours());
    maxH = Math.max(maxH, a.end.getMinutes() > 0 ? a.end.getHours() + 1 : a.end.getHours());
  }
  return { startHour: Math.max(0, minH), endHour: Math.min(24, Math.max(maxH, minH + 1)) };
}

const BLOCK_HUES = ["primary", "gold", "info", "warning"] as const;
function hueForGroup(groupId: string): (typeof BLOCK_HUES)[number] {
  let h = 0;
  for (let i = 0; i < groupId.length; i++) h = (h * 31 + groupId.charCodeAt(i)) >>> 0;
  return BLOCK_HUES[h % BLOCK_HUES.length] ?? "primary";
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

const EVENT_STATUS_LABEL: Record<EventItem["status"], string> = {
  DRAFT: "Nacrt",
  PUBLISHED: "Objavljeno",
  CANCELLED: "Otkazano",
  COMPLETED: "Završeno",
};
function eventStatusTone(
  status: EventItem["status"],
): "success" | "error" | "info" | "neutral" {
  if (status === "PUBLISHED") return "success";
  if (status === "CANCELLED") return "error";
  if (status === "COMPLETED") return "info";
  return "neutral";
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

/*
 * Calendar-style edit scope, in the words a person picking it would use.
 * ALL_FUTURE rewrites the series template and every upcoming occurrence, so
 * "cela serija" is what it means to the operator, past occurrences are history
 * and are deliberately never rewritten.
 */
const EDIT_SCOPE_LABEL: Record<SessionEditScope, string> = {
  SINGLE: "Samo ovaj termin",
  THIS_AND_FUTURE: "Ovaj i svi naredni termini",
  ALL_FUTURE: "Cela serija",
};

type ViewMode = "day" | "week" | "list";
/** Which kinds of activity the calendar is showing. */
type KindFilter = "all" | "sessions" | "events";

/** 0 = Monday .. 6 = Sunday, matching the API's `date.weekday()`. */
const WEEKDAY_PICKER = [
  { value: 0, label: "Pon" },
  { value: 1, label: "Uto" },
  { value: 2, label: "Sre" },
  { value: 3, label: "Čet" },
  { value: 4, label: "Pet" },
  { value: 5, label: "Sub" },
  { value: 6, label: "Ned" },
] as const;

/* ===================================================================== */
/* Page                                                                   */
/* ===================================================================== */

export function SchedulePage() {
  const { activeContext } = useSession();
  const org = useAsync(() => api.get<School>("/schools/current"), []);
  const groups = useAsync(() => api.get<Page<Group>>("/groups?limit=100"), []);
  const people = useAsync(() => api.get<Page<PersonSummary>>("/people?limit=100"), []);
  const locations = useAsync(() => api.get<Page<LocationSummary>>("/locations?limit=100"), []);

  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [anchor, setAnchor] = useState(() => new Date());
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [groupFilter, setGroupFilter] = useState("");
  const [trainerFilter, setTrainerFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [scheduledOnly, setScheduledOnly] = useState(false);
  const [selected, setSelected] = useState<Activity | null>(null);

  const newSessionRef = useRef<HTMLDivElement>(null);
  const groupSelectRef = useRef<HTMLSelectElement>(null);

  const today = useMemo(() => new Date(), []);
  const weekStart = useMemo(() => startOfWeek(anchor), [anchor]);
  const weekDays = useMemo(
    () => [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(weekStart, i)),
    [weekStart],
  );
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

  const rangeQuery = `date_from=${encodeURIComponent(range.from.toISOString())}&date_to=${encodeURIComponent(range.to.toISOString())}`;

  const sessions = useAsync(
    () => api.get<SessionSummary[]>(`/schedule/sessions?${rangeQuery}`),
    [range.from.getTime(), range.to.getTime()],
  );
  /*
   * Events share the calendar but are a separate feed, and a school that has
   * not created any (or a role that may not read them) must not blank out the
   * timetable. A failure here degrades to "no events", never to an error page.
   */
  const events = useAsync(
    () => api.get<EventItem[]>(`/events/calendar?${rangeQuery}`).catch(() => [] as EventItem[]),
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
  const locationList = useMemo(() => locations.data?.items ?? [], [locations.data]);
  const locationsMap = useMemo(
    () => new Map(locationList.map((l) => [l.id, l])),
    [locationList],
  );

  const activities = useMemo(
    () => toActivities(sessions.data ?? [], events.data ?? []),
    [sessions.data, events.data],
  );

  /*
   * Trainer options come from the people actually referenced by the loaded
   * activities, so the menu never offers a name that would filter to nothing.
   */
  const trainerOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const a of activities) {
      const personId = activityPersonId(a);
      if (personId) ids.add(personId);
    }
    return Array.from(ids)
      .map((id) => ({ value: id, label: peopleMap.get(id) ?? "Nepoznata osoba" }))
      .sort((a, b) => a.label.localeCompare(b.label, "sr"));
  }, [activities, peopleMap]);

  const locationOptions = useMemo(
    () =>
      locationList.map((l) => ({
        value: l.id,
        label: `${l.name} · ${LOCATION_KIND_LABEL[l.kind]}`,
      })),
    [locationList],
  );

  const filtered = useMemo(() => {
    let list = activities;
    if (kindFilter === "sessions") list = list.filter((a) => a.kind === "session");
    if (kindFilter === "events") list = list.filter((a) => a.kind === "event");
    if (groupFilter) {
      list = list.filter((a) => a.kind === "session" && a.session.group_id === groupFilter);
    }
    if (trainerFilter) list = list.filter((a) => activityPersonId(a) === trainerFilter);
    if (locationFilter) list = list.filter((a) => activityLocationId(a) === locationFilter);
    if (scheduledOnly) list = list.filter((a) => !isCancelled(a));
    return list;
  }, [activities, kindFilter, groupFilter, trainerFilter, locationFilter, scheduledOnly]);

  const sortedForList = useMemo(
    () => [...filtered].sort((a, b) => a.start.getTime() - b.start.getTime()),
    [filtered],
  );

  function focusNewSession() {
    newSessionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    groupSelectRef.current?.focus();
  }

  function reloadAll() {
    sessions.reload();
    events.reload();
  }

  const orgName = org.data?.name ?? activeContext?.school_name ?? "";
  // The IANA zone id is an implementation detail; a person reads a city name.
  const city = timezoneCity(org.data?.timezone);

  const loading = sessions.loading || events.loading;

  return (
    <div>
      <PageHeader
        eyebrow="Termini i događaji"
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
          {orgName}
          {city ? ` · Vremenska zona: ${city}` : ""}
        </p>
      ) : null}

      <FilterBar>
        <FilterMenu
          triggerLabel="Sve aktivnosti"
          value={kindFilter === "all" ? "" : kindFilter}
          onChange={(v) => setKindFilter((v || "all") as KindFilter)}
          options={[
            { value: "sessions", label: "Termini" },
            { value: "events", label: "Događaji" },
          ]}
          dataCy="filter-kind"
        />
        <FilterMenu
          triggerLabel="Sve grupe"
          value={groupFilter}
          onChange={setGroupFilter}
          options={(groups.data?.items ?? []).map((g) => ({ value: g.id, label: g.name }))}
          dataCy="filter-group"
        />
        <FilterMenu
          triggerLabel="Svi treneri"
          value={trainerFilter}
          onChange={setTrainerFilter}
          options={trainerOptions}
          dataCy="filter-trainer"
        />
        <FilterMenu
          triggerLabel="Sve lokacije"
          value={locationFilter}
          onChange={setLocationFilter}
          options={locationOptions}
          emptyHint="Škola još nema unetih lokacija."
          dataCy="filter-location"
        />
        <FilterChip active={scheduledOnly} onClick={() => setScheduledOnly((v) => !v)}>
          Bez otkazanih
        </FilterChip>
      </FilterBar>

      <div className="schedule-nav">
        {viewMode === "list" ? (
          <span className="schedule-nav__label schedule-nav__label--muted">
            Sve aktivnosti u narednih {RANGE_DAYS} dana
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
              {viewMode === "day"
                ? formatWeekdayDate(anchor)
                : formatDateRange(weekStart, addDays(weekStart, 6))}
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

      {loading ? (
        <LoadingState />
      ) : sessions.error ? (
        <SystemState error={sessions.error} />
      ) : viewMode === "list" ? (
        sortedForList.length === 0 ? (
          <EmptyState>Još nema zakazanih aktivnosti.</EmptyState>
        ) : (
          <ActivityListView
            activities={sortedForList}
            groupsMap={groupsMap}
            peopleMap={peopleMap}
            locationsMap={locationsMap}
            onSelect={setSelected}
          />
        )
      ) : (
        <ScheduleGrid
          days={gridDays}
          activities={filtered}
          today={today}
          groupsMap={groupsMap}
          onSelect={setSelected}
        />
      )}

      <div ref={newSessionRef}>
        <NewSessionCard
          groups={groups.data?.items ?? []}
          people={people.data?.items ?? []}
          locations={locationList}
          groupSelectRef={groupSelectRef}
          onCreated={reloadAll}
        />
      </div>

      <ActivityDetailDialog
        activity={selected}
        groupsMap={groupsMap}
        people={people.data?.items ?? []}
        peopleMap={peopleMap}
        locations={locationList}
        locationsMap={locationsMap}
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
  emptyHint,
  dataCy,
}: {
  triggerLabel: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  emptyHint?: string;
  dataCy?: string;
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
        data-cy={dataCy}
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
          {options.length === 0 && emptyHint ? (
            <p className="filter-menu__empty">{emptyHint}</p>
          ) : null}
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="menuitem"
              className={cx(
                "filter-menu__item",
                value === o.value && "filter-menu__item--active",
              )}
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
  activities,
  today,
  groupsMap,
  onSelect,
}: {
  days: Date[];
  activities: Activity[];
  today: Date;
  groupsMap: Map<string, Group>;
  onSelect: (a: Activity) => void;
}) {
  const { startHour, endHour } = useMemo(() => gridBounds(activities), [activities]);
  const hours = useMemo(() => {
    const arr: number[] = [];
    for (let h = startHour; h < endHour; h++) arr.push(h);
    return arr;
  }, [startHour, endHour]);
  const totalHeight = hours.length * HOUR_PX;

  const byDay = useMemo(() => {
    const map = new Map<string, Activity[]>();
    for (const day of days) map.set(day.toDateString(), []);
    for (const a of activities) {
      const key = a.start.toDateString();
      if (map.has(key)) map.get(key)!.push(a);
    }
    return map;
  }, [days, activities]);

  function blockStyle(a: Activity): React.CSSProperties {
    const top = Math.max(
      0,
      (((a.start.getHours() - startHour) * 60 + a.start.getMinutes()) / 60) * HOUR_PX,
    );
    const rawHeight = ((a.end.getTime() - a.start.getTime()) / 60000 / 60) * HOUR_PX;
    /*
     * Clamped to the bottom of the day column. A training slot never reaches
     * it, but an event can run for a week, and its untrimmed height (24h ×
     * 7 × the hour height) would be a block several thousand pixels tall
     * spilling out of the grid and over everything under it. The block only
     * ever represents this day's share of the activity; the full span is on
     * the block's own label and in its detail.
     */
    const available = totalHeight - top;
    return {
      top: `${top}px`,
      height: `${Math.max(28, Math.min(rawHeight, available))}px`,
    };
  }

  return (
    <div className="schedule-scroll">
      <div className="schedule-grid">
        <div className="schedule-grid__header">
          <div className="schedule-grid__gutter" />
          {days.map((day) => (
            <div
              key={day.toISOString()}
              className={cx(
                "schedule-grid__daylabel",
                sameDay(day, today) && "schedule-grid__daylabel--today",
              )}
            >
              <span className="schedule-grid__weekday">{formatWeekdayShort(day)}</span>
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
            const dayActivities = byDay.get(day.toDateString()) ?? [];
            return (
              <div
                key={day.toISOString()}
                className={cx(
                  "schedule-grid__daycol",
                  sameDay(day, today) && "schedule-grid__daycol--today",
                )}
              >
                {hours.map((h) => (
                  <div key={h} className="schedule-grid__hourrow" style={{ height: `${HOUR_PX}px` }} />
                ))}
                <div className="schedule-grid__blocks">
                  {dayActivities.map((a) => (
                    <button
                      key={`${a.kind}-${a.id}`}
                      type="button"
                      className={cx(
                        "session-block",
                        // An event is not a training slot, so it never borrows a
                        // group's colour: it gets its own outlined treatment.
                        a.kind === "event"
                          ? "session-block--event"
                          : `session-block--${hueForGroup(a.session.group_id)}`,
                        isCancelled(a) && "session-block--cancelled",
                      )}
                      style={blockStyle(a)}
                      onClick={() => onSelect(a)}
                      data-cy={a.kind === "event" ? "calendar-event" : "calendar-session"}
                    >
                      <span className="session-block__title">
                        {a.kind === "event" ? <EventGlyph /> : null}
                        {activityTitle(a, groupsMap)}
                      </span>
                      <span className="session-block__time">
                        {a.start.toDateString() === a.end.toDateString()
                          ? `${formatTime(a.start)}–${formatTime(a.end)}`
                          : `od ${formatTime(a.start)} · više dana`}
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

function ActivityListView({
  activities,
  groupsMap,
  peopleMap,
  locationsMap,
  onSelect,
}: {
  activities: Activity[];
  groupsMap: Map<string, Group>;
  peopleMap: Map<string, string>;
  locationsMap: Map<string, LocationSummary>;
  onSelect: (a: Activity) => void;
}) {
  return (
    <TableContainer>
      <table className="data" data-cy="session-list">
        <thead>
          <tr>
            <th>Aktivnost</th>
            <th>Vrsta</th>
            <th>Vreme</th>
            <th>Trener / odgovorna osoba</th>
            <th>Lokacija</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {activities.map((a) => {
            const personId = activityPersonId(a);
            const locationId = activityLocationId(a);
            return (
              <tr
                key={`${a.kind}-${a.id}`}
                data-cy={a.kind === "event" ? "event-row" : "session-row"}
              >
                <td>{activityTitle(a, groupsMap)}</td>
                <td>
                  {a.kind === "event" ? (
                    <span className="badge badge--info">
                      {EVENT_TYPE_LABEL[a.event.type]}
                    </span>
                  ) : (
                    <span className="badge badge--neutral">Termin</span>
                  )}
                </td>
                <td>{activityWhen(a)}</td>
                <td>{personId ? (peopleMap.get(personId) ?? "Nepoznata osoba") : "-"}</td>
                <td>
                  {locationId ? (locationsMap.get(locationId)?.name ?? "Nepoznata lokacija") : "-"}
                </td>
                <td>
                  {a.kind === "event" ? (
                    <StatusBadge tone={eventStatusTone(a.event.status)}>
                      {EVENT_STATUS_LABEL[a.event.status]}
                    </StatusBadge>
                  ) : (
                    <StatusBadge tone={statusTone(a.session.status)}>
                      {STATUS_LABEL[a.session.status]}
                    </StatusBadge>
                  )}
                </td>
                <td className="schedule-row-actions">
                  <button
                    className="btn btn--secondary btn--sm"
                    type="button"
                    onClick={() => onSelect(a)}
                    data-cy={a.kind === "event" ? "event-detail-open" : "session-detail-open"}
                  >
                    Detalji
                  </button>
                  {a.kind === "session" ? (
                    <Link
                      className="btn btn--secondary btn--sm"
                      to={`/raspored/${a.id}/prisustvo`}
                      data-cy="session-attendance"
                    >
                      Prisustvo
                    </Link>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableContainer>
  );
}

/* ===================================================================== */
/* Novi termin, create form (data-cy hooks preserved from the prior UI)  */
/* ===================================================================== */

function NewSessionCard({
  groups,
  people,
  locations,
  groupSelectRef,
  onCreated,
}: {
  groups: Group[];
  people: PersonSummary[];
  locations: LocationSummary[];
  groupSelectRef: React.RefObject<HTMLSelectElement | null>;
  onCreated: () => void;
}) {
  const [groupId, setGroupId] = useState("");
  const [startsLocal, setStartsLocal] = useState("");
  const [duration, setDuration] = useState(60);
  const [title, setTitle] = useState("");
  const [trainerId, setTrainerId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [repeats, setRepeats] = useState(false);
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [weeks, setWeeks] = useState(12);
  const [conflict, setConflict] = useState<SessionSummary[] | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const group = groups.find((g) => g.id === groupId);
  /*
   * The group is the default source for trainer and location, so picking a
   * group fills both in. They stay editable: the defaults are a starting
   * value for THIS session, never a lock.
   */
  function chooseGroup(id: string) {
    setGroupId(id);
    const picked = groups.find((g) => g.id === id);
    setTrainerId(picked?.default_trainer_person_id ?? "");
    setLocationId(picked?.default_location_id ?? "");
  }

  function toggleWeekday(day: number) {
    setWeekdays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day].sort(),
    );
  }

  /** Local wall-clock parts of the datetime-local input, for the series rule. */
  function localParts(): { date: string; time: string } | null {
    const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(startsLocal);
    return match ? { date: match[1]!, time: match[2]! } : null;
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setConflict(null);
    setResult(null);
    try {
      if (repeats) {
        await createSeries();
      } else {
        await createOneOff();
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function createOneOff() {
    const startsAt = new Date(startsLocal).toISOString();
    const endsAt = new Date(new Date(startsLocal).getTime() + duration * 60000).toISOString();
    const draft = {
      group_id: groupId,
      starts_at: startsAt,
      ends_at: endsAt,
      title: title || null,
      trainer_person_id: trainerId || null,
      location_id: locationId || null,
    };
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
  }

  /*
   * A repeating slot is a rule plus the occurrences it has generated so far.
   * Creating the rule alone would leave the calendar empty, so the generate
   * call is part of the same action rather than a second thing to remember.
   */
  async function createSeries() {
    const parts = localParts();
    if (!parts) {
      setError(new Error("Unesite datum i vreme početka."));
      return;
    }
    const series = await api.post<SessionSeriesSummary>("/schedule/series", {
      group_id: groupId,
      title: title || group?.name || "Termin",
      weekdays,
      start_date: parts.date,
      local_time: `${parts.time}:00`,
      duration_minutes: duration,
      trainer_person_id: trainerId || null,
      location_id: locationId || null,
    });
    const generated = await api.post<SeriesGenerateResult>(
      `/schedule/series/${series.id}/generate`,
      { from_date: parts.date, weeks },
    );
    const skipped = generated.skipped_conflicts.length;
    setResult(
      `Kreirano ${generated.created_count} termina` +
        (skipped ? `, ${skipped} preskočeno zbog preklapanja.` : "."),
    );
    setStartsLocal("");
    setTitle("");
    onCreated();
  }

  const canSubmit = Boolean(groupId && startsLocal) && (!repeats || weekdays.length > 0);

  return (
    <section className="card" data-cy="new-session-card">
      <h2>Novi termin</h2>
      {error ? <SystemState error={error} /> : null}
      {conflict ? (
        <InlineNotice tone="warning">
          Termin se preklapa sa postojećim ({conflict.length}). Izmenite vreme i pokušajte ponovo.
        </InlineNotice>
      ) : null}
      {result ? <InlineNotice tone="info" data-cy="series-result">{result}</InlineNotice> : null}
      <form onSubmit={save}>
        <div className="field">
          <label htmlFor="s-group">Grupa</label>
          <select
            id="s-group"
            ref={groupSelectRef}
            value={groupId}
            onChange={(e) => chooseGroup(e.target.value)}
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
          <label htmlFor="s-trainer">Trener</label>
          <select
            id="s-trainer"
            value={trainerId}
            onChange={(e) => setTrainerId(e.target.value)}
            data-cy="session-trainer"
          >
            <option value="">Nije dodeljen</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
          {group?.default_trainer_person_id ? (
            <small className="field__hint">Preuzeto iz grupe; možete promeniti samo za ovaj termin.</small>
          ) : null}
        </div>
        <div className="field">
          <label htmlFor="s-location">Lokacija</label>
          <select
            id="s-location"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            data-cy="session-location"
          >
            <option value="">Nije određena</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} · {LOCATION_KIND_LABEL[l.kind]}
              </option>
            ))}
          </select>
          {group?.default_location_id ? (
            <small className="field__hint">Preuzeto iz grupe; možete promeniti samo za ovaj termin.</small>
          ) : null}
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

        <label className="checkfield">
          <input
            type="checkbox"
            checked={repeats}
            onChange={(e) => setRepeats(e.target.checked)}
            data-cy="session-repeats"
          />
          <span>Ponavlja se svake nedelje</span>
        </label>

        {repeats ? (
          <div className="schedule-repeat" data-cy="session-repeat-options">
            <fieldset className="schedule-weekdays">
              <legend>Dani u nedelji</legend>
              <div className="schedule-weekdays__row">
                {WEEKDAY_PICKER.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    className={cx(
                      "schedule-weekday",
                      weekdays.includes(d.value) && "is-active",
                    )}
                    aria-pressed={weekdays.includes(d.value)}
                    onClick={() => toggleWeekday(d.value)}
                    data-cy={`session-weekday-${d.value}`}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="field">
              <label htmlFor="s-weeks">Zakaži unapred (nedelja)</label>
              <input
                id="s-weeks"
                type="number"
                min={1}
                max={104}
                value={weeks}
                onChange={(e) => setWeeks(Number(e.target.value))}
                data-cy="session-weeks"
              />
            </div>
            <p className="schedule-repeat__hint">
              Termini se kreiraju za izabrane dane, počev od datuma iznad. Kasnije možete
              izmeniti samo jedan termin, ovaj i sve naredne, ili celu seriju.
            </p>
          </div>
        ) : null}

        <button
          className="btn btn--primary"
          type="submit"
          disabled={busy || !canSubmit}
          data-cy="session-save"
        >
          {repeats ? "Sačuvaj ponavljajuće termine" : "Sačuvaj termin"}
        </button>
      </form>
    </section>
  );
}

/* ===================================================================== */
/* Detail dialog: one for both kinds, branching only where they differ   */
/* ===================================================================== */

function ActivityDetailDialog({
  activity,
  groupsMap,
  people,
  peopleMap,
  locations,
  locationsMap,
  onClose,
  onChanged,
}: {
  activity: Activity | null;
  groupsMap: Map<string, Group>;
  people: PersonSummary[];
  peopleMap: Map<string, string>;
  locations: LocationSummary[];
  locationsMap: Map<string, LocationSummary>;
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
  const [editLocation, setEditLocation] = useState("");
  const [editReason, setEditReason] = useState<SessionChangeReasonCode>("OTHER");
  const [editScope, setEditScope] = useState<SessionEditScope>("SINGLE");

  const [cancelReason, setCancelReason] = useState<SessionCancellationReasonCode>("OTHER");
  const [cancelNote, setCancelNote] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (activity && !dialog.open) dialog.showModal();
    else if (!activity && dialog.open) dialog.close();
  }, [activity]);

  useEffect(() => {
    if (!activity) return;
    setMode("view");
    setError(null);
    setEditTime(
      `${String(activity.start.getHours()).padStart(2, "0")}:${String(activity.start.getMinutes()).padStart(2, "0")}`,
    );
    setEditDuration(
      Math.round((activity.end.getTime() - activity.start.getTime()) / 60000),
    );
    setEditTitle(activity.kind === "session" ? (activity.session.title ?? "") : "");
    setEditTrainer(activityPersonId(activity) ?? "");
    setEditLocation(activityLocationId(activity) ?? "");
    setEditReason("OTHER");
    setEditScope("SINGLE");
    setCancelReason("OTHER");
    setCancelNote("");
  }, [activity]);

  if (!activity) {
    return (
      <dialog ref={dialogRef} className="card session-dialog" onCancel={onClose} data-cy="session-detail" />
    );
  }

  const isEvent = activity.kind === "event";
  const session = activity.kind === "session" ? activity.session : null;
  const event = activity.kind === "event" ? activity.event : null;
  const group = session ? groupsMap.get(session.group_id) : undefined;
  const personId = activityPersonId(activity);
  const personName = personId
    ? (peopleMap.get(personId) ?? "Nepoznata osoba")
    : "Nije dodeljen";
  const locationId = activityLocationId(activity);
  const location = locationId ? locationsMap.get(locationId) : undefined;

  async function submitEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await api.patch<SessionSummary[]>(`/schedule/sessions/${session.id}`, {
        local_time: editTime,
        duration_minutes: editDuration,
        title: editTitle || null,
        trainer_person_id: editTrainer || null,
        location_id: editLocation || null,
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
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await api.post<SessionSummary>(`/schedule/sessions/${session.id}/cancel`, {
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
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await api.post<SessionSummary>(`/schedule/sessions/${session.id}/reactivate`);
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
      data-cy={isEvent ? "event-detail" : "session-detail"}
    >
      <div className="session-dialog__head">
        <div>
          <span className="eyebrow">
            {isEvent ? `Događaj · ${EVENT_TYPE_LABEL[event!.type]}` : "Termin"}
          </span>
          <h2>{activityTitle(activity, groupsMap)}</h2>
          <p className="session-dialog__meta">{activityWhen(activity, { long: true })}</p>
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
          {isEvent ? (
            <StatusBadge tone={eventStatusTone(event!.status)}>
              {EVENT_STATUS_LABEL[event!.status]}
            </StatusBadge>
          ) : (
            <StatusBadge tone={statusTone(session!.status)}>
              {STATUS_LABEL[session!.status]}
            </StatusBadge>
          )}
          <dl className="session-dialog__facts">
            {isEvent ? null : (
              <div>
                <dt>Grupa</dt>
                <dd>{group?.name ?? "-"}</dd>
              </div>
            )}
            <div>
              <dt>{isEvent ? "Odgovorna osoba" : "Trener"}</dt>
              <dd>{personName}</dd>
            </div>
            <div>
              <dt>Lokacija</dt>
              <dd>
                {location ? `${location.name} · ${LOCATION_KIND_LABEL[location.kind]}` : "-"}
                {event?.location_note ? (
                  <>
                    <br />
                    <span className="session-dialog__note">{event.location_note}</span>
                  </>
                ) : null}
              </dd>
            </div>
            {event?.description ? (
              <div>
                <dt>Opis</dt>
                <dd>{event.description}</dd>
              </div>
            ) : null}
            {session?.status === "CANCELLED" && session.cancellation_reason ? (
              <div>
                <dt>Razlog otkazivanja</dt>
                <dd>{CANCEL_REASON_LABEL[session.cancellation_reason]}</dd>
              </div>
            ) : null}
          </dl>
          <div className="session-dialog__actions">
            {isEvent ? (
              <Link className="btn btn--secondary" to="/dogadjaji" data-cy="event-open-page">
                Otvori Događaje
              </Link>
            ) : (
              <>
                <button
                  className="btn btn--secondary"
                  type="button"
                  onClick={() => setMode("edit")}
                  data-cy="session-edit-open"
                >
                  Izmeni
                </button>
                {session!.status === "SCHEDULED" ? (
                  <>
                    <Link
                      className="btn btn--secondary"
                      to={`/raspored/${session!.id}/prisustvo`}
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
                {session!.status === "CANCELLED" ? (
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
              </>
            )}
          </div>
        </>
      ) : null}

      {mode === "edit" && session ? (
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
          <div className="field">
            <label htmlFor="e-location">Lokacija</label>
            <select
              id="e-location"
              value={editLocation}
              onChange={(e) => setEditLocation(e.target.value)}
              data-cy="session-edit-location"
            >
              <option value="">Nije određena</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} · {LOCATION_KIND_LABEL[l.kind]}
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
                {(Object.keys(EDIT_SCOPE_LABEL) as SessionEditScope[]).map((scope) => (
                  <option key={scope} value={scope}>
                    {EDIT_SCOPE_LABEL[scope]}
                  </option>
                ))}
              </select>
              <small className="field__hint">
                Prošli termini se nikada ne menjaju, oni su evidencija onoga što se dogodilo.
              </small>
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

      {mode === "cancel" && session ? (
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
/* Small inline icons (stroke, currentColor, matches shell.tsx style)   */
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
/** The star that marks an event apart from a training slot on the grid. */
function EventGlyph(): ReactNode {
  return (
    <svg
      className="session-block__glyph"
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 3.5 14.6 9l5.9.8-4.3 4.1 1 5.8L12 17l-5.2 2.7 1-5.8L3.5 9.8 9.4 9z" />
    </svg>
  );
}
