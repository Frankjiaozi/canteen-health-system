import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { DishCategory } from '../types';

interface BrowseState {
  page: number;
  pageSize: number;
  view: string;
  keyword: string;
  category: DishCategory | null;
  includeInactive: boolean;
}
const defaults: BrowseState = {
  page: 1,
  pageSize: 12,
  view: 'cards',
  keyword: '',
  category: null,
  includeInactive: false,
};
const categories = ['MEAT', 'HALF_MEAT', 'VEGETABLE', 'SOUP', 'STAPLE', 'DRINK'];

export function useDishBrowseState(userId?: string) {
  const key = `zhiwei:dishes:browse:v1:${userId ?? 'current'}`;
  const [snapshot] = useState(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(key) ?? 'null');
      return {
        state: {
          page: Number.isInteger(value?.page) && value.page > 0 ? value.page : 1,
          pageSize: [12, 24, 48].includes(value?.pageSize) ? value.pageSize : 12,
          view: value?.view === 'list' ? 'list' : 'cards',
          keyword: typeof value?.keyword === 'string' ? value.keyword.slice(0, 200) : '',
          category: categories.includes(value?.category) ? (value.category as DishCategory) : null,
          includeInactive: value?.includeInactive === true,
        },
        scroll: typeof value?.scroll === 'number' && value.scroll > 0 ? value.scroll : 0,
      };
    } catch {
      return { state: defaults, scroll: 0 };
    }
  });
  const [state, setState] = useState<BrowseState>(snapshot.state);
  const current = useRef(state);
  const position = useRef(snapshot.scroll);
  const restored = useRef(false);
  useEffect(() => {
    current.current = state;
    try {
      sessionStorage.setItem(key, JSON.stringify({ ...state, scroll: position.current }));
    } catch {
      /* 存储不可用时仍可浏览 */
    }
  }, [key, snapshot.scroll, state]);
  useLayoutEffect(() => {
    let frame = 0;
    const save = () => {
      if (!restored.current) return;
      try {
        sessionStorage.setItem(
          key,
          JSON.stringify({ ...current.current, scroll: position.current }),
        );
      } catch {
        /* 浏览不依赖存储 */
      }
    };
    const onScroll = () => {
      if (restored.current) position.current = window.scrollY;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(save);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      save();
      window.removeEventListener('scroll', onScroll);
    };
  }, [key]);
  const restoreScroll = useCallback(() => {
    if (restored.current) return;
    restored.current = true;
    window.scrollTo({ top: snapshot.scroll, behavior: 'instant' });
  }, [snapshot.scroll]);
  const update = useCallback((value: Partial<BrowseState>) => {
    restored.current = true;
    position.current = 0;
    setState((previous) => ({ ...previous, ...value }));
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);
  return { state, update, restoreScroll };
}
