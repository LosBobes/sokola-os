import { useEffect, useState } from "react";
import { api, setAuthHeaders } from "../api/client";
import { NoTenantAccessError, useSession } from "../auth/session";
import { SystemState } from "../components/ui";
import type { AuthConfig, Organization, TenantPublic } from "../api/types";

interface DevIdentityResponse {
  person_id: string;
  display_name: string;
}

type View = "landing" | "login-code" | "login-id" | "register" | "registered";

function GoogleIcon() {
  // Google's four-colour "G" mark.
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.47.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
    </svg>
  );
}

function GoogleButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      className="btn btn--secondary"
      onClick={onClick}
      data-cy="google-login"
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "var(--space-2)" }}
    >
      <GoogleIcon />
      Prijava Google nalogom
    </button>
  );
}

/**
 * Unauthenticated entry. Login is tenant-first: you name the school (its code),
 * get routed to that tenant's login, then authenticate into it. Creating a new
 * school is a separate path. In production the identity step is an OIDC redirect;
 * here it's the dev access code (a person id).
 */
export function Entry({ initialMessage }: { initialMessage?: string }) {
  const { signInWithGoogle } = useSession();
  const [view, setView] = useState<View>("landing");
  const [tenant, setTenant] = useState<TenantPublic | null>(null);
  const [created, setCreated] = useState<{ slug: string; personId: string } | null>(null);
  const [config, setConfig] = useState<AuthConfig>({ google_enabled: false, dev_auth_enabled: true });
  const [loginFailed, setLoginFailed] = useState(false);

  useEffect(() => {
    api.get<AuthConfig>("/auth/config").then(setConfig).catch(() => undefined);
  }, []);

  useEffect(() => {
    // The Google callback redirects here with ?login=failed on a provider
    // outage or denied consent. Show a soft notice and clean the URL.
    const params = new URLSearchParams(window.location.search);
    if (params.get("login") === "failed") {
      setLoginFailed(true);
      params.delete("login");
      const clean = window.location.pathname + (params.toString() ? `?${params}` : "");
      window.history.replaceState(null, "", clean);
    }
  }, []);

  return (
    <div style={{ maxWidth: 460, margin: "8vh auto" }}>
      <div className="card">
        <h1>🐦 SOKOLA OS</h1>
        {loginFailed ? (
          <p className="notice notice--warning" data-cy="login-failed">
            Prijava Google nalogom trenutno nije uspela. Pokušajte ponovo.
          </p>
        ) : null}
        {initialMessage && view === "landing" ? (
          <p className="notice notice--info">{initialMessage}</p>
        ) : null}

        {view === "landing" && (
          <Landing
            google={config.google_enabled}
            onGoogle={() => signInWithGoogle()}
            onLogin={() => setView("login-code")}
            onRegister={() => setView("register")}
          />
        )}
        {view === "login-code" && (
          <FindTenant
            onFound={(t) => {
              setTenant(t);
              setView("login-id");
            }}
            onBack={() => setView("landing")}
          />
        )}
        {view === "login-id" && tenant && (
          <TenantLogin
            tenant={tenant}
            config={config}
            onGoogle={() => signInWithGoogle(tenant.organization_id)}
            onBack={() => setView("login-code")}
          />
        )}
        {view === "register" && (
          <Register
            onCreated={(slug, personId) => {
              setCreated({ slug, personId });
              setView("registered");
            }}
            onBack={() => setView("landing")}
          />
        )}
        {view === "registered" && created && <Registered slug={created.slug} personId={created.personId} />}
      </div>
    </div>
  );
}

function Landing({
  onLogin,
  onRegister,
  google,
  onGoogle,
}: {
  onLogin: () => void;
  onRegister: () => void;
  google: boolean;
  onGoogle: () => void;
}) {
  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      <p>Platforma za vođenje sportskih klubova, plesnih i drugih škola.</p>
      {google ? <GoogleButton onClick={onGoogle} /> : null}
      <button className="btn btn--primary" onClick={onLogin} data-cy="go-login">
        Prijavi se u školu
      </button>
      <button className="btn btn--secondary" onClick={onRegister} data-cy="go-register">
        Osnuj novu školu
      </button>
    </div>
  );
}

