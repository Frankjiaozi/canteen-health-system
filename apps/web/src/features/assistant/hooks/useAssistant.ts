import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import {
  cancelProposal,
  confirmProposal,
  fetchAssistantStatus,
  fetchConversation,
  fetchConversations,
  revokeProposal,
  streamAssistantMessage,
} from '../api/assistantApi';
import type { ToolCallTrace } from '../types';

export const assistantKeys = {
  status: ['assistant', 'status'] as const,
  conversations: ['assistant', 'conversations'] as const,
  conversation: (id: string) => ['assistant', 'conversations', id] as const,
};

export function useAssistantStatus() {
  return useQuery({
    queryKey: assistantKeys.status,
    queryFn: fetchAssistantStatus,
    // 有没有接模型是部署时定的，运行期不会变；出错了也别反复重试
    staleTime: Infinity,
    retry: 1,
  });
}

export interface AskHandlers {
  onStart: (conversationId: string) => void;
  onToolStart: (label: string) => void;
  onTool: (trace: ToolCallTrace) => void;
  onDelta: (text: string) => void;
}

/**
 * 问助手一句话（流式）。

 * 不做成 TanStack Query 的 mutation：流式的价值就在于**过程可见**，
 * 而 mutation 只给最终结果。这里把增量通过回调交给调用方去拼。
 * 错误仍然统一提示——未接模型、连不上模型服务这类原因要原样显示。
 */
export function useAskAssistant() {
  const { message } = App.useApp();

  return {
    ask: async (question: string, conversationId: string | null, handlers: AskHandlers) => {
      try {
        return await streamAssistantMessage(question, conversationId, handlers);
      } catch (error) {
        void message.error(error instanceof ApiError ? error.message : '助手暂时不可用', 8);
        throw error;
      }
    },
  };
}

export function useConversations(enabled: boolean) {
  return useQuery({
    queryKey: assistantKeys.conversations,
    queryFn: () => fetchConversations(),
    // 打开抽屉、问完一轮之后才需要刷新，不必轮询
    enabled,
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: assistantKeys.conversation(id ?? ''),
    queryFn: () => fetchConversation(id as string),
    enabled: id !== null,
  });
}

/**
 * 确认或取消一条方案。

 * 确认会真的写库（新增食材/菜品），所以成功之后要把看板、食材库、菜品库的缓存一起作废——
 * 用户切到那些页面时看到的必须是更新后的数据。
 */
export function useDecideProposal() {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { id: string; action: 'confirm' | 'cancel' | 'revoke' }) =>
      input.action === 'confirm'
        ? confirmProposal(input.id)
        : input.action === 'cancel'
          ? cancelProposal(input.id)
          : revokeProposal(input.id),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: assistantKeys.conversations });
      await queryClient.invalidateQueries({ queryKey: ['ingredient'] });
      await queryClient.invalidateQueries({ queryKey: ['dish'] });
      await queryClient.invalidateQueries({ queryKey: ['collection'] });
      const ok = result.status === 'CONFIRMED';
      const done = ok || result.status === 'CANCELLED' || result.status === 'REVERTED';
      void message[done ? 'success' : 'error'](
        ok
          ? `${result.title}：已执行`
          : result.status === 'CANCELLED'
            ? '已取消，什么也没有发生'
            : result.status === 'REVERTED'
              ? `${result.title}：已撤回，数据改回原来的样子`
              : (result.error ?? '执行失败'),
        6,
      );
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '操作失败，请稍后重试', 8);
    },
  });
}
