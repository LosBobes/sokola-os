import { useEffect, useState } from "react";
import { ApiError, api, setAuthHeaders } from "../api/client";
import { NoTenantAccessError, useSession } from "../auth/session";
import { BrandMark } from "../components/shell";
import { InlineNotice, SegmentedControl, SystemState } from "../components/ui";
import type { AuthConfig, Organization, TenantPublic } from "../api/types";
import "./Entry.css";

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

/**
 * Error line for the credential forms. On the sign-in screen a 401 means the
 * email or password was wrong, not that a session expired, SystemState's
 * generic "Vaša prijava je istekla" copy would be actively misleading (there was
 * no session to expire), so show what the server actually said. Everything else
 * still goes through the canonical states.
 */
function CredentialError({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.status === 401) {
    return <InlineNotice tone="error">{error.message}</InlineNotice>;
  }
  return <SystemState error={error} />;
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
 * Email + password: the default sign-in. On success the session cookie is set
 * and the app re-renders itself (existing role → the school; brand-new account
 * → CreateSchool), so there's nothing to do here beyond surfacing errors.
 *
 *  - "signin": email + password.
 *  - "signup": email + password + name, registers a new account, then signs in.
 *
 * `organizationId` (signin only) pre-selects that school once `/me` loads,
 * mirroring `signInWithGoogle(organizationId)`.
 */
function PasswordForm({
  mode,
  organizationId,
}: {
  mode: "signin" | "signup";
  organizationId?: string;
}) {
  const { signInWithPassword, registerWithPassword } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [given, setGiven] = useState("");
  const [family, setFamily] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") {
        await registerWithPassword({
          email: email.trim(),
          password,
          givenName: given.trim(),
          familyName: family.trim(),
        });
      } else {
        await signInWithPassword(email.trim(), password, organizationId);
      }
      // On success the session is set and <App> re-renders into the shell.
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} data-cy="password-form" style={{ display: "grid", gap: "var(--space-2)" }}>
      {error ? <CredentialError error={error} /> : null}
      {mode === "signup" ? (
        <>
          <div className="field">
            <label htmlFor="pw-given">Ime</label>
            <input
              id="pw-given"
              value={given}
              onChange={(e) => setGiven(e.target.value)}
              required
              data-cy="password-given"
            />
          </div>
          <div className="field">
            <label htmlFor="pw-family">Prezime</label>
            <input
              id="pw-family"
              value={family}
              onChange={(e) => setFamily(e.target.value)}
              required
              data-cy="password-family"
            />
          </div>
        </>
      ) : null}
      <div className="field">
        <label htmlFor="pw-email">Mejl adresa</label>
        <input
          id="pw-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
          data-cy="password-email"
        />
      </div>
      <div className="field">
        <label htmlFor="pw-password">Lozinka</label>
        <input
          id="pw-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={mode === "signup" ? 8 : undefined}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          data-cy="password-password"
        />
        {mode === "signup" ? (
          <small style={{ color: "var(--text-secondary)" }}>Najmanje 8 karaktera.</small>
        ) : null}
      </div>
      <button className="btn btn--primary" type="submit" disabled={busy} data-cy="password-submit">
        {mode === "signup" ? "Registruj se" : "Prijava"}
      </button>
    </form>
  );
}

/**
 * The email side of sign-in. Password is the only email method; when password
 * auth is switched off server-side there is nothing to render here, and Google
 * (or the dev adapter) is the way in.
 */
function EmailAuth({
  mode,
  organizationId,
  passwordEnabled,
}: {
  mode: "signin" | "signup";
  organizationId?: string;
  passwordEnabled: boolean;
}) {
  if (!passwordEnabled) return null;
  return <PasswordForm mode={mode} organizationId={organizationId} />;
}

/**
 * Unauthenticated entry. Email+password is the default sign-in in every
 * environment, with Google beside it where it's configured. Signing up needs
 * no school code: a new account authenticates first and then lands in
 * CreateSchool, because a person exists before any organization does. Naming a school up front (`login-code`) stays available for people
 * joining an existing one. The old raw-ID dev flow only remains reachable when
 * Google isn't configured (`showDevAuth`), which keeps it alive for Cypress/CI
 * without showing it to a real user.
 */
