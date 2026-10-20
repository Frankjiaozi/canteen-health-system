import type { DailyLogWrite, MealType } from '../types';

/** 队列里一条待提交的采集单。 */
export interface QueuedEntry {
  /** 旧版记录没有归属；保留在本地但不能自动交给当前账号。 */
  ownerId?: string;
  /** 队列内唯一标识：同一 (日期, 餐次) 复用同一个 id，覆盖时不会留下两条 */
  id: string;
  onDate: string;
  mealType: MealType;
  payload: DailyLogWrite;
  /** 入队时间，用于展示与排序 */
  queuedAt: string;
  /** 上一次同步失败的原因；成功后不该留在这里 */
  lastError: string | null;
  attempts: number;
}

export function entryId(onDate: string, mealType: MealType, ownerId?: string): string {
  return `${ownerId ? `${ownerId}:` : ''}${onDate}:${mealType}`;
}

export interface EnqueueResult {
  entries: QueuedEntry[];
  /** 覆盖掉的旧条目；为空表示这是一条新记录 */
  replaced: QueuedEntry | null;
}

/**
 * 把一次提交放进队列。
 *
 * 同一 (日期, 餐次) 只保留一条：录入员改了数字再提交、或者断网期间反复点保存，
 * 队列里都不该堆出互相矛盾的版本。被覆盖的那条要返回给调用方，界面得说清覆盖了谁——
 * 静默丢弃用户的输入是最不能接受的一种「成功」。
 */
export function enqueue(
  entries: QueuedEntry[],
  input: {
    onDate: string;
    mealType: MealType;
    payload: DailyLogWrite;
    now: string;
    ownerId?: string;
  },
): EnqueueResult {
  const id = entryId(input.onDate, input.mealType, input.ownerId);
  const previous = entries.find((entry) => entry.id === id) ?? null;
  const rest = entries.filter((entry) => entry.id !== id);
  const next: QueuedEntry = {
    ownerId: input.ownerId,
    id,
    onDate: input.onDate,
    mealType: input.mealType,
    payload: input.payload,
    queuedAt: input.now,
    lastError: null,
    attempts: 0,
  };
  // 新入队的放最前面：同步时先补齐最近录的那一餐
  return { entries: [next, ...rest], replaced: previous };
}

export function markFailed(entries: QueuedEntry[], id: string, error: string): QueuedEntry[] {
  return entries.map((entry) =>
    entry.id === id ? { ...entry, lastError: error, attempts: entry.attempts + 1 } : entry,
  );
}

export function remove(entries: QueuedEntry[], id: string): QueuedEntry[] {
  return entries.filter((entry) => entry.id !== id);
}

/**
 * 判断一次失败该不该进队列。
 *
 * 只把**网络层**失败当作「离线」：服务端明确拒绝（4xx/5xx 且带业务错误体）说明
 * 这条数据本身有问题，排进队列只会让它每次同步都被拒，界面还得一直显示一条红记录。
 * 那种情况要当场告诉录入员改，而不是替他留着。
 */
export function shouldQueue(status: number): boolean {
  return status === 0 || status >= 500;
}

/** 界面上的一句话状态。 */
export function describeEntry(entry: QueuedEntry): string {
  if (entry.lastError === null) {
    return entry.attempts === 0 ? '等待同步' : '重试中';
  }
  return `上次同步失败：${entry.lastError}`;
}
