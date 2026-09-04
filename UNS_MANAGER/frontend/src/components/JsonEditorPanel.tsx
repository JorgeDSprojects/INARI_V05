import { useEffect, useState } from "react";
import type { Asset } from "../types/uns";

interface Props {
  payload: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
  onValidChange: (valid: boolean) => void;
  unsTopic: string;
  asset: Asset | null;
  readOnly: boolean;
  onEdit: () => void;
  lines?: number;
}

export function JsonEditorPanel({ payload, onChange, onValidChange, unsTopic, asset, readOnly, onEdit }: Props) {
  const [text, setText] = useState(() => JSON.stringify(payload, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(JSON.stringify(payload, null, 2));
  }, [payload]);

  const handleChange = (raw: string) => {
    setText(raw);
    try {
      const parsed = JSON.parse(raw);
      setError(null);
      onValidChange(true);
      onChange(parsed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
      onValidChange(false);
    }
  };

  const lineNumbers = Array.from({ length: text.split("\n").length }, (_, i) => i + 1).join("\n");

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* JSON Editor */}
      <div className="flex-1 flex flex-col overflow-hidden bg-code-bg">
        {/* Editor toolbar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-[#18222C] border-b border-white/5">
          <div className="flex items-center gap-2">
            <span className="text-[#71B9E3] text-xs">◆</span>
            <span className="text-code-ink text-xs font-mono">_descriptive.json</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-[#8DA0B0] text-[10px] font-mono">{readOnly ? "READ ONLY" : "EDIT"} · JSON · UTF-8</span>
            {readOnly && (
              <button
                onClick={onEdit}
                className="px-2 py-0.5 text-[10px] border border-white/10 text-code-muted hover:text-code-ink rounded font-mono"
              >
                Edit payload
              </button>
            )}
          </div>
        </div>

        {/* Editor body */}
        <div className="flex flex-1 overflow-auto">
          {/* Line numbers */}
          <div className="px-3 py-4 text-right select-none shrink-0 w-12">
            <pre className="text-code-muted text-xs font-mono leading-5">{lineNumbers}</pre>
          </div>
          {/* Code */}
          <div className="flex-1 py-4 pr-4">
            {readOnly ? (
              <pre className="text-code-ink text-xs font-mono leading-5 whitespace-pre-wrap break-all">{text}</pre>
            ) : (
              <textarea
                className="w-full h-full bg-transparent text-code-ink text-xs font-mono leading-5 resize-none focus:outline-none caret-white"
                value={text}
                onChange={e => handleChange(e.target.value)}
                spellCheck={false}
                style={{ minHeight: "100%" }}
              />
            )}
          </div>
        </div>

        {/* Error bar */}
        {error && (
          <div className="px-4 py-1.5 bg-danger/20 text-danger text-xs font-mono border-t border-danger/30">
            {error}
          </div>
        )}
      </div>

      {/* Inspector panel */}
      <div className="w-64 flex flex-col border-l border-border bg-surface overflow-y-auto shrink-0">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <span className="text-[10px] tracking-widest text-ink font-semibold">PAYLOAD DETAILS</span>
        </div>

        {/* MQTT Topic */}
        <div className="px-4 py-3 border-b border-border-subtle">
          <div className="text-[10px] tracking-widest text-ink-muted mb-2">FULL MQTT TOPIC</div>
          <div className="bg-surface-subtle rounded px-2 py-2">
            <span className="text-ink text-xs font-mono break-all leading-relaxed">{unsTopic}</span>
          </div>
        </div>

        {/* Properties */}
        <div className="px-4 py-3 border-b border-border-subtle space-y-3">
          {[
            { label: "Retain", value: "Enabled", color: "text-ink" },
            { label: "QoS", value: "1", color: "text-ink" },
            { label: "Schema", value: "Not assigned", color: "text-warning" },
            { label: "DB revision", value: asset ? "active" : "–", color: "text-ink" },
            { label: "Last modified", value: asset ? new Date(asset.updated_at).toLocaleString() : "–", color: "text-ink" },
          ].map(p => (
            <div key={p.label} className="flex items-start justify-between gap-2">
              <span className="text-xs text-ink-secondary shrink-0">{p.label}</span>
              <span className={`text-xs ${p.color} text-right`}>{p.value}</span>
            </div>
          ))}
        </div>

        {/* Validation */}
        <div className="px-4 py-3">
          <div className="text-[10px] tracking-widest text-ink-muted mb-2">VALIDATION</div>
          <div className={`flex items-center gap-2 rounded px-3 py-2 ${error ? "bg-danger-soft" : "bg-success-soft"}`}>
            <span className={`text-sm ${error ? "text-danger" : "text-success"}`}>{error ? "✗" : "✓"}</span>
            <span className={`text-xs ${error ? "text-danger" : "text-success"}`}>
              {error ? "Invalid JSON" : "Valid JSON · Schema OK"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
