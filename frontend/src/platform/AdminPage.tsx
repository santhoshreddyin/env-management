// GOV-01..08 administration: roles, API tokens, webhooks, settings, audit, bulk rollback, approvals.
import { Alert, Box, Button, Chip, IconButton, MenuItem, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, fmtDateTime, useAction, useCan, useGet, type Row } from '../api/platform';
import { DataTable, ErrorAlert, FormDialog, Section, StatusChip } from './common';

function Roles() {
  const r = useGet('/admin/roles');
  const [open, setOpen] = useState(false);
  const del = useAction((id: number) => api.del(`/admin/roles/${id}`));
  return (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Roles from SSO groups are set in the server configuration (ADMIN_GROUPS, ENV_MANAGER_GROUPS, …). Grants here add roles for a user or a group (<code>group:name</code>), optionally limited to an environment, programme, region or family.
      </Typography>
      <DataTable
        rows={r.data?.assignments ?? []}
        label="Role assignments"
        toolbar={<Button size="small" variant="contained" onClick={() => setOpen(true)}>Grant role</Button>}
        columns={[
          { key: 'principal', label: 'User or group' },
          { key: 'role', label: 'Role' },
          { key: 'scope', label: 'Scope', value: (a) => (a.scope_type === 'global' ? 'everything' : `${a.scope_type}: ${a.scope_value}`) },
          { key: 'created_by', label: 'Granted by' },
          { key: 'x', label: '', render: (a) => <IconButton size="small" aria-label={`Revoke ${a.principal}`} onClick={() => del.mutate(a.id)}><DeleteIcon fontSize="small" /></IconButton> },
        ]}
      />
      <FormDialog
        open={open}
        title="Grant a role"
        fields={[
          { key: 'principal', label: 'User, or group:<name>', required: true },
          { key: 'role', label: 'Role', type: 'select', options: r.data?.roles ?? [], required: true },
          { key: 'scope_type', label: 'Scope', type: 'select', options: r.data?.scope_types ?? [], required: true },
          { key: 'scope_value', label: 'Scope value (environment name, programme, region or family)' },
        ]}
        initial={{ role: 'booker', scope_type: 'global' }}
        onClose={() => setOpen(false)}
        onSubmit={async (v) => { await api.post('/admin/roles', v); r.refetch(); }}
      />
    </>
  );
}

function Tokens() {
  const t = useGet<Row[]>('/admin/tokens');
  const [created, setCreated] = useState<Row | null>(null);
  const [open, setOpen] = useState(false);
  const revoke = useAction((id: number) => api.del(`/admin/tokens/${id}`));
  return (
    <>
      {created && <Alert severity="warning" onClose={() => setCreated(null)}>Copy this token now; it will not be shown again: <code>{created.token}</code></Alert>}
      <DataTable
        rows={t.data ?? []}
        label="API tokens"
        toolbar={<Button size="small" variant="contained" onClick={() => setOpen(true)}>New token</Button>}
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'prefix', label: 'Token', value: (x) => `${x.prefix}…` },
          { key: 'role', label: 'Role' },
          { key: 'created_by', label: 'Created by' },
          { key: 'last_used_at', label: 'Last used', render: (x) => fmtDateTime(x.last_used_at) },
          { key: 'revoked', label: 'Status', render: (x) => <StatusChip value={x.revoked ? 'red' : 'green'} label={x.revoked ? 'revoked' : 'active'} /> },
          { key: 'a', label: '', render: (x) => !x.revoked && <Button size="small" color="error" onClick={() => window.confirm(`Revoke ${x.name}?`) && revoke.mutate(x.id)}>Revoke</Button> },
        ]}
      />
      <FormDialog
        open={open}
        title="New API token"
        fields={[
          { key: 'name', label: 'Name (e.g. jenkins-payments)', required: true },
          { key: 'role', label: 'Role', type: 'select', options: ['viewer', 'booker', 'contributor', 'env_manager'], required: true },
        ]}
        initial={{ role: 'contributor' }}
        onClose={() => setOpen(false)}
        onSubmit={async (v) => { setCreated(await api.post('/admin/tokens', v)); t.refetch(); }}
      />
    </>
  );
}

