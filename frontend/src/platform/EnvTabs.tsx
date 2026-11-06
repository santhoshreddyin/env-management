// Environment detail tabs: deployments, bookings, issues, test data, health, readiness.
import { Alert, Box, Button, Chip, List, ListItem, ListItemText, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useState } from 'react';
import { api, fmtDate, fmtDateTime, useAction, useCan, useGet, type Environment, type Row } from '../api/platform';
import { DataTable, ErrorAlert, FormDialog, HealthChip, Kpi, Section, StatusChip, type Column } from './common';
import { BookingDialog, IssueDialog } from './dialogs';
import { EnvSelect } from './EnvironmentDetailPage';

export const DEPLOYMENT_COLUMNS: Column[] = [
  { key: 'deployed_at', label: 'When', value: (d) => d.deployed_at, render: (d) => fmtDateTime(d.deployed_at) },
  { key: 'environment', label: 'Environment' },
  { key: 'system_name', label: 'System', value: (d) => d.system_name ?? d.system_id },
  { key: 'version', label: 'Version' },
  { key: 'build', label: 'Build' },
  { key: 'outcome', label: 'Outcome', render: (d) => <StatusChip value={d.outcome} /> },
  { key: 'deployed_by', label: 'By' },
  { key: 'source', label: 'Source', render: (d) => <>{d.source}{d.tool ? ` (${d.tool})` : ''}</> },
  { key: 'pipeline', label: 'Pipeline', render: (d) => d.pipeline_run_url ? <a href={d.pipeline_run_url} target="_blank" rel="noreferrer">{d.pipeline ?? 'run'}</a> : d.pipeline },
  { key: 'commit_sha', label: 'Commit', hidden: true },
  { key: 'release', label: 'Release', hidden: true },
  { key: 'rollback_of_id', label: 'Rollback of', hidden: true },
];

export function DeploymentsTab({ env, canEdit }: { env: Environment; canEdit: boolean }) {
  const deps = useGet<Row[]>('/deployments', { environment_id: env.id });
  const insts = useGet<Row[]>(`/environments/${env.id}/instances`);
  const [open, setOpen] = useState(false);
  const [warn, setWarn] = useState<string[]>([]);
  const rollback = useAction((id: number) => api.post(`/deployments/${id}/rollback`));
  const cols = [...DEPLOYMENT_COLUMNS.filter((c) => c.key !== 'environment'), ...(canEdit ? [{ key: 'rb', label: '', render: (d: Row) => d.outcome === 'success' ? <Button size="small" onClick={() => window.confirm(`Record a rollback of ${d.system_id} ${d.version}?`) && rollback.mutate(d.id)}>Roll back</Button> : null }] : [])];
  return (
    <Stack spacing={1}>
      {warn.length > 0 && <Alert severity="warning" onClose={() => setWarn([])}>{warn.join(' · ')}</Alert>}
      <ErrorAlert error={rollback.error} />
      <DataTable rows={deps.data ?? []} columns={cols} label="Deployments" toolbar={canEdit && <Button size="small" variant="contained" onClick={() => setOpen(true)}>Record deployment</Button>} />
      <Typography variant="caption" color="text.secondary">
        Pipelines report deployments automatically with <code>POST /api/v1/ci/deployments</code> and an API token (see Admin → API tokens).
      </Typography>
      <FormDialog
        open={open}
        title={`Record a deployment to ${env.name}`}
        fields={[
          { key: 'instance_id', label: 'System', type: 'select', required: true, options: (insts.data ?? []).filter((i) => !i.shared_in).map((i) => ({ value: i.id, label: i.instance_name })) },
          { key: 'version', label: 'Version', required: true },
          { key: 'build', label: 'Build' },
          { key: 'commit_sha', label: 'Commit' },
          { key: 'release', label: 'Release' },
          { key: 'outcome', label: 'Outcome', type: 'select', options: ['success', 'failed', 'in_progress'], required: true },
          { key: 'pipeline', label: 'Pipeline' },
          { key: 'pipeline_run_url', label: 'Pipeline run URL' },
          { key: 'override_reason', label: 'Freeze override reason', help: 'Needed only during an enforced freeze' },
          { key: 'notes', label: 'Notes', type: 'multiline' },
        ]}
        initial={{ outcome: 'success' }}
        onClose={() => setOpen(false)}
        onSubmit={async (v) => {
          const r = await api.post('/deployments', v);
          setWarn(r.warnings ?? []);
          deps.refetch();
          insts.refetch();
        }}
      />
    </Stack>
  );
}

