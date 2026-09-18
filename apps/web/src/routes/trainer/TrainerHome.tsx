import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useSession } from "../../auth/session";
import type { Group, GroupMember, Page, SessionSummary } from "../../api/types";
import { BrandMark } from "../../components/shell";
import { Card, EmptyState, LoadingState, StatusBadge, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { formatTime, formatWeekdayDate } from "../../lib/format";
import "../home.css";

function todayRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
  const to = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0);
  return { from: from.toISOString(), to: to.toISOString() };
}

function dateLabel(): string {
  const s = formatWeekdayDate(new Date());
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function timeLabel(iso: string): string {
  return formatTime(iso);
}

/** Headcount per group, fetched only for the handful of groups on today's
 *  agenda. Best-effort: a failed fetch just leaves that group's count blank. */
function useGroupHeadcounts(groupIds: string[]) {
  const key = groupIds.slice().sort().join(",");
  const [counts, setCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    const ids = key ? key.split(",") : [];
    if (ids.length === 0) return;
    let cancelled = false;
    Promise.allSettled(ids.map((id) => api.get<GroupMember[]>(`/groups/${id}/members`))).then((results) => {
      if (cancelled) return;
      const next: Record<string, number> = {};
      results.forEach((r, i) => {
        const id = ids[i];
        if (id && r.status === "fulfilled") next[id] = r.value.length;
      });
      setCounts((prev) => ({ ...prev, ...next }));
    });
    return () => {
      cancelled = true;
    };
  }, [key]);

  return counts;
}

export function TrainerHome() {
  const { me, activeContext } = useSession();
  const orgName = activeContext?.school_name ?? "";
  const firstName = (me?.display_name ?? "").split(/\s+/)[0] ?? "";

  // Re-render every minute so "Za N min" stays fresh without a full reload.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(id);
  }, []);

  const range = useMemo(todayRange, []);
  const sessions = useAsync(
    () =>
      api.get<SessionSummary[]>(
        `/schedule/sessions?date_from=${encodeURIComponent(range.from)}&date_to=${encodeURIComponent(range.to)}`,
      ),
    [range.from, range.to],
  );
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);

  // Client-side scoping (#3 M8 gap): the schedule endpoint isn't trainer-scoped
  // yet, so only render sessions this trainer is actually assigned to , 
  // never show another trainer's roster or termini.
  const mine = useMemo(() => {
    if (!sessions.data || !me) return [];
    return sessions.data
      .filter((s) => s.status !== "CANCELLED" && s.trainer_person_id === me.person_id)
      .filter((s) => new Date(s.ends_at).getTime() >= now)
      .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());
  }, [sessions.data, me, now]);

  const next = mine[0];
  const later = mine.slice(1);

  const headcounts = useGroupHeadcounts(
    useMemo(() => [...new Set(mine.map((s) => s.group_id))], [mine]),
  );

  const groupName = (id: string) => groups.data?.items.find((g) => g.id === id)?.name ?? "-";
  const statusTone = (s: SessionSummary["status"]) =>
    s === "SCHEDULED" ? "success" : s === "COMPLETED" ? "info" : "error";

  const loading = sessions.loading || groups.loading;

  return (
    <div>
      <div className="trainer-topbar">
        <BrandMark />
        <span className="trainer-topbar__org">{orgName}</span>
        <span className="trainer-topbar__date">{dateLabel()}</span>
      </div>

      <h1 className="trainer-greeting">Dobar dan{firstName ? `, ${firstName}` : ""}.</h1>

      {loading ? <LoadingState /> : null}
      {sessions.error ? <SystemState error={sessions.error} /> : null}

      {!loading && !sessions.error && !next ? (
        <EmptyState>Nema zakazanih termina danas.</EmptyState>
      ) : null}

      {next ? (
        <div className="trainer-hero" data-cy="trainer-hero">
          <div className="trainer-hero__eyebrow">Sledeći termin</div>
          <div className="trainer-hero__time">
            {timeLabel(next.starts_at)}
            <span className="trainer-hero__countdown">
              {new Date(next.starts_at).getTime() <= now
                ? "U toku"
                : `Za ${Math.round((new Date(next.starts_at).getTime() - now) / 60000)} min`}
            </span>
          </div>
          <p className="trainer-hero__group">{groupName(next.group_id)}</p>
          {/* Sessions have no room assignment in the API yet, degrade honestly. */}
          <p className="trainer-hero__meta">
            {headcounts[next.group_id] != null ? `${headcounts[next.group_id]} učenika · ` : ""}
            do {timeLabel(next.ends_at)}
          </p>
          <Link
            className="btn trainer-hero__cta"
            to={`/raspored/${next.id}/prisustvo`}
            data-cy="trainer-open-attendance"
          >
            Otvori prisustvo
          </Link>
        </div>
      ) : null}

      {later.length > 0 ? (
        <Card title="Kasnije danas">
          <ul className="trainer-later__list" data-cy="trainer-later-list">
            {later.map((s) => (
              <li key={s.id} className="trainer-later__row" data-cy="trainer-later-row">
                <span className="trainer-later__time">{timeLabel(s.starts_at)}</span>
                <span className="trainer-later__body">
                  <span className="trainer-later__group">{groupName(s.group_id)}</span>
                  <span className="trainer-later__meta">
                    {headcounts[s.group_id] != null ? `${headcounts[s.group_id]} učenika · ` : ""}
                    do {timeLabel(s.ends_at)}
                  </span>
                </span>
                <StatusBadge tone={statusTone(s.status)}>{s.status}</StatusBadge>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
