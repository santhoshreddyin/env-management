import { MarkerType, type Edge, type Node } from '@xyflow/react';
import type { Direction, FlowConfig, Graph, Hop, Integration, Protocol, System } from '../api/types';
import { NODE_H, type LayoutResult } from './layout';
import type { DirectionView, Selected } from './store';

export type NodeRole = 'upstream' | 'downstream' | 'focus' | null;

export interface SystemNodeData extends Record<string, unknown> {
  system: System;
  typeLabel: string;
  typeColor: string;
  dimmed: boolean;
  role: NodeRole;
  selected: boolean;
}

export interface BandNodeData extends Record<string, unknown> {
  label: string;
}

export interface FlowEdgeData extends Record<string, unknown> {
  kind: 'base' | 'path';
  protocol: Protocol;
  direction: Direction;
  integrationIds?: string[];
  hops?: Hop[];
}

export type SystemFlowNode = Node<SystemNodeData, 'system'>;
export type BandFlowNode = Node<BandNodeData, 'band'>;
export type FlowNode = SystemFlowNode | BandFlowNode;
export type FlowEdge = Edge<FlowEdgeData>;

interface BuildInput {
  graph: Graph;
  config: FlowConfig;
  layout: LayoutResult;
  integration: Integration | null;
  direction: DirectionView;
  exploreId: string | null;
  selected: Selected;
}

const matchesDirection = (d: Direction, view: DirectionView) => view === 'both' || view === d;

/** Choose handles so edges flow left-to-right between layers; replies use a second slot. */
function handles(input: BuildInput, source: string, target: string, direction: Direction) {
  const { layerIndex, positions } = input.layout;
  const slot = direction === 'reply' ? 'b' : 'a';
  const sl = layerIndex.get(source) ?? 0;
  const tl = layerIndex.get(target) ?? 0;
  if (tl > sl) return { sourceHandle: `s-right-${slot}`, targetHandle: `t-left-${slot}` };
  if (tl < sl) return { sourceHandle: `s-left-${slot}`, targetHandle: `t-right-${slot}` };
  const below = (positions.get(target)?.y ?? 0) >= (positions.get(source)?.y ?? 0);
  return below
    ? { sourceHandle: `s-bottom-${slot}`, targetHandle: `t-top-${slot}` }
    : { sourceHandle: `s-top-${slot}`, targetHandle: `t-bottom-${slot}` };
}

export function protocolStyle(config: FlowConfig, protocol: string) {
  return config.protocols[protocol] ?? { label: protocol, color: '#475569', dash: null };
}

function edgeVisual(config: FlowConfig, protocol: Protocol, direction: Direction, emphasis: number, opacity: number) {
  const p = protocolStyle(config, protocol);
  const d = config.directions[direction];
  return {
    style: {
      stroke: p.color,
      strokeWidth: d.stroke_width * emphasis,
      strokeDasharray: p.dash ?? undefined,
      opacity,
    },
    markerEnd: {
      type: d.marker === 'arrow' ? MarkerType.Arrow : MarkerType.ArrowClosed,
      color: p.color,
      width: 16,
      height: 16,
    },
  };
}

export function buildFlow(input: BuildInput): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const { graph, config, layout, integration, direction, exploreId, selected } = input;

  // Which systems/edges are "lit": the selected path, or an explored system and its neighbours.
  let lit: Set<string> | null = null;
  const pathHops = integration ? integration.hops.filter((h) => matchesDirection(h.direction, direction)) : [];
  if (integration) {
    lit = new Set([integration.upstream_id, integration.downstream_id]);
    pathHops.forEach((h) => {
      lit!.add(h.from_system);
      lit!.add(h.to_system);
    });
  } else if (exploreId) {
    lit = new Set([exploreId]);
    graph.edges.forEach((e) => {
      if (e.source === exploreId) lit!.add(e.target);
      if (e.target === exploreId) lit!.add(e.source);
    });
  }

  const nodes: FlowNode[] = layout.bands.map((b) => ({
    id: `band-${b.id}`,
    type: 'band',
    position: { x: b.x, y: b.y },
    data: { label: b.label },
    style: { width: b.width, height: b.height },
    width: b.width,
    height: b.height,
    selectable: false,
    draggable: false,
    focusable: false,
    zIndex: -1,
  }));

  graph.nodes.forEach((s) => {
    const t = config.system_types[s.type] ?? { label: s.type, color: '#f1f5f9' };
    let role: NodeRole = null;
    if (integration?.upstream_id === s.id) role = 'upstream';
    else if (integration?.downstream_id === s.id) role = 'downstream';
    else if (exploreId === s.id) role = 'focus';
    nodes.push({
      id: s.id,
      type: 'system',
      position: layout.positions.get(s.id) ?? { x: 0, y: 0 },
      data: {
        system: s,
        typeLabel: t.label,
        typeColor: t.color,
        dimmed: lit !== null && !lit.has(s.id),
        role,
        selected: selected?.kind === 'node' && selected.id === s.id,
      },
      height: NODE_H,
      ariaLabel: `${s.name}, ${t.label}${role ? `, ${role}` : ''}`,
    });
  });

  const edges: FlowEdge[] = [];
  graph.edges.forEach((e) => {
    if (!matchesDirection(e.direction, direction)) return;
    let opacity = 0.55;
    if (integration) opacity = 0.08;
    else if (exploreId) opacity = e.source === exploreId || e.target === exploreId ? 1 : 0.08;
    const isSel = selected?.kind === 'edge' && selected.id === e.id;
    edges.push({
      id: e.id,
      source: e.source,
      target: e.target,
      ...handles(input, e.source, e.target, e.direction),
      ...edgeVisual(config, e.protocol, e.direction, isSel ? 2 : 1, isSel ? 1 : opacity),
      data: { kind: 'base', protocol: e.protocol, direction: e.direction, integrationIds: e.integration_ids },
      ariaLabel: `${e.protocol} ${e.direction} from ${e.source} to ${e.target}`,
    });
  });

  if (integration) {
    // Group hops that share the same visual edge, so labels read e.g. "2, 6 · MQ".
    const groups = new Map<string, Hop[]>();
    pathHops.forEach((h) => {
      const key = `${h.from_system}>${h.to_system}:${h.protocol}:${h.direction}`;
      groups.set(key, [...(groups.get(key) ?? []), h]);
    });
    groups.forEach((hops) => {
      const h = hops[0];
      const id = `hop-${hops.map((x) => x.sequence).join('-')}`;
      const isSel = selected?.kind === 'edge' && selected.id === id;
      const p = protocolStyle(config, h.protocol);
      const label = `${hops.map((x) => x.sequence).join(', ')} · ${p.label}${h.direction === 'reply' ? ' ↩ reply' : ''}`;
      edges.push({
        id,
        source: h.from_system,
        target: h.to_system,
        ...handles(input, h.from_system, h.to_system, h.direction),
        ...edgeVisual(config, h.protocol, h.direction, isSel ? 1.8 : 1.3, 1),
        type: 'path',
        label,
        selected: isSel,
        zIndex: 10,
        data: { kind: 'path', protocol: h.protocol, direction: h.direction, hops },
        ariaLabel: `Hop ${label} from ${h.from_name} to ${h.to_name}`,
      });
    });
  }

  return { nodes, edges };
}
