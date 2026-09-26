const TOKEN_KEY = "geoint_token";
const USER_KEY = "geoint_user";

const store: Storage = sessionStorage;

export type AuthUser = {
  user_id?: string;
  tenant_id?: string;
  roles?: string[];
};

function purgeLegacyLocalStorage() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* storage may be unavailable */
  }
}

export function saveAuth(data: AuthUser & { access_token?: string }) {
  purgeLegacyLocalStorage();
  if (data.access_token) setToken(data.access_token);
  setUser(data);
}

export function clearToken() {
  store.removeItem(TOKEN_KEY);
  purgeLegacyLocalStorage();
}

export function clearAuth() {
  store.removeItem(TOKEN_KEY);
  store.removeItem(USER_KEY);
  purgeLegacyLocalStorage();
}

export function getToken(): string | null {
  purgeLegacyLocalStorage();
  return store.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  purgeLegacyLocalStorage();
  const raw = store.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setToken(token: string) {
  purgeLegacyLocalStorage();
  store.setItem(TOKEN_KEY, token);
}

export function setUser(user: AuthUser) {
  purgeLegacyLocalStorage();
  const prev = getUser();
  store.setItem(
    USER_KEY,
    JSON.stringify({
      user_id: user.user_id ?? prev?.user_id,
      tenant_id: user.tenant_id ?? prev?.tenant_id ?? "default",
      roles: user.roles ?? prev?.roles ?? [],
    }),
  );
}

/** Clear client storage and server HttpOnly cookie when cookie mode is on. */
export async function logoutRemote(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
  } catch {
    /* ignore network errors on logout */
  }
  clearAuth();
}
