// RPT-04..09, BKG-07, CHG-05/06: utilisation, contention, forecast, cost, data quality, test impact, issues.
import { Alert, Box, Button, MenuItem, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { api, useGet, type Row } from '../api/platform';
import { DataTable, Kpi, Section, StatusChip, type Column } from './common';

function Bar({ pct, warn = 80, bad = 100 }: { pct: number; warn?: number; bad?: number }) {
  const color = pct >= bad ? 'error.main' : pct >= warn ? 'warning.main' : 'primary.main';
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 160 }}>
      <Box sx={{ flex: 1, height: 8, bgcolor: 'grey.200', borderRadius: 1 }} aria-hidden>
        <Box sx={{ width: `${Math.min(pct, 100)}%`, height: '100%', bgcolor: color, borderRadius: 1 }} />
      </Box>
      <Typography variant="caption" sx={{ width: 44, textAlign: 'right' }}>{pct}%</Typography>
    </Stack>
  );
}

function Exports({ path, params }: { path: string; params?: Record<string, string | undefined> }) {
  return (
    <Stack direction="row" spacing={1}>
      <Button size="small" href={api.url(path, { ...params, format: 'csv' })}>CSV</Button>
      <Button size="small" href={api.url(path, { ...params, format: 'xlsx' })}>Excel</Button>
      <Button size="small" onClick={() => window.print()}>Print / PDF</Button>
    </Stack>
  );
}

function Utilisation() {
  const [group, setGroup] = useState('environment');
  const [days, setDays] = useState(30);
  const start = useMemo(() => new Date(Math.floor(Date.now() / 60_000) * 60_000 - days * 86_400_000).toISOString(), [days]);
  const r = useGet('/reports/utilisation', { group_by: group, start });
  const cols: Column[] =
    group === 'environment'
      ? [
          { key: 'environment', label: 'Environment' },
          { key: 'env_type', label: 'Type' },
          { key: 'utilisation_pct', label: 'Utilisation', render: (x) => <Bar pct={x.utilisation_pct} warn={85} bad={101} /> },
          { key: 'booked_hours', label: 'Booked h' },
          { key: 'idle_hours', label: 'Idle h' },
          { key: 'bookings', label: 'Bookings' },
          { key: 'programme', label: 'Programme' },
        ]
      : [{ key: group, label: group === 'team' ? 'Team' : 'Project' }, { key: 'booked_hours', label: 'Booked h' }, { key: 'bookings', label: 'Bookings' }, { key: 'environments', label: 'Environments' }];
  const idle = ((r.data?.rows ?? []) as Row[]).filter((x) => x.utilisation_pct !== undefined && x.utilisation_pct < 20);
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} justifyContent="space-between">
        <Stack direction="row" spacing={1}>
          <TextField select size="small" label="Group by" value={group} onChange={(e) => setGroup(e.target.value)}>
            {['environment', 'team', 'project'].map((g) => <MenuItem key={g} value={g}>{g}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[7, 30, 90, 365].map((d) => <MenuItem key={d} value={d}>last {d} days</MenuItem>)}
          </TextField>
        </Stack>
        <Exports path="/reports/utilisation" params={{ group_by: group, start }} />
      </Stack>
      {group === 'environment' && idle.length > 0 && <Alert severity="info">Mostly idle (under 20% booked): {idle.map((x) => x.environment).join(', ')} — candidates to share or retire.</Alert>}
      <DataTable rows={r.data?.rows ?? []} columns={cols} label="Utilisation" rowKey={group === 'environment' ? 'environment_id' : group} />
    </Stack>
  );
}

function Contention() {
  const r = useGet('/reports/contention', { weeks: 12 });
  const f = useGet('/reports/forecast', { weeks: 12 });
  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between"><Typography variant="subtitle2">Over-subscribed environments and weeks (requested + waitlisted demand)</Typography><Exports path="/reports/contention" /></Stack>
      <DataTable
        rows={((r.data?.rows ?? []) as Row[]).map((x, i): Row => ({ ...x, id: i }))}
        columns={[
          { key: 'environment', label: 'Environment' },
          { key: 'week_start', label: 'Week of' },
          { key: 'demand_pct', label: 'Demand', render: (x) => <Bar pct={x.demand_pct} /> },
          { key: 'overlaps', label: 'Overlaps' },
          { key: 'waitlisted', label: 'Waitlisted' },
          { key: 'projects', label: 'Projects' },
          { key: 'oversubscribed', label: 'Status', render: (x) => <StatusChip value={x.oversubscribed ? 'red' : 'green'} label={x.oversubscribed ? 'over-subscribed' : 'ok'} /> },
        ]}
        label="Contention"
      />
      <Stack direction="row" justifyContent="space-between"><Typography variant="subtitle2">Demand versus supply by environment type (next 12 weeks)</Typography><Exports path="/reports/forecast" /></Stack>
      <DataTable
        rows={((f.data?.rows ?? []) as Row[]).map((x, i): Row => ({ ...x, id: i }))}
        columns={[
          { key: 'env_type', label: 'Type' },
          { key: 'week_start', label: 'Week of' },
          { key: 'environments', label: 'Supply (envs)' },
          { key: 'demand_pct', label: 'Demand', render: (x) => <Bar pct={x.demand_pct ?? 0} /> },
          { key: 'shortfall_environments', label: 'Shortfall (envs)' },
        ]}
        label="Forecast"
      />
    </Stack>
  );
}

