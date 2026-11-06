import { apiUrl, request } from './http';

export interface Environment {
  id: number;
  name: string;
  description: string | null;
  variable_count: number;
}

export interface Variable {
  id: number;
  environment_id: number;
  key: string;
  value: string;
  is_secret: boolean;
}

export type VariableInput = Pick<Variable, 'key' | 'value' | 'is_secret'>;

export const envApi = {
  listEnvironments: () => request<Environment[]>('/environments'),
  createEnvironment: (data: { name: string; description?: string }) =>
    request<Environment>('/environments', { method: 'POST', body: data }),
  deleteEnvironment: (id: number) => request<null>(`/environments/${id}`, { method: 'DELETE' }),
  listVariables: (envId: number) => request<Variable[]>(`/environments/${envId}/variables`),
  createVariable: (envId: number, data: VariableInput) =>
    request<Variable>(`/environments/${envId}/variables`, { method: 'POST', body: data }),
  updateVariable: (envId: number, varId: number, data: Partial<VariableInput>) =>
    request<Variable>(`/environments/${envId}/variables/${varId}`, { method: 'PATCH', body: data }),
  deleteVariable: (envId: number, varId: number) =>
    request<null>(`/environments/${envId}/variables/${varId}`, { method: 'DELETE' }),
  exportUrl: (envId: number) => apiUrl(`/environments/${envId}/variables/export/dotenv`),
};
