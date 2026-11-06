import type { GraphEdge, System } from '../api/types';

export const NODE_W = 200;
export const NODE_H = 64;
const COL_GAP = 90;
const ROW_GAP = 26;
const BAND_PAD = 18;
const HEADER = 44;

export interface Band {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LayoutResult {
  positions: Map<string, { x: number; y: number }>;
  layerIndex: Map<string, number>;
  bands: Band[];
}

/**
 * Layered layout (FR-9): one column per configured layer, left to right, nodes ordered
 * within each column by the barycentre heuristic to reduce edge crossings.
 * Deterministic and O(iterations x edges), so it stays fast at ~300 systems.
 */
export function layeredLayout(nodes: System[], edges: GraphEdge[], layers: { id: string; label: string }[]): LayoutResult {
  const layerIds = layers.map((l) => l.id);
  const layerIndex = new Map<string, number>();
  nodes.forEach((n) => {
    const i = layerIds.indexOf(n.display_layer);
    layerIndex.set(n.id, i >= 0 ? i : layerIds.length - 1);
  });

  const columns: string[][] = layerIds.map(() => []);
  [...nodes]
    .sort((a, b) => (a.domain ?? '').localeCompare(b.domain ?? '') || a.name.localeCompare(b.name))
    .forEach((n) => columns[layerIndex.get(n.id)!].push(n.id));

  const neighbours = new Map<string, Set<string>>();
  edges.forEach((e) => {
    if (layerIndex.get(e.source) === layerIndex.get(e.target)) return;
    if (!neighbours.has(e.source)) neighbours.set(e.source, new Set());
    if (!neighbours.has(e.target)) neighbours.set(e.target, new Set());
    neighbours.get(e.source)!.add(e.target);
    neighbours.get(e.target)!.add(e.source);
  });

  const rank = new Map<string, number>();
  const updateRanks = () =>
    columns.forEach((col) => col.forEach((id, i) => rank.set(id, col.length > 1 ? i / (col.length - 1) : 0.5)));
  updateRanks();

  for (let iter = 0; iter < 6; iter++) {
    const order = iter % 2 === 0 ? columns.keys() : [...columns.keys()].reverse();
    for (const ci of order) {
      const bary = new Map<string, number>();
      columns[ci].forEach((id) => {
        const ns = [...(neighbours.get(id) ?? [])];
        bary.set(id, ns.length ? ns.reduce((sum, n) => sum + rank.get(n)!, 0) / ns.length : rank.get(id)!);
      });
      columns[ci].sort((a, b) => bary.get(a)! - bary.get(b)!);
      updateRanks();
    }
  }

  const maxRows = Math.max(1, ...columns.map((c) => c.length));
  const rowH = NODE_H + ROW_GAP;
  const bandHeight = HEADER + BAND_PAD * 2 + maxRows * rowH - ROW_GAP;
  const positions = new Map<string, { x: number; y: number }>();
  const bands: Band[] = [];

  columns.forEach((col, ci) => {
    const bandX = ci * (NODE_W + BAND_PAD * 2 + COL_GAP);
    const offset = ((maxRows - col.length) * rowH) / 2;
    col.forEach((id, i) => positions.set(id, { x: bandX + BAND_PAD, y: HEADER + BAND_PAD + offset + i * rowH }));
    bands.push({ id: layers[ci].id, label: layers[ci].label, x: bandX, y: 0, width: NODE_W + BAND_PAD * 2, height: bandHeight });
  });

  return { positions, layerIndex, bands };
}
