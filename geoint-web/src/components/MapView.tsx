import { useEffect, useRef, useState } from "react";
import maplibregl, { Map, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { GeofenceRow, Observation, TrackPoint } from "@/api/client";
import { fetchFirmsWms } from "@/api/client";

/** Carto dark + DEM Terrarium + opcional NASA GIBS (sin API key). */
const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution: "© OpenStreetMap © CARTO",
    },
    terrainSource: {
      type: "raster-dem",
      tiles: [
        "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
      ],
      encoding: "terrarium",
      tileSize: 256,
      maxzoom: 15,
    },
    hillshadeSource: {
      type: "raster-dem",
      tiles: [
        "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
      ],
      encoding: "terrarium",
      tileSize: 256,
      maxzoom: 15,
    },
    /** NASA GIBS Blue Marble — sin registro */
    gibs: {
      type: "raster",
      tiles: [
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpg",
      ],
      tileSize: 256,
      maxzoom: 8,
      attribution: "NASA GIBS / Blue Marble",
    },
    /** NASA GIBS VIIRS True Color (día reciente genérico — capa estática de matriz) */
    gibs_viirs: {
      type: "raster",
      tiles: [
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
      ],
      tileSize: 256,
      maxzoom: 9,
      attribution: "NASA GIBS / VIIRS",
    },
  },
  layers: [
    { id: "carto", type: "raster", source: "carto" },
    {
      id: "hillshade",
      type: "hillshade",
      source: "hillshadeSource",
      paint: {
        "hillshade-shadow-color": "#0a1018",
        "hillshade-highlight-color": "#c8d6e5",
        "hillshade-exaggeration": 0.45,
      },
    },
  ],
};

const TYPE_COLOR: Record<string, string> = {
  aircraft: "#5b9cff",
  vessel: "#3dd6c6",
  radar_site: "#c792ea",
  satellite_weather: "#ffcb6b",
  earthquake: "#f07178",
  fire: "#ff8b4d",
  ephemeris_body: "#82aaff",
  sensor: "#c3e88d",
  unknown: "#8b9bb0",
};

type TopoPickMode = "idle" | "elev" | "profile" | "los";

type Props = {
  observations: Observation[];
  geofences: GeofenceRow[];
  track: TrackPoint[];
  selectedEntityId: string | null;
  drawMode: boolean;
  onPolygonComplete?: (coords: [number, number][]) => void;
  onSelectEntity?: (entityId: string) => void;
  center?: [number, number];
  zoom?: number;
  /** Topography interactive mode */
  topoMode?: TopoPickMode;
  topoPickPoints?: [number, number][];
  onTopoPick?: (pt: [number, number]) => void;
  topoProfileCoords?: [number, number][];
  topoLos?: {
    observer: [number, number];
    target: [number, number];
    obstruction?: [number, number] | null;
    visible?: boolean;
  } | null;
  /** Slope PNG overlay: object URL + [w,s,e,n] */
  slopeOverlay?: { url: string; bounds: [number, number, number, number] } | null;
};

