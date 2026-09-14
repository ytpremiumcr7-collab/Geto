import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchAdminJobs,
  fetchDlq,
  patchAdminJob,
  requeueDlq,
  type AdminJob,
  type DlqItem,
} from "@/api/client";
import { getUser } from "@/lib/auth";
import { AlertsPanel } from "@/components/AlertsPanel";

export function Admin() {
  const user = getUser();
  const isAdmin = user?.roles?.includes("admin");
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [dlq, setDlq] = useState<DlqItem[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const [j, d] = await Promise.all([fetchAdminJobs(), fetchDlq("open")]);
      setJobs(j.jobs || []);
      setDlq(d.items || []);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    }
  }, [isAdmin]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  async function toggleJob(job: AdminJob) {
    setBusy(job.id);
    try {
      await patchAdminJob(job.id, { enabled: !job.enabled });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "patch failed");
    } finally {
      setBusy(null);
    }
  }

  async function onRequeue(id: string) {
    setBusy(id);
    try {
      await requeueDlq(id);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "requeue failed");
    } finally {
      setBusy(null);
    }
  }

  if (!isAdmin) {
    return (
      <div className="page">
        <p>Se requiere rol admin.</p>
        <Link to="/">Volver al mapa</Link>
      </div>
    );
  }

  return (
    <div className="page admin-page">
      <header className="row between">
        <h2>Admin · fuentes / jobs / DLQ</h2>
        <Link to="/">← Mapa</Link>
      </header>
      {err && <p className="error">{err}</p>}

      <section>
        <h3>Source jobs</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Fuente</th>
              <th>Nombre</th>
              <th>Estado</th>
              <th>Intervalo</th>
              <th>Último OK</th>
              <th>Error</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.source_id}</td>
                <td>{j.name}</td>
                <td>{j.status}</td>
                <td>{j.interval_seconds}s</td>
                <td>{j.last_success_at?.slice(0, 19) || "—"}</td>
                <td className="error">{j.last_error?.slice(0, 80) || ""}</td>
                <td>
                  <button disabled={busy === j.id} onClick={() => toggleJob(j)}>
                    {j.enabled ? "Deshabilitar" : "Habilitar"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>DLQ abierta</h3>
        {dlq.length === 0 && <p className="muted">Vacía</p>}
        <ul className="simple-list">
          {dlq.map((d) => (
            <li key={d.id} className="row between">
              <span>
                <strong>{d.source_id}</strong> · {d.error?.slice(0, 120)}
              </span>
              <button disabled={busy === d.id} onClick={() => onRequeue(d.id)}>
                Requeue
              </button>
            </li>
          ))}
        </ul>
      </section>

      <AlertsPanel />
    </div>
  );
}
