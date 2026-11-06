// CHG-04 change calendar (planned changes, releases, outages, refreshes, bookings, deployments) and DEP-07 freezes.
import { Box, Button, Chip, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useMemo, useState } from 'react';
import { api, fmtDateTime, useCan, useEnvironments, useGet, type Row } from '../api/platform';
import { FormDialog, Section, StatusChip } from './common';

const KINDS = ['freeze', 'blackout', 'planned_change', 'release', 'outage', 'refresh', 'maintenance'];

export default function CalendarPage() {
  const [weeks, setWeeks] = useState(6);
  const [env, setEnv] = useState<number | ''>('');
  const [types, setTypes] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const envs = useEnvironments();
  const canManage = useCan('env_manager');
  const start = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);
  const end = new Date(start.getTime() + weeks * 7 * 86_400_000);
  const items = useGet<Row[]>('/calendar', { start: start.toISOString(), end: end.toISOString(), environment_id: env || undefined });
  const shown = (items.data ?? []).filter((i) => types.length === 0 || types.includes(i.type));
  const byDay = new Map<string, Row[]>();
  shown.forEach((i) => {
    const k = new Date(i.start_at).toDateString();
    byDay.set(k, [...(byDay.get(k) ?? []), i]);
  });
  return (
    <Section
      title="Change calendar"
      actions={
        <>
          {canManage && <Button variant="contained" onClick={() => setOpen(true)}>Add freeze / change</Button>}
          <Button href={api.url('/calendar.ics', { environment_id: env || undefined })}>Subscribe (iCal)</Button>
        </>
      }
    >
      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', rowGap: 1 }}>
        <TextField select size="small" label="Environment" value={env} onChange={(e) => setEnv(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem>
          {(envs.data ?? []).map((e) => <MenuItem key={e.id} value={e.id}>{e.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Show" SelectProps={{ multiple: true }} value={types} onChange={(e) => setTypes(e.target.value as unknown as string[])} sx={{ minWidth: 200 }}>
          {['event', 'booking', 'deployment', 'incident'].map((t) => <MenuItem key={t} value={t}>{t}s</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Weeks" value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} sx={{ minWidth: 100 }}>
          {[2, 4, 6, 12].map((w) => <MenuItem key={w} value={w}>{w}</MenuItem>)}
        </TextField>
      </Stack>
      {[...byDay.entries()].map(([day, list]) => (
        <Box key={day} sx={{ display: 'grid', gridTemplateColumns: '130px 1fr', borderTop: 1, borderColor: 'divider', py: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, color: new Date(day).toDateString() === new Date().toDateString() ? 'primary.main' : undefined }}>
            {new Date(day).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}
          </Typography>
          <Stack spacing={0.5}>
            {list.map((i) => (
              <Stack key={`${i.type}-${i.id}`} direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <StatusChip value={i.kind === 'freeze' || i.kind === 'outage' || i.kind === 'incident' ? 'red' : i.kind === 'booking' ? 'green' : 'amber'} label={i.kind.replace('_', ' ')} />
                <Typography variant="body2"><strong>{i.environment}</strong> {i.title}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {fmtDateTime(i.start_at)}{i.end_at !== i.start_at ? ` – ${fmtDateTime(i.end_at)}` : ''}
                </Typography>
                {i.enforce && <Chip size="small" color="error" variant="outlined" label="enforced" />}
              </Stack>
            ))}
          </Stack>
        </Box>
      ))}
      {byDay.size === 0 && <Typography variant="body2">Nothing scheduled.</Typography>}
      <FormDialog
        open={open}
        title="Add to the calendar"
        fields={[
          { key: 'kind', label: 'Kind', type: 'select', options: KINDS, required: true },
          { key: 'title', label: 'Title', required: true },
          { key: 'environment_id', label: 'Environment (empty = all)', type: 'select', options: (envs.data ?? []).map((e) => ({ value: e.id, label: e.name })) },
          { key: 'start_at', label: 'Start', type: 'datetime', required: true },
          { key: 'end_at', label: 'End', type: 'datetime', required: true },
          { key: 'enforce', label: 'Enforce (block deployments without an override)', type: 'checkbox' },
          { key: 'external_ref', label: 'Change ticket' },
          { key: 'notes', label: 'Notes', type: 'multiline' },
        ]}
        initial={{ kind: 'freeze' }}
        onClose={() => setOpen(false)}
        onSubmit={async (v) => {
          const r = await api.post('/calendar/events', v);
          items.refetch();
          if (r.affected_bookings?.length) window.alert(`${r.affected_bookings.length} booking(s) overlap; their owners have been notified.`);
        }}
      />
    </Section>
  );
}
