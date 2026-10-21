import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useMenuDataRevision } from '@/shared/hooks/useMenuDataRevision';
import { fetchPublicBoard } from '../api/displayApi';
import type { DisplayMeal } from '../lib/meal';

// 公开大屏数据。
//
// 免登录接口，出错时不该把用户往登录页赶。大屏常年挂着运行，
// 因此定时刷新——食堂当天补录之后，画面会自己跟上。
//
// 带 `?date=` 时看的是那一天（回看与功能验证用），不带就是今天。挂机的大屏不带参数。
export function usePublicBoard(onDate?: string, mealType?: DisplayMeal) {
  const [params] = useSearchParams();
  const target = onDate ?? params.get('date') ?? undefined;
  const revision = useMenuDataRevision();

  return useQuery({
    queryKey: ['public', 'board', target ?? 'today', mealType ?? 'auto', revision],
    queryFn: () => fetchPublicBoard(target, mealType),
    retry: 2,
    refetchInterval: 60_000,
  });
}
