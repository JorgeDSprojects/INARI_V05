import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { EnterpriseTree, SelectedNode, Asset } from "../types/uns";
import { JsonEditorPanel } from "./JsonEditorPanel";

interface Props {
  enterprise: EnterpriseTree;
  selected: SelectedNode | null;
  onRefresh: () => void;
}

type Tab = "definition" | "_descriptive" | "branches" | "_operational" | "_analytical";

export function NodeWorkspace({ enterprise, selected, onRefresh }: Props) {
  const [tab, setTab] = useState<Tab>("_descriptive");
  const [asset, setAsset] = useState<Asset | null>(null);
  const [payload, setPayload] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [published, setPublished] = useState(false);
  const [jsonValid, setJsonValid] = useState(true);
  const [editMode, setEditMode] = useState(false);

  useEffect(() => {
    if (selected?.level === "asset" && selected.parentIds.cell_id) {
      api.assets.list(selected.parentIds.cell_id).then(list => {
        const found = list.find(a => a.id === selected.id);
        if (found) { setAsset(found); setPayload(found.descriptive_payload ?? {}); }
      });
    } else {
      setAsset(null);
    }
  }, [selected]);

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
  const unsTopic = asset?.uns_topic ?? buildTopic(enterprise, selected, nodeName);

  const handleSave = async () => {
    if (!asset || !selected.parentIds.cell_id) return;
    setSaving(true);
    try {
      const updated = await api.assets.update(selected.parentIds.cell_id, asset.id, { descriptive_payload: payload });
      setAsset(updated);
      setEditMode(false);
      onRefresh();
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    if (!asset || !selected.parentIds.cell_id) return;
    setSaving(true);
    try {
      await api.assets.update(selected.parentIds.cell_id, asset.id, { descriptive_payload: payload });
      await api.assets.publish(selected.parentIds.cell_id, asset.id);
      setPublished(true);
      setTimeout(() => setPublished(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  const TABS: { id: Tab; label: string; dot?: "success" | "muted" }[] = [
    { id: "definition", label: "Definition" },
    { id: "_descriptive", label: "_descriptive", dot: asset ? "success" : "muted" },
    { id: "branches", label: "Data branches · 0", dot: "muted" },
    { id: "_operational", label: "_operational", dot: "muted" },
    { id: "_analytical", label: "_analytical", dot: "muted" },
  ];

  const payloadStr = JSON.stringify(payload, null, 2);
  const lines = payloadStr.split("\n").length;
  const byteSize = new TextEncoder().encode(payloadStr).length;

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
              {asset && (
                <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-success-soft text-success text-[10px] font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />SYNCED
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

      {/* Meta bar */}
      {tab === "_descriptive" && (
        <div className="flex items-center justify-between px-6 py-2.5 bg-surface-subtle border-b border-border-subtle">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-accent-soft text-accent text-[10px] font-medium">
              ◈ RETAINED
            </span>
            <span className="text-ink-secondary text-xs">application/json</span>
            <span className="text-ink-muted text-[10px]">{byteSize} BYTES</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1">
              {jsonValid ? (
                <><span className="text-success text-xs">✓</span><span className="text-success text-xs">Valid JSON</span></>
              ) : (
                <><span className="text-danger text-xs">✗</span><span className="text-danger text-xs">Invalid JSON</span></>
              )}
            </div>
            <span className="text-ink-muted text-[10px]">POSTGRES REV {asset ? "active" : "–"}</span>
            {editMode && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={saving || !jsonValid}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-ink text-white text-xs rounded disabled:opacity-50"
                >
                  SAVE
                </button>
                <button
                  onClick={handlePublish}
                  disabled={saving || !jsonValid}
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
        {tab === "_descriptive" && selected.level === "asset" ? (
          <JsonEditorPanel
            payload={payload}
            onChange={setPayload}
            onValidChange={setJsonValid}
            unsTopic={unsTopic}
            asset={asset}
            readOnly={!editMode}
            onEdit={() => setEditMode(true)}
            lines={lines}
          />
        ) : tab === "definition" ? (
          <DefinitionPanel enterprise={enterprise} selected={selected} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
            {tab === "branches" ? "No data branch consumers registered." : `${tab} payload comes from external services at runtime.`}
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
