import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchMe, type MeResponse } from "@/api/client";
import { clearAuth, getToken, getUser, setToken, setUser } from "@/lib/auth";

type AuthState = {
  token: string | null;
  user: { user_id?: string; tenant_id?: string; roles?: string[] } | null;
  me: MeResponse | null;
  loading: boolean;
  refreshMe: () => Promise<void>;
  login: (token: string, user?: { user_id: string; tenant_id: string; roles: string[] }) => void;
  logout: () => void;
  hasPermission: (perm: string) => boolean;
  canReadSource: (sourceId: string) => boolean;
  canAdminSource: (sourceId: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(() => getToken());
  const [user, setUsr] = useState(() => getUser());
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(!!getToken());

  const refreshMe = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const m = await fetchMe();
      setMe(m);
      setUsr({
        user_id: m.user_id,
        tenant_id: m.tenant_id,
        roles: m.roles,
      });
      setUser({
        user_id: m.user_id,
        tenant_id: m.tenant_id,
        roles: m.roles,
      });
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) void refreshMe();
    else {
      setMe(null);
      setLoading(false);
    }
  }, [token, refreshMe]);

  const login = useCallback(
    (t: string, u?: { user_id: string; tenant_id: string; roles: string[] }) => {
      setToken(t);
      setTok(t);
      if (u) {
        setUser(u);
        setUsr(u);
      }
    },
    [],
  );

  const logout = useCallback(() => {
    clearAuth();
    setTok(null);
    setUsr(null);
    setMe(null);
  }, []);

  const hasPermission = useCallback(
    (perm: string) => !!me?.permissions?.includes(perm),
    [me],
  );

  const canReadSource = useCallback(
    (sourceId: string) =>
      !!me?.sources?.find((s) => s.source_id === sourceId)?.can_read,
    [me],
  );

  const canAdminSource = useCallback(
    (sourceId: string) =>
      !!me?.sources?.find((s) => s.source_id === sourceId)?.can_admin,
    [me],
  );

  const value = useMemo(
    () => ({
      token,
      user,
      me,
      loading,
      refreshMe,
      login,
      logout,
      hasPermission,
      canReadSource,
      canAdminSource,
    }),
    [
      token,
      user,
      me,
      loading,
      refreshMe,
      login,
      logout,
      hasPermission,
      canReadSource,
      canAdminSource,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
