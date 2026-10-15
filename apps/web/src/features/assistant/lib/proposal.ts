/**
 * 方案卡片要展示什么。

 * 两份方案的数据形状不一样（新增食材是「字段 → 值」，新增菜品还带配方行），
 * 所以这里把 `preview` 归一成三种块：键值、表格、条目。卡片只负责画，
 * 判断在纯函数里，便于单测——确认卡片上写错一个字，用户就会按错的参数确认。
 */

export interface KeyValueRow {
  label: string;
  value: string;
}

export type PreviewBlock =
  | { kind: 'kv'; title: string | null; rows: KeyValueRow[] }
  | { kind: 'table'; title: string; header: string[]; rows: string[][] }
  | { kind: 'hints'; title: string; items: string[] };

function asText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.length > 0 ? value.join('、') : '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function isKeyValueMap(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isTableRows(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.length > 0 && value.every((item) => isKeyValueMap(item));
}

export function toPreviewBlocks(preview: Record<string, unknown>): PreviewBlock[] {
  const blocks: PreviewBlock[] = [];
  const fieldBlocks: KeyValueRow[] = [];

  for (const [key, value] of Object.entries(preview)) {
    if (key === '提示') continue;
    if (key === '动作') continue;
    if (isTableRows(value)) {
      const header = Object.keys(value[0]);
      blocks.push({
        kind: 'table',
        title: key,
        header,
        rows: value.map((row) => header.map((column) => asText(row[column]))),
      });
      continue;
    }
    if (isKeyValueMap(value)) {
      for (const [innerKey, innerValue] of Object.entries(value)) {
        fieldBlocks.push({ label: innerKey, value: asText(innerValue) });
      }
      continue;
    }
    fieldBlocks.push({ label: key, value: asText(value) });
  }

  if (fieldBlocks.length > 0) {
    blocks.unshift({ kind: 'kv', title: null, rows: fieldBlocks });
  }

  const hints = preview['提示'];
  if (Array.isArray(hints) && hints.length > 0) {
    blocks.push({ kind: 'hints', title: '要注意', items: hints.map(asText) });
  }
  return blocks;
}

/** 方案的状态说法。待确认要显眼，已执行要能一眼看出确实发生了。 */
export function describeProposalStatus(
  status: string,
  statusLabel: string,
): {
  text: string;
  tone: 'pending' | 'ok' | 'muted' | 'bad';
} {
  if (status === 'PENDING') return { text: statusLabel, tone: 'pending' };
  if (status === 'CONFIRMED') return { text: statusLabel, tone: 'ok' };
  if (status === 'FAILED') return { text: statusLabel, tone: 'bad' };
  return { text: statusLabel, tone: 'muted' };
}
