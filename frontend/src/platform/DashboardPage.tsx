// RPT-03 executive dashboard + HLT-07 status summary + RPT-10 first-run empty state.
import { Alert, Box, Button, Link, List, ListItem, ListItemText, Stack, Typography } from '@mui/material';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { api, fmtDate, fmtDateTime, useAction, useCan, useGet, type Row } from '../api/platform';
import { EmptyState, ErrorAlert, HealthChip, Kpi, Section, StatusChip } from './common';

export default function DashboardPage() {
  const d = useGet('/reports/dashboard');
  const status = useGet<Row[]>('/health/status', undefined, { refetchInterval: 60_000 });
  const isAdmin = useCan('admin');
  const sample = useAction(() => api.post('/admin/sample-data'));
  const nav = useNavigate();

  if (d.isError) return <ErrorAlert error={d.error} />;
  if (!d.data) return null;
  const x = d.data;
  if (x.environments === 0)
    return (
      <Section title="Welcome">
        <EmptyState
          title="No environments yet"
          action={
            <Stack direction="row" spacing={1} justifyContent="center">
              <Button variant="contained" onClick={() => nav('/environments?new=1')}>
                Register an environment
              </Button>
              <Button onClick={() => nav('/environments?import=1')}>Import from a file</Button>
              {isAdmin && (
                <Button onClick={() => sample.mutate()} disabled={sample.isPending}>
                  Load sample data
                </Button>
              )}
            </Stack>
          }
        >
          Start by registering your environments (DEV, SIT, UAT, PreProd…), or import them from CSV / Excel. Then map
          systems onto each one, record versions, and take bookings.
        </EmptyState>
        <ErrorAlert error={sample.error} />
      </Section>
    );

  const tone = (v: number | null, good: number, ok: number) => (v === null ? 'grey.400' : v >= good ? 'success.main' : v >= ok ? 'warning.main' : 'error.main');
  return (
    <Stack spacing={2}>
      <Stack direction="row" flexWrap="wrap" gap={1.5}>
        <Kpi label="Environments" value={x.environments} hint={Object.entries(x.by_type).map(([k, v]) => `${v} ${k}`).join(' · ')} />
        <Kpi label="Availability (30 days)" value={x.availability_30d_pct === null ? '—' : `${x.availability_30d_pct}%`} tone={tone(x.availability_30d_pct, 99.5, 97)} />
        <Kpi label="Utilisation (30 days)" value={`${x.utilisation_30d_pct}%`} hint="booked ÷ available time" />
        <Kpi label="Open issues" value={x.open_issues} hint={`${x.sla_breached} past SLA`} tone={x.sla_breached ? 'error.main' : undefined} />
        <Kpi label="Pending approvals" value={x.pending_approvals} tone={x.pending_approvals ? 'warning.main' : undefined} />
        <Kpi label="Data quality" value={`${x.data_quality.score}%`} hint={`${x.data_quality.findings} findings`} tone={tone(x.data_quality.score, 90, 70)} />
      </Stack>
      {x.unhealthy.length > 0 && (
        <Alert severity="warning">
          Not healthy:{' '}
          {x.unhealthy.map((u: Row, i: number) => (
            <span key={u.id}>
              {i > 0 && ', '}
              <Link component={RouterLink} to={`/environments/${u.id}`}>
                {u.name}
              </Link>{' '}
              ({u.health_status})
            </span>
          ))}
        </Alert>
      )}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '2fr 1fr' }, gap: 2 }}>
        <Section title="Status of every environment" actions={<Typography variant="caption">refreshes every minute</Typography>}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 1 }} aria-label="Environment status">
            {(status.data ?? []).map((e) => (
              <Box key={e.id} component={RouterLink} to={`/environments/${e.id}`} sx={{ p: 1.25, border: 1, borderColor: 'divider', borderRadius: 1, textDecoration: 'none', color: 'inherit', '&:hover': { bgcolor: 'action.hover' } }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography sx={{ fontWeight: 600 }}>{e.name}</Typography>
                  <HealthChip status={e.health_status} />
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {e.env_type} · {e.lifecycle}
                  {e.override ? ` · ${e.override}` : ''}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  {(() => {
                    const bad = e.instances.filter((i: Row) => ['Down', 'Degraded'].includes(i.health_status));
                    if (bad.length === 0) return `${e.instances.length} components`;
                    if (bad.length > 3) return `${bad.length} of ${e.instances.length} components down or degraded`;
                    return bad.map((i: Row) => `${i.name}: ${i.health_status}`).join(', ');
                  })()}
                </Typography>
              </Box>
            ))}
          </Box>
        </Section>
        <Stack spacing={2}>
          <Section title="In use now">
            <List dense disablePadding>
              {x.active_bookings.map((b: Row) => (
                <ListItem key={b.id} disableGutters>
                  <ListItemText primary={`${b.environment}: ${b.project}`} secondary={`${b.team ?? ''} until ${fmtDate(b.end_at)}`} />
                </ListItem>
              ))}
              {x.active_bookings.length === 0 && <Typography variant="body2">No active bookings.</Typography>}
            </List>
          </Section>
          <Section title="Next 14 days: changes, freezes, releases">
            <List dense disablePadding>
              {x.upcoming_changes.map((c: Row) => (
                <ListItem key={c.id} disableGutters>
                  <ListItemText primary={<><StatusChip value={c.kind} /> {c.title}</>} secondary={`${c.environment} · ${fmtDateTime(c.start_at)} – ${fmtDateTime(c.end_at)}`} />
                </ListItem>
              ))}
              {x.upcoming_changes.length === 0 && <Typography variant="body2">Nothing planned.</Typography>}
            </List>
          </Section>
        </Stack>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        <Section title="Recent deployments">
          <List dense disablePadding>
            {x.recent_deployments.map((r: Row) => (
              <ListItem key={r.id} disableGutters>
                <ListItemText primary={<>{r.system_id} {r.version} → {r.environment} <StatusChip value={r.outcome} /></>} secondary={fmtDateTime(r.deployed_at)} />
              </ListItem>
            ))}
          </List>
        </Section>
        <Section title="Open issues by severity" actions={<Button size="small" component={RouterLink} to="/issues">All issues</Button>}>
          <Stack direction="row" spacing={1}>
            {['critical', 'high', 'medium', 'low'].map((s) => (
              <Kpi key={s} label={s} value={x.open_issues_by_severity[s] ?? 0} tone={s === 'critical' ? 'error.main' : s === 'high' ? 'warning.main' : 'grey.400'} />
            ))}
          </Stack>
        </Section>
      </Box>
    </Stack>
  );
}
