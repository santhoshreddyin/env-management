import { Box, Button, Stack, Typography } from '@mui/material';
import { useState } from 'react';
import type { FlowConfig } from '../../api/types';
import { LineSample } from './ProtocolBadge';

export default function Legend({ config }: { config: FlowConfig }) {
  const [open, setOpen] = useState(true);
  if (!open) {
    return (
      <Button size="small" variant="outlined" sx={{ bgcolor: 'background.paper' }} onClick={() => setOpen(true)} aria-expanded={false}>
        Legend
      </Button>
    );
  }
  return (
    <Box
      component="section"
      aria-label="Legend"
      sx={{ bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: 1, p: 1, fontSize: 12 }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="caption" fontWeight={700} component="h3" sx={{ m: 0 }}>
          Protocols
        </Typography>
        <Button size="small" sx={{ minWidth: 0, py: 0, fontSize: 11 }} onClick={() => setOpen(false)} aria-expanded>
          Hide
        </Button>
      </Stack>
      <Stack spacing={0.25} sx={{ mb: 0.75 }}>
        {Object.entries(config.protocols).map(([key, p]) => (
          <Stack key={key} direction="row" spacing={1} alignItems="center">
            <LineSample color={p.color} dash={p.dash} />
            <span>{p.label}</span>
          </Stack>
        ))}
      </Stack>
      <Typography variant="caption" fontWeight={700} component="h3" sx={{ m: 0 }}>
        Direction
      </Typography>
      <Stack spacing={0.25}>
        <Stack direction="row" spacing={1} alignItems="center">
          <LineSample color="#334155" dash={null} width={config.directions.request.stroke_width} />
          <span>Request (thick, solid arrow)</span>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <LineSample color="#334155" dash={null} width={config.directions.reply.stroke_width} />
          <span>Reply (thin, open arrow, "↩")</span>
        </Stack>
      </Stack>
    </Box>
  );
}
