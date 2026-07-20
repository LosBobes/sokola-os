import {
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import { ApiError } from "../api/client";
import "./ui.css";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* ===================================================================== */
/* Buttons                                                                */
/* ===================================================================== */

type ButtonVariant = "primary" | "secondary" | "on-dark";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: ReactNode;
}

/** Re-skinned primary/secondary/on-dark button. Renders the same `.btn`
 * classes routes already use directly (`className="btn btn--primary"`), so
 * both styles stay in sync from one CSS source. */
export function Button({ variant = "primary", icon, className, children, ...rest }: ButtonProps) {
  return (
    <button className={cx("btn", `btn--${variant}`, className)} {...rest}>
      {icon}
      {children}
    </button>
  );
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  label: string;
  variant?: ButtonVariant;
}

/** Icon-only button; `label` becomes the accessible name (aria-label + title). */
export function IconButton({ icon, label, variant = "secondary", className, ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      className={cx("btn", `btn--${variant}`, "btn--icon", className)}
      aria-label={label}
      title={label}
      {...rest}
    >
      {icon}
    </button>
  );
}

/* ===================================================================== */
/* Cards + section headers                                               */
/* ===================================================================== */

export interface SectionHeaderProps {
  eyebrow?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** Eyebrow + title + subtitle, with an optional action slot on the right. */
export function SectionHeader({ eyebrow, title, subtitle, action, className }: SectionHeaderProps) {
  return (
    <div className={cx("section-header", className)}>
      <div className="section-header__text">
        {eyebrow ? <span className="section-header__eyebrow">{eyebrow}</span> : null}
        {title ? <h2 className="section-header__title">{title}</h2> : null}
        {subtitle ? <p className="section-header__subtitle">{subtitle}</p> : null}
      </div>
      {action ? <div className="section-header__action">{action}</div> : null}
    </div>
  );
}

export interface CardProps {
  eyebrow?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
  interactive?: boolean;
  flat?: boolean;
  "data-cy"?: string;
}

/** White raised card (`--surface-raised`), optionally with a built-in
 * section header. Plain `<section className="card">` keeps working
 * unchanged for existing routes — this is an additive, richer entry point. */
export function Card({
  eyebrow,
  title,
  subtitle,
  action,
  children,
  className,
  interactive,
  flat,
  ...rest
}: CardProps) {
  const hasHeader = eyebrow || title || subtitle || action;
  return (
    <section
      className={cx("card", interactive && "card--interactive", flat && "card--flat", className)}
      {...rest}
    >
      {hasHeader ? (
        <SectionHeader eyebrow={eyebrow} title={title} subtitle={subtitle} action={action} />
      ) : null}
      {children}
    </section>
  );
}

/* ===================================================================== */
/* Status badges                                                         */
/* ===================================================================== */

type Tone = "success" | "warning" | "error" | "info" | "neutral";

/** Status is conveyed by text + tone, never color alone. */
export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`badge badge--${tone}`} data-cy="status-badge">
      {children}
    </span>
  );
}

export function InlineNotice({
  tone,
  children,
}: {
  tone: "error" | "info" | "warning";
  children: ReactNode;
}) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

/* ===================================================================== */
/* Stat tiles                                                            */
/* ===================================================================== */

export interface StatTileProps {
  icon?: ReactNode;
  label: ReactNode;
  value: ReactNode;
  delta?: { label: ReactNode; tone?: "up" | "down" | "neutral" };
  className?: string;
}

