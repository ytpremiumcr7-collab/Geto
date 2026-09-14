export type Locale = "es" | "en";

const es = {
  appName: "GEOINT Platform",
  login: "Iniciar sesión",
  logout: "Salir",
  admin: "Admin",
  sources: "Fuentes",
  observations: "Observaciones",
  alerts: "Alertas",
  workspaces: "Workspaces / AOI",
  ack: "Ack",
  resolve: "Resolver",
  noOpenAlerts: "Sin alertas abiertas",
  skipToMap: "Saltar al mapa",
  skipToNav: "Saltar al contenido",
  apiStatus: "Estado API",
  permissions: "Permisos",
  loading: "Cargando…",
  errorGeneric: "Error",
  create: "Crear",
  enable: "Habilitar",
  disable: "Deshabilitar",
  map: "Mapa",
  analytics: "Analytics",
  onboarding: "Primeros pasos",
  onboardingTitle: "Bienvenido a GEOINT",
  onboardingBody:
    "1) Revisa tus permisos por fuente. 2) Abre el mapa y observa entidades. 3) Crea un geofence y canal de alerta. 4) Consulta analytics si ClickHouse está habilitado.",
  continueToMap: "Ir al mapa",
  yourRoles: "Tus roles",
  yourPermissions: "Permisos efectivos",
  sourceAccess: "Acceso por fuente",
  canRead: "Lectura",
  canAdmin: "Admin",
  noPermission: "Sin acceso",
  analyticsDisabled: "ClickHouse deshabilitado o sin datos",
  runQuery: "Ejecutar",
  deliveries: "Entregas",
  channels: "Canales",
  signInHint: "Token de desarrollo o IdP (OIDC) en producción",
  userId: "Usuario",
  tenantId: "Tenant",
  roles: "Roles",
  getToken: "Obtener token",
} as const;

const en: { [K in keyof typeof es]: string } = {
  appName: "GEOINT Platform",
  login: "Sign in",
  logout: "Sign out",
  admin: "Admin",
  sources: "Sources",
  observations: "Observations",
  alerts: "Alerts",
  workspaces: "Workspaces / AOI",
  ack: "Ack",
  resolve: "Resolve",
  noOpenAlerts: "No open alerts",
  skipToMap: "Skip to map",
  skipToNav: "Skip to content",
  apiStatus: "API status",
  permissions: "Permissions",
  loading: "Loading…",
  errorGeneric: "Error",
  create: "Create",
  enable: "Enable",
  disable: "Disable",
  map: "Map",
  analytics: "Analytics",
  onboarding: "Getting started",
  onboardingTitle: "Welcome to GEOINT",
  onboardingBody:
    "1) Review source permissions. 2) Open the map and watch entities. 3) Create a geofence and alert channel. 4) Use analytics when ClickHouse is enabled.",
  continueToMap: "Go to map",
  yourRoles: "Your roles",
  yourPermissions: "Effective permissions",
  sourceAccess: "Access by source",
  canRead: "Read",
  canAdmin: "Admin",
  noPermission: "No access",
  analyticsDisabled: "ClickHouse disabled or empty",
  runQuery: "Run",
  deliveries: "Deliveries",
  channels: "Channels",
  signInHint: "Dev token or IdP (OIDC) in production",
  userId: "User",
  tenantId: "Tenant",
  roles: "Roles",
  getToken: "Get token",
};

const catalogs: Record<Locale, typeof es> = { es, en };

let current: Locale =
  (typeof localStorage !== "undefined" &&
    (localStorage.getItem("geoint_locale") as Locale)) ||
  "es";

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
