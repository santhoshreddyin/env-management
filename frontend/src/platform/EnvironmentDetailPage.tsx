// One environment: overview, lifecycle, and tabs for topology, deployments, config, bookings, issues, data, health.
import { Alert, Box, Breadcrumbs, Button, Checkbox, Chip, FormControlLabel, Link, MenuItem, Paper, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, fmtDate, fmtDateTime, useAction, useCan, useEnvironments, useGet, useMeta, type Environment, type Row } from '../api/platform';
import { ApiError } from '../api/http';
import { ErrorAlert, FormDialog, HealthChip, Section, StatusChip } from './common';
import { environmentFields } from './environmentFields';
import { BookingsTab, DataTab, DeploymentsTab, HealthTab, IssuesTab, ReadinessTab } from './EnvTabs';
import ConfigTab from './ConfigTab';
import TopologyTab from './TopologyTab';

const TABS = ['overview', 'topology', 'deployments', 'config', 'bookings', 'issues', 'data', 'health', 'readiness'];
const LABELS: Record<string, string> = {
  overview: 'Overview', topology: 'Topology', deployments: 'Deployments', config: 'Configuration', bookings: 'Bookings',
  issues: 'Issues', data: 'Test data', health: 'Health', readiness: 'Readiness',
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" component="div">
        {label}
      </Typography>
      <Typography variant="body2" component="div">{children || '—'}</Typography>
    </Box>
  );
}

