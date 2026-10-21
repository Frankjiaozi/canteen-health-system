import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AgentPage } from './AgentPage';
import { agentApi, sendMessage } from './api/client';
import { AgentHeaderTitle } from './components/AgentHeaderTitle';
import type { Conversation, PlanParameters, PlanVersion } from './api/types';

vi.mock('@/features/auth/hooks/useAuth', () => ({
  useCurrentUser: () => ({ data: { id: 'owner' } }),
}));
vi.mock('./api/client', () => ({
  agentApi: {
    status: vi.fn(),
    sessions: vi.fn(),
    dishes: vi.fn(),
    dinerForecast: vi.fn(),
    session: vi.fn(),
    create: vi.fn(),
    publish: vi.fn(),
  },
  sendMessage: vi.fn(),
}));
vi.mock('./components/TaskPanel', () => ({
  TaskPanel: ({ parameters, onNew }: { parameters: PlanParameters; onNew: () => void }) => (
    <>
      <output data-testid="parameters">{JSON.stringify(parameters)}</output>
      <button onClick={onNew}>新建测试任务</button>
    </>
  ),
}));
vi.mock('./components/ConversationView', () => ({
  ConversationView: ({ onSend }: { onSend: (text: string) => void }) => (
    <button onClick={() => onSend('按当前条件安排菜单')}>发送测试任务</button>
  ),
}));
vi.mock('./components/ResultPanel', () => ({ ResultPanel: () => null }));

const parameters: PlanParameters = {
  on_date: '2026-10-20',
  meal_type: 'DINNER',
  diner_count: 1000,
  budget_per_person: '12',
  excluded_dish_ids: ['excluded-dish'],
};
const emptyDinerForecast = {
  on_date: '2026-10-20',
  meal_type: 'LUNCH',
  meal_type_label: '午餐',
  predicted_diner_count: null,
  lower: null,
  upper: null,
  basis: 'UNAVAILABLE',
  basis_label: '历史不足',
  samples: [],
  calendar_note: null,
  note: '',
};
const empty: Conversation = {
  id: 'fresh',
  title: '新任务',
  created_at: '',
  updated_at: '',
  messages: [],
  plans: [],
  review: null,
};
const existing: Conversation = {
  ...empty,
  id: 'old',
  plans: [
    {
      revision: 1,
      created_at: '',
      parameters,
      publication: null,
      data_notice: '',
      result: {},
    } as PlanVersion,
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(agentApi.status).mockResolvedValue({
    mode: 'rules',
    model_name: null,
    data_notice: '合成数据',
    can_plan: true,
    capabilities: [],
  });
  vi.mocked(agentApi.sessions).mockResolvedValue([]);
  vi.mocked(agentApi.dishes).mockResolvedValue([]);
  vi.mocked(agentApi.dinerForecast).mockResolvedValue(emptyDinerForecast);
  vi.mocked(agentApi.session).mockImplementation(async (id) => (id === 'old' ? existing : empty));
  vi.mocked(agentApi.create).mockResolvedValue(empty);
  vi.mocked(sendMessage).mockResolvedValue(empty);
});

it('处理中的任务不会提前显示完成，生成方案后明确等待确认', async () => {
  let complete!: (value: Conversation) => void;
  vi.mocked(sendMessage).mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App>
        <MemoryRouter initialEntries={['/admin/agent']}>
          <AgentPage />
        </MemoryRouter>
      </App>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.getByRole('status', { name: '任务进度' })).toHaveTextContent('可以开始'),
  );
  fireEvent.click(screen.getByRole('button', { name: '发送测试任务' }));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: '任务进度' })).toHaveTextContent('正在处理'),
  );
  expect(screen.getByRole('status', { name: '任务进度' })).not.toHaveTextContent('已完成');
  await waitFor(() => expect(complete).toBeTypeOf('function'));
  await act(async () => complete(existing));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: '任务进度' })).toHaveTextContent('等待确认'),
  );
  client.clear();
});

it('服务连接失败时显示不可用和重试提示', async () => {
  vi.mocked(agentApi.status).mockRejectedValue(new Error('连接失败'));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App>
        <MemoryRouter initialEntries={['/admin/agent']}>
          <AgentPage />
        </MemoryRouter>
      </App>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.getByRole('status', { name: '任务进度' })).toHaveTextContent('暂不可用'),
  );
  expect(screen.getByRole('button', { name: /^重\s*试$/ })).toBeInTheDocument();
  client.clear();
});

it('新建任务不会因路由过渡重新带入旧会话的餐次、人数、预算和排除条件', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App>
        <MemoryRouter initialEntries={['/admin/agent?session=old']}>
          <AgentPage />
        </MemoryRouter>
      </App>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.getByTestId('parameters').textContent).toContain('excluded-dish'),
  );
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '新建测试任务' })));
  const current = JSON.parse(screen.getByTestId('parameters').textContent!);
  expect(current).toMatchObject({
    meal_type: 'LUNCH',
    diner_count: null,
    budget_per_person: '8',
    excluded_dish_ids: [],
  });
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '发送测试任务' })));
  await waitFor(() => expect(sendMessage).toHaveBeenCalled());
  expect(vi.mocked(sendMessage).mock.calls[0][2]).toMatchObject({
    diner_count: null,
    excluded_dish_ids: [],
  });
  client.clear();
});

it('模型接入状态收进顶部标题栏，数据来源提示不再占据工作区上方', async () => {
  vi.mocked(agentApi.status).mockResolvedValue({
    mode: 'model',
    model_name: 'deepseek-v4-pro',
    data_notice: '数据来源尚未核实，仅用于功能验证。',
    can_plan: true,
    capabilities: [],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App>
        <MemoryRouter initialEntries={['/admin/agent']}>
          <AgentHeaderTitle />
          <AgentPage />
        </MemoryRouter>
      </App>
    </QueryClientProvider>,
  );
  expect(await screen.findByText('已接入 DeepSeek V4 Pro')).toBeInTheDocument();
  expect(screen.getAllByRole('heading', { name: '知味膳食助手' })).toHaveLength(1);
  expect(screen.queryByText('数据来源尚未核实，仅用于功能验证。')).not.toBeInTheDocument();
  client.clear();
});

it('预计人次为空时自动填入系统预测人数', async () => {
  vi.mocked(agentApi.dinerForecast).mockResolvedValue({
    on_date: '2026-10-20',
    meal_type: 'LUNCH',
    meal_type_label: '午餐',
    predicted_diner_count: 920,
    lower: 840,
    upper: 1030,
    basis: 'SAME_WEEKDAY',
    basis_label: '同星期几中位数',
    samples: [],
    calendar_note: null,
    note: '',
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App>
        <MemoryRouter initialEntries={['/admin/agent']}>
          <AgentPage />
        </MemoryRouter>
      </App>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.getByTestId('parameters').textContent).toContain('"diner_count":920'),
  );
  client.clear();
});
