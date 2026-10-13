import { useQuery } from '@tanstack/react-query';
import { fetchEnumOptions } from '@/shared/api/metaApi';

/**
 * 枚举取值与中文文案。

 * 这些内容随代码发布变化，运行期不会变，所以缓存不过期。
 * 前端的下拉框一律用这里的 label，不再自己维护一份中文映射。
 */
export function useEnumOptions() {
  return useQuery({
    queryKey: ['meta', 'enums'],
    queryFn: fetchEnumOptions,
    staleTime: Infinity,
  });
}
