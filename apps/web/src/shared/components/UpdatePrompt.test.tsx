import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppProviders } from '@/app/providers';

/** 由用例控制「有没有新版本」；虚拟模块在测试环境里不存在，必须 mock。 */
const needRefresh = { value: false };
const updateServiceWorker = vi.fn();
const onRegisteredSW = { current: undefined as undefined | ((url: string, reg: unknown) => void) };

vi.mock('virtual:pwa-register/react', () => ({
  useRegisterSW: (options?: { onRegisteredSW?: (url: string, registration: unknown) => void }) => {
    if (options?.onRegisteredSW) onRegisteredSW.current = options.onRegisteredSW;
    return {
      needRefresh: [needRefresh.value, vi.fn()],
      offlineReady: [false, vi.fn()],
      updateServiceWorker,
    };
  },
}));

const { UpdatePrompt } = await import('./UpdatePrompt');

/**
 * 用生产同一套 Provider 包起来。
 *
 * 不这么做的话，AntD 会给「两个汉字的按钮」自动插入空格，「刷新」会变成「刷 新」——
 * 测试里查不到按钮，界面上倒是真的多一个空格。AppProviders 里关掉了这个行为，
 * 测试跟着它走才不会和实际界面对不上。
 */
function renderPrompt() {
  return render(
    <AppProviders>
      <UpdatePrompt />
    </AppProviders>,
  );
}

describe('新版本提示', () => {
  beforeEach(() => {
    needRefresh.value = false;
    updateServiceWorker.mockClear();
  });

  it('没有新版本时不打扰用户', () => {
    renderPrompt();

    expect(screen.queryByTestId('update-prompt')).toBeNull();
  });

  it('有新版本时说清刷新会丢什么，而不是只说「有新版本」', () => {
    needRefresh.value = true;
    renderPrompt();

    // 填了一半的录入会丢，这一句必须有：否则用户会在录到一半时点刷新
    expect(screen.getByText(/填了一半还没提交的录入会丢失/)).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: '刷新' }));
    // 传 true 表示「立即激活新版本」，否则新 SW 会一直停在等待态
    expect(updateServiceWorker).toHaveBeenCalledWith(true);
  });

  it('注册后定时主动检查新版本——大屏整天开着，只靠加载时查一次永远等不到提示', () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval');
    renderPrompt();

    const update = vi.fn();
    onRegisteredSW.current?.('/sw.js', { update });

    expect(setIntervalSpy).toHaveBeenCalled();
    const [, delay] = setIntervalSpy.mock.calls.at(-1) ?? [];
    expect(delay).toBeGreaterThan(0);
  });
});
