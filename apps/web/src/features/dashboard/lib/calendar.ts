/** 只在展示层补齐接口 start/end 之间的日历，不补写台账或改变服务端计算结果。 */
export function calendarRows<T extends { date: string }>(response?: {
  start: string;
  end: string;
  points: T[];
}): { date: string; point: T | null }[] {
  if (!response) return [];
  const start = Date.parse(`${response.start}T00:00:00Z`);
  const end = Date.parse(`${response.end}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return [];
  const byDate = new Map(response.points.map((point) => [point.date, point]));
  const rows: { date: string; point: T | null }[] = [];
  for (let stamp = start; stamp <= end; stamp += 86_400_000) {
    const date = new Date(stamp).toISOString().slice(0, 10);
    rows.push({ date, point: byDate.get(date) ?? null });
  }
  return rows;
}
