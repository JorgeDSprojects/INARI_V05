import { useState } from "react";
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent,
  PointerSensor, useSensor, useSensors,
} from "@dnd-kit/core";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { api } from "../api/client";
import type { EnterpriseTree, SelectedNode, HierarchyLevel } from "../types/uns";
import { CreateWithDescriptiveModal } from "./CreateWithDescriptiveModal";
import { CopyMoveModal } from "./CopyMoveModal";

// ─── Level colours ─────────────────────────────────────────────────────────────
export const LEVEL_COLORS: Record<HierarchyLevel, {
  dot: string; icon: string; badge: string; dropRing: string;
}> = {
  enterprise: { dot: "bg-violet-400", icon: "text-violet-500", badge: "bg-violet-100 text-violet-700", dropRing: "ring-2 ring-violet-300 bg-violet-50" },
  site:       { dot: "bg-blue-400",   icon: "text-blue-500",   badge: "bg-blue-100 text-blue-700",     dropRing: "ring-2 ring-blue-300 bg-blue-50" },
  area:       { dot: "bg-cyan-400",   icon: "text-cyan-500",   badge: "bg-cyan-100 text-cyan-700",     dropRing: "ring-2 ring-cyan-300 bg-cyan-50" },
  line:       { dot: "bg-emerald-400",icon: "text-emerald-500",badge: "bg-emerald-100 text-emerald-700",dropRing: "ring-2 ring-emerald-300 bg-emerald-50" },
  cell:       { dot: "bg-amber-400",  icon: "text-amber-500",  badge: "bg-amber-100 text-amber-700",   dropRing: "ring-2 ring-amber-300 bg-amber-50" },
  asset:      { dot: "bg-orange-400", icon: "text-orange-500", badge: "bg-orange-100 text-orange-700", dropRing: "ring-2 ring-orange-300 bg-orange-50" },
};

// Which level a dragged node can be dropped onto (its valid parent level)
const PARENT_LEVEL: Partial<Record<HierarchyLevel, HierarchyLevel>> = {
  area: "site",
  line: "area",
  cell: "line",
  asset: "cell",
};

// ─── Props ─────────────────────────────────────────────────────────────────────
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
  onCopy?: () => void;
  children?: React.ReactNode;
  draggingLevel?: HierarchyLevel | null; // level currently being dragged (to highlight valid targets)
}

