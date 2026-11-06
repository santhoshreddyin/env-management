const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((d) => d.msg).join(', ');
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  listEnvironments: () => request('/environments'),
  createEnvironment: (data) => request('/environments', { method: 'POST', body: data }),
  updateEnvironment: (id, data) => request(`/environments/${id}`, { method: 'PATCH', body: data }),
  deleteEnvironment: (id) => request(`/environments/${id}`, { method: 'DELETE' }),

  listVariables: (envId) => request(`/environments/${envId}/variables`),
  createVariable: (envId, data) =>
    request(`/environments/${envId}/variables`, { method: 'POST', body: data }),
  updateVariable: (envId, varId, data) =>
    request(`/environments/${envId}/variables/${varId}`, { method: 'PATCH', body: data }),
  deleteVariable: (envId, varId) =>
    request(`/environments/${envId}/variables/${varId}`, { method: 'DELETE' }),
  exportUrl: (envId) => `${BASE_URL}/environments/${envId}/variables/export/dotenv`,
};
