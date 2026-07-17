import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, apiRequest, setAuthHeaders } from "../api/client";
import type { Context, Me } from "../api/types";

/*
 * Client session state. Two identity paths converge on the same `/me`:
 *  - dev header adapter (local): a person id sent as a header, persisted locally;
 *  - Google OIDC (prod-like): a signed session cookie set by the login callback.
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
  chooseContext: (roleAssignmentId: string) => void;
  signOut: () => void;
  loading: boolean;
}

const SessionCtx = createContext<SessionState | null>(null);

const PERSON_KEY = "sokola.personId";
const CONTEXT_KEY = "sokola.roleAssignmentId";
const PENDING_ORG_KEY = "sokola.pendingOrg";

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [activeContext, setActiveContext] = useState<Context | null>(null);
  const [loading, setLoading] = useState(true);

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
    return next;
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
      .catch(() => localStorage.removeItem(PERSON_KEY))
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

  const chooseContext = useCallback(
    (roleAssignmentId: string) => applyContext(me, roleAssignmentId),
    [applyContext, me],
  );

  const signOut = useCallback(() => {
    void apiRequest("POST", "/auth/logout").catch(() => undefined);
    localStorage.removeItem(PERSON_KEY);
    localStorage.removeItem(CONTEXT_KEY);
    setAuthHeaders(null, null);
    setMe(null);
    setActiveContext(null);
  }, []);

  const value = useMemo(
    () => ({
      me,
      activeContext,
      signInAs,
      signInToTenant,
      signInWithGoogle,
      chooseContext,
      signOut,
      loading,
    }),
    [me, activeContext, signInAs, signInToTenant, signInWithGoogle, chooseContext, signOut, loading],
  );

  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionCtx);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
