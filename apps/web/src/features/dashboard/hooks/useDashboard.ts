import { useQuery } from '@tanstack/react-query';
import {
  fetchCompliance,
  fetchMenuOverview,
  fetchPerCapita,
  fetchSummary,
  fetchTrends,
  fetchWaste,
} from '../api/dashboardApi';

// 看板是服务端聚合结果，时间范围一变就该重新取，不做长缓存
const COMMON = { staleTime: 60_000 } as const;

export function useDashboard(days: number) {
  const params = { query: { days } };

  const summary = useQuery({
    queryKey: ['dashboard', 'summary', days],
    queryFn: () => fetchSummary(params),
    ...COMMON,
  });
  const trends = useQuery({
    queryKey: ['dashboard', 'trends', days],
    queryFn: () => fetchTrends(params),
    ...COMMON,
  });
  const perCapita = useQuery({
    queryKey: ['dashboard', 'per-capita', days],
    queryFn: () => fetchPerCapita(params),
    ...COMMON,
  });
  const compliance = useQuery({
    queryKey: ['dashboard', 'compliance', days],
    queryFn: () => fetchCompliance(params),
    ...COMMON,
  });
  const waste = useQuery({
    queryKey: ['dashboard', 'waste', days],
    queryFn: () => fetchWaste(params),
    ...COMMON,
  });

  return { summary, trends, perCapita, compliance, waste };
}

export function useMenuOverview() {
  return useQuery({
    queryKey: ['dashboard', 'menus'],
    queryFn: fetchMenuOverview,
    staleTime: 30_000,
  });
}
