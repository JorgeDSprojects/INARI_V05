import ReactECharts from "echarts-for-react";
import type { ChartSignal } from "../../types/dashboard";

export function BarChart({ signals, values }: { signals: ChartSignal[]; values: Record<string, number> }) {
  const option = {
    grid: { left: 40, right: 16, top: 24, bottom: 32 },
    xAxis: { type: "category", data: signals.map((s) => s.label ?? s.signal_key), axisLabel: { fontSize: 10 } },
    yAxis: { type: "value", axisLabel: { fontSize: 10 } },
    series: [{
      type: "bar",
      data: signals.map((s) => ({ value: values[s.signal_key] ?? 0, itemStyle: { color: s.color ?? "#3B82F6" } })),
      label: {
        show: true,
        position: "top",
        fontSize: 10,
        formatter: (p: { dataIndex: number; value: number }) => `${p.value}${signals[p.dataIndex]?.unit ?? ""}`,
      },
    }],
  };

  return <ReactECharts option={option} style={{ height: "100%", width: "100%" }} opts={{ renderer: "svg" }} notMerge />;
}
