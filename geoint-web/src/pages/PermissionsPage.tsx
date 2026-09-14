import { useAuth } from "@/auth/AuthContext";
import { t } from "@/i18n";

export function PermissionsPage() {
  const { me, loading } = useAuth();

  if (loading) return <p className="page-pad muted">{t("loading")}</p>;
  if (!me) return <p className="page-pad muted">{t("errorGeneric")}</p>;

  return (
    <div className="page-pad permissions-page">
      <h1>{t("permissions")}</h1>
      <section>
        <h2>{t("yourRoles")}</h2>
        <ul className="chip-list">
          {me.roles.map((r) => (
            <li key={r} className="chip">
              {r}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>{t("yourPermissions")}</h2>
        <ul className="perm-list">
          {me.permissions.length === 0 && <li className="muted">{t("noPermission")}</li>}
          {me.permissions.map((p) => (
            <li key={p}>
              <code>{p}</code>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>{t("sourceAccess")}</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("sources")}</th>
              <th>{t("canRead")}</th>
              <th>{t("canAdmin")}</th>
              <th>Policy</th>
            </tr>
          </thead>
          <tbody>
            {me.sources.map((s) => (
              <tr key={s.source_id}>
                <td>
                  <code>{s.source_id}</code>
                </td>
                <td>{s.can_read ? "✓" : "—"}</td>
                <td>{s.can_admin ? "✓" : "—"}</td>
                <td>{s.access_policy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
