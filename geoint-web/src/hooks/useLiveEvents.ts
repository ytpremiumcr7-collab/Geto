import { useEffect, useRef, useState } from "react";
import { getToken } from "@/lib/auth";

export type LiveEvent = {
  type?: string;
  event_type?: string;
  entity_id?: string;
  source_id?: string;
  tenant_id?: string;
  occurred_at?: string;
  data?: Record<string, unknown>;
  [key: string]: unknown;
};

/** Conecta a /ws/events y autentica con mensaje {type:auth,token} (sin token en URL). */
export function useLiveEvents(enabled: boolean) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const token = getToken();
    if (!token) return;

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const url = `${proto}://${host}/ws/events`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "auth", token }));
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as LiveEvent;
        if (data.type === "auth_ok") {
          setConnected(true);
          return;
        }
        if (data.type === "ack") return;
        setEvents((prev) => [data, ...prev].slice(0, 80));
      } catch {
        /* ignore */
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [enabled]);

  return { events, connected };
}
