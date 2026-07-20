import { useMemo, useState, type FormEvent } from "react";
import { api, newIdempotencyKey } from "../../api/client";
import type { Announcement, AnnouncementPreview, Group, Page } from "../../api/types";
import { PageHeader } from "../../components/shell";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  FilterBar,
  InlineNotice,
  SegmentedControl,
  SplitPane,
  SplitPaneRow,
  StatusBadge,
  SystemState,
} from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";

/*
 * M10 · Komunikacija — manager compose/list screen (#30).
 *
 * Backend today (openapi/sokola-p0-v1.openapi.json) only exposes two
 * communications endpoints:
 *   POST /communications/announcements/preview  → recipient snapshot + count
 *   POST /communications/announcements          → publish (needs snapshot_hash)
 *
 * There is no GET /communications/announcements (list), no draft-save
 * endpoint, and AnnouncementResponse carries no per-recipient delivery
 * status — #15 (communications backend enhancements) has not landed on
 * main yet. Consequences, called out again in the PR description:
 *   - the "Poslato" list below is session-local: it fills up with what
 *     THIS browser tab has published since it was opened, not a durable
 *     server-side list. A page refresh loses it. Once #15 ships a list
 *     endpoint this should load from the server instead.
 *   - "Sačuvaj nacrt" is a disabled stub — there is nowhere to persist a
 *     draft server-side yet, so only one in-progress compose is tracked,
 *     client-side, at a time.
 *   - no delivery/read status per recipient is shown (no field exists to
 *     show — if/when #15 adds one, surface it on SentDetail below).
 *   - GET /communications/inbox (parent-facing in-app inbox) is a separate
 *     screen (#34) and is intentionally not built here.
 */

const ALL_AUDIENCE = "ALL";

interface SentAnnouncement extends Announcement {
  body: string;
  audienceLabel: string;
  publishedAt: number;
}

type Tab = "nacrti" | "poslato";

function resolveAudienceLabel(sel: string, groups: Group[]): string {
  if (sel === ALL_AUDIENCE) return "Cela škola";
  const g = groups.find((item) => item.id === sel);
  return g ? `Grupa: ${g.name}` : "Ciljna grupa nije izabrana";
}

