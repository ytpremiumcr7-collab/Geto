import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { issueToken } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { t } from "@/i18n";

export function Login() {
  const nav = useNavigate();
  const { login } = useAuth();
  const [userId, setUserId] = useState("operator1");
  const [tenantId, setTenantId] = useState("default");
  const [roles, setRoles] = useState("operator,admin");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
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

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={onSubmit} aria-labelledby="login-title">
        <div className="brand">
          <span className="logo-mark" aria-hidden />
          <h1 id="login-title">{t("appName")}</h1>
        </div>
        <p className="muted">{t("signInHint")}</p>
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
