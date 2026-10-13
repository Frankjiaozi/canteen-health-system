import { useQuery } from '@tanstack/react-query';
import { fetchPublicBoard } from '../api/displayApi';

// 公开大屏数据。
//
// 免登录接口，出错时不该把用户往登录页赶。大屏常年挂着运行，
// 因此定时刷新——食堂当天补录之后，画面会自己跟上。
export function usePublicBoard() {
  return useQuery({
    queryKey: ['public', 'board', 'today'],
    queryFn: fetchPublicBoard,
    retry: 2,
    refetchInterval: 5 * 60_000,
  });
}
