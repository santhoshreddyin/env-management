import AddIcon from '@mui/icons-material/Add';
import ArrowDownIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import EditIcon from '@mui/icons-material/EditOutlined';
import {
  Autocomplete, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Grid2 as Grid, IconButton, MenuItem, Snackbar,
  Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { flowsApi } from '../api/flows';
import { PATTERNS, PROTOCOLS, type FlowConfig, type HopFields, type Integration, type IntegrationFields } from '../api/types';
import { useGraph, useIntegrations, useJourneys } from '../flows/queries';
import { SaveError, blankToNull } from './editorCommon';

type Draft = IntegrationFields & { hops: HopFields[] };

const EMPTY: Draft = {
  id: '', name: '', journey: null, upstream_id: '', downstream_id: '', pattern: 'sync', primary_protocol: null,
  status: null, verified_by: null, last_verified: null, notes: null, hops: [],
};

function toDraft(i: Integration): Draft {
  const { upstream_name: _u, downstream_name: _d, narrative: _n, hops, ...rest } = i;
  return {
    ...rest,
    hops: hops.map((h) => ({
      sequence: h.sequence, from_system: h.from_system, to_system: h.to_system, protocol: h.protocol,
      direction: h.direction, queue_name: h.queue_name, queue_manager: h.queue_manager, notes: h.notes,
    })),
  };
}

function clean(d: Draft): Draft {
  return {
    ...d,
    id: d.id.trim(),
    name: d.name.trim(),
    journey: blankToNull(d.journey),
    status: blankToNull(d.status),
    verified_by: blankToNull(d.verified_by),
    last_verified: blankToNull(d.last_verified),
    notes: blankToNull(d.notes),
    hops: d.hops.map((h, i) => ({
      ...h,
      sequence: i + 1,
      queue_name: blankToNull(h.queue_name),
      queue_manager: blankToNull(h.queue_manager),
      notes: blankToNull(h.notes),
    })),
  };
}

/** FR-14: in-app editing of integrations and their ordered hops. */
export default function IntegrationsEditor({ config }: { config: FlowConfig }) {
  const graph = useGraph();
  const integrations = useIntegrations({}, true);
  const journeys = useJourneys();
  const qc = useQueryClient();
  const [filter, setFilter] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [toast, setToast] = useState('');

  const systems = useMemo(() => [...(graph.data?.nodes ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [graph.data]);
  const save = useMutation({
    mutationFn: (d: Draft) => flowsApi.saveIntegration(clean(d), isNew),
    onSuccess: (r) => {
      setDraft(null);
      setToast(`Saved ${r.id}${r.warnings.length ? ` — ${r.warnings.map((w) => w.message).join('; ')}` : ''}`);
      qc.invalidateQueries();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => flowsApi.deleteIntegration(id),
    onSuccess: () => {
      setToast('Integration deleted');
      qc.invalidateQueries();
    },
    onError: (e) => setToast((e as Error).message),
  });

  const rows = useMemo(() => {
    const f = filter.toLowerCase();
    return (integrations.data ?? []).filter(
      (i) => !f || `${i.id} ${i.name} ${i.journey ?? ''} ${i.upstream_name} ${i.downstream_name}`.toLowerCase().includes(f),
    );
  }, [integrations.data, filter]);

  const set = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const setHop = (i: number, patch: Partial<HopFields>) =>
    setDraft((d) => (d ? { ...d, hops: d.hops.map((h, j) => (j === i ? { ...h, ...patch } : h)) } : d));
  const moveHop = (i: number, delta: number) =>
    setDraft((d) => {
      if (!d) return d;
      const hops = [...d.hops];
      const [h] = hops.splice(i, 1);
      hops.splice(i + delta, 0, h);
      return { ...d, hops };
    });
  const addHop = () =>
    setDraft((d) => {
      if (!d) return d;
      const prev = d.hops[d.hops.length - 1];
      const hop: HopFields = {
        sequence: d.hops.length + 1, from_system: prev?.to_system ?? d.upstream_id, to_system: '',
        protocol: prev?.protocol ?? d.primary_protocol ?? 'REST', direction: prev?.direction ?? 'request',
        queue_name: null, queue_manager: null, notes: null,
      };
      return { ...d, hops: [...d.hops, hop] };
    });

  const systemSelect = (label: string, value: string, onChange: (v: string) => void) => (
    <TextField select label={label} size="small" fullWidth value={value} onChange={(e) => onChange(e.target.value)}>
      {systems.map((s) => (
        <MenuItem key={s.id} value={s.id}>
          {s.name}
        </MenuItem>
      ))}
    </TextField>
  );

  return (
    <>
      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <TextField size="small" label="Search integrations" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <Button
          startIcon={<AddIcon />}
          variant="outlined"
          onClick={() => {
            save.reset();
            setIsNew(true);
            setDraft({ ...EMPTY, hops: [] });
          }}
        >
          Add integration
        </Button>
      </Stack>
      <Table size="small" aria-label="Integrations">
        <TableHead>
          <TableRow>
            <TableCell>ID</TableCell>
            <TableCell>Name</TableCell>
            <TableCell>Route</TableCell>
            <TableCell>Journey</TableCell>
            <TableCell>Pattern</TableCell>
            <TableCell>Hops</TableCell>
            <TableCell>Last verified</TableCell>
            <TableCell />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((i) => (
            <TableRow key={i.id} hover>
              <TableCell sx={{ fontFamily: 'monospace' }}>{i.id}</TableCell>
              <TableCell>{i.name}</TableCell>
              <TableCell>
                {i.upstream_name} → {i.downstream_name}
              </TableCell>
              <TableCell>{i.journey}</TableCell>
              <TableCell>{i.pattern}</TableCell>
              <TableCell>{i.hops.length}</TableCell>
              <TableCell>{i.last_verified ?? 'never'}</TableCell>
              <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                <IconButton
                  size="small"
                  aria-label={`Edit ${i.name}`}
                  onClick={() => {
                    save.reset();
                    setIsNew(false);
                    setDraft(toDraft(i));
                  }}
                >
                  <EditIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" aria-label={`Delete ${i.name}`} onClick={() => window.confirm(`Delete integration ${i.name}?`) && remove.mutate(i.id)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={Boolean(draft)} onClose={() => setDraft(null)} maxWidth="lg" fullWidth>
        <DialogTitle>{isNew ? 'Add integration' : `Edit ${draft?.name}`}</DialogTitle>
        {draft && (
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid size={3}>
                <TextField label="ID" required fullWidth size="small" value={draft.id} disabled={!isNew} onChange={(e) => set({ id: e.target.value })} />
              </Grid>
              <Grid size={6}>
                <TextField label="Name" required fullWidth size="small" value={draft.name} onChange={(e) => set({ name: e.target.value })} />
              </Grid>
              <Grid size={3}>
                <Autocomplete
                  freeSolo
                  options={journeys.data ?? []}
                  value={draft.journey ?? ''}
                  onInputChange={(_, v) => set({ journey: v })}
                  renderInput={(p) => <TextField {...p} label="Journey" size="small" />}
                />
              </Grid>
              <Grid size={3}>{systemSelect('Upstream', draft.upstream_id, (v) => set({ upstream_id: v }))}</Grid>
              <Grid size={3}>{systemSelect('Downstream', draft.downstream_id, (v) => set({ downstream_id: v }))}</Grid>
              <Grid size={2}>
                <TextField select label="Pattern" size="small" fullWidth value={draft.pattern} onChange={(e) => set({ pattern: e.target.value as Draft['pattern'] })}>
                  {PATTERNS.map((p) => (
                    <MenuItem key={p} value={p}>
                      {p}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={2}>
                <TextField
                  select
                  label="Primary protocol"
                  size="small"
                  fullWidth
                  value={draft.primary_protocol ?? ''}
                  onChange={(e) => set({ primary_protocol: (e.target.value || null) as Draft['primary_protocol'] })}
                >
                  <MenuItem value="">
                    <em>None</em>
                  </MenuItem>
                  {PROTOCOLS.map((p) => (
                    <MenuItem key={p} value={p}>
                      {config.protocols[p]?.label ?? p}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={2}>
                <TextField label="Status" size="small" fullWidth value={draft.status ?? ''} onChange={(e) => set({ status: e.target.value })} />
              </Grid>
              <Grid size={4}>
                <TextField label="Verified by" size="small" fullWidth value={draft.verified_by ?? ''} onChange={(e) => set({ verified_by: e.target.value })} />
              </Grid>
              <Grid size={3}>
                <TextField
                  label="Last verified"
                  type="date"
                  size="small"
                  fullWidth
                  value={draft.last_verified ?? ''}
                  onChange={(e) => set({ last_verified: e.target.value })}
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </Grid>
              <Grid size={5}>
                <TextField label="Notes" size="small" fullWidth value={draft.notes ?? ''} onChange={(e) => set({ notes: e.target.value })} />
              </Grid>
            </Grid>

            <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }}>
              Hops (in order; sequence numbers are assigned from the order)
            </Typography>
            {draft.hops.map((h, i) => (
              <Box key={i} sx={{ display: 'grid', gridTemplateColumns: '32px 1.4fr 1.4fr 0.9fr 0.9fr 1.2fr 1fr 1fr auto', gap: 1, mb: 1, alignItems: 'center' }}>
                <Typography fontWeight={700} textAlign="center" aria-label={`Hop ${i + 1}`}>
                  {i + 1}
                </Typography>
                {systemSelect('From', h.from_system, (v) => setHop(i, { from_system: v }))}
                {systemSelect('To', h.to_system, (v) => setHop(i, { to_system: v }))}
                <TextField select label="Protocol" size="small" value={h.protocol} onChange={(e) => setHop(i, { protocol: e.target.value as HopFields['protocol'] })}>
                  {PROTOCOLS.map((p) => (
                    <MenuItem key={p} value={p}>
                      {p}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField select label="Direction" size="small" value={h.direction} onChange={(e) => setHop(i, { direction: e.target.value as HopFields['direction'] })}>
                  <MenuItem value="request">request</MenuItem>
                  <MenuItem value="reply">reply</MenuItem>
                </TextField>
                <TextField label="Queue name" size="small" value={h.queue_name ?? ''} onChange={(e) => setHop(i, { queue_name: e.target.value })} />
                <TextField label="Queue manager" size="small" value={h.queue_manager ?? ''} onChange={(e) => setHop(i, { queue_manager: e.target.value })} />
                <TextField label="Notes" size="small" value={h.notes ?? ''} onChange={(e) => setHop(i, { notes: e.target.value })} />
                <Stack direction="row">
                  <IconButton size="small" aria-label="Move hop up" disabled={i === 0} onClick={() => moveHop(i, -1)}>
                    <ArrowUpIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" aria-label="Move hop down" disabled={i === draft.hops.length - 1} onClick={() => moveHop(i, 1)}>
                    <ArrowDownIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" aria-label="Remove hop" onClick={() => set({ hops: draft.hops.filter((_, j) => j !== i) })}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              </Box>
            ))}
            <Button size="small" startIcon={<AddIcon />} onClick={addHop}>
              Add hop
            </Button>
            <SaveError error={save.error} />
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setDraft(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={save.isPending || !draft?.id || !draft?.name || !draft?.upstream_id || !draft?.downstream_id}
            onClick={() => draft && save.mutate(draft)}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={Boolean(toast)} autoHideDuration={5000} onClose={() => setToast('')} message={toast} />
    </>
  );
}
