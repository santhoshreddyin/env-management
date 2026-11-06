import { create } from 'zustand';

export type DirectionView = 'both' | 'request' | 'reply';
export type Selected = { kind: 'node'; id: string } | { kind: 'edge'; id: string } | null;

export interface FlowSelection {
  upstream: string | null;
  downstream: string | null;
  journey: string | null;
  pattern: string | null;
  protocol: string | null;
  integrationId: string | null;
  direction: DirectionView;
  /** FR-10: system whose connections are shown in free exploration mode. */
  exploreId: string | null;
}

interface FlowState extends FlowSelection {
  selected: Selected;
  setUpstream: (id: string | null) => void;
  setDownstream: (id: string | null) => void;
  setFilter: (key: 'journey' | 'pattern' | 'protocol', value: string | null) => void;
  setIntegration: (id: string | null) => void;
  setDirection: (d: DirectionView) => void;
  select: (s: Selected) => void;
  explore: (id: string | null) => void;
  /** Jump to a specific integration (from explore lists, detail panel, deep links). */
  showIntegration: (upstream: string, downstream: string, integrationId: string) => void;
  hydrate: (s: Partial<FlowSelection> & { selected?: Selected }) => void;
  reset: () => void;
}

const initial: FlowSelection = {
  upstream: null,
  downstream: null,
  journey: null,
  pattern: null,
  protocol: null,
  integrationId: null,
  direction: 'both',
  exploreId: null,
};

export const useFlowStore = create<FlowState>((set) => ({
  ...initial,
  selected: null,
  setUpstream: (upstream) =>
    set((s) => ({
      upstream,
      downstream: upstream === s.upstream ? s.downstream : null,
      integrationId: null,
      selected: null,
      exploreId: null,
    })),
  setDownstream: (downstream) => set({ downstream, integrationId: null, selected: null, exploreId: null }),
  setFilter: (key, value) => set({ [key]: value, integrationId: null, selected: null } as Partial<FlowState>),
  setIntegration: (integrationId) => set({ integrationId, selected: null }),
  setDirection: (direction) => set({ direction }),
  select: (selected) => set({ selected }),
  explore: (exploreId) => set({ exploreId, selected: exploreId ? { kind: 'node', id: exploreId } : null }),
  showIntegration: (upstream, downstream, integrationId) =>
    set({ upstream, downstream, integrationId, journey: null, pattern: null, protocol: null, exploreId: null, selected: null }),
  hydrate: (s) => set(s),
  reset: () => set({ ...initial, selected: null }),
}));
