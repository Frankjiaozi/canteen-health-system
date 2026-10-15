import { describe, expect, it } from 'vitest';
import type { ToolCallTrace } from '../types';
import { describeStreamEvent, parseStreamEvent } from './stream';

function trace(): ToolCallTrace {
  return {
    name: 'get_dashboard',
    label: '看板指标',
    arguments: { days: 7 },
    ok: true,
    summary: '看板指标：统计最近 7 天',
  };
}

describe('解析 SSE 块', () => {
  it('取出 data 行的 JSON', () => {
    expect(parseStreamEvent('data: {"type":"delta","text":"好"}')).toEqual({
      type: 'delta',
      text: '好',
    });
  });

  it('只认 data 行，注释与心跳忽略', () => {
    expect(parseStreamEvent(': ping')).toBeNull();
    expect(parseStreamEvent('event: done')).toBeNull();
    expect(parseStreamEvent('')).toBeNull();
  });

  it('坏 JSON 或结束标记当作没有这条，而不是抛出去把整段回答打断', () => {
    expect(parseStreamEvent('data: {半截')).toBeNull();
    expect(parseStreamEvent('data: [DONE]')).toBeNull();
    expect(parseStreamEvent('data: "just a string"')).toBeNull();
  });
});

describe('事件对界面意味着什么', () => {
  it('开聊给出对话 id', () => {
    expect(describeStreamEvent({ type: 'start', conversation_id: 'abc' })).toEqual({
      conversationId: 'abc',
    });
  });

  it('开始查工具只要一个名字就够显示「正在查……」', () => {
    expect(
      describeStreamEvent({ type: 'tool_start', name: 'get_dashboard', label: '看板指标' }),
    ).toEqual({ toolStart: { name: 'get_dashboard', label: '看板指标' } });
  });

  it('三种正常事件分别映射到痕迹、文字、最终结果', () => {
    expect(describeStreamEvent({ type: 'tool', trace: trace() }).tool).toMatchObject({
      label: '看板指标',
    });
    expect(describeStreamEvent({ type: 'delta', text: '嗯' })).toEqual({ delta: '嗯' });
    expect(
      describeStreamEvent({
        type: 'done',
        reply: {
          reply: '好了',
          tool_calls: [],
          conversation_id: 'abc',
          proposals: [],
          rounds: 1,
          truncated: false,
        },
      }).reply?.reply,
    ).toBe('好了');
  });

  it('错误事件带出原因，界面要原样转述', () => {
    expect(describeStreamEvent({ type: 'error', message: '连不上模型服务' }).error).toBe(
      '连不上模型服务',
    );
  });

  it('缺字段或认不出来的类型返回空，不猜', () => {
    expect(describeStreamEvent({ type: 'tool' })).toEqual({});
    expect(describeStreamEvent({ type: 'delta' })).toEqual({});
    expect(describeStreamEvent({ type: 'unknown-kind' })).toEqual({});
  });
});
