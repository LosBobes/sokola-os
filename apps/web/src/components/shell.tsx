import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useSession } from "../auth/session";
import type { RoleCode } from "../api/types";
import "./shell.css";

type IconName =
  | "danas"
  | "ljudi"
  | "raspored"
  | "finansije"
  | "komunikacija"
  | "dogadjaji"
  | "izvestaji"
  | "vise"
  | "prisustvo";

interface Destination {
  to: string;
  label: string;
  hint: string;
  icon: IconName;
  /*
   * Whether this destination survives into the mobile tab bar.
   *
   * A phone tab bar fits four items plus "Više" before the icons and their
   * labels start colliding, and the manager surface has eight. Rather than
   * shrink everything until nothing is legible, the non-primary destinations
   * drop out of the bar (CSS hides them below 861px) and are reached through
   * Više, which lists exactly the ones the bar left out. Defaults to true, so
   * a role with a short nav needs to say nothing.
   */
  primary?: boolean;
}

/** The destinations a role's mobile tab bar hides behind "Više". */
export function overflowDestinations(role: RoleCode): Destination[] {
  return (NAV[role] ?? []).filter((d) => d.primary === false);
}

/*
 * Role-aware navigation. The server hands the active role via /me/contexts
 * (see useSession → activeContext.role_code); the shell only decides which
 * destinations that role sees. Mapping is derived from RoleHome.tsx routing:
 * managers get the full operational surface, trainers a slim on-the-floor set,
 * parents/students the family view. Manager also lists Događaji/Izveštaji/Više
 * from the design; Izveštaji has no route yet, so it falls through the
 * router's `*` redirect to home until its screen lands (separate ticket, M2).
 * Više routes to routes/More.tsx (#18, M1), the account-actions catch-all,
 * since the primary nav already surfaces every other destination directly.
 */
const NAV: Record<RoleCode, Destination[]> = {
  OWNER: managerNav(),
  MANAGER: managerNav(),
  ADMIN: managerNav(),
  // T01 (#27): trainer bottom tab bar is Danas/Prisustvo/Raspored/Grupe/Više.
  // Bare /prisustvo has no dedicated screen yet (separate ticket, M2) so it
  // falls through the router's `*` redirect to home; Više routes to
  // routes/More.tsx like the manager nav above.
  TRAINER: [
    { to: "/", label: "Danas", hint: "Termini i prisustvo", icon: "danas" },
    { to: "/prisustvo", label: "Prisustvo", hint: "Evidencija", icon: "prisustvo" },
    { to: "/raspored", label: "Raspored", hint: "Svi termini", icon: "raspored" },
    { to: "/grupe", label: "Grupe", hint: "Moje grupe", icon: "ljudi" },
    { to: "/vise", label: "Više", hint: "Ostalo", icon: "vise" },
  ],
  PARENT: [
    { to: "/", label: "Početna", hint: "Šta je sledeće", icon: "danas" },
    { to: "/dogadjaji", label: "Događaji", hint: "Prijave", icon: "dogadjaji" },
    { to: "/roditelj/finansije", label: "Finansije", hint: "Zaduženja i uplate", icon: "finansije" },
    { to: "/obavestenja", label: "Obaveštenja", hint: "Poruke škole", icon: "komunikacija" },
  ],
  STUDENT: [{ to: "/", label: "Početna", hint: "", icon: "danas" }],
};

function managerNav(): Destination[] {
  return [
    { to: "/", label: "Danas", hint: "Pregled dana", icon: "danas" },
    { to: "/ljudi", label: "Ljudi i grupe", hint: "Članovi", icon: "ljudi" },
    { to: "/raspored", label: "Raspored", hint: "Termini i događaji", icon: "raspored" },
    { to: "/finansije", label: "Finansije", hint: "Zaduženja i uplate", icon: "finansije" },
    // Below the fold on a phone; reachable through Više (see Destination.primary).
    {
      to: "/komunikacija",
      label: "Komunikacija",
      // Not "Obaveštenja": this is what the school SENDS to parents and
      // trainers. Personal/system notifications are a separate thing and get
      // their own name, so the two never share a label.
      hint: "Objave i poruke",
      icon: "komunikacija",
      primary: false,
    },
    { to: "/dogadjaji", label: "Događaji", hint: "Prijave", icon: "dogadjaji", primary: false },
    { to: "/izvestaji", label: "Izveštaji", hint: "Uvidi", icon: "izvestaji", primary: false },
    { to: "/vise", label: "Više", hint: "Ostalo", icon: "vise" },
  ];
}

export const ROLE_LABEL: Record<RoleCode, string> = {
  OWNER: "Vlasnik",
  MANAGER: "Menadžer",
  ADMIN: "Administrator",
  TRAINER: "Trener",
  PARENT: "Roditelj",
  STUDENT: "Učenik",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0];
  if (!first) return "?";
  const last = parts.length > 1 ? parts[parts.length - 1] : undefined;
  if (!last) return first.slice(0, 2).toUpperCase();
  return ((first[0] ?? "") + (last[0] ?? "")).toUpperCase();
}

