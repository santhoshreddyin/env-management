import { Autocomplete, FormControl, InputLabel, MenuItem, Select, Stack, TextField, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useEffect, useMemo } from 'react';
import type { FlowConfig } from '../../api/types';
import { useJourneys, usePairs } from '../queries';
import { useFlowStore, type DirectionView } from '../store';

interface Option {
  id: string;
  name: string;
  count: number;
}

/** FR-1 searchable upstream/downstream pickers, FR-2 filters, FR-6 request/reply toggle. */
export default function SelectionPanel({ config }: { config: FlowConfig }) {
  const s = useFlowStore();
  const filters = { journey: s.journey, pattern: s.pattern, protocol: s.protocol };
  const allPairs = usePairs(filters);
  const downstreamPairs = usePairs({ ...filters, upstream: s.upstream });
  const journeys = useJourneys();

  const upstreamOptions = useMemo<Option[]>(() => {
    const m = new Map<string, Option>();
    (allPairs.data ?? []).forEach((p) => {
      const o = m.get(p.upstream_id) ?? { id: p.upstream_id, name: p.upstream_name, count: 0 };
      o.count += p.integration_count;
      m.set(p.upstream_id, o);
    });
    return [...m.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [allPairs.data]);

  const downstreamOptions = useMemo<Option[]>(
    () =>
      s.upstream
        ? (downstreamPairs.data ?? []).map((p) => ({ id: p.downstream_id, name: p.downstream_name, count: p.integration_count }))
        : [],
    [downstreamPairs.data, s.upstream],
  );

  // Drop a downstream that is no longer valid for the chosen upstream / filters.
  useEffect(() => {
    if (s.downstream && downstreamPairs.isSuccess && s.upstream && !downstreamOptions.some((o) => o.id === s.downstream)) {
      s.setDownstream(null);
    }
  }, [downstreamOptions, downstreamPairs.isSuccess, s]);

  const upstreamValue = upstreamOptions.find((o) => o.id === s.upstream) ?? null;
  const downstreamValue = downstreamOptions.find((o) => o.id === s.downstream) ?? null;

  return (
    <Stack spacing={1.5}>
      <Autocomplete
        options={upstreamOptions}
        value={upstreamValue}
        getOptionLabel={(o) => o.name}
        isOptionEqualToValue={(a, b) => a.id === b.id}
        renderOption={(props, o) => (
          <li {...props} key={o.id}>
            {o.name}&nbsp;<small style={{ color: '#64748b' }}>({o.count})</small>
          </li>
        )}
        onChange={(_, v) => s.setUpstream(v?.id ?? null)}
        loading={allPairs.isLoading}
        renderInput={(params) => <TextField {...params} label="Upstream system" size="small" />}
      />
      <Autocomplete
        options={downstreamOptions}
        value={downstreamValue}
        disabled={!s.upstream}
        getOptionLabel={(o) => o.name}
        isOptionEqualToValue={(a, b) => a.id === b.id}
        renderOption={(props, o) => (
          <li {...props} key={o.id}>
            {o.name}&nbsp;<small style={{ color: '#64748b' }}>({o.count})</small>
          </li>
        )}
        onChange={(_, v) => s.setDownstream(v?.id ?? null)}
        renderInput={(params) => (
          <TextField {...params} label="Downstream system" size="small" helperText={s.upstream ? 'Only valid pairs are listed' : 'Choose an upstream first'} />
        )}
      />
      <Stack direction="row" spacing={1}>
        <FormControl size="small" fullWidth>
          <InputLabel id="journey-label">Journey</InputLabel>
          <Select labelId="journey-label" label="Journey" value={s.journey ?? ''} onChange={(e) => s.setFilter('journey', e.target.value || null)}>
            <MenuItem value="">
              <em>Any</em>
            </MenuItem>
            {(journeys.data ?? []).map((j) => (
              <MenuItem key={j} value={j}>
                {j}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" fullWidth>
          <InputLabel id="protocol-label">Protocol</InputLabel>
          <Select labelId="protocol-label" label="Protocol" value={s.protocol ?? ''} onChange={(e) => s.setFilter('protocol', e.target.value || null)}>
            <MenuItem value="">
              <em>Any</em>
            </MenuItem>
            {Object.entries(config.protocols).map(([k, p]) => (
              <MenuItem key={k} value={k}>
                {p.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <ToggleButtonGroup
          size="small"
          exclusive
          value={s.pattern ?? 'any'}
          onChange={(_, v) => v && s.setFilter('pattern', v === 'any' ? null : v)}
          aria-label="Pattern"
        >
          <ToggleButton value="any">Any</ToggleButton>
          <ToggleButton value="sync">Sync</ToggleButton>
          <ToggleButton value="async">Async</ToggleButton>
        </ToggleButtonGroup>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={s.direction}
          onChange={(_, v: DirectionView | null) => v && s.setDirection(v)}
          aria-label="Direction"
        >
          <ToggleButton value="both">Both</ToggleButton>
          <ToggleButton value="request">Request</ToggleButton>
          <ToggleButton value="reply">Reply</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
    </Stack>
  );
}
