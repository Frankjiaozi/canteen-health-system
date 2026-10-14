import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { MenuSuggestionRead, SuggestionStatus, SuggestionSummary } from '../types';

export async function fetchSuggestions(onDate: string): Promise<SuggestionSummary[]> {
  return unwrap(
    await api.GET('/api/v1/recommendation', { params: { query: { on_date: onDate } } }),
  );
}

export async function fetchSuggestionById(id: string): Promise<MenuSuggestionRead> {
  return unwrap(
    await api.GET('/api/v1/recommendation/{suggestion_id}', {
      params: { path: { suggestion_id: id } },
    }),
  );
}

export async function decideSuggestion(
  id: string,
  status: SuggestionStatus,
  reason: string | null,
): Promise<MenuSuggestionRead> {
  return unwrap(
    await api.POST('/api/v1/recommendation/{suggestion_id}/decide', {
      params: { path: { suggestion_id: id } },
      body: { status, reason },
    }),
  );
}
