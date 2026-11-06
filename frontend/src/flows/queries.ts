import { useQuery } from '@tanstack/react-query';
import { flowsApi, type FlowFilters } from '../api/flows';

export const useMe = () => useQuery({ queryKey: ['me'], queryFn: flowsApi.me, staleTime: Infinity });
export const useFlowConfig = () => useQuery({ queryKey: ['flow-config'], queryFn: flowsApi.config, staleTime: Infinity });
export const useGraph = () => useQuery({ queryKey: ['graph'], queryFn: flowsApi.graph });
export const useJourneys = () => useQuery({ queryKey: ['journeys'], queryFn: flowsApi.journeys });

export const usePairs = (params: FlowFilters & { upstream?: string | null }) =>
  useQuery({ queryKey: ['pairs', params], queryFn: () => flowsApi.pairs(params) });

export const useIntegrations = (params: FlowFilters & { from?: string | null; to?: string | null }, enabled: boolean) =>
  useQuery({ queryKey: ['integrations', params], queryFn: () => flowsApi.integrations(params), enabled });

export const useVersions = () => useQuery({ queryKey: ['imports'], queryFn: flowsApi.versions });
export const useAudit = (enabled: boolean) => useQuery({ queryKey: ['audit'], queryFn: flowsApi.audit, enabled });