function Webhooks() {
  const w = useGet('/admin/webhooks');
  const [edit, setEdit] = useState<Row | null>(null);
  const test = useAction((id: number) => api.post(`/admin/webhooks/${id}/test`));
  const del = useAction((id: number) => api.del(`/admin/webhooks/${id}`));
  return (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Send events to Slack or Teams (incoming webhook URL) or any HTTP endpoint (signed with X-Signature-SHA256 when a secret is set). Events: {(w.data?.events ?? []).join(', ')}. Patterns like <code>booking.*</code> work.
      </Typography>
      {test.data && <Alert severity="info">Test delivery: {test.data.result}</Alert>}
      <DataTable
        rows={w.data?.webhooks ?? []}
        label="Webhooks"
        toolbar={<Button size="small" variant="contained" onClick={() => setEdit({ kind: 'slack', events: ['*'], active: true })}>Add webhook</Button>}
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'kind', label: 'Kind' },
          { key: 'url', label: 'URL' },
          { key: 'events', label: 'Events' },
          { key: 'active', label: 'Active', value: (h) => (h.active ? 'yes' : 'no') },
          { key: 'a', label: '', render: (h) => <Stack direction="row"><Button size="small" onClick={() => test.mutate(h.id)}>Test</Button><Button size="small" onClick={() => setEdit(h)}>Edit</Button><IconButton size="small" aria-label={`Delete ${h.name}`} onClick={() => del.mutate(h.id)}><DeleteIcon fontSize="small" /></IconButton></Stack> },
        ]}
      />
      <FormDialog
        open={!!edit}
        title={edit?.id ? `Edit ${edit.name}` : 'Add webhook'}
        fields={[
          { key: 'name', label: 'Name', required: true },
          { key: 'kind', label: 'Kind', type: 'select', options: ['slack', 'teams', 'generic'], required: true },
          { key: 'url', label: 'URL', required: true },
          { key: 'events', label: 'Events (comma-separated patterns)', type: 'tags' },
          { key: 'secret', label: 'Signing secret (generic)', type: 'password' },
          { key: 'active', label: 'Active', type: 'checkbox' },
        ]}
        initial={edit ?? {}}
        onClose={() => setEdit(null)}
        onSubmit={async (v) => {
          if (edit?.id) await api.put(`/admin/webhooks/${edit.id}`, v);
          else await api.post('/admin/webhooks', v);
          w.refetch();
        }}
      />
    </>
  );
}

function Settings() {
  const s = useGet('/admin/settings');
  const [key, setKey] = useState('policies');
  const [text, setText] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const save = useAction((value: unknown) => api.put(`/admin/settings/${key}`, value));
  const current = s.data?.[key];
  const shown = text || JSON.stringify(current ?? null, null, 2);
  return (
    <Stack spacing={1}>
      <Typography variant="body2" color="text.secondary">Lists of values, mandatory fields per environment type, custom attributes, policies (booking limits, approval types, protected types, SLAs), decommissioning checklist and notification templates.</Typography>
      <TextField select size="small" label="Setting" value={key} onChange={(e) => { setKey(e.target.value); setText(''); setMsg(null); }} sx={{ maxWidth: 300 }}>
        {Object.keys(s.data ?? {}).map((k) => <MenuItem key={k} value={k}>{k.replace(/_/g, ' ')}</MenuItem>)}
      </TextField>
      <TextField multiline minRows={12} value={shown} onChange={(e) => setText(e.target.value)} inputProps={{ style: { fontFamily: 'monospace', fontSize: 13 }, 'aria-label': 'Setting value (JSON)' }} />
      <Box>
        <Button
          variant="contained"
          onClick={async () => {
            try {
              await save.mutateAsync(JSON.parse(shown));
              setMsg('Saved');
              setText('');
            } catch (e) {
              setMsg((e as Error).message);
            }
          }}
        >
          Save
        </Button>
        {msg && <Typography component="span" variant="body2" sx={{ ml: 2 }}>{msg}</Typography>}
      </Box>
    </Stack>
  );
}

