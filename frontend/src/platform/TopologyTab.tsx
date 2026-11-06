// TOP-02..11: system instances, integrations, graph, journeys, compare, import/export for one environment.
import { Alert, Box, Button, ButtonGroup, Chip, IconButton, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import VerifiedIcon from '@mui/icons-material/Verified';
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from '@xyflow/react';
import { useMemo, useState } from 'react';
import { api, fmtDate, useAction, useEnvironments, useGet, type Environment, type Row } from '../api/platform';
import { DataTable, ErrorAlert, FormDialog, HealthChip, ImportDialog, Section, StatusChip, type Column, type Field } from './common';
import { EnvSelect } from './EnvironmentDetailPage';

const MODES = ['real', 'virtualised', 'stubbed', 'mocked', 'not_available'];
const EDGE_COLOR: Record<string, string> = { connected: '#16a34a', broken: '#dc2626', not_connected: '#94a3b8', virtualised: '#2563eb' };

function TopologyGraph({ instances, integrations }: { instances: Row[]; integrations: Row[] }) {
  const { nodes, edges } = useMemo(() => {
    // Lay out by role: systems that only send on the left, only receive on the right, the rest in the middle.
    const out = new Set(integrations.map((i) => i.from_instance_id));
    const inn = new Set(integrations.map((i) => i.to_instance_id));
    const col = (id: number) => (out.has(id) && !inn.has(id) ? 0 : inn.has(id) && !out.has(id) ? 2 : 1);
    const counts = [0, 0, 0];
    const nodes: Node[] = instances.map((i) => {
      const c = col(i.id);
      const y = counts[c]++ * 80;
      const border = i.health_status === 'Down' ? '#dc2626' : i.health_status === 'Degraded' ? '#d97706' : '#cbd5e1';
      return {
        id: String(i.id),
        position: { x: c * 320, y },
        data: { label: `${i.system_name ?? i.system_id}${i.deployed_version ? ` · ${i.deployed_version}` : ''}${i.mode !== 'real' ? ` (${i.mode})` : ''}${i.shared_in ? ' ⇄ shared' : ''}` },
        style: { border: `2px ${i.mode === 'real' ? 'solid' : 'dashed'} ${border}`, borderRadius: 8, fontSize: 12, width: 230, background: i.shared_in ? '#eff6ff' : '#fff' },
      };
    });
    const edges: Edge[] = integrations
      .filter((i) => i.from_instance_id && i.to_instance_id)
      .map((i) => ({
        id: `e${i.id}`,
        source: String(i.from_instance_id),
        target: String(i.to_instance_id),
        label: `${i.protocol ?? ''} ${i.status !== 'connected' ? i.status : ''}`.trim(),
        style: { stroke: EDGE_COLOR[i.status] ?? '#64748b', strokeDasharray: i.status === 'connected' ? undefined : '6 4', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[i.status] ?? '#64748b' },
        labelStyle: { fontSize: 11 },
      }));
    return { nodes, edges };
  }, [instances, integrations]);
  return (
    <Box sx={{ height: 520, border: 1, borderColor: 'divider', borderRadius: 1 }} data-testid="topology-graph">
      <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable proOptions={{ hideAttribution: true }}>
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </Box>
  );
}

export default function TopologyTab({ env, canEdit }: { env: Environment; canEdit: boolean }) {
  const base = `/environments/${env.id}`;
  const insts = useGet<Row[]>(`${base}/instances`);
  const ints = useGet<Row[]>(`${base}/integrations`);
  const catalogue = useGet<Row[]>('/catalogue/systems');
  const flowInts = useGet<Row[]>('/integrations');
  const envs = useEnvironments();
  const journeys = useGet<Row[]>(`${base}/journeys`);
  const [view, setView] = useState<'table' | 'graph' | 'journeys' | 'compare'>('table');
  const [editing, setEditing] = useState<Row | null>(null);
  const [editingInt, setEditingInt] = useState<Row | null>(null);
  const [importing, setImporting] = useState(false);
  const [other, setOther] = useState<number | ''>('');
  const compare = useGet(other ? '/topology/compare' : null, { left: env.id, right: other || undefined });
  const populate = useAction(() => api.post(`${base}/topology/populate`));
  const verify = useAction((id: number) => api.post(`/instances/${id}/verify`));
  const remove = useAction((id: number) => api.del(`/instances/${id}`));
  const removeInt = useAction((id: number) => api.del(`/environment-integrations/${id}`));

  const instFields: Field[] = [
    { key: 'system_id', label: 'System', type: 'select', required: true, options: (catalogue.data ?? []).map((s) => ({ value: s.id, label: s.name })) },
    { key: 'instance_name', label: 'Instance name', help: 'Defaults to SYSTEM-ENV' },
    { key: 'url', label: 'URL' },
    { key: 'deployed_version', label: 'Version' },
    { key: 'build', label: 'Build' },
    { key: 'release', label: 'Release' },
    { key: 'mode', label: 'Mode', type: 'select', options: MODES, required: true },
    { key: 'virtualisation_ref', label: 'Service-virtualisation asset' },
    { key: 'health_check_url', label: 'Health check URL' },
    { key: 'last_verified', label: 'Last verified', type: 'date' },
    { key: 'verified_by', label: 'Verified by' },
    { key: 'notes', label: 'Notes', type: 'multiline' },
  ];
  const ids = (insts.data ?? []).map((i) => ({ value: i.id, label: i.instance_name }));
  const intFields: Field[] = [
    { key: 'integration_id', label: 'Catalogue integration', type: 'select', options: (flowInts.data ?? []).map((i) => ({ value: i.id, label: `${i.id} ${i.name}` })) },
    { key: 'name', label: 'Name (if not in catalogue)' },
    { key: 'from_instance_id', label: 'From', type: 'select', options: ids },
    { key: 'to_instance_id', label: 'To', type: 'select', options: ids },
    { key: 'protocol', label: 'Protocol', type: 'select', options: ['REST', 'SOAP', 'MQ', 'FILE', 'MFT'] },
    { key: 'status', label: 'Status', type: 'select', options: ['connected', 'broken', 'not_connected', 'virtualised'], required: true },
    { key: 'endpoint', label: 'Endpoint' },
    { key: 'last_verified', label: 'Last verified', type: 'date' },
    { key: 'notes', label: 'Notes', type: 'multiline' },
  ];

  const instCols: Column[] = [
    { key: 'system_name', label: 'System', render: (i) => <>{i.system_name ?? <em>{i.system_id} (not in catalogue)</em>}</> },
    { key: 'instance_name', label: 'Instance', render: (i) => <>{i.instance_name}{i.shared_in && <Chip size="small" sx={{ ml: 1 }} label={`shared from ${i.environment}`} />}{i.shared_with.length > 0 && <Chip size="small" sx={{ ml: 1 }} label={`shared with ${i.shared_with.map((s: Row) => s.name).join(', ')}`} />}</> },
    { key: 'deployed_version', label: 'Version' },
    { key: 'mode', label: 'Mode', render: (i) => <Tooltip title={i.virtualisation_ref ?? ''}><span><StatusChip value={i.mode} /></span></Tooltip> },
    { key: 'health_status', label: 'Health', render: (i) => <HealthChip status={i.health_status} /> },
    { key: 'last_verified', label: 'Verified', render: (i) => <>{fmtDate(i.last_verified)} {i.stale && <Chip size="small" color="warning" variant="outlined" label="stale" />}</> },
    { key: 'url', label: 'URL', hidden: true },
    { key: 'build', label: 'Build', hidden: true },
    { key: 'verified_by', label: 'Verified by', hidden: true },
    {
      key: 'actions', label: '', render: (i) => canEdit && !i.shared_in ? (
        <Stack direction="row">
          <IconButton size="small" aria-label={`Verify ${i.instance_name}`} onClick={() => verify.mutate(i.id)}><VerifiedIcon fontSize="small" /></IconButton>
          <IconButton size="small" aria-label={`Edit ${i.instance_name}`} onClick={() => setEditing(i)}><EditIcon fontSize="small" /></IconButton>
          <IconButton size="small" aria-label={`Delete ${i.instance_name}`} onClick={() => window.confirm(`Remove ${i.instance_name} from ${env.name}?`) && remove.mutate(i.id)}><DeleteIcon fontSize="small" /></IconButton>
        </Stack>
      ) : null,
    },
  ];
  const intCols: Column[] = [
    { key: 'name', label: 'Integration', render: (i) => <>{i.integration_id && <Typography variant="caption" color="text.secondary">{i.integration_id} </Typography>}{i.name}</> },
    { key: 'journey', label: 'Journey' },
    { key: 'from_instance', label: 'From' },
    { key: 'to_instance', label: 'To' },
    { key: 'protocol', label: 'Protocol' },
    { key: 'hop_count', label: 'Hops' },
    { key: 'status', label: 'Status', render: (i) => <StatusChip value={i.status} /> },
    { key: 'endpoint', label: 'Endpoint', hidden: true },
    { key: 'last_verified', label: 'Verified', render: (i) => <>{fmtDate(i.last_verified)} {i.stale && <Chip size="small" color="warning" variant="outlined" label="stale" />}</> },
    {
      key: 'actions', label: '', render: (i) => canEdit ? (
        <Stack direction="row">
          <IconButton size="small" aria-label={`Edit integration ${i.name}`} onClick={() => setEditingInt(i)}><EditIcon fontSize="small" /></IconButton>
          <IconButton size="small" aria-label={`Delete integration ${i.name}`} onClick={() => window.confirm('Remove this integration?') && removeInt.mutate(i.id)}><DeleteIcon fontSize="small" /></IconButton>
        </Stack>
      ) : null,
    },
  ];

  const saveInstance = async (v: Row) => {
    if (editing?.id) await api.patch(`/instances/${editing.id}`, { ...v, row_version: editing.row_version });
    else await api.post(`${base}/instances`, v);
    insts.refetch();
  };
  const saveInt = async (v: Row) => {
    if (editingInt?.id) await api.patch(`/environment-integrations/${editingInt.id}`, v);
    else await api.post(`${base}/integrations`, v);
    ints.refetch();
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <ButtonGroup size="small">
          {(['table', 'graph', 'journeys', 'compare'] as const).map((v) => (
            <Button key={v} variant={view === v ? 'contained' : 'outlined'} onClick={() => setView(v)}>
              {v === 'table' ? 'Systems & integrations' : v === 'graph' ? 'Diagram' : v === 'journeys' ? 'Journeys' : 'Compare'}
            </Button>
          ))}
        </ButtonGroup>
        <Box sx={{ flex: 1 }} />
        {canEdit && <Button size="small" variant="contained" onClick={() => setEditing({ mode: 'real' })}>Add system</Button>}
        {canEdit && <Button size="small" onClick={() => setEditingInt({ status: 'connected' })}>Add integration</Button>}
        {canEdit && <Button size="small" onClick={() => populate.mutate()}>Add all from catalogue</Button>}
        {canEdit && <Button size="small" onClick={() => setImporting(true)}>Import</Button>}
        <Button size="small" href={api.url(`${base}/topology/export`, { format: 'xlsx' })}>Excel</Button>
        <Button size="small" href={api.url(`${base}/topology/export`, { format: 'json' })}>JSON</Button>
        <Button size="small" href={api.url(`${base}/topology/export`, { format: 'mermaid' })}>Diagram (Mermaid)</Button>
      </Stack>
      {populate.data && <Alert severity="success">Added {populate.data.instances_added} systems and {populate.data.integrations_added} integrations.</Alert>}
      <ErrorAlert error={populate.error ?? remove.error ?? verify.error} />

      {view === 'table' && (
        <>
          <Section title={`Systems in ${env.name}`}>
            <DataTable rows={insts.data ?? []} columns={instCols} label="System instances" page="instances" />
          </Section>
          <Section title="Integrations">
            <DataTable rows={ints.data ?? []} columns={intCols} label="Environment integrations" />
          </Section>
        </>
      )}
      {view === 'graph' && <TopologyGraph instances={insts.data ?? []} integrations={ints.data ?? []} />}
      {view === 'graph' && (
        <Typography variant="caption" color="text.secondary">
          Solid border: real system · dashed: virtualised/stubbed · red/amber border: down/degraded · blue fill: shared from another environment. Edge colour and dash show integration status.
        </Typography>
      )}
      {view === 'journeys' && (
        <Stack spacing={1}>
          {(journeys.data ?? []).map((j) => (
            <Section key={j.journey} title={j.journey} actions={<StatusChip value={j.complete ? 'green' : 'amber'} label={j.complete ? 'complete' : 'gaps'} />}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                {j.systems.map((s: Row) => `${s.system_name}${s.mode !== 'real' ? ` (${s.mode.replace('_', ' ')})` : ''}`).join(' · ')}
              </Typography>
              <Table size="small">
                <TableBody>
                  {j.integrations.map((i: Row) => (
                    <TableRow key={i.integration_id}>
                      <TableCell>{i.name}</TableCell>
                      <TableCell><StatusChip value={i.status} /></TableCell>
                      <TableCell>{i.missing_systems.length ? `Missing: ${i.missing_systems.join(', ')}` : ''}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          ))}
        </Stack>
      )}
      {view === 'compare' && (
        <Section title="Compare topology" actions={<EnvSelect value={other} onChange={setOther} label="Compare with" exclude={env.id} />}>
          {!other && <Typography variant="body2">Choose an environment to compare with {env.name}.</Typography>}
          {compare.data && (
            <>
              <Typography variant="body2" sx={{ mb: 1 }}>
                {compare.data.summary.systems_different} systems and {compare.data.summary.integrations_different} integrations differ.
              </Typography>
              <Table size="small" aria-label="Topology comparison">
                <TableHead>
                  <TableRow>
                    <TableCell>System</TableCell>
                    <TableCell>{env.name}</TableCell>
                    <TableCell>{compare.data.right.name}</TableCell>
                    <TableCell>Differences</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {compare.data.systems.map((s: Row) => (
                    <TableRow key={s.system_id} sx={{ bgcolor: s.differences.length ? '#fef3c7' : undefined }}>
                      <TableCell>{s.system_name}</TableCell>
                      <TableCell>{s.left ? `${s.left.version ?? '—'} (${s.left.mode})` : <em>missing</em>}</TableCell>
                      <TableCell>{s.right ? `${s.right.version ?? '—'} (${s.right.mode})` : <em>missing</em>}</TableCell>
                      <TableCell>{s.differences.join(', ')}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </Section>
      )}

      <FormDialog
        open={!!editing}
        title={editing?.id ? `Edit ${editing.instance_name}` : 'Add a system to this environment'}
        fields={editing?.id ? [...instFields.slice(1), { key: 'shared_with', label: 'Also serves (environment ids, comma-separated)', type: 'tags' }] : instFields}
        initial={editing ? { ...editing, shared_with: (editing.shared_with ?? []).map((s: Row) => s.id) } : {}}
        onClose={() => setEditing(null)}
        onSubmit={async (v) => {
          if (Array.isArray(v.shared_with)) v.shared_with = v.shared_with.map(Number).filter(Boolean);
          await saveInstance(v);
        }}
        extra={editing?.id ? <Typography variant="caption">Environments: {(envs.data ?? []).map((e) => `${e.id}=${e.name}`).join(', ')}</Typography> : undefined}
      />
      <FormDialog open={!!editingInt} title={editingInt?.id ? 'Edit integration' : 'Add integration'} fields={intFields} initial={editingInt ?? {}} onClose={() => setEditingInt(null)} onSubmit={saveInt} />
      <ImportDialog
        open={importing}
        onClose={() => { setImporting(false); insts.refetch(); ints.refetch(); }}
        title={`Import topology into ${env.name}`}
        path={`${base}/topology/import`}
        accept=".xlsx,.json,.csv"
        hint="Excel with Instances and Integrations sheets (as exported), JSON {instances, integrations}, or CSV of instances. Rows update existing instances by instance_name."
      />
    </Stack>
  );
}
