import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import { toApiError } from '@/shared/api/errors';
import type { AuthUser, LoginPayload, RegisterPayload } from '../types';

export async function register(payload: RegisterPayload): Promise<AuthUser> {
  return unwrap(await api.POST('/api/v1/auth/register', { body: payload }));
}

export async function login(payload: LoginPayload): Promise<AuthUser> {
  return unwrap(await api.POST('/api/v1/auth/login', { body: payload }));
}

export async function logout(): Promise<void> {
  const result = await api.POST('/api/v1/auth/logout');
  if (!result.response.ok) {
    throw toApiError(result.response.status, result.error);
  }
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return unwrap(await api.GET('/api/v1/auth/me'));
}

export async function fetchAuthOptions() {
  return unwrap(await api.GET('/api/v1/auth/options'));
}
