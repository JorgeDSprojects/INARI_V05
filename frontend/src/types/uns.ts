export interface Enterprise {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Site {
  id: string;
  enterprise_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Area {
  id: string;
  site_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Line {
  id: string;
  area_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Cell {
  id: string;
  line_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  cell_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  uns_topic: string | null;
  created_at: string;
  updated_at: string;
}

export interface CellTree extends Cell {
  assets: Asset[];
}

export interface LineTree extends Line {
  cells: CellTree[];
}

export interface AreaTree extends Area {
  lines: LineTree[];
}

export interface SiteTree extends Site {
  areas: AreaTree[];
}

export interface EnterpriseTree extends Enterprise {
  sites: SiteTree[];
}

export type HierarchyLevel = "enterprise" | "site" | "area" | "line" | "cell" | "asset";

export interface SelectedNode {
  level: HierarchyLevel;
  id: string;
  parentIds: Record<string, string>;
}

export interface Broker {
  id: string;
  label: string;
  host: string;
  port: number;
  api_port: number;
  username: string | null;
  use_tls: boolean;
  created_at: string;
  updated_at: string;
}

export interface BrokerStatus {
  connected: boolean;
  version: string | null;
  node: string | null;
  error: string | null;
}

export interface BrokerTestResult {
  ok: boolean;
  latency_ms: number | null;
  error: string | null;
}
