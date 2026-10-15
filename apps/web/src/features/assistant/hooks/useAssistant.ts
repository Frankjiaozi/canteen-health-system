import { useMutation, useQuery } from '@tanstack/react-query';
import { App } from 'antd';
import { ApiError } from '@/shared/api/errors';
import { fetchAssistantStatus, sendAssistantMessage } from '../api/assistantApi';
import type { ChatTurn } from '../types';

export const assistantKeys = {
  status: ['assistant', 'status'] as const,
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
    mutationFn: (input: { question: string; history: ChatTurn[] }) =>
      sendAssistantMessage(input.question, input.history),
    onError: (error: unknown) => {
      // 未接模型、连不上模型服务这类原因要原样显示，它决定了用户下一步该找谁
      void message.error(error instanceof ApiError ? error.message : '助手暂时不可用', 8);
    },
  });
}
