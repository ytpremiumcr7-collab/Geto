import type { LiveEvent } from "@/hooks/useLiveEvents";

type Props = {
  events: LiveEvent[];
  connected: boolean;
};

export function EventsFeed({ events, connected }: Props) {
  return (
    <div className="panel events-panel">
      <div className="panel-header">
        <span>LIVE</span>
        <span className={`live-dot ${connected ? "on" : "off"}`} />
      </div>
      <div className="panel-body feed">
        {events.length === 0 && (
          <div className="muted empty">Esperando eventos NATS…</div>
        )}
        {events.map((e, i) => (
          <div key={i} className="event-row">
            <div className="event-type">
              {String(e.event_type || e.type || "event")}
            </div>
            <div className="event-meta">
              {e.entity_id || e.source_id || "—"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
