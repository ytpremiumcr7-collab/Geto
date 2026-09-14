import { getToken, clearAuth } from "@/lib/auth";

const BASE = "";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    const detail =
      typeof body === "object" && body && "detail" in body
        ? JSON.stringify((body as { detail: unknown }).detail)
        : `HTTP ${status}`;
    super(detail);
    this.status = status;
    this.body = body;
  }
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearAuth();
    if (!path.includes("/auth/token")) {
      window.location.href = "/login";
    }
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export type SourceRow = {
  source_id: string;
  source_type: string;
  description: string;
  available?: boolean;
  can_read?: boolean;
  can_admin?: boolean;
  access_policy?: string;
  commercial_status?: string;
  license?: string;
  scope?: string;
};

export type Observation = {
  id: string;
  entity_id: string;
  entity_type: string;
  source_id: string;
  observed_at: string;
  lon?: number | null;
  lat?: number | null;
  altitude_m?: number | null;
  speed_mps?: number | null;
  heading_deg?: number | null;
  confidence?: number | null;
};

export type GeofenceRow = {
  id: string;
  name: string;
  enabled: boolean;
  description?: string | null;
  geometry?: GeoJSON.Geometry | null;
};

export async function issueToken(body: {
  user_id: string;
  tenant_id: string;
  roles: string[];
  bootstrap_secret?: string;
}) {
  return api<{ access_token: string; token_type: string }>(
    "/api/v1/auth/token",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function fetchSources() {
  return api<{ sources: SourceRow[]; tenant_id: string; roles: string[] }>(
    "/api/v1/sources"
  );
}

export async function fetchObservations(params?: {
  source_id?: string;
  since?: string;
  until?: string;
  limit?: number;
}) {
  const q = new URLSearchParams();
  if (params?.source_id) q.set("source_id", params.source_id);
  if (params?.since) q.set("since", params.since);
  if (params?.until) q.set("until", params.until);
  q.set("limit", String(params?.limit ?? 200));
  return api<{ observations: Observation[]; count: number }>(
    `/api/v1/observations?${q}`
  );
}

export async function fetchGeofences() {
  return api<{ geofences: GeofenceRow[]; tenant_id?: string }>(
    "/api/v1/geofences"
  );
}

export async function createGeofence(body: {
  name: string;
  description?: string;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}) {
  return api<{ id: string; name: string }>("/api/v1/geofences", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchReady() {
  return api<{
    status: string;
    postgres?: boolean;
    nats?: boolean;
    minio?: boolean;
  }>("/health/ready");
}

export type TrackPoint = {
  observed_at: string;
  lon?: number | null;
  lat?: number | null;
  altitude_m?: number | null;
  speed_mps?: number | null;
  heading_deg?: number | null;
};

export async function fetchTrack(entityId: string, limit = 200) {
  return api<{ entity_id: string; track: TrackPoint[]; tenant_id?: string }>(
    `/api/v1/entities/${encodeURIComponent(entityId)}/track?limit=${limit}`
  );
}

export async function fetchFirmsWms() {
  return api<{ available: boolean; tile_url?: string; layer?: string; detail?: string }>(
    "/api/v1/sources/nasa_firms/wms"
  );
}

export async function fetchLive() {
  return api<{ status: string }>("/health/live");
}

/* ── Topography ─────────────────────────────────────────── */

export type ElevationResult = {
  elevation_m: number | null;
  lat: number;
  lon: number;
  source: string;
  provider: string;
  product_name?: string | null;
  resolution_m?: number | null;
  crs?: string | null;
  vertical_datum?: string | null;
  dem_id?: string | null;
  sampled_at: string;
  note?: string | null;
};

export type ProfilePoint = {
  distance_m: number;
  lon: number;
  lat: number;
  elevation_m?: number | null;
  slope_deg?: number | null;
};

export type ProfileResult = {
  points: ProfilePoint[];
  total_distance_m: number;
  source: string;
  provider: string;
  resolution_m?: number | null;
  dem_id?: string | null;
  sample_distance_m: number;
};

export type LosResult = {
  visible: boolean;
  observer: { lon: number; lat: number; height_m?: number };
  target: { lon: number; lat: number; height_m?: number };
  obstruction_distance_m?: number | null;
  obstruction_lon?: number | null;
  obstruction_lat?: number | null;
  profile: ProfilePoint[];
  source: string;
  provider: string;
  dem_id?: string | null;
  note?: string | null;
};

export type DemAsset = {
  id: string;
  provider: string;
  product_name: string;
  resolution_m: number;
  file_uri: string;
  bbox_west: number;
  bbox_south: number;
  bbox_east: number;
  bbox_north: number;
};

export async function fetchElevation(lat: number, lon: number, demId?: string) {
  const q = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  if (demId) q.set("dem_id", demId);
  return api<ElevationResult>(`/api/v1/topography/elevation?${q}`);
}

export async function fetchProfile(
  coordinates: [number, number][],
  sampleDistanceM = 25,
  demId?: string
) {
  return api<ProfileResult>("/api/v1/topography/profile", {
    method: "POST",
    body: JSON.stringify({
      coordinates,
      sample_distance_m: sampleDistanceM,
      dem_id: demId || null,
    }),
  });
}

export async function fetchLos(body: {
  observer_lon: number;
  observer_lat: number;
  target_lon: number;
  target_lat: number;
  observer_height_m?: number;
  target_height_m?: number;
  dem_id?: string;
}) {
  return api<LosResult>("/api/v1/topography/los", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchDemAssets() {
  return api<{ dem_assets: DemAsset[]; tenant_id?: string }>(
    "/api/v1/topography/dem"
  );
}

export async function fetchTopoProviders() {
  return api<Record<string, unknown>>("/api/v1/topography/providers");
}

export type SlopePreview = {
  objectUrl: string;
  bounds: [number, number, number, number]; // w,s,e,n
  stats: { slope_min: number; slope_max: number; slope_mean: number };
};

export async function fetchSlopePreview(
  demId: string,
  bbox?: [number, number, number, number]
): Promise<SlopePreview> {
  const q = new URLSearchParams({ dem_id: demId });
  if (bbox) {
    q.set("west", String(bbox[0]));
    q.set("south", String(bbox[1]));
    q.set("east", String(bbox[2]));
    q.set("north", String(bbox[3]));
  }
  const base = (import.meta as any).env?.VITE_API_BASE || "";
  const token = getToken() || "";
  const res = await fetch(`${base}/api/v1/topography/slope-preview?${q}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const bounds: [number, number, number, number] = [
    Number(res.headers.get("X-Bounds-West") || 0),
    Number(res.headers.get("X-Bounds-South") || 0),
    Number(res.headers.get("X-Bounds-East") || 0),
    Number(res.headers.get("X-Bounds-North") || 0),
  ];
  return {
    objectUrl,
    bounds,
    stats: {
      slope_min: Number(res.headers.get("X-Slope-Min") || 0),
      slope_max: Number(res.headers.get("X-Slope-Max") || 0),
      slope_mean: Number(res.headers.get("X-Slope-Mean") || 0),
    },
  };
}
