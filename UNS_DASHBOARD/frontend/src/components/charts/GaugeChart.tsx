import ReactECharts from "echarts-for-react";
import type { ChartSignal } from "../../types/dashboard";

export function GaugeChart({ signal, value }: { signal: ChartSignal; value: number }) {
  const min = signal.min ?? 0;
  const max = signal.max ?? 100;
  const color = signal.color ?? "#198ACB";

  const option = {
    series: [{
      type: "gauge",
      min,
      max,
      startAngle: 225,
      endAngle: -45,
      progress: { show: true, width: 10, itemStyle: { color } },
      axisLine: { lineStyle: { width: 10, color: [[1, "#DDE2E7"]] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      detail: { show: false },
      data: [{ value }],
    }],
  };

  return (
    <div className="h-full flex flex-col items-center justify-center gap-1">
      <div className="w-32 h-32">
        <ReactECharts option={option} style={{ height: "100%", width: "100%" }} opts={{ renderer: "svg" }} notMerge />
      </div>
      <span className="text-2xl font-bold text-ink -mt-16">{value}{signal.unit}</span>
      <span className="text-xs text-ink-secondary mt-16">{signal.label ?? signal.signal_key}</span>
    </div>
  );
}
