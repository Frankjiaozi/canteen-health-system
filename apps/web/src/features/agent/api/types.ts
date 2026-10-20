import type { components as Business } from '@canteen/api-client';
import type { components as Agent } from './schema';

// Agent OpenAPI 是对话协议真源；业务结果复用业务 OpenAPI。
// 服务端响应包含默认字段，Required 收敛为页面实际读取形态。
export type PlanParameters = Required<Agent['schemas']['PlanParameters-Output']>;
export type ToolTrace = Required<Agent['schemas']['ToolTrace']>;
export type ChatMessage = Omit<Agent['schemas']['ChatMessage'], 'trace'> & { trace: ToolTrace[] };
export type PlanVersion = Omit<
  Agent['schemas']['PlanVersion'],
  'parameters' | 'result' | 'publication' | 'undone' | 'readiness'
> & {
  parameters: PlanParameters;
  result: Business['schemas']['MenuPlanResponse'];
  publication: Business['schemas']['PublishPlanReceipt'] | null;
  undone?: Business['schemas']['UndoPlanReceipt'] | null;
  readiness?: Readiness | null;
};
export type ReviewIssue = Agent['schemas']['ReviewIssue'];
export type Review = Agent['schemas']['ReviewReport'];
export type PendingTask = Omit<Agent['schemas']['PendingTask'], 'parameters'> & {
  parameters: PlanParameters;
};
export type Conversation = Omit<
  Agent['schemas']['Conversation'],
  'messages' | 'plans' | 'review' | 'readiness' | 'pending_task'
> & {
  messages: ChatMessage[];
  plans: PlanVersion[];
  review: Review | null;
  readiness?: Readiness | null;
  pending_task?: PendingTask | null;
};
export type Readiness = Business['schemas']['PlanReadiness'];
export type AgentStatus = Agent['schemas']['AgentStatus'];
export type SessionSummary = Agent['schemas']['SessionSummary'];

export type DinerForecast = {
  on_date: string;
  meal_type: string;
  meal_type_label: string;
  predicted_diner_count: number | null;
  lower: number | null;
  upper: number | null;
  basis: string;
  basis_label: string;
  samples: { date: string; diner_count: number }[];
  calendar_note: string | null;
  note: string;
};

/** 对应 shared-contract.md 的 NDJSON 逐行事件，不包含推理文本。 */
export type AgentEvent =
  | { type: 'status'; message: string; mode: string }
  | { type: 'trace'; trace: ToolTrace }
  | { type: 'error'; message: string; code: string }
  | { type: 'done'; conversation: Conversation };

export type AgentDish = Pick<
  Business['schemas']['DishRead'],
  'id' | 'name' | 'category_label' | 'image_url'
>;
