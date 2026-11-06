import { Box, List, ListItemButton, Stack, Typography } from '@mui/material';
import type { FlowConfig, Integration } from '../../api/types';
import { useFlowStore } from '../store';
import ProtocolBadge from './ProtocolBadge';

/** FR-5: hops numbered in sequence; clicking one selects its edge on the diagram. */
export default function HopList({ config, integration }: { config: FlowConfig; integration: Integration }) {
  const direction = useFlowStore((s) => s.direction);
  const selected = useFlowStore((s) => s.selected);
  const select = useFlowStore((s) => s.select);
  const hops = integration.hops.filter((h) => direction === 'both' || h.direction === direction);

  const edgeIdFor = (seq: number) => {
    const h = integration.hops.find((x) => x.sequence === seq)!;
    const group = hops.filter(
      (x) => x.from_system === h.from_system && x.to_system === h.to_system && x.protocol === h.protocol && x.direction === h.direction,
    );
    return `hop-${group.map((x) => x.sequence).join('-')}`;
  };

  return (
    <List dense disablePadding aria-label="Hops in sequence" component="ol" sx={{ listStyle: 'none' }}>
      {hops.map((h) => {
        const id = edgeIdFor(h.sequence);
        const isSel = selected?.kind === 'edge' && selected.id === id;
        return (
          <li key={h.sequence}>
            <ListItemButton selected={isSel} onClick={() => select({ kind: 'edge', id })} sx={{ borderRadius: 1, alignItems: 'flex-start', gap: 1 }}>
              <Box
                aria-label={`Step ${h.sequence}`}
                sx={{
                  minWidth: 24,
                  height: 24,
                  borderRadius: '50%',
                  bgcolor: h.direction === 'reply' ? 'background.paper' : 'grey.800',
                  color: h.direction === 'reply' ? 'grey.800' : 'common.white',
                  border: 2,
                  borderColor: 'grey.800',
                  borderStyle: h.direction === 'reply' ? 'dashed' : 'solid',
                  display: 'grid',
                  placeItems: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                  mt: 0.25,
                }}
              >
                {h.sequence}
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2">
                  {h.from_name} → {h.to_name}
                </Typography>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.25 }}>
                  <ProtocolBadge config={config} protocol={h.protocol} />
                  <Typography variant="caption" color="text.secondary">
                    {h.direction === 'reply' ? '↩ reply' : 'request'}
                  </Typography>
                </Stack>
                {h.queue_name && (
                  <Typography variant="caption" color="text.secondary" component="div" sx={{ fontFamily: 'monospace' }}>
                    {h.queue_name}
                    {h.queue_manager ? ` @ ${h.queue_manager}` : ''}
                  </Typography>
                )}
              </Box>
            </ListItemButton>
          </li>
        );
      })}
    </List>
  );
}
