import { Box } from '@mui/material';
import { Background, Controls, MiniMap, Panel, ReactFlow, useReactFlow, type EdgeTypes, type NodeTypes } from '@xyflow/react';
import { useEffect, useMemo, useRef } from 'react';
import type { FlowConfig, Graph, Integration } from '../../api/types';
import { buildFlow, type FlowEdge, type FlowNode } from '../graphModel';
import { layeredLayout } from '../layout';
import { useFlowStore } from '../store';
import ExportMenu from './ExportMenu';
import Legend from './Legend';
import { PathEdge } from './PathEdge';
import { BandNode, SystemNode } from './SystemNode';

const nodeTypes: NodeTypes = { system: SystemNode, band: BandNode };
const edgeTypes: EdgeTypes = { path: PathEdge };

function sameNode(a: FlowNode, b: FlowNode): boolean {
  if (a.position.x !== b.position.x || a.position.y !== b.position.y) return false;
  const ad = a.data as Record<string, unknown>;
  const bd = b.data as Record<string, unknown>;
  return Object.keys(bd).every((k) => ad[k] === bd[k]);
}

function sameEdge(a: FlowEdge, b: FlowEdge): boolean {
  return (
    a.label === b.label &&
    a.sourceHandle === b.sourceHandle &&
    a.targetHandle === b.targetHandle &&
    a.selected === b.selected &&
    a.data?.hops === b.data?.hops &&
    JSON.stringify(a.style) === JSON.stringify(b.style)
  );
}

interface Props {
  graph: Graph;
  config: FlowConfig;
  integration: Integration | null;
  title: string;
}

export default function FlowGraph({ graph, config, integration, title }: Props) {
  const direction = useFlowStore((s) => s.direction);
  const exploreId = useFlowStore((s) => s.exploreId);
  const selected = useFlowStore((s) => s.selected);
  const select = useFlowStore((s) => s.select);
  const explore = useFlowStore((s) => s.explore);
  const { fitView } = useReactFlow();

  // Layout depends only on the dataset, so selecting a path never re-runs it.
  const layout = useMemo(() => layeredLayout(graph.nodes, graph.edges, config.layers), [graph, config]);
  const built = useMemo(
    () => buildFlow({ graph, config, layout, integration, direction, exploreId, selected }),
    [graph, config, layout, integration, direction, exploreId, selected],
  );
  // Reuse unchanged node/edge objects so React Flow re-renders only what a selection changed
  // (keeps path rendering well under 1 s at ~300 systems / 2,000 hops).
  const prev = useRef<{ nodes: Map<string, FlowNode>; edges: Map<string, FlowEdge> }>({ nodes: new Map(), edges: new Map() });
  const { nodes, edges } = useMemo(() => {
    const nodes = built.nodes.map((n) => {
      const old = prev.current.nodes.get(n.id);
      return old && sameNode(old, n) ? old : n;
    });
    const edges = built.edges.map((e) => {
      const old = prev.current.edges.get(e.id);
      return old && sameEdge(old, e) ? old : e;
    });
    prev.current = { nodes: new Map(nodes.map((n) => [n.id, n])), edges: new Map(edges.map((e) => [e.id, e])) };
    return { nodes, edges };
  }, [built]);

  // Zoom to the highlighted path (or explored neighbourhood); fit everything otherwise.
  const focusKey = integration ? `i:${integration.id}:${direction}` : exploreId ? `e:${exploreId}` : 'all';
  useEffect(() => {
    const ids = new Set<string>();
    if (integration) {
      integration.hops.forEach((h) => {
        ids.add(h.from_system);
        ids.add(h.to_system);
      });
    } else if (exploreId) {
      ids.add(exploreId);
      graph.edges.forEach((e) => {
        if (e.source === exploreId) ids.add(e.target);
        if (e.target === exploreId) ids.add(e.source);
      });
    }
    const t = window.setTimeout(() => {
      fitView(ids.size ? { nodes: [...ids].map((id) => ({ id })), padding: 0.1, duration: 300, maxZoom: 1.2 } : { padding: 0.05, duration: 300 });
    }, 30);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey, fitView]);

  return (
    <Box sx={{ position: 'absolute', inset: 0 }} data-testid="flow-graph">
      <ReactFlow<FlowNode, FlowEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable
        minZoom={0.1}
        maxZoom={2.5}
        fitView
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => {
          if (node.type !== 'system') return;
          // FR-10: without a selected integration, clicking a system explores its connections.
          if (integration) select({ kind: 'node', id: node.id });
          else explore(exploreId === node.id ? null : node.id);
        }}
        onEdgeClick={(_, edge) => select({ kind: 'edge', id: edge.id })}
        onPaneClick={() => (integration ? select(null) : explore(null))}
      >
        <Background gap={24} color="#e2e8f0" />
        <Controls showInteractive={false} position="bottom-right" />
        <MiniMap
          pannable
          zoomable
          position="bottom-left"
          style={{ width: 160, height: 100 }}
          nodeColor={(n) => (n.type === 'band' ? '#e2e8f0' : (n.data as { dimmed?: boolean }).dimmed ? '#cbd5e1' : '#334155')}
          ariaLabel="Mini map"
        />
        <Panel position="top-right">
          <ExportMenu integration={integration} title={title} />
        </Panel>
        <Panel position="top-left">
          <Legend config={config} />
        </Panel>
      </ReactFlow>
    </Box>
  );
}