export const BOOKING_COLUMNS: Column[] = [
  { key: 'environment', label: 'Environment' },
  { key: 'project', label: 'Project' },
  { key: 'team', label: 'Team' },
  { key: 'start_at', label: 'From', value: (b) => b.start_at, render: (b) => fmtDateTime(b.start_at) },
  { key: 'end_at', label: 'To', value: (b) => b.end_at, render: (b) => fmtDateTime(b.end_at) },
  { key: 'status', label: 'Status', render: (b) => <>{<StatusChip value={b.status} />}{b.escalated && <Chip size="small" color="warning" label="escalated" sx={{ ml: 0.5 }} />}</> },
  { key: 'scope', label: 'Scope', value: (b) => (b.scope === 'whole' ? 'whole environment' : b.instances.join(', ')) },
  { key: 'priority', label: 'Priority' },
  { key: 'requested_by', label: 'Requested by' },
  { key: 'purpose', label: 'Purpose', hidden: true },
  { key: 'decided_by', label: 'Decided by', hidden: true },
  { key: 'decision_note', label: 'Note', hidden: true },
];

export function BookingActions({ b }: { b: Row }) {
  const access = useGet('/me/access');
  const canDecide = useCan('env_manager') || b.approver === access.data?.name;
  const decide = useAction((args: { decision: string }) => api.post(`/bookings/${b.id}/decision`, { ...args, apply_to_series: false }));
  const live = ['Requested', 'Approved', 'Active', 'Waitlisted'].includes(b.status);
  return (
    <Stack direction="row" spacing={0.5}>
      {b.status === 'Requested' && canDecide && <Button size="small" onClick={() => decide.mutate({ decision: 'approve' })}>Approve</Button>}
      {b.status === 'Requested' && canDecide && <Button size="small" color="error" onClick={() => decide.mutate({ decision: 'reject' })}>Reject</Button>}
      {live && (b.requested_by === access.data?.name || canDecide) && <Button size="small" onClick={() => window.confirm('Cancel this booking?') && decide.mutate({ decision: 'cancel' })}>Cancel</Button>}
      {decide.error && <Typography variant="caption" color="error">{decide.error.message}</Typography>}
    </Stack>
  );
}

export function BookingsTab({ env }: { env: Environment }) {
  const rows = useGet<Row[]>('/bookings', { environment_id: env.id });
  const [open, setOpen] = useState(false);
  const canBook = useCan('booker', env.my_level);
  return (
    <>
      <DataTable rows={rows.data ?? []} columns={[...BOOKING_COLUMNS.filter((c) => c.key !== 'environment'), { key: 'a', label: '', render: (b) => <BookingActions b={b} /> }]} label="Bookings" toolbar={canBook && <Button size="small" variant="contained" onClick={() => setOpen(true)}>Book</Button>} />
      <BookingDialog open={open} onClose={() => setOpen(false)} environmentId={env.id} onBooked={() => rows.refetch()} />
    </>
  );
}