function Cost() {
  const [group, setGroup] = useState('programme');
  const r = useGet('/reports/cost', { group_by: group });
  const rows = (r.data?.rows ?? []) as Row[];
  const total = rows.reduce((s, x) => s + (x.monthly_cost ?? x.allocated_cost ?? 0), 0);
  return (
    <Stack spacing={1}>
      <Stack direction="row" justifyContent="space-between">
        <TextField select size="small" label="Group by" value={group} onChange={(e) => setGroup(e.target.value)}>
          {['environment', 'programme', 'cost_centre', 'project'].map((g) => <MenuItem key={g} value={g}>{g.replace('_', ' ')}</MenuItem>)}
        </TextField>
        <Exports path="/reports/cost" params={{ group_by: group }} />
      </Stack>
      <Kpi label={group === 'project' ? 'Allocated (30 days)' : 'Run cost per month'} value={total.toLocaleString(undefined, { maximumFractionDigits: 0 })} />
      <DataTable rows={rows.map((x, i): Row => ({ ...x, id: i }))} columns={Object.keys(rows[0] ?? {}).map((k) => ({ key: k, label: k.replace(/_/g, ' ') }))} label="Cost" />
    </Stack>
  );
}

function Quality() {
  const r = useGet('/reports/data-quality');
  if (!r.data) return null;
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between">
        <Stack direction="row" spacing={2}>
          <Kpi label="Data quality score" value={`${r.data.summary.score}%`} />
          <Kpi label="Findings" value={r.data.summary.findings} hint={`${r.data.summary.errors} errors`} />
        </Stack>
        <Exports path="/reports/data-quality" />
      </Stack>
      <DataTable
        rows={(r.data.findings as Row[]).map((x, i): Row => ({ ...x, id: i }))}
        columns={[
          { key: 'severity', label: 'Severity', render: (x) => <StatusChip value={x.severity === 'error' ? 'red' : x.severity === 'warning' ? 'amber' : 'green'} label={x.severity} /> },
          { key: 'kind', label: 'Check', value: (x) => x.kind.replace(/_/g, ' ') },
          { key: 'detail', label: 'Finding' },
          { key: 'link', label: '', render: (x) => x.link ? <Button size="small" component={RouterLink} to={x.link}>Fix</Button> : null },
        ]}
        label="Data quality findings"
        page="data-quality"
      />
    </Stack>
  );
}

function Impact() {
  const r = useGet('/reports/test-impact');
  const i = useGet('/reports/issues');
  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between"><Kpi label="Test hours lost (90 days)" value={r.data?.total_hours_lost ?? '—'} /><Exports path="/reports/test-impact" /></Stack>
      <DataTable rows={((r.data?.rows ?? []) as Row[]).map((x): Row => ({ ...x, id: x.booking_id }))} columns={[
        { key: 'environment', label: 'Environment' }, { key: 'project', label: 'Project' }, { key: 'team', label: 'Team' },
        { key: 'outage_hours', label: 'Outage h' }, { key: 'incident_hours_logged', label: 'Logged h' }, { key: 'incidents', label: 'Incidents' }, { key: 'hours_lost', label: 'Hours lost' },
      ]} label="Test impact" />
      <Typography variant="subtitle2">Issues by root cause</Typography>
      <DataTable rows={((i.data?.by_category ?? []) as Row[]).map((x): Row => ({ ...x, id: x.category }))} columns={[
        { key: 'category', label: 'Category' }, { key: 'total', label: 'Total' }, { key: 'open', label: 'Open' }, { key: 'sla_breached', label: 'SLA breached' }, { key: 'mean_hours_to_resolve', label: 'Mean h to resolve' },
      ]} label="Issues by category" />
      {i.data && <Typography variant="body2">Open issue ageing: {Object.entries(i.data.ageing).map(([k, v]) => `${k}: ${v}`).join(' · ')}</Typography>}
    </Stack>
  );
}

export default function ReportsPage() {
  const [tab, setTab] = useState('utilisation');
  return (
    <Section title="Reports">
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ mb: 2 }}>
        <Tab value="utilisation" label="Utilisation" />
        <Tab value="contention" label="Contention & forecast" />
        <Tab value="cost" label="Cost" />
        <Tab value="quality" label="Data quality" />
        <Tab value="impact" label="Test impact & issues" />
      </Tabs>
      {tab === 'utilisation' && <Utilisation />}
      {tab === 'contention' && <Contention />}
      {tab === 'cost' && <Cost />}
      {tab === 'quality' && <Quality />}
      {tab === 'impact' && <Impact />}
    </Section>
  );
}
