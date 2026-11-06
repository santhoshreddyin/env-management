import CloseIcon from '@mui/icons-material/Close';
import { Alert, Box, Chip, Divider, IconButton, Link, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import type { FlowConfig, Graph, Hop, Integration, IntegrationSummary, System } from '../../api/types';
import { useFlowStore } from '../store';
import ProtocolBadge from './ProtocolBadge';

const STALE_DAYS = 365;

function Field({ label, children }: { label: string; children: ReactNode }) {
  if (children === null || children === undefined || children === '') return null;
  return (
    <Box sx={{ mb: 0.75 }}>
      <Typography variant="caption" color="text.secondary" component="div">
        {label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ wordBreak: 'break-word' }}>
        {children}
      </Typography>
    </Box>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="subtitle2" component="h3" sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function IntegrationLinks({ items, names }: { items: IntegrationSummary[]; names: Map<string, string> }) {
  const showIntegration = useFlowStore((s) => s.showIntegration);
  if (!items.length) return <Typography variant="body2" color="text.secondary">None</Typography>;
  return (
    <Box component="ul" sx={{ pl: 2, m: 0 }}>
      {items.map((i) => (
        <li key={i.id}>
          <Link component="button" variant="body2" onClick={() => showIntegration(i.upstream_id, i.downstream_id, i.id)} sx={{ textAlign: 'left' }}>
            {i.name}
          </Link>{' '}
          <Typography variant="caption" color="text.secondary">
            {names.get(i.upstream_id)} → {names.get(i.downstream_id)}
            {i.journey ? ` · ${i.journey}` : ''}
          </Typography>
        </li>
      ))}
    </Box>
  );
}

function SystemDetail({ system, graph, config, names }: { system: System; graph: Graph; config: FlowConfig; names: Map<string, string> }) {
  const layer = config.layers.find((l) => l.id === system.display_layer)?.label ?? system.display_layer;
  const asUpstream = graph.integrations.filter((i) => i.upstream_id === system.id);
  const asDownstream = graph.integrations.filter((i) => i.downstream_id === system.id);
  const via = graph.integrations.filter(
    (i) => i.system_ids.includes(system.id) && i.upstream_id !== system.id && i.downstream_id !== system.id,
  );
  const outgoing = graph.edges.filter((e) => e.source === system.id);
  const incoming = graph.edges.filter((e) => e.target === system.id);
  const neighbourList = (edges: typeof outgoing, key: 'source' | 'target') => {
    const m = new Map<string, Set<string>>();
    edges.forEach((e) => m.set(e[key], (m.get(e[key]) ?? new Set()).add(e.protocol)));
    return [...m.entries()].sort((a, b) => (names.get(a[0]) ?? '').localeCompare(names.get(b[0]) ?? ''));
  };

  return (
    <>
      <Typography variant="h6" component="h2">
        {system.name}
      </Typography>
      <Stack direction="row" spacing={0.5} sx={{ mb: 1 }}>
        <Chip size="small" label={config.system_types[system.type]?.label ?? system.type} />
        <Chip size="small" variant="outlined" label={layer} />
      </Stack>
      <Field label="ID">{system.id}</Field>
      <Field label="Domain">{system.domain}</Field>
      <Field label="Owner">{system.owner}</Field>
      <Field label="Environment">{system.environment}</Field>
      <Field label="Notes">{system.notes}</Field>
      {system.component_details.map((d, i) => (
        <Section key={i} title={d.gateway_tier ? `Component: ${d.gateway_tier}` : 'Component detail'}>
          <Field label="Gateway tier">{d.gateway_tier}</Field>
          <Field label="Endpoint">{d.endpoint && <code>{d.endpoint}</code>}</Field>
          <Field label="Queue references">{d.queue_references && <code>{d.queue_references}</code>}</Field>
          <Field label="Notes">{d.notes}</Field>
        </Section>
      ))}
      <Divider sx={{ my: 1.5 }} />
      <Typography variant="subtitle1" component="h3">
        Connections
      </Typography>
      <Section title={`Upstream of (${asUpstream.length})`}>
        <IntegrationLinks items={asUpstream} names={names} />
      </Section>
      <Section title={`Downstream of (${asDownstream.length})`}>
        <IntegrationLinks items={asDownstream} names={names} />
      </Section>
      <Section title={`Intermediary in (${via.length})`}>
        <IntegrationLinks items={via} names={names} />
      </Section>
      <Section title="Direct links">
        <Typography variant="body2" component="div">
          {neighbourList(incoming, 'source').map(([id, ps]) => (
            <div key={`in-${id}`}>
              ← {names.get(id)} <small>({[...ps].join(', ')})</small>
            </div>
          ))}
          {neighbourList(outgoing, 'target').map(([id, ps]) => (
            <div key={`out-${id}`}>
              → {names.get(id)} <small>({[...ps].join(', ')})</small>
            </div>
          ))}
        </Typography>
      </Section>
    </>
  );
}

function HopDetail({ hops, config }: { hops: Hop[]; config: FlowConfig }) {
  return (
    <>
      {hops.map((h) => (
        <Box key={h.sequence} sx={{ mb: 2 }}>
          <Typography variant="h6" component="h2">
            Hop {h.sequence}
          </Typography>
          <Field label="From → to">
            {h.from_name} → {h.to_name}
          </Field>
          <Field label="Protocol">
            <ProtocolBadge config={config} protocol={h.protocol} />
          </Field>
          <Field label="Direction">{h.direction === 'reply' ? '↩ Reply' : 'Request'}</Field>
          <Field label="Queue name">{h.queue_name && <code>{h.queue_name}</code>}</Field>
          <Field label="Queue manager">{h.queue_manager && <code>{h.queue_manager}</code>}</Field>
          <Field label="Notes">{h.notes}</Field>
        </Box>
      ))}
    </>
  );
}

function IntegrationDetail({ integration, config }: { integration: Integration; config: FlowConfig }) {
  const verified = integration.last_verified ? new Date(integration.last_verified) : null;
  const stale = verified ? (Date.now() - verified.getTime()) / 86_400_000 > STALE_DAYS : true;
  return (
    <>
      <Typography variant="h6" component="h2">
        {integration.name}
      </Typography>
      <Field label="ID">{integration.id}</Field>
      <Field label="Route">
        {integration.upstream_name} → {integration.downstream_name}
      </Field>
      <Field label="Journey">{integration.journey}</Field>
      <Field label="Pattern">{integration.pattern}</Field>
      <Field label="Primary protocol">
        {integration.primary_protocol && <ProtocolBadge config={config} protocol={integration.primary_protocol} />}
      </Field>
      <Field label="Status">{integration.status}</Field>
      <Field label="Last verified">
        {verified ? `${integration.last_verified}${integration.verified_by ? ` by ${integration.verified_by}` : ''}` : null}
      </Field>
      {stale && (
        <Alert severity="warning" sx={{ my: 1 }}>
          {verified ? 'Last architect sign-off is more than 12 months old.' : 'This integration has not been verified by an architect.'}
        </Alert>
      )}
      <Field label="Notes">{integration.notes}</Field>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Click a system or a hop on the diagram to see its details.
      </Typography>
    </>
  );
}

interface Props {
  graph: Graph;
  config: FlowConfig;
  integration: Integration | null;
}

/** FR-7: attributes of the clicked node or edge. */
export default function DetailPanel({ graph, config, integration }: Props) {
  const selected = useFlowStore((s) => s.selected);
  const select = useFlowStore((s) => s.select);
  const explore = useFlowStore((s) => s.explore);
  const names = new Map(graph.nodes.map((n) => [n.id, n.name]));

  let content: ReactNode = null;
  if (selected?.kind === 'node') {
    const system = graph.nodes.find((n) => n.id === selected.id);
    if (system) content = <SystemDetail system={system} graph={graph} config={config} names={names} />;
  } else if (selected?.kind === 'edge') {
    if (selected.id.startsWith('hop-') && integration) {
      const seqs = selected.id.slice(4).split('-').map(Number);
      content = <HopDetail hops={integration.hops.filter((h) => seqs.includes(h.sequence))} config={config} />;
    } else {
      const edge = graph.edges.find((e) => e.id === selected.id);
      if (edge) {
        content = (
          <>
            <Typography variant="h6" component="h2">
              {names.get(edge.source)} → {names.get(edge.target)}
            </Typography>
            <Field label="Protocol">
              <ProtocolBadge config={config} protocol={edge.protocol} />
            </Field>
            <Field label="Direction">{edge.direction}</Field>
            <Section title={`Used by ${edge.integration_ids.length} integration(s)`}>
              <IntegrationLinks items={graph.integrations.filter((i) => edge.integration_ids.includes(i.id))} names={names} />
            </Section>
          </>
        );
      }
    }
  }
  if (!content && integration) content = <IntegrationDetail integration={integration} config={config} />;
  if (!content) {
    content = (
      <Typography variant="body2" color="text.secondary">
        Choose an upstream and downstream system to trace a flow, or click any system on the diagram to explore its
        upstream and downstream connections.
      </Typography>
    );
  }

  return (
    <Box sx={{ position: 'relative' }} data-testid="detail-panel">
      {selected && (
        <IconButton
          size="small"
          aria-label="Close details"
          onClick={() => (integration ? select(null) : explore(null))}
          sx={{ position: 'absolute', right: 0, top: 0 }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      )}
      {content}
    </Box>
  );
}
