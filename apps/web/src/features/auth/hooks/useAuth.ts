import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchCurrentUser, login, logout } from '../api/authApi';
import type { AuthUser, LoginPayload } from '../types';

export const authKeys = {
  me: ['auth', 'me'] as const,
};

// 当前登录用户。
//
// 刻意用 TanStack Query 而不是 Zustand 存：登录态是服务端状态，
// 再往客户端 store 里放一份就多出一处需要手工保持同步的副本。
// Zustand 留给真正只存在于客户端的状态（离线队列等）。
export function useCurrentUser() {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: fetchCurrentUser,
    // 401 是「未登录」的正常结果，重试没有意义，反而会拖慢跳转
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LoginPayload) => login(payload),
    onSuccess: (user: AuthUser) => {
      queryClient.setQueryData(authKeys.me, user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.setQueryData(authKeys.me, null);
      queryClient.clear();
    },
  });
}
