import { toApiError } from '@/shared/api/errors';
import type {
  AgentDish,
  AgentEvent,
  AgentStatus,
  Conversation,
  PlanParameters,
  SessionSummary,
} from './types';

const BASE = '/agent-api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      ...init,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new Error('无法连接膳食助手，请确认 Agent 服务已启动');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}

export const agentApi = {
  status: () => request<AgentStatus>('/status'),
  dishes: async () => (await request<{ items: AgentDish[] }>('/dishes')).items,
  sessions: () => request<SessionSummary[]>('/sessions'),
  create: () => request<Conversation>('/sessions', { method: 'POST' }),
  session: (id: string) => request<Conversation>(`/sessions/${encodeURIComponent(id)}`),
  publish: (id: string, revision: number) =>
    request<Conversation>(`/sessions/${encodeURIComponent(id)}/publish`, {
      method: 'POST',
      body: JSON.stringify({ revision }),
    }),
};

/** 网络分块与 JSON 行无关；缓冲跨块 UTF-8 和半行，不能逐块直接 JSON.parse。 */
export async function readEvents(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: AgentEvent) => void,
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const parse = (line: string) => {
    if (!line.trim()) return;
    const value: unknown = JSON.parse(line);
    if (typeof value !== 'object' || value === null || !('type' in value)) {
      throw new Error('助手返回了无法识别的消息，请刷新对话');
    }
    if (['status', 'trace', 'error', 'done'].includes(String(value.type)))
      onEvent(value as AgentEvent);
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 4_000_000) throw new Error('助手返回内容过大，请缩小任务范围');
      let index: number;
      while ((index = buffer.indexOf('\n')) >= 0) {
        parse(buffer.slice(0, index));
        buffer = buffer.slice(index + 1);
      }
      if (done) break;
    }
    parse(buffer);
  } finally {
    reader.releaseLock();
  }
}

export async function sendMessage(
  id: string,
  content: string,
  parameters: PlanParameters,
  revision: number,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<Conversation> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/sessions/${encodeURIComponent(id)}/messages`, {
      method: 'POST',
      credentials: 'include',
      signal,
      headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
      body: JSON.stringify({
        content,
        parameters,
        expected_revision: revision,
        request_id: crypto.randomUUID(),
      }),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('无法连接膳食助手，请检查服务和网络', { cause: error });
  }
  if (!response.ok) throw toApiError(response.status, await response.json().catch(() => null));
  if (!response.body) throw new Error('浏览器无法读取助手的处理过程');
  let result: Conversation | null = null;
  await readEvents(response.body, (event) => {
    if (event.type === 'done') result = event.conversation;
    onEvent(event);
  });
  if (!result) throw new Error('连接提前中断，请刷新对话检查已经完成的结果');
  return result;
}
