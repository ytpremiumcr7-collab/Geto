import { useCallback, useEffect, useState } from "react";
import { ackAlert, fetchAlerts, resolveAlert, type GeofenceAlert } from "@/api/client";

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<GeofenceAlert[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetchAlerts("open");
      setAlerts(r.alerts || []);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  async function onAck(id: string) {
    setBusy(id);
    try {
      await ackAlert(id);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ack failed");
    } finally {
      setBusy(null);
    }
  }

  async function onResolve(id: string) {
    setBusy(id);
    try {
      await resolveAlert(id);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "resolve failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="panel">
      <h3>Alertas geofence</h3>
      {err && <p className="error">{err}</p>}
      {alerts.length === 0 && <p className="muted">Sin alertas abiertas</p>}
      <ul className="alert-list">
        {alerts.map((a) => (
          <li key={a.id} className={`alert sev-${a.severity}`}>
            <div>
              <strong>{a.event_type}</strong> · {a.entity_id}
              <br />
              <span className="muted">
                {a.severity} · {a.occurred_at?.slice(0, 19) || "—"}
              </span>
            </div>
            <div className="row gap">
              <button disabled={busy === a.id} onClick={() => onAck(a.id)}>
                Ack
              </button>
              <button disabled={busy === a.id} onClick={() => onResolve(a.id)}>
                Resolver
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
