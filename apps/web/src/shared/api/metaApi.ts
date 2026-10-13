import type { components } from '@canteen/api-client';
import { api } from './client';
import { unwrap } from './result';

export type EnumOption = components['schemas']['EnumOption'];
export type EnumOptions = components['schemas']['EnumOptions'];

export async function fetchEnumOptions(): Promise<EnumOptions> {
  return unwrap(await api.GET('/api/v1/meta/enums'));
}
