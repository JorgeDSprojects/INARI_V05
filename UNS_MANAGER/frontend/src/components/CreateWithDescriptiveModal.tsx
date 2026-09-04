import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { NodeType } from "../types/uns";

interface Props {
  cellId: string;
  onClose: () => void;
  onCreated: () => void;
}

export function CreateWithDescriptiveModal({ cellId, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nodeTypes, setNodeTypes] = useState<NodeType[]>([]);
  const [selectedNodeTypeId, setSelectedNodeTypeId] = useState<string>("");
  const [payloadText, setPayloadText] = useState("{\n  \n}");
  const [payloadError, setPayloadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    api.nodeTypes.list().then(setNodeTypes).catch(() => {});
  }, []);

  // When a node type is selected, load its schema as a template payload
  useEffect(() => {
    if (!selectedNodeTypeId) { setPayloadText("{\n  \n}"); return; }
    const nt = nodeTypes.find(n => n.id === selectedNodeTypeId);
    if (!nt) return;
    // Build a template from the schema's properties
    const props = (nt.json_schema.properties ?? {}) as Record<string, unknown>;
    const template: Record<string, unknown> = {};
    for (const [key, def] of Object.entries(props)) {
      const d = def as Record<string, unknown>;
      if (d.type === "number") template[key] = 0;
      else if (d.type === "boolean") template[key] = false;
      else if (d.type === "array") template[key] = [];
      else if (d.type === "object") template[key] = {};
      else template[key] = "";
    }
    setPayloadText(JSON.stringify(template, null, 2));
    setPayloadError(null);
  }, [selectedNodeTypeId, nodeTypes]);

  const handlePayloadChange = (text: string) => {
    setPayloadText(text);
    try { JSON.parse(text); setPayloadError(null); }
    catch (e: unknown) { setPayloadError(e instanceof Error ? e.message : "Invalid JSON"); }
  };

  const handleCreate = async () => {
    if (!name.trim() || payloadError) return;
    let parsed: Record<string, unknown> | undefined;
    try { parsed = JSON.parse(payloadText); }
    catch { setPayloadError("Invalid JSON"); return; }
    setSaving(true);
    setSaveError(null);
    try {
      await api.assets.create(cellId, {
        name: name.trim(),
        description: description.trim() || undefined,
        descriptive_payload: parsed,
        node_type_id: selectedNodeTypeId || undefined,
      });
      onCreated();
      onClose();
    } catch {
      setSaveError("Failed to create asset. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const lineNumbers = payloadText.split("\n").map((_, i) => i + 1).join("\n");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-xl border border-border w-full max-w-2xl shadow-xl overflow-hidden flex flex-col" style={{ maxHeight: "90vh" }}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <h2 className="text-base font-semibold text-ink">New Asset</h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-lg">&#x2715;</button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Fields */}
          <div className="px-6 py-5 space-y-4 border-b border-border">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">NAME *</label>
                <input autoFocus type="text" placeholder="TempSensor_01"
                  value={name} onChange={e => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">NODE TYPE</label>
                <select value={selectedNodeTypeId} onChange={e => setSelectedNodeTypeId(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent">
                  <option value="">&#x2014; None &#x2014;</option>
                  {nodeTypes.map(nt => (
                    <option key={nt.id} value={nt.id}>{nt.name}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">DESCRIPTION</label>
              <input type="text" placeholder="Optional description"
                value={description} onChange={e => setDescription(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
            </div>
          </div>

          {/* Inline JSON editor */}
          <div className="flex flex-col bg-code-bg" style={{ minHeight: "220px" }}>
            <div className="flex items-center justify-between px-4 py-2.5 bg-[#18222C] border-b border-white/5">
              <div className="flex items-center gap-2">
                <span className="text-[#71B9E3] text-xs">&#x25C6;</span>
                <span className="text-code-ink text-xs font-mono">_descriptive.json</span>
              </div>
              <span className="text-[#8DA0B0] text-[10px] font-mono">EDIT &middot; JSON &middot; UTF-8</span>
            </div>
            <div className="flex flex-1 overflow-auto" style={{ minHeight: "180px" }}>
              <div className="px-3 py-4 text-right select-none shrink-0 w-10">
                <pre className="text-code-muted text-xs font-mono leading-5">{lineNumbers}</pre>
              </div>
              <div className="flex-1 py-4 pr-4">
                <textarea value={payloadText} spellCheck={false}
                  onChange={e => handlePayloadChange(e.target.value)}
                  className="w-full h-full bg-transparent text-code-ink text-xs font-mono leading-5 resize-none focus:outline-none caret-white"
                  style={{ minHeight: "160px" }} />
              </div>
            </div>
            {payloadError && (
              <div className="px-4 py-1.5 bg-danger/20 text-danger text-xs font-mono border-t border-danger/30">
                {payloadError}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-surface-subtle shrink-0">
          <div className="flex items-center gap-1">
            {payloadError ? (
              <><span className="text-danger text-xs">&#x2717;</span><span className="text-danger text-xs">Invalid JSON</span></>
            ) : (
              <><span className="text-success text-xs">&#x2713;</span><span className="text-success text-xs">Valid JSON</span></>
            )}
          </div>
          {saveError && (
            <span className="text-danger text-xs px-2">{saveError}</span>
          )}
          <div className="flex gap-2">
            <button onClick={onClose} className="px-4 py-2 text-sm text-ink-secondary border border-border rounded hover:bg-surface">
              Cancel
            </button>
            <button onClick={handleCreate} disabled={saving || !name.trim() || !!payloadError}
              className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50 hover:bg-ink/90">
              {saving ? "Creating…" : "Create asset"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
