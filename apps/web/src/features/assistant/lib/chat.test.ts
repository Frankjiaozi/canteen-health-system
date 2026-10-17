import { describe, expect, it } from 'vitest';
import type { ToolCallTrace } from '../types';
import { TOKEN_NOTICE_THRESHOLD, describeTokens, describeToolRun, nextMessageId } from './chat';
import { describeProposalStatus, toPreviewBlocks } from './proposal';

function trace(overrides: Partial<ToolCallTrace> = {}): ToolCallTrace {
  return {
    name: 'search_ingredients',
    label: '查食材库',
    arguments: { keyword: '西兰花' },
    ok: true,
    summary: '查食材库：返回 1 条（共 1 条）',
    ...overrides,
  };
}

describe('用量说法', () => {
  it('小额不显示：每句回答后面挂一串数字只会变噪音', () => {
    expect(describeTokens(undefined)).toBeNull();
    expect(describeTokens(TOKEN_NOTICE_THRESHOLD - 1)).toBeNull();
  });

  it('上千按 k 说，够大才说', () => {
    expect(describeTokens(2400)).toBe('这一轮约用 2.4k token');
    expect(describeTokens(TOKEN_NOTICE_THRESHOLD)).toBe('这一轮约用 2.0k token');
  });
});

describe('消息 id', () => {
  it('同一个序号也各不相同，React 列表不会串', () => {
    const first = nextMessageId(1);
    const second = nextMessageId(1);

    expect(first).not.toBe(second);
    expect(first.startsWith('m-1-')).toBe(true);
  });
});

describe('工具调用的说法', () => {
  it('查到时给结果摘要', () => {
    expect(describeToolRun(trace())).toBe('查食材库：返回 1 条（共 1 条）');
  });

  it('没查到时要标出来，不能看着像查到了', () => {
    const text = describeToolRun(
      trace({ ok: false, label: '查菜品配方', summary: '菜品库里没有找到「不存在的菜」' }),
    );

    expect(text).toContain('没查到');
    expect(text).toContain('没有找到');
  });
});

describe('方案卡片怎么摆', () => {
  it('嵌套的字段拍平成键值，别把 JSON 直接甩给用户看', () => {
    const blocks = toPreviewBlocks({
      将新增: { 名称: '西兰花', 单价_元每公斤市品: '6.0', 备注: null },
      提示: [],
      动作: '在食材库新增一条食材',
    });

    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ kind: 'kv', title: null });
    if (blocks[0].kind === 'kv') {
      expect(blocks[0].rows).toEqual([
        { label: '名称', value: '西兰花' },
        { label: '单价_元每公斤市品', value: '6.0' },
        { label: '备注', value: '—' },
      ]);
    }
  });

  it('配方行做成表格：列就是字段名，空值写成 —', () => {
    const blocks = toPreviewBlocks({
      配方食材: [
        { 食材: '鸡胸肉', 单份用量_克: '70', 库里匹配: null },
        { 食材: '黄瓜', 单份用量_克: '30', 库里匹配: '黄瓜' },
      ],
      提示: ['食材库里没有「花生仁」，先建这条食材再录配方'],
    });

    const table = blocks.find((block) => block.kind === 'table');
    expect(table).toMatchObject({ title: '配方食材', header: ['食材', '单份用量_克', '库里匹配'] });
    if (table?.kind === 'table') {
      expect(table.rows[0]).toEqual(['鸡胸肉', '70', '—']);
    }
    const hints = blocks.find((block) => block.kind === 'hints');
    expect(hints).toMatchObject({ kind: 'hints', title: '要注意' });
  });

  it('没有提示时不摆一个空标题', () => {
    const blocks = toPreviewBlocks({ 将新增: { 名称: 'x' } });

    expect(blocks.some((block) => block.kind === 'hints')).toBe(false);
  });
});

describe('方案状态的说法', () => {
  it('四种状态各有语气，待确认与失败要能一眼看出来', () => {
    expect(describeProposalStatus('PENDING', '待确认').tone).toBe('pending');
    expect(describeProposalStatus('CONFIRMED', '已确认并执行').tone).toBe('ok');
    expect(describeProposalStatus('FAILED', '执行失败').tone).toBe('bad');
    expect(describeProposalStatus('CANCELLED', '已取消').tone).toBe('muted');
  });
});
