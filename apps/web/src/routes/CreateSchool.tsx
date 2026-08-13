import { useState } from "react";
import { api } from "../api/client";
import { PENDING_ORG_KEY, useSession } from "../auth/session";
import { BrandMark } from "../components/shell";
import { SystemState } from "../components/ui";
import type { Organization } from "../api/types";

/**
 * Shown for an authenticated person (password or Google session already
 * established) with no active role in any school yet, either a brand-new
 * account, or one whose invitations/roles were all revoked. Creating the
 * organization itself needs no prior context (`POST /organizations` only
 * requires an authenticated principal), so this just names the school and
 * refreshes the session's contexts.
 */
export function CreateSchool() {
  const { refreshContexts, signOut } = useSession();
  const [school, setSchool] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const org = await api.post<Organization>("/organizations", {
        name: school,
        type: "SPORTS_CLUB",
      });
      localStorage.setItem(PENDING_ORG_KEY, org.id);
      await refreshContexts();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 460, margin: "8vh auto" }}>
      <div className="card">
        <h1 style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <BrandMark /> SOKOLA OS
        </h1>
        <p className="notice notice--info">
          Vaš nalog nema aktivnu ulogu ni u jednoj školi. Osnujte svoju školu da nastavite, ili se
          prijavite drugim nalogom kome je već dodeljena uloga.
        </p>
        <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-2)" }}>
          <h2 style={{ margin: "0 0 var(--space-2)" }}>Osnuj školu</h2>
          {error ? <SystemState error={error} /> : null}
          <div className="field">
            <label htmlFor="cs-school">Naziv škole</label>
            <input
              id="cs-school"
              value={school}
              onChange={(e) => setSchool(e.target.value)}
              required
              data-cy="create-school-name"
            />
          </div>
          <button className="btn btn--primary" type="submit" disabled={busy} data-cy="create-school-submit">
            Napravi školu
          </button>
        </form>
        <button
          className="btn btn--secondary"
          type="button"
          onClick={signOut}
          style={{ marginTop: "var(--space-3)" }}
          data-cy="create-school-signout"
        >
          Odjavi se
        </button>
      </div>
    </div>
  );
}
