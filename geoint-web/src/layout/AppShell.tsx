import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { t, getLocale, setLocale, type Locale } from "@/i18n";

const nav = [
  { to: "/map", labelKey: "map" as const },
  { to: "/alerts", labelKey: "alerts" as const },
  { to: "/analytics", labelKey: "analytics" as const },
  { to: "/permissions", labelKey: "permissions" as const },
  { to: "/admin", labelKey: "admin" as const },
];

export function AppShell() {
  const { user, me, logout, loading } = useAuth();
  const navTo = useNavigate();
  const locale = getLocale();

  function onLocale(l: Locale) {
    setLocale(l);
    window.location.reload();
  }

  return (
    <div className="shell product-shell">
      <a href="#main-content" className="skip-link">
        {t("skipToNav")}
      </a>
      <header className="topbar product-topbar" role="banner">
        <div className="brand">
          <span className="logo-mark" aria-hidden />
          <span>{t("appName")}</span>
        </div>
        <nav className="product-nav" aria-label="Primary">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {t(item.labelKey)}
            </NavLink>
          ))}
        </nav>
        <div className="top-actions">
          <label className="locale-select">
            <span className="sr-only">Language</span>
            <select
              value={locale}
              onChange={(e) => onLocale(e.target.value as Locale)}
              aria-label="Language"
            >
              <option value="es">ES</option>
              <option value="en">EN</option>
            </select>
          </label>
          <span className="muted user-chip" title={me?.tenant_id}>
            {loading ? t("loading") : user?.user_id || "—"}
            {me?.roles?.length ? ` · ${me.roles.join(",")}` : ""}
          </span>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              logout();
              navTo("/login");
            }}
          >
            {t("logout")}
          </button>
        </div>
      </header>
      <div id="main-content" className="product-main" role="main">
        <Outlet />
      </div>
    </div>
  );
}
