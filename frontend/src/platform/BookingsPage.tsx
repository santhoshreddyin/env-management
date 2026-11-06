// BKG-02 timeline by environment / project / team, BKG-04 approvals, BKG-06 bulk booking.
import { Box, Button, ButtonGroup, MenuItem, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { useMemo, useState } from 'react';
import { api, useEnvironments, useGet, type Row } from '../api/platform';
import { DataTable, Section } from './common';
import { BookingDialog } from './dialogs';
import { BOOKING_COLUMNS, BookingActions } from './EnvTabs';

const COLORS: Record<string, string> = { Active: '#1d4ed8', Approved: '#16a34a', Requested: '#a855f7', Waitlisted: '#d97706', Completed: '#94a3b8' };
const DAY = 86_400_000;

function Timeline({ bookings, events, rows, groupBy, start, days }: { bookings: Row[]; events: Row[]; rows: string[]; groupBy: string; start: Date; days: number }) {
  const end = start.getTime() + days * DAY;
  const pct = (t: number) => `${(100 * (Math.min(Math.max(t, start.getTime()), end) - start.getTime())) / (end - start.getTime())}%`;
  const width = (a: number, b: number) => `${(100 * (Math.min(b, end) - Math.max(a, start.getTime()))) / (end - start.getTime())}%`;
  const ticks = Array.from({ length: days }, (_, i) => new Date(start.getTime() + i * DAY));
  const today = Date.now();
  return (
    <Box sx={{ overflowX: 'auto' }} role="table" aria-label="Booking timeline">
      <Box sx={{ minWidth: 900 }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: '160px 1fr', position: 'sticky', top: 0, bgcolor: 'background.paper', zIndex: 1 }}>
          <Box />
          <Box sx={{ display: 'flex' }}>
            {ticks.map((t) => (
              <Box key={t.toISOString()} sx={{ flex: 1, fontSize: 10, color: t.getDay() % 6 === 0 ? 'text.disabled' : 'text.secondary', borderLeft: 1, borderColor: 'divider', pl: 0.25 }}>
                {t.getDate() === 1 || t === ticks[0] ? t.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : t.getDate()}
              </Box>
            ))}
          </Box>
        </Box>
        {rows.map((r) => {
          const mine = bookings.filter((b) => (groupBy === 'environment' ? b.environment : groupBy === 'team' ? b.team ?? '(no team)' : b.project) === r);
          const freezes = groupBy === 'environment' ? events.filter((e) => e.environment === r || e.environment_id === null) : [];
          const lanes: Row[][] = [];
          mine.forEach((b) => {
            const s = new Date(b.start_at).getTime();
            const lane = lanes.find((l) => l.every((x) => new Date(x.end_at).getTime() <= s || new Date(x.start_at).getTime() >= new Date(b.end_at).getTime()));
            if (lane) lane.push(b);
            else lanes.push([b]);
          });
          const h = Math.max(1, lanes.length) * 24 + 8;
          return (
            <Box key={r} role="row" sx={{ display: 'grid', gridTemplateColumns: '160px 1fr', borderTop: 1, borderColor: 'divider' }}>
              <Typography variant="body2" sx={{ fontWeight: 600, py: 0.5, pr: 1, overflow: 'hidden', textOverflow: 'ellipsis' }} role="rowheader">{r}</Typography>
              <Box sx={{ position: 'relative', height: h }}>
                {freezes.map((f) => (
                  <Tooltip key={`f${f.id}`} title={`${f.kind}: ${f.title}`}>
                    <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: pct(new Date(f.start_at).getTime()), width: width(new Date(f.start_at).getTime(), new Date(f.end_at).getTime()), bgcolor: f.kind === 'freeze' || f.kind === 'blackout' ? 'rgba(59,130,246,0.12)' : 'rgba(234,179,8,0.15)', backgroundImage: 'repeating-linear-gradient(45deg, transparent 0 6px, rgba(0,0,0,0.05) 6px 12px)' }} />
                  </Tooltip>
                ))}
                {today > start.getTime() && today < end && <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: pct(today), width: 2, bgcolor: 'error.main' }} />}
                {lanes.map((lane, li) =>
                  lane.map((b) => {
                    const s = new Date(b.start_at).getTime();
                    const e = new Date(b.end_at).getTime();
                    if (e < start.getTime() || s > end) return null;
                    return (
                      <Tooltip key={b.id} title={`${b.project} · ${b.environment} · ${b.status} · ${new Date(b.start_at).toLocaleString()} – ${new Date(b.end_at).toLocaleString()}${b.scope === 'partial' ? ` · ${b.instances.join(', ')}` : ''}`}>
                        <Box
                          data-testid="timeline-bar"
                          sx={{ position: 'absolute', top: 4 + li * 24, height: 20, left: pct(s), width: width(s, e), bgcolor: COLORS[b.status] ?? '#64748b', color: '#fff', borderRadius: 0.75, fontSize: 11, px: 0.5, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', border: b.scope === 'partial' ? '2px dashed rgba(255,255,255,0.8)' : undefined, opacity: b.status === 'Waitlisted' ? 0.7 : 1 }}
                        >
                          {groupBy === 'environment' ? b.project : b.environment} {b.status !== 'Active' && b.status !== 'Approved' ? `(${b.status})` : ''}
                        </Box>
                      </Tooltip>
                    );
                  }),
                )}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

export default function BookingsPage() {
  const [days, setDays] = useState(42);
  const [offset, setOffset] = useState(-7);
  const [groupBy, setGroupBy] = useState<'environment' | 'project' | 'team'>('environment');
  const [envType, setEnvType] = useState('');
  const [open, setOpen] = useState(false);
  const start = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return new Date(d.getTime() + offset * DAY);
  }, [offset]);
  const endIso = new Date(start.getTime() + days * DAY).toISOString();
  const bookings = useGet<Row[]>('/bookings', { start: start.toISOString(), end: endIso, status: 'Requested,Approved,Active,Waitlisted,Completed' });
  const events = useGet<Row[]>('/calendar/events', { start: start.toISOString(), end: endIso });
  const pending = useGet<Row[]>('/approvals/bookings');
  const envs = useEnvironments();
  const types = [...new Set((envs.data ?? []).map((e) => e.env_type))];
  const envRows = (envs.data ?? []).filter((e) => !envType || e.env_type === envType).filter((e) => e.status !== 'Retired');
  const shown = (bookings.data ?? []).filter((b) => !envType || b.env_type === envType);
  const rows = groupBy === 'environment' ? envRows.map((e) => e.name) : [...new Set(shown.map((b) => (groupBy === 'team' ? b.team ?? '(no team)' : b.project)))].sort();

  return (
    <Stack spacing={2}>
      {(pending.data ?? []).length > 0 && (
        <Section title={`Waiting for your approval (${pending.data?.length})`}>
          <DataTable rows={pending.data ?? []} columns={[...BOOKING_COLUMNS.slice(0, 6), { key: 'a', label: '', render: (b) => <BookingActions b={b} /> }]} label="Pending approvals" />
        </Section>
      )}
      <Section
        title="Booking calendar"
        actions={
          <>
            <Button variant="contained" onClick={() => setOpen(true)}>Book an environment</Button>
            <Button href={api.url("/calendar.ics")}>Subscribe (iCal)</Button>
          </>
        }
      >
        <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: 'wrap', rowGap: 1 }} alignItems="center">
          <ButtonGroup size="small">
            {(['environment', 'project', 'team'] as const).map((g) => (
              <Button key={g} variant={groupBy === g ? 'contained' : 'outlined'} onClick={() => setGroupBy(g)}>By {g}</Button>
            ))}
          </ButtonGroup>
          <TextField select size="small" label="Type" value={envType} onChange={(e) => setEnvType(e.target.value)} sx={{ minWidth: 110 }}>
            <MenuItem value="">All</MenuItem>
            {types.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </TextField>
          <ButtonGroup size="small">
            <Button onClick={() => setOffset((o) => o - 14)}>◀</Button>
            <Button onClick={() => setOffset(-7)}>Today</Button>
            <Button onClick={() => setOffset((o) => o + 14)}>▶</Button>
          </ButtonGroup>
          <TextField select size="small" label="Span" value={days} onChange={(e) => setDays(Number(e.target.value))} sx={{ minWidth: 100 }}>
            {[14, 28, 42, 90].map((d) => <MenuItem key={d} value={d}>{d} days</MenuItem>)}
          </TextField>
          <Typography variant="caption" color="text.secondary">
            Bars: <b style={{ color: COLORS.Active }}>active</b> · <b style={{ color: COLORS.Approved }}>approved</b> · <b style={{ color: COLORS.Requested }}>requested</b> · <b style={{ color: COLORS.Waitlisted }}>waitlisted</b> · dashed = part of an environment · hatched = freeze/change
          </Typography>
        </Stack>
        <Timeline bookings={shown} events={events.data ?? []} rows={rows} groupBy={groupBy} start={start} days={days} />
      </Section>
      <Section title="All bookings in this period">
        <DataTable rows={shown} columns={[...BOOKING_COLUMNS, { key: 'a', label: '', render: (b) => <BookingActions b={b} /> }]} label="Bookings" page="bookings" />
      </Section>
      <BookingDialog open={open} onClose={() => setOpen(false)} onBooked={() => bookings.refetch()} />
    </Stack>
  );
}
