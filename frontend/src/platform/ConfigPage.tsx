// CFG-02 global defaults, CFG-04 side-by-side comparison, CFG-08 templates, CFG-09 pipeline access.
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, IconButton, MenuItem, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import { useState } from 'react';
import { api, useAction, useCan, useEnvironments, useGet, useMeta, type Row } from '../api/platform';
import { DataTable, ErrorAlert, FormDialog, Section, type Column } from './common';
import { HistoryDialog, RevealButton, VARIABLE_FIELDS } from './ConfigTab';

function Compare() {
  const envs = useEnvironments();
  const [ids, setIds] = useState<number[]>([]);
  const [onlyDiff, setOnlyDiff] = useState(true);
  const cmp = useGet(ids.length >= 2 ? '/config/compare' : null, { env_ids: ids.join(',') });
  const rows = ((cmp.data?.rows ?? []) as Row[]).filter((r) => !onlyDiff || r.differs);
  return (
    <>
      <Stack direction="row" spacing={2} sx={{ mb: 2 }} alignItems="center">
        <TextField select size="small" label="Environments (2 or more)" SelectProps={{ multiple: true }} value={ids} onChange={(e) => setIds(e.target.value as unknown as number[])} sx={{ minWidth: 300 }}>
          {(envs.data ?? []).map((e) => <MenuItem key={e.id} value={e.id}>{e.name}</MenuItem>)}
        </TextField>
        <FormControlLabel control={<Checkbox checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} />} label="Only differences" />
        {cmp.data && <Typography variant="body2">{cmp.data.summary.different} of {cmp.data.summary.keys} keys differ · {cmp.data.summary.missing} missing somewhere</Typography>}
      </Stack>
      {cmp.data && (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-label="Configuration comparison">
            <TableHead>
              <TableRow>
                <TableCell>Key</TableCell>
                {(cmp.data.environments as Row[]).map((e) => <TableCell key={e.id}>{e.name}</TableCell>)}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.key}>
                  <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{r.key}</TableCell>
                  {(cmp.data?.environments as Row[]).map((e) => {
                    const c = r.cells[String(e.id)];
                    return (
                      <TableCell key={e.id} sx={{ fontFamily: 'monospace', fontSize: 12, bgcolor: !c ? '#fee2e2' : r.differs ? '#fef3c7' : undefined }}>
                        {c ? <>{c.value}{c.scope === 'global' && <Chip size="small" label="default" sx={{ ml: 0.5 }} />}</> : <em>missing</em>}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </>
  );
}

function Globals() {
  const vars = useGet<Row[]>('/global-variables');
  const canManage = useCan('env_manager');
  const [edit, setEdit] = useState<Row | null>(null);
  const [hist, setHist] = useState<Row | null>(null);
  const del = useAction((id: number) => api.del(`/variables/${id}`));
  const cols: Column[] = [
    { key: 'key', label: 'Key', render: (v) => <Box component="span" sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{v.key}</Box> },
    { key: 'value', label: 'Default value', render: (v) => (v.is_secret ? <><span>••••</span><RevealButton v={v} /></> : <Box component="span" sx={{ fontFamily: 'monospace' }}>{v.value}</Box>) },
    { key: 'description', label: 'Description' },
    { key: 'owner', label: 'Owner' },
    { key: 'a', label: '', render: (v) => (
      <Stack direction="row">
        <Button size="small" onClick={() => setHist(v)}>History</Button>
        {canManage && <Button size="small" onClick={() => setEdit(v)}>Edit</Button>}
        {canManage && <IconButton size="small" aria-label={`Delete ${v.key}`} onClick={() => window.confirm(`Delete global ${v.key}?`) && del.mutate(v.id)}><DeleteIcon fontSize="small" /></IconButton>}
      </Stack>
    ) },
  ];
  return (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Defaults apply to every environment unless an environment (or a system instance) overrides the key.
      </Typography>
      <ErrorAlert error={del.error} />
      <DataTable rows={vars.data ?? []} columns={cols} label="Global variables" toolbar={canManage && <Button size="small" variant="contained" onClick={() => setEdit({ value_type: 'string', sensitivity: 'internal' })}>Add default</Button>} />
      <FormDialog
        open={!!edit}
        title={edit?.id ? `Edit ${edit.key}` : 'Add a global default'}
        fields={VARIABLE_FIELDS}
        initial={edit ?? {}}
        onClose={() => setEdit(null)}
        onSubmit={async (v) => {
          if (edit?.id) await api.patch(`/variables/${edit.id}`, { ...v, row_version: edit.row_version });
          else await api.post('/global-variables', v);
          vars.refetch();
        }}
      />
      <HistoryDialog variable={hist} onClose={() => setHist(null)} />
    </>
  );
}

function Templates() {
  const t = useGet<Row[]>('/config-templates');
  const meta = useMeta();
  const canManage = useCan('env_manager');
  const [open, setOpen] = useState(false);
  const del = useAction((id: number) => api.del(`/config-templates/${id}`));
  return (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Keys every environment of a type must define. The Configuration tab of each environment shows what is missing.</Typography>
      <Table size="small" aria-label="Configuration templates">
        <TableHead><TableRow><TableCell>Type</TableCell><TableCell>Key</TableCell><TableCell>Required</TableCell><TableCell>Secret</TableCell><TableCell>Default</TableCell><TableCell>Description</TableCell><TableCell /></TableRow></TableHead>
        <TableBody>
          {(t.data ?? []).map((k) => (
            <TableRow key={k.id}>
              <TableCell>{k.env_type === '*' ? 'every type' : k.env_type}</TableCell>
              <TableCell sx={{ fontFamily: 'monospace' }}>{k.key}</TableCell>
              <TableCell>{k.required ? 'yes' : 'no'}</TableCell>
              <TableCell>{k.is_secret ? 'yes' : ''}</TableCell>
              <TableCell>{k.default_value}</TableCell>
              <TableCell>{k.description}</TableCell>
              <TableCell>{canManage && <IconButton size="small" aria-label={`Remove ${k.key}`} onClick={() => del.mutate(k.id)}><DeleteIcon fontSize="small" /></IconButton>}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {canManage && <Button sx={{ mt: 1 }} onClick={() => setOpen(true)}>Add template key</Button>}
      <FormDialog
        open={open}
        title="Add template key"
        fields={[
          { key: 'env_type', label: 'Environment type', type: 'select', options: ['*', ...(meta.data?.env_types ?? [])], required: true },
          { key: 'key', label: 'Key', required: true },
          { key: 'required', label: 'Required', type: 'checkbox' },
          { key: 'is_secret', label: 'Secret', type: 'checkbox' },
          { key: 'default_value', label: 'Default value' },
          { key: 'description', label: 'Description' },
        ]}
        initial={{ env_type: '*', required: true }}
        onClose={() => setOpen(false)}
        onSubmit={async (v) => { await api.post('/config-templates', v); t.refetch(); }}
      />
    </>
  );
}

export default function ConfigPage() {
  const [tab, setTab] = useState('compare');
  return (
    <Section title="Configuration">
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="compare" label="Compare environments" />
        <Tab value="global" label="Global defaults" />
        <Tab value="templates" label="Templates" />
        <Tab value="pipelines" label="Pipeline access" />
      </Tabs>
      {tab === 'compare' && <Compare />}
      {tab === 'global' && <Globals />}
      {tab === 'templates' && <Templates />}
      {tab === 'pipelines' && (
        <Stack spacing={1}>
          <Alert severity="info">Pipelines read effective configuration from the platform instead of keeping their own copies. Create an API token in Admin → API tokens.</Alert>
          <Box component="pre" sx={{ bgcolor: 'grey.100', p: 2, borderRadius: 1, fontSize: 13, overflowX: 'auto' }}>
{`# Read configuration for SIT2 as a .env file (secrets come back as vault: references)
curl -H "Authorization: Bearer $ENVMGMT_TOKEN" \\
  "$ENVMGMT_URL/api/v1/config/SIT2?format=env" > .env

# Report a deployment from CI (GitHub Actions, Jenkins, Azure DevOps, GitLab)
curl -X POST -H "Authorization: Bearer $ENVMGMT_TOKEN" -H "Content-Type: application/json" \\
  "$ENVMGMT_URL/api/v1/ci/deployments" \\
  -d '{"environment":"SIT2","system":"BILLING","version":"2.6.0","commit_sha":"'$GIT_SHA'","tool":"github_actions"}'`}
          </Box>
        </Stack>
      )}
    </Section>
  );
}
