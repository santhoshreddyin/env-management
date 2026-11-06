import { Box } from '@mui/material';
import type { FlowConfig } from '../../api/types';
import { protocolStyle } from '../graphModel';

/** Protocol shown as colour + line pattern + text, so colour is never the only cue. */
export function LineSample({ color, dash, width = 2.5, length = 28 }: { color: string; dash: string | null; width?: number; length?: number }) {
  return (
    <svg width={length} height={10} aria-hidden="true" style={{ flexShrink: 0 }}>
      <line x1={1} y1={5} x2={length - 1} y2={5} stroke={color} strokeWidth={width} strokeDasharray={dash ?? undefined} />
    </svg>
  );
}

export default function ProtocolBadge({ config, protocol }: { config: FlowConfig; protocol: string }) {
  const p = protocolStyle(config, protocol);
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.5,
        px: 0.75,
        borderRadius: 1,
        border: `1px solid ${p.color}`,
        color: p.color,
        fontSize: 12,
        fontWeight: 700,
        lineHeight: '20px',
        whiteSpace: 'nowrap',
      }}
    >
      <LineSample color={p.color} dash={p.dash} length={18} width={2} />
      {p.label}
    </Box>
  );
}