function FindTenant({ onFound, onBack }: { onFound: (t: TenantPublic) => void; onBack: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onFound(await api.get<TenantPublic>(`/tenants/${encodeURIComponent(code.trim())}`));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <p>Unesite kôd škole da nastavite do prijave.</p>
      {error ? <SystemState error={error} /> : null}
      <div className="field">
        <label htmlFor="code">Kôd škole</label>
        <input id="code" value={code} onChange={(e) => setCode(e.target.value)} required data-cy="tenant-code" placeholder="npr. klub-soko" />
      </div>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <button className="btn btn--primary" type="submit" disabled={busy} data-cy="tenant-continue">
          Nastavi
        </button>
        <button className="btn btn--secondary" type="button" onClick={onBack}>
          Nazad
        </button>
      </div>
    </form>
  );
}

function TenantLogin({
  tenant,
  config,
  onGoogle,
  onBack,
}: {
  tenant: TenantPublic;
  config: AuthConfig;
  onGoogle: () => void;
  onBack: () => void;
}) {
  const { signInToTenant } = useSession();
  const [personId, setPersonId] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signInToTenant(personId.trim(), tenant.organization_id);
      // On success the app re-renders into the tenant's shell.
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 style={{ margin: "0 0 var(--space-2)" }}>Prijava — {tenant.name}</h2>
      {error instanceof NoTenantAccessError ? (
        <div className="notice notice--warning" data-cy="login-error">
          Nemate ulogu u ovoj školi.
        </div>
      ) : error ? (
        <div className="notice notice--warning" data-cy="login-error">
          Neispravan pristupni kôd ili nemate pristup ovoj školi.
        </div>
      ) : null}

      {config.google_enabled ? (
        <div style={{ marginBottom: "var(--space-3)" }}>
          <GoogleButton onClick={onGoogle} />
        </div>
      ) : null}

      {config.dev_auth_enabled ? (
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="pid">Pristupni kôd</label>
            <input id="pid" value={personId} onChange={(e) => setPersonId(e.target.value)} required data-cy="access-code" />
            <small style={{ color: "var(--text-secondary)" }}>
              Privremeni razvojni način prijave — unesite ID osobe iz registracije.
            </small>
          </div>
          <button className="btn btn--primary" type="submit" disabled={busy} data-cy="do-login">
            Uđi
          </button>
        </form>
      ) : null}

      <button className="btn btn--secondary" type="button" onClick={onBack} style={{ marginTop: "var(--space-3)" }}>
        Druga škola
      </button>
    </div>
  );
}

function Register({ onCreated, onBack }: { onCreated: (slug: string, personId: string) => void; onBack: () => void }) {
  const [given, setGiven] = useState("");
  const [family, setFamily] = useState("");
  const [school, setSchool] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const identity = await api.post<DevIdentityResponse>("/internal/dev/identities", {
        given_name: given,
        family_name: family,
      });
      setAuthHeaders(identity.person_id, null);
      const org = await api.post<Organization>("/organizations", { name: school, type: "SPORTS_CLUB" });
      onCreated(org.slug ?? "", identity.person_id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <h2 style={{ margin: "0 0 var(--space-2)" }}>Osnuj školu</h2>
      {error ? <SystemState error={error} /> : null}
      <div className="field">
        <label htmlFor="r-given">Vaše ime</label>
        <input id="r-given" value={given} onChange={(e) => setGiven(e.target.value)} required data-cy="given" />
      </div>
      <div className="field">
        <label htmlFor="r-family">Vaše prezime</label>
        <input id="r-family" value={family} onChange={(e) => setFamily(e.target.value)} required data-cy="family" />
      </div>
      <div className="field">
        <label htmlFor="r-school">Naziv škole</label>
        <input id="r-school" value={school} onChange={(e) => setSchool(e.target.value)} required data-cy="school" />
      </div>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <button className="btn btn--primary" type="submit" disabled={busy} data-cy="do-register">
          Napravi školu
        </button>
        <button className="btn btn--secondary" type="button" onClick={onBack}>
          Nazad
        </button>
      </div>
    </form>
  );
}

function Registered({ slug, personId }: { slug: string; personId: string }) {
  const { signInAs } = useSession();
  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }} data-cy="registered">
      <h2 style={{ margin: 0 }}>Škola je napravljena! 🎉</h2>
      <p>
        Kôd vaše škole je <strong data-cy="school-code">{slug}</strong>. Njime drugi članovi biraju vašu školu pri prijavi.
      </p>
      <p>
        Vaš privremeni pristupni kôd (za sada zamenjuje prijavu nalogom):{" "}
        <strong data-cy="access-id">{personId}</strong>. Zapišite ga.
      </p>
      <button className="btn btn--primary" onClick={() => void signInAs(personId)} data-cy="enter-school">
        Uđi u školu
      </button>
    </div>
  );
}
