import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { notifyMenuDataChanged, useMenuDataRevision } from './useMenuDataRevision';

class MockBroadcastChannel {
  onmessage: ((event: MessageEvent<number>) => void) | null = null;

  constructor(public name: string) {}
  postMessage(): void {}
  close(): void {}
}

describe('菜单数据跨页面刷新', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal('BroadcastChannel', MockBroadcastChannel);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('收到其它标签页的版本事件后更新查询版本', () => {
    const { result } = renderHook(() => useMenuDataRevision());
    const next = result.current + 100;

    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'canteen:menu-data-revision',
          newValue: String(next),
        }),
      );
    });

    expect(result.current).toBe(next);
  });

  it('菜单发布后写入新版本供大屏和看板重新取数', () => {
    act(() => notifyMenuDataChanged());

    expect(Number(window.localStorage.getItem('canteen:menu-data-revision'))).toBeGreaterThan(0);
  });

  it('没有广播接口时，同页也会立即更新，连续通知版本递增', () => {
    vi.stubGlobal('BroadcastChannel', undefined);
    const { result } = renderHook(() => useMenuDataRevision());
    const before = result.current;
    act(() => notifyMenuDataChanged());
    expect(result.current).toBeGreaterThan(before);
    const first = result.current;
    act(() => notifyMenuDataChanged());
    expect(result.current).toBeGreaterThan(first);
  });

  it('本地存储和广播被禁用时不使业务提交失败', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.stubGlobal(
      'BroadcastChannel',
      class {
        constructor() {
          throw new Error('denied');
        }
      },
    );
    const { result } = renderHook(() => useMenuDataRevision());
    const before = result.current;
    act(() => {
      expect(() => notifyMenuDataChanged()).not.toThrow();
    });
    expect(result.current).toBeGreaterThan(before);
  });

  it('忽略无效或过期的跨页版本', () => {
    const { result } = renderHook(() => useMenuDataRevision());
    const before = result.current;
    for (const value of ['NaN', 'Infinity', '-1', '0']) {
      act(() =>
        window.dispatchEvent(
          new StorageEvent('storage', { key: 'canteen:menu-data-revision', newValue: value }),
        ),
      );
      expect(result.current).toBe(before);
    }
  });
});