/* --- Icons: 24x24 line marks, 1.9px stroke, inheriting the row's colour --- */
function NavIcon({ name }: { name: IconName }) {
  const p = {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
  };
  switch (name) {
    case "danas":
      return (
        <svg {...p}>
          <path d="M3.5 11.5 12 4l8.5 7.5" />
          <path d="M5.5 10v10h13V10" />
          <path d="M10 20v-5h4v5" />
        </svg>
      );
    case "ljudi":
      return (
        <svg {...p}>
          <circle cx="9" cy="8" r="3" />
          <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
          <path d="M16 5.5a3 3 0 0 1 0 6" />
          <path d="M18.5 19a5 5 0 0 0-3-4.6" />
        </svg>
      );
    case "raspored":
      return (
        <svg {...p}>
          <rect x="3.5" y="5" width="17" height="15" rx="2.5" />
          <path d="M3.5 9.5h17M8 3v4M16 3v4" />
        </svg>
      );
    case "finansije":
      return (
        <svg {...p}>
          <rect x="3" y="6" width="18" height="13" rx="2.5" />
          <path d="M3 10.5h18" />
          <path d="M15.5 15h2.5" />
        </svg>
      );
    case "komunikacija":
      return (
        <svg {...p}>
          <path d="M5 4.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9l-4 3.5V15.5H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z" />
        </svg>
      );
    case "dogadjaji":
      return (
        <svg {...p}>
          <path d="M12 3.5 14.6 9l5.9.8-4.3 4.1 1 5.8L12 17l-5.2 2.7 1-5.8L3.5 9.8 9.4 9z" />
        </svg>
      );
    case "izvestaji":
      return (
        <svg {...p}>
          <path d="M4 20h16" />
          <path d="M6 20v-6M12 20V6M18 20v-9" />
        </svg>
      );
    case "vise":
      return (
        <svg {...p}>
          <rect x="4" y="4" width="6.5" height="6.5" rx="1.6" />
          <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" />
          <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" />
          <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6" />
        </svg>
      );
    case "prisustvo":
      return (
        <svg {...p}>
          <rect x="4" y="4.5" width="16" height="15" rx="2.5" />
          <path d="M8.5 12l2.4 2.4L16 9" />
        </svg>
      );
  }
}

/**
 * The approved SOKOLA OS lockup, served from public/brand.
 *
 * These are vector files from Brand Package v1.1.0 and must not be redrawn,
 * recoloured, retyped, rotated, stretched or wrapped in an extra shape. The
 * CSS therefore sets ONE dimension (height) and lets the original viewBox
 * decide the other. Pick the colourway by the surface behind it:
 *
 *  - `reverse`  gold symbol + white wordmark, for the navy sidebar
 *  - `primary`  navy symbol + navy wordmark, for white and canvas surfaces
 *  - `stacked`  the tall lockup, for login and onboarding
 */
export type BrandVariant = "primary" | "reverse" | "stacked";

const BRAND_SRC: Record<BrandVariant, string> = {
  primary: "/brand/logo-horizontal.svg",
  reverse: "/brand/logo-reverse-on-navy.svg",
  stacked: "/brand/logo-stacked.svg",
};

export function BrandMark({
  variant = "primary",
  className = "brandmark",
}: {
  variant?: BrandVariant;
  className?: string;
}) {
  return <img className={className} src={BRAND_SRC[variant]} alt="SOKOLA OS" />;
}

/** Organisation switcher, the active school. Kept as a native <select> so the
 *  existing [data-cy=context-switcher] contract and keyboard behaviour hold. */
