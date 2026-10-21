import { describe, expect, it } from 'vitest';
import { calendarRows } from './calendar';

describe('前端日历补齐', () => {
  it('跨月与闰日正确，原始接口数据保持不变', () => {
    const point = { date: '2024-02-29', value: 0 };
    const response = { start: '2024-02-28', end: '2024-03-01', points: [point] };
    const rows = calendarRows(response);
    expect(rows.map((row) => row.date)).toEqual(['2024-02-28', '2024-02-29', '2024-03-01']);
    expect(rows.map((row) => row.point)).toEqual([null, point, null]);
    expect(response.points).toEqual([point]);
  });
  it('跨年和全空日期区间仍显示完整日历', () => {
    expect(
      calendarRows({ start: '2025-12-30', end: '2026-01-02', points: [] }).map((row) => row.date),
    ).toEqual(['2025-12-30', '2025-12-31', '2026-01-01', '2026-01-02']);
  });
});
