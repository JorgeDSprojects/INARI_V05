import { ChartCardShell } from "./ChartCardShell";
import { TimeSeriesChart } from "./charts/TimeSeriesChart";
import { BarChart } from "./charts/BarChart";
import { GaugeChart } from "./charts/GaugeChart";
import { KpiTile } from "./charts/KpiTile";
import { StatusIndicator } from "./charts/StatusIndicator";
import { ValuesTable } from "./charts/ValuesTable";
import { useDashboardSocket } from "../hooks/useDashboardSocket";
import { useHistoricalQuery } from "../hooks/useHistoricalQuery";
import type { Chart } from "../types/dashboard";

export function ChartRenderer({ dashboardId, chart, editable, onRemove }: { dashboardId: string; chart: Chart; editable: boolean; onRemove?: () => void }) {
  const topics = chart.data_mode === "live" ? [...new Set(chart.signals.map((s) => s.topic))] : [];
  const liveFrames = useDashboardSocket(dashboardId, topics);
  const historyPoints = useHistoricalQuery(
    chart.id,
    chart.data_mode === "historical" ? chart.historical_range_type : null,
    chart.data_mode === "historical" ? chart.historical_relative_rule : null
  );

  const liveValue = (signalKey: string, topic: string): number =>
    liveFrames[topic]?.payload[signalKey] ?? 0;

  const modeLabel = chart.data_mode === "live"
    ? "Live · tiempo real"
    : chart.historical_range_type === "relative"
      ? `Histórico · ${chart.historical_relative_rule}`
      : "Histórico · rango fijo";

  const body = () => {
    switch (chart.chart_type) {
      case "timeseries":
        return <TimeSeriesChart signals={chart.signals} points={historyPoints} />;
      case "bar": {
        const values = Object.fromEntries(chart.signals.map((s) => [s.signal_key, liveValue(s.signal_key, s.topic)]));
        return <BarChart signals={chart.signals} values={values} />;
      }
      case "gauge":
        return <GaugeChart signal={chart.signals[0]} value={liveValue(chart.signals[0]?.signal_key, chart.signals[0]?.topic)} />;
      case "kpi":
        return <KpiTile signal={chart.signals[0]} value={liveValue(chart.signals[0]?.signal_key, chart.signals[0]?.topic)} />;
      case "status":
        return (
          <StatusIndicator
            states={chart.signals.map((s) => ({ label: s.label ?? s.signal_key, value: String(liveValue(s.signal_key, s.topic)), color: "success" }))}
          />
        );
      case "table": {
        const values = Object.fromEntries(
          chart.signals.map((s) => [s.signal_key, { value: liveValue(s.signal_key, s.topic), updatedAt: liveFrames[s.topic]?.time ?? "—" }])
        );
        return <ValuesTable signals={chart.signals} values={values} />;
      }
    }
  };

  return (
    <ChartCardShell title={chart.name} modeLabel={modeLabel} editable={editable} onRemove={onRemove}>
      {body()}
    </ChartCardShell>
  );
}
