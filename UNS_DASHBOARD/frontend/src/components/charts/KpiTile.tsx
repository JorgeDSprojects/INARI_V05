import type { ChartSignal } from "../../types/dashboard";

export function KpiTile({ signal, value }: { signal: ChartSignal; value: number }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-1">
      <span className="text-4xl font-extrabold text-ink">{value}</span>
      <span className="text-xs text-ink-secondary">{signal.unit} · {signal.label ?? signal.signal_key}</span>
    </div>
  );
}