export function Entry({ initialMessage }: { initialMessage?: string }) {
  const { signInWithGoogle } = useSession();
  const [view, setView] = useState<View>("landing");
  const [tenant, setTenant] = useState<TenantPublic | null>(null);
  const [created, setCreated] = useState<{ slug: string; personId: string } | null>(null);
  const [config, setConfig] = useState<AuthConfig>({
    google_enabled: false,
    password_enabled: true,
    dev_auth_enabled: true,
  });
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

  const showDevAuth = config.dev_auth_enabled && !config.google_enabled;

  return (
    <div className="entry">
      {/* Left: the brand panel. Purely decorative, hidden on narrow viewports
          so the phone gets the full width for the form. */}
      <aside className="entry__panel" aria-hidden>
        <BrandMark variant="reverse" className="entry__logo" />
        <p className="entry__eyebrow">Operativni sistem škole</p>
        <p className="display-line entry__display">
          Sve obaveze.
          <br />
          Bez iznenađenja.
        </p>
        <p className="entry__lede">
          Članovi, raspored, finansije, komunikacija i dokumenti jedne škole na jednom mestu, sa
          jasnim poreklom svakog broja.
        </p>
      </aside>

      <div className="entry__main">
        <div className="card entry__card">
          <BrandMark variant="stacked" className="entry__cardlogo" />
          <h1 className="entry__title">Prijava u sistem</h1>
          <p className="entry__sub">Nastavite nalogom kojim vas je škola dodala.</p>
          {loginFailed ? (
            <p className="notice notice--warning" data-cy="login-failed">
              Prijava trenutno nije uspela. Pokušajte ponovo.
            </p>
          ) : null}
          {initialMessage && view === "landing" ? (
            <p className="notice notice--info">{initialMessage}</p>
          ) : null}

          {view === "landing" && (
            <Landing
              google={config.google_enabled}
              passwordEnabled={config.password_enabled}
              showDevAuth={showDevAuth}
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
              showDevAuth={showDevAuth}
              onGoogle={() => signInWithGoogle(tenant.organization_id)}
              onBack={() => setView("login-code")}
            />
          )}
          {view === "register" && showDevAuth && (
            <Register
              onCreated={(slug, personId) => {
                setCreated({ slug, personId });
                setView("registered");
              }}
              onBack={() => setView("landing")}
            />
          )}
          {view === "registered" && created && (
            <Registered slug={created.slug} personId={created.personId} />
          )}
        </div>
        <p className="entry__footnote">
          mySOKOLA je pristup za roditelje. Škola vas dodaje; nalog se ne otvara sam.
        </p>
      </div>
    </div>
  );
}

function Landing({
  onLogin,
  onRegister,
  google,
  passwordEnabled,
  showDevAuth,
  onGoogle,
}: {
  onLogin: () => void;
  onRegister: () => void;
  google: boolean;
  passwordEnabled: boolean;
  showDevAuth: boolean;
  onGoogle: () => void;
}) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      <p>Platforma za vođenje sportskih klubova, plesnih i drugih škola.</p>
      {google ? <GoogleButton onClick={onGoogle} /> : null}
      <SegmentedControl
        ariaLabel="Prijava ili registracija"
        value={mode}
        onChange={setMode}
        options={[
          { value: "signin", label: "Već imam nalog" },
          { value: "signup", label: "Prvi put sam ovde" },
        ]}
      />
      <EmailAuth mode={mode} passwordEnabled={passwordEnabled} />
      <button className="btn btn--secondary" onClick={onLogin} data-cy="go-login">
        Prijavi se u školu
      </button>
      {showDevAuth ? (
        <button className="btn btn--secondary" onClick={onRegister} data-cy="go-register">
          Osnuj novu školu
        </button>
      ) : null}
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
  showDevAuth,
  onGoogle,
  onBack,
}: {
  tenant: TenantPublic;
  config: AuthConfig;
  showDevAuth: boolean;
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
      <h2 style={{ margin: "0 0 var(--space-2)" }}>Prijava · {tenant.name}</h2>
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

      <EmailAuth
        mode="signin"
        organizationId={tenant.organization_id}
        passwordEnabled={config.password_enabled}
      />

      {showDevAuth ? (
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="pid">Pristupni kôd</label>
            <input id="pid" value={personId} onChange={(e) => setPersonId(e.target.value)} required data-cy="access-code" />
            <small style={{ color: "var(--text-secondary)" }}>
              Privremeni razvojni način prijave: unesite ID osobe iz registracije.
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
