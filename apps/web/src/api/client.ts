/*
 * Thin typed API client + the shared journey adapter.
 *
 * Every mutation/read goes through here so outcomes map to the canonical UI
 * states exactly once: 401/403 -> permission, 409 -> conflict/review, and a
 * missing or 5xx response on a mutation -> manual recovery (never an automatic
 * replay of the primary action).
 */

export type CanonicalState =
  | "ok"
  | "unauthenticated"
  | "permission"
  | "conflict"
  | "validation"
  | "manual_recovery"
  | "not_found";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly canonical: CanonicalState;

  constructor(status: number, body: ApiErrorBody, canonical: CanonicalState) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? {};
    this.canonical = canonical;
  }
}

let authPersonId: string | null = null;
let authRoleAssignmentId: string | null = null;

export function setAuthHeaders(personId: string | null, roleAssignmentId: string | null): void {
  authPersonId = personId;
  authRoleAssignmentId = roleAssignmentId;
}

/**
 * Fired whenever ANY request comes back 401, the session is gone (expired,
 * or the person behind it no longer exists), not just missing one permission.
 * The session layer registers a handler that clears local auth state and
 * bounces the app back to the login screen, instead of every page showing
 * its own dead-end "no access" error with no way to actually fix it.
 */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

interface RequestOptions {
  body?: unknown;
  idempotencyKey?: string;
  /** true for mutations: an unknown outcome becomes manual_recovery, not a retry. */
  mutation?: boolean;
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export const CSRF_COOKIE = "sokola_csrf";

/** Read the JS-readable CSRF cookie set by every login flow. */
function readCsrfToken(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${CSRF_COOKIE}=([^;]+)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

/**
 * Drop the CSRF cookie locally. The session cookie it pairs with is httpOnly,
 * so once the server has rejected that session there is nothing else the client
 * can clear, and leaving this one behind makes the app believe on every
 * subsequent page load that it still holds a session, which is what turned one
 * dead cookie into a permanent "your session expired" notice. Logout deletes it
 * server-side; this covers the case where the session died on its own.
 */
export function clearCsrfCookie(): void {
  document.cookie = `${CSRF_COOKIE}=; path=/; max-age=0`;
}

function classify(status: number, mutation: boolean): CanonicalState {
  if (status === 401) return "unauthenticated";
  if (status === 403) return "permission";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "validation";
  if (status >= 500) return "manual_recovery";
  return mutation ? "manual_recovery" : "ok";
}

export async function apiRequest<T>(
  method: string,
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authPersonId) headers["x-sokola-person-id"] = authPersonId;
  if (authRoleAssignmentId) headers["x-sokola-role-assignment-id"] = authRoleAssignmentId;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  // Synchronizer token for cookie-authenticated mutations. The server ignores it
  // for dev-header requests (no session), so sending it unconditionally is safe.
  if (UNSAFE_METHODS.has(method.toUpperCase())) {
    const csrf = readCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: "include",
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    // Network failure. For a mutation the outcome is unknown → manual recovery.
    throw new ApiError(
      0,
      { code: "NETWORK", message: "Mreža nije dostupna. Podaci nisu izgubljeni." },
      opts.mutation ? "manual_recovery" : "ok",
    );
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const errBody: ApiErrorBody = payload?.error ?? {
      code: "HTTP_ERROR",
      message: "Zahtev nije uspeo.",
    };
    // A 401 from a sign-in attempt means the credentials were wrong, not that a
    // session died, firing the handler there would raise "your session
    // expired" on top of a login screen nobody was logged into. `/me` is the
    // deliberate exception: it IS the session check, and its 401 on page load
    // is how an expired cookie gets noticed.
    const isCredentialCheck = path.startsWith("/auth/") && path !== "/auth/config";
    if (response.status === 401 && !isCredentialCheck) onUnauthorized?.();
    throw new ApiError(response.status, errBody, classify(response.status, opts.mutation ?? false));
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string) => apiRequest<T>("GET", path),
  post: <T>(path: string, body?: unknown, idempotencyKey?: string) =>
    apiRequest<T>("POST", path, { body, idempotencyKey, mutation: true }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>("PUT", path, { body, mutation: true }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>("PATCH", path, { body, mutation: true }),
};

/** A fresh idempotency key for a deliberate mutation attempt. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
