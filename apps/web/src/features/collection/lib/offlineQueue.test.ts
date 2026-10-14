import { describe, expect, it } from 'vitest';
import {
  describeEntry,
  enqueue,
  entryId,
  markFailed,
  remove,
  shouldQueue,
  type QueuedEntry,
} from './offlineQueue';
import type { DailyLogWrite } from '../types';

const payload = (dinerCount: number): DailyLogWrite => ({
  meal_type: 'LUNCH',
  diner_count: dinerCount,
  oil_total_g: '900',
  salt_total_g: '300',
  sugar_total_g: '120',
  leftover_weight_g: null,
  note: null,
  anomaly_flags: [],
  dishes: [{ dish_id: 'd1', servings_produced: '140', is_substituted: false }],
});

const push = (
  entries: QueuedEntry[],
  onDate: string,
  dinerCount: number,
  now = '2026-10-14T10:00:00.000Z',
) => enqueue(entries, { onDate, mealType: 'LUNCH', payload: payload(dinerCount), now });

describe('入队', () => {
  it('新记录排在队首，先补交最近录的那一餐', () => {
    const first = push([], '2026-10-15', 200).entries;
    const second = push(first, '2026-10-16', 220).entries;

    expect(second.map((entry) => entry.onDate)).toEqual(['2026-10-16', '2026-10-15']);
  });

  it('同一 (日期, 餐次) 只留一条，并把被覆盖的那条交回来', () => {
    const first = push([], '2026-10-15', 200).entries;

    const { entries, replaced } = push(first, '2026-10-15', 260);

    expect(entries).toHaveLength(1);
    expect(entries[0].payload.diner_count).toBe(260);
    // 覆盖必须让界面说得出「覆盖了哪一条」，静默丢弃录入是最不能接受的成功
    expect(replaced?.payload.diner_count).toBe(200);
  });

  it('不同餐次各留一条', () => {
    const first = push([], '2026-10-15', 200).entries;
    const { entries } = enqueue(first, {
      onDate: '2026-10-15',
      mealType: 'DINNER',
      payload: payload(80),
      now: '2026-10-14T11:00:00.000Z',
    });

    expect(entries).toHaveLength(2);
    expect(entryId('2026-10-15', 'LUNCH')).not.toBe(entryId('2026-10-15', 'DINNER'));
  });
});

describe('失败与移除', () => {
  it('记下失败原因并累加尝试次数', () => {
    const entries = push([], '2026-10-15', 200).entries;

    const failed = markFailed(entries, entries[0].id, '不能连接服务器');

    expect(failed[0].lastError).toBe('不能连接服务器');
    expect(failed[0].attempts).toBe(1);
  });

  it('只影响命中的那一条', () => {
    const entries = push(push([], '2026-10-15', 200).entries, '2026-10-16', 210).entries;

    const failed = markFailed(entries, entries[1].id, '失败');

    expect(failed.find((entry) => entry.onDate === '2026-10-16')?.lastError).toBeNull();
  });

  it('放弃后不再出现', () => {
    const entries = push([], '2026-10-15', 200).entries;

    expect(remove(entries, entries[0].id)).toHaveLength(0);
    expect(remove(entries, 'not-there')).toHaveLength(1);
  });
});

describe('什么情况才进队列', () => {
  it('网络不通与服务端故障才排队——它们过一会儿重试就有意义', () => {
    expect(shouldQueue(0)).toBe(true);
    expect(shouldQueue(500)).toBe(true);
    expect(shouldQueue(503)).toBe(true);
  });

  it('服务端明确拒绝的不排队——那说明数据本身有问题，排进去只会次次被拒', () => {
    expect(shouldQueue(422)).toBe(false);
    expect(shouldQueue(400)).toBe(false);
    expect(shouldQueue(401)).toBe(false);
    expect(shouldQueue(403)).toBe(false);
    expect(shouldQueue(404)).toBe(false);
  });
});

describe('状态文案', () => {
  it('没试过、试过、失败过各说各的', () => {
    const [entry] = push([], '2026-10-15', 200).entries;

    expect(describeEntry(entry)).toBe('等待同步');
    expect(describeEntry(markFailed([entry], entry.id, '服务端 500')[0])).toBe(
      '上次同步失败：服务端 500',
    );
  });
});
