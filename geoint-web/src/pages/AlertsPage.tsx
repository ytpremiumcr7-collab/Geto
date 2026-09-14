import { AlertsPanel } from "@/components/AlertsPanel";
import { t } from "@/i18n";

export function AlertsPage() {
  return (
    <div className="page-pad alerts-page">
      <h1>{t("alerts")}</h1>
      <p className="muted">
        Regla → alerta → ack/silence → entregas (webhook / SMTP / log). Worker:{" "}
        <code>python -m app.workers.alert_notifier</code>
      </p>
      <div className="panel-card">
        <AlertsPanel />
      </div>
    </div>
  );
}
