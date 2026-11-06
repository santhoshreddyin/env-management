// Shared UI building blocks: status chips, generic data table, form dialog, empty states, file upload preview.
import BookmarkIcon from '@mui/icons-material/BookmarkBorder';
import DownloadIcon from '@mui/icons-material/Download';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMemo, useState, type ReactNode } from 'react';
import { ApiError } from '../api/http';
import { api, useAction, useGet, type Row } from '../api/platform';

// --- Status chips: colour + text + symbol, never colour alone ---------------------------

const HEALTH: Record<string, { color: 'success' | 'warning' | 'error' | 'default'; sym: string }> = {
  Healthy: { color: 'success', sym: '●' },
  Degraded: { color: 'warning', sym: '▲' },
  Down: { color: 'error', sym: '■' },
  Unknown: { color: 'default', sym: '?' },
};

export function HealthChip({ status }: { status: string }) {
  const h = HEALTH[status] ?? HEALTH.Unknown;
  return <Chip size="small" color={h.color} variant={status === 'Unknown' ? 'outlined' : 'filled'} label={`${h.sym} ${status}`} />;
}

const STATUS_COLOR: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default' | 'primary' | 'secondary'> = {
  Available: 'success',
  'In use': 'primary',
  Frozen: 'info',
  'Under maintenance': 'warning',
  Requested: 'secondary',
  Provisioning: 'secondary',
  Decommissioning: 'warning',
  Retired: 'default',
  Approved: 'success',
  Active: 'primary',
  Completed: 'default',
  Cancelled: 'default',
  Rejected: 'error',
  Waitlisted: 'warning',
  open: 'error',
  in_progress: 'warning',
  resolved: 'success',
  closed: 'default',
  connected: 'success',
  broken: 'error',
  not_connected: 'default',
  virtualised: 'info',
  real: 'success',
  stubbed: 'info',
  mocked: 'info',
  not_available: 'error',
  success: 'success',
  failed: 'error',
  rolled_back: 'warning',
  red: 'error',
  amber: 'warning',
  green: 'success',
  critical: 'error',
  high: 'warning',
  medium: 'info',
  low: 'default',
};

export function StatusChip({ value, label }: { value: string | null | undefined; label?: string }) {
  if (!value) return <>—</>;
  return <Chip size="small" variant="outlined" color={STATUS_COLOR[value] ?? 'default'} label={label ?? value.replace(/_/g, ' ')} />;
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <Alert severity="error" sx={{ my: 1 }}>
      {(error as Error).message}
    </Alert>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <Box sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }} data-testid="empty-state">
      <Typography variant="subtitle1" color="text.primary" gutterBottom>
        {title}
      </Typography>
      {children && <Typography variant="body2" sx={{ mb: 2 }}>{children}</Typography>}
      {action}
    </Box>
  );
}

export function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1, gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {actions}
        </Stack>
      </Stack>
      {children}
    </Paper>
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, minWidth: 150, flex: '1 1 150px', borderLeft: 4, borderLeftColor: tone ?? 'primary.main' }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h5" component="div" sx={{ fontWeight: 700 }}>
        {value}
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.secondary">
          {hint}
        </Typography>
      )}
    </Paper>
  );
}

// --- Generic data table (RPT-02: filter, sort, column choice, saved views, export) -----

export interface Column<T extends Row = Row> {
  key: string;
  label: string;
  render?: (row: T) => ReactNode;
  value?: (row: T) => string | number | null | undefined;
  hidden?: boolean; // hidden by default (user can show it)
  width?: number | string;
}

function cellValue<T extends Row>(c: Column<T>, r: T): string | number | null | undefined {
  if (c.value) return c.value(r);
  const v = r[c.key];
  if (v === null || v === undefined) return '';
  if (Array.isArray(v)) return v.join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  return v as string | number;
}

function toCsv<T extends Row>(cols: Column<T>[], rows: T[]): string {
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.map((c) => esc(c.label)).join(','), ...rows.map((r) => cols.map((c) => esc(cellValue(c, r))).join(','))].join('\n');
}

export function downloadText(name: string, text: string, type = 'text/csv') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

interface ViewConfig {
  q?: string;
  sort?: string;
  dir?: 'asc' | 'desc';
  columns?: string[];
}

