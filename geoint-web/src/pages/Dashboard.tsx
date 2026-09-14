import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createGeofence,
  fetchGeofences,
  fetchLive,
  fetchObservations,
  fetchReady,
  fetchSources,
  fetchTrack,
  type GeofenceRow,
  type Observation,
  type SourceRow,
  type TrackPoint,
} from "@/api/client";
import { clearAuth, getUser } from "@/lib/auth";
import { MapView } from "@/components/MapView";
import { SourcesPanel } from "@/components/SourcesPanel";
import { EventsFeed } from "@/components/EventsFeed";
import { TimeFilter } from "@/components/TimeFilter";
import { GeofencesPanel } from "@/components/GeofencesPanel";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { TopographyPanel, type TopoMode } from "@/components/TopographyPanel";
import type { LosResult, ProfilePoint } from "@/api/client";

export function Dashboard() {
  const nav = useNavigate();
  const user = getUser();
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [geofences, setGeofences] = useState<GeofenceRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [entityId, setEntityId] = useState<string | null>(null);
  const [track, setTrack] = useState<TrackPoint[]>([]);
  const [trackIdx, setTrackIdx] = useState(0);
  const [hours, setHours] = useState<number | null>(24);
  const [status, setStatus] = useState("loading");
  const [ready, setReady] = useState("…");
  const [drawMode, setDrawMode] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [topoMode, setTopoMode] = useState<TopoMode>("idle");
  const [topoPicks, setTopoPicks] = useState<[number, number][]>([]);
  const [topoProfile, setTopoProfile] = useState<ProfilePoint[]>([]);
  const [topoLos, setTopoLos] = useState<LosResult | null>(null);
  const [slopeOverlay, setSlopeOverlay] = useState<{ url: string; bounds: [number, number, number, number] } | null>(null);
  const { events, connected } = useLiveEvents(true);

  const sinceIso = useMemo(() => {
    if (hours == null) return undefined;
    return new Date(Date.now() - hours * 3600_000).toISOString();
  }, [hours]);

  const load = useCallback(async () => {
    try {
      const [src, obs, geo] = await Promise.all([
        fetchSources(),
        fetchObservations({
          source_id: selected || undefined,
          since: sinceIso,
          limit: 300,
        }),
        fetchGeofences().catch(() => ({ geofences: [] as GeofenceRow[] })),
      ]);
      setSources(src.sources || []);
      setObservations(obs.observations || []);
      setGeofences(geo.geofences || []);
      setStatus("ok");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "error");
    }
  }, [selected, sinceIso]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetchReady();
        setReady(r.status);
      } catch {
        try {
          await fetchLive();
          setReady("live-only");
        } catch {
          setReady("down");
        }
      }
    })();
  }, []);

  useEffect(() => {
    if (!entityId) {
      setTrack([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchTrack(entityId, 300);
        if (!cancelled) {
          setTrack(res.track || []);
          setTrackIdx(Math.max(0, (res.track?.length || 1) - 1));
        }
      } catch {
        if (!cancelled) setTrack([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  const trackVisible = useMemo(() => {
    if (!track.length) return [];
    return track.slice(0, trackIdx + 1);
  }, [track, trackIdx]);

  async function onPolygonComplete(coords: [number, number][]) {
    const name = window.prompt("Nombre del geofence");
    if (!name) {
      setDrawMode(false);
      return;
    }
    try {
      await createGeofence({
        name,
        geometry: { type: "Polygon", coordinates: [coords] },
      });
      setMsg(`Geofence «${name}» creado`);
      setDrawMode(false);
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Error creando geofence");
      setDrawMode(false);
    }
  }

  function logout() {
    clearAuth();
    nav("/login");
  }

  const withCoords = observations.filter((o) => o.lon != null && o.lat != null);

  const onTopoPick = useCallback((pt: [number, number]) => {
    setTopoPicks((prev) => {
      if (topoMode === "elev") return [pt];
      if (topoMode === "los") return prev.length >= 2 ? [pt] : [...prev, pt].slice(0, 2);
      // profile: accumulate
      return [...prev, pt];
    });
  }, [topoMode]);

  const topoLosOverlay = useMemo(() => {
    if (!topoLos) return null;
    return {
      observer: [topoLos.observer.lon, topoLos.observer.lat] as [number, number],
      target: [topoLos.target.lon, topoLos.target.lat] as [number, number],
      obstruction:
        topoLos.obstruction_lon != null && topoLos.obstruction_lat != null
          ? ([topoLos.obstruction_lon, topoLos.obstruction_lat] as [number, number])
          : null,
      visible: topoLos.visible,
    };
  }, [topoLos]);

  const topoProfileCoords = useMemo(
    () =>
      topoProfile
        .filter((p) => p.lon != null && p.lat != null)
        .map((p) => [p.lon, p.lat] as [number, number]),
    [topoProfile]
  );


  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="logo-mark sm" />
          <span>GEOINT</span>
          <span className="muted mono">platform</span>
        </div>
        <TimeFilter hours={hours} onChange={setHours} />
        <div className="top-stats">
          <span className="stat">
            <em>{withCoords.length}</em> on map
          </span>
          <span className="stat">
            <em>{sources.filter((s) => s.available !== false).length}</em> sources
          </span>
          <span className="stat">
            <em>{geofences.length}</em> fences
          </span>
          <span className={`stat live ${connected ? "on" : ""}`}>
            WS {connected ? "LIVE" : "OFF"}
          </span>
          <span className="stat mono">API {ready}</span>
        </div>
        <div className="user-chip">
          <button
            type="button"
            className={`ghost ${drawMode ? "active-draw" : ""}`}
            onClick={() => setDrawMode((d) => !d)}
          >
            {drawMode ? "Dibujando…" : "Geofence"}
          </button>
          <span className="mono">{user?.tenant_id || "—"}</span>
          <span className="muted">{(user?.roles || []).join(", ")}</span>
          <button type="button" className="ghost" onClick={logout}>
            Salir
          </button>
        </div>
      </header>

      <div className="workspace">
        <aside className="left">
          <SourcesPanel
            sources={sources}
            selected={selected}
            onSelect={setSelected}
          />
          <TopographyPanel
            mode={topoMode}
            onModeChange={setTopoMode}
            pickPoints={topoPicks}
            onClearPoints={() => setTopoPicks([])}
            profilePoints={topoProfile}
            onProfileResult={(pts, _meta) => setTopoProfile(pts)}
            losResult={topoLos}
            onLosResult={setTopoLos}
            onSlopeOverlay={setSlopeOverlay}
          />
          <GeofencesPanel geofences={geofences} />
        </aside>

        <main className="map-stage">
          <MapView
            observations={observations}
            geofences={geofences}
            track={trackVisible}
            selectedEntityId={entityId}
            drawMode={drawMode}
            onPolygonComplete={onPolygonComplete}
            onSelectEntity={setEntityId}
            topoMode={topoMode}
            topoPickPoints={topoPicks}
            onTopoPick={onTopoPick}
            topoProfileCoords={topoProfileCoords}
            topoLos={topoLosOverlay}
            slopeOverlay={slopeOverlay}
          />
          {status !== "ok" && status !== "loading" && (
            <div className="map-banner error">{status}</div>
          )}
          {status === "loading" && (
            <div className="map-banner">Conectando API…</div>
          )}
          {msg && (
            <div className="map-banner" onClick={() => setMsg(null)}>
              {msg}
            </div>
          )}
          {drawMode && (
            <div className="map-banner">
              Clicks = vértices · doble-click = guardar en API
            </div>
          )}
          {topoMode !== "idle" && !drawMode && (
            <div className="map-banner topo">
              Topografía · modo {topoMode} · click en el mapa
            </div>
          )}
          {entityId && track.length > 0 && (
            <div className="timeline-bar">
              <span className="mono track-label">{entityId}</span>
              <input
                type="range"
                min={0}
                max={Math.max(0, track.length - 1)}
                value={trackIdx}
                onChange={(e) => setTrackIdx(Number(e.target.value))}
              />
              <span className="mono muted">
                {track[trackIdx]?.observed_at?.slice(0, 19) || "—"}
              </span>
              <button type="button" className="ghost" onClick={() => setEntityId(null)}>
                Clear
              </button>
            </div>
          )}
        </main>

        <aside className="right">
          <EventsFeed events={events} connected={connected} />
          <div className="panel obs-panel">
            <div className="panel-header">
              <span>OBSERVATIONS</span>
              <span className="muted">{observations.length}</span>
            </div>
            <div className="panel-body feed">
              {observations.length === 0 && (
                <div className="muted empty">
                  Sin datos en este rango — cambia filtro o ingerir fuentes
                </div>
              )}
              {observations.slice(0, 40).map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className={`obs-row clickable ${entityId === o.entity_id ? "selected" : ""}`}
                  onClick={() => setEntityId(o.entity_id)}
                >
                  <div className="obs-id">{o.entity_id}</div>
                  <div className="obs-meta">
                    {o.entity_type} · {o.source_id}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
