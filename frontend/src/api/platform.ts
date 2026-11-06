// Client for the environment management platform API (backend/app/platform).
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { apiUrl, request } from './http';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Row = Record<string, any>;

export interface Environment extends Row {
  id: number;
  name: string;
  description: string | null;
  env_type: string;
  status: string;
  health_status: string;
  owner: string | null;
  programme: string | null;
  region: string | null;
  tags: string[];
  urls: { label: string; url: string }[];
  allowed_transitions: string[];
  row_version: number;
  variable_count: number;
  instance_count: number;
  open_issues?: number;
  active_bookings?: { id: number; project: string; team: string | null; end_at: string }[];
}

export interface Meta {
  env_types: string[];
  tiers: string[];
  platforms: string[];
  lifecycle: string[];
  transitions: Record<string, string[]>;
  custom_attributes: { key: string; label?: string; type?: string; options?: string[]; required_for?: string[] }[];
  mandatory_fields: Record<string, string[]>;
  policies: Row;
  system_categories: string[];
  issue_categories: string[];
  programmes: string[];
  regions: string[];
  families: string[];
  tags: string[];
}

export interface Access {
  name: string;
  role: string;
  level: number;
  roles: string[];
  unread_notifications: number;
  instance: string;
}

type Params = Record<string, string | number | boolean | null | undefined>;

export const api = {
  get: <T = Row>(path: string, params?: Params) => request<T>(path, { params }),
  post: <T = Row>(path: string, body?: unknown, params?: Params) => request<T>(path, { method: 'POST', body, params }),
  patch: <T = Row>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  put: <T = Row>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  del: (path: string, params?: Params) => request<null>(path, { method: 'DELETE', params }),
  upload: <T = Row>(path: string, file: File, params?: Params) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<T>(path, { method: 'POST', formData: fd, params });
  },
  url: apiUrl,
};

/** useQuery over a GET path; the key is the path + params. */
export function useGet<T = Row>(path: string | null, params?: Params, opts: { refetchInterval?: number } = {}) {
  return useQuery<T>({
    queryKey: [path, params ?? {}],
    queryFn: () => api.get<T>(path as string, params),
    enabled: path !== null,
    staleTime: 15_000,
    ...opts,
  });
}

/** A mutation that invalidates everything (or the given keys) on success. */
export function useAction<TArgs = void, TResult = Row>(fn: (args: TArgs) => Promise<TResult>, invalidate?: QueryKey[]) {
  const qc = useQueryClient();
  return useMutation<TResult, Error, TArgs>({
    mutationFn: fn,
    onSuccess: () => {
      if (invalidate) invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      else qc.invalidateQueries();
    },
  });
}

export const useMeta = () => useGet<Meta>('/environments/meta');
export const useAccess = () => useGet<Access>('/me/access', undefined, { refetchInterval: 60_000 });
export const useEnvironments = (params?: Params) => useGet<Environment[]>('/environments', params);

export const LEVEL = { viewer: 1, booker: 2, contributor: 3, env_manager: 4, admin: 5 } as const;
export type RoleName = keyof typeof LEVEL;

/** Global level check for showing controls; the server enforces scoped rules. */
export function useCan(role: RoleName, envLevel?: number): boolean {
  const a = useAccess();
  const lvl = Math.max(a.data?.level ?? 0, envLevel ?? 0);
  return lvl >= LEVEL[role];
}

export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleDateString() : '—');
export const fmtDateTime = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—';
/** ISO string for a datetime-local input value (local time → UTC, NFR-12). */
export const toIso = (local: string) => (local ? new Date(local).toISOString() : '');
export const toLocalInput = (iso: string | null | undefined) => {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
