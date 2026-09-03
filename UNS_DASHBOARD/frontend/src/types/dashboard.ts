export interface ChartSignal {
  id?: string;
  topic: string;
  signal_key: string;
  label?: string | null;
  unit?: string | null;
  color?: string | null;
  min?: number | null;
  max?: number | null;
  source?: "auto" | "manual";
}

export type ChartType = "timeseries" | "gauge" | "kpi" | "bar" | "table" | "status";
export type DataMode = "live" | "historical";
export type HistoricalRangeType = "fixed" | "relative";
export type RelativeRule = "1h" | "24h" | "7d" | "30d";

export interface Chart {
  id: string;
  dashboard_id: string;
  name: string;
  description?: string | null;
  chart_type: ChartType;
  data_mode: DataMode;
  historical_range_type?: HistoricalRangeType | null;
  historical_from?: string | null;
  historical_to?: string | null;
  historical_relative_rule?: RelativeRule | null;
  layout_x: number;
  layout_y: number;
  layout_w: number;
  layout_h: number;
  color?: string | null;
  config?: Record<string, unknown> | null;
  signals: ChartSignal[];
}

export interface Dashboard {
  id: string;
  name: string;
  description?: string | null;
  status: "draft" | "published";
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DashboardDetail extends Dashboard {
  charts: Chart[];
}

export interface HistoryPoint {
  time: string;
  [signalKey: string]: string | number | null;
}
