import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type {
  AttendanceEntry,
  AttendanceSheet,
  Group,
  Page,
  SaveAttendanceResponse,
  SessionSummary,
} from "../../api/types";
import { PageHeader } from "../../components/shell";
import { Button, EmptyState, InlineNotice, LoadingState, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { formatDate, formatTime } from "../../lib/format";
import "./Attendance.css";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// How far past/ahead of "now" we search when resolving the session's group
// name and time window for the header. There is no single "get session"
// endpoint, so this mirrors SchedulePage's list+match approach.
const META_RANGE_DAYS = 400;

interface SessionMeta {
  session: SessionSummary | null;
  group: Group | null;
}

function useSessionMeta(sessionId: string | undefined) {
  return useAsync<SessionMeta>(async () => {
    if (!sessionId) return { session: null, group: null };
    try {
      const from = new Date(Date.now() - META_RANGE_DAYS * 86400000).toISOString();
      const to = new Date(Date.now() + META_RANGE_DAYS * 86400000).toISOString();
      const [sessions, groups] = await Promise.all([
        api.get<SessionSummary[]>(
          `/schedule/sessions?date_from=${encodeURIComponent(from)}&date_to=${encodeURIComponent(to)}`,
        ),
        api.get<Page<Group>>("/groups"),
      ]);
      const session = sessions.find((s) => s.id === sessionId) ?? null;
      const group = session ? (groups.items.find((g) => g.id === session.group_id) ?? null) : null;
      return { session, group };
    } catch {
      // Header context (group/time) is supplementary, never block the
      // core attendance-taking flow on it.
      return { session: null, group: null };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);
}

function formatSessionWindow(session: SessionSummary): string {
  return `${formatDate(session.starts_at)} · ${formatTime(session.starts_at)}–${formatTime(session.ends_at)}`;
}

export function AttendancePage() {
  const { sessionId } = useParams();
  const sheet = useAsync(
    () => api.get<AttendanceSheet>(`/schedule/sessions/${sessionId}/attendance`),
    [sessionId],
  );
  const meta = useSessionMeta(sessionId);

  if (sheet.loading) return <LoadingState label="Učitavanje prisustva…" />;
  if (sheet.error) return <SystemState error={sheet.error} />;
  if (!sheet.data) return null;

  return (
    <AttendanceForm
      sheet={sheet.data}
      onReload={sheet.reload}
      sessionId={sessionId!}
      session={meta.data?.session ?? null}
      group={meta.data?.group ?? null}
    />
  );
}

/*
 * Local per-row status.
 *
 * Attendance answers ONE question: was this person here? So the only marks are
 * Prisutan and Odsutan. Whether an absence was excused is a different question,
 * asked and answered elsewhere; mixing it in here gave one fact two
 * vocabularies , per-person buttons offering two states while the summary
 * counted four, and a percentage that agreed with neither.
 *
 * UNSET is not a third answer, it is the absence of one. The sheet's own
 * default is PRESENT for anyone without a recorded exception, which is
 * indistinguishable from "the trainer never looked at this person", so
 * PRESENT-from-server folds into UNSET on load to force an explicit mark.
 * Historical EXCUSED rows were absences and LATE rows were presences; they are
 * shown as such until someone re-marks them.
 */
type LocalStatus = "UNSET" | "PRESENT" | "ABSENT";

function initialLocalStatus(entry: AttendanceEntry): LocalStatus {
  if (entry.status === "EXCUSED" || entry.status === "ABSENT") return "ABSENT";
  if (entry.status === "LATE") return "PRESENT";
  return "UNSET";
}

function buildStatusMap(entries: AttendanceEntry[]): Record<string, LocalStatus> {
  return Object.fromEntries(entries.map((e) => [e.person_id, initialLocalStatus(e)]));
}

function AttendanceForm({
  sheet,
  onReload,
  sessionId,
  session,
  group,
}: {
  sheet: AttendanceSheet;
  onReload: () => void;
  sessionId: string;
  session: SessionSummary | null;
  group: Group | null;
}) {
  const [statuses, setStatuses] = useState<Record<string, LocalStatus>>(() => buildStatusMap(sheet.entries));
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [version, setVersion] = useState(sheet.attendance_version);
  const [saved, setSaved] = useState<SaveAttendanceResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  useEffect(() => {
    setStatuses(buildStatusMap(sheet.entries));
    setTouched(new Set());
    setVersion(sheet.attendance_version);
    setSaved(null);
    setError(null);
  }, [sheet]);

  function mark(personId: string, status: LocalStatus) {
    setStatuses((s) => ({ ...s, [personId]: status }));
    setTouched((t) => new Set(t).add(personId));
    setSaved(null);
  }

  function markAllPresent() {
    setStatuses(Object.fromEntries(sheet.entries.map((e) => [e.person_id, "PRESENT" as LocalStatus])));
    setTouched(new Set(sheet.entries.map((e) => e.person_id)));
    setSaved(null);
  }

  /*
   * Present / absent / not-yet-recorded, plus the attendance percentage.
   *
   * The percentage is Prisutan / (Prisutan + Odsutan), i.e. over what was
   * actually recorded and never over the whole roster. Counting unmarked people
   * as absent would report a sheet nobody has opened as 0% attendance, which
   * reads as "nobody came" rather than "nobody has taken attendance yet".
   */
  const counts = useMemo(() => {
    const tally = { present: 0, absent: 0, unset: 0 };
    for (const e of sheet.entries) {
      switch (statuses[e.person_id] ?? "UNSET") {
        case "PRESENT":
          tally.present += 1;
          break;
        case "ABSENT":
          tally.absent += 1;
          break;
        default:
          tally.unset += 1;
      }
    }
    const recorded = tally.present + tally.absent;
    return {
      ...tally,
      recorded,
      pct: recorded > 0 ? Math.round((tally.present / recorded) * 100) : null,
    };
  }, [sheet.entries, statuses]);

  const dirty = touched.size > 0;

  async function save() {
    if (busyRef.current) return; // no duplicate submit
    busyRef.current = true;
    setBusy(true);
    setError(null);
    // The API's roster default is PRESENT, so only absences travel. An UNSET
    // row is left at that default rather than invented as an absence: the sheet
    // records what was observed, and "not recorded" is not an observation.
    const exceptions = sheet.entries.flatMap((e) => {
      if ((statuses[e.person_id] ?? "UNSET") !== "ABSENT") return [];
      return [{ person_id: e.person_id, status: "ABSENT" as const, override_reason: null }];
    });
    try {
      const result = await api.put<SaveAttendanceResponse>(`/schedule/sessions/${sessionId}/attendance`, {
        attendance_version: version,
        exceptions,
      });
      setSaved(result);
      setVersion(result.attendance_version);
      setTouched(new Set());
    } catch (err) {
      setError(err); // manual_recovery/conflict/etc., never auto-retried
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  }

  const isConflict = error instanceof ApiError && error.canonical === "conflict";

  return (
    <div>
      <PageHeader eyebrow="Evidencija" title="Prisustvo" />

      <header className="attendance-header" data-cy="attendance-header">
        <div>
          <h2 className="attendance-header__title">{group?.name ?? "Termin"}</h2>
          <p className="attendance-header__sub">
            {session ? formatSessionWindow(session) : null}
            {session ? " · " : ""}
            {sheet.entries.length} polaznika
          </p>
        </div>
        {dirty ? (
          <span className="badge badge--warning attendance-header__dirty" data-cy="attendance-dirty">
            Nije sačuvano
          </span>
        ) : null}
      </header>

      {saved ? (
        <InlineNotice tone="info" data-cy="attendance-saved">
          Sačuvano prisustvo: prisutnih {saved.present}, odsutnih {saved.absent}.
        </InlineNotice>
      ) : null}

      {error ? (
        <div className="attendance-error" data-cy="attendance-error">
          <SystemState error={error} />
          {isConflict ? (
            <Button variant="secondary" onClick={onReload} data-cy="attendance-reload">
              Osveži spisak
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => void save()} disabled={busy} data-cy="attendance-retry">
              Pokušaj ponovo
            </Button>
          )}
        </div>
      ) : null}

      {sheet.entries.length === 0 ? (
        <EmptyState>U ovoj grupi trenutno nema članova.</EmptyState>
      ) : (
        <>
          <div className="attendance-toolbar">
            <Button variant="secondary" onClick={markAllPresent} data-cy="attendance-mark-all-present">
              Označi sve kao prisutne
            </Button>
            <ul className="attendance-counters" data-cy="attendance-counters">
              <CounterPill label="Prisutnih" value={counts.present} tone="success" />
              <CounterPill label="Odsutnih" value={counts.absent} tone="error" />
              <CounterPill label="Neevidentiranih" value={counts.unset} tone="neutral" />
            </ul>
            <p className="attendance-rate" data-cy="attendance-rate">
              {counts.pct !== null ? (
                <>
                  <strong>{counts.pct}%</strong> prisutnih, od {counts.recorded} evidentiranih
                </>
              ) : (
                "Prisustvo još nije evidentirano."
              )}
            </p>
          </div>

          <ul className="attendance-list" data-cy="attendance-table">
            {sheet.entries.map((e) => (
              <AttendanceRow key={e.person_id} entry={e} status={statuses[e.person_id] ?? "UNSET"} onMark={mark} />
            ))}
          </ul>
        </>
      )}

      <div className="attendance-footer">
        <Button
          className="attendance-save-btn"
          onClick={() => void save()}
          disabled={busy || sheet.entries.length === 0}
          data-cy="attendance-save"
        >
          {busy ? "Čuvanje…" : "Sačuvaj prisustvo"}
        </Button>
      </div>
    </div>
  );
}

function CounterPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "info" | "error" | "neutral";
}) {
  return (
    <li className="attendance-counter" data-cy="attendance-counter">
      <span className={`badge badge--${tone}`}>{value}</span>
      <span className="attendance-counter__label">{label}</span>
    </li>
  );
}

function AttendanceRow({
  entry,
  status,
  onMark,
}: {
  entry: AttendanceEntry;
  status: LocalStatus;
  onMark: (personId: string, status: LocalStatus) => void;
}) {
  return (
    <li className="attendance-row" data-cy="attendance-row">
      <div className="attendance-row__name">{entry.display_name}</div>
      <div className="attendance-row__controls" role="group" aria-label={`Prisustvo za ${entry.display_name}`}>
        <button
          type="button"
          className={cx("attendance-btn attendance-btn--present", status === "PRESENT" && "is-active")}
          aria-pressed={status === "PRESENT"}
          onClick={() => onMark(entry.person_id, "PRESENT")}
          data-cy={`attendance-mark-present-${entry.person_id}`}
        >
          Prisutan
        </button>
        <button
          type="button"
          className={cx("attendance-btn attendance-btn--absent", status === "ABSENT" && "is-active")}
          aria-pressed={status === "ABSENT"}
          onClick={() => onMark(entry.person_id, "ABSENT")}
          data-cy={`attendance-mark-absent-${entry.person_id}`}
        >
          Odsutan
        </button>
      </div>

      {status === "UNSET" ? <p className="attendance-row__hint">Nije evidentirano</p> : null}
    </li>
  );
}
