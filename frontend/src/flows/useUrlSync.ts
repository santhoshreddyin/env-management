import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { Graph } from '../api/types';
import { useFlowStore, type DirectionView } from './store';

/**
 * FR-15 deep links: keeps the selection in the URL, e.g.
 * ?from=Polisy&to=Billing&journey=renewal&integration=INT-003&direction=reply
 * System references use names (readable) but ids are accepted too.
 */
export function useUrlSync(graph: Graph | undefined) {
  const [params, setParams] = useSearchParams();
  const hydrated = useRef(false);
  const state = useFlowStore();

  useEffect(() => {
    if (!graph || hydrated.current) return;
    const resolve = (ref: string | null) => {
      if (!ref) return null;
      const r = ref.toLowerCase();
      return graph.nodes.find((n) => n.id === ref)?.id ?? graph.nodes.find((n) => n.name.toLowerCase() === r)?.id ?? null;
    };
    const direction = params.get('direction');
    const explore = resolve(params.get('system'));
    state.hydrate({
      upstream: resolve(params.get('from')),
      downstream: resolve(params.get('to')),
      journey: params.get('journey'),
      pattern: params.get('pattern'),
      protocol: params.get('protocol'),
      integrationId: params.get('integration'),
      direction: (['request', 'reply'].includes(direction ?? '') ? direction : 'both') as DirectionView,
      exploreId: explore,
      selected: explore ? { kind: 'node', id: explore } : null,
    });
    hydrated.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  const { upstream, downstream, journey, pattern, protocol, integrationId, direction, exploreId } = state;
  useEffect(() => {
    if (!graph || !hydrated.current) return;
    const name = (id: string | null) => (id ? (graph.nodes.find((n) => n.id === id)?.name ?? id) : null);
    const next = new URLSearchParams();
    const entries: [string, string | null][] = [
      ['from', name(upstream)],
      ['to', name(downstream)],
      ['journey', journey],
      ['pattern', pattern],
      ['protocol', protocol],
      ['integration', integrationId],
      ['direction', direction === 'both' ? null : direction],
      ['system', integrationId ? null : name(exploreId)],
    ];
    entries.forEach(([k, v]) => v && next.set(k, v));
    if (next.toString() !== params.toString()) setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, upstream, downstream, journey, pattern, protocol, integrationId, direction, exploreId]);
}
