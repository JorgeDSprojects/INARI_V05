import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";
import type { NodeType } from "../types/uns";

function extractRequiredFields(schema: Record<string, unknown>): string {
  const required = schema.required as string[] | undefined;
  if (!required || required.length === 0) return "—";
  return required.slice(0, 3).join(", ") + (required.length > 3 ? "…" : "");
}

export function NodeTypesView() {
  const [nodeTypes, setNodeTypes] = useState<NodeType[]>([]);
  const [selected, setSelected] = useState<NodeType | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formSchema, setFormSchema] = useState("{\n  \n}");
  const [formSchemaError, setFormSchemaError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editSchema, setEditSchema] = useState("");
  const [editSchemaError, setEditSchemaError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);

  const load = useCallback(async () => {
    setNodeTypes(await api.nodeTypes.list());
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (selected) {
      setEditSchema(JSON.stringify(selected.json_schema, null, 2));
      setEditSchemaError(null);
      setEditMode(false);
    }
  }, [selected]);

  const parseSchema = (text: string): [Record<string, unknown> | null, string | null] => {
    try { return [JSON.parse(text), null]; }
    catch (e: unknown) { return [null, e instanceof Error ? e.message : "Invalid JSON"]; }
  };

  const handleCreate = async () => {
    const [parsed, err] = parseSchema(formSchema);
    if (err) { setFormSchemaError(err); return; }
    setSaving(true);
    try {
      const nt = await api.nodeTypes.create({
        name: formName.trim(),
        description: formDesc.trim() || undefined,
        json_schema: parsed!,
      });
      setNodeTypes(prev => [...prev, nt]);
      setShowForm(false);
      setFormName(""); setFormDesc(""); setFormSchema("{\n  \n}"); setFormSchemaError(null);
    } finally { setSaving(false); }
  };

  const handleSaveEdit = async () => {
    if (!selected) return;
    const [parsed, err] = parseSchema(editSchema);
    if (err) { setEditSchemaError(err); return; }
    setSavingEdit(true);
    try {
      const updated = await api.nodeTypes.update(selected.id, { json_schema: parsed! });
      setNodeTypes(prev => prev.map(n => n.id === updated.id ? updated : n));
      setSelected(updated);
      setEditMode(false);
    } finally { setSavingEdit(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this node type? Existing assets with this type will lose their schema.")) return;
    await api.nodeTypes.delete(id);
    setNodeTypes(prev => prev.filter(n => n.id !== id));
    if (selected?.id === id) setSelected(null);
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left panel */}
      <div className="w-96 border-r border-border flex flex-col overflow-hidden bg-surface shrink-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-ink">Node type catalog</h2>
          <button onClick={() => setShowForm(v => !v)}
            className="px-3 py-1.5 text-xs bg-ink text-white rounded hover:bg-ink/90">
            + New node type
          </button>
        </div>

        {showForm && (
          <div className="px-5 py-4 border-b border-border space-y-3 bg-surface-subtle">
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1">NAME</label>
              <input type="text" placeholder="Temperature Sensor" value={formName}
                onChange={e => setFormName(e.target.value)}
                className="w-full px-3 py-1.5 text-sm border border-border rounded bg-surface text-ink focus:outline-none focus:border-accent" />
            </div>
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1">DESCRIPTION</label>
              <input type="text" placeholder="Optional" value={formDesc}
                onChange={e => setFormDesc(e.target.value)}
                className="w-full px-3 py-1.5 text-sm border border-border rounded bg-surface text-ink focus:outline-none focus:border-accent" />
            </div>
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1">JSON SCHEMA</label>
              <textarea value={formSchema} rows={6} spellCheck={false}
                onChange={e => { setFormSchema(e.target.value); const [, err] = parseSchema(e.target.value); setFormSchemaError(err); }}
                className="w-full px-3 py-2 text-xs font-mono border border-border rounded bg-code-bg text-code-ink focus:outline-none resize-none" />
              {formSchemaError && <p className="text-danger text-xs mt-1 font-mono">{formSchemaError}</p>}
            </div>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={saving || !formName.trim() || !!formSchemaError}
                className="px-3 py-1.5 text-xs bg-ink text-white rounded disabled:opacity-50">
                {saving ? "Saving…" : "Save"}
              </button>
              <button onClick={() => setShowForm(false)}
                className="px-3 py-1.5 text-xs text-ink-secondary border border-border rounded">
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {nodeTypes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-ink-muted text-sm py-12">
              No node types defined
            </div>
          ) : nodeTypes.map(nt => (
            <button key={nt.id} onClick={() => setSelected(nt)}
              className={`w-full text-left px-5 py-3.5 border-b border-border-subtle flex items-start justify-between group hover:bg-surface-subtle ${selected?.id === nt.id ? "bg-surface-subtle" : ""}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink truncate">{nt.name}</div>
                <div className="text-xs text-ink-muted mt-0.5 truncate">
                  required: {extractRequiredFields(nt.json_schema)}
                </div>
              </div>
              <button onClick={e => { e.stopPropagation(); handleDelete(nt.id); }}
                className="opacity-0 group-hover:opacity-100 text-danger text-[10px] px-1.5 py-0.5 rounded hover:bg-danger-soft ml-2 shrink-0 transition-opacity">
                ✕
              </button>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel */}
      {selected ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
            <div>
              <h3 className="text-lg font-semibold text-ink">{selected.name}</h3>
              {selected.description && (
                <p className="text-sm text-ink-muted mt-0.5">{selected.description}</p>
              )}
            </div>
            <button onClick={() => { setEditMode(v => !v); setEditSchemaError(null); }}
              className="px-3 py-1.5 text-sm border border-border rounded text-ink hover:bg-surface-subtle">
              {editMode ? "Cancel" : "Edit schema"}
            </button>
          </div>

          <div className="flex-1 flex flex-col overflow-hidden bg-code-bg">
            <div className="flex items-center justify-between px-4 py-2.5 bg-[#18222C] border-b border-white/5 shrink-0">
              <span className="text-code-ink text-xs font-mono">json_schema.json</span>
              <span className="text-[#8DA0B0] text-[10px] font-mono">
                {editMode ? "EDIT" : "READ ONLY"} · JSON Schema draft-7
              </span>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {editMode ? (
                <div className="flex flex-col gap-3">
                  <textarea value={editSchema} spellCheck={false}
                    onChange={e => { setEditSchema(e.target.value); const [, err] = parseSchema(e.target.value); setEditSchemaError(err); }}
                    className="w-full bg-transparent text-code-ink text-xs font-mono leading-5 resize-none focus:outline-none caret-white"
                    style={{ minHeight: "300px" }} />
                  {editSchemaError && (
                    <p className="text-danger text-xs font-mono">{editSchemaError}</p>
                  )}
                  <div>
                    <button onClick={handleSaveEdit} disabled={savingEdit || !!editSchemaError}
                      className="px-4 py-2 text-sm bg-ink text-white rounded disabled:opacity-50">
                      {savingEdit ? "Saving…" : "Save schema"}
                    </button>
                  </div>
                </div>
              ) : (
                <pre className="text-code-ink text-xs font-mono leading-5 whitespace-pre-wrap">
                  {JSON.stringify(selected.json_schema, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
          Select a node type to view its schema
        </div>
      )}
    </div>
  );
}
