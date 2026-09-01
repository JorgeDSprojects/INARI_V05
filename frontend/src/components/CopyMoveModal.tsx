import { useState } from "react";
import { api } from "../api/client";
import type { EnterpriseTree, HierarchyLevel } from "../types/uns";

interface Props {
  sourceId: string;
  sourceLevel: HierarchyLevel;
  sourceName: string;
  enterprise: EnterpriseTree;
  onClose: () => void;
  onDone: () => void;
}

// Valid parent levels for each source level
const VALID_PARENT: Record<string, HierarchyLevel[]> = {
  site: ["enterprise"], area: ["site"], line: ["area"],
  cell: ["line"], asset: ["cell"],
};

type Node = { id: string; name: string; level: HierarchyLevel };

function collectNodes(enterprise: EnterpriseTree): Node[] {
  const nodes: Node[] = [{ id: enterprise.id, name: enterprise.name, level: "enterprise" }];
  enterprise.sites.forEach(s => {
    nodes.push({ id: s.id, name: s.name, level: "site" });
    s.areas.forEach(a => {
      nodes.push({ id: a.id, name: a.name, level: "area" });
      a.lines.forEach(l => {
        nodes.push({ id: l.id, name: l.name, level: "line" });
        l.cells.forEach(c => {
          nodes.push({ id: c.id, name: c.name, level: "cell" });
        });
      });
    });
  });
  return nodes;
}

export function CopyMoveModal({ sourceId, sourceLevel, sourceName, enterprise, onClose, onDone }: Props) {
  const [mode, setMode] = useState<"copy" | "move">("copy");
  const [targetParentId, setTargetParentId] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ count: number } | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<{ published: number; failed: number } | null>(null);
  const [opError, setOpError] = useState<string | null>(null);

  const validParentLevels = VALID_PARENT[sourceLevel] ?? [];
  const allNodes = collectNodes(enterprise);
  const validParents = allNodes.filter(n => validParentLevels.includes(n.level) && n.id !== sourceId);

  const handleConfirm = async () => {
    if (!targetParentId) return;
    setOpError(null);
    setLoading(true);
    try {
      const body = { source_id: sourceId, source_level: sourceLevel, target_parent_id: targetParentId };
      if (mode === "copy") {
        const r = await api.tree.copy(body);
        setResult({ count: r.node_count });
      } else {
        const r = await api.tree.move(body);
        setResult({ count: r.node_count });
      }
    } catch {
      setOpError(`Failed to ${mode} subtree. Please try again.`);
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async () => {
    setOpError(null);
    setPublishing(true);
    try {
      const r = await api.tree.publishSubtree({ root_id: sourceId, root_level: sourceLevel });
      setPublishResult(r);
      onDone();
    } catch {
      setOpError("Failed to publish subtree. Please try again.");
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-xl border border-border w-full max-w-lg shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-ink">Copy / Move Subtree</h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-lg">✕</button>
        </div>

        {!result ? (
          <div className="px-6 py-5 space-y-5">
            {/* Mode */}
            <div className="flex gap-2">
              {(["copy", "move"] as const).map(m => (
                <button key={m} onClick={() => setMode(m)}
                  className={`px-4 py-2 text-sm rounded border ${mode === m ? "bg-ink text-white border-ink" : "border-border text-ink-secondary hover:bg-surface-subtle"}`}>
                  {m === "copy" ? "Copy" : "Move"}
                </button>
              ))}
            </div>

            {/* Source */}
            <div>
              <div className="text-[10px] tracking-widest text-ink-muted mb-1.5">SOURCE</div>
              <div className="flex items-center gap-2 px-3 py-2 border border-border rounded bg-surface-subtle">
                <span className="text-ink text-sm font-medium">{sourceName}</span>
                <span className="px-2 py-0.5 rounded bg-surface text-ink-secondary text-[10px] font-medium tracking-wider border border-border">
                  {sourceLevel.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Target */}
            <div>
              <div className="text-[10px] tracking-widest text-ink-muted mb-1.5">DESTINATION PARENT</div>
              <select value={targetParentId} onChange={e => setTargetParentId(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent">
                <option value="">Select destination…</option>
                {validParents.map(n => (
                  <option key={n.id} value={n.id}>
                    {n.name} ({n.level})
                  </option>
                ))}
              </select>
            </div>

            {opError && (
              <p className="text-sm text-danger">{opError}</p>
            )}

            <div className="flex items-center justify-between pt-2 border-t border-border-subtle">
              <button onClick={onClose} className="px-4 py-2 text-sm text-ink-secondary border border-border rounded">
                Cancel
              </button>
              <button onClick={handleConfirm} disabled={loading || !targetParentId}
                className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50">
                {loading ? "Processing…" : `Confirm ${mode}`}
              </button>
            </div>
          </div>
        ) : (
          <div className="px-6 py-5 space-y-5">
            <div className="flex items-center gap-3 p-4 rounded-lg bg-success-soft">
              <span className="text-success text-xl">✓</span>
              <div>
                <p className="text-success font-medium text-sm">
                  {mode === "copy" ? "Copy" : "Move"} completed — {result.count} node{result.count !== 1 ? "s" : ""}
                </p>
                <p className="text-success/70 text-xs mt-0.5">New MQTT topics not yet published</p>
              </div>
            </div>
            {publishResult ? (
              <div className="p-4 rounded-lg bg-surface-subtle text-sm text-ink">
                Published {publishResult.published} asset{publishResult.published !== 1 ? "s" : ""}.
                {publishResult.failed > 0 && <span className="text-warning"> {publishResult.failed} failed.</span>}
              </div>
            ) : (
              <p className="text-sm text-ink-secondary">
                Do you want to publish all assets in the {mode === "copy" ? "copied" : "moved"} subtree to EMQX now?
              </p>
            )}

            {opError && (
              <p className="text-sm text-danger">{opError}</p>
            )}

            <div className="flex items-center justify-between pt-2 border-t border-border-subtle">
              <button onClick={() => { onDone(); onClose(); }}
                className="px-4 py-2 text-sm text-ink-secondary border border-border rounded">
                {publishResult ? "Close" : "Publish later"}
              </button>
              {!publishResult && (
                <button onClick={handlePublish} disabled={publishing}
                  className="px-5 py-2 text-sm bg-accent text-white rounded disabled:opacity-50">
                  {publishing ? "Publishing…" : "Publish to EMQX"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
