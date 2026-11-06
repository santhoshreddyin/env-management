import { Alert, Box, Button, CircularProgress, Divider, Paper, Stack, Typography } from '@mui/material';
import { ReactFlowProvider } from '@xyflow/react';
import { useEffect } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import DetailPanel from './components/DetailPanel';
import FlowGraph from './components/FlowGraph';
import HopList from './components/HopList';
import IntegrationList from './components/IntegrationList';
import Narrative from './components/Narrative';
import SelectionPanel from './components/SelectionPanel';
import { useFlowConfig, useGraph, useIntegrations } from './queries';
import { useFlowStore } from './store';
import { useUrlSync } from './useUrlSync';

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Typography variant="overline" component="h2" sx={{ display: 'block', lineHeight: 2, color: 'text.secondary' }}>
      {children}
    </Typography>
  );
}

export default function FlowExplorerPage() {
  const graph = useGraph();
  const config = useFlowConfig();
  useUrlSync(graph.data);

  const s = useFlowStore();
  const integrations = useIntegrations(
    { from: s.upstream, to: s.downstream, journey: s.journey, pattern: s.pattern, protocol: s.protocol },
    Boolean(s.upstream),
  );
  const list = s.upstream ? (integrations.data ?? []) : [];
  const integration = list.find((i) => i.id === s.integrationId) ?? null;

  // Auto-select the first match (or keep a deep-linked one if it is in the list).
  useEffect(() => {
    if (!integrations.isSuccess || !s.downstream) return;
    if (!list.some((i) => i.id === s.integrationId)) s.setIntegration(list[0]?.id ?? null);
  }, [integrations.isSuccess, list, s]);

  if (graph.isError || config.isError) {
    return <Alert severity="error">Could not load the architecture: {(graph.error ?? config.error)?.message}</Alert>;
  }
  if (!graph.data || !config.data) {
    return (
      <Box sx={{ display: 'grid', placeItems: 'center', height: '60vh' }}>
        <CircularProgress aria-label="Loading" />
      </Box>
    );
  }
  if (!graph.data.nodes.length) {
    return (
      <Alert severity="info" action={<Button component={RouterLink} to="/data">Go to data</Button>}>
        No integration data yet. Import an Excel workbook on the Data page.
      </Alert>
    );
  }

  const title = integration
    ? `${integration.name}: ${integration.upstream_name} → ${integration.downstream_name}`
    : 'Base architecture';

  return (
    <ReactFlowProvider>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '360px 1fr 320px' },
          gridTemplateRows: { xs: 'auto 70vh auto', lg: '1fr' },
          gap: 1.5,
          height: { lg: 'calc(100vh - 88px)' },
        }}
      >
        <Paper variant="outlined" sx={{ p: 2, overflowY: 'auto' }} component="aside" aria-label="Flow selection">
          <SectionTitle>Trace a flow</SectionTitle>
          <SelectionPanel config={config.data} />
          {(s.upstream || s.exploreId) && (
            <Button size="small" sx={{ mt: 1 }} onClick={s.reset}>
              Clear selection
            </Button>
          )}

          {s.upstream && (
            <>
              <Divider sx={{ my: 2 }} />
              <SectionTitle>
                {s.downstream ? 'Matching integrations' : 'Integrations from this upstream'} ({list.length})
              </SectionTitle>
              {integrations.isLoading && <CircularProgress size={20} />}
              {integrations.isSuccess && !list.length && (
                <Typography variant="body2" color="text.secondary">
                  No integrations match the current filters.
                </Typography>
              )}
              <IntegrationList
                config={config.data}
                integrations={list}
                selectedId={integration?.id ?? null}
                onSelect={(id) => {
                  const it = list.find((i) => i.id === id)!;
                  if (!s.downstream) s.showIntegration(it.upstream_id, it.downstream_id, id);
                  else s.setIntegration(id);
                }}
              />
            </>
          )}

          {integration && (
            <>
              <Divider sx={{ my: 2 }} />
              <SectionTitle>Hops ({integration.hops.length})</SectionTitle>
              <HopList config={config.data} integration={integration} />
              <Divider sx={{ my: 2 }} />
              <SectionTitle>Step by step</SectionTitle>
              <Narrative integration={integration} />
            </>
          )}
        </Paper>

        <Paper variant="outlined" sx={{ position: 'relative', overflow: 'hidden', minHeight: 420 }} component="section" aria-label={`Diagram: ${title}`}>
          <FlowGraph graph={graph.data} config={config.data} integration={integration} title={title} />
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, overflowY: 'auto' }} component="aside" aria-label="Details">
          <Stack>
            <SectionTitle>Details</SectionTitle>
            <DetailPanel graph={graph.data} config={config.data} integration={integration} />
          </Stack>
        </Paper>
      </Box>
    </ReactFlowProvider>
  );
}