function Audit() {
  const [q, setQ] = useState('');
  const [action, setAction] = useState('');
  const params = { q: q || undefined, action: action || undefined, limit: 1000 };
  const a = useGet<Row[]>('/audit/search', params);
  const verify = useAction(() => api.get('/audit/verify'));
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <TextField size="small" label="Search details / user / action" value={q} onChange={(e) => setQ(e.target.value)} />
        <TextField size="small" label="Action" value={action} onChange={(e) => setAction(e.target.value)} />
        <Button href={api.url('/audit/search', { ...params, format: 'csv' })}>Export CSV</Button>
        <Button href={api.url('/audit/search', { ...params, format: 'xlsx' })}>Export Excel</Button>
        <Button onClick={() => verify.mutate()}>Verify integrity</Button>
        {verify.data && <StatusChip value={verify.data.valid ? 'green' : 'red'} label={verify.data.valid ? `chain intact (${verify.data.checked} entries)` : `tampered at entry ${verify.data.broken_at_id}`} />}
      </Stack>
      <DataTable
        rows={a.data ?? []}
        label="Audit log"
        columns={[
          { key: 'at', label: 'When', render: (r) => fmtDateTime(r.at) },
          { key: 'user', label: 'Who' },
          { key: 'action', label: 'Action' },
          { key: 'entity', label: 'Entity', value: (r) => [r.entity_type, r.entity_id].filter(Boolean).join(' ') },
          { key: 'details', label: 'Details', render: (r) => <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 12 }}>{r.details ? JSON.stringify(r.details).slice(0, 200) : ''}</Box> },
        ]}
      />
    </Stack>
  );
}

function BulkOps() {
  const ops = useGet<Row[]>('/bulk-operations');
  const rb = useAction((id: number) => api.post(`/bulk-operations/${id}/rollback`));
  return (
    <>
      {rb.data && <Alert severity="success">Rolled back {rb.data.undone} changes{rb.data.skipped.length ? `; skipped ${rb.data.skipped.join(', ')}` : ''}.</Alert>}
      <ErrorAlert error={rb.error} />
      <DataTable
        rows={ops.data ?? []}
        label="Bulk operations"
        columns={[
          { key: 'at', label: 'When', render: (o) => fmtDateTime(o.at) },
          { key: 'user', label: 'Who' },
          { key: 'kind', label: 'Kind' },
          { key: 'summary', label: 'Summary' },
          { key: 'changes', label: 'Changes' },
          { key: 'a', label: '', render: (o) => (o.rolled_back_at ? <Chip size="small" label={`rolled back by ${o.rolled_back_by}`} /> : <Button size="small" onClick={() => window.confirm(`Undo "${o.summary}"?`) && rb.mutate(o.id)}>Roll back</Button>) },
        ]}
      />
    </>
  );
}

function Approvals() {
  const a = useGet<Row[]>('/approvals', { status: 'pending,approved,rejected' });
  const decide = useAction((args: { id: number; decision: string }) => api.post(`/approvals/${args.id}/decision`, { decision: args.decision }));
  return (
    <>
      <ErrorAlert error={decide.error} />
      <DataTable
        rows={a.data ?? []}
        label="Approval requests"
        columns={[
          { key: 'requested_at', label: 'Requested', render: (r) => fmtDateTime(r.requested_at) },
          { key: 'requested_by', label: 'By' },
          { key: 'environment', label: 'Environment' },
          { key: 'summary', label: 'Change' },
          { key: 'status', label: 'Status', render: (r) => <StatusChip value={r.status === 'approved' ? 'green' : r.status === 'rejected' ? 'red' : 'amber'} label={r.status} /> },
          { key: 'a', label: '', render: (r) => r.status === 'pending' && r.can_decide && <Stack direction="row"><Button size="small" onClick={() => decide.mutate({ id: r.id, decision: 'approve' })}>Approve</Button><Button size="small" color="error" onClick={() => decide.mutate({ id: r.id, decision: 'reject' })}>Reject</Button></Stack> },
        ]}
      />
    </>
  );
}

