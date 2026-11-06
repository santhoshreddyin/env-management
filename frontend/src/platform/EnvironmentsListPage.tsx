// Environment inventory list (ENV-*, RPT-02): filters, sort, columns, saved views, create/request/import/export.
import AddIcon from '@mui/icons-material/Add';
import { Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, useAction, useCan, useEnvironments, useMeta, type Environment } from '../api/platform';
import { DataTable, EmptyState, ErrorAlert, FormDialog, HealthChip, ImportDialog, Section, StatusChip, type Column } from './common';
import { environmentFields } from './environmentFields';

const COLUMNS: Column<Environment>[] = [
  { key: 'name', label: 'Name', render: (e) => <strong>{e.name}</strong> },
  { key: 'env_type', label: 'Type' },
  { key: 'status', label: 'Lifecycle', render: (e) => <StatusChip value={e.status} /> },
  { key: 'health_status', label: 'Health', render: (e) => <HealthChip status={e.health_status} /> },
  { key: 'owner', label: 'Owner', render: (e) => e.owner ?? <Typography variant="caption" color="error">missing</Typography> },
  { key: 'programme', label: 'Programme' },
  { key: 'region', label: 'Region' },
  {
    key: 'active_bookings',
    label: 'Booked by',
    value: (e) => (e.active_bookings ?? []).map((b) => b.project).join(', '),
  },
  { key: 'instance_count', label: 'Systems' },
  { key: 'open_issues', label: 'Open issues' },
  { key: 'tier', label: 'Tier', hidden: true },
  { key: 'platform', label: 'Platform', hidden: true },
  { key: 'family', label: 'Family', hidden: true },
  { key: 'parent', label: 'Parent', hidden: true },
  { key: 'support_group', label: 'Support group', hidden: true },
  { key: 'cost_centre', label: 'Cost centre', hidden: true },
  { key: 'run_cost', label: 'Run cost / month', hidden: true },
  { key: 'tags', label: 'Tags', hidden: true },
  { key: 'variable_count', label: 'Variables', hidden: true },
];

export default function EnvironmentsListPage() {
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [deleted, setDeleted] = useState(false);
  const envs = useEnvironments({ ...filters, deleted_only: deleted || undefined });
  const all = useEnvironments();
  const meta = useMeta();
  const nav = useNavigate();
  const canManage = useCan('env_manager');
  const canRequest = useCan('booker');
  const create = useAction((v: Record<string, unknown>) => api.post<Environment>('/environments', v));
  const request = useAction((v: Record<string, unknown>) => api.post<Environment>('/environments/requests', v));
  const restore = useAction((id: number) => api.post(`/environments/${id}/restore`));
  const showNew = params.get('new') === '1';
  const showRequest = params.get('request') === '1';
  const showImport = params.get('import') === '1';
  const createdId = useRef<number | null>(null);
  const close = () => {
    if (createdId.current !== null) {
      nav(`/environments/${createdId.current}`);
      createdId.current = null;
    } else setParams({});
  };

  const filter = (key: string, label: string, options: string[]) => (
    <TextField select size="small" label={label} value={filters[key] ?? ''} sx={{ minWidth: 130 }} onChange={(e) => setFilters((f) => ({ ...f, [key]: e.target.value }))}>
      <MenuItem value="">All</MenuItem>
      {options.map((o) => (
        <MenuItem key={o} value={o}>
          {o}
        </MenuItem>
      ))}
    </TextField>
  );

  const cols: Column<Environment>[] = deleted
    ? [...COLUMNS.slice(0, 2), { key: 'deleted_at', label: 'Deleted', value: (e) => e.deleted_at }, { key: 'restore', label: '', render: (e) => <Button size="small" onClick={(ev) => { ev.stopPropagation(); restore.mutate(e.id); }}>Restore</Button> }]
    : COLUMNS;

  return (
    <Section
      title="Environment inventory"
      actions={
        <>
          {canManage && (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setParams({ new: '1' })}>
              New environment
            </Button>
          )}
          {canRequest && !canManage && <Button variant="contained" onClick={() => setParams({ request: '1' })}>Request an environment</Button>}
          {canManage && <Button onClick={() => setParams({ request: '1' })}>Request</Button>}
          {canManage && <Button onClick={() => setParams({ import: '1' })}>Import</Button>}
          <Button href={api.url('/environments/export', { format: 'xlsx' })}>Export Excel</Button>
        </>
      }
    >
      <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: 'wrap', rowGap: 1 }}>
        {filter('env_type', 'Type', meta.data?.env_types ?? [])}
        {filter('status', 'Lifecycle', meta.data?.lifecycle ?? [])}
        {filter('health', 'Health', ['Healthy', 'Degraded', 'Down', 'Unknown'])}
        {filter('programme', 'Programme', meta.data?.programmes ?? [])}
        {filter('region', 'Region', meta.data?.regions ?? [])}
        {filter('tag', 'Tag', meta.data?.tags ?? [])}
        <TextField select size="small" label="Show" value={deleted ? 'deleted' : 'live'} onChange={(e) => setDeleted(e.target.value === 'deleted')} sx={{ minWidth: 120 }}>
          <MenuItem value="live">Current</MenuItem>
          <MenuItem value="deleted">Deleted</MenuItem>
        </TextField>
      </Stack>
      <ErrorAlert error={envs.error ?? restore.error} />
      <DataTable
        rows={envs.data ?? []}
        columns={cols}
        page="environments"
        label="Environments"
        onRowClick={deleted ? undefined : (e) => nav(`/environments/${e.id}`)}
        empty={
          <EmptyState title="No environments match" action={canManage ? <Button onClick={() => setParams({ new: '1' })}>Register one</Button> : undefined}>
            Register an environment, import a CSV/Excel file, or (as an administrator) load the sample data from the dashboard.
          </EmptyState>
        }
      />
      <FormDialog
        open={showNew}
        title="New environment"
        fields={environmentFields(meta.data, all.data ?? [])}
        initial={{ env_type: 'DEV' }}
        onClose={close}
        onSubmit={async (v) => {
          const e = await create.mutateAsync(v);
          createdId.current = e.id;
        }}
        submitLabel="Create"
      />
      <FormDialog
        open={showRequest}
        title="Request a new environment"
        fields={[
          { key: 'name', label: 'Proposed name', required: true },
          { key: 'env_type', label: 'Type', type: 'select', options: meta.data?.env_types ?? [], required: true },
          { key: 'programme', label: 'Programme' },
          { key: 'needed_by', label: 'Needed by', type: 'date' },
          { key: 'justification', label: 'Why is it needed?', type: 'multiline', required: true },
        ]}
        initial={{ env_type: 'SIT' }}
        onClose={close}
        onSubmit={async (v) => {
          const e = await request.mutateAsync(v);
          createdId.current = e.id;
        }}
        submitLabel="Submit request"
      />
      <ImportDialog
        open={showImport}
        onClose={close}
        title="Import environments"
        path="/environments/import"
        accept=".csv,.xlsx,.json"
        hint="CSV, Excel or JSON with a header row. Rows match existing environments by name (update) or create new ones. Columns: name, env_type, owner, programme, region, tags, parent, … (same as the export)."
      />
    </Section>
  );
}
