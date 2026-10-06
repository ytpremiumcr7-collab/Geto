import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchOidcStatus, issueToken } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { t } from "@/i18n";

type LoginMode = "loading" | "oidc" | "development" | "unavailable";

export function Login() {
  const nav = useNavigate();
  const { login } = useAuth();
  const [mode, setMode] = useState<LoginMode>("loading");
  const [userId, setUserId] = useState("operator1");
  const [tenantId, setTenantId] = useState("default");
  const [roles, setRoles] = useState("operator");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void fetchOidcStatus()
      .then((status) => {
        if (!active) return;
        if (status.enabled) setMode("oidc");
        else if (status.development_bootstrap) setMode("development");
        else setMode("unavailable");
      })
      .catch(() => {
        if (active) setMode("unavailable");
      });
    return () => {
      active = false;
    };
  }, []);

  function beginOidc() {
    const returnTo = encodeURIComponent("/onboarding");
    window.location.assign(`/api/v1/auth/oidc/start?return_to=${returnTo}`);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (mode !== "development") return;
    setBusy(true);
    setErr(null);
    try {
      const roleList = roles
        .split(",")
        .map((r) => r.trim())
        .filter(Boolean);
      const tok = await issueToken({
        user_id: userId,
        tenant_id: tenantId,
        roles: roleList,
      });
      await login(tok.access_token, {
        user_id: userId,
        tenant_id: tenantId,
        roles: roleList,
      });
      nav("/onboarding", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : t("errorGeneric"));
    } finally {
      setBusy(false);
    }
  }

  if (mode === "loading") {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="brand">
            <span className="logo-mark" aria-hidden />
            <h1>{t("appName")}</h1>
          </div>
          <p className="muted">{t("loading")}</p>
        </div>
      </div>
    );
  }

  if (mode === "oidc") {
    return (
      <div className="login-page">
        <div className="login-card" aria-labelledby="login-title">
          <div className="brand">
            <span className="logo-mark" aria-hidden />
            <h1 id="login-title">{t("appName")}</h1>
          </div>
          <p className="muted">Acceso institucional seguro</p>
          <button type="button" className="primary" onClick={beginOidc}>
            Iniciar sesión con SSO
          </button>
        </div>
      </div>
    );
  }

  if (mode === "unavailable") {
    return (
      <div className="login-page">
        <div className="login-card" aria-labelledby="login-title">
          <div className="brand">
            <span className="logo-mark" aria-hidden />
            <h1 id="login-title">{t("appName")}</h1>
          </div>
          <p className="error-text" role="alert">
            El inicio de sesión institucional no está configurado. El servidor
            debe habilitar OIDC antes de aceptar usuarios.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={onSubmit} aria-labelledby="login-title">
        <div className="brand">
          <span className="logo-mark" aria-hidden />
          <h1 id="login-title">{t("appName")}</h1>
        </div>
        <p className="muted">Bootstrap local de desarrollo</p>
        <label>
          {t("userId")}
          <input value={userId} onChange={(e) => setUserId(e.target.value)} required autoComplete="username" />
        </label>
        <label>
          {t("tenantId")}
          <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} required />
        </label>
        <label>
          {t("roles")}
          <input value={roles} onChange={(e) => setRoles(e.target.value)} required />
        </label>
        {err && (
          <p className="error-text" role="alert">
            {err}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy}>
          {busy ? t("loading") : t("getToken")}
        </button>
      </form>
    </div>
  );
}
