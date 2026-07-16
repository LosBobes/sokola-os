import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, setAuthHeaders } from "../api/client";
import type { Context, Me } from "../api/types";

/*
 * Client session state. In local dev the "identity" is just a person id (the
 * server's dev header adapter). The chosen context is a RoleAssignment id; the
 * server re-derives and re-checks organization/role on every request — the
 * client never grants access.
 */

interface SessionState {
  me: Me | null;
  activeContext: Context | null;
  signInAs: (personId: string) => Promise<Me>;
  chooseContext: (roleAssignmentId: string) => void;
  signOut: () => void;
  loading: boolean;
}

const SessionCtx = createContext<SessionState | null>(null);

const PERSON_KEY = "sokola.personId";
const CONTEXT_KEY = "sokola.roleAssignmentId";

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

  const loadMe = useCallback(
    async (personId: string): Promise<Me> => {
      setAuthHeaders(personId, null);
      const next = await api.get<Me>("/me");
      setMe(next);
      localStorage.setItem(PERSON_KEY, personId);
      const stored = localStorage.getItem(CONTEXT_KEY);
      const preferred = next.contexts.find((c) => c.role_assignment_id === stored);
      applyContext(next, (preferred ?? next.contexts[0])?.role_assignment_id ?? null);
      return next;
    },
    [applyContext],
  );

  useEffect(() => {
    const stored = localStorage.getItem(PERSON_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    loadMe(stored)
      .catch(() => {
        localStorage.removeItem(PERSON_KEY);
      })
      .finally(() => setLoading(false));
  }, [loadMe]);

  const signInAs = useCallback((personId: string) => loadMe(personId), [loadMe]);

  const chooseContext = useCallback(
    (roleAssignmentId: string) => applyContext(me, roleAssignmentId),
    [applyContext, me],
  );

  const signOut = useCallback(() => {
    localStorage.removeItem(PERSON_KEY);
    localStorage.removeItem(CONTEXT_KEY);
    setAuthHeaders(null, null);
    setMe(null);
    setActiveContext(null);
  }, []);

  const value = useMemo(
    () => ({ me, activeContext, signInAs, chooseContext, signOut, loading }),
    [me, activeContext, signInAs, chooseContext, signOut, loading],
  );

  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionCtx);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