export function NotificationsPanel() {
  const n = useGet<Row[]>('/notifications');
  const subs = useGet('/subscriptions');
  const read = useAction(() => api.post('/notifications/read'));
  const del = useAction((id: number) => api.del(`/subscriptions/${id}`));
  const [open, setOpen] = useState(false);
  return (
    <Stack spacing={2}>
      <Section title="Notifications" actions={<Button size="small" onClick={() => read.mutate()}>Mark all read</Button>}>
        <DataTable rows={n.data ?? []} label="Notifications" columns={[
          { key: 'at', label: 'When', render: (x) => fmtDateTime(x.at) },
          { key: 'title', label: 'Message', render: (x) => <span style={{ fontWeight: x.read ? 400 : 700 }}>{x.title}</span> },
          { key: 'body', label: 'Detail' },
          { key: 'event', label: 'Event' },
        ]} />
      </Section>
      <Section title="My subscriptions" actions={<Button size="small" variant="contained" onClick={() => setOpen(true)}>Subscribe</Button>}>
        <DataTable rows={subs.data?.subscriptions ?? []} label="Subscriptions" columns={[
          { key: 'environment', label: 'Environment' },
          { key: 'events', label: 'Events' },
          { key: 'channel', label: 'Channel', value: (s) => (s.channel === 'email' ? `e-mail ${s.email}` : 'in app') },
          { key: 'x', label: '', render: (s) => <IconButton size="small" aria-label="Unsubscribe" onClick={() => del.mutate(s.id)}><DeleteIcon fontSize="small" /></IconButton> },
        ]} />
      </Section>
      <FormDialog
        open={open}
        title="Subscribe to events"
        fields={[
          { key: 'events', label: 'Events (patterns, comma-separated)', type: 'tags', help: (subs.data?.events ?? []).join(', ') },
          { key: 'channel', label: 'Channel', type: 'select', options: ['inapp', 'email'], required: true },
          { key: 'email', label: 'E-mail address' },
        ]}
        initial={{ events: ['health.changed', 'booking.*'], channel: 'inapp' }}
        onClose={() => setOpen(false)}
        onSubmit={async (v) => { await api.post('/subscriptions', v); subs.refetch(); }}
      />
    </Stack>
  );
}

export default function AdminPage() {
  const isAdmin = useCan('admin');
  const isManager = useCan('env_manager');
  const tabs = [
    ...(isAdmin ? ['roles', 'tokens', 'webhooks', 'settings'] : []),
    ...(isManager ? ['audit', 'bulk', 'approvals'] : []),
    'notifications',
  ];
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? tabs[0];
  const setTab = (t: string) => setParams({ tab: t });
  const current = tabs.includes(tab) ? tab : tabs[0];
  const label: Record<string, string> = { roles: 'Roles', tokens: 'API tokens', webhooks: 'Webhooks & chat', settings: 'Settings & policies', audit: 'Audit log', bulk: 'Bulk operations', approvals: 'Approvals', notifications: 'My notifications' };
  return (
    <Section title="Administration">
      <Tabs value={current} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ mb: 2 }}>
        {tabs.map((t) => <Tab key={t} value={t} label={label[t]} />)}
      </Tabs>
      {current === 'roles' && <Roles />}
      {current === 'tokens' && <Tokens />}
      {current === 'webhooks' && <Webhooks />}
      {current === 'settings' && <Settings />}
      {current === 'audit' && <Audit />}
      {current === 'bulk' && <BulkOps />}
      {current === 'approvals' && <Approvals />}
      {current === 'notifications' && <NotificationsPanel />}
    </Section>
  );
}
