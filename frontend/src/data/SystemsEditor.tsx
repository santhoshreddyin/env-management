import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import EditIcon from '@mui/icons-material/EditOutlined';
import {
  Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Grid2 as Grid, IconButton, MenuItem, Snackbar, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { flowsApi } from '../api/flows';
import { SYSTEM_TYPES, type ComponentDetail, type FlowConfig, type System, type SystemFields } from '../api/types';
import { useGraph } from '../flows/queries';
import { SaveError, blankToNull } from './editorCommon';

type Draft = SystemFields & { component_details: ComponentDetail[] };

const EMPTY: Draft = { id: '', name: '', type: 'downstream', layer: null, domain: null, owner: null, environment: null, notes: null, component_details: [] };
const EMPTY_DETAIL: ComponentDetail = { gateway_tier: null, endpoint: null, queue_references: null, notes: null };

function toDraft(s: System): Draft {
  const { display_layer: _ignored, ...rest } = s;
  return { ...rest, component_details: s.component_details.map((d) => ({ ...d })) };
}

function clean(d: Draft): Draft {
  return {
    ...d,
    id: d.id.trim(),
    name: d.name.trim(),
    layer: blankToNull(d.layer),
    domain: blankToNull(d.domain),
    owner: blankToNull(d.owner),
    environment: blankToNull(d.environment),
    notes: blankToNull(d.notes),
    component_details: d.component_details.map((c) => ({
      gateway_tier: blankToNull(c.gateway_tier),
      endpoint: blankToNull(c.endpoint),
      queue_references: blankToNull(c.queue_references),
      notes: blankToNull(c.notes),
    })),
  };
}

/** FR-14: in-app editing of systems and their component details. */
export default function SystemsEditor({ config }: { config: FlowConfig }) {
  const graph = useGraph();
  const qc = useQueryClient();
  const [filter, setFilter] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [toast, setToast] = useState('');

  const save = useMutation({
    mutationFn: (d: Draft) => flowsApi.saveSystem(clean(d), isNew),
    onSuccess: (r) => {
      setDraft(null);
      setToast(`Saved ${r.id}${r.warnings.length ? ` — ${r.warnings.map((w) => w.message).join('; ')}` : ''}`);
      qc.invalidateQueries();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => flowsApi.deleteSystem(id),
    onSuccess: () => {
      setToast('System deleted');
      qc.invalidateQueries();
    },
    onError: (e) => setToast((e as Error).message),
  });

  const rows = useMemo(() => {
    const f = filter.toLowerCase();
    return (graph.data?.nodes ?? []).filter((s) => !f || `${s.id} ${s.name} ${s.type} ${s.owner ?? ''}`.toLowerCase().includes(f));
  }, [graph.data, filter]);

  const set = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const setDetail = (i: number, patch: Partial<ComponentDetail>) =>
    setDraft((d) => (d ? { ...d, component_details: d.component_details.map((c, j) => (j === i ? { ...c, ...patch } : c)) } : d));

  return (
    <>
      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <TextField size="small" label="Search systems" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <Button
          startIcon={<AddIcon />}
          variant="outlined"
          onClick={() => {
            save.reset();
            setIsNew(true);
            setDraft({ ...EMPTY });
          }}
        >
          Add system
        </Button>
      </Stack>
      <Table size="small" aria-label="Systems">
        <TableHead>
          <TableRow>
            <TableCell>ID</TableCell>
            <TableCell>Name</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Layer</TableCell>
            <TableCell>Domain</TableCell>
            <TableCell>Owner</TableCell>
            <TableCell />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((s) => (
            <TableRow key={s.id} hover>
              <TableCell sx={{ fontFamily: 'monospace' }}>{s.id}</TableCell>
              <TableCell>{s.name}</TableCell>
              <TableCell>{config.system_types[s.type]?.label ?? s.type}</TableCell>
              <TableCell>{config.layers.find((l) => l.id === s.display_layer)?.label}</TableCell>
              <TableCell>{s.domain}</TableCell>
              <TableCell>{s.owner}</TableCell>
              <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                <IconButton
                  size="small"
                  aria-label={`Edit ${s.name}`}
                  onClick={() => {
                    save.reset();
                    setIsNew(false);
                    setDraft(toDraft(s));
                  }}
                >
                  <EditIcon fontSize="small" />
                </IconButton>
                <IconButton
                  size="small"
                  aria-label={`Delete ${s.name}`}
                  onClick={() => window.confirm(`Delete system ${s.name}?`) && remove.mutate(s.id)}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={Boolean(draft)} onClose={() => setDraft(null)} maxWidth="md" fullWidth>
        <DialogTitle>{isNew ? 'Add system' : `Edit ${draft?.name}`}</DialogTitle>
        {draft && (
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid size={4}>
                <TextField label="ID" required fullWidth size="small" value={draft.id} disabled={!isNew} onChange={(e) => set({ id: e.target.value })} />
              </Grid>
              <Grid size={8}>
                <TextField label="Name" required fullWidth size="small" value={draft.name} onChange={(e) => set({ name: e.target.value })} />
              </Grid>
              <Grid size={4}>
                <TextField select label="Type" fullWidth size="small" value={draft.type} onChange={(e) => set({ type: e.target.value as Draft['type'] })}>
                  {SYSTEM_TYPES.map((t) => (
                    <MenuItem key={t} value={t}>
                      {config.system_types[t]?.label ?? t}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={4}>
                <TextField select label="Layer (optional)" fullWidth size="small" value={draft.layer ?? ''} onChange={(e) => set({ layer: e.target.value || null })}>
                  <MenuItem value="">
                    <em>Default for type</em>
                  </MenuItem>
                  {config.layers.map((l) => (
                    <MenuItem key={l.id} value={l.id}>
                      {l.label}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={4}>
                <TextField label="Environment" fullWidth size="small" value={draft.environment ?? ''} onChange={(e) => set({ environment: e.target.value })} />
              </Grid>
              <Grid size={6}>
                <TextField label="Domain" fullWidth size="small" value={draft.domain ?? ''} onChange={(e) => set({ domain: e.target.value })} />
              </Grid>
              <Grid size={6}>
                <TextField label="Owner" fullWidth size="small" value={draft.owner ?? ''} onChange={(e) => set({ owner: e.target.value })} />
              </Grid>
              <Grid size={12}>
                <TextField label="Notes" fullWidth size="small" multiline minRows={2} value={draft.notes ?? ''} onChange={(e) => set({ notes: e.target.value })} />
              </Grid>
            </Grid>
            <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }}>
              Component details
            </Typography>
            {draft.component_details.map((c, i) => (
              <Box key={i} sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: 1, mb: 1 }}>
                <TextField label="Gateway tier" size="small" value={c.gateway_tier ?? ''} onChange={(e) => setDetail(i, { gateway_tier: e.target.value })} />
                <TextField label="Endpoint" size="small" value={c.endpoint ?? ''} onChange={(e) => setDetail(i, { endpoint: e.target.value })} />
                <TextField label="Queue references" size="small" value={c.queue_references ?? ''} onChange={(e) => setDetail(i, { queue_references: e.target.value })} />
                <TextField label="Notes" size="small" value={c.notes ?? ''} onChange={(e) => setDetail(i, { notes: e.target.value })} />
                <IconButton aria-label="Remove component detail" onClick={() => set({ component_details: draft.component_details.filter((_, j) => j !== i) })}>
                  <DeleteIcon />
                </IconButton>
              </Box>
            ))}
            <Button size="small" startIcon={<AddIcon />} onClick={() => set({ component_details: [...draft.component_details, { ...EMPTY_DETAIL }] })}>
              Add component detail
            </Button>
            <SaveError error={save.error} />
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setDraft(null)}>Cancel</Button>
          <Button variant="contained" disabled={save.isPending || !draft?.id || !draft?.name} onClick={() => draft && save.mutate(draft)}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={Boolean(toast)} autoHideDuration={5000} onClose={() => setToast('')} message={toast} />
    </>
  );
}
