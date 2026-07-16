import { useEffect, useRef, type ReactNode } from "react";
import { ApiError } from "../api/client";

type Tone = "success" | "warning" | "error" | "info";

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
    <p aria-busy="true" data-cy="loading">
      {label}
    </p>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="notice notice--info" data-cy="empty">
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