/** Icon + label + big number + delta line, as used on the "Danas" overview. */
export function StatTile({ icon, label, value, delta, className }: StatTileProps) {
  return (
    <div className={cx("stat-tile", className)} data-cy="stat-tile">
      {icon ? <div className="stat-tile__icon">{icon}</div> : null}
      <div className="stat-tile__body">
        <div className="stat-tile__label">{label}</div>
        <div className="stat-tile__value">{value}</div>
        {delta ? (
          <div className={cx("stat-tile__delta", delta.tone && `stat-tile__delta--${delta.tone}`)}>
            {delta.label}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ===================================================================== */
/* Tables                                                                 */
/* ===================================================================== */

/** Wraps a `<table className="data">` so wide tables scroll horizontally
 * instead of overflowing the page on small screens. */
export function TableContainer({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("table-wrap", className)}>{children}</div>;
}

/* ===================================================================== */
/* Split pane (list + detail)                                            */
/* ===================================================================== */

export interface SplitPaneProps {
  list: ReactNode;
  detail: ReactNode;
  className?: string;
}

/** Two-column list + detail layout (e.g. Ljudi: table on the left, the
 * selected person's profile on the right). Collapses to a single column
 * on narrow viewports. */
export function SplitPane({ list, detail, className }: SplitPaneProps) {
  return (
    <div className={cx("split-pane", className)}>
      <div className="split-pane__list card">
        <div className="split-pane__list-body">{list}</div>
      </div>
      <div className="split-pane__detail card">
        <div className="split-pane__detail-body">{detail}</div>
      </div>
    </div>
  );
}

export interface SplitPaneRowProps {
  active?: boolean;
  onClick?: () => void;
  children: ReactNode;
  className?: string;
}

/** One selectable row inside a `SplitPane`'s list side. */
export function SplitPaneRow({ active, onClick, children, className }: SplitPaneRowProps) {
  return (
    <button
      type="button"
      className={cx("split-pane__row", active && "split-pane__row--active", className)}
      aria-current={active ? "true" : undefined}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

/* ===================================================================== */
/* Filter chips / segmented controls                                     */
/* ===================================================================== */

export function FilterBar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("filter-bar", className)}>{children}</div>;
}

export interface FilterChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  /** Show a caret, for chips that open a dropdown (e.g. "Ogranak", "Grupa"). */
  caret?: boolean;
}

/** A single filter pill, e.g. "Aktivni" / "Ogranak" / "Grupa" in the Ljudi
 * toolbar. Toggle it with `active`, or use `caret` for a dropdown trigger. */
export function FilterChip({ active, caret, className, children, ...rest }: FilterChipProps) {
  return (
    <button
      type="button"
      className={cx("filter-chip", active && "filter-chip--active", className)}
      aria-pressed={active}
      {...rest}
    >
      {children}
      {caret ? (
        <svg
          className="filter-chip__caret"
          width="14"
          height="14"
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M5 8l5 5 5-5" />
        </svg>
      ) : null}
    </button>
  );
}

export interface SegmentedControlOption<T extends string> {
  value: T;
  label: ReactNode;
}

export interface SegmentedControlProps<T extends string> {
  options: SegmentedControlOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
}

/** Pill switch for a small set of mutually-exclusive views, e.g.
 * "Danas / Ovaj mesec" or "Dan / Nedelja / Spisak". */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  className,
}: SegmentedControlProps<T>) {
  return (
    <div className={cx("segmented", className)} role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={cx("segmented__option", o.value === value && "segmented__option--active")}
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ===================================================================== */
/* Capacity progress bars                                                */
/* ===================================================================== */

export interface CapacityBarProps {
  value: number;
  max: number;
  label?: ReactNode;
  className?: string;
}

/** Group/roster capacity, e.g. "18 od 20". Fill tone shifts from primary
 * green -> amber near capacity -> red once full, computed from value/max. */
export function CapacityBar({ value, max, label, className }: CapacityBarProps) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const full = max > 0 && value >= max;
  const near = !full && pct >= 85;
  return (
    <div className={cx("capacity-bar", className)} data-cy="capacity-bar">
      {label ? <div className="capacity-bar__label">{label}</div> : null}
      <div
        className="capacity-bar__track"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
      >
        <div
          className={cx(
            "capacity-bar__fill",
            full && "capacity-bar__fill--error",
            near && "capacity-bar__fill--warning",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ===================================================================== */
/* Canonical system states                                               */
/* ===================================================================== */

/**
 * Renders one of the canonical non-normal states. Every state answers: what
 * happened, what was preserved, what is the safe next action.
 */
export function SystemState({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    switch (error.canonical) {
      case "permission":
        return (
          <InlineNotice tone="warning">
            Nemate pristup ovom sadržaju u trenutnom kontekstu. Promenite školu/ulogu.
          </InlineNotice>
        );
      case "conflict":
        return (
          <InlineNotice tone="warning">
            {error.message} Osvežite i pregledajte pre ponovnog pokušaja.
          </InlineNotice>
        );
      case "manual_recovery":
        return (
          <InlineNotice tone="error">
            Ishod nije potvrđen. Podaci i prijava su sačuvani — proverite status pre ponovne akcije.
          </InlineNotice>
        );
      default:
        return <InlineNotice tone="error">{error.message}</InlineNotice>;
    }
  }
  return <InlineNotice tone="error">Došlo je do greške.</InlineNotice>;
}

export function LoadingState({ label = "Učitavanje…" }: { label?: string }) {
  return (
    <p className="loading-state" aria-busy="true" data-cy="loading">
      <span className="loading-state__spinner" aria-hidden="true" />
      {label}
    </p>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="empty-state" data-cy="empty">
      {children}
    </p>
  );
}

/** Native <dialog> confirmation with focus restoration. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  busy,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const restoreTo = useRef<Element | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      restoreTo.current = document.activeElement;
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
      (restoreTo.current as HTMLElement | null)?.focus?.();
    }
  }, [open]);

  return (
    <dialog ref={ref} className="card" onCancel={onCancel} data-cy="confirm-dialog">
      <h2>{title}</h2>
      <div>{children}</div>
      <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <button className="btn btn--primary" onClick={onConfirm} disabled={busy} data-cy="confirm-yes">
          {confirmLabel}
        </button>
        <button className="btn btn--secondary" onClick={onCancel} data-cy="confirm-no">
          Odustani
        </button>
      </div>
    </dialog>
  );
}
