import { afterEach, describe, expect, it, vi } from 'vitest';
import { readEvents, sendMessage } from './client';
import type { AgentEvent } from './types';

afterEach(() => vi.unstubAllGlobals());

function fragmented(text: string, width: number) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < bytes.length; i += width) controller.enqueue(bytes.slice(i, i + width));
      controller.close();
    },
  });
}

describe('助手分步响应', () => {
  it('跨网络分块和汉字字节边界仍能正确读取每行', async () => {
    const values: AgentEvent[] = [];
    const text =
      '\n' +
      JSON.stringify({ type: 'status', message: '知味正在核查', mode: 'rules' }) +
      '\n' +
      JSON.stringify({ type: 'error', message: '菜品不足', code: 'business_rule_violated' });
    await readEvents(fragmented(text, 2), (value) => values.push(value));
    expect(values).toEqual([
      { type: 'status', message: '知味正在核查', mode: 'rules' },
      { type: 'error', message: '菜品不足', code: 'business_rule_violated' },
    ]);
  });
  it('损坏协议明确失败，不悄悄忽略', async () => {
    await expect(readEvents(fragmented('{broken}\n', 1), () => {})).rejects.toThrow();
  });
  it('流提前结束时不能宣称任务完成', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(fragmented('{"type":"status","message":"处理中","mode":"rules"}\n', 8), {
          status: 200,
        }),
      ),
    );
    await expect(
      sendMessage(
        'session',
        '安排菜单',
        {
          on_date: '2026-10-17',
          meal_type: 'LUNCH',
          diner_count: 800,
          budget_per_person: '8',
          excluded_dish_ids: [],
        },
        0,
        () => {},
      ),
    ).rejects.toThrow('连接提前中断');
  });
  it('权限错误保留服务端说明', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ code: 'unauthorized', message: '登录已过期', details: null }),
            { status: 401 },
          ),
        ),
    );
    await expect(
      sendMessage(
        'session',
        '安排菜单',
        {
          on_date: '2026-10-17',
          meal_type: 'LUNCH',
          diner_count: 800,
          budget_per_person: '8',
          excluded_dish_ids: [],
        },
        0,
        () => {},
      ),
    ).rejects.toMatchObject({ status: 401, message: '登录已过期' });
  });
});
