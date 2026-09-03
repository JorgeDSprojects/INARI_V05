import type { Chart } from "../../types/dashboard";

export function PendingChartsList({ charts, onRemove }: { charts: Chart[]; onRemove: (id: string) => void }) {
  if (charts.length === 0) {
    return <p className="text-xs text-ink-muted">No hay gráficas sin colocar.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {charts.map((c) => (
        <div key={c.id} className="flex items-center justify-between bg-surface-subtle rounded-lg px-3 py-2">
          <div>
            <div className="text-xs font-semibold text-ink">{c.name}</div>
            <div className="text-xs text-ink-muted">{c.chart_type} · {c.data_mode}</div>
          </div>
          <button onClick={() => onRemove(c.id)} className="text-ink-muted text-xs">✕</button>
        </div>
      ))}
    </div>
  );
}
