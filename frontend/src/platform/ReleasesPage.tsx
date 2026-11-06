// DEP-04 version matrix, DEP-05 drift, DEP-06 promotion paths, DEP-02 deployment log.
import { Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, TextField, Tooltip, Typography } from '@mui/material';
import { useState } from 'react';
import { api, useAction, useCan, useEnvironments, useGet, type Row } from '../api/platform';
import { DataTable, ErrorAlert, FormDialog, Section, StatusChip } from './common';
import { EnvSelect } from './EnvironmentDetailPage';
import { DEPLOYMENT_COLUMNS } from './EnvTabs';

function Matrix() {
  const [diff, setDiff] = useState(false);
  const [type, setType] = useState('');
  const m = useGet('/version-matrix', { differences_only: diff, env_type: type || undefined });
  const envs = (m.data?.environments ?? []) as Row[];
  return (
    <>
      <Stack direction="row" spacing={2} sx={{ mb: 1 }}>
        <FormControlLabel control={<Checkbox checked={diff} onChange={(e) => setDiff(e.target.checked)} />} label="Only systems that differ" />
        <TextField select size="small" label="Type" value={type} onChange={(e) => setType(e.target.value)} sx={{ minWidth: 120 }}>
          <MenuItem value="">All</MenuItem>
          {['DEV', 'SIT', 'UAT', 'PreProd', 'Perf', 'Training', 'Sandbox'].map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
        </TextField>
      </Stack>
      <Box sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label="Version matrix">
          <TableHead>
            <TableRow>
              <TableCell>System</TableCell>
              {envs.map((e) => <TableCell key={e.id}>{e.name}</TableCell>)}
            </TableRow>
          </TableHead>
          <TableBody>
            {((m.data?.rows ?? []) as Row[]).map((r) => {
              const versions = envs.map((e) => r.cells[String(e.id)]?.version).filter(Boolean);
              const newest = versions.sort((a: string, b: string) => b.localeCompare(a, undefined, { numeric: true }))[0];
              return (
                <TableRow key={r.system_id}>
                  <TableCell sx={{ fontWeight: 600 }}>{r.system_name}</TableCell>
                  {envs.map((e) => {
                    const c = r.cells[String(e.id)];
                    return (
                      <TableCell key={e.id} sx={{ fontFamily: 'monospace', bgcolor: c?.version && c.version === newest && r.distinct_versions > 1 ? '#dcfce7' : undefined, color: c ? undefined : 'text.disabled' }}>
                        {c ? <Tooltip title={[c.build, c.release, c.mode !== 'real' ? c.mode : null].filter(Boolean).join(' · ')}><span>{c.version ?? '—'}{c.mode !== 'real' ? '*' : ''}</span></Tooltip> : 'n/a'}
                      </TableCell>
                    );
                  })}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Box>
      <Typography variant="caption" color="text.secondary">Shaded: the newest version where versions differ · * virtualised / stubbed · n/a: not in that environment</Typography>
    </>
  );
}

function Drift() {
  const [env, setEnv] = useState<number | ''>('');
  const [base, setBase] = useState<number | ''>('');
  const d = useGet(env ? '/drift' : null, { environment_id: env || undefined, baseline_id: base || undefined });
  return (
    <>
      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <EnvSelect value={env} onChange={setEnv} />
        <EnvSelect value={base} onChange={setBase} label="Baseline (default: next on promotion path)" exclude={env || undefined} />
      </Stack>
      <ErrorAlert error={d.error} />
      {d.data && (
        <Stack spacing={2}>
          <Alert severity={d.data.drifted ? 'warning' : 'success'}>
            {d.data.environment.name} vs {d.data.baseline.name}: {d.data.versions.length} version differences, {d.data.structural_config_drift} structural configuration differences.
          </Alert>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
            <Section title="Versions">
              <Table size="small">
                <TableHead><TableRow><TableCell>System</TableCell><TableCell>{d.data.environment.name}</TableCell><TableCell>{d.data.baseline.name}</TableCell></TableRow></TableHead>
                <TableBody>
                  {d.data.versions.map((v: Row) => (
                    <TableRow key={v.system_id}><TableCell>{v.system_name}</TableCell><TableCell>{v.version ?? '—'}</TableCell><TableCell>{v.baseline_version ?? '—'}</TableCell></TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
            <Section title="Configuration">
              <Table size="small">
                <TableHead><TableRow><TableCell>Key</TableCell><TableCell>Difference</TableCell><TableCell>Values</TableCell></TableRow></TableHead>
                <TableBody>
                  {d.data.config.map((c: Row) => (
                    <TableRow key={c.key}><TableCell sx={{ fontFamily: 'monospace' }}>{c.key}</TableCell><TableCell><StatusChip value={['value', 'secret_value'].includes(c.kind) ? 'amber' : 'red'} label={c.kind.replace('_', ' ')} /></TableCell><TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{c.value !== undefined ? `${c.value} ≠ ${c.baseline_value}` : ''}</TableCell></TableRow>
                  ))}
                </TableBody>
              </Table>
            </Section>
          </Box>
        </Stack>
      )}
    </>
  );
}

function Paths() {
  const paths = useGet<Row[]>('/promotion-paths');
  const envs = useEnvironments();
  const canManage = useCan('env_manager');
  const [editing, setEditing] = useState<Row | null>(null);
  const setGate = useAction((args: { p: Row; idx: number; gate: string }) =>
    api.put(`/promotion-paths/${args.p.id}`, { name: args.p.name, description: args.p.description, stages: args.p.stages.map((s: Row, i: number) => ({ environment_id: s.environment_id, gate_status: i === args.idx ? args.gate : s.gate_status, gate_note: s.gate_note })) }),
  );
  return (
    <Stack spacing={2}>
      {canManage && <Box><Button variant="outlined" onClick={() => setEditing({})}>New promotion path</Button></Box>}
      <ErrorAlert error={setGate.error} />
      {(paths.data ?? []).map((p) => (
        <Section key={p.id} title={p.name}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2, flexWrap: 'wrap', rowGap: 1 }}>
            {p.stages.map((s: Row, i: number) => (
              <Stack key={s.environment_id} direction="row" spacing={1} alignItems="center">
                <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1, textAlign: 'center' }}>
                  <Typography sx={{ fontWeight: 600 }}>{s.environment}</Typography>
                  {canManage ? (
                    <TextField select size="small" variant="standard" value={s.gate_status} onChange={(e) => setGate.mutate({ p, idx: i, gate: e.target.value })} inputProps={{ 'aria-label': `Gate after ${s.environment}` }}>
                      {['open', 'passed', 'failed', 'blocked'].map((g) => <MenuItem key={g} value={g}>gate: {g}</MenuItem>)}
                    </TextField>
                  ) : (
                    <StatusChip value={s.gate_status === 'passed' ? 'green' : s.gate_status === 'open' ? 'amber' : 'red'} label={`gate: ${s.gate_status}`} />
                  )}
                </Box>
                {i < p.stages.length - 1 && <Typography>→</Typography>}
              </Stack>
            ))}
          </Stack>
          <Typography variant="subtitle2">Waiting to be promoted ({p.pending_promotions.length})</Typography>
          <Table size="small">
            <TableBody>
              {p.pending_promotions.map((x: Row, i: number) => (
                <TableRow key={i}>
                  <TableCell>{x.system_name}</TableCell>
                  <TableCell>{x.version} in {x.from}</TableCell>
                  <TableCell>→ {x.to} (has {x.current ?? 'none'})</TableCell>
                  <TableCell><StatusChip value={x.gate_status === 'passed' ? 'green' : 'amber'} label={x.gate_status === 'passed' ? 'gate passed' : `gate ${x.gate_status}`} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      ))}
      <FormDialog
        open={!!editing}
        title="New promotion path"
        fields={[
          { key: 'name', label: 'Name', required: true },
          { key: 'description', label: 'Description' },
          { key: 'stages', label: 'Environments in order (names, comma-separated)', type: 'tags', required: true },
        ]}
        onClose={() => setEditing(null)}
        onSubmit={async (v) => {
          const byName = new Map((envs.data ?? []).map((e) => [e.name.toLowerCase(), e.id]));
          const stages = (v.stages as string[]).map((n) => {
            const id = byName.get(n.toLowerCase());
            if (!id) throw new Error(`Unknown environment '${n}'`);
            return { environment_id: id, gate_status: 'open' };
          });
          await api.post('/promotion-paths', { name: v.name, description: v.description, stages });
          paths.refetch();
        }}
      />
    </Stack>
  );
}

export default function ReleasesPage() {
  const [tab, setTab] = useState('matrix');
  const deps = useGet<Row[]>(tab === 'log' ? '/deployments' : null, { limit: 500 });
  return (
    <Section title="Releases and versions">
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="matrix" label="Version matrix" />
        <Tab value="drift" label="Drift" />
        <Tab value="paths" label="Promotion paths" />
        <Tab value="log" label="Deployment log" />
      </Tabs>
      {tab === 'matrix' && <Matrix />}
      {tab === 'drift' && <Drift />}
      {tab === 'paths' && <Paths />}
      {tab === 'log' && <DataTable rows={deps.data ?? []} columns={DEPLOYMENT_COLUMNS} label="Deployment log" page="deployments" />}
    </Section>
  );
}