export default function EnvironmentDetailPage() {
  const id = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const tab = TABS.includes(params.get('tab') ?? '') ? (params.get('tab') as string) : 'overview';
  const env = useGet<Environment>(`/environments/${id}`);
  const meta = useMeta();
  const all = useEnvironments();
  const nav = useNavigate();
  const canManage = useCan('env_manager', env.data?.my_level);
  const canContribute = useCan('contributor', env.data?.my_level);
  const [edit, setEdit] = useState(false);
  const [clone, setClone] = useState(false);
  const [override, setOverride] = useState(false);
  const [reason, setReason] = useState('');
  const update = useAction((v: Row) => api.patch(`/environments/${id}`, { ...v, row_version: env.data?.row_version }));
  const move = useAction((to: string) => api.post(`/environments/${id}/transition`, { to, reason: reason || null, row_version: env.data?.row_version }));
  const del = useAction(() => api.del(`/environments/${id}`));
  const checklist = useAction((items: Row[]) => api.put(`/environments/${id}/checklist`, { items }));
  const clearOverride = useAction(() => api.del(`/environments/${id}/health/override`));
  const subscribe = useAction(() => api.post('/subscriptions', { environment_id: id, events: ['*'] }));

  if (env.isError) return <ErrorAlert error={env.error} />;
  const e = env.data;
  if (!e) return null;

  const conflict = (update.error as ApiError | null)?.status === 409 || (move.error as ApiError | null)?.status === 409;
  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/environments">
          Environments
        </Link>
        {e.parent && <Link component={RouterLink} to={`/environments/${e.parent_id}`}>{e.parent}</Link>}
        <Typography color="text.primary">{e.name}</Typography>
      </Breadcrumbs>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
          <Box>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
                {e.name}
              </Typography>
              <Chip size="small" label={e.env_type} />
              <StatusChip value={e.status} />
              <HealthChip status={e.health_status} />
              {e.sensitive_data && <Chip size="small" color="warning" variant="outlined" label="sensitive data" />}
              {e.production_derived_data && <Chip size="small" color="warning" variant="outlined" label="production-derived data" />}
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {e.description}
            </Typography>
            {(e.active_bookings ?? []).length > 0 && (
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                In use by {(e.active_bookings ?? []).map((b) => `${b.project} (until ${fmtDate(b.end_at)})`).join(', ')}
              </Typography>
            )}
          </Box>
          <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
            {canManage && <Button variant="outlined" onClick={() => setEdit(true)}>Edit</Button>}
            {canManage && <Button onClick={() => setClone(true)}>Clone</Button>}
            {canContribute && <Button onClick={() => setOverride(true)}>Set status</Button>}
            <Button onClick={() => subscribe.mutate()} disabled={subscribe.isSuccess}>{subscribe.isSuccess ? 'Subscribed' : 'Subscribe'}</Button>
            {canManage && (
              <Button
                color="error"
                onClick={async () => {
                  if (window.confirm(`Delete ${e.name}? You can restore it later from the deleted list.`)) {
                    await del.mutateAsync();
                    nav('/environments');
                  }
                }}
              >
                Delete
              </Button>
            )}
          </Stack>
        </Stack>
        {e.health_override && (
          <Alert severity="info" sx={{ mt: 1 }} action={canContribute && <Button size="small" onClick={() => clearOverride.mutate()}>Clear</Button>}>
            Status set to {e.health_override.status}: {e.health_override.reason}
            {e.health_override.until ? ` (until ${fmtDateTime(e.health_override.until)})` : ''}
          </Alert>
        )}
        {e.sla_breached && <Alert severity="error" sx={{ mt: 1 }}>This request is past its SLA ({fmtDate(e.sla_due_at)}).</Alert>}
        {conflict && <Alert severity="warning" sx={{ mt: 1 }}>Someone else changed this environment. <Button size="small" onClick={() => { update.reset(); move.reset(); env.refetch(); }}>Reload</Button></Alert>}
        <ErrorAlert error={!conflict ? (move.error ?? update.error ?? del.error) : null} />
      </Paper>

      <Paper variant="outlined">
        <Tabs value={tab} onChange={(_, v) => setParams({ tab: v })} variant="scrollable" sx={{ borderBottom: 1, borderColor: 'divider', px: 1 }}>
          {TABS.map((t) => (
            <Tab key={t} value={t} label={LABELS[t]} />
          ))}
        </Tabs>
        <Box sx={{ p: 2 }}>
          {tab === 'overview' && (
            <Stack spacing={2}>
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 2 }}>
                <Field label="Tier">{e.tier}</Field>
                <Field label="Purpose">{e.purpose}</Field>
                <Field label="Owner">{e.owner}</Field>
                <Field label="Delivery manager">{e.delivery_manager}</Field>
                <Field label="Technical contact">{e.technical_contact}</Field>
                <Field label="Support group">{e.support_group}</Field>
                <Field label="Programme">{e.programme}</Field>
                <Field label="Cost centre">{e.cost_centre}</Field>
                <Field label="Platform">{e.platform}</Field>
                <Field label="Cloud account / data centre">{e.hosting_location}</Field>
                <Field label="Region">{e.region}</Field>
                <Field label="Network zone">{e.network_zone}</Field>
                <Field label="Family">{e.family}</Field>
                <Field label="Child environments">{(e.children ?? []).map((c: Row) => c.name).join(', ')}</Field>
                <Field label="Tags">{e.tags.join(', ')}</Field>
                <Field label="Run cost / month">{e.run_cost ? e.run_cost.toLocaleString() : null}</Field>
                <Field label="Chargeback">{e.chargeback_model}</Field>
                <Field label="CMDB id">{e.cmdb_id}</Field>
                <Field label="Health check">{e.health_check_url}</Field>
                <Field label="Data controls">{e.data_controls}</Field>
                <Field label="Licence constraints">{e.licence_notes}</Field>
                <Field label="Retirement date">{e.retirement_date ? fmtDate(e.retirement_date) : null}</Field>
                <Field label="Last changed">{`${fmtDateTime(e.updated_at)} by ${e.updated_by ?? '—'} (v${e.row_version})`}</Field>
                {e.requested_by && <Field label="Requested">{`${e.requested_by}, ${fmtDate(e.requested_at)} · SLA ${fmtDate(e.sla_due_at)}`}</Field>}
                {Object.entries(e.attributes ?? {}).map(([k, v]) => (
                  <Field key={k} label={meta.data?.custom_attributes.find((a) => a.key === k)?.label ?? k}>{String(v)}</Field>
                ))}
              </Box>
              {e.urls.length > 0 && (
                <Box>
                  <Typography variant="caption" color="text.secondary">Access URLs</Typography>
                  <Stack direction="row" spacing={2}>
                    {e.urls.map((u) => (
                      <Link key={u.url} href={u.url} target="_blank" rel="noreferrer">{u.label || u.url}</Link>
                    ))}
                  </Stack>
                </Box>
              )}
              {canManage && e.allowed_transitions.length > 0 && (
                <Section title="Lifecycle">
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="body2">Move from <strong>{e.status}</strong> to</Typography>
                    {e.allowed_transitions.map((t) => (
                      <Button key={t} size="small" variant="outlined" onClick={() => move.mutate(t)} disabled={move.isPending}>
                        {t}
                      </Button>
                    ))}
                    <TextField size="small" label="Reason (logged)" value={reason} onChange={(ev) => setReason(ev.target.value)} sx={{ minWidth: 240 }} />
                  </Stack>
                </Section>
              )}
              {e.decommission_checklist.length > 0 && (
                <Section title="Decommissioning checklist">
                  {e.decommission_checklist.map((item: Row, i: number) => (
                    <Box key={item.item}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={item.done}
                            disabled={!canManage}
                            onChange={(ev) =>
                              checklist.mutate(e.decommission_checklist.map((x: Row, j: number) => (j === i ? { ...x, done: ev.target.checked } : x)))
                            }
                          />
                        }
                        label={item.item + (item.done ? ` — ${item.by}, ${fmtDate(item.at)}` : '')}
                      />
                    </Box>
                  ))}
                </Section>
              )}
            </Stack>
          )}
          {tab === 'topology' && <TopologyTab env={e} canEdit={canContribute} />}
          {tab === 'deployments' && <DeploymentsTab env={e} canEdit={canContribute} />}
          {tab === 'config' && <ConfigTab env={e} canEdit={canContribute} canManage={canManage} />}
          {tab === 'bookings' && <BookingsTab env={e} />}
          {tab === 'issues' && <IssuesTab env={e} />}
          {tab === 'data' && <DataTab env={e} canEdit={canContribute} />}
          {tab === 'health' && <HealthTab env={e} />}
          {tab === 'readiness' && <ReadinessTab env={e} />}
        </Box>
      </Paper>

      <FormDialog
        open={edit}
        title={`Edit ${e.name}`}
        fields={environmentFields(meta.data, (all.data ?? []).filter((x) => x.id !== e.id))}
        initial={e}
        onClose={() => setEdit(false)}
        onSubmit={(v) => update.mutateAsync(v)}
      />
      <FormDialog
        open={clone}
        title={`Clone ${e.name}`}
        fields={[
          { key: 'name', label: 'New name', required: true },
          { key: 'status', label: 'Initial status', type: 'select', options: ['Provisioning', 'Requested', 'Available'], required: true },
          { key: 'include_topology', label: 'Copy topology (systems and integrations)', type: 'checkbox' },
          { key: 'include_variables', label: 'Copy configuration (secret values are not copied)', type: 'checkbox' },
        ]}
        initial={{ name: `${e.name}-copy`, status: 'Provisioning', include_topology: true, include_variables: true }}
        onClose={() => setClone(false)}
        onSubmit={async (v) => {
          const r = await api.post(`/environments/${id}/clone`, v);
          nav(`/environments/${r.id}`);
        }}
        submitLabel="Clone"
      />
      <FormDialog
        open={override}
        title="Set status manually / planned outage"
        fields={[
          { key: 'status', label: 'Status', type: 'select', options: ['Healthy', 'Degraded', 'Down', 'Unknown'], required: true },
          { key: 'reason', label: 'Reason', required: true },
          { key: 'until', label: 'Until (optional)', type: 'datetime' },
        ]}
        initial={{ status: 'Down' }}
        onClose={() => setOverride(false)}
        onSubmit={(v) => api.post(`/environments/${id}/health/override`, v).then(() => env.refetch())}
      />
    </Stack>
  );
}

export function EnvSelect({ value, onChange, label = 'Environment', exclude }: { value: number | ''; onChange: (id: number) => void; label?: string; exclude?: number }) {
  const envs = useEnvironments();
  return (
    <TextField select size="small" label={label} value={value} onChange={(e) => onChange(Number(e.target.value))} sx={{ minWidth: 160 }}>
      {(envs.data ?? []).filter((e) => e.id !== exclude).map((e) => (
        <MenuItem key={e.id} value={e.id}>
          {e.name}
        </MenuItem>
      ))}
    </TextField>
  );
}
