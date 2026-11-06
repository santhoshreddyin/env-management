import { Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { flowsApi } from '../api/flows';
import type { Version } from '../api/types';
import { useVersions } from '../flows/queries';

/** FR-13: version history of imports and edits, with rollback. */
export default function VersionHistory({ canEdit }: { canEdit: boolean }) {
  const versions = useVersions();
  const qc = useQueryClient();
  const [target, setTarget] = useState<Version | null>(null);
  const rollback = useMutation({
    mutationFn: (id: number) => flowsApi.rollback(id),
    onSuccess: () => {
      setTarget(null);
      qc.invalidateQueries();
    },
  });

  if (versions.isError) return <Alert severity="error">{versions.error.message}</Alert>;
  return (
    <>
      <Table size="small" aria-label="Version history">
        <TableHead>
          <TableRow>
            <TableCell>Version</TableCell>
            <TableCell>When</TableCell>
            <TableCell>Who</TableCell>
            <TableCell>Source</TableCell>
            <TableCell>Summary</TableCell>
            <TableCell align="right">Systems / integrations / hops</TableCell>
            {canEdit && <TableCell />}
          </TableRow>
        </TableHead>
        <TableBody>
          {(versions.data ?? []).map((v) => (
            <TableRow key={v.id} selected={v.is_current}>
              <TableCell>
                v{v.id} {v.is_current && <Chip size="small" color="primary" label="Current" />}
              </TableCell>
              <TableCell>{new Date(v.created_at).toLocaleString()}</TableCell>
              <TableCell>{v.created_by}</TableCell>
              <TableCell>{v.source}</TableCell>
              <TableCell>{v.summary}</TableCell>
              <TableCell align="right">
                {v.system_count} / {v.integration_count} / {v.hop_count}
              </TableCell>
              {canEdit && (
                <TableCell align="right">
                  {!v.is_current && (
                    <Button size="small" onClick={() => setTarget(v)}>
                      Roll back
                    </Button>
                  )}
                </TableCell>
              )}
            </TableRow>
          ))}
          {versions.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={7}>No versions yet.</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <Dialog open={Boolean(target)} onClose={() => setTarget(null)}>
        <DialogTitle>Roll back to version {target?.id}?</DialogTitle>
        <DialogContent>
          The current dataset will be replaced by version {target?.id} ({target?.summary}). This is recorded as a new
          version, so it can itself be undone.
          {rollback.isError && <Alert severity="error" sx={{ mt: 2 }}>{(rollback.error as Error).message}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTarget(null)}>Cancel</Button>
          <Button variant="contained" disabled={rollback.isPending} onClick={() => target && rollback.mutate(target.id)}>
            Roll back
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
