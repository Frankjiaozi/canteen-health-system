import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import {
  cancelProposal,
  confirmProposal,
  fetchAssistantStatus,
  fetchConversation,
  fetchConversations,
  sendAssistantMessage,
} from '../api/assistantApi';

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

/**
 * 问助手一句话。

 * 会话不落库（阶段一），历史由调用方从本地消息列表里取——所以这里只用变更的返回值，
 * 不往查询缓存里塞。
 */
export function useAskAssistant() {
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (input: { question: string; conversationId: string | null }) =>
      sendAssistantMessage(input.question, input.conversationId),
    onError: (error: unknown) => {
      // 未接模型、连不上模型服务这类原因要原样显示，它决定了用户下一步该找谁
      void message.error(error instanceof ApiError ? error.message : '助手暂时不可用', 8);
    },
  });
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
    mutationFn: (input: { id: string; action: 'confirm' | 'cancel' }) =>
      input.action === 'confirm' ? confirmProposal(input.id) : cancelProposal(input.id),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: assistantKeys.conversations });
      await queryClient.invalidateQueries({ queryKey: ['ingredient'] });
      await queryClient.invalidateQueries({ queryKey: ['dish'] });
      await queryClient.invalidateQueries({ queryKey: ['collection'] });
      const ok = result.status === 'CONFIRMED';
      void message[ok || result.status === 'CANCELLED' ? 'success' : 'error'](
        ok
          ? `${result.title}：已执行`
          : result.status === 'CANCELLED'
            ? '已取消，什么也没有发生'
            : (result.error ?? '执行失败'),
        6,
      );
    },
    onError: (error: unknown) => {
      void message.error(error instanceof ApiError ? error.message : '操作失败，请稍后重试', 8);
    },
  });
}
