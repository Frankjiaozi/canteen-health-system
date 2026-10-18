import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StartupGate } from './StartupGate';

vi.mock('./InkProgressStroke', () => ({ InkProgressStroke: () => null }));
let imageFails = false;

beforeEach(() => {
  vi.useFakeTimers();
  imageFails = false;
  window.history.replaceState(null, '', '/admin/ingredients?search=rice');
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  vi.stubGlobal(
    'Image',
    class {
      src = '';
      decode() {
        return imageFails ? Promise.reject(new Error('offline')) : Promise.resolve();
      }
    },
  );
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(performance.now()), 16),
  );
  vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id));
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

describe('正式入口进场动画', () => {
  it('自动结束后放行原地址，业务交互不重新播放，也没有播放控件', async () => {
    render(
      <StartupGate>
        <button onClick={() => window.history.pushState(null, '', '/admin/collection')}>
          进入采集
        </button>
      </StartupGate>,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByRole('main', { name: '知味进场动画' })).toBeVisible();
    expect(screen.queryByRole('slider')).toBeNull();
    expect(screen.queryByRole('button', { name: /重播|暂停|慢放/ })).toBeNull();
    expect(screen.queryByRole('button', { name: '进入采集' })).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(screen.queryByRole('main', { name: '知味进场动画' })).toBeNull();
    expect(window.location.pathname + window.location.search).toBe(
      '/admin/ingredients?search=rice',
    );
    fireEvent.click(screen.getByRole('button', { name: '进入采集' }));
    expect(window.location.pathname).toBe('/admin/collection');
    expect(screen.queryByRole('main', { name: '知味进场动画' })).toBeNull();
  });

  it('图片失败时仍然放行，离线或资源异常不能卡住系统', async () => {
    imageFails = true;
    render(
      <StartupGate>
        <button>进入系统</button>
      </StartupGate>,
    );
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(screen.getByRole('button', { name: '进入系统' })).toBeVisible();
    expect(screen.queryByRole('main', { name: '知味进场动画' })).toBeNull();
  });

  it('公开大屏直接展示，不等待进场动画', () => {
    window.history.replaceState(null, '', '/display');
    render(
      <StartupGate>
        <div>公开大屏</div>
      </StartupGate>,
    );
    expect(screen.getByText('公开大屏')).toBeVisible();
    expect(screen.queryByRole('main', { name: '知味进场动画' })).toBeNull();
  });
});