export function DataTable<T extends Row>({
  rows,
  columns,
  page,
  label,
  onRowClick,
  toolbar,
  rowKey = 'id',
  empty,
  maxHeight = 600,
  dense = true,
}: {
  rows: T[];
  columns: Column<T>[];
  page?: string; // enables saved views when set
  label: string;
  onRowClick?: (row: T) => void;
  toolbar?: ReactNode;
  rowKey?: string;
  empty?: ReactNode;
  maxHeight?: number;
  dense?: boolean;
}) {
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<string | null>(null);
  const [dir, setDir] = useState<'asc' | 'desc'>('asc');
  const [visible, setVisible] = useState<string[]>(columns.filter((c) => !c.hidden).map((c) => c.key));
  const [colMenu, setColMenu] = useState<HTMLElement | null>(null);
  const [viewMenu, setViewMenu] = useState<HTMLElement | null>(null);
  const views = useGet<Row[]>(page ? '/views' : null, page ? { page } : undefined);
  const saveView = useAction((v: { name: string; config: ViewConfig }) => api.post('/views', { page, ...v }), [['/views']]);

  const shown = columns.filter((c) => visible.includes(c.key));
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let out = needle
      ? rows.filter((r) => columns.some((c) => String(cellValue(c, r) ?? '').toLowerCase().includes(needle)))
      : rows;
    if (sort) {
      const col = columns.find((c) => c.key === sort);
      if (col) {
        out = [...out].sort((a, b) => {
          const x = cellValue(col, a);
          const y = cellValue(col, b);
          const cmp = typeof x === 'number' && typeof y === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''), undefined, { numeric: true });
          return dir === 'asc' ? cmp : -cmp;
        });
      }
    }
    return out;
  }, [rows, columns, q, sort, dir]);

  const apply = (c: ViewConfig) => {
    setQ(c.q ?? '');
    setSort(c.sort ?? null);
    setDir(c.dir ?? 'asc');
    if (c.columns) setVisible(c.columns);
  };

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1, flexWrap: 'wrap', rowGap: 1 }}>
        <TextField size="small" placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} inputProps={{ 'aria-label': `Filter ${label}` }} />
        <Typography variant="caption" color="text.secondary">
          {filtered.length} of {rows.length}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {toolbar}
        <Tooltip title="Columns">
          <IconButton size="small" aria-label="Choose columns" onClick={(e) => setColMenu(e.currentTarget)}>
            <ViewColumnIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        {page && (
          <Tooltip title="Saved views">
            <IconButton size="small" aria-label="Saved views" onClick={(e) => setViewMenu(e.currentTarget)}>
              <BookmarkIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Export CSV">
          <IconButton size="small" aria-label={`Export ${label} as CSV`} onClick={() => downloadText(`${label.toLowerCase().replace(/\s+/g, '-')}.csv`, toCsv(shown, filtered))}>
            <DownloadIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
      <Menu anchorEl={colMenu} open={!!colMenu} onClose={() => setColMenu(null)}>
        {columns.map((c) => (
          <MenuItem key={c.key} dense onClick={() => setVisible((v) => (v.includes(c.key) ? v.filter((k) => k !== c.key) : [...v, c.key]))}>
            <Checkbox size="small" checked={visible.includes(c.key)} sx={{ p: 0.5 }} />
            {c.label}
          </MenuItem>
        ))}
      </Menu>
      <Menu anchorEl={viewMenu} open={!!viewMenu} onClose={() => setViewMenu(null)}>
        {(views.data ?? []).map((v) => (
          <MenuItem key={v.id} dense onClick={() => { apply(v.config as ViewConfig); setViewMenu(null); }}>
            {v.name}
            {!v.mine && <Chip size="small" label="shared" sx={{ ml: 1 }} />}
          </MenuItem>
        ))}
        <MenuItem
          dense
          onClick={() => {
            const name = window.prompt('Name this view');
            if (name) saveView.mutate({ name, config: { q, sort: sort ?? undefined, dir, columns: visible } });
            setViewMenu(null);
          }}
        >
          <em>Save current view…</em>
        </MenuItem>
      </Menu>
      {rows.length === 0 && empty ? (
        empty
      ) : (
        <TableContainer sx={{ maxHeight, border: 1, borderColor: 'divider', borderRadius: 1 }}>
          <Table size={dense ? 'small' : 'medium'} stickyHeader aria-label={label}>
            <TableHead>
              <TableRow>
                {shown.map((c) => (
                  <TableCell key={c.key} sx={{ whiteSpace: 'nowrap', width: c.width, fontWeight: 600 }} sortDirection={sort === c.key ? dir : false}>
                    <TableSortLabel
                      active={sort === c.key}
                      direction={sort === c.key ? dir : 'asc'}
                      onClick={() => {
                        if (sort === c.key) setDir(dir === 'asc' ? 'desc' : 'asc');
                        else {
                          setSort(c.key);
                          setDir('asc');
                        }
                      }}
                    >
                      {c.label}
                    </TableSortLabel>
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map((r, i) => (
                <TableRow key={String(r[rowKey] ?? i)} hover={!!onRowClick} onClick={onRowClick ? () => onRowClick(r) : undefined} sx={{ cursor: onRowClick ? 'pointer' : undefined }}>
                  {shown.map((c) => (
                    <TableCell key={c.key}>{c.render ? c.render(r) : String(cellValue(c, r) ?? '')}</TableCell>
                  ))}
                </TableRow>
              ))}
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={shown.length} sx={{ color: 'text.secondary' }}>
                    Nothing matches.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

// --- Form dialog driven by field definitions --------------------------------------------

export interface Field {
  key: string;
  label: string;
  type?: 'text' | 'number' | 'select' | 'multiline' | 'checkbox' | 'datetime' | 'date' | 'tags' | 'password';
  options?: (string | { value: string | number; label: string })[];
  required?: boolean;
  help?: string;
  half?: boolean;
}

export function FormDialog({
  open,
  title,
  fields,
  initial,
  onClose,
  onSubmit,
  submitLabel = 'Save',
  extra,
}: {
  open: boolean;
  title: string;
  fields: Field[];
  initial?: Row;
  onClose: () => void;
  onSubmit: (values: Row) => Promise<unknown>;
  submitLabel?: string;
  extra?: ReactNode;
}) {
  const [values, setValues] = useState<Row>(initial ?? {});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setValues(initial ?? {});
      setError(null);
    }
  }
  const set = (k: string, v: unknown) => setValues((s) => ({ ...s, [k]: v }));

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const out: Row = {};
      for (const f of fields) {
        let v = values[f.key];
        if (v === '' && f.type !== 'checkbox') v = null;
        if (f.type === 'number' && v !== null && v !== undefined) v = Number(v);
        if (f.type === 'tags' && typeof v === 'string') v = v.split(',').map((s: string) => s.trim()).filter(Boolean);
        if (f.type === 'datetime' && v) v = new Date(v).toISOString();
        if (v !== undefined) out[f.key] = v;
      }
      await onSubmit(out);
      onClose();
    } catch (e) {
      const err = e as ApiError;
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} role="alert">
            {error}
          </Alert>
        )}
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2, pt: 1 }}>
          {fields.map((f) => {
            const v = values[f.key];
            const span = f.half ? undefined : f.type === 'multiline' ? '1 / -1' : undefined;
            if (f.type === 'checkbox')
              return (
                <FormControlLabel key={f.key} control={<Checkbox checked={!!v} onChange={(e) => set(f.key, e.target.checked)} />} label={f.label} />
              );
            if (f.type === 'select')
              return (
                <TextField key={f.key} select label={f.label} value={v ?? ''} required={f.required} helperText={f.help} onChange={(e) => set(f.key, e.target.value)} size="small" sx={{ gridColumn: span }}>
                  {!f.required && <MenuItem value="">—</MenuItem>}
                  {(f.options ?? []).map((o) => {
                    const opt = typeof o === 'string' ? { value: o, label: o } : o;
                    return (
                      <MenuItem key={String(opt.value)} value={opt.value}>
                        {opt.label}
                      </MenuItem>
                    );
                  })}
                </TextField>
              );
            return (
              <TextField
                key={f.key}
                label={f.label}
                size="small"
                required={f.required}
                helperText={f.help}
                multiline={f.type === 'multiline'}
                minRows={f.type === 'multiline' ? 2 : undefined}
                type={f.type === 'number' ? 'number' : f.type === 'datetime' ? 'datetime-local' : f.type === 'date' ? 'date' : f.type === 'password' ? 'password' : 'text'}
                InputLabelProps={f.type === 'datetime' || f.type === 'date' ? { shrink: true } : undefined}
                value={Array.isArray(v) ? v.join(', ') : (v ?? '')}
                onChange={(e) => set(f.key, e.target.value)}
                sx={{ gridColumn: span }}
              />
            );
          })}
        </Box>
        {extra}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={busy}>
          {submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// --- Upload with preview then apply (GOV-05, ENV-10, CFG-06, TOP-11) --------------------

export function ImportDialog({
  open,
  onClose,
  title,
  path,
  accept,
  params,
  hint,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  path: string;
  accept: string;
  params?: Record<string, string | boolean>;
  hint?: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<Row | null>(null);
  const [error, setError] = useState<string | null>(null);
  const apply = useAction(() => api.upload(path, file as File, { ...params, dry_run: false }));

  async function preview(f: File) {
    setFile(f);
    setError(null);
    try {
      setReport(await api.upload(path, f, { ...params, dry_run: true }));
    } catch (e) {
      setError((e as Error).message);
      setReport(null);
    }
  }
  const close = () => {
    setFile(null);
    setReport(null);
    setError(null);
    apply.reset();
    onClose();
  };
  const applied = apply.data;
  const plan = (report?.plan as Row[]) ?? [];
  return (
    <Dialog open={open} onClose={close} maxWidth="md" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {hint && <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{hint}</Typography>}
        <Button variant="outlined" component="label">
          Choose file
          <input hidden type="file" accept={accept} data-testid="import-input" onChange={(e) => e.target.files?.[0] && preview(e.target.files[0])} />
        </Button>
        {file && <Typography variant="caption" sx={{ ml: 1 }}>{file.name}</Typography>}
        <ErrorAlert error={error ? new Error(error) : null} />
        {report && (
          <Box sx={{ mt: 2 }}>
            <Alert severity={report.valid ? 'success' : 'error'} sx={{ mb: 1 }}>
              {report.valid ? 'Preview: ' : 'Fix these problems first. '}
              {Object.entries((report.counts as Row) ?? {})
                .map(([k, v]) => `${v} ${k}`)
                .join(', ')}
            </Alert>
            {(report.issues as Row[]).length > 0 && (
              <Table size="small" aria-label="Import problems">
                <TableHead>
                  <TableRow>
                    <TableCell>Row</TableCell>
                    <TableCell>Field</TableCell>
                    <TableCell>Problem</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(report.issues as Row[]).map((i, n) => (
                    <TableRow key={n}>
                      <TableCell>{[i.sheet, i.row].filter(Boolean).join(' ')}</TableCell>
                      <TableCell>{i.column ?? i.key}</TableCell>
                      <TableCell>{i.message}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {report.valid && plan.length > 0 && (
              <TableContainer sx={{ maxHeight: 300 }}>
                <Table size="small" aria-label="Import preview">
                  <TableHead>
                    <TableRow>
                      <TableCell>Action</TableCell>
                      <TableCell>Item</TableCell>
                      <TableCell>Change</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {plan
                      .filter((p) => p.action !== 'unchanged')
                      .map((p, n) => (
                        <TableRow key={n}>
                          <TableCell>
                            <StatusChip value={p.action} />
                          </TableCell>
                          <TableCell>{p.name ?? p.key ?? p.instance_name ?? p.integration}</TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                            {p.old !== undefined ? `${p.old ?? '∅'} → ${p.new ?? '∅'}` : p.changes ? Object.keys(p.changes).join(', ') : ''}
                          </TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Box>
        )}
        {applied && (
          <Alert severity="success" sx={{ mt: 2 }}>
            Applied. You can undo it from Admin → Bulk operations (#{applied.bulk_operation_id}).
          </Alert>
        )}
        <ErrorAlert error={apply.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{applied ? 'Close' : 'Cancel'}</Button>
        {!applied && (
          <Button variant="contained" disabled={!report?.valid || apply.isPending} onClick={() => apply.mutate()}>
            Apply
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

export function confirmAction(message: string): boolean {
  return window.confirm(message);
}
