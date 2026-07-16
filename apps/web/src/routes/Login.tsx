import { useState } from "react";
import { api, setAuthHeaders } from "../api/client";
import { useSession } from "../auth/session";
import { SystemState } from "../components/ui";
import type { Organization } from "../api/types";

interface DevIdentityResponse {
  person_id: string;
  display_name: string;
}

/**
 * Local onboarding. In production this screen is replaced by an OIDC redirect;
 * here it creates a dev identity and (optionally) a first organization so the
 * rest of the app — and the E2E tests — have something to act on.
 */
export function Login({ message }: { message?: string }) {
  const { signInAs } = useSession();
  const [given, setGiven] = useState("");
  const [family, setFamily] = useState("");
  const [school, setSchool] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onboard(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const identity = await api.post<DevIdentityResponse>("/internal/dev/identities", {
        given_name: given,
        family_name: family,
      });
      setAuthHeaders(identity.person_id, null);
      if (school.trim()) {
        await api.post<Organization>("/organizations", { name: school, type: "SPORTS_CLUB" });
      }
      await signInAs(identity.person_id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 440, margin: "10vh auto" }}>
      <div className="card">
        <h1>🐦 SOKOLA OS</h1>
        <p>Operativni sistem za sportske klubove i škole.</p>
        {message && <p className="notice notice--info">{message}</p>}
        {error ? <SystemState error={error} /> : null}
        <form onSubmit={onboard}>
          <div className="field">
            <label htmlFor="given">Ime</label>
            <input id="given" value={given} onChange={(e) => setGiven(e.target.value)} required data-cy="given" />
          </div>
          <div className="field">
            <label htmlFor="family">Prezime</label>
            <input id="family" value={family} onChange={(e) => setFamily(e.target.value)} required data-cy="family" />
          </div>
          <div className="field">
            <label htmlFor="school">Naziv škole (opciono)</label>
            <input id="school" value={school} onChange={(e) => setSchool(e.target.value)} data-cy="school" />
          </div>
          <button className="btn btn--primary" type="submit" disabled={busy} data-cy="onboard">
            {busy ? "Kreiranje…" : "Kreiraj nalog"}
          </button>
        </form>
      </div>
    </div>
  );
}
