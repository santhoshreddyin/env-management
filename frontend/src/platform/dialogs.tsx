// Booking (BKG-01/03/06/08) and issue (CHG-01/02) dialogs, shared by several pages.
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, List, ListItem, ListItemText, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { ApiError } from '../api/http';
import { api, fmtDate, toIso, useCan, useEnvironments, useGet, useMeta, type Row } from '../api/platform';
import { FormDialog, StatusChip } from './common';

function addDays(d: Date, n: number) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
const local = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T09:00`;

export function BookingDialog({ open, onClose, environmentId, onBooked }: { open: boolean; onClose: () => void; environmentId?: number; onBooked?: () => void }) {
  const envs = useEnvironments();
  const canOverride = useCan('env_manager');
  const [v, setV] = useState<Row>({});
  const [check, setCheck] = useState<Row | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Row | null>(null);
  const insts = useGet<Row[]>(v.environment_id ? `/environments/${v.environment_id}/instances` : null);

  useEffect(() => {
    if (open) {
      const start = addDays(new Date(), 1);
      setV({ environment_id: environmentId ?? '', start: local(start), end: local(addDays(start, 5)), priority: 'project', instance_ids: [], recurrence: false, every_days: 7, count: 4 });
      setCheck(null);
      setError(null);
      setResult(null);
    }
  }, [open, environmentId]);

  useEffect(() => {
    if (!open || !v.environment_id || !v.start || !v.end || new Date(v.end) <= new Date(v.start)) return;
    const t = setTimeout(() => {
      api
        .post('/bookings/check', { environment_id: v.environment_id, instance_ids: v.instance_ids, start_at: toIso(v.start), end_at: toIso(v.end), priority: v.priority })
        .then(setCheck)
        .catch(() => setCheck(null));
    }, 250);
    return () => clearTimeout(t);
  }, [open, v.environment_id, v.start, v.end, v.instance_ids, v.priority]);

  const set = (k: string, val: unknown) => setV((s) => ({ ...s, [k]: val }));
  async function submit(waitlist = false) {
    setError(null);
    try {
      const r = await api.post('/bookings', {
        environment_id: v.environment_id, instance_ids: v.instance_ids, project: v.project, team: v.team || null, purpose: v.purpose || null,
        start_at: toIso(v.start), end_at: toIso(v.end), priority: v.priority, approver: v.approver || null, waitlist,
        allow_conflict: !!v.allow_conflict, recurrence: v.recurrence ? { every_days: Number(v.every_days), count: Number(v.count) } : null,
      });
      setResult(r);
      onBooked?.();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }
  const conflicts = (check?.conflicts as Row[]) ?? [];
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Book an environment</DialogTitle>
      <DialogContent>
        {result ? (
          <Alert severity="success">
            {result.bookings.length} booking{result.bookings.length > 1 ? 's' : ''} created: {result.bookings[0].status}
            {result.bookings[0].status === 'Requested' && ' — waiting for approval'}
            {result.warnings.length > 0 && <div>{result.warnings.join(' · ')}</div>}
          </Alert>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2, pt: 1 }}>
            <TextField select size="small" label="Environment" required value={v.environment_id ?? ''} onChange={(e) => setV((s) => ({ ...s, environment_id: Number(e.target.value), instance_ids: [] }))}>
              {(envs.data ?? []).map((e) => (
                <MenuItem key={e.id} value={e.id}>{e.name} ({e.env_type}, {e.status})</MenuItem>
              ))}
            </TextField>
            <TextField select size="small" label="Components (empty = whole environment)" SelectProps={{ multiple: true }} value={v.instance_ids ?? []} onChange={(e) => set('instance_ids', e.target.value)}>
              {(insts.data ?? []).map((i) => (
                <MenuItem key={i.id} value={i.id}>{i.instance_name}{i.shared_in ? ' (shared)' : ''}</MenuItem>
              ))}
            </TextField>
            <TextField size="small" label="Project" required value={v.project ?? ''} onChange={(e) => set('project', e.target.value)} />
            <TextField size="small" label="Team" value={v.team ?? ''} onChange={(e) => set('team', e.target.value)} />
            <TextField size="small" label="Start" type="datetime-local" InputLabelProps={{ shrink: true }} value={v.start ?? ''} onChange={(e) => set('start', e.target.value)} />
            <TextField size="small" label="End" type="datetime-local" InputLabelProps={{ shrink: true }} value={v.end ?? ''} onChange={(e) => set('end', e.target.value)} />
            <TextField select size="small" label="Priority" value={v.priority} onChange={(e) => set('priority', e.target.value)}>
              <MenuItem value="production_fix">Production fix (highest)</MenuItem>
              <MenuItem value="release">Release</MenuItem>
              <MenuItem value="project">Project</MenuItem>
              <MenuItem value="training">Training</MenuItem>
            </TextField>
            <TextField size="small" label="Delegated approver (optional)" value={v.approver ?? ''} onChange={(e) => set('approver', e.target.value)} />
            <TextField size="small" label="Purpose" value={v.purpose ?? ''} onChange={(e) => set('purpose', e.target.value)} sx={{ gridColumn: '1 / -1' }} />
            <Stack direction="row" spacing={1} alignItems="center" sx={{ gridColumn: '1 / -1' }}>
              <FormControlLabel control={<Checkbox checked={!!v.recurrence} onChange={(e) => set('recurrence', e.target.checked)} />} label="Repeat" />
              {v.recurrence && (
                <>
                  <TextField size="small" type="number" label="every (days)" value={v.every_days} onChange={(e) => set('every_days', e.target.value)} sx={{ width: 120 }} />
                  <TextField size="small" type="number" label="times" value={v.count} onChange={(e) => set('count', e.target.value)} sx={{ width: 100 }} />
                </>
              )}
              {canOverride && <FormControlLabel control={<Checkbox checked={!!v.allow_conflict} onChange={(e) => set('allow_conflict', e.target.checked)} />} label="Book despite conflicts (manager)" />}
            </Stack>
          </Box>
        )}
        {!result && check && (
          <Box sx={{ mt: 2 }} data-testid="booking-check">
            {conflicts.length === 0 ? (
              <Alert severity="success">No conflicts{check.requires_approval ? '. This environment type needs approval.' : '.'}</Alert>
            ) : (
              <Alert severity="error">
                Conflicts with {conflicts.length} booking{conflicts.length > 1 ? 's' : ''}:
                <List dense disablePadding>
                  {conflicts.map((c) => (
                    <ListItem key={c.booking_id} disableGutters>
                      <ListItemText
                        primary={`${c.project} on ${c.environment} (${c.status}) ${fmtDate(c.start_at)} – ${fmtDate(c.end_at)}`}
                        secondary={c.type === 'shared_component' ? `shares ${c.shared_components.join(', ')}` : c.type === 'component' ? `same components: ${c.shared_components.join(', ')}` : 'whole environment'}
                      />
                      {c.outranked && <StatusChip value="amber" label="you outrank this" />}
                    </ListItem>
                  ))}
                </List>
              </Alert>
            )}
            {check.warnings.length > 0 && <Alert severity="warning" sx={{ mt: 1 }}>{check.warnings.join(' · ')}</Alert>}
            {check.known_issues.length > 0 && (
              <Alert severity="info" sx={{ mt: 1 }}>
                Known issues: {check.known_issues.map((k: Row) => `${k.title}${k.workaround ? ` (workaround: ${k.workaround})` : ''}`).join(' · ')}
              </Alert>
            )}
          </Box>
        )}
        {error && <Alert severity="error" sx={{ mt: 2 }} role="alert">{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{result ? 'Close' : 'Cancel'}</Button>
        {!result && conflicts.length > 0 && <Button onClick={() => submit(true)} disabled={!v.project}>Join waitlist</Button>}
        {!result && <Button variant="contained" onClick={() => submit(false)} disabled={!v.project || !v.environment_id}>Book</Button>}
      </DialogActions>
    </Dialog>
  );
}

export function IssueDialog({ open, onClose, environmentId, initial }: { open: boolean; onClose: () => void; environmentId?: number; initial?: Row }) {
  const envs = useEnvironments();
  const meta = useMeta();
  const insts = useGet<Row[]>(environmentId ? `/environments/${environmentId}/instances` : null);
  const editing = !!initial?.id;
  return (
    <FormDialog
      open={open}
      title={editing ? `Issue #${initial?.id}` : 'Log an environment issue'}
      fields={[
        ...(editing ? [] : [{ key: 'environment_id', label: 'Environment', type: 'select' as const, required: true, options: (envs.data ?? []).map((e) => ({ value: e.id, label: e.name })) }]),
        { key: 'title', label: 'Title', required: true },
        { key: 'kind', label: 'Kind', type: 'select', options: ['issue', 'incident'], required: true },
        { key: 'severity', label: 'Severity', type: 'select', options: ['critical', 'high', 'medium', 'low'], required: true },
        ...(editing ? [{ key: 'status', label: 'Status', type: 'select' as const, options: ['open', 'in_progress', 'resolved', 'closed'], required: true }] : []),
        { key: 'instance_id', label: 'Component', type: 'select', options: (insts.data ?? []).map((i) => ({ value: i.id, label: i.instance_name })) },
        { key: 'owner', label: 'Owner' },
        { key: 'category', label: 'Root-cause category', type: 'select', options: meta.data?.issue_categories ?? [] },
        { key: 'description', label: 'Description', type: 'multiline' },
        { key: 'known_issue', label: 'Show to bookers as a known issue', type: 'checkbox' },
        { key: 'workaround', label: 'Workaround' },
        { key: 'external_system', label: 'Ticket system', type: 'select', options: ['servicenow', 'jira', 'azure_devops', 'other'] },
        { key: 'external_ref', label: 'Ticket reference' },
        { key: 'external_url', label: 'Ticket URL' },
        { key: 'hours_lost', label: 'Test hours lost', type: 'number' },
        ...(editing ? [{ key: 'resolution', label: 'Resolution', type: 'multiline' as const }] : []),
      ]}
      initial={initial ?? { environment_id: environmentId, severity: 'medium', kind: 'issue' }}
      onClose={onClose}
      onSubmit={(v) => {
        if (editing) {
          const { environment_id: _e, ...rest } = v;
          void _e;
          return api.patch(`/issues/${initial?.id}`, { ...rest, row_version: initial?.row_version });
        }
        return api.post('/issues', { ...v, environment_id: v.environment_id ?? environmentId });
      }}
      extra={initial?.external_url ? <Typography variant="caption"><a href={initial.external_url} target="_blank" rel="noreferrer">Open ticket</a></Typography> : undefined}
    />
  );
}
