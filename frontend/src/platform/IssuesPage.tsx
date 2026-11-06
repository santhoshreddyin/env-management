// CHG-01..03 issue and incident register across environments.
import { Button, MenuItem, Stack, TextField } from '@mui/material';
import { useState } from 'react';
import { useGet, type Row } from '../api/platform';
import { DataTable, Section } from './common';
import { IssueDialog } from './dialogs';
import { ISSUE_COLUMNS } from './EnvTabs';

export default function IssuesPage() {
  const [status, setStatus] = useState('open,in_progress');
  const [known, setKnown] = useState('');
  const rows = useGet<Row[]>('/issues', { status: status || undefined, known: known === '' ? undefined : known === 'yes' });
  const [edit, setEdit] = useState<Row | null>(null);
  return (
    <Section title="Environment issues and incidents" actions={<Button variant="contained" onClick={() => setEdit({})}>Log issue</Button>}>
      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 150 }}>
          <MenuItem value="open,in_progress">Open</MenuItem>
          <MenuItem value="resolved,closed">Resolved</MenuItem>
          <MenuItem value="">All</MenuItem>
        </TextField>
        <TextField select size="small" label="Known issues" value={known} onChange={(e) => setKnown(e.target.value)} sx={{ minWidth: 150 }}>
          <MenuItem value="">All</MenuItem>
          <MenuItem value="yes">Known issues only</MenuItem>
        </TextField>
      </Stack>
      <DataTable rows={rows.data ?? []} columns={ISSUE_COLUMNS} label="Issues" page="issues" onRowClick={setEdit} />
      <IssueDialog open={!!edit} onClose={() => { setEdit(null); rows.refetch(); }} environmentId={edit?.environment_id} initial={edit?.id ? edit : undefined} />
    </Section>
  );
}
