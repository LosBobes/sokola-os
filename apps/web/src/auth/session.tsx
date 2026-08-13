import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  apiRequest,
  clearCsrfCookie,
  setAuthHeaders,
  setUnauthorizedHandler,
} from "../api/client";
import type { Context, Me } from "../api/types";

/*
 * Client session state. Three identity paths converge on the same `/me`:
 *  - email+password (the default): a signed session cookie set by the login XHR;
 *  - Google OIDC: the same cookie, set by the login callback;
 *  - dev header adapter (local only): a person id sent as a header, persisted locally.
 * Either way the chosen context is a RoleAssignment id the server re-checks on
 * every request; the client never grants access.
 */

export class NoTenantAccessError extends Error {}

interface SessionState {
  me: Me | null;
  activeContext: Context | null;
  signInAs: (personId: string) => Promise<Me>;
  signInToTenant: (personId: string, organizationId: string) => Promise<Context>;
  signInWithGoogle: (organizationId?: string) => void;
  /** Email+password sign-in. Establishes the same session cookie Google does,
   * then loads `/me` and activates the right context. */
  signInWithPassword: (email: string, password: string, organizationId?: string) => Promise<Me>;
  /** Register a brand-new email+password account, then sign in. The new person
   * has no school yet, so the app drops into CreateSchool. */
  registerWithPassword: (input: {
    email: string;
    password: string;
    givenName: string;
    familyName: string;
  }) => Promise<Me>;
  chooseContext: (roleAssignmentId: string) => void;
  /** Re-fetch `/me` and re-activate contexts. For a cookie-authenticated
   * session (password/Google) whose role set just changed server-side,
   * e.g. right after creating a new organization. */
  refreshContexts: () => Promise<void>;
  signOut: () => void;
  loading: boolean;
  /** True after any request came back 401, the session is gone, not just
   * missing one permission. Cleared on the next successful sign-in. */
  sessionExpired: boolean;
}

const SessionCtx = createContext<SessionState | null>(null);

const PERSON_KEY = "sokola.personId";
const CONTEXT_KEY = "sokola.roleAssignmentId";
export const PENDING_ORG_KEY = "sokola.pendingOrg";

/**
 * Whether this browser was carrying credentials of some kind. A first-time
 * visitor's `/me` is a 401 too, and telling them their session expired when
 * they never had one is nonsense, so "expired" is only claimed when there was
 * something to expire: a dev-header person id, or the JS-readable CSRF cookie
 * that every cookie login sets and logout deletes (the session cookie itself is
 * httpOnly and invisible from here).
 */
