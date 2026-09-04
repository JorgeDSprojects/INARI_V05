import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { resolveColor } from "../../lib/palette";
import type { ChartSignal, SignalTreeNode } from "../../types/dashboard";

function matchesFilter(node: SignalTreeNode, filter: string): boolean {
  if (!filter) return true;
  const needle = filter.toLowerCase();
  if (node.segment.toLowerCase().includes(needle)) return true;
  if (node.leaf?.keys.some((k) => k.toLowerCase().includes(needle))) return true;
  return node.children.some((c) => matchesFilter(c, filter));
}

function TreeBranch({
  node,
  filter,
  onAdd,
}: {
  node: SignalTreeNode;
  filter: string;
  onAdd: (topic: string, signalKey: string) => void;
}) {
  const [open, setOpen] = useState(true);
  if (!matchesFilter(node, filter)) return null;

  if (node.leaf) {
    const needle = filter.toLowerCase();
    const keys = node.leaf.keys.filter(
      (k) => !filter || k.toLowerCase().includes(needle) || node.segment.toLowerCase().includes(needle)
    );
    return (
      <div className="pl-2">
        <div className="flex items-center gap-1.5 text-xs text-ink-muted">
          <span className="border border-border rounded px-1 text-[10px] uppercase">{node.leaf.topic_type}</span>
          {node.segment}
        </div>
        <div className="flex flex-wrap gap-1 pl-2 py-1">
          {keys.map((key) => (
            <button
              key={key}
              onClick={() => onAdd(node.leaf!.topic, key)}
              className="border border-border rounded px-2 py-0.5 text-xs"
            >
              + {key}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="pl-2">
      <button onClick={() => setOpen(!open)} className="text-xs font-semibold text-ink-secondary">
        {open ? "▾" : "▸"} {node.segment}
      </button>
      {open && node.children.map((child) => (
        <TreeBranch key={child.segment} node={child} filter={filter} onAdd={onAdd} />
      ))}
    </div>
  );
}

export function SignalTreePicker({
  source,
  selected,
  chartColor,
  onChange,
}: {
  source: "historical" | "live";
  selected: ChartSignal[];
  chartColor: string | null;
  onChange: (signals: ChartSignal[]) => void;
}) {
  const [tree, setTree] = useState<SignalTreeNode[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    const fetchTree = source === "historical" ? api.signals.treeHistorical() : api.signals.treeLive();
    fetchTree.then(setTree).catch(() =>
      setError(source === "historical" ? "No se pudo cargar el árbol histórico." : "No se pudo cargar el árbol en vivo.")
    );
  }, [source]);

  const addSignal = async (topic: string, signalKey: string) => {
    setError(null);
    try {
      const descriptivePrefix = topic.replace(/\/_(informative|analytical)$/, "");
      const descriptive = await api.signals.descriptive(descriptivePrefix, signalKey);
      const signal: ChartSignal = {
        topic,
        signal_key: signalKey,
        label: signalKey,
        unit: descriptive.unit ?? null,
        min: descriptive.min ?? null,
        max: descriptive.max ?? null,
        source: descriptive.unit ? "auto" : "manual",
      };
      onChange([...selected, signal]);
    } catch {
      setError("No se pudo añadir la señal.");
    }
  };

  const removeSignal = (topic: string, signalKey: string) => {
    onChange(selected.filter((s) => !(s.topic === topic && s.signal_key === signalKey)));
  };

  const setSignalColor = (topic: string, signalKey: string, color: string) => {
    onChange(selected.map((s) => (s.topic === topic && s.signal_key === signalKey ? { ...s, color } : s)));
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-bold text-ink-secondary">
        Señales ({source === "historical" ? "histórico" : "en vivo"})
      </label>
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filtrar por nombre…"
        className="border border-border rounded px-2 py-1 text-xs"
      />
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {selected.map((s, i) => (
          <span key={`${s.topic}|${s.signal_key}`} className="bg-surface-subtle rounded-full px-3 py-1 text-xs flex items-center gap-1.5">
            <input
              type="color"
              value={resolveColor(s, chartColor, i, selected.length)}
              onChange={(e) => setSignalColor(s.topic, s.signal_key, e.target.value)}
              className="w-4 h-4 border-0 p-0 bg-transparent"
            />
            {s.label}
            <button onClick={() => removeSignal(s.topic, s.signal_key)}>✕</button>
          </span>
        ))}
      </div>
      <div className="max-h-56 overflow-y-auto border border-border rounded-lg p-2">
        {tree.map((node) => (
          <TreeBranch key={node.segment} node={node} filter={filter} onAdd={addSignal} />
        ))}
      </div>
    </div>
  );
}
