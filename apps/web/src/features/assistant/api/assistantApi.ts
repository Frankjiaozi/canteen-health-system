import { api } from '@/shared/api/client';
import { toApiError } from '@/shared/api/errors';
import { unwrap } from '@/shared/api/result';
import { describeStreamEvent, parseStreamEvent } from '../lib/stream';
import type {
  AssistantStatus,
  ChatReply,
  ConversationDetail,
  ConversationSummary,
  ProposalRead,
  ToolCallTrace,
} from '../types';

/** 助手是否可用、能做什么。界面上据此决定给不给输入框。 */
export async function fetchAssistantStatus(): Promise<AssistantStatus> {
  return unwrap(await api.GET('/api/v1/assistant/status'));
}

export async function sendAssistantMessage(
  message: string,
  conversationId: string | null,
): Promise<ChatReply> {
  // 历史由服务端从库里读，这里只带「接着哪次对话问」
  return unwrap(
    await api.POST('/api/v1/assistant/chat', {
      body: { message, conversation_id: conversationId },
    }),
  );
}

/** 历史对话（审计视角：谁在哪个对话里让助手做了什么）。 */
export async function fetchConversations(limit = 20): Promise<ConversationSummary[]> {
  return unwrap(await api.GET('/api/v1/assistant/conversations', { params: { query: { limit } } }));
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  return unwrap(
    await api.GET('/api/v1/assistant/conversations/{conversation_id}', {
      params: { path: { conversation_id: id } },
    }),
  );
}

/** 确认执行助手提出的方案。这一步才会真的写库。 */
export async function confirmProposal(id: string): Promise<ProposalRead> {
  return unwrap(
    await api.POST('/api/v1/assistant/proposals/{proposal_id}/confirm', {
      params: { path: { proposal_id: id } },
    }),
  );
}

export async function cancelProposal(id: string): Promise<ProposalRead> {
  return unwrap(
    await api.POST('/api/v1/assistant/proposals/{proposal_id}/cancel', {
      params: { path: { proposal_id: id } },
    }),
  );
}

export interface StreamHandlers {
  onStart?: (conversationId: string) => void;
  onToolStart?: (name: string, label: string) => void;
  onTool?: (trace: ToolCallTrace) => void;
  onDelta?: (text: string) => void;
}

/**
 * 流式问一句。

 * 用 fetch 读 SSE 而不是 EventSource：EventSource 只支持 GET，而提问要带 JSON 体。
 * 协议很简单——每条消息以空行结尾、正文是 `data: {json}`，这里按空行切。
 */
export async function streamAssistantMessage(
  message: string,
  conversationId: string | null,
  handlers: StreamHandlers,
): Promise<ChatReply> {
  const response = await fetch('/api/v1/assistant/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin', // 登录态在 httpOnly Cookie 里
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!response.ok || !response.body) {
    throw toApiError(response.status, await response.json().catch(() => null));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: ChatReply | undefined;
  let failure: string | null = null;

  const consume = (raw: string) => {
    const event = parseStreamEvent(raw);
    if (!event) return;
    const effect = describeStreamEvent(event);
    if (effect.conversationId) handlers.onStart?.(effect.conversationId);
    if (effect.toolStart) handlers.onToolStart?.(effect.toolStart.name, effect.toolStart.label);
    if (effect.tool) handlers.onTool?.(effect.tool);
    if (effect.delta) handlers.onDelta?.(effect.delta);
    if (effect.reply) final = effect.reply;
    if (effect.error) failure = effect.error;
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      consume(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim()) consume(buffer);

  if (failure) throw toApiError(0, { code: 'assistant_failed', message: failure, details: null });
  if (!final) {
    throw toApiError(0, {
      code: 'assistant_no_result',
      message: '助手没有返回结果，请重试',
      details: null,
    });
  }
  return final;
}
