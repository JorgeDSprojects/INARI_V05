import axios from "axios";
import type { Asset, Area, Broker, BrokerStatus, BrokerTestResult, Cell, DataBranch, Enterprise, EnterpriseTree, Line, NodeType, Site, SyncStatus, ValidationResult } from "../types/uns";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const http = axios.create({ baseURL: BASE });

type PayloadFields = {
  descriptive_payload?: Record<string, unknown> | null;
  informative_payload?: Record<string, unknown> | null;
};

export const api = {
  tree: {
    get: () => http.get<EnterpriseTree[]>("/tree/").then((r) => r.data),
    copy: (body: { source_id: string; source_level: string; target_parent_id: string }) =>
      http.post<{ new_root_id: string; node_count: number }>("/tree/copy", body).then((r) => r.data),
    move: (body: { source_id: string; source_level: string; target_parent_id: string }) =>
      http.post<{ moved_root_id: string; node_count: number }>("/tree/move", body).then((r) => r.data),
    publishSubtree: (body: { root_id: string; root_level: string }) =>
      http.post<{ published: number; failed: number }>("/tree/publish-subtree", body).then((r) => r.data),
  },
  enterprises: {
    list: () => http.get<Enterprise[]>("/enterprises/").then((r) => r.data),
    get: (id: string) => http.get<Enterprise>(`/enterprises/${id}`).then((r) => r.data),
    create: (body: { name: string; description?: string; metadata?: Record<string, unknown> }) =>
      http.post<Enterprise>("/enterprises/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ name: string; description: string; metadata: Record<string, unknown> } & PayloadFields>) =>
      http.patch<Enterprise>(`/enterprises/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/enterprises/${id}`),
    publish: (id: string) =>
      http.post<Enterprise>(`/enterprises/${id}/publish`).then((r) => r.data),
  },
  sites: {
    list: (enterpriseId: string) =>
      http.get<Site[]>(`/enterprises/${enterpriseId}/sites/`).then((r) => r.data),
    create: (enterpriseId: string, body: { name: string; description?: string }) =>
      http.post<Site>(`/enterprises/${enterpriseId}/sites/`, body).then((r) => r.data),
    update: (enterpriseId: string, siteId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Site>(`/enterprises/${enterpriseId}/sites/${siteId}`, body).then((r) => r.data),
    delete: (enterpriseId: string, siteId: string) =>
      http.delete(`/enterprises/${enterpriseId}/sites/${siteId}`),
    publish: (enterpriseId: string, siteId: string) =>
      http.post<Site>(`/enterprises/${enterpriseId}/sites/${siteId}/publish`).then((r) => r.data),
  },
  areas: {
    list: (siteId: string) => http.get<Area[]>(`/sites/${siteId}/areas/`).then((r) => r.data),
    create: (siteId: string, body: { name: string; description?: string }) =>
      http.post<Area>(`/sites/${siteId}/areas/`, body).then((r) => r.data),
    update: (siteId: string, areaId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Area>(`/sites/${siteId}/areas/${areaId}`, body).then((r) => r.data),
    delete: (siteId: string, areaId: string) => http.delete(`/sites/${siteId}/areas/${areaId}`),
    publish: (siteId: string, areaId: string) =>
      http.post<Area>(`/sites/${siteId}/areas/${areaId}/publish`).then((r) => r.data),
  },
  lines: {
    list: (areaId: string) => http.get<Line[]>(`/areas/${areaId}/lines/`).then((r) => r.data),
    create: (areaId: string, body: { name: string; description?: string }) =>
      http.post<Line>(`/areas/${areaId}/lines/`, body).then((r) => r.data),
    update: (areaId: string, lineId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Line>(`/areas/${areaId}/lines/${lineId}`, body).then((r) => r.data),
    delete: (areaId: string, lineId: string) => http.delete(`/areas/${areaId}/lines/${lineId}`),
    publish: (areaId: string, lineId: string) =>
      http.post<Line>(`/areas/${areaId}/lines/${lineId}/publish`).then((r) => r.data),
  },
  cells: {
    list: (lineId: string) => http.get<Cell[]>(`/lines/${lineId}/cells/`).then((r) => r.data),
    create: (lineId: string, body: { name: string; description?: string }) =>
      http.post<Cell>(`/lines/${lineId}/cells/`, body).then((r) => r.data),
    update: (lineId: string, cellId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Cell>(`/lines/${lineId}/cells/${cellId}`, body).then((r) => r.data),
    delete: (lineId: string, cellId: string) => http.delete(`/lines/${lineId}/cells/${cellId}`),
    publish: (lineId: string, cellId: string) =>
      http.post<Cell>(`/lines/${lineId}/cells/${cellId}/publish`).then((r) => r.data),
  },
  assets: {
    list: (cellId: string) => http.get<Asset[]>(`/cells/${cellId}/assets/`).then((r) => r.data),
    create: (cellId: string, body: { name: string; description?: string; descriptive_payload?: Record<string, unknown>; node_type_id?: string }) =>
      http.post<Asset>(`/cells/${cellId}/assets/`, body).then((r) => r.data),
    update: (cellId: string, assetId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Asset>(`/cells/${cellId}/assets/${assetId}`, body).then((r) => r.data),
    delete: (cellId: string, assetId: string) => http.delete(`/cells/${cellId}/assets/${assetId}`),
    publish: (cellId: string, assetId: string) =>
      http.post<Asset>(`/cells/${cellId}/assets/${assetId}/publish`).then((r) => r.data),
  },
  brokers: {
    list: () => http.get<Broker[]>("/brokers/").then((r) => r.data),
    create: (body: { label: string; host: string; port: number; api_port: number; username?: string; password?: string; use_tls?: boolean }) =>
      http.post<Broker>("/brokers/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ label: string; host: string; port: number; api_port: number; username: string; password: string; use_tls: boolean }>) =>
      http.put<Broker>(`/brokers/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/brokers/${id}`),
    status: (id: string) => http.get<BrokerStatus>(`/brokers/${id}/status`).then((r) => r.data),
    test: (id: string) => http.post<BrokerTestResult>(`/brokers/${id}/test`).then((r) => r.data),
  },
  nodeTypes: {
    list: () => http.get<NodeType[]>("/node-types/").then((r) => r.data),
    create: (body: { name: string; description?: string; json_schema: Record<string, unknown> }) =>
      http.post<NodeType>("/node-types/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ name: string; description: string; json_schema: Record<string, unknown> }>) =>
      http.put<NodeType>(`/node-types/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/node-types/${id}`),
    validate: (id: string, payload: Record<string, unknown>) =>
      http.post<ValidationResult>(`/node-types/${id}/validate`, { payload }).then((r) => r.data),
  },
  branches: {
    list: (cellId: string, assetId: string) =>
      http.get<DataBranch[]>(`/cells/${cellId}/assets/${assetId}/branches`).then((r) => r.data),
  },
  syncStatus: {
    get: (cellId: string, assetId: string) =>
      http.get<SyncStatus>(`/cells/${cellId}/assets/${assetId}/sync-status`).then((r) => r.data),
  },
};
