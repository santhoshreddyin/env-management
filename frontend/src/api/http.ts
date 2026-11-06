import type { ValidationIssue } from './types';

export const BASE_URL: string = import.meta.env.VITE_API_BASE_URL || '/api';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public issues: ValidationIssue[] = [],
  ) {
    super(message);
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

export function apiUrl(path: string, params?: Params): string {
  const qs = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') qs.set(k, String(v));
  });
  const q = qs.toString();
  return `${BASE_URL}${path}${q ? `?${q}` : ''}`;
}

interface RequestOptions {
  method?: string;
  params?: Params;
  body?: unknown;
  formData?: FormData;
}

export async function request<T>(path: string, { method = 'GET', params, body, formData }: RequestOptions = {}): Promise<T> {
  const res = await fetch(apiUrl(path, params), {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    let issues: ValidationIssue[] = [];
    try {
      const data = await res.json();
      const detail = data.detail;
      if (typeof detail === 'string') message = detail;
      else if (Array.isArray(detail)) message = detail.map((d: { msg: string }) => d.msg).join(', ');
      else if (detail && typeof detail === 'object') {
        message = detail.message ?? message;
        issues = detail.issues ?? [];
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, res.status, issues);
  }
  return (res.status === 204 ? null : await res.json()) as T;
}
