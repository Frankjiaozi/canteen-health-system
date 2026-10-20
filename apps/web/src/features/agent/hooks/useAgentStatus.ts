import { useQuery } from '@tanstack/react-query';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { agentApi } from '../api/client';

export function useAgentStatus() {
  const { data: user } = useCurrentUser();
  return useQuery({
    queryKey: ['agent', 'status', user?.id],
    queryFn: agentApi.status,
    retry: false,
  });
}