// ─── TreeRow ───────────────────────────────────────────────────────────────────
function TreeRow({
  label, level, id, indent, selected, hasChildren,
  status = "idle", onClick, onAdd, onCopy, children, draggingLevel,
}: RowProps) {
  const [open, setOpen] = useState(true);
  const [hovered, setHovered] = useState(false);

  // Draggable — enterprise is NOT draggable
  const canDrag = level !== "enterprise";
  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: `drag-${id}`,
    data: { id, level, label },
    disabled: !canDrag,
  });

  // Droppable — valid when the dragged level maps to this level as parent
  const isValidDropTarget = draggingLevel !== null && draggingLevel !== undefined
    && PARENT_LEVEL[draggingLevel] === level;
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `drop-${id}`,
    data: { id, level },
    disabled: !isValidDropTarget,
  });

  // Combine drag + drop onto the row div
  const combineRef = (el: HTMLElement | null) => {
    setDragRef(el);
    setDropRef(el);
  };

  const colors = LEVEL_COLORS[level];

  return (
    <div style={{ opacity: isDragging ? 0.4 : 1 }}>
      <div
        ref={combineRef}
        style={{ paddingLeft: `${8 + indent * 16}px` }}
        className={[
          "flex items-center gap-1.5 h-9 px-2 cursor-pointer rounded mx-1 group transition-colors",
          isOver && isValidDropTarget ? colors.dropRing : "",
          selected && !isOver ? "bg-accent-soft" : "",
          hovered && !selected && !isOver ? "bg-surface-subtle" : "",
        ].join(" ")}
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {/* Drag handle — appears on hover for draggable levels */}
        {canDrag && (
          <button
            {...listeners}
            {...attributes}
            className="touch-none flex-shrink-0 w-3.5 h-3.5 flex items-center justify-center cursor-grab active:cursor-grabbing text-ink-muted/30 hover:text-ink-muted opacity-0 group-hover:opacity-100 transition-opacity"
            onClick={e => e.stopPropagation()}
            title="Drag to move"
            tabIndex={-1}
          >
            <svg width="8" height="12" viewBox="0 0 8 12" fill="currentColor">
              <circle cx="2" cy="2" r="1.5"/><circle cx="6" cy="2" r="1.5"/>
              <circle cx="2" cy="6" r="1.5"/><circle cx="6" cy="6" r="1.5"/>
              <circle cx="2" cy="10" r="1.5"/><circle cx="6" cy="10" r="1.5"/>
            </svg>
          </button>
        )}
        {!canDrag && <span className="w-3.5 shrink-0" />}

        {/* Collapse toggle */}
        <button
          onClick={e => { e.stopPropagation(); setOpen(!open); }}
          className="w-3.5 h-3.5 flex items-center justify-center text-ink-muted shrink-0"
        >
          {hasChildren ? (
            <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
              {open ? <path d="M0 2l4 4 4-4H0z"/> : <path d="M2 0l4 4-4 4V0z"/>}
            </svg>
          ) : (
            <span className="w-1 h-1 rounded-full bg-ink-muted/40 inline-block" />
          )}
        </button>

        {/* Level icon */}
        <span className={`w-3.5 h-3.5 shrink-0 ${selected ? "text-accent" : colors.icon}`}>
          {LEVEL_ICON[level]}
        </span>

        {/* Label */}
        <span className={`flex-1 text-sm truncate ${selected ? "text-ink font-medium" : "text-ink-secondary"}`}>
          {label}
        </span>

        {/* Status dot */}
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${status === "synced" ? colors.dot : "bg-ink-muted/40"}`} />

        {/* Action buttons */}
        {onAdd && (hovered || selected) && (
          <button
            onClick={e => { e.stopPropagation(); onAdd(); }}
            className="w-5 h-5 flex items-center justify-center text-ink-muted hover:text-ink rounded text-xs shrink-0"
            title="Add child"
          >+</button>
        )}
        {onCopy && (hovered || selected) && (
          <button
            onClick={e => { e.stopPropagation(); onCopy(); }}
            className="w-5 h-5 flex items-center justify-center text-ink-muted hover:text-ink rounded text-xs shrink-0"
            title="Copy/Move"
          >⧉</button>
        )}
      </div>
      {open && children}
    </div>
  );
}

// ─── Level icons ───────────────────────────────────────────────────────────────
const LEVEL_ICON: Record<HierarchyLevel, JSX.Element> = {
  enterprise: <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><rect x="2" y="4" width="12" height="9" rx="1" opacity=".3"/><rect x="5" y="2" width="6" height="3" rx="1"/></svg>,
  site:       <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><circle cx="8" cy="8" r="6" opacity=".3"/><circle cx="8" cy="8" r="3"/></svg>,
  area:       <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><path d="M8 2l6 4v6H2V6z" opacity=".3"/><path d="M8 2l6 4v1H2V6z"/></svg>,
  line:       <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><rect x="2" y="6" width="12" height="4" rx="2" opacity=".4"/><rect x="6" y="4" width="4" height="8" rx="2"/></svg>,
  cell:       <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><rect x="3" y="3" width="10" height="10" rx="2" opacity=".3"/><rect x="6" y="6" width="4" height="4" rx="1"/></svg>,
  asset:      <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><polygon points="8,2 14,11 2,11" opacity=".4"/><polygon points="8,5 11,10 5,10"/></svg>,
};

// ─── TreePanel ─────────────────────────────────────────────────────────────────
export function TreePanel({ enterprise, selected, onSelect, onRefresh }: Props) {
  const [search, setSearch] = useState("");
  const [addingChild, setAddingChild] = useState<{ level: HierarchyLevel; parentId: string } | null>(null);
  const [newName, setNewName] = useState("");
  const [assetModalCellId, setAssetModalCellId] = useState<string | null>(null);
  const [copyMoveNode, setCopyMoveNode] = useState<{ id: string; level: HierarchyLevel; name: string } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<{ published: number; failed: number } | null>(null);
  const [draggingLevel, setDraggingLevel] = useState<HierarchyLevel | null>(null);
  const [draggingLabel, setDraggingLabel] = useState<string>("");

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const syncAll = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await api.tree.publishSubtree({ root_id: enterprise.id, root_level: "enterprise" });
      setSyncResult(result);
      setTimeout(() => setSyncResult(null), 4000);
    } finally { setSyncing(false); }
  };

  const createChild = async () => {
    if (!addingChild || !newName.trim()) return;
    const body = { name: newName.trim() };
    const { level, parentId } = addingChild;
    if (level === "enterprise") await api.sites.create(parentId, body);
    else if (level === "site") await api.areas.create(parentId, body);
    else if (level === "area") await api.lines.create(parentId, body);
    else if (level === "line") await api.cells.create(parentId, body);
    setAddingChild(null);
    setNewName("");
    onRefresh();
  };

  const handleDragStart = (event: DragStartEvent) => {
    const data = event.active.data.current as { level: HierarchyLevel; label: string };
    setDraggingLevel(data.level);
    setDraggingLabel(data.label);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    setDraggingLevel(null);
    setDraggingLabel("");
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const source = active.data.current as { id: string; level: HierarchyLevel; label: string };
    const target = over.data.current as { id: string; level: HierarchyLevel };

    const expectedParentLevel = PARENT_LEVEL[source.level];
    if (!expectedParentLevel || target.level !== expectedParentLevel) return;

    try {
      await api.tree.move({ source_id: source.id, source_level: source.level, target_parent_id: target.id });
      onRefresh();
    } catch {
      // Move failed silently — tree unchanged
    }
  };

  const rootTopic = `${enterprise.name.replace(/\s+/g, "_")}`;

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <aside className="w-[280px] flex flex-col border-r border-border bg-surface-subtle shrink-0">
        {/* Tree header */}
        <div className="px-4 pt-4 pb-2 border-b border-border-subtle">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-[10px] tracking-widest text-ink-muted">NAMESPACE</div>
              <div
                className={`text-sm font-semibold truncate cursor-pointer hover:text-accent transition-colors ${
                  selected?.level === "enterprise" && selected.id === enterprise.id ? "text-accent" : "text-ink"
                }`}
                onClick={() => onSelect({ level: "enterprise", id: enterprise.id, parentIds: {} })}
              >
                <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${LEVEL_COLORS.enterprise.dot}`} />
                {enterprise.name}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={syncAll}
                disabled={syncing}
                title="Publish all retained payloads to MQTT broker"
                className="flex items-center gap-1 px-2 py-1 text-xs text-ink-secondary hover:text-ink rounded border border-border bg-surface disabled:opacity-50"
              >
                {syncing ? "⟳" : "↑ Sync"}
              </button>
              <button
                onClick={() => setAddingChild({ level: "enterprise", parentId: enterprise.id })}
                className="flex items-center gap-1 px-2 py-1 text-xs text-ink-secondary hover:text-ink rounded border border-border bg-surface"
              >
                + Add
              </button>
            </div>
          </div>
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-surface-muted w-fit">
            <span className="text-accent text-[10px]">◈</span>
            <span className="text-ink-secondary text-xs font-mono">{rootTopic}</span>
          </div>
          {syncResult && (
            <div className={`mt-1.5 px-2 py-1 rounded text-xs ${syncResult.failed === 0 ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}>
              ↑ {syncResult.published} published{syncResult.failed > 0 ? `, ${syncResult.failed} failed` : " ✓"}
            </div>
          )}
          {draggingLevel && (
            <div className="mt-1.5 px-2 py-1 rounded text-xs bg-accent/10 text-accent">
              Drop on a <span className="font-semibold">{PARENT_LEVEL[draggingLevel]}</span> to move
            </div>
          )}
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
              <TreeRow
                key={site.id}
                label={site.name} level="site" id={site.id} indent={0}
                hasChildren={site.areas.length > 0} status="synced"
                selected={selected?.level === "site" && selected.id === site.id}
                draggingLevel={draggingLevel}
                onClick={() => onSelect({ level: "site", id: site.id, parentIds: { enterprise_id: enterprise.id } })}
                onAdd={() => setAddingChild({ level: "site", parentId: site.id })}
                onCopy={() => setCopyMoveNode({ id: site.id, level: "site", name: site.name })}
              >
                {site.areas.map(area => (
                  <TreeRow
                    key={area.id}
                    label={area.name} level="area" id={area.id} indent={1}
                    hasChildren={area.lines.length > 0}
                    selected={selected?.level === "area" && selected.id === area.id}
                    draggingLevel={draggingLevel}
                    onClick={() => onSelect({ level: "area", id: area.id, parentIds: { site_id: site.id } })}
                    onAdd={() => setAddingChild({ level: "area", parentId: area.id })}
                    onCopy={() => setCopyMoveNode({ id: area.id, level: "area", name: area.name })}
                  >
                    {area.lines.map(line => (
                      <TreeRow
                        key={line.id}
                        label={line.name} level="line" id={line.id} indent={2}
                        hasChildren={line.cells.length > 0}
                        selected={selected?.level === "line" && selected.id === line.id}
                        draggingLevel={draggingLevel}
                        onClick={() => onSelect({ level: "line", id: line.id, parentIds: { area_id: area.id } })}
                        onAdd={() => setAddingChild({ level: "line", parentId: line.id })}
                        onCopy={() => setCopyMoveNode({ id: line.id, level: "line", name: line.name })}
                      >
                        {line.cells.map(cell => (
                          <TreeRow
                            key={cell.id}
                            label={cell.name} level="cell" id={cell.id} indent={3}
                            hasChildren={cell.assets.length > 0}
                            selected={selected?.level === "cell" && selected.id === cell.id}
                            draggingLevel={draggingLevel}
                            onClick={() => onSelect({ level: "cell", id: cell.id, parentIds: { line_id: line.id } })}
                            onAdd={() => setAssetModalCellId(cell.id)}
                            onCopy={() => setCopyMoveNode({ id: cell.id, level: "cell", name: cell.name })}
                          >
                            {cell.assets.map(asset => (
                              <TreeRow
                                key={asset.id}
                                label={asset.name} level="asset" id={asset.id} indent={4}
                                hasChildren={false}
                                status={asset.descriptive_payload && Object.keys(asset.descriptive_payload).length > 0 ? "synced" : "idle"}
                                selected={selected?.level === "asset" && selected.id === asset.id}
                                draggingLevel={draggingLevel}
                                onClick={() => onSelect({ level: "asset", id: asset.id, parentIds: { cell_id: cell.id } })}
                              />
                            ))}
                          </TreeRow>
                        ))}
                      </TreeRow>
                    ))}
                  </TreeRow>
                ))}
              </TreeRow>
            ))}
        </div>

        {/* Footer */}
        <div className="px-3 py-2 border-t border-border-subtle text-[10px] text-ink-muted flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
          <span>
            {enterprise.sites.length} sites ·{" "}
            {enterprise.sites.reduce((a, s) => a + s.areas.reduce((b, ar) => b + ar.lines.reduce((c, l) => c + l.cells.reduce((d, ce) => d + ce.assets.length, 0), 0), 0), 0)} assets
          </span>
        </div>

        {assetModalCellId && (
          <CreateWithDescriptiveModal
            cellId={assetModalCellId}
            onClose={() => setAssetModalCellId(null)}
            onCreated={() => { setAssetModalCellId(null); onRefresh(); }}
          />
        )}
        {copyMoveNode && (
          <CopyMoveModal
            sourceId={copyMoveNode.id}
            sourceLevel={copyMoveNode.level}
            sourceName={copyMoveNode.name}
            enterprise={enterprise}
            onClose={() => setCopyMoveNode(null)}
            onDone={() => { setCopyMoveNode(null); onRefresh(); }}
          />
        )}
      </aside>

      {/* Drag overlay — ghost shown while dragging */}
      <DragOverlay>
        {draggingLevel && (
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-xl border border-border bg-surface text-sm font-medium`}>
            <span className={`w-2 h-2 rounded-full shrink-0 ${LEVEL_COLORS[draggingLevel].dot}`} />
            <span className="text-ink">{draggingLabel}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${LEVEL_COLORS[draggingLevel].badge}`}>
              {draggingLevel}
            </span>
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
