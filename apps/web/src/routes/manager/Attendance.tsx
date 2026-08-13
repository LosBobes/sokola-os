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
  const start = new Date(session.starts_at);
  const end = new Date(session.ends_at);
  const date = start.toLocaleDateString("sr-Latn", { day: "numeric", month: "long" });
  const startTime = start.toLocaleTimeString("sr-Latn", { hour: "2-digit", minute: "2-digit" });
  const endTime = end.toLocaleTimeString("sr-Latn", { hour: "2-digit", minute: "2-digit" });
  return `${date} · ${startTime}–${endTime}`;
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
 * Local per-row status. The sheet's own default is PRESENT for anyone
 * without a recorded exception, which is indistinguishable from "the
 * trainer never looked at this person". To force an explicit check on
 * every roster member, PRESENT-from-server folds into UNSET on load;
 * an already-recorded exception (EXCUSED/ABSENT) still shows as such, so
 * reopening a session to correct it never silently reverts to present.
 * LATE isn't part of this flow (Prisutan / Odsutan + Opravdano-Neopravdano
 * only), legacy LATE entries show as an unexcused absence until re-marked.
 */
type LocalStatus = "UNSET" | "PRESENT" | "EXCUSED" | "ABSENT";

function initialLocalStatus(entry: AttendanceEntry): LocalStatus {
  if (entry.status === "EXCUSED") return "EXCUSED";
  if (entry.status === "ABSENT" || entry.status === "LATE") return "ABSENT";
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

  const counts = useMemo(() => {
    const tally = { present: 0, excused: 0, absent: 0, unset: 0 };
    for (const e of sheet.entries) {
      switch (statuses[e.person_id] ?? "UNSET") {
        case "PRESENT":
          tally.present += 1;
          break;
        case "EXCUSED":
          tally.excused += 1;
          break;
        case "ABSENT":
          tally.absent += 1;
          break;
        default:
          tally.unset += 1;
      }
    }
    return tally;
  }, [sheet.entries, statuses]);

  const dirty = touched.size > 0;

  async function save() {
    if (busyRef.current) return; // no duplicate submit
    busyRef.current = true;
    setBusy(true);
    setError(null);
    const exceptions = sheet.entries.flatMap((e) => {
      const status = statuses[e.person_id] ?? "UNSET";
      if (status === "UNSET" || status === "PRESENT") return []; // matches the PRESENT default, omit
      return [
        {
          person_id: e.person_id,
          status,
          override_reason: status === "EXCUSED" ? ("EXCUSED_ABSENCE" as const) : null,
        },
      ];
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
          Sačuvano prisustvo: prisutnih {saved.present}, odsutnih {saved.absent}, opravdanih {saved.excused}
          {saved.late ? `, kasnili ${saved.late}` : ""}.
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
              <CounterPill label="Prisutan" value={counts.present} tone="success" />
              <CounterPill label="Opravdano" value={counts.excused} tone="info" />
              <CounterPill label="Neopravdano" value={counts.absent} tone="error" />
              <CounterPill label="Nije evid." value={counts.unset} tone="neutral" />
            </ul>
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
  const showReason = status === "EXCUSED" || status === "ABSENT";
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
          className={cx("attendance-btn attendance-btn--absent", showReason && "is-active")}
          aria-pressed={showReason}
          onClick={() => onMark(entry.person_id, "ABSENT")}
          data-cy={`attendance-mark-absent-${entry.person_id}`}
        >
          Odsutan
        </button>
      </div>

      {showReason ? (
        <div className="attendance-row__reason" role="group" aria-label={`Razlog odsustva za ${entry.display_name}`}>
          <button
            type="button"
            className={cx("attendance-reason", status === "EXCUSED" && "is-active")}
            aria-pressed={status === "EXCUSED"}
            onClick={() => onMark(entry.person_id, "EXCUSED")}
            data-cy={`attendance-reason-excused-${entry.person_id}`}
          >
            Opravdano
          </button>
          <button
            type="button"
            className={cx("attendance-reason", status === "ABSENT" && "is-active")}
            aria-pressed={status === "ABSENT"}
            onClick={() => onMark(entry.person_id, "ABSENT")}
            data-cy={`attendance-reason-unexcused-${entry.person_id}`}
          >
            Neopravdano
          </button>
        </div>
      ) : status === "UNSET" ? (
        <p className="attendance-row__hint">Nije evidentirano</p>
      ) : null}
    </li>
  );
}
