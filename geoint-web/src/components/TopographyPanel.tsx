import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchDemAssets,
  fetchElevation,
  fetchLos,
  fetchProfile,
  fetchSlopePreview,
  type DemAsset,
  type ElevationResult,
  type LosResult,
  type ProfilePoint,
  type ProfileResult,
} from "@/api/client";

export type TopoMode = "idle" | "elev" | "profile" | "los";

type Props = {
  mode: TopoMode;
  onModeChange: (m: TopoMode) => void;
  /** Points collected from map clicks: [lon, lat][] */
  pickPoints: [number, number][];
  onClearPoints: () => void;
  profilePoints: ProfilePoint[];
  onProfileResult: (pts: ProfilePoint[], meta: ProfileResult | null) => void;
  losResult: LosResult | null;
  onLosResult: (r: LosResult | null) => void;
  onSlopeOverlay?: (ov: { url: string; bounds: [number, number, number, number] } | null) => void;
};

export function TopographyPanel({
  mode,
  onModeChange,
  pickPoints,
  onClearPoints,
  profilePoints,
  onProfileResult,
  losResult,
  onLosResult,
  onSlopeOverlay,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [elev, setElev] = useState<ElevationResult | null>(null);
  const [profile, setProfile] = useState<ProfileResult | null>(null);
  const [dems, setDems] = useState<DemAsset[]>([]);
  const [demId, setDemId] = useState<string>("");
  const [obsH, setObsH] = useState(1.7);
  const [tgtH, setTgtH] = useState(0);

  useEffect(() => {
    fetchDemAssets()
      .then((r) => setDems(r.dem_assets || []))
      .catch(() => setDems([]));
  }, []);

  const need =
    mode === "elev" ? 1 : mode === "profile" ? 2 : mode === "los" ? 2 : 0;

  const run = useCallback(async () => {
    if (pickPoints.length < need) return;
    setBusy(true);
    setErr(null);
    try {
      if (mode === "elev") {
        const [lon, lat] = pickPoints[0];
        const r = await fetchElevation(lat, lon, demId || undefined);
        setElev(r);
        onProfileResult([], null);
        onLosResult(null);
      } else if (mode === "profile") {
        const r = await fetchProfile(pickPoints, 25, demId || undefined);
        setProfile(r);
        setElev(null);
        onProfileResult(r.points || [], r);
        onLosResult(null);
      } else if (mode === "los") {
        const [oLon, oLat] = pickPoints[0];
        const [tLon, tLat] = pickPoints[1];
        const r = await fetchLos({
          observer_lon: oLon,
          observer_lat: oLat,
          target_lon: tLon,
          target_lat: tLat,
          observer_height_m: obsH,
          target_height_m: tgtH,
          dem_id: demId || undefined,
        });
        onLosResult(r);
        setElev(null);
        onProfileResult(r.profile || [], null);
        setProfile(null);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }, [mode, pickPoints, need, demId, obsH, tgtH, onProfileResult, onLosResult]);

  const chart = useMemo(() => {
    const pts = profilePoints.filter((p) => p.elevation_m != null);
    if (pts.length < 2) return null;
    const elevs = pts.map((p) => p.elevation_m as number);
    const minE = Math.min(...elevs);
    const maxE = Math.max(...elevs);
    const span = Math.max(maxE - minE, 1);
    const maxD = pts[pts.length - 1].distance_m || 1;
    const w = 280;
    const h = 80;
    const poly = pts
      .map((p, i) => {
        const x = (p.distance_m / maxD) * (w - 4) + 2;
        const y = h - 4 - ((p.elevation_m! - minE) / span) * (h - 8);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
    return { poly, minE, maxE, maxD, w, h };
  }, [profilePoints]);

  return (
    <div className="panel topo-panel">
      <div className="panel-head">
        <span>TOPOGRAFÍA</span>
        <span className="muted">{mode === "idle" ? "—" : mode}</span>
      </div>
      <div className="panel-body topo-body">
        <div className="topo-modes">
          {(
            [
              ["elev", "Elevación"],
              ["profile", "Perfil"],
              ["los", "LOS"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              className={`topo-mode-btn ${mode === m ? "active" : ""}`}
              onClick={() => {
                onModeChange(m);
                onClearPoints();
                setElev(null);
                setProfile(null);
                onLosResult(null);
                onProfileResult([], null);
              }}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            className="topo-mode-btn"
            onClick={() => {
              onModeChange("idle");
              onClearPoints();
              setElev(null);
              setProfile(null);
              onLosResult(null);
              onProfileResult([], null);
            }}
          >
            ✕
          </button>
        </div>

        {mode !== "idle" && (
          <div className="topo-hint muted">
            {mode === "elev" && "Click en el mapa (1 punto)"}
            {mode === "profile" && "Click A → B en el mapa (≥2 puntos)"}
            {mode === "los" && "Click observador → objetivo"}
            {pickPoints.length > 0 && (
              <span>
                {" "}
                · {pickPoints.length}/{need || "…"} pts
              </span>
            )}
          </div>
        )}

        {dems.length > 0 && mode !== "idle" && (
          <label className="topo-field">
            <span>DEM</span>
            <select
              value={demId}
              onChange={(e) => setDemId(e.target.value)}
            >
              <option value="">Auto / Terrarium</option>
              {dems.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.provider} · {d.product_name} ({d.resolution_m}m)
                </option>
              ))}
            </select>
          </label>
        )}

        {mode === "los" && (
          <div className="topo-heights">
            <label>
              h obs (m)
              <input
                type="number"
                step="0.1"
                value={obsH}
                onChange={(e) => setObsH(Number(e.target.value))}
              />
            </label>
            <label>
              h tgt (m)
              <input
                type="number"
                step="0.1"
                value={tgtH}
                onChange={(e) => setTgtH(Number(e.target.value))}
              />
            </label>
          </div>
        )}

        {mode !== "idle" && (
          <div className="topo-actions">
            <button
              type="button"
              className="topo-run"
              disabled={busy || pickPoints.length < need}
              onClick={run}
            >
              {busy ? "Calculando…" : "Calcular"}
            </button>
            <button type="button" className="ghost" onClick={onClearPoints}>
              Limpiar pts
            </button>
          </div>
        )}

        {demId && onSlopeOverlay && (
          <button
            type="button"
            className="topo-run"
            style={{ background: "linear-gradient(135deg, #c792ea, #5b9cff)" }}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setErr(null);
              try {
                const prev = await fetchSlopePreview(demId);
                onSlopeOverlay({ url: prev.objectUrl, bounds: prev.bounds });
              } catch (e) {
                setErr(e instanceof Error ? e.message : "slope error");
              } finally {
                setBusy(false);
              }
            }}
          >
            Overlay slope
          </button>
        )}


        {err && <div className="topo-err">{err}</div>}

        {elev && (
          <div className="topo-result">
            <div className="topo-elev">
              {elev.elevation_m != null
                ? `${elev.elevation_m.toFixed(1)} m`
                : "—"}
            </div>
            <div className="muted small">
              {elev.provider}
              {elev.product_name ? ` · ${elev.product_name}` : ""}
              {elev.resolution_m != null ? ` · ${elev.resolution_m} m` : ""}
            </div>
            {elev.note && <div className="muted small">{elev.note}</div>}
          </div>
        )}

        {losResult && (
          <div className="topo-result">
            <div
              className={`topo-los-badge ${losResult.visible ? "ok" : "blocked"}`}
            >
              {losResult.visible ? "VISIBLE" : "OBSTRUIDO"}
            </div>
            {!losResult.visible &&
              losResult.obstruction_distance_m != null && (
                <div className="muted small">
                  Obstrucción a{" "}
                  {losResult.obstruction_distance_m.toFixed(0)} m
                </div>
              )}
            <div className="muted small">
              {losResult.provider}
              {losResult.note ? ` · ${losResult.note}` : ""}
            </div>
          </div>
        )}

        {chart && (
          <div className="topo-chart">
            <svg width={chart.w} height={chart.h} className="topo-svg">
              <path d={chart.poly} fill="none" stroke="#3dd6c6" strokeWidth="1.5" />
            </svg>
            <div className="topo-chart-labels muted small">
              <span>{chart.minE.toFixed(0)} m</span>
              <span>{(chart.maxD / 1000).toFixed(2)} km</span>
              <span>{chart.maxE.toFixed(0)} m</span>
            </div>
          </div>
        )}

        {profile && (
          <div className="muted small">
            Perfil · {profile.total_distance_m.toFixed(0)} m · {profile.provider}
            {profile.resolution_m != null
              ? ` · ${profile.resolution_m} m`
              : ""}
          </div>
        )}
      </div>
    </div>
  );
}