function formatWhen(ms: number): string {
  return new Date(ms).toLocaleString("sr-Latn", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function CommunicationsPage() {
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const groupItems = useMemo(() => groups.data?.items ?? [], [groups.data]);

  const [tab, setTab] = useState<Tab>("nacrti");
  const [composing, setComposing] = useState(false);
  const [selectedSentId, setSelectedSentId] = useState<string | null>(null);
  const [sent, setSent] = useState<SentAnnouncement[]>([]);
  const [search, setSearch] = useState("");

  const [audience, setAudience] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<AnnouncementPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [justPublished, setJustPublished] = useState<SentAnnouncement | null>(null);

  const selectedSent = sent.find((s) => s.id === selectedSentId) ?? null;

  function openCompose() {
    setComposing(true);
    setSelectedSentId(null);
    setTab("nacrti");
    setAudience("");
    setTitle("");
    setBody("");
    setPreview(null);
    setError(null);
    setJustPublished(null);
  }

  function cancelCompose() {
    setComposing(false);
    setPreview(null);
    setError(null);
  }

  function draftPayload() {
    return {
      title,
      body,
      target_type: (audience === ALL_AUDIENCE ? "ORGANIZATION" : "GROUP") as "ORGANIZATION" | "GROUP",
      target_group_id: audience === ALL_AUDIENCE ? null : audience,
    };
  }

  async function doPreview(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setPreview(await api.post<AnnouncementPreview>("/communications/announcements/preview", draftPayload()));
    } catch (err) {
      setError(err);
    }
  }

  async function publish() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<Announcement>(
        "/communications/announcements",
        { ...draftPayload(), snapshot_hash: preview.snapshot_hash },
        newIdempotencyKey(),
      );
      const record: SentAnnouncement = {
        ...result,
        body,
        audienceLabel: resolveAudienceLabel(audience, groupItems),
        publishedAt: Date.now(),
      };
      setSent((prev) => [record, ...prev]);
      setJustPublished(record);
      setPreview(null);
      setComposing(false);
      setTab("poslato");
      setSelectedSentId(record.id);
    } catch (err) {
      setError(err); // 409 SNAPSHOT_STALE → conflict guidance via SystemState
    } finally {
      setBusy(false);
    }
  }

  const filteredSent = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sent;
    return sent.filter(
      (s) => s.title.toLowerCase().includes(q) || s.audienceLabel.toLowerCase().includes(q),
    );
  }, [sent, search]);

  return (
    <div>
      <PageHeader
        title="Komunikacija"
        action={
          <Button onClick={openCompose} data-cy="ann-new">
            Novo obaveštenje
          </Button>
        }
      />
      <p style={{ color: "var(--text-secondary)", marginTop: 0, marginBottom: "var(--space-4)" }}>
        Jasna obaveštenja roditeljima i trenerima, bez razgovora u aplikaciji.
      </p>

      {justPublished ? (
        <InlineNotice tone="info">
          Poruka „{justPublished.title}“ je objavljena za {justPublished.recipient_count} primalaca.
        </InlineNotice>
      ) : null}

      <FilterBar>
        <SegmentedControl
          ariaLabel="Prikaz obaveštenja"
          value={tab}
          onChange={(v) => {
            setTab(v);
            setSelectedSentId(null);
          }}
          options={[
            { value: "nacrti", label: `Nacrti · ${composing ? 1 : 0}` },
            { value: "poslato", label: `Poslato · ${sent.length}` },
          ]}
        />
        <div className="field" style={{ margin: "0 0 0 auto", minWidth: 220 }}>
          <input
            type="search"
            placeholder="Pronađi obaveštenje"
            aria-label="Pronađi obaveštenje"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-cy="ann-search"
          />
        </div>
      </FilterBar>

      {groups.error ? <SystemState error={groups.error} /> : null}

      <SplitPane
        list={
          tab === "nacrti" ? (
            <div>
              <div style={{ padding: "var(--space-3) var(--space-4) 0" }}>
                <InlineNotice tone="info">
                  Nacrti se ne čuvaju na serveru — aktivni nacrt je prikazan dok ga ne objavite ili odustanete.
                </InlineNotice>
              </div>
              {composing ? (
                <SplitPaneRow active onClick={() => setComposing(true)}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
                    <strong>{title || "Novi nacrt"}</strong>
                    <StatusBadge tone="warning">Nacrt</StatusBadge>
                  </div>
                  <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginTop: 4 }}>
                    {audience ? resolveAudienceLabel(audience, groupItems) : "Ciljna grupa nije izabrana"}
                  </div>
                </SplitPaneRow>
              ) : (
                <div style={{ padding: "var(--space-4)" }}>
                  <EmptyState>Nema aktivnog nacrta. Kliknite na „Novo obaveštenje“ da započnete.</EmptyState>
                </div>
              )}
            </div>
          ) : filteredSent.length === 0 ? (
            <div style={{ padding: "var(--space-4)" }}>
              <EmptyState>
                {sent.length === 0
                  ? "Još nema poslatih obaveštenja u ovoj sesiji."
                  : "Nema obaveštenja koja odgovaraju pretrazi."}
              </EmptyState>
            </div>
          ) : (
            <div>
              {filteredSent.map((s) => (
                <SplitPaneRow
                  key={s.id}
                  active={s.id === selectedSentId}
                  onClick={() => {
                    setComposing(false);
                    setSelectedSentId(s.id);
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
                    <strong>{s.title}</strong>
                    <StatusBadge tone="success">Poslato</StatusBadge>
                  </div>
                  <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginTop: 4 }}>
                    {s.audienceLabel} · {s.recipient_count}{" "}
                    {s.recipient_count === 1 ? "primalac" : "primalaca"} · {formatWhen(s.publishedAt)}
                  </div>
                </SplitPaneRow>
              ))}
            </div>
          )
        }
        detail={
          composing ? (
            <ComposeDetail
              groups={groupItems}
              audience={audience}
              onAudienceChange={setAudience}
              title={title}
              onTitleChange={setTitle}
              body={body}
              onBodyChange={setBody}
              error={error}
              onPreview={doPreview}
              onCancel={cancelCompose}
            />
          ) : selectedSent ? (
            <SentDetail item={selectedSent} />
          ) : (
            <EmptyState>Izaberite obaveštenje sa liste ili kliknite „Novo obaveštenje“.</EmptyState>
          )
        }
      />

      <ConfirmDialog
        open={preview !== null}
        title="Objavi obaveštenje"
        confirmLabel="Objavi"
        busy={busy}
        onCancel={() => setPreview(null)}
        onConfirm={() => void publish()}
      >
        <p data-cy="ann-preview-summary">
          Poruka „{title}“ će biti poslata za <strong>{preview?.recipient_count ?? 0}</strong>{" "}
          {(preview?.recipient_count ?? 0) === 1 ? "primaoca" : "primalaca"} ({resolveAudienceLabel(audience, groupItems)}).
        </p>
        <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
          Posle objave sadržaj se ne menja.
        </p>
      </ConfirmDialog>
    </div>
  );
}

