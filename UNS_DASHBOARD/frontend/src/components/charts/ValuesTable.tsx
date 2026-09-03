import type { ChartSignal } from "../../types/dashboard";

export function ValuesTable({
  signals,
  values,
}: {
  signals: ChartSignal[];
  values: Record<string, { value: number; updatedAt: string }>;
}) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-ink-muted uppercase border-b border-border">
          <th className="py-1">Señal</th>
          <th>Valor</th>
          <th>Actualizado</th>
        </tr>
      </thead>
      <tbody>
        {signals.map((s) => {
          const entry = values[s.signal_key];
          return (
            <tr key={s.signal_key} className="border-b border-border-subtle">
              <td className="py-2 font-semibold text-ink">{s.label ?? s.signal_key}</td>
              <td className="text-ink">{entry ? `${entry.value} ${s.unit ?? ""}` : "—"}</td>
              <td className="text-ink-muted">{entry ? entry.updatedAt : "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
