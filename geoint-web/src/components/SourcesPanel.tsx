import type { SourceRow } from "@/api/client";

type Props = {
  sources: SourceRow[];
  selected?: string | null;
  onSelect: (id: string | null) => void;
};

export function SourcesPanel({ sources, selected, onSelect }: Props) {
  return (
    <div className="panel sources-panel">
      <div className="panel-header">
        <span>FUENTES</span>
        <span className="muted">{sources.length}</span>
      </div>
      <div className="panel-body">
        <button
          className={`source-row ${!selected ? "active" : ""}`}
          onClick={() => onSelect(null)}
        >
          <span className="dot all" />
          Todas
        </button>
        {sources.map((s) => (
          <button
            key={s.source_id}
            className={`source-row ${selected === s.source_id ? "active" : ""} ${
              s.available === false ? "denied" : ""
            }`}
            onClick={() => s.available !== false && onSelect(s.source_id)}
            title={s.description}
            disabled={s.available === false}
          >
            <span
              className={`dot ${s.available === false ? "off" : "on"}`}
            />
            <span className="sid">{s.source_id}</span>
            {s.scope === "goodmode" && <span className="badge">GM</span>}
            {s.commercial_status === "restricted" && (
              <span className="badge warn">R</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
