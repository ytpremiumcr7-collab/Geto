const TOKEN_KEY = "geoint_token";
const USER_KEY = "geoint_user";

/** Prefer sessionStorage (cleared when tab closes) over localStorage for JWT. */
const store: Storage =
  typeof sessionStorage !== "undefined" ? sessionStorage : localStorage;

export type AuthUser = {
  access_token: string;
  token_type: string;
  expires_in: number;
  tenant_id: string;
  roles: string[];
};

function migrateFromLocalStorage() {
  try {
    const t = localStorage.getItem(TOKEN_KEY);
    const u = localStorage.getItem(USER_KEY);
    if (t && !store.getItem(TOKEN_KEY)) store.setItem(TOKEN_KEY, t);
    if (u && !store.getItem(USER_KEY)) store.setItem(USER_KEY, u);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

export function saveAuth(data: AuthUser) {
  migrateFromLocalStorage();
  store.setItem(TOKEN_KEY, data.access_token);
  store.setItem(USER_KEY, JSON.stringify(data));
}

export function clearAuth() {
  store.removeItem(TOKEN_KEY);
  store.removeItem(USER_KEY);
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

export function getToken(): string | null {
  migrateFromLocalStorage();
  return store.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  migrateFromLocalStorage();
  const raw = store.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}


export function setToken(token: string) {
  migrateFromLocalStorage();
  store.setItem(TOKEN_KEY, token);
}

export function setUser(user: { user_id?: string; tenant_id?: string; roles?: string[] }) {
  migrateFromLocalStorage();
  const prev = getUser();
  const merged = {
    access_token: prev?.access_token || getToken() || "",
    token_type: prev?.token_type || "bearer",
    expires_in: prev?.expires_in || 3600,
    tenant_id: user.tenant_id || prev?.tenant_id || "default",
    roles: user.roles || prev?.roles || [],
    user_id: user.user_id,
  };
  store.setItem(USER_KEY, JSON.stringify(merged));
}
