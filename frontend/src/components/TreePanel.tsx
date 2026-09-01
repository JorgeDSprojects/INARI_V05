import { useState } from "react";
import { api } from "../api/client";
import type { EnterpriseTree, SelectedNode, HierarchyLevel } from "../types/uns";

interface Props {
  enterprise: EnterpriseTree;
  selected: SelectedNode | null;
  onSelect: (node: SelectedNode) => void;
  onRefresh: () => void;
}

interface RowProps {
  label: string;
  level: HierarchyLevel;
  id: string;
  indent: number;
  selected: boolean;
  hasChildren: boolean;
  status?: "synced" | "idle";
  onClick: () => void;
  onAdd?: () => void;
}

function TreeRow({ label, level, indent, selected, hasChildren, status = "idle", onClick, onAdd }: RowProps) {
  const [open, setOpen] = useState(true);
  const [hovered, setHovered] = useState(false);

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 h-9 px-2 cursor-pointer rounded mx-1 group ${
          selected ? "bg-accent-soft" : hovered ? "bg-surface-subtle" : ""
        }`}
        style={{ paddingLeft: `${8 + indent * 16}px` }}
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <button
          onClick={e => { e.stopPropagation(); setOpen(!open); }}
          className="w-3.5 h-3.5 flex items-center justify-center text-ink-muted shrink-0"
        >
          {hasChildren ? (
            <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
              {open
                ? <path d="M0 2l4 4 4-4H0z"/>
                : <path d="M2 0l4 4-4 4V0z"/>
              }
            </svg>
          ) : (
            <span className="w-1 h-1 rounded-full bg-ink-muted/40 inline-block" />
          )}
        </button>

        <span className={`w-3.5 h-3.5 shrink-0 ${selected ? "text-accent" : "text-ink-secondary"}`}>
          {LEVEL_ICON[level]}
        </span>

        <span className={`flex-1 text-sm truncate ${selected ? "text-ink font-medium" : "text-ink-secondary"}`}>
          {label}
        </span>

        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${status === "synced" ? "bg-success" : "bg-ink-muted/40"}`} />

        {onAdd && (hovered || selected) && (
          <button
            onClick={e => { e.stopPropagation(); onAdd(); }}
            className="w-5 h-5 flex items-center justify-center text-ink-muted hover:text-ink rounded text-xs shrink-0"
            title="Add child"
          >+</button>
        )}
      </div>
      {open && hasChildren && <div>{/* children rendered by parent */}</div>}
    </div>
  );
}

const LEVEL_ICON: Record<HierarchyLevel, JSX.Element> = {
  enterprise: <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><rect x="2" y="4" width="12" height="9" rx="1" opacity=".3"/><rect x="5" y="2" width="6" height="3" rx="1"/></svg>,
  site: <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><circle cx="8" cy="8" r="6" opacity=".3"/><circle cx="8" cy="8" r="3"/></svg>,
  area: <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><path d="M8 2l6 4v6H2V6z" opacity=".3"/><path d="M8 2l6 4v1H2V6z"/></svg>,
  line: <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><rect x="2" y="6" width="12" height="4" rx="2" opacity=".4"/><rect x="6" y="4" width="4" height="8" rx="2"/></svg>,
  cell: <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><rect x="3" y="3" width="10" height="10" rx="2" opacity=".3"/><rect x="6" y="6" width="4" height="4" rx="1"/></svg>,
  asset: <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><polygon points="8,2 14,11 2,11" opacity=".4"/><polygon points="8,5 11,10 5,10"/></svg>,
};

