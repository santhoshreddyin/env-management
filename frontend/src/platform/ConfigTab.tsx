// CFG-01..09 and SEC-01..05 for one environment.
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import EditIcon from '@mui/icons-material/Edit';
import HistoryIcon from '@mui/icons-material/History';
import VisibilityIcon from '@mui/icons-material/Visibility';
import { Alert, Box, Button, ButtonGroup, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import { useState } from 'react';
import { api, fmtDateTime, useAction, useGet, type Environment, type Row } from '../api/platform';
import { DataTable, ErrorAlert, FormDialog, ImportDialog, StatusChip, type Column, type Field } from './common';
import { EnvSelect } from './EnvironmentDetailPage';

export const VARIABLE_FIELDS: Field[] = [
  { key: 'key', label: 'Key', required: true, help: 'Letters, digits, _ . -; must not start with a digit' },
  { key: 'value', label: 'Value', help: 'For secrets, prefer a vault reference instead' },
  { key: 'is_secret', label: 'Secret', type: 'checkbox' },
  { key: 'vault_ref', label: 'Vault reference', help: 'e.g. kv://my-vault/db-password or vault:secret/data/app#key' },
  { key: 'description', label: 'Description' },
  { key: 'owner', label: 'Owner' },
  { key: 'value_type', label: 'Type', type: 'select', options: ['string', 'number', 'boolean', 'url', 'json'], required: true },
  { key: 'sensitivity', label: 'Sensitivity', type: 'select', options: ['public', 'internal', 'confidential', 'restricted'], required: true },
  { key: 'rotation_due_at', label: 'Rotation due', type: 'datetime' },
  { key: 'rotation_owner', label: 'Rotation owner' },
];

export function HistoryDialog({ variable, onClose }: { variable: Row | null; onClose: () => void }) {
  const hist = useGet<Row[]>(variable ? `/variables/${variable.id}/history` : null);
  const restore = useAction((id: number) => api.post(`/variables/history/${id}/restore`));
  return (
    <Dialog open={!!variable} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>History of {variable?.key}</DialogTitle>
      <DialogContent>
        <ErrorAlert error={restore.error} />
        {restore.isSuccess && <Alert severity="success">Restored.</Alert>}
        <Table size="small" aria-label="Variable history">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Who</TableCell>
              <TableCell>Change</TableCell>
              <TableCell>Old</TableCell>
              <TableCell>New</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {(hist.data ?? []).map((h) => (
              <TableRow key={h.id}>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDateTime(h.at)}</TableCell>
                <TableCell>{h.user}</TableCell>
                <TableCell>{h.action}{h.changes ? ` (${Object.keys(h.changes).join(', ')})` : ''}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{h.is_secret ? '(secret)' : h.old_value}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{h.is_secret ? '(secret)' : h.new_value}</TableCell>
                <TableCell>{h.restorable && <Button size="small" onClick={() => restore.mutate(h.id)}>Restore old value</Button>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

export function RevealButton({ v }: { v: Row }) {
  const [shown, setShown] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (shown !== null)
    return (
      <Box component="span" sx={{ fontFamily: 'monospace' }}>
        {shown || '(empty)'} <Button size="small" onClick={() => setShown(null)}>Hide</Button>
      </Box>
    );
  return (
    <Tooltip title={err ?? 'Reveal (logged)'}>
      <IconButton
        size="small"
        aria-label={`Reveal ${v.key}`}
        onClick={async () => {
          try {
            const r = await api.post(`/variables/${v.id}/reveal`);
            setShown(r.vault_ref ? `vault: ${r.vault_ref}` : r.value);
          } catch (e) {
            setErr((e as Error).message);
          }
        }}
      >
        <VisibilityIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}

export default function ConfigTab({ env, canEdit, canManage }: { env: Environment; canEdit: boolean; canManage: boolean }) {
  const base = `/environments/${env.id}`;
  const [effective, setEffective] = useState(false);
  const vars = useGet<Row[]>(effective ? `${base}/config` : `${base}/variables`);
  const check = useGet(`${base}/config/check`);
  const [editing, setEditing] = useState<Row | null>(null);
  const [history, setHistory] = useState<Row | null>(null);
  const [importing, setImporting] = useState(false);
  const [copyTo, setCopyTo] = useState<number | ''>('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const remove = useAction((v: Row) => api.del(`${base}/variables/${v.id}`));
  const applyTemplate = useAction(() => api.post(`${base}/config/apply-template`));
  const copy = useAction((target: number) => api.post('/variables/copy', { source_environment_id: env.id, target_environment_id: target }));

  const cols: Column[] = [
    { key: 'key', label: 'Key', render: (v) => <Box component="span" sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{v.key}</Box> },
    {
      key: 'value', label: 'Value', render: (v) => v.is_secret ? (
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <span>{v.vault_ref ? <Chip size="small" label={`vault: ${v.vault_ref}`} /> : '••••••••'}</span>
          {canEdit && <RevealButton v={v} />}
          {v.rotation_overdue && <Chip size="small" color="error" label="rotation overdue" />}
        </Stack>
      ) : <Box component="span" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{v.value}</Box>,
    },
    ...(effective ? [{ key: 'source', label: 'Source', render: (v: Row) => <>{v.source}{v.overrides.length > 0 && <Typography variant="caption" color="text.secondary"> overrides {v.overrides.join(', ')}</Typography>}</> }] : []),
    { key: 'is_secret', label: 'Secret', value: (v) => (v.is_secret ? 'yes' : '') },
    { key: 'description', label: 'Description' },
    { key: 'value_type', label: 'Type', hidden: true },
    { key: 'sensitivity', label: 'Sensitivity', render: (v) => <StatusChip value={v.sensitivity} /> },
    { key: 'owner', label: 'Owner', hidden: true },
    { key: 'updated_at', label: 'Changed', value: (v) => `${fmtDateTime(v.updated_at)} ${v.updated_by ?? ''}`, hidden: true },
    {
      key: 'actions', label: '', render: (v) => (
        <Stack direction="row">
          <IconButton size="small" aria-label={`History of ${v.key}`} onClick={() => setHistory(v)}><HistoryIcon fontSize="small" /></IconButton>
          {canEdit && (!effective || v.source === 'environment') && (
            <>
              <IconButton size="small" aria-label={`Edit ${v.key}`} onClick={() => setEditing(v)}><EditIcon fontSize="small" /></IconButton>
              <IconButton size="small" aria-label={`Delete ${v.key}`} onClick={() => window.confirm(`Delete ${v.key} from ${env.name}?`) && remove.mutate(v)}><DeleteIcon fontSize="small" /></IconButton>
            </>
          )}
        </Stack>
      ),
    },
  ];

  const save = async (v: Row) => {
    const body = { ...v };
    if (editing?.id) {
      if (editing.is_secret && body.value === editing.value) delete body.value;
      const r = await api.patch(`${base}/variables/${editing.id}`, { ...body, row_version: editing.row_version });
      setWarnings(r.warnings ?? []);
    } else {
      const r = await api.post(`${base}/variables`, body);
      setWarnings(r.warnings ?? []);
    }
    vars.refetch();
    check.refetch();
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <ButtonGroup size="small">
          <Button variant={!effective ? 'contained' : 'outlined'} onClick={() => setEffective(false)}>This environment</Button>
          <Button variant={effective ? 'contained' : 'outlined'} onClick={() => setEffective(true)}>Effective (with global defaults)</Button>
        </ButtonGroup>
        <Box sx={{ flex: 1 }} />
        {canEdit && <Button size="small" variant="contained" onClick={() => setEditing({ value_type: 'string', sensitivity: 'internal' })}>Add variable</Button>}
        {canEdit && <Button size="small" onClick={() => setImporting(true)}>Import</Button>}
        {['env', 'json', 'yaml', 'csv'].map((f) => (
          <Button key={f} size="small" href={api.url(`${base}/variables/export`, { format: f, effective })}>.{f}</Button>
        ))}
        {canManage && <Button size="small" href={api.url(`${base}/variables/export`, { format: 'env', include_secrets: true })} color="warning">.env with secrets</Button>}
        {canEdit && (
          <>
            <EnvSelect value={copyTo} onChange={setCopyTo} label="Copy to…" exclude={env.id} />
            <Button size="small" disabled={!copyTo} onClick={() => copyTo && copy.mutate(copyTo)}>Copy new keys</Button>
          </>
        )}
      </Stack>
      {check.data && !check.data.complete && (
        <Alert severity="warning" action={canEdit && check.data.missing.length > 0 && <Button size="small" onClick={() => applyTemplate.mutate()}>Add missing keys</Button>}>
          Template for {env.env_type}: {check.data.missing.length > 0 && `missing ${check.data.missing.map((m: Row) => m.key).join(', ')}`}
          {check.data.empty.filter((m: Row) => m.required).length > 0 && ` · empty ${check.data.empty.filter((m: Row) => m.required).map((m: Row) => m.key).join(', ')}`}
        </Alert>
      )}
      {warnings.length > 0 && <Alert severity="warning" onClose={() => setWarnings([])}>{warnings.join(' · ')}</Alert>}
      {copy.data && <Alert severity="info">{copy.data.message ?? `Copied: ${copy.data.counts?.create ?? 0} new keys${copy.data.skipped?.length ? `; skipped ${copy.data.skipped.join(', ')}` : ''}`}</Alert>}
      <ErrorAlert error={remove.error ?? copy.error ?? applyTemplate.error} />
      <DataTable rows={vars.data ?? []} columns={cols} label="Variables" page="variables" />
      <FormDialog open={!!editing} title={editing?.id ? `Edit ${editing.key}` : `Add variable to ${env.name}`} fields={VARIABLE_FIELDS} initial={editing ?? {}} onClose={() => setEditing(null)} onSubmit={save} />
      <HistoryDialog variable={history} onClose={() => { setHistory(null); vars.refetch(); }} />
      <ImportDialog
        open={importing}
        onClose={() => { setImporting(false); vars.refetch(); }}
        title={`Import configuration into ${env.name}`}
        path={`${base}/variables/import`}
        accept=".env,.json,.yaml,.yml,.csv,.txt"
        params={{ mode: 'merge' }}
        hint=".env (KEY=value), JSON or YAML (mapping), or CSV (key,value,is_secret,description). New keys are added and changed values updated; nothing is deleted."
      />
    </Stack>
  );
}
