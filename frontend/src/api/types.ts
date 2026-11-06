// Mirrors backend/app/flows/schemas.py

export type SystemType = 'upstream' | 'downstream' | 'gateway' | 'queue_manager' | 'mainframe';
export type Protocol = 'REST' | 'SOAP' | 'MQ' | 'FILE' | 'MFT';
export type Direction = 'request' | 'reply';
export type Pattern = 'sync' | 'async';

export const SYSTEM_TYPES: SystemType[] = ['upstream', 'downstream', 'gateway', 'queue_manager', 'mainframe'];
export const PROTOCOLS: Protocol[] = ['REST', 'SOAP', 'MQ', 'FILE', 'MFT'];
export const PATTERNS: Pattern[] = ['sync', 'async'];

export interface ComponentDetail {
  gateway_tier: string | null;
  endpoint: string | null;
  queue_references: string | null;
  notes: string | null;
}

export interface SystemFields {
  id: string;
  name: string;
  type: SystemType;
  layer: string | null;
  domain: string | null;
  owner: string | null;
  environment: string | null;
  notes: string | null;
}

export interface System extends SystemFields {
  display_layer: string;
  component_details: ComponentDetail[];
}

export interface HopFields {
  sequence: number;
  from_system: string;
  to_system: string;
  protocol: Protocol;
  direction: Direction;
  queue_name: string | null;
  queue_manager: string | null;
  notes: string | null;
}

export interface Hop extends HopFields {
  integration_id: string;
  from_name: string;
  to_name: string;
}

export interface IntegrationFields {
  id: string;
  name: string;
  journey: string | null;
  upstream_id: string;
  downstream_id: string;
  pattern: Pattern;
  primary_protocol: Protocol | null;
  status: string | null;
  verified_by: string | null;
  last_verified: string | null;
  notes: string | null;
}

export interface Integration extends IntegrationFields {
  upstream_name: string;
  downstream_name: string;
  hops: Hop[];
  narrative: string[];
}

export interface IntegrationSummary {
  id: string;
  name: string;
  journey: string | null;
  pattern: Pattern;
  primary_protocol: Protocol | null;
  status: string | null;
  upstream_id: string;
  downstream_id: string;
  system_ids: string[];
  protocols: Protocol[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  protocol: Protocol;
  direction: Direction;
  integration_ids: string[];
}

export interface Graph {
  nodes: System[];
  edges: GraphEdge[];
  integrations: IntegrationSummary[];
}

export interface Pair {
  upstream_id: string;
  upstream_name: string;
  downstream_id: string;
  downstream_name: string;
  integration_count: number;
  journeys: string[];
}

export interface FlowConfig {
  layers: { id: string; label: string }[];
  type_layers: Record<string, string>;
  protocols: Record<string, { label: string; color: string; dash: string | null }>;
  directions: Record<Direction, { label: string; stroke_width: number; marker: 'arrow' | 'arrowclosed' }>;
  system_types: Record<string, { label: string; color: string }>;
}

export interface ValidationIssue {
  severity: 'error' | 'warning';
  sheet: string;
  row: number | null;
  column: string | null;
  ref: string | null;
  message: string;
}

export interface ImportReport {
  filename: string | null;
  dry_run: boolean;
  valid: boolean;
  imported: boolean;
  version_id: number | null;
  counts: Record<string, number>;
  error_count: number;
  warning_count: number;
  issues: ValidationIssue[];
}

export interface Version {
  id: number;
  created_at: string;
  created_by: string;
  source: string;
  filename: string | null;
  summary: string | null;
  system_count: number;
  integration_count: number;
  hop_count: number;
  is_current: boolean;
}

export interface AuditEntry {
  id: number;
  at: string;
  user: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
}

export interface Me {
  name: string;
  roles: string[];
}

export interface EditResult {
  id: string;
  warnings: ValidationIssue[];
}
