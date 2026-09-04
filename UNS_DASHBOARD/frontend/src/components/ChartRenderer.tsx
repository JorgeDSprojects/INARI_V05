import { useEffect, useRef, useState } from "react";
import { ChartCardShell } from "./ChartCardShell";
import { TimeSeriesChart } from "./charts/TimeSeriesChart";
import { BarChart } from "./charts/BarChart";
import { GaugeChart } from "./charts/GaugeChart";
import { KpiTile } from "./charts/KpiTile";
import { StatusIndicator } from "./charts/StatusIndicator";
import { ValuesTable } from "./charts/ValuesTable";
import { useDashboardSocket } from "../hooks/useDashboardSocket";
import { useHistoricalQuery } from "../hooks/useHistoricalQuery";
import { resolveColor } from "../lib/palette";
import { computeConnectionState } from "../lib/connectionState";
import type { Chart, HistoryPoint } from "../types/dashboard";

const LIVE_BUFFER_MAX_POINTS = 200;

export function ChartRenderer({
  dashboardId,
  chart,
  editable,
  onRemove,
  onEdit,
}: {
  dashboardId: string;
  chart: Chart;
  editable: boolean;
  onRemove?: () => void;
  onEdit?: () => void;
}) {
  const topics = chart.data_mode === "live" ? [...new Set(chart.signals.map((s) => s.topic))] : [];
  const { frames: liveFrames, wsOpen, lastFrameAt, connectedAt } = useDashboardSocket(dashboardId, topics);
  const { points: historyPoints, error: historyError, retry: retryHistory } = useHistoricalQuery(
    chart.id,
    chart.data_mode === "historical" ? chart.historical_range_type : null,
    chart.data_mode === "historical" ? chart.historical_relative_rule : null
  );

  const signals = chart.signals.map((s, i) => ({ ...s, color: resolveColor(s, chart.color, i, chart.signals.length) }));

  const [, forceTick] = useState(0);
  useEffect(() => {
    if (chart.data_mode !== "live") return;
    const id = setInterval(() => forceTick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, [chart.data_mode]);

  const connectionState = chart.data_mode === "live"
    ? computeConnectionState(wsOpen, topics, lastFrameAt, connectedAt, Date.now())
    : null;

  const [liveBuffer, setLiveBuffer] = useState<HistoryPoint[]>([]);
  const lastFrameKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (chart.data_mode !== "live" || chart.chart_type !== "timeseries") return;
    const frameKey = Object.values(liveFrames).map((f) => f.time).join(",");
    if (!frameKey || frameKey === lastFrameKeyRef.current) return;
    lastFrameKeyRef.current = frameKey;
    const point: HistoryPoint = { time: new Date().toISOString() };
    for (const s of signals) {
      const v = liveFrames[s.topic]?.payload[s.signal_key];
      if (v !== undefined) point[s.signal_key] = v;
    }
    setLiveBuffer((prev) => [...prev, point].slice(-LIVE_BUFFER_MAX_POINTS));
  }, [liveFrames, chart.data_mode, chart.chart_type, signals]);

  const liveValue = (signalKey: string, topic: string): number | null => {
    const v = liveFrames[topic]?.payload[signalKey];
    return typeof v === "number" ? v : null;
  };

  const lastHistoricalValue = (signalKey: string): number | null => {
    for (let i = historyPoints.length - 1; i >= 0; i--) {
      const v = historyPoints[i][signalKey];
      if (typeof v === "number") return v;
    }
    return null;
  };

  const currentValue = (signalKey: string, topic: string): number | null =>
    chart.data_mode === "live" ? liveValue(signalKey, topic) : lastHistoricalValue(signalKey);

  const historicalStaleWarning = chart.data_mode === "historical" && historyError && historyPoints.length > 0;

  const modeLabel = chart.data_mode === "live"
    ? "Live · tiempo real"
    : chart.historical_range_type === "relative"
      ? `Histórico · ${chart.historical_relative_rule}`
      : "Histórico · rango fijo";

  const body = () => {
    if (chart.data_mode === "historical" && historyError && historyPoints.length === 0) {
      return (
        <div className="h-full flex flex-col items-center justify-center gap-2 text-center">
          <p className="text-xs text-danger">No se pudo cargar el histórico.</p>
          <button onClick={retryHistory} className="text-xs font-semibold text-accent">Reintentar</button>
        </div>
      );
    }
    switch (chart.chart_type) {
      case "timeseries": {
        const points = chart.data_mode === "live" ? liveBuffer : historyPoints;
        return <TimeSeriesChart signals={signals} points={points} />;
      }
      case "bar": {
        const values = Object.fromEntries(signals.map((s) => [s.signal_key, currentValue(s.signal_key, s.topic) ?? 0]));
        return <BarChart signals={signals} values={values} />;
      }
      case "gauge": {
        const first = signals[0];
        return <GaugeChart signal={first} value={currentValue(first?.signal_key, first?.topic) ?? 0} />;
      }
      case "kpi": {
        const first = signals[0];
        return <KpiTile signal={first} value={currentValue(first?.signal_key, first?.topic) ?? 0} />;
      }
      case "status":
        return (
          <StatusIndicator
            states={signals.map((s) => ({
              label: s.label ?? s.signal_key,
              value: String(currentValue(s.signal_key, s.topic) ?? "—"),
              color: s.color,
            }))}
          />
        );
      case "table": {
        const values = Object.fromEntries(
          signals.map((s) => [
            s.signal_key,
            {
              value: currentValue(s.signal_key, s.topic) ?? 0,
              updatedAt: chart.data_mode === "live"
                ? (liveFrames[s.topic]?.time ?? "—")
                : (historyPoints[historyPoints.length - 1]?.time ?? "—"),
            },
          ])
        );
        return <ValuesTable signals={signals} values={values} />;
      }
    }
  };

  return (
    <ChartCardShell title={chart.name} modeLabel={modeLabel} connectionState={connectionState} staleWarning={historicalStaleWarning} editable={editable} onRemove={onRemove} onEdit={onEdit}>
      {body()}
    </ChartCardShell>
  );
}
