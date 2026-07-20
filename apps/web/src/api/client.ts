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

interface RequestOptions {
  body?: unknown;
  idempotencyKey?: string;
  /** true for mutations: an unknown outcome becomes manual_recovery, not a retry. */
  mutation?: boolean;
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Read the JS-readable CSRF cookie set by the Google login callback. */
function readCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)sokola_csrf=([^;]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function classify(status: number, mutation: boolean): CanonicalState {
  if (status === 401 || status === 403) return "permission";
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
