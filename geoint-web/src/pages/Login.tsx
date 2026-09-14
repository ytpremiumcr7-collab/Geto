import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { issueToken } from "@/api/client";
import { saveAuth } from "@/lib/auth";

const ROLE_PRESETS: Record<string, string[]> = {
  admin: ["admin"],
  operator: ["operator"],
  goodmode: ["goodmode"],
};

export function Login() {
  const nav = useNavigate();
  const [userId, setUserId] = useState("ops-1");
  const [tenantId, setTenantId] = useState("default");
  const [preset, setPreset] = useState("operator");
  const [bootstrap, setBootstrap] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const roles = ROLE_PRESETS[preset] || ["operator"];
      const data = await issueToken({
        user_id: userId,
        tenant_id: tenantId,
        roles,
        bootstrap_secret: bootstrap || undefined,
      });
      saveAuth({
        access_token: data.access_token,
        token_type: data.token_type || "bearer",
        expires_in: 3600,
        tenant_id: tenantId,
        roles,
      });
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="dev-banner" role="status">
          DEV: emite JWT de bootstrap (roles elegidos). Producción = OIDC / IdP, no este formulario.
        </div>
        <div className="login-brand">
          <div className="logo-mark" />
          <h1>GEOINT</h1>
          <p>Intelligence platform · open sources</p>
        </div>
        <form onSubmit={onSubmit}>
          <label>
            User ID
            <input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            Tenant
            <input
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            />
          </label>
          <label>
            Rol
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value)}
              style={{
                width: "100%",
                marginTop: 6,
                padding: "10px 12px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--bg)",
                color: "var(--text)",
              }}
            >
              <option value="operator">operator</option>
              <option value="admin">admin</option>
              <option value="goodmode">goodmode (OpenSky read)</option>
            </select>
          </label>
          <label>
            Bootstrap secret (prod)
            <input
              type="password"
              value={bootstrap}
              onChange={(e) => setBootstrap(e.target.value)}
              placeholder="solo si app_env ≠ development"
            />
          </label>
          {error && <div className="error">{error}</div>}
          <button type="submit" disabled={loading}>
            {loading ? "…" : "Entrar"}
          </button>
        </form>
        <p className="login-hint">
          POST /api/v1/auth/token · JWT HS256
        </p>
      </div>
    </div>
  );
}
