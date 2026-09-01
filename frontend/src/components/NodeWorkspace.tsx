import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { DataBranch, EnterpriseTree, SelectedNode, Asset, SyncStatus } from "../types/uns";
import { JsonEditorPanel } from "./JsonEditorPanel";

interface Props {
  enterprise: EnterpriseTree;
  selected: SelectedNode | null;
  onRefresh: () => void;
}

type Tab = "definition" | "_descriptive" | "_informative" | "branches" | "_operational" | "_analytical";

export function NodeWorkspace({ enterprise, selected, onRefresh }: Props) {
  const [tab, setTab] = useState<Tab>("_descriptive");
  const [asset, setAsset] = useState<Asset | null>(null);
  const [payload, setPayload] = useState<Record<string, unknown>>({});
  const [infoPayload, setInfoPayload] = useState<Record<string, unknown>>({});
  const [infoJsonValid, setInfoJsonValid] = useState(true);
  const [infoEditMode, setInfoEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [published, setPublished] = useState(false);
  const [jsonValid, setJsonValid] = useState(true);
  const [editMode, setEditMode] = useState(false);
  const [branches, setBranches] = useState<DataBranch[]>([]);
  const [branchesLoading, setBranchesLoading] = useState(false);
  const [branchesError, setBranchesError] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    // Reset all payload state on node change
    setPayload({});
    setInfoPayload({});
    setEditMode(false);
    setInfoEditMode(false);
    setAsset(null);
    setSyncStatus(null);
    setSyncError(null);
    setBranches([]);

    if (!selected) return;

    // Load payloads from the already-loaded tree (works for all levels)
    const node = findNodeInTree(enterprise, selected);
    if (node) {
      setPayload(node.descriptive_payload ?? {});
      setInfoPayload(node.informative_payload ?? {});
    }

    // For assets: also fetch the full Asset object from the API
    // (needed for uns_topic, node_type_id, and sync status)
    if (selected.level === "asset" && selected.parentIds.cell_id) {
      api.assets.list(selected.parentIds.cell_id).then(list => {
        const found = list.find(a => a.id === selected.id);
        if (found) {
          setAsset(found);
          setPayload(found.descriptive_payload ?? {});
          setInfoPayload(found.informative_payload ?? {});
          api.syncStatus.get(selected.parentIds.cell_id, found.id)
            .then(setSyncStatus)
            .catch(() => setSyncStatus(null));
        }
      });
    }
  }, [selected, enterprise]);

  useEffect(() => {
    if (tab !== "branches" || !asset || !selected?.parentIds.cell_id) return;
    setBranches([]);
    setBranchesLoading(true);
    setBranchesError(false);
    api.branches.list(selected.parentIds.cell_id, asset.id)
      .then(data => { setBranches(data); setBranchesLoading(false); })
      .catch(() => { setBranchesError(true); setBranchesLoading(false); });
  }, [tab, asset, selected]);

  if (!selected) {
    return (
      <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
        Select a node in the tree to inspect it
      </div>
    );
  }

  const nodeName = getNodeName(enterprise, selected);
  const nodePath = getNodePath(enterprise, selected);
  const nodeType = selected.level.toUpperCase();

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const isInfo = tab === "_informative";
      const body = isInfo
        ? { informative_payload: infoPayload }
        : { descriptive_payload: payload };
      switch (selected.level) {
        case "enterprise":
          await api.enterprises.update(selected.id, body); break;
        case "site":
          await api.sites.update(selected.parentIds.enterprise_id, selected.id, body); break;
        case "area":
          await api.areas.update(selected.parentIds.site_id, selected.id, body); break;
        case "line":
          await api.lines.update(selected.parentIds.area_id, selected.id, body); break;
        case "cell":
          await api.cells.update(selected.parentIds.line_id, selected.id, body); break;
        case "asset":
          await api.assets.update(selected.parentIds.cell_id, selected.id, body); break;
      }
      if (isInfo) setInfoEditMode(false); else setEditMode(false);
      onRefresh();
    } finally { setSaving(false); }
  };

  const handlePublish = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const isInfo = tab === "_informative";
      const body = isInfo
        ? { informative_payload: infoPayload }
        : { descriptive_payload: payload };
      switch (selected.level) {
        case "enterprise":
          await api.enterprises.update(selected.id, body);
          await api.enterprises.publish(selected.id); break;
        case "site":
          await api.sites.update(selected.parentIds.enterprise_id, selected.id, body);
          await api.sites.publish(selected.parentIds.enterprise_id, selected.id); break;
        case "area":
          await api.areas.update(selected.parentIds.site_id, selected.id, body);
          await api.areas.publish(selected.parentIds.site_id, selected.id); break;
        case "line":
          await api.lines.update(selected.parentIds.area_id, selected.id, body);
          await api.lines.publish(selected.parentIds.area_id, selected.id); break;
        case "cell":
          await api.cells.update(selected.parentIds.line_id, selected.id, body);
          await api.cells.publish(selected.parentIds.line_id, selected.id); break;
        case "asset": {
          await api.assets.update(selected.parentIds.cell_id, selected.id, body);
          await api.assets.publish(selected.parentIds.cell_id, selected.id);
          const s = await api.syncStatus.get(selected.parentIds.cell_id, selected.id);
          setSyncStatus(s);
          break;
        }
      }
      setPublished(true);
      setTimeout(() => setPublished(false), 3000);
      onRefresh();
    } finally { setSaving(false); }
  };

  const TABS: { id: Tab; label: string; dot?: "success" | "muted" }[] = [
    { id: "definition", label: "Definition" },
    { id: "_descriptive", label: "_descriptive", dot: Object.keys(payload).length > 0 ? "success" : "muted" },
    { id: "_informative", label: "_informative", dot: Object.keys(infoPayload).length > 0 ? "success" : "muted" },
    { id: "branches", label: `Data branches · ${branches.length}`, dot: branches.length > 0 ? "success" : "muted" },
    { id: "_operational", label: "_operational", dot: "muted" },
    { id: "_analytical", label: "_analytical", dot: "muted" },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-surface">
      {/* Node header */}
      <div className="px-6 pt-4 pb-0 border-b border-border">
        <div className="flex items-start justify-between pb-4">
          <div>
            <div className="text-xs text-ink-muted font-mono mb-1">{nodePath}</div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-semibold text-ink">{nodeName}</h2>
              <span className="px-2 py-0.5 rounded bg-surface-muted text-ink-secondary text-[10px] font-medium tracking-wider">{nodeType}</span>
              {asset && syncStatus && (
                <span className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${
                  syncStatus.synced ? "bg-success-soft text-success" : "bg-danger-soft text-danger"
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full inline-block ${syncStatus.synced ? "bg-success" : "bg-danger"}`} />
                  {syncStatus.synced ? "SYNCED" : "UNSYNCED"}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setEditMode(!editMode)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm border border-border rounded text-ink hover:bg-surface-subtle"
            >
              Edit node
            </button>
            {selected.level !== "asset" && (
              <button
                className="flex items-center gap-1.5 px-3 py-2 text-sm bg-ink text-white rounded hover:bg-ink/90"
              >
                + Add child
              </button>
            )}
          </div>
        </div>

        {/* Unsynced banner */}
        {asset && syncStatus && !syncStatus.synced && (
          <div className="-mx-6 px-6 py-3 bg-danger/10 border-b border-danger/20 flex items-start justify-between gap-4">
            <div className="flex items-start gap-2">
              <span className="text-danger text-sm mt-0.5">⚠</span>
              <div>
                <p className="text-danger text-sm font-medium">Out of sync with EMQX</p>
                <p className="text-danger/70 text-xs mt-0.5">{syncStatus.diff_note}</p>
                {syncError && <p className="text-danger text-xs mt-1">{syncError}</p>}
              </div>
            </div>
            <button
              onClick={async () => {
                if (!selected?.parentIds.cell_id || !asset) return;
                setSaving(true);
                setSyncError(null);
                try {
                  await api.assets.update(selected.parentIds.cell_id, asset.id, { descriptive_payload: payload });
                  await api.assets.publish(selected.parentIds.cell_id, asset.id);
                  const s = await api.syncStatus.get(selected.parentIds.cell_id, asset.id);
                  setSyncStatus(s);
                  setPublished(true);
                  setTimeout(() => setPublished(false), 3000);
                } catch {
                  setSyncError("Re-sync failed. Please try again.");
                } finally {
                  setSaving(false);
                }
              }}
              disabled={saving}
              className="px-3 py-1.5 text-xs bg-danger text-white rounded shrink-0 disabled:opacity-50"
            >
              Re-sync
            </button>
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-0">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm border-b-2 transition-colors ${
                tab === t.id
                  ? "border-ink text-ink font-medium"
                  : "border-transparent text-ink-secondary hover:text-ink"
              }`}
            >
              {t.dot && (
                <span className={`w-1.5 h-1.5 rounded-full inline-block ${t.dot === "success" ? "bg-success" : "bg-ink-muted/50"}`} />
              )}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Meta bar — _descriptive and _informative */}
      {(tab === "_descriptive" || tab === "_informative") && (
        <div className="flex items-center justify-between px-6 py-2.5 bg-surface-subtle border-b border-border-subtle">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-accent-soft text-accent text-[10px] font-medium">
              ◈ RETAINED
            </span>
            <span className="text-ink-secondary text-xs">application/json</span>
            <span className="text-ink-muted text-[10px]">
              {new TextEncoder().encode(
                JSON.stringify(tab === "_informative" ? infoPayload : payload, null, 2)
              ).length} BYTES
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1">
              {(tab === "_informative" ? infoJsonValid : jsonValid) ? (
                <><span className="text-success text-xs">✓</span><span className="text-success text-xs">Valid JSON</span></>
              ) : (
                <><span className="text-danger text-xs">✗</span><span className="text-danger text-xs">Invalid JSON</span></>
              )}
            </div>
            <span className="text-ink-muted text-[10px]">POSTGRES REV {asset ? "active" : "–"}</span>
            {(tab === "_descriptive" ? editMode : infoEditMode) && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={saving || !(tab === "_informative" ? infoJsonValid : jsonValid)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-ink text-white text-xs rounded disabled:opacity-50"
                >
                  SAVE
                </button>
                <button
                  onClick={handlePublish}
                  disabled={saving || !(tab === "_informative" ? infoJsonValid : jsonValid)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-accent text-white text-xs rounded disabled:opacity-50"
                >
                  {published ? "PUBLISHED ✓" : "SAVE & PUBLISH"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Work area */}
      <div className="flex flex-1 overflow-hidden">
        {tab === "_descriptive" ? (
          <JsonEditorPanel
            payload={payload}
            onChange={setPayload}
            onValidChange={setJsonValid}
            unsTopic={asset?.uns_topic ?? buildTopic(enterprise, selected, nodeName)}
            asset={asset}
            readOnly={!editMode}
            onEdit={() => setEditMode(true)}
            lines={JSON.stringify(payload, null, 2).split("\n").length}
          />
        ) : tab === "_informative" ? (
          <JsonEditorPanel
            payload={infoPayload}
            onChange={setInfoPayload}
            onValidChange={setInfoJsonValid}
            unsTopic={(asset?.uns_topic ?? buildTopic(enterprise, selected, nodeName)).replace("_descriptive", "_informative")}
            asset={null}
            readOnly={!infoEditMode}
            onEdit={() => setInfoEditMode(true)}
            lines={JSON.stringify(infoPayload, null, 2).split("\n").length}
          />
        ) : tab === "definition" ? (
          <DefinitionPanel enterprise={enterprise} selected={selected} />
        ) : tab === "branches" ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle bg-surface-subtle">
              <span className="text-xs text-ink-muted">{branches.length} active subscriber{branches.length !== 1 ? "s" : ""}</span>
              <button
                onClick={() => {
                  if (!asset || !selected?.parentIds.cell_id) return;
                  setBranchesError(false);
                  setBranchesLoading(true);
                  api.branches.list(selected.parentIds.cell_id, asset.id)
                    .then(data => { setBranches(data); setBranchesLoading(false); })
                    .catch(() => { setBranchesError(true); setBranchesLoading(false); });
                }}
                className="text-xs text-ink-muted hover:text-ink border border-border-subtle rounded px-2 py-0.5"
              >
                ↺ Refresh
              </button>
            </div>
            {branchesLoading ? (
              <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">Loading…</div>
            ) : branchesError ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center space-y-1">
                  <p className="text-warning text-sm">Branch discovery unavailable</p>
                  <p className="text-ink-muted text-xs">EMQX API unreachable or no broker configured</p>
                </div>
              </div>
            ) : branches.length === 0 ? (
              <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
                No active subscribers on this topic
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto">
                <div className="grid grid-cols-[1fr_1fr_60px] text-[10px] tracking-widest text-ink-muted px-5 py-2 border-b border-border-subtle bg-surface-subtle">
                  <span>CLIENT ID</span><span>TOPIC FILTER</span><span>QOS</span>
                </div>
                {branches.map((b, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1fr_60px] px-5 py-3 border-b border-border-subtle hover:bg-surface-subtle text-sm">
                    <span className="text-ink font-mono text-xs truncate">{b.client_id}</span>
                    <span className="text-ink-secondary font-mono text-xs truncate">{b.topic_filter}</span>
                    <span className="text-ink-muted text-xs">QoS {b.qos}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
            {`${tab} payload comes from external services at runtime.`}
          </div>
        )}
      </div>
    </div>
  );
}

function DefinitionPanel({ enterprise, selected }: { enterprise: EnterpriseTree; selected: SelectedNode }) {
  const nodeName = getNodeName(enterprise, selected);
  return (
    <div className="flex-1 p-6 space-y-4 overflow-y-auto">
      <div className="grid grid-cols-2 gap-4 max-w-lg">
        {[
          ["Level", selected.level.toUpperCase()],
          ["Name", nodeName],
          ["ID", selected.id],
        ].map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] tracking-widest text-ink-muted mb-1">{k}</div>
            <div className="text-sm text-ink font-mono">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function getNodeName(enterprise: EnterpriseTree, selected: SelectedNode): string {
  for (const s of enterprise.sites) {
    if (selected.level === "site" && s.id === selected.id) return s.name;
    for (const a of s.areas) {
      if (selected.level === "area" && a.id === selected.id) return a.name;
      for (const l of a.lines) {
        if (selected.level === "line" && l.id === selected.id) return l.name;
        for (const c of l.cells) {
          if (selected.level === "cell" && c.id === selected.id) return c.name;
          for (const asset of c.assets) {
            if (selected.level === "asset" && asset.id === selected.id) return asset.name;
          }
        }
      }
    }
  }
  return selected.id;
}

function getNodePath(enterprise: EnterpriseTree, selected: SelectedNode): string {
  const parts: string[] = [enterprise.name.toLowerCase()];
  for (const s of enterprise.sites) {
    if (selected.level === "site" && s.id === selected.id) return parts.join(" / ");
    parts.push(s.name.toLowerCase());
    for (const a of s.areas) {
      if (selected.level === "area" && a.id === selected.id) return parts.join(" / ");
      parts.push(a.name.toLowerCase());
      for (const l of a.lines) {
        if (selected.level === "line" && l.id === selected.id) return parts.join(" / ");
        parts.push(l.name.toLowerCase());
        for (const c of l.cells) {
          if (selected.level === "cell" && c.id === selected.id) return parts.join(" / ");
          parts.push(c.name.toLowerCase());
          for (const asset of c.assets) {
            if (selected.level === "asset" && asset.id === selected.id) return parts.join(" / ");
          }
          parts.pop();
        }
        parts.pop();
      }
      parts.pop();
    }
    parts.pop();
  }
  return enterprise.name.toLowerCase();
}

function buildTopic(enterprise: EnterpriseTree, _selected: SelectedNode, name: string): string {
  return `spBv1/${enterprise.name.toLowerCase().replace(/\s+/g,"_")}/${name.toLowerCase().replace(/\s+/g,"_")}/_descriptive`;
}

type NodePayloads = {
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
};

function findNodeInTree(enterprise: EnterpriseTree, selected: SelectedNode): NodePayloads | null {
  if (selected.level === "enterprise" && enterprise.id === selected.id) return enterprise;
  for (const site of enterprise.sites) {
    if (selected.level === "site" && site.id === selected.id) return site;
    for (const area of site.areas) {
      if (selected.level === "area" && area.id === selected.id) return area;
      for (const line of area.lines) {
        if (selected.level === "line" && line.id === selected.id) return line;
        for (const cell of line.cells) {
          if (selected.level === "cell" && cell.id === selected.id) return cell;
          for (const asset of cell.assets) {
            if (selected.level === "asset" && asset.id === selected.id) return asset;
          }
        }
      }
    }
  }
  return null;
}
