import { apiUrl, request } from './http';
import type {
  AuditEntry,
  EditResult,
  FlowConfig,
  Graph,
  HopFields,
  ImportReport,
  Integration,
  IntegrationFields,
  Me,
  Pair,
  ComponentDetail,
  SystemFields,
  Version,
} from './types';

export interface FlowFilters {
  journey?: string | null;
  pattern?: string | null;
  protocol?: string | null;
}

export const flowsApi = {
  me: () => request<Me>('/me'),
  config: () => request<FlowConfig>('/flow-config'),
  graph: () => request<Graph>('/graph'),
  journeys: () => request<string[]>('/journeys'),
  pairs: (params: FlowFilters & { upstream?: string | null }) => request<Pair[]>('/pairs', { params: { ...params } }),
  integrations: (params: FlowFilters & { from?: string | null; to?: string | null }) =>
    request<Integration[]>('/integrations', { params: { ...params } }),

  importWorkbook: (file: File, dryRun: boolean) => {
    const form = new FormData();
    form.append('file', file);
    return request<ImportReport>('/import', { method: 'POST', params: { dry_run: dryRun }, formData: form });
  },
  versions: () => request<Version[]>('/imports'),
  rollback: (id: number) => request<Version>(`/imports/${id}/rollback`, { method: 'POST' }),
  audit: () => request<AuditEntry[]>('/audit'),
  exportUrl: (format: 'xlsx' | 'json') => apiUrl('/export', { format }),
  templateUrl: () => apiUrl('/template'),

  saveSystem: (data: SystemFields & { component_details: ComponentDetail[] }, isNew: boolean) =>
    request<EditResult>(isNew ? '/systems' : `/systems/${encodeURIComponent(data.id)}`, {
      method: isNew ? 'POST' : 'PUT',
      body: data,
    }),
  deleteSystem: (id: string) => request<null>(`/systems/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  saveIntegration: (data: IntegrationFields & { hops: HopFields[] }, isNew: boolean) =>
    request<EditResult>(isNew ? '/integrations' : `/integrations/${encodeURIComponent(data.id)}`, {
      method: isNew ? 'POST' : 'PUT',
      body: data,
    }),
  deleteIntegration: (id: string) => request<null>(`/integrations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};
