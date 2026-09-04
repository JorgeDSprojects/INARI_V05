import ReactECharts from "echarts-for-react";
import type { ChartSignal, HistoryPoint } from "../../types/dashboard";

export function TimeSeriesChart({ signals, points }: { signals: ChartSignal[]; points: HistoryPoint[] }) {
  const times = points.map((p) => p.time);
  const option = {
    grid: { left: 40, right: 16, top: 16, bottom: 48 },
    xAxis: { type: "category", data: times, axisLabel: { show: false }, axisTick: { show: false } },
    yAxis: { type: "value", axisLabel: { fontSize: 10 } },
    tooltip: { trigger: "axis" },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 4 }],
    series: signals.map((s) => ({
      name: s.label ?? s.signal_key,
      type: "line",
      areaStyle: { opacity: 0.15 },
      showSymbol: false,
      smooth: true,
      lineStyle: { color: s.color ?? "#3B82F6" },
      itemStyle: { color: s.color ?? "#3B82F6" },
      data: points.map((p) => (p[s.signal_key] as number) ?? null),
    })),
  };

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
      <div className="flex-1 min-h-0">
        <ReactECharts option={option} style={{ height: "100%", width: "100%" }} opts={{ renderer: "svg" }} />
      </div>
    </div>
  );
}
