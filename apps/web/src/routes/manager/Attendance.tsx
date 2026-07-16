import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { AttendanceSheet, AttendanceStatus, SaveAttendanceResponse } from "../../api/types";
import { PageHeader } from "../../components/shell";
import { InlineNotice, LoadingState, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";

const STATUSES: AttendanceStatus[] = ["PRESENT", "ABSENT", "EXCUSED", "LATE"];

export function AttendancePage() {
  const { sessionId } = useParams();
  const sheet = useAsync(
    () => api.get<AttendanceSheet>(`/schedule/sessions/${sessionId}/attendance`),
    [sessionId],
  );

  if (sheet.loading) return <LoadingState />;
  if (sheet.error) return <SystemState error={sheet.error} />;
  if (!sheet.data) return null;

  return <AttendanceForm sheet={sheet.data} onReload={sheet.reload} sessionId={sessionId!} />;
}

function AttendanceForm({
  sheet,
  onReload,
  sessionId,
}: {
  sheet: AttendanceSheet;
  onReload: () => void;
  sessionId: string;
}) {
  const [statuses, setStatuses] = useState<Record<string, AttendanceStatus>>({});
  const [saved, setSaved] = useState<SaveAttendanceResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setStatuses(Object.fromEntries(sheet.entries.map((e) => [e.person_id, e.status])));
  }, [sheet]);

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(null);
    // Send only the people who differ from the PRESENT default.
    const exceptions = sheet.entries
      .filter((e) => (statuses[e.person_id] ?? "PRESENT") !== "PRESENT")
      .map((e) => ({ person_id: e.person_id, status: statuses[e.person_id] }));
    try {
      const result = await api.put<SaveAttendanceResponse>(
        `/schedule/sessions/${sessionId}/attendance`,
        { attendance_version: sheet.attendance_version, exceptions },
      );
      setSaved(result);
    } catch (err) {
      setError(err); // 409 → SystemState renders the conflict/reload guidance
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Prisustvo" />
      {error ? (
        <div>
          <SystemState error={error} />
          <button className="btn btn--secondary" onClick={onReload} data-cy="attendance-reload">
            Osveži spisak
          </button>
        </div>
      ) : null}
      {saved ? (
        <InlineNotice tone="info">
          Sačuvano prisustvo: prisutnih {saved.present}, odsutnih {saved.absent}, opravdanih{" "}
          {saved.excused}, kasnili {saved.late}.
        </InlineNotice>
      ) : null}
      <table className="data" data-cy="attendance-table">
        <thead>
          <tr>
            <th>Osoba</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {sheet.entries.map((e) => (
            <tr key={e.person_id} data-cy="attendance-row">
              <td>{e.display_name}</td>
              <td>
                <select
                  value={statuses[e.person_id] ?? "PRESENT"}
                  onChange={(ev) =>
                    setStatuses((s) => ({ ...s, [e.person_id]: ev.target.value as AttendanceStatus }))
                  }
                  data-cy={`attendance-status-${e.person_id}`}
                >
                  {STATUSES.map((st) => (
                    <option key={st} value={st}>
                      {st}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        className="btn btn--primary"
        onClick={save}
        disabled={busy}
        style={{ marginTop: "var(--space-4)" }}
        data-cy="attendance-save"
      >
        Sačuvaj prisustvo
      </button>
    </div>
  );
}
