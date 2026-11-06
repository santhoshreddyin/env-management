import { Alert, Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import { useAudit } from '../flows/queries';

export default function AuditLog() {
  const audit = useAudit(true);
  if (audit.isError) return <Alert severity="error">{audit.error.message}</Alert>;
  return (
    <Table size="small" aria-label="Audit log">
      <TableHead>
        <TableRow>
          <TableCell>When</TableCell>
          <TableCell>Who</TableCell>
          <TableCell>Action</TableCell>
          <TableCell>Entity</TableCell>
          <TableCell>Details</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {(audit.data ?? []).map((a) => (
          <TableRow key={a.id}>
            <TableCell sx={{ whiteSpace: 'nowrap' }}>{new Date(a.at).toLocaleString()}</TableCell>
            <TableCell>{a.user}</TableCell>
            <TableCell>{a.action}</TableCell>
            <TableCell>{[a.entity_type, a.entity_id].filter(Boolean).join(' ')}</TableCell>
            <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
              {a.details
                ? Object.entries(a.details)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(', ')
                : ''}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
