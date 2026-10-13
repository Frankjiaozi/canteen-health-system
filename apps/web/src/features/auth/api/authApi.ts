import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { AuthUser, LoginPayload } from '../types';

export async function login(payload: LoginPayload): Promise<AuthUser> {
  return unwrap(await api.POST('/api/v1/auth/login', { body: payload }));
}

export async function logout(): Promise<void> {
  await api.POST('/api/v1/auth/logout');
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return unwrap(await api.GET('/api/v1/auth/me'));
}