function ContextSwitcher() {
  const { me, activeContext, chooseContext } = useSession();
  if (!me) return null;
  const orgName = activeContext?.school_name ?? "";
  return (
    <div className="orgswitcher">
      <span className="orgswitcher__avatar" aria-hidden>
        {(orgName[0] ?? "?").toUpperCase()}
      </span>
      <label className="orgswitcher__label">
        <span className="visually-hidden">Škola / uloga</span>
        <select
          value={activeContext?.role_assignment_id ?? ""}
          onChange={(e) => chooseContext(e.target.value)}
          data-cy="context-switcher"
          aria-label="Aktivna škola i uloga"
        >
          {me.contexts.map((c) => (
            <option key={c.role_assignment_id} value={c.role_assignment_id}>
              {c.school_name} · {ROLE_LABEL[c.role_code]}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/** Top-bar account menu, mirrors the sidebar chip, and is the sign-out path on
 *  mobile where the sidebar collapses. The canonical [data-cy=sign-out] lives on
 *  the always-visible sidebar chip, so this menu item stays unmarked. */
function UserMenu({ name, role }: { name: string; role: string }) {
  const { signOut } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="usermenu" ref={ref}>
      <button
        type="button"
        className="avatar avatar--user"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Nalog"
        onClick={() => setOpen((v) => !v)}
      >
        {initials(name)}
      </button>
      {open && (
        <div className="usermenu__pop" role="menu">
          <div className="usermenu__id">
            <strong>{name}</strong>
            <span>{role}</span>
          </div>
          <button
            type="button"
            className="usermenu__item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
          >
            Odjava
          </button>
        </div>
      )}
    </div>
  );
}

/** Announces route changes politely and moves focus to main content.
 *  `preventScroll` avoids a real bug this surfaced on taller pages (M12
 *  Izveštaji is the first to be taller than one viewport): the default
 *  focus() scroll-into-view aligns a too-tall <main> to the viewport top,
 *  which pushes it *behind* the sticky topbar (`.topbar` reserves ~69px
 *  in flow but stays pinned on top), hiding the page's own <h1> on load.
 *  Shorter existing pages never hit this because they already fit within
 *  one viewport, so no scroll was ever triggered. Focus still moves to
 *  main for screen readers; only the (incorrect) visual scroll is dropped. */
function RouteAnnouncer({ mainRef }: { mainRef: React.RefObject<HTMLElement | null> }) {
  const location = useLocation();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.textContent = `Stranica: ${location.pathname}`;
    mainRef.current?.focus({ preventScroll: true });
  }, [location.pathname, mainRef]);
  return <div ref={ref} aria-live="polite" className="visually-hidden" />;
}

export function ProductShell({ children }: { children: ReactNode }) {
  const { me, activeContext, signOut } = useSession();
  const mainRef = useRef<HTMLElement>(null);
  const destinations = activeContext ? NAV[activeContext.role_code] : [];
  const name = me?.display_name ?? "";
  const roleLabel = activeContext ? ROLE_LABEL[activeContext.role_code] : "";

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Preskoči na sadržaj
      </a>

      <aside className="sidebar">
        <div className="sidebar__brand">
          <BrandMark variant="reverse" />
        </div>
        <p className="sidebar__eyebrow">Operativni sistem</p>

        <nav className="sidebar__nav" aria-label="Glavna navigacija">
          {destinations.map((d) => (
            <NavLink
              key={d.to}
              to={d.to}
              end={d.to === "/"}
              className={d.primary === false ? "navlink navlink--overflow" : "navlink"}
              data-cy={`nav-${d.to}`}
            >
              <span className="navlink__icon">
                <NavIcon name={d.icon} />
              </span>
              <span className="navlink__text">
                <span className="navlink__label">{d.label}</span>
                {d.hint && <small className="navlink__hint">{d.hint}</small>}
              </span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__user">
          <span className="avatar avatar--gold" aria-hidden>
            {initials(name)}
          </span>
          <span className="sidebar__userid">
            <strong>{name}</strong>
            <span>{roleLabel}</span>
          </span>
          <button
            type="button"
            className="sidebar__logout"
            onClick={signOut}
            data-cy="sign-out"
            aria-label="Odjava"
            title="Odjava"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
              focusable="false"
            >
              <path d="M14 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8" />
              <path d="M10 12h10" />
              <path d="M17 9l3 3-3 3" />
            </svg>
          </button>
        </div>
      </aside>

      <div className="shell__body">
        <header className="topbar">
          <ContextSwitcher />
          <div className="topbar__search">
            {/* TODO(#14): wire operativna pretraga to the search endpoint. */}
            <svg
              className="topbar__searchicon"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
              focusable="false"
            >
              <circle cx="11" cy="11" r="6.5" />
              <path d="m16 16 4 4" />
            </svg>
            <input
              type="search"
              placeholder="Operativna pretraga"
              aria-label="Operativna pretraga"
              disabled
            />
          </div>
          <div className="topbar__actions">
            {/*
              The "Obaveštenja" bell is deliberately absent until there is an
              inbox behind it. It rendered an unread dot and did nothing when
              clicked, which reads as a broken control rather than an
              unfinished one, and taught people to ignore it before it ever
              worked. When personal/system notifications land, the bell comes
              back here , and it keeps that name, distinct from Komunikacija
              (what the school sends to parents and trainers).
            */}
            <UserMenu name={name} role={roleLabel} />
          </div>
        </header>

        <RouteAnnouncer mainRef={mainRef} />
        <main id="main" className="shell__main" tabIndex={-1} ref={mainRef}>
          {children}
        </main>
      </div>
    </div>
  );
}

/**
 * Page header: uppercase eyebrow, 38px title, one supporting line, and the
 * page's primary action pinned top-right. `eyebrow` and `subtitle` are
 * optional, so the existing `<PageHeader title=… action=… />` calls keep
 * rendering exactly as before.
 */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow?: ReactNode;
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="pageheader">
      <div className="pageheader__text">
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {subtitle ? <p className="pageheader__subtitle">{subtitle}</p> : null}
      </div>
      {action}
    </header>
  );
}
