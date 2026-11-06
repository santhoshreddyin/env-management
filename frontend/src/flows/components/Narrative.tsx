import { Box, Typography } from '@mui/material';
import type { Integration } from '../../api/types';

/** FR-8: step-by-step narrative generated (server-side) from the hop list. */
export default function Narrative({ integration }: { integration: Integration }) {
  const [intro, ...rest] = integration.narrative;
  const summary = rest.length ? rest[rest.length - 1] : null;
  const steps = rest.slice(0, -1);
  return (
    <Box data-testid="narrative">
      <Typography variant="body2" sx={{ mb: 1 }}>
        {intro}
      </Typography>
      <Box component="ol" sx={{ pl: 2.5, m: 0, '& li': { mb: 0.5 } }}>
        {steps.map((line, i) => (
          <Typography component="li" variant="body2" key={i}>
            {line.replace(/^Step \d+: /, '')}
          </Typography>
        ))}
      </Box>
      {summary && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {summary}
        </Typography>
      )}
    </Box>
  );
}
