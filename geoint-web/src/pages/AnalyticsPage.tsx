import { useCallback, useEffect, useState } from "react";
import {
  fetchAnalyticsQuery,
  fetchAnalyticsTemplates,
} from "@/api/client";
import { t } from "@/i18n";

export function AnalyticsPage() {
  const [enabled, setEnabled] = useState(false);
  const [templates, setTemplates] = useState<Array<{ id: string; description: string }>>([]);
  const [rows, setRows] = useState<unknown[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchAnalyticsTemplates()
      .then((r) => {
        setEnabled(r.enabled);
        setTemplates(r.templates || []);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : "error"));
  }, []);

  const run = useCallback(async (id: string) => {
    setBusy(true);
    setActive(id);
    setErr(null);
    try {
      const r = await fetchAnalyticsQuery(id);
      setEnabled(r.enabled);
      setRows(r.rows || []);
      if (r.error) setErr(r.error);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="page-pad analytics-page">
      <h1>{t("analytics")}</h1>
      {!enabled && <p className="muted">{t("analyticsDisabled")}</p>}
      {err && <p className="error-text">{err}</p>}
      <div className="template-list">
        {templates.map((tpl) => (
          <button
            key={tpl.id}
            type="button"
            className={active === tpl.id ? "primary" : "ghost"}
            disabled={busy}
            onClick={() => run(tpl.id)}
          >
            {t("runQuery")}: {tpl.id}
          </button>
        ))}
      </div>
      {rows.length > 0 && (
        <pre className="code-block" tabIndex={0}>
          {JSON.stringify(rows, null, 2)}
        </pre>
      )}
    </div>
  );
}
