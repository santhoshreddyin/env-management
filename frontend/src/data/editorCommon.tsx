import { Alert, Box } from '@mui/material';
import { ApiError } from '../api/http';

export const blankToNull = (v: string | null | undefined) => (v && v.trim() ? v.trim() : null);

export function SaveError({ error }: { error: unknown }) {
  if (!error) return null;
  const issues = error instanceof ApiError ? error.issues : [];
  return (
    <Alert severity="error" sx={{ mt: 2 }}>
      {(error as Error).message}
      {issues.length > 1 && (
        <Box component="ul" sx={{ m: 0, pl: 2 }}>
          {issues.slice(1).map((i, idx) => (
            <li key={idx}>{i.message}</li>
          ))}
        </Box>
      )}
    </Alert>
  );
}
