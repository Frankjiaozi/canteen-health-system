import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type { AssistantStatus, ChatReply, ChatTurn } from '../types';

/** 助手是否可用、能做什么。界面上据此决定给不给输入框。 */
export async function fetchAssistantStatus(): Promise<AssistantStatus> {
  return unwrap(await api.GET('/api/v1/assistant/status'));
}

export async function sendAssistantMessage(
  message: string,
  history: ChatTurn[],
): Promise<ChatReply> {
  return unwrap(await api.POST('/api/v1/assistant/chat', { body: { message, history } }));
}
