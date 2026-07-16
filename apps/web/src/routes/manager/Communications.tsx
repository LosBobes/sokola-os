import { useState } from "react";
import { api, newIdempotencyKey } from "../../api/client";
import type { Announcement, AnnouncementPreview, Group, Page } from "../../api/types";
import { PageHeader } from "../../components/shell";
import { ConfirmDialog, InlineNotice, SystemState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";

export function CommunicationsPage() {
  const groups = useAsync(() => api.get<Page<Group>>("/groups"), []);
  const [groupId, setGroupId] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<AnnouncementPreview | null>(null);
  const [published, setPublished] = useState<Announcement | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function draft() {
    return { title, body: text, target_type: "GROUP" as const, target_group_id: groupId };
  }

  async function doPreview(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPublished(null);
    try {
      setPreview(await api.post<AnnouncementPreview>("/communications/announcements/preview", draft()));
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
        { ...draft(), snapshot_hash: preview.snapshot_hash },
        newIdempotencyKey(),
      );
      setPublished(result);
      setPreview(null);
      setTitle("");
      setText("");
    } catch (err) {
      setError(err); // 409 SNAPSHOT_STALE → conflict guidance
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Komunikacija" />
      <section className="card">
        <h2>Nova poruka</h2>
        {error ? <SystemState error={error} /> : null}
        {published ? (
          <InlineNotice tone="info">
            Poruka „{published.title}“ je objavljena za {published.recipient_count} primalaca.
          </InlineNotice>
        ) : null}
        <form onSubmit={doPreview}>
          <div className="field">
            <label htmlFor="a-group">Grupa (primaoci)</label>
            <select id="a-group" value={groupId} onChange={(e) => setGroupId(e.target.value)} required data-cy="ann-group">
              <option value="">Izaberi grupu…</option>
              {(groups.data?.items ?? []).map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="a-title">Naslov</label>
            <input id="a-title" value={title} onChange={(e) => setTitle(e.target.value)} required data-cy="ann-title" />
          </div>
          <div className="field">
            <label htmlFor="a-body">Tekst</label>
            <textarea id="a-body" value={text} onChange={(e) => setText(e.target.value)} required rows={4} data-cy="ann-body" />
          </div>
          <button className="btn btn--secondary" type="submit" data-cy="ann-preview">
            Pregledaj primaoce
          </button>
        </form>
      </section>

      <ConfirmDialog
        open={preview !== null}
        title="Objavi poruku"
        confirmLabel="Objavi"
        busy={busy}
        onCancel={() => setPreview(null)}
        onConfirm={() => void publish()}
      >
        <p data-cy="ann-preview-summary">
          Poruka će biti poslata za <strong>{preview?.recipient_count ?? 0}</strong> primalaca.
        </p>
      </ConfirmDialog>
    </div>
  );
}
