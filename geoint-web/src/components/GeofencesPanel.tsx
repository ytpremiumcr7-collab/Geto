import type { GeofenceRow } from "@/api/client";

type Props = {
  geofences: GeofenceRow[];
  onFocus?: (g: GeofenceRow) => void;
};

export function GeofencesPanel({ geofences, onFocus }: Props) {
  return (
    <div className="panel geofences-panel">
      <div className="panel-header">
        <span>GEOFENCES</span>
        <span className="muted">{geofences.length}</span>
      </div>
      <div className="panel-body feed">
        {geofences.length === 0 && (
          <div className="muted empty">
            Ninguno — usa «Geofence» y dibuja en el mapa
          </div>
        )}
        {geofences.map((g) => (
          <button
            key={g.id}
            type="button"
            className="fence-row"
            onClick={() => onFocus?.(g)}
          >
            <span className={`dot ${g.enabled ? "on" : "off"}`} />
            <span className="fence-name">{g.name}</span>
            {!g.geometry && <span className="badge">no geom</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