function ComposeDetail({
  groups,
  audience,
  onAudienceChange,
  title,
  onTitleChange,
  body,
  onBodyChange,
  error,
  onPreview,
  onCancel,
}: {
  groups: Group[];
  audience: string;
  onAudienceChange: (v: string) => void;
  title: string;
  onTitleChange: (v: string) => void;
  body: string;
  onBodyChange: (v: string) => void;
  error: unknown;
  onPreview: (e: FormEvent) => void;
  onCancel: () => void;
}) {
  return (
    <div data-cy="ann-compose">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-3)" }}>
        <div>
          <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-secondary)" }}>
            NACRT OBAVEŠTENJA
          </span>
          <h2 style={{ margin: "4px 0 0" }}>{title || "Novo obaveštenje"}</h2>
        </div>
        <StatusBadge tone="warning">Nacrt</StatusBadge>
      </div>

      {error ? (
        <div style={{ marginTop: "var(--space-3)" }}>
          <SystemState error={error} />
        </div>
      ) : null}

      <form onSubmit={onPreview} style={{ marginTop: "var(--space-4)" }}>
        <div className="field">
          <label htmlFor="ann-group">Ciljna grupa</label>
          <select
            id="ann-group"
            value={audience}
            onChange={(e) => onAudienceChange(e.target.value)}
            required
            data-cy="ann-group"
          >
            <option value="">Izaberi ciljnu grupu…</option>
            <option value={ALL_AUDIENCE}>Cela škola (svi roditelji i treneri)</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="ann-title">Naslov</label>
          <input
            id="ann-title"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            required
            data-cy="ann-title"
          />
        </div>
        <div className="field">
          <label htmlFor="ann-body">Poruka</label>
          <textarea
            id="ann-body"
            value={body}
            onChange={(e) => onBodyChange(e.target.value)}
            required
            rows={6}
            data-cy="ann-body"
          />
        </div>

        <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", marginTop: "var(--space-4)" }}>
          <Button
            type="button"
            variant="secondary"
            disabled
            title="Uskoro — čuvanje nacrta na serveru dolazi sa #15"
          >
            Sačuvaj nacrt
          </Button>
          <Button type="submit" data-cy="ann-preview">
            Pregledaj primaoce
          </Button>
          <Button type="button" variant="secondary" onClick={onCancel} data-cy="ann-compose-cancel">
            Odustani
          </Button>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", marginTop: "var(--space-2)" }}>
          Posle objave sadržaj se ne menja.
        </p>
      </form>
    </div>
  );
}

function SentDetail({ item }: { item: SentAnnouncement }) {
  return (
    <div data-cy="ann-sent-detail">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-3)" }}>
        <div>
          <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-secondary)" }}>
            OBJAVLJENO OBAVEŠTENJE
          </span>
          <h2 style={{ margin: "4px 0 0" }}>{item.title}</h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
            {item.audienceLabel} · {formatWhen(item.publishedAt)}
          </p>
        </div>
        <StatusBadge tone="success">Poslato</StatusBadge>
      </div>

      <p style={{ marginTop: "var(--space-4)", whiteSpace: "pre-wrap" }}>{item.body}</p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "160px 1fr",
          rowGap: "var(--space-2)",
          columnGap: "var(--space-3)",
          marginTop: "var(--space-4)",
        }}
      >
        <span style={{ color: "var(--text-secondary)", fontWeight: 600, fontSize: "var(--text-sm)" }}>Primalaca</span>
        <span>{item.recipient_count}</span>
      </div>

      <div style={{ marginTop: "var(--space-4)" }}>
        <InlineNotice tone="info">
          Status isporuke po primaocu (dostavljeno/pročitano) još nije dostupan — očekuje se sa #15.
        </InlineNotice>
      </div>
    </div>
  );
}
