import { useState } from "react";
import { SignalPicker } from "./SignalPicker";
import type { Chart, ChartSignal, ChartType, DataMode, HistoricalRangeType, RelativeRule } from "../../types/dashboard";

const CHART_TYPES: ChartType[] = ["timeseries", "gauge", "kpi", "bar", "table", "status"];
const RELATIVE_RULES: RelativeRule[] = ["1h", "24h", "7d", "30d"];

export function ChartForm({
  topicPrefix,
  onSubmit,
}: {
  topicPrefix: string;
  onSubmit: (chart: Omit<Chart, "id" | "dashboard_id">) => void;
}) {
  const [name, setName] = useState("");
  const [chartType, setChartType] = useState<ChartType>("timeseries");
  const [signals, setSignals] = useState<ChartSignal[]>([]);
  const [dataMode, setDataMode] = useState<DataMode>("live");
  const [rangeType, setRangeType] = useState<HistoricalRangeType>("relative");
  const [relativeRule, setRelativeRule] = useState<RelativeRule>("24h");
  const [historicalFrom, setHistoricalFrom] = useState("");
  const [historicalTo, setHistoricalTo] = useState("");
  const [color, setColor] = useState("#198ACB");

  const submit = () => {
    onSubmit({
      name,
      chart_type: chartType,
      data_mode: dataMode,
      historical_range_type: dataMode === "historical" ? rangeType : null,
      historical_relative_rule: dataMode === "historical" && rangeType === "relative" ? relativeRule : null,
      historical_from: dataMode === "historical" && rangeType === "fixed" && historicalFrom ? new Date(historicalFrom).toISOString() : null,
      historical_to: dataMode === "historical" && rangeType === "fixed" && historicalTo ? new Date(historicalTo).toISOString() : null,
      layout_x: 0,
      layout_y: 0,
      layout_w: 4,
      layout_h: 4,
      color,
      config: null,
      signals,
    });
    setName("");
    setSignals([]);
  };

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <label className="text-xs font-bold text-ink-muted uppercase">Nueva gráfica</label>
      <input className="border border-border rounded-lg px-3 py-2 text-sm" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre de la gráfica" />

      <select className="border border-border rounded-lg px-3 py-2 text-sm" value={chartType} onChange={(e) => setChartType(e.target.value as ChartType)}>
        {CHART_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>

      <SignalPicker topicPrefix={topicPrefix} selected={signals} onChange={setSignals} />

      <div className="flex gap-2">
        <button className={`flex-1 rounded-lg py-2 text-xs font-semibold ${dataMode === "live" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setDataMode("live")}>Tiempo real</button>
        <button className={`flex-1 rounded-lg py-2 text-xs font-semibold ${dataMode === "historical" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setDataMode("historical")}>Histórico</button>
      </div>

      {dataMode === "historical" && (
        <div className="flex flex-col gap-2 bg-surface-subtle rounded-lg p-3">
          <div className="flex gap-2">
            <button className={`flex-1 rounded py-1 text-xs ${rangeType === "fixed" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setRangeType("fixed")}>Rango fijo</button>
            <button className={`flex-1 rounded py-1 text-xs ${rangeType === "relative" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setRangeType("relative")}>Regla relativa</button>
          </div>
          {rangeType === "relative" && (
            <div className="flex gap-1">
              {RELATIVE_RULES.map((r) => (
                <button key={r} className={`flex-1 rounded py-1 text-xs ${relativeRule === r ? "bg-accent text-white" : "border border-border"}`} onClick={() => setRelativeRule(r)}>{r}</button>
              ))}
            </div>
          )}
          {rangeType === "fixed" && (
            <div className="flex flex-col gap-2">
              <input type="datetime-local" value={historicalFrom} onChange={(e) => setHistoricalFrom(e.target.value)} className="border border-border rounded px-2 py-1 text-xs" />
              <input type="datetime-local" value={historicalTo} onChange={(e) => setHistoricalTo(e.target.value)} className="border border-border rounded px-2 py-1 text-xs" />
            </div>
          )}
        </div>
      )}

      <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-8 w-full" />

      <button onClick={submit} disabled={!name || signals.length === 0} className="bg-ink text-white rounded-lg py-2 text-sm font-bold disabled:opacity-40">
        + Añadir al panel
      </button>
    </div>
  );
}
