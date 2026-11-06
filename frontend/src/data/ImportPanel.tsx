import UploadFileIcon from '@mui/icons-material/UploadFile';
import { Alert, Box, Button, LinearProgress, Stack, Typography } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { flowsApi } from '../api/flows';
import type { ImportReport } from '../api/types';
import IssueTable from '../common/IssueTable';

/** FR-11: upload, validate (dry run), then import. */
export default function ImportPanel() {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);

  const run = useMutation({
    mutationFn: ({ f, dryRun }: { f: File; dryRun: boolean }) => flowsApi.importWorkbook(f, dryRun),
    onSuccess: (r) => {
      setReport(r);
      if (r.imported) qc.invalidateQueries();
    },
  });

  function choose(f: File | null) {
    setFile(f);
    setReport(null);
    if (f) run.mutate({ f, dryRun: true });
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Upload a workbook based on the template. It is validated first (types, unknown references, duplicates, broken hop
        sequences, orphan systems); errors are reported by sheet, row and column and must be fixed before importing.
        Every import becomes a new version that can be rolled back.
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center">
        <input
          ref={input}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          hidden
          data-testid="import-file"
          onChange={(e) => {
            choose(e.target.files?.[0] ?? null);
            e.target.value = '';
          }}
        />
        <Button variant="outlined" startIcon={<UploadFileIcon />} onClick={() => input.current?.click()}>
          Choose Excel file
        </Button>
        <Typography variant="body2">{file?.name ?? 'No file selected'}</Typography>
      </Stack>
      {run.isPending && <LinearProgress />}
      {run.isError && <Alert severity="error">{(run.error as Error).message}</Alert>}

      {report && (
        <Box>
          {report.imported ? (
            <Alert severity="success">
              Imported {report.filename} as version {report.version_id}: {report.counts.systems} systems,{' '}
              {report.counts.integrations} integrations, {report.counts.hops} hops
              {report.warning_count ? ` (${report.warning_count} warnings)` : ''}.
            </Alert>
          ) : report.valid ? (
            <Alert
              severity="info"
              action={
                <Button color="inherit" size="small" variant="outlined" disabled={run.isPending} onClick={() => file && run.mutate({ f: file, dryRun: false })}>
                  Import
                </Button>
              }
            >
              Validation passed: {report.counts.systems} systems, {report.counts.integrations} integrations,{' '}
              {report.counts.hops} hops, {report.counts.component_details} component details
              {report.warning_count ? `, ${report.warning_count} warning(s)` : ''}. Importing replaces the current dataset.
            </Alert>
          ) : (
            <Alert severity="error">
              {report.error_count} error(s) and {report.warning_count} warning(s). Fix the workbook and upload it again.
            </Alert>
          )}
          {report.issues.length > 0 && (
            <Box sx={{ mt: 1.5 }}>
              <IssueTable issues={report.issues} />
            </Box>
          )}
        </Box>
      )}
    </Stack>
  );
}