export function MapView({
  observations,
  geofences,
  track,
  selectedEntityId,
  drawMode,
  onPolygonComplete,
  onSelectEntity,
  center = [-99.13, 19.43],
  zoom = 4.2,
  topoMode = "idle",
  topoPickPoints = [],
  onTopoPick,
  topoProfileCoords = [],
  topoLos = null,
  slopeOverlay = null,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const drawPts = useRef<[number, number][]>([]);
  const [pitch3d, setPitch3d] = useState(true);
  const [terrainOn, setTerrainOn] = useState(true);
  const [gibs, setGibs] = useState<"off" | "marble" | "viirs">("off");
  const [firmsOn, setFirmsOn] = useState(false);
  const [firmsUrl, setFirmsUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: BASE_STYLE,
      center,
      zoom,
      pitch: 50,
      bearing: -12,
      maxPitch: 80,
      attributionControl: { compact: true },
    });
    map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true }),
      "top-right"
    );
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120 }));

    map.on("load", () => {
      try {
        map.setTerrain({ source: "terrainSource", exaggeration: 1.35 });
      } catch {
        /* optional */
      }

      map.addSource("geofences", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "geofences-fill",
        type: "fill",
        source: "geofences",
        paint: { "fill-color": "#3dd6c6", "fill-opacity": 0.18 },
      });
      map.addLayer({
        id: "geofences-line",
        type: "line",
        source: "geofences",
        paint: { "line-color": "#3dd6c6", "line-width": 2 },
      });

      map.addSource("track", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "track-line",
        type: "line",
        source: "track",
        paint: {
          "line-color": "#5b9cff",
          "line-width": 3,
          "line-opacity": 0.9,
        },
      });
      map.addLayer({
        id: "track-pts",
        type: "circle",
        source: "track",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 4,
          "circle-color": "#5b9cff",
          "circle-stroke-width": 1,
          "circle-stroke-color": "#0a1018",
        },
      });

      map.addSource("draw", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("topo-profile", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("topo-los", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("topo-picks", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // slope overlay placeholder — updated via effect

      map.addLayer({
        id: "draw-line",
        type: "line",
        source: "draw",
        paint: {
          "line-color": "#f0b429",
          "line-width": 2,
          "line-dasharray": [2, 1],
        },
      });
      map.addLayer({
        id: "draw-pts",
        type: "circle",
        source: "draw",
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 5, "circle-color": "#f0b429" },
      });
      map.addLayer({
        id: "topo-profile-line",
        type: "line",
        source: "topo-profile",
        paint: {
          "line-color": "#3dd6c6",
          "line-width": 3,
          "line-opacity": 0.95,
        },
      });
      map.addLayer({
        id: "topo-los-line",
        type: "line",
        source: "topo-los",
        paint: {
          "line-color": "#f07178",
          "line-width": 2.5,
          "line-dasharray": [2, 1],
        },
      });
      map.addLayer({
        id: "topo-picks-pts",
        type: "circle",
        source: "topo-picks",
        paint: {
          "circle-radius": 7,
          "circle-color": "#ffcb6b",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#0a1018",
        },
      });
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({
      pitch: pitch3d ? 50 : 0,
      bearing: pitch3d ? -12 : 0,
      duration: 600,
    });
  }, [pitch3d]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    try {
      if (terrainOn) map.setTerrain({ source: "terrainSource", exaggeration: 1.35 });
      else map.setTerrain(null);
    } catch {
      /* ignore */
    }
  }, [terrainOn]);

  // GIBS overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      for (const id of ["gibs-marble", "gibs-viirs"]) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      if (gibs === "marble" && map.getSource("gibs")) {
        map.addLayer(
          { id: "gibs-marble", type: "raster", source: "gibs", paint: { "raster-opacity": 0.85 } },
          "hillshade"
        );
      }
      if (gibs === "viirs" && map.getSource("gibs_viirs")) {
        map.addLayer(
          {
            id: "gibs-viirs",
            type: "raster",
            source: "gibs_viirs",
            paint: { "raster-opacity": 0.9 },
          },
          "hillshade"
        );
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [gibs]);

  // FIRMS WMS (requires MAP_KEY on backend)
  useEffect(() => {
    if (!firmsOn) return;
    let cancelled = false;
    (async () => {
      try {
        const info = await fetchFirmsWms();
        if (!cancelled && info.available && info.tile_url) {
          const u = info.tile_url.startsWith("http")
            ? info.tile_url
            : `${window.location.origin}${info.tile_url}`;
          setFirmsUrl(u);
        }
        else if (!cancelled) setFirmsOn(false);
      } catch {
        if (!cancelled) setFirmsOn(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [firmsOn]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (map.getLayer("firms-wms")) map.removeLayer("firms-wms");
      if (map.getSource("firms-wms")) map.removeSource("firms-wms");
      if (firmsOn && firmsUrl) {
        map.addSource("firms-wms", {
          type: "raster",
          tiles: [firmsUrl],
          tileSize: 256,
          attribution: "NASA FIRMS",
        });
        map.addLayer(
          {
            id: "firms-wms",
            type: "raster",
            source: "firms-wms",
            paint: { "raster-opacity": 0.95 },
          },
          "hillshade"
        );
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [firmsOn, firmsUrl]);

  // Markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    for (const obs of observations) {
      if (obs.lon == null || obs.lat == null) continue;
      const color = TYPE_COLOR[obs.entity_type] || TYPE_COLOR.unknown;
      const selected = selectedEntityId === obs.entity_id;
      const el = document.createElement("div");
      el.style.cssText = `width:${selected ? 14 : 11}px;height:${selected ? 14 : 11}px;border-radius:50%;background:${color};box-shadow:0 0 0 2px rgba(0,0,0,.55),0 0 14px ${color};cursor:pointer;`;
      el.title = obs.entity_id;
      el.onclick = (ev) => {
        ev.stopPropagation();
        onSelectEntity?.(obs.entity_id);
      };
      const box = document.createElement("div");
      box.style.cssText = "font-family:IBM Plex Mono,monospace;font-size:12px";
      const strong = document.createElement("strong");
      strong.textContent = String(obs.entity_id);
      const meta = document.createElement("div");
      meta.style.opacity = "0.75";
      meta.textContent = `${obs.entity_type} · ${obs.source_id}`;
      const when = document.createElement("div");
      when.textContent = String(obs.observed_at);
      const hint = document.createElement("div");
      hint.style.opacity = "0.6";
      hint.textContent = "Click → track";
      box.append(strong, meta, when, hint);
      const popup = new maplibregl.Popup({ offset: 14 }).setDOMContent(box);
      markersRef.current.push(
        new maplibregl.Marker({ element: el })
          .setLngLat([obs.lon, obs.lat])
          .setPopup(popup)
          .addTo(map)
      );
    }
  }, [observations, selectedEntityId, onSelectEntity]);

  // Geofences
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const src = map.getSource("geofences") as maplibregl.GeoJSONSource | undefined;
      if (!src) return;
      const features = geofences
        .filter((g) => g.geometry && g.enabled !== false)
        .map((g) => ({
          type: "Feature" as const,
          properties: { id: g.id, name: g.name },
          geometry: g.geometry as GeoJSON.Geometry,
        }));
      src.setData({ type: "FeatureCollection", features });
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [geofences]);

  // Track polyline
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const src = map.getSource("track") as maplibregl.GeoJSONSource | undefined;
      if (!src) return;
      const coords = track
        .filter((p) => p.lon != null && p.lat != null)
        .map((p) => [p.lon as number, p.lat as number]);
      const features: GeoJSON.Feature[] = [];
      if (coords.length >= 2) {
        features.push({
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: coords },
        });
      }
      for (const c of coords) {
        features.push({
          type: "Feature",
          properties: {},
          geometry: { type: "Point", coordinates: c },
        });
      }
      src.setData({ type: "FeatureCollection", features });
      if (coords.length >= 1) {
        const bounds = coords.reduce(
          (b, c) => b.extend(c as [number, number]),
          new maplibregl.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number])
        );
        if (coords.length > 1) {
          map.fitBounds(bounds, { padding: 60, maxZoom: 12, duration: 800 });
        }
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [track]);

  // Draw polygon
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const updateDraw = () => {
      const src = map.getSource("draw") as maplibregl.GeoJSONSource | undefined;
      if (!src) return;
      const pts = drawPts.current;
      const features: GeoJSON.Feature[] = pts.map((c) => ({
        type: "Feature",
        properties: {},
        geometry: { type: "Point", coordinates: c },
      }));
      if (pts.length >= 2) {
        features.push({
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: pts },
        });
      }
      src.setData({ type: "FeatureCollection", features });
    };

    const onClick = (e: maplibregl.MapMouseEvent) => {
      if (!drawMode) return;
      drawPts.current.push([e.lngLat.lng, e.lngLat.lat]);
      updateDraw();
    };
    const onDbl = (e: maplibregl.MapMouseEvent) => {
      if (!drawMode) return;
      e.preventDefault();
      const pts = drawPts.current;
      if (pts.length >= 3) onPolygonComplete?.([...pts, pts[0]]);
      drawPts.current = [];
      updateDraw();
    };

    map.getCanvas().style.cursor = drawMode ? "crosshair" : "";
    map.on("click", onClick);
    map.on("dblclick", onDbl);
    if (!drawMode) {
      drawPts.current = [];
      updateDraw();
    }
    return () => {
      map.off("click", onClick);
      map.off("dblclick", onDbl);
      map.getCanvas().style.cursor = "";
    };
  }, [drawMode, onPolygonComplete]);


  // Topography: profile line
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("topo-profile") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    if (!topoProfileCoords || topoProfileCoords.length < 2) {
      src.setData({ type: "FeatureCollection", features: [] });
      return;
    }
    src.setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: topoProfileCoords },
        },
      ],
    });
  }, [topoProfileCoords]);

  // Topography: LOS line + obstruction
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("topo-los") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    if (!topoLos) {
      src.setData({ type: "FeatureCollection", features: [] });
      return;
    }
    const features: GeoJSON.Feature[] = [
      {
        type: "Feature",
        properties: { kind: "los" },
        geometry: {
          type: "LineString",
          coordinates: [topoLos.observer, topoLos.target],
        },
      },
    ];
    if (topoLos.obstruction) {
      features.push({
        type: "Feature",
        properties: { kind: "obstruction" },
        geometry: { type: "Point", coordinates: topoLos.obstruction },
      });
    }
    src.setData({ type: "FeatureCollection", features });
  }, [topoLos]);

  // Topography: pick points markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource("topo-picks") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData({
      type: "FeatureCollection",
      features: (topoPickPoints || []).map((c, i) => ({
        type: "Feature" as const,
        properties: { idx: i },
        geometry: { type: "Point" as const, coordinates: c },
      })),
    });
  }, [topoPickPoints]);

  // Topography click-to-pick
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !onTopoPick || topoMode === "idle") return;
    const handler = (e: maplibregl.MapMouseEvent) => {
      if (drawMode) return;
      onTopoPick([e.lngLat.lng, e.lngLat.lat]);
    };
    map.getCanvas().style.cursor = "crosshair";
    map.on("click", handler);
    return () => {
      map.off("click", handler);
      map.getCanvas().style.cursor = "";
    };
  }, [topoMode, onTopoPick, drawMode]);


  // Slope PNG overlay (MapLibre image source)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (map.getLayer("slope-overlay-layer")) map.removeLayer("slope-overlay-layer");
      if (map.getSource("slope-overlay")) map.removeSource("slope-overlay");
      if (!slopeOverlay || !slopeOverlay.url) return;
      const [w, s, e, n] = slopeOverlay.bounds;
      map.addSource("slope-overlay", {
        type: "image",
        url: slopeOverlay.url,
        coordinates: [
          [w, n],
          [e, n],
          [e, s],
          [w, s],
        ],
      });
      map.addLayer({
        id: "slope-overlay-layer",
        type: "raster",
        source: "slope-overlay",
        paint: { "raster-opacity": 0.65 },
      });
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [slopeOverlay]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div ref={container} style={{ width: "100%", height: "100%" }} />
      <div className="map-tools">
        <button type="button" className={pitch3d ? "active" : ""} onClick={() => setPitch3d((v) => !v)}>
          3D
        </button>
        <button type="button" className={terrainOn ? "active" : ""} onClick={() => setTerrainOn((v) => !v)}>
          DEM
        </button>
        <button
          type="button"
          className={gibs === "marble" ? "active" : ""}
          onClick={() => setGibs((g) => (g === "marble" ? "off" : "marble"))}
          title="NASA GIBS Blue Marble (sin key)"
        >
          NASA
        </button>
        <button
          type="button"
          className={gibs === "viirs" ? "active" : ""}
          onClick={() => setGibs((g) => (g === "viirs" ? "off" : "viirs"))}
          title="NASA GIBS VIIRS True Color"
        >
          VIIRS
        </button>
        <button
          type="button"
          className={firmsOn ? "active" : ""}
          onClick={() => setFirmsOn((v) => !v)}
          title="NASA FIRMS WMS (requiere FIRMS_MAP_KEY en API)"
        >
          FIRMS
        </button>
      </div>
    </div>
  );
}
