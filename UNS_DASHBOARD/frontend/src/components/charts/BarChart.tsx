import type { ChartSignal } from "../../types/dashboard";

export function BarChart({ signals, values }: { signals: ChartSignal[]; values: Record<string, number> }) {
  const max = Math.max(1, ...signals.map((s) => values[s.signal_key] ?? 0));
  return (
    <div className="h-full flex items-end justify-center gap-8">
      {signals.map((s) => {
        const value = values[s.signal_key] ?? 0;
        return (
          <div key={s.signal_key} className="flex flex-col items-center gap-1.5">
            <span className="text-xs font-bold text-ink">{value}{s.unit}</span>
            <div
              className="w-10 rounded-t"
              style={{ height: `${(value / max) * 140}px`, backgroundColor: s.color ?? "#3B82F6" }}
            />
            <span className="text-xs text-ink-secondary">{s.label ?? s.signal_key}</span>
          </div>
        );
      })}
    </div>
  );
}
