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
  const [options, setOptions] = useState<{ topic: string; keys: string[] }[]>([]);

  const search = async () => {
    const catalog = await api.signals.catalog(topicPrefix);
    setOptions(catalog);
  };

  const addSignal = async (topic: string, signalKey: string) => {
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
  };

  const removeSignal = (signalKey: string) => {
    onChange(selected.filter((s) => s.signal_key !== signalKey));
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between items-center">
        <label className="text-xs font-bold text-ink-secondary">Señales (_informative)</label>
        <button onClick={search} className="text-xs font-semibold text-accent">buscar</button>
      </div>
      <div className="flex flex-wrap gap-2">
        {selected.map((s) => (
          <span key={s.signal_key} className="bg-surface-subtle rounded-full px-3 py-1 text-xs flex items-center gap-1.5">
            {s.label}
            <button onClick={() => removeSignal(s.signal_key)}>✕</button>
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
