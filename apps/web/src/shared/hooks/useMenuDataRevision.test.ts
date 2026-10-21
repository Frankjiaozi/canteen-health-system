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
  });

  it('收到其它标签页的版本事件后更新查询版本', () => {
    const { result } = renderHook(() => useMenuDataRevision());
    expect(result.current).toBe(0);

    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'canteen:menu-data-revision',
          newValue: String(1234),
        }),
      );
    });

    expect(result.current).toBe(1234);
  });

  it('菜单发布后写入新版本供大屏和看板重新取数', () => {
    act(() => notifyMenuDataChanged());

    expect(Number(window.localStorage.getItem('canteen:menu-data-revision'))).toBeGreaterThan(0);
  });
});
