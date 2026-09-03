import { useState } from "react";
import { api } from "../../api/client";
import type { ChartSignal } from "../../types/dashboard";

export function SignalPicker({
  topicPrefix,
  selected,
  onChange,
}: {
  topicPrefix: string;
  selected: ChartSignal[];
  onChange: (signals: ChartSignal[]) => void;
}) {
  const [prefix, setPrefix] = useState(topicPrefix);
  const [options, setOptions] = useState<{ topic: string; keys: string[] }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    setError(null);
    try {
      const catalog = await api.signals.catalog(prefix);
      setOptions(catalog);
    } catch {
      setError("No se pudo buscar señales. Comprueba que el backend esté disponible.");
    }
  };

  const addSignal = async (topic: string, signalKey: string) => {
    setError(null);
    try {
      const descriptive = await api.signals.descriptive(topic.replace(/\/_informative$/, ""), signalKey);
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

  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-bold text-ink-secondary">Señales (_informative)</label>
      <div className="flex gap-2">
        <input
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          placeholder="Prefijo de topic (vacío = todos)"
          className="flex-1 border border-border rounded px-2 py-1 text-xs"
        />
        <button onClick={search} className="text-xs font-semibold text-accent">buscar</button>
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {selected.map((s) => (
          <span key={`${s.topic}|${s.signal_key}`} className="bg-surface-subtle rounded-full px-3 py-1 text-xs flex items-center gap-1.5">
            {s.label}
            <button onClick={() => removeSignal(s.topic, s.signal_key)}>✕</button>
          </span>
        ))}
      </div>
      {options.map((topicOpt) => (
        <div key={topicOpt.topic} className="text-xs">
          <div className="text-ink-muted">{topicOpt.topic}</div>
          <div className="flex flex-wrap gap-1">
            {topicOpt.keys.map((key) => (
              <button
                key={key}
                onClick={() => addSignal(topicOpt.topic, key)}
                className="border border-border rounded px-2 py-0.5"
              >
                + {key}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
