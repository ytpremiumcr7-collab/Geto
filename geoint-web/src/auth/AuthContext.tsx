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
import {
  clearAuth,
  clearToken,
  getToken,
  getUser,
  setToken,
  setUser,
  logoutRemote,
  type AuthUser,
} from "@/lib/auth";

type AuthState = {
  token: string | null;
  user: AuthUser | null;
  me: MeResponse | null;
  authenticated: boolean;
  loading: boolean;
  refreshMe: () => Promise<void>;
  login: (token: string | null, user?: AuthUser) => Promise<void>;
  logout: () => void;
  hasPermission: (perm: string) => boolean;
  canReadSource: (sourceId: string) => boolean;
  canAdminSource: (sourceId: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(() => getToken());
  const [user, setUsr] = useState<AuthUser | null>(() => getUser());
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    setLoading(true);
    try {
      const current = await fetchMe();
      const identity: AuthUser = {
        user_id: current.user_id,
        tenant_id: current.tenant_id,
        roles: current.roles,
      };
      setMe(current);
      setUsr(identity);
      setUser(identity);
    } catch {
      clearAuth();
      setTok(null);
      setUsr(null);
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const login = useCallback(
    async (nextToken: string | null, nextUser?: AuthUser) => {
      if (nextToken) {
        setToken(nextToken);
        setTok(nextToken);
      } else {
        clearToken();
        setTok(null);
      }
      if (nextUser) {
        setUser(nextUser);
        setUsr(nextUser);
      }
      await refreshMe();
    },
    [refreshMe],
  );

  const logout = useCallback(() => {
    void logoutRemote();
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
      !!me?.sources?.find((source) => source.source_id === sourceId)?.can_read,
    [me],
  );

  const canAdminSource = useCallback(
    (sourceId: string) =>
      !!me?.sources?.find((source) => source.source_id === sourceId)?.can_admin,
    [me],
  );

  const value = useMemo(
    () => ({
      token,
      user,
      me,
      authenticated: me !== null,
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
