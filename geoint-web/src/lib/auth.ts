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
