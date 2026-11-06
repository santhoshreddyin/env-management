// TOP-01 system catalogue, TOP-05 shared components, TOP-10 impact analysis.
import { Alert, Box, Button, Chip, List, ListItem, ListItemText, MenuItem, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { api, fmtDate, useCan, useGet, useMeta, type Row } from '../api/platform';
import { DataTable, FormDialog, HealthChip, Section } from './common';

function Impact({ initial }: { initial?: string }) {
  const systems = useGet<Row[]>('/catalogue/systems');
  const [sys, setSys] = useState(initial ?? '');
  const r = useGet(sys ? '/impact' : null, { system_id: sys });
  return (
    <Stack spacing={2}>
      <TextField select size="small" label="If this system has an outage or changes…" value={sys} onChange={(e) => setSys(e.target.value)} sx={{ maxWidth: 400 }}>
        {(systems.data ?? []).map((s) => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}
      </TextField>
      {r.data && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 2 }}>
          <Section title={`Environments (${r.data.environments.length})`}>
            <List dense>{r.data.environments.map((e: Row) => <ListItem key={e.id} disableGutters><ListItemText primary={<RouterLink to={`/environments/${e.id}`}>{e.name}</RouterLink>} secondary={`${e.owner ?? 'no owner'} · ${e.support_group ?? ''}`} /></ListItem>)}</List>
          </Section>
          <Section title={`Journeys and integrations (${r.data.integrations.length})`}>
            <Typography variant="body2" sx={{ mb: 1 }}>{r.data.journeys.join(', ')}</Typography>
            <List dense>{r.data.integrations.map((i: Row) => <ListItem key={i.id} disableGutters><ListItemText primary={i.name} secondary={i.journey} /></ListItem>)}</List>
            {r.data.dependent_systems.length > 0 && <Typography variant="caption">Connected systems: {r.data.dependent_systems.join(', ')}</Typography>}
          </Section>
          <Section title={`Bookings and projects (${r.data.bookings.length})`}>
            <List dense>{r.data.bookings.map((b: Row) => <ListItem key={b.id} disableGutters><ListItemText primary={`${b.project} on ${b.environment}`} secondary={`${b.status} until ${fmtDate(b.end_at)} · ${b.requested_by}`} /></ListItem>)}</List>
            {r.data.open_issues.length > 0 && <Alert severity="warning">Open issues: {r.data.open_issues.map((i: Row) => i.title).join(' · ')}</Alert>}
          </Section>
        </Box>
      )}
    </Stack>
  );
}

export default function CataloguePage() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get('system') ? 'impact' : 'catalogue');
  const cat = useGet<Row[]>('/catalogue/systems');
  const shared = useGet<Row[]>('/topology/shared');
  const meta = useMeta();
  const canManage = useCan('env_manager');
  const [edit, setEdit] = useState<Row | null>(null);
  return (
    <Section title="System catalogue" actions={<Button component={RouterLink} to="/data">Edit systems and integrations</Button>}>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="catalogue" label="Systems" />
        <Tab value="shared" label="Shared components" />
        <Tab value="impact" label="Impact analysis" />
      </Tabs>
      {tab === 'catalogue' && (
        <DataTable
          rows={cat.data ?? []}
          label="System catalogue"
          page="catalogue"
          onRowClick={canManage ? setEdit : undefined}
          columns={[
            { key: 'name', label: 'System' },
            { key: 'id', label: 'Id' },
            { key: 'category', label: 'Category' },
            { key: 'criticality', label: 'Criticality' },
            { key: 'technology', label: 'Technology' },
            { key: 'domain', label: 'Domain' },
            { key: 'owner', label: 'Owner' },
            { key: 'environments', label: 'Exists in', render: (s) => <Stack direction="row" spacing={0.5} flexWrap="wrap">{s.environments.map((e: string) => <Chip key={e} size="small" label={e} />)}</Stack> },
          ]}
        />
      )}
      {tab === 'shared' && (
        <DataTable
          rows={(shared.data ?? []).map((s): Row => ({ ...s, id: s.instance_id }))}
          label="Shared components"
          columns={[
            { key: 'system_name', label: 'System' },
            { key: 'instance_name', label: 'Instance' },
            { key: 'owner_environment', label: 'Hosted in' },
            { key: 'environments', label: 'Serves' },
            { key: 'health_status', label: 'Health', render: (s) => <HealthChip status={s.health_status} /> },
          ]}
          empty={<Typography variant="body2">No shared components. Mark an instance as serving other environments in its environment's Topology tab.</Typography>}
        />
      )}
      {tab === 'impact' && <Impact initial={params.get('system') ?? undefined} />}
      <FormDialog
        open={!!edit}
        title={`Catalogue details: ${edit?.name}`}
        fields={[
          { key: 'category', label: 'Category', type: 'select', options: meta.data?.system_categories ?? [] },
          { key: 'criticality', label: 'Criticality', type: 'select', options: ['critical', 'high', 'medium', 'low'] },
          { key: 'technology', label: 'Technology' },
          { key: 'owner', label: 'Owner' },
          { key: 'domain', label: 'Domain' },
        ]}
        initial={edit ?? {}}
        onClose={() => setEdit(null)}
        onSubmit={async (v) => { await api.put(`/catalogue/systems/${edit?.id}`, v); cat.refetch(); }}
      />
    </Section>
  );
}
