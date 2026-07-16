import { useEffect, useRef, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useSession } from "../auth/session";
import type { RoleCode } from "../api/types";
import "./shell.css";

interface Destination {
  to: string;
  label: string;
  hint: string;
}

// Role-based shells: each role gets its own home and at most five destinations.
const NAV: Record<RoleCode, Destination[]> = {
  OWNER: managerNav(),
  MANAGER: managerNav(),
  ADMIN: managerNav(),
  TRAINER: [
    { to: "/", label: "Danas", hint: "Termini i prisustvo" },
    { to: "/raspored", label: "Raspored", hint: "Svi termini" },
  ],
  PARENT: [
    { to: "/", label: "Početna", hint: "Šta je sledeće" },
    { to: "/dogadjaji", label: "Događaji", hint: "Prijave" },
  ],
  STUDENT: [{ to: "/", label: "Početna", hint: "" }],
};

function managerNav(): Destination[] {
  return [
    { to: "/", label: "Danas", hint: "Pregled dana" },
    { to: "/ljudi", label: "Ljudi i grupe", hint: "Članovi" },
    { to: "/raspored", label: "Raspored", hint: "Termini" },
    { to: "/finansije", label: "Finansije", hint: "Zaduženja i uplate" },
    { to: "/komunikacija", label: "Komunikacija", hint: "Obaveštenja" },
  ];
}

function ContextSwitcher() {
  const { me, activeContext, chooseContext } = useSession();
  if (!me) return null;
  return (
    <div className="context-switcher">
      <label className="field" style={{ margin: 0 }}>
        <span>Škola / uloga</span>
        <select
          value={activeContext?.role_assignment_id ?? ""}
          onChange={(e) => chooseContext(e.target.value)}
          data-cy="context-switcher"
        >
          {me.contexts.map((c) => (
            <option key={c.role_assignment_id} value={c.role_assignment_id}>
              {c.organization_name} · {c.role_code}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/** Announces route changes politely and moves focus to main content. */
function RouteAnnouncer({ mainRef }: { mainRef: React.RefObject<HTMLElement | null> }) {
  const location = useLocation();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.textContent = `Stranica: ${location.pathname}`;
    mainRef.current?.focus();
  }, [location.pathname, mainRef]);
  return <div ref={ref} aria-live="polite" className="visually-hidden" />;
}

export function ProductShell({ children }: { children: ReactNode }) {
  const { activeContext, signOut } = useSession();
  const mainRef = useRef<HTMLElement>(null);
  const destinations = activeContext ? NAV[activeContext.role_code] : [];

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Preskoči na sadržaj
      </a>
      <nav className="shell__nav" aria-label="Glavna navigacija">
        <div className="shell__brand">SOKOLA</div>
        {destinations.map((d) => (
          <NavLink key={d.to} to={d.to} end={d.to === "/"} className="navlink" data-cy={`nav-${d.to}`}>
            {d.label}
            {d.hint && <small>{d.hint}</small>}
          </NavLink>
        ))}
        <ContextSwitcher />
        <button className="btn btn--secondary" onClick={signOut} data-cy="sign-out">
          Odjava
        </button>
      </nav>
      <RouteAnnouncer mainRef={mainRef} />
      <main id="main" className="shell__main" tabIndex={-1} ref={mainRef}>
        {children}
      </main>
    </div>
  );
}

export function PageHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <header className="pageheader">
      <h1>{title}</h1>
      {action}
    </header>
  );
}
