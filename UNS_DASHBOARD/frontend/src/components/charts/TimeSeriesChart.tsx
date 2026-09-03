import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartSignal, HistoryPoint } from "../../types/dashboard";

export function TimeSeriesChart({ signals, points }: { signals: ChartSignal[]; points: HistoryPoint[] }) {
  return (
    <div className="h-full flex flex-col gap-2">
      <div className="flex gap-4">
        {signals.map((s) => (
          <div key={s.signal_key} className="flex items-center gap-1.5 text-xs text-ink-secondary">
            <span className="w-2.5 h-0.5 rounded" style={{ backgroundColor: s.color ?? "#3B82F6" }} />
            {s.label ?? s.signal_key}
          </div>
        ))}
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points}>
          <XAxis dataKey="time" hide />
          <YAxis width={32} tick={{ fontSize: 10 }} />
          <Tooltip />
          {signals.map((s) => (
            <Area
              key={s.signal_key}
              type="monotone"
              dataKey={s.signal_key}
              stroke={s.color ?? "#3B82F6"}
              fill={s.color ?? "#3B82F6"}
              fillOpacity={0.15}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
