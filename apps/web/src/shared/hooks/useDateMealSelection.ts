import dayjs from 'dayjs';
import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * 「日期 + 餐次」的选择状态，同时同步到地址栏。
 *
 * 同步到地址栏不只是为了好看：录入员可以把「去录今天这餐」的链接直接发给同事，
 * 刷新页面也不会跳回今天；端到端测试同样可以径直打开某一天，不必去操作日期控件。
 */
export function useDateMealSelection(defaultMeal: string) {
  const [params, setParams] = useSearchParams();
  const date = params.get('date') ?? dayjs().format('YYYY-MM-DD');
  const meal = params.get('meal') ?? defaultMeal;

  const update = useCallback(
    (next: { date?: string; meal?: string }) => {
      const merged = new URLSearchParams(params);
      if (next.date !== undefined) merged.set('date', next.date);
      if (next.meal !== undefined) merged.set('meal', next.meal);
      // replace：翻日期不该在浏览历史里堆一串记录
      setParams(merged, { replace: true });
    },
    [params, setParams],
  );

  return {
    date,
    meal,
    setDate: (value: string) => update({ date: value }),
    setMeal: (value: string) => update({ meal: value }),
  };
}
