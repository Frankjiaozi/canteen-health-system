import type { ChatReply, ToolCallTrace } from '../types';

/** 后端推来的一个事件。字段按 type 区分，认不出来的直接忽略。 */
export interface StreamEvent {
  type: string;
  text?: string;
  name?: string;
  label?: string;
  trace?: ToolCallTrace;
  reply?: ChatReply;
  message?: string;
  conversation_id?: string;
}

/** 一条事件对界面意味着什么。 */
export interface StreamEffect {
  conversationId?: string;
  toolStart?: { name: string; label: string };
  tool?: ToolCallTrace;
  delta?: string;
  reply?: ChatReply;
  error?: string;
}

/**
 * 从 SSE 的一个块里取出事件。

 * 只认 `data:` 行——注释、心跳、空行都不是事件。JSON 坏了就当没这条，
 * 一条坏消息不该让整段回答断掉（后端也是同样态度）。
 */
export function parseStreamEvent(raw: string): StreamEvent | null {
  const line = raw
    .split('\n')
    .map((item) => item.trim())
    .find((item) => item.startsWith('data:'));
  if (!line) return null;
  const payload = line.slice('data:'.length).trim();
  if (!payload || payload === '[DONE]') return null;
  try {
    const parsed: unknown = JSON.parse(payload);
    if (typeof parsed !== 'object' || parsed === null) return null;
    return parsed as StreamEvent;
  } catch {
    return null;
  }
}

export function describeStreamEvent(event: StreamEvent): StreamEffect {
  switch (event.type) {
    case 'start':
      return event.conversation_id ? { conversationId: event.conversation_id } : {};
    case 'tool_start':
      return { toolStart: { name: event.name ?? '', label: event.label ?? event.name ?? '' } };
    case 'tool':
      return event.trace ? { tool: event.trace } : {};
    case 'delta':
      return event.text ? { delta: event.text } : {};
    case 'done':
      return event.reply ? { reply: event.reply } : {};
    case 'error':
      return { error: event.message ?? '助手出错了' };
    default:
      return {};
  }
}
