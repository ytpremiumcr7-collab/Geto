import { useCallback, useEffect, useState } from "react";
import {
  createWorkspace,
  fetchWorkspaceLayers,
  fetchWorkspaces,
  type SavedLayer,
  type Workspace,
} from "@/api/client";

type Props = {
  onSelectWorkspace?: (w: Workspace) => void;
};

export function WorkspacePanel({ onSelectWorkspace }: Props) {
  const [items, setItems] = useState<Workspace[]>([]);
  const [layers, setLayers] = useState<SavedLayer[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetchWorkspaces();
      setItems(r.workspaces || []);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selected) {
      setLayers([]);
      return;
    }
    fetchWorkspaceLayers(selected)
      .then((r) => setLayers(r.layers || []))
      .catch(() => setLayers([]));
  }, [selected]);

  async function onCreate() {
    if (!name.trim()) return;
    try {
      const w = await createWorkspace({ name: name.trim() });
      setName("");
      await load();
      setSelected(w.id);
      onSelectWorkspace?.(w);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "create failed");
    }
  }

  return (
    <div className="panel">
      <h3>Workspaces / AOI</h3>
      {err && <p className="error">{err}</p>}
      <div className="row gap">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre workspace"
        />
        <button onClick={onCreate}>Crear</button>
      </div>
      <ul className="simple-list">
        {items.map((w) => (
          <li key={w.id}>
            <button
              className={selected === w.id ? "active" : ""}
              onClick={() => {
                setSelected(w.id);
                onSelectWorkspace?.(w);
              }}
            >
              {w.name}
              {w.is_default ? " ★" : ""}
            </button>
          </li>
        ))}
      </ul>
      {selected && (
        <div>
          <h4>Capas guardadas</h4>
          {layers.length === 0 && <p className="muted">Sin capas</p>}
          <ul className="simple-list">
            {layers.map((l) => (
              <li key={l.id}>
                {l.visible ? "👁" : "–"} {l.name}{" "}
                <span className="muted">({l.layer_type})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