export function TreePanel({ enterprise, selected, onSelect, onRefresh }: Props) {
  const [search, setSearch] = useState("");
  const [addingChild, setAddingChild] = useState<{ level: HierarchyLevel; parentId: string } | null>(null);
  const [newName, setNewName] = useState("");

  const createChild = async () => {
    if (!addingChild || !newName.trim()) return;
    const body = { name: newName.trim() };
    const { level, parentId } = addingChild;
    if (level === "enterprise") await api.sites.create(parentId, body);
    else if (level === "site") await api.areas.create(parentId, body);
    else if (level === "area") await api.lines.create(parentId, body);
    else if (level === "line") await api.cells.create(parentId, body);
    else if (level === "cell") await api.assets.create(parentId, { ...body, descriptive_payload: {} });
    setAddingChild(null);
    setNewName("");
    onRefresh();
  };

  const rootTopic = `spBv1/${enterprise.name.toLowerCase().replace(/\s+/g, "-")}`;

  return (
    <aside className="w-[280px] flex flex-col border-r border-border bg-surface-subtle shrink-0">
      {/* Tree header */}
      <div className="px-4 pt-4 pb-2 border-b border-border-subtle">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="text-[10px] tracking-widest text-ink-muted">NAMESPACE</div>
            <div className="text-sm font-semibold text-ink truncate">{enterprise.name}</div>
          </div>
          <button
            onClick={() => setAddingChild({ level: "enterprise", parentId: enterprise.id })}
            className="flex items-center gap-1 px-2 py-1 text-xs text-ink-secondary hover:text-ink rounded border border-border bg-surface"
          >
            + Add
          </button>
        </div>
        <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-surface-muted w-fit">
          <span className="text-accent text-[10px]">◈</span>
          <span className="text-ink-secondary text-xs font-mono">{rootTopic}</span>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <input
          className="w-full text-xs border border-border rounded px-2.5 py-1.5 bg-surface focus:outline-none focus:ring-1 focus:ring-accent text-ink placeholder:text-ink-muted"
          placeholder="Search nodes…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {/* Inline add form */}
      {addingChild && (
        <div className="px-3 pb-2">
          <div className="flex gap-1.5">
            <input
              autoFocus
              className="flex-1 text-xs border border-accent rounded px-2 py-1.5 bg-surface focus:outline-none"
              placeholder="Node name…"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") createChild(); if (e.key === "Escape") setAddingChild(null); }}
            />
            <button onClick={createChild} className="px-2 py-1 bg-ink text-white text-xs rounded">✓</button>
            <button onClick={() => setAddingChild(null)} className="px-2 py-1 text-ink-muted text-xs rounded border border-border">✕</button>
          </div>
        </div>
      )}

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1">
        {enterprise.sites
          .filter(s => !search || s.name.toLowerCase().includes(search.toLowerCase()))
          .map(site => (
            <div key={site.id}>
              <TreeRow
                label={site.name} level="site" id={site.id} indent={0}
                hasChildren={site.areas.length > 0} status="synced"
                selected={selected?.level === "site" && selected.id === site.id}
                onClick={() => onSelect({ level: "site", id: site.id, parentIds: { enterprise_id: enterprise.id } })}
                onAdd={() => setAddingChild({ level: "site", parentId: site.id })}
              />
              {site.areas.map(area => (
                <div key={area.id}>
                  <TreeRow
                    label={area.name} level="area" id={area.id} indent={1}
                    hasChildren={area.lines.length > 0}
                    selected={selected?.level === "area" && selected.id === area.id}
                    onClick={() => onSelect({ level: "area", id: area.id, parentIds: { site_id: site.id } })}
                    onAdd={() => setAddingChild({ level: "area", parentId: area.id })}
                  />
                  {area.lines.map(line => (
                    <div key={line.id}>
                      <TreeRow
                        label={line.name} level="line" id={line.id} indent={2}
                        hasChildren={line.cells.length > 0}
                        selected={selected?.level === "line" && selected.id === line.id}
                        onClick={() => onSelect({ level: "line", id: line.id, parentIds: { area_id: area.id } })}
                        onAdd={() => setAddingChild({ level: "line", parentId: line.id })}
                      />
                      {line.cells.map(cell => (
                        <div key={cell.id}>
                          <TreeRow
                            label={cell.name} level="cell" id={cell.id} indent={3}
                            hasChildren={cell.assets.length > 0}
                            selected={selected?.level === "cell" && selected.id === cell.id}
                            onClick={() => onSelect({ level: "cell", id: cell.id, parentIds: { line_id: line.id } })}
                            onAdd={() => setAddingChild({ level: "cell", parentId: cell.id })}
                          />
                          {cell.assets.map(asset => (
                            <TreeRow
                              key={asset.id}
                              label={asset.name} level="asset" id={asset.id} indent={4}
                              hasChildren={false}
                              status={asset.descriptive_payload && Object.keys(asset.descriptive_payload).length > 0 ? "synced" : "idle"}
                              selected={selected?.level === "asset" && selected.id === asset.id}
                              onClick={() => onSelect({ level: "asset", id: asset.id, parentIds: { cell_id: cell.id } })}
                            />
                          ))}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ))}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-border-subtle text-[10px] text-ink-muted flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
        <span>{enterprise.sites.length} sites · {enterprise.sites.reduce((a, s) => a + s.areas.reduce((b, ar) => b + ar.lines.reduce((c, l) => c + l.cells.reduce((d, ce) => d + ce.assets.length, 0), 0), 0), 0)} assets</span>
      </div>
    </aside>
  );
}
