import axios from "axios";
import type { Chart, Dashboard, DashboardDetail, HistoryPoint, SignalTreeNode } from "../types/dashboard";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";
const http = axios.create({ baseURL: BASE });

export const api = {
  dashboards: {
    list: () => http.get<Dashboard[]>("/dashboards/").then((r) => r.data),
    get: (id: string) => http.get<DashboardDetail>(`/dashboards/${id}`).then((r) => r.data),
    create: (body: { name: string; description?: string }) =>
      http.post<Dashboard>("/dashboards/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ name: string; description: string }>) =>
      http.patch<Dashboard>(`/dashboards/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/dashboards/${id}`),
    publish: (id: string) => http.post<Dashboard>(`/dashboards/${id}/publish`).then((r) => r.data),
  },
  charts: {
    create: (dashboardId: string, body: Omit<Chart, "id" | "dashboard_id">) =>
      http.post<Chart>(`/dashboards/${dashboardId}/charts/`, body).then((r) => r.data),
    update: (chartId: string, body: Partial<Omit<Chart, "id" | "dashboard_id">>) =>
      http.patch<Chart>(`/charts/${chartId}`, body).then((r) => r.data),
    delete: (chartId: string) => http.delete(`/charts/${chartId}`),
  },
  signals: {
    treeHistorical: (topicPrefix = "") =>
      http.get<SignalTreeNode[]>("/signals/tree/historical", { params: { topic_prefix: topicPrefix } }).then((r) => r.data),
    treeLive: () =>
      http.get<SignalTreeNode[]>("/signals/tree/live").then((r) => r.data),
    descriptive: (topicPrefix: string, signalKey: string) =>
      http.get<{ unit?: string; min?: number; max?: number }>("/signals/descriptive", { params: { topic_prefix: topicPrefix, signal_key: signalKey } }).then((r) => r.data),
  },
  history: {
    get: (chartId: string) => http.get<{ points: HistoryPoint[] }>(`/charts/${chartId}/history`).then((r) => r.data),
  },
};

export function wsUrl(dashboardId: string): string {
  const wsBase = BASE.replace(/^http/, "ws");
  return `${wsBase}/ws/dashboards/${dashboardId}`;
}
