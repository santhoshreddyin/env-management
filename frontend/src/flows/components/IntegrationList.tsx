import { Chip, List, ListItemButton, ListItemText, Stack, Typography } from '@mui/material';
import type { FlowConfig, Integration } from '../../api/types';
import ProtocolBadge from './ProtocolBadge';

interface Props {
  config: FlowConfig;
  integrations: Integration[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** FR-4: when several integrations match, list them and let the user switch. */
export default function IntegrationList({ config, integrations, selectedId, onSelect }: Props) {
  return (
    <List dense disablePadding aria-label="Matching integrations">
      {integrations.map((it) => (
        <ListItemButton
          key={it.id}
          selected={it.id === selectedId}
          onClick={() => onSelect(it.id)}
          sx={{ borderRadius: 1, mb: 0.5, border: 1, borderColor: it.id === selectedId ? 'primary.main' : 'divider' }}
        >
          <ListItemText
            primary={
              <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
                <Typography variant="body2" fontWeight={600}>
                  {it.name}
                </Typography>
                {it.primary_protocol && <ProtocolBadge config={config} protocol={it.primary_protocol} />}
              </Stack>
            }
            secondary={
              <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap', gap: 0.5 }} component="span">
                <Chip size="small" label={it.id} variant="outlined" component="span" />
                {it.journey && <Chip size="small" label={it.journey} component="span" />}
                <Chip size="small" label={it.pattern} component="span" />
                <Chip size="small" label={`${it.hops.length} hops`} variant="outlined" component="span" />
                {it.upstream_name && <Typography variant="caption" component="span">{`${it.upstream_name} → ${it.downstream_name}`}</Typography>}
              </Stack>
            }
            secondaryTypographyProps={{ component: 'div' }}
          />
        </ListItemButton>
      ))}
    </List>
  );
}
