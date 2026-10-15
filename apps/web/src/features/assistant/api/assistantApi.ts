import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import type {
  AssistantStatus,
  ChatReply,
  ConversationDetail,
  ConversationSummary,
  ProposalRead,
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
