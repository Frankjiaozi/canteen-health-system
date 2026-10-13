import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type {
  ComplianceResponse,
  DashboardSummary,
  PerCapitaResponse,
  TrendsResponse,
  WasteResponse,
} from '../types';

type Query = { query: { days: number } };

export async function fetchSummary(args: Query): Promise<DashboardSummary> {
  return unwrap(await api.GET('/api/v1/dashboard/summary', { params: args }));
}

export async function fetchTrends(args: Query): Promise<TrendsResponse> {
  return unwrap(await api.GET('/api/v1/dashboard/trends', { params: args }));
}

export async function fetchPerCapita(args: Query): Promise<PerCapitaResponse> {
  return unwrap(await api.GET('/api/v1/dashboard/per-capita', { params: args }));
}

export async function fetchCompliance(args: Query): Promise<ComplianceResponse> {
  return unwrap(await api.GET('/api/v1/dashboard/compliance', { params: args }));
}

export async function fetchWaste(args: Query): Promise<WasteResponse> {
  return unwrap(await api.GET('/api/v1/dashboard/waste', { params: args }));
}
