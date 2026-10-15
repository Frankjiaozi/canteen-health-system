import { describe, expect, it } from 'vitest';
import type { ToolCallTrace } from '../types';
import { HISTORY_LIMIT, buildHistory, describeToolRun, type ChatMessage } from './chat';

function message(
  role: 'user' | 'assistant',
  content: string,
  extra: Partial<ChatMessage> = {},
): ChatMessage {
  return { id: `${role}-${content}`, role, content, ...extra };
}

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

describe('送给模型的历史', () => {
  it('只带用户与助手的文字，工具调用不回传——上一轮上下文里已经有了', () => {
    const history = buildHistory([
      message('user', '今天吃什么？'),
      message('assistant', '今天有米饭和番茄炒蛋。', { toolCalls: [trace()] }),
    ]);

    expect(history).toEqual([
      { role: 'user', content: '今天吃什么？' },
      { role: 'assistant', content: '今天有米饭和番茄炒蛋。' },
    ]);
  });

  it('只留最近几轮，避免每问一次都背着越来越长的历史', () => {
    const many = Array.from({ length: HISTORY_LIMIT + 6 }, (_, index) =>
      message(index % 2 === 0 ? 'user' : 'assistant', `第 ${index} 句`),
    );

    const history = buildHistory(many);

    expect(history).toHaveLength(HISTORY_LIMIT);
    expect(history.at(-1)?.content).toBe(`第 ${HISTORY_LIMIT + 5} 句`);
  });

  it('空内容不进历史', () => {
    expect(buildHistory([message('user', '   ')])).toEqual([]);
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
