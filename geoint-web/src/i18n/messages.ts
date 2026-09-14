export type Locale = "es" | "en";

const es = {
  appName: "GEOINT Platform",
  login: "Iniciar sesión",
  logout: "Salir",
  admin: "Admin",
  sources: "Fuentes",
  observations: "Observaciones",
  alerts: "Alertas geofence",
  workspaces: "Workspaces / AOI",
  ack: "Ack",
  resolve: "Resolver",
  noOpenAlerts: "Sin alertas abiertas",
  skipToMap: "Saltar al mapa",
  skipToNav: "Saltar a navegación",
  apiStatus: "Estado API",
  permissions: "Permisos",
  loading: "Cargando…",
  errorGeneric: "Error",
  create: "Crear",
  enable: "Habilitar",
  disable: "Deshabilitar",
} as const;

const en: { [K in keyof typeof es]: string } = {
  appName: "GEOINT Platform",
  login: "Sign in",
  logout: "Sign out",
  admin: "Admin",
  sources: "Sources",
  observations: "Observations",
  alerts: "Geofence alerts",
  workspaces: "Workspaces / AOI",
  ack: "Ack",
  resolve: "Resolve",
  noOpenAlerts: "No open alerts",
  skipToMap: "Skip to map",
  skipToNav: "Skip to navigation",
  apiStatus: "API status",
  permissions: "Permissions",
  loading: "Loading…",
  errorGeneric: "Error",
  create: "Create",
  enable: "Enable",
  disable: "Disable",
};

const catalogs: Record<Locale, typeof es> = { es, en };

let current: Locale = (typeof localStorage !== "undefined" &&
  (localStorage.getItem("geoint_locale") as Locale)) || "es";

export function getLocale(): Locale {
  return current;
}

export function setLocale(locale: Locale) {
  current = locale;
  try {
    localStorage.setItem("geoint_locale", locale);
  } catch {
    /* ignore */
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale;
  }
}

export function t(key: keyof typeof es): string {
  return catalogs[current][key] ?? catalogs.es[key] ?? key;
}