export const ISSUE_COLUMNS: Column[] = [
  { key: 'id', label: '#' },
  { key: 'environment', label: 'Environment' },
  { key: 'title', label: 'Title', render: (i) => <>{i.title}{i.known_issue && <Chip size="small" label="known issue" sx={{ ml: 0.5 }} />}</> },
  { key: 'severity', label: 'Severity', render: (i) => <StatusChip value={i.severity} /> },
  { key: 'status', label: 'Status', render: (i) => <StatusChip value={i.status} /> },
  { key: 'owner', label: 'Owner' },
  { key: 'age_hours', label: 'Age (h)' },
  { key: 'sla_breached', label: 'SLA', value: (i) => (i.sla_breached ? 'breached' : ''), render: (i) => i.sla_breached ? <Chip size="small" color="error" label="breached" /> : '' },
  { key: 'external_ref', label: 'Ticket', render: (i) => i.external_url ? <a href={i.external_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{i.external_ref}</a> : i.external_ref },
  { key: 'category', label: 'Category', hidden: true },
  { key: 'kind', label: 'Kind', hidden: true },
  { key: 'hours_lost', label: 'Hours lost', hidden: true },
  { key: 'opened_at', label: 'Opened', render: (i) => fmtDateTime(i.opened_at), hidden: true },
];

export function IssuesTab({ env }: { env: Environment }) {
  const rows = useGet<Row[]>('/issues', { environment_id: env.id });
  const [edit, setEdit] = useState<Row | null>(null);
  return (
    <>
      <DataTable rows={rows.data ?? []} columns={ISSUE_COLUMNS.filter((c) => c.key !== 'environment')} label="Issues" onRowClick={setEdit} toolbar={<Button size="small" variant="contained" onClick={() => setEdit({})}>Log issue</Button>} />
      <IssueDialog open={!!edit} onClose={() => { setEdit(null); rows.refetch(); }} environmentId={env.id} initial={edit?.id ? edit : undefined} />
    </>
  );
}

export function DataTab({ env, canEdit }: { env: Environment; canEdit: boolean }) {
  const rows = useGet<Row[]>('/test-data', { environment_id: env.id });
  const [edit, setEdit] = useState<Row | null>(null);
  const [job, setJob] = useState<Row | null>(null);
  const reserve = useAction((id: number) => api.post(`/test-data/${id}/reserve`, {}));
  const release = useAction((id: number) => api.post(`/test-data/${id}/release`));
  const cols: Column[] = [
    { key: 'name', label: 'Data set' },
    { key: 'source', label: 'Source', value: (d) => [d.source, d.source_environment].filter(Boolean).join(' from ') },
    { key: 'volume', label: 'Volume' },
    { key: 'refresh_date', label: 'Refreshed', render: (d) => <>{fmtDate(d.refresh_date)}{d.refresh_age_days > 90 && <Chip size="small" color="warning" variant="outlined" label={`${d.refresh_age_days} days`} sx={{ ml: 0.5 }} />}</> },
    { key: 'masking_status', label: 'Masking', render: (d) => <StatusChip value={d.masking_status === 'masked' || d.masking_status === 'synthetic' ? 'green' : 'red'} label={d.masking_status} /> },
    { key: 'risk', label: 'Risk', render: (d) => <StatusChip value={d.risk === 'high' ? 'red' : d.risk === 'medium' ? 'amber' : 'green'} label={d.risk} /> },
    { key: 'owner', label: 'Owner' },
    { key: 'reserved_by', label: 'Reserved', value: (d) => (d.reserved_by ? `${d.reserved_by} until ${fmtDate(d.reserved_until)}` : '') },
    { key: 'jobs', label: 'Last job', value: (d) => (d.jobs[0] ? `${d.jobs[0].kind} ${d.jobs[0].status}` : '') },
    {
      key: 'a', label: '', render: (d) => (
        <Stack direction="row" spacing={0.5}>
          {d.reserved_by ? <Button size="small" onClick={() => release.mutate(d.id)}>Release</Button> : <Button size="small" onClick={() => reserve.mutate(d.id)}>Reserve</Button>}
          {canEdit && <Button size="small" onClick={() => setJob(d)}>Log job</Button>}
          {canEdit && <Button size="small" onClick={() => setEdit(d)}>Edit</Button>}
        </Stack>
      ),
    },
  ];
  return (
    <Stack spacing={1}>
      {(env.sensitive_data || env.production_derived_data) && <Alert severity="warning">This environment holds {env.production_derived_data ? 'production-derived' : 'sensitive'} data. Controls: {env.data_controls ?? 'not recorded'}</Alert>}
      <ErrorAlert error={reserve.error ?? release.error} />
      <DataTable rows={rows.data ?? []} columns={cols} label="Test data" toolbar={canEdit && <Button size="small" variant="contained" onClick={() => setEdit({ masking_status: 'masked' })}>Add data set</Button>} />
      <FormDialog
        open={!!edit}
        title={edit?.id ? `Edit ${edit.name}` : 'Add a test data set'}
        fields={[
          { key: 'name', label: 'Name', required: true },
          { key: 'description', label: 'Description', type: 'multiline' },
          { key: 'source', label: 'Source' },
          { key: 'volume', label: 'Volume' },
          { key: 'refresh_date', label: 'Refresh date', type: 'date' },
          { key: 'masking_status', label: 'Masking', type: 'select', options: ['masked', 'unmasked', 'synthetic', 'partial'], required: true },
          { key: 'production_derived', label: 'Derived from production', type: 'checkbox' },
          { key: 'system_id', label: 'System' },
          { key: 'owner', label: 'Owner' },
        ]}
        initial={edit ?? {}}
        onClose={() => setEdit(null)}
        onSubmit={async (v) => {
          if (edit?.id) await api.patch(`/test-data/${edit.id}`, v);
          else await api.post('/test-data', { ...v, environment_id: env.id });
          rows.refetch();
        }}
      />
      <FormDialog
        open={!!job}
        title={`Log a data job for ${job?.name}`}
        fields={[
          { key: 'kind', label: 'Job', type: 'select', options: ['refresh', 'mask', 'subset', 'synthesise'], required: true },
          { key: 'status', label: 'Status', type: 'select', options: ['scheduled', 'running', 'succeeded', 'failed'], required: true },
          { key: 'started_at', label: 'Started', type: 'datetime' },
          { key: 'finished_at', label: 'Finished', type: 'datetime' },
          { key: 'notes', label: 'Notes' },
        ]}
        initial={{ kind: 'refresh', status: 'succeeded' }}
        onClose={() => setJob(null)}
        onSubmit={async (v) => {
          await api.post(`/test-data/${job?.id}/jobs`, v);
          rows.refetch();
        }}
      />
    </Stack>
  );
}

export function HealthTab({ env }: { env: Environment }) {
  const metrics = useGet(`/environments/${env.id}/health/metrics`, { days: 30 });
  const history = useGet<Row[]>(`/environments/${env.id}/health/history`);
  const insts = useGet<Row[]>(`/environments/${env.id}/instances`);
  const run = useAction(() => api.post(`/environments/${env.id}/health/check`));
  const m = metrics.data;
  return (
    <Stack spacing={2}>
      <Stack direction="row" gap={1.5} flexWrap="wrap">
        <Kpi label="Current status" value={<HealthChip status={env.health_status} />} hint={`checked ${fmtDateTime(env.health_checked_at)}`} />
        <Kpi label="Uptime (30 days)" value={m?.uptime_pct === null || !m ? '—' : `${m.uptime_pct}%`} />
        <Kpi label="Outages" value={m?.outage_count ?? '—'} />
        <Kpi label="Mean time to restore" value={m?.mttr_hours ? `${m.mttr_hours} h` : '—'} />
      </Stack>
      <Stack direction="row" spacing={1}>
        <Button variant="outlined" onClick={() => run.mutate()} disabled={run.isPending}>Run checks now</Button>
        {run.data && <Typography variant="body2">{run.data.results.length === 0 ? 'No health check URLs configured on this environment or its systems.' : `${run.data.results.length} checks run.`}</Typography>}
      </Stack>
      <ErrorAlert error={run.error} />
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        <Section title="Components">
          <Table size="small">
            <TableBody>
              {(insts.data ?? []).map((i) => (
                <TableRow key={i.id}>
                  <TableCell>{i.instance_name}</TableCell>
                  <TableCell><HealthChip status={i.health_status} /></TableCell>
                  <TableCell>{fmtDateTime(i.health_checked_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
        <Section title="Results history">
          <List dense sx={{ maxHeight: 400, overflow: 'auto' }}>
            {(history.data ?? []).map((h) => (
              <ListItem key={h.id} disableGutters>
                <ListItemText primary={<><HealthChip status={h.status} /> {h.message}</>} secondary={`${fmtDateTime(h.checked_at)} · ${h.source}${h.response_ms ? ` · ${Math.round(h.response_ms)} ms` : ''}`} />
              </ListItem>
            ))}
          </List>
        </Section>
      </Box>
    </Stack>
  );
}

export function ReadinessTab({ env }: { env: Environment }) {
  const [baseline, setBaseline] = useState<number | ''>('');
  const r = useGet(`/reports/readiness/${env.id}`, { baseline_id: baseline || undefined });
  if (!r.data) return <ErrorAlert error={r.error} />;
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} alignItems="center">
        <Typography variant="h6">Overall:</Typography>
        <StatusChip value={r.data.overall} label={r.data.overall.toUpperCase()} />
        <EnvSelect value={baseline} onChange={setBaseline} label="Compare versions with" exclude={env.id} />
        <Button onClick={() => window.print()}>Print / PDF</Button>
      </Stack>
      <Table size="small" aria-label="Readiness checks">
        <TableHead>
          <TableRow>
            <TableCell>Area</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Detail</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {r.data.checks.map((c: Row) => (
            <TableRow key={c.area}>
              <TableCell>{c.area}</TableCell>
              <TableCell><StatusChip value={c.status} /></TableCell>
              <TableCell>{c.detail}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {r.data.known_issues.length > 0 && <Alert severity="info">Known issues: {r.data.known_issues.map((k: Row) => k.title).join(' · ')}</Alert>}
    </Stack>
  );
}