function hadCredentials(): boolean {
  return (
    localStorage.getItem(PERSON_KEY) !== null || /(?:^|;\s*)sokola_csrf=/.test(document.cookie)
  );
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [activeContext, setActiveContext] = useState<Context | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  const applyContext = useCallback((next: Me | null, roleAssignmentId: string | null) => {
    const ctx = next?.contexts.find((c) => c.role_assignment_id === roleAssignmentId) ?? null;
    setActiveContext(ctx);
    setAuthHeaders(next?.person_id ?? null, ctx?.role_assignment_id ?? null);
    if (ctx) localStorage.setItem(CONTEXT_KEY, ctx.role_assignment_id);
    else localStorage.removeItem(CONTEXT_KEY);
  }, []);

  const fetchMe = useCallback(async (): Promise<Me> => {
    const next = await api.get<Me>("/me");
    setMe(next);
    setSessionExpired(false);
    return next;
  }, []);

  // A 401 anywhere means the session is gone (expired, or the person behind
  // it was deleted), clear local auth state and drop back to the login
  // screen with an explanation, instead of every page showing its own
  // dead-end "no access" error with no way to actually fix it.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      const expired = hadCredentials();
      localStorage.removeItem(PERSON_KEY);
      localStorage.removeItem(CONTEXT_KEY);
      // Every trace of the dead session goes at once, or the leftovers make the
      // next page load look like another expiry.
      clearCsrfCookie();
      setAuthHeaders(null, null);
      setMe(null);
      setActiveContext(null);
      setSessionExpired(expired);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // Pick the context to activate: a pending tenant (set before a Google
  // redirect), else the last-used one, else the first available.
  const activateContexts = useCallback(
    (next: Me) => {
      const pending = localStorage.getItem(PENDING_ORG_KEY);
      const stored = localStorage.getItem(CONTEXT_KEY);
      const chosen =
        (pending && next.contexts.find((c) => c.organization_id === pending)) ||
        next.contexts.find((c) => c.role_assignment_id === stored) ||
        next.contexts[0];
      applyContext(next, chosen?.role_assignment_id ?? null);
      localStorage.removeItem(PENDING_ORG_KEY);
    },
    [applyContext],
  );

  useEffect(() => {
    const stored = localStorage.getItem(PERSON_KEY);
    if (stored) setAuthHeaders(stored, null);
    fetchMe()
      .then((next) => activateContexts(next))
      .catch(() => {
        // A real 401 is already handled by the unauthorized handler above
        // (clears PERSON_KEY and everything else). A network hiccup or a
        // backend that's still booting (status 0 or 5xx) must not wipe a
        // still-valid saved identity, or every transient failure on page
        // load forces the user back through onboarding, so nothing to do
        // here beyond not letting the rejection go unhandled.
      })
      .finally(() => setLoading(false));
  }, [fetchMe, activateContexts]);

  const signInAs = useCallback(
    async (personId: string): Promise<Me> => {
      setAuthHeaders(personId, null);
      localStorage.setItem(PERSON_KEY, personId);
      const next = await fetchMe();
      activateContexts(next);
      return next;
    },
    [fetchMe, activateContexts],
  );

  const signInToTenant = useCallback(
    async (personId: string, organizationId: string): Promise<Context> => {
      setAuthHeaders(personId, null);
      localStorage.setItem(PERSON_KEY, personId);
      const next = await fetchMe();
      const ctx = next.contexts.find((c) => c.organization_id === organizationId);
      if (!ctx) throw new NoTenantAccessError("Nemate pristup ovoj školi.");
      applyContext(next, ctx.role_assignment_id);
      return ctx;
    },
    [fetchMe, applyContext],
  );

  const signInWithGoogle = useCallback((organizationId?: string) => {
    if (organizationId) localStorage.setItem(PENDING_ORG_KEY, organizationId);
    window.location.href = "/api/auth/google/login";
  }, []);

  const signInWithPassword = useCallback(
    async (email: string, password: string, organizationId?: string): Promise<Me> => {
      if (organizationId) localStorage.setItem(PENDING_ORG_KEY, organizationId);
      await api.post("/auth/password/login", { email, password });
      const next = await fetchMe();
      activateContexts(next);
      return next;
    },
    [fetchMe, activateContexts],
  );

  const registerWithPassword = useCallback(
    async (input: {
      email: string;
      password: string;
      givenName: string;
      familyName: string;
    }): Promise<Me> => {
      await api.post("/auth/password/register", {
        email: input.email,
        password: input.password,
        given_name: input.givenName,
        family_name: input.familyName,
      });
      const next = await fetchMe();
      activateContexts(next);
      return next;
    },
    [fetchMe, activateContexts],
  );

  const chooseContext = useCallback(
    (roleAssignmentId: string) => applyContext(me, roleAssignmentId),
    [applyContext, me],
  );

  const refreshContexts = useCallback(async (): Promise<void> => {
    const next = await fetchMe();
    activateContexts(next);
  }, [fetchMe, activateContexts]);

  const signOut = useCallback(() => {
    void apiRequest("POST", "/auth/logout").catch(() => undefined);
    localStorage.removeItem(PERSON_KEY);
    localStorage.removeItem(CONTEXT_KEY);
    // The server deletes it too, but not if that request never lands.
    clearCsrfCookie();
    setAuthHeaders(null, null);
    setMe(null);
    setActiveContext(null);
    setSessionExpired(false);
  }, []);

  const value = useMemo(
    () => ({
      me,
      activeContext,
      signInAs,
      signInToTenant,
      signInWithGoogle,
      signInWithPassword,
      registerWithPassword,
      chooseContext,
      refreshContexts,
      signOut,
      loading,
      sessionExpired,
    }),
    [
      me,
      activeContext,
      signInAs,
      signInToTenant,
      signInWithGoogle,
      signInWithPassword,
      registerWithPassword,
      chooseContext,
      refreshContexts,
      signOut,
      loading,
      sessionExpired,
    ],
  );

  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionCtx);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
