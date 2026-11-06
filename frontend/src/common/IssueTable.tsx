import ErrorIcon from '@mui/icons-material/ErrorOutline';
import WarningIcon from '@mui/icons-material/WarningAmber';
import { Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';
import type { ValidationIssue } from '../api/types';

/** Validation issues by sheet, row and column; severity shown by icon + text, not colour alone. */
export default function IssueTable({ issues, maxHeight = 360 }: { issues: ValidationIssue[]; maxHeight?: number }) {
  return (
    <TableContainer sx={{ maxHeight, border: 1, borderColor: 'divider', borderRadius: 1 }}>
      <Table size="small" stickyHeader aria-label="Validation issues">
        <TableHead>
          <TableRow>
            <TableCell>Severity</TableCell>
            <TableCell>Sheet</TableCell>
            <TableCell>Row</TableCell>
            <TableCell>Column</TableCell>
            <TableCell>Message</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {issues.map((i, idx) => (
            <TableRow key={idx}>
              <TableCell>
                <Chip
                  size="small"
                  variant="outlined"
                  color={i.severity === 'error' ? 'error' : 'warning'}
                  icon={i.severity === 'error' ? <ErrorIcon /> : <WarningIcon />}
                  label={i.severity === 'error' ? 'Error' : 'Warning'}
                />
              </TableCell>
              <TableCell>{i.sheet}</TableCell>
              <TableCell>{i.row ?? '—'}</TableCell>
              <TableCell>{i.column ?? '—'}</TableCell>
              <TableCell>{i.message}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
