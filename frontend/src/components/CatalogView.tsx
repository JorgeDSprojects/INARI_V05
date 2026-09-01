import type { EnterpriseTree } from "../types/uns";
import { api } from "../api/client";
import { useState } from "react";

interface Props {
  tree: EnterpriseTree[];
  loading: boolean;
  onOpen: (enterpriseId: string) => void;
  onRefresh: () => void;
}

function countNodes(e: EnterpriseTree) {
  let n = 0;
  e.sites.forEach(s => { n++; s.areas.forEach(a => { n++; a.lines.forEach(l => { n++; l.cells.forEach(c => { n++; n += c.assets.length; }); }); }); });
  return n;
}

export function CatalogView({ tree, loading, onOpen, onRefresh }: Props) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [showForm, setShowForm] = useState(false);

  const totalNodes = tree.reduce((acc, e) => acc + countNodes(e), 0);
  const totalAssets = tree.reduce((acc, e) => acc + e.sites.flatMap(s => s.areas.flatMap(a => a.lines.flatMap(l => l.cells.flatMap(c => c.assets)))).length, 0);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.enterprises.create({ name: newName.trim() });
      setNewName("");
      setShowForm(false);
      onRefresh();
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Delete this namespace and all its contents?")) return;
    await api.enterprises.delete(id);
    onRefresh();
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-8 space-y-6">
        {/* Page header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Unified Namespaces</h1>
            <p className="text-ink-secondary text-sm mt-1">
              Manage your ISA-95 namespace hierarchy and descriptive payloads
            </p>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-ink text-white text-sm rounded font-medium hover:bg-ink/90"
          >
            + New UNS
          </button>
        </div>

        {/* Stats strip */}
        <div className="grid grid-cols-4 gap-px bg-border rounded-lg overflow-hidden border border-border">
          {[
            { label: "NAMESPACES", value: tree.length },
            { label: "TOTAL NODES", value: totalNodes },
            { label: "ASSETS", value: totalAssets },
            { label: "NEED ATTENTION", value: 0 },
          ].map(m => (
            <div key={m.label} className="bg-surface px-6 py-4">
              <div className="text-2xl font-semibold text-ink">{m.value}</div>
              <div className="text-[10px] tracking-widest text-ink-muted mt-1">{m.label}</div>
            </div>
          ))}
        </div>

        {/* Create form */}
        {showForm && (
          <div className="bg-surface border border-border rounded-lg p-4 flex items-center gap-3">
            <input
              autoFocus
              className="flex-1 border border-border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="Namespace name (e.g. ACME Corp)"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleCreate()}
            />
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="px-4 py-1.5 bg-ink text-white text-sm rounded disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create"}
            </button>
            <button onClick={() => setShowForm(false)} className="text-ink-muted text-sm hover:text-ink">
              Cancel
            </button>
          </div>
        )}

        {/* Table */}
        <div className="bg-surface border border-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[1fr_120px_80px_80px_80px_100px] text-[10px] tracking-widest text-ink-muted px-6 py-2.5 border-b border-border-subtle bg-surface-subtle">
            <span>NAMESPACE</span>
            <span>ROOT TOPIC</span>
            <span>NODES</span>
            <span>ASSETS</span>
            <span>SITES</span>
            <span>STATUS</span>
          </div>
          {loading ? (
            <div className="px-6 py-8 text-ink-muted text-sm">Loading…</div>
          ) : tree.length === 0 ? (
            <div className="px-6 py-12 text-center text-ink-muted text-sm">
              No namespaces yet. Create your first UNS to get started.
            </div>
          ) : (
            tree.map(e => {
              const nodes = countNodes(e);
              const assets = e.sites.flatMap(s => s.areas.flatMap(a => a.lines.flatMap(l => l.cells.flatMap(c => c.assets)))).length;
              return (
                <div
                  key={e.id}
                  onClick={() => onOpen(e.id)}
                  className="grid grid-cols-[1fr_120px_80px_80px_80px_100px] px-6 py-4 border-b border-border-subtle hover:bg-surface-subtle cursor-pointer group"
                >
                  <div>
                    <div className="font-medium text-ink text-sm group-hover:text-accent">{e.name}</div>
                    {e.description && <div className="text-ink-muted text-xs mt-0.5">{e.description}</div>}
                  </div>
                  <div className="text-ink-secondary text-xs self-center font-mono">{e.name.toLowerCase().replace(/\s+/g, "-")}</div>
                  <div className="text-ink text-sm self-center">{nodes}</div>
                  <div className="text-ink text-sm self-center">{assets}</div>
                  <div className="text-ink text-sm self-center">{e.sites.length}</div>
                  <div className="self-center flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
                    <span className="text-success text-xs">SYNCED</span>
                    <button
                      onClick={ev => handleDelete(e.id, ev)}
                      className="ml-2 text-ink-muted hover:text-danger opacity-0 group-hover:opacity-100 text-xs transition-opacity"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
