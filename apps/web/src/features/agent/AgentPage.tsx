import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Skeleton } from 'antd';
import dayjs from 'dayjs';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { ApiError } from '@/shared/api/errors';
import { agentApi, sendMessage } from './api/client';
import type { Conversation, PlanParameters, PlanVersion, ToolTrace } from './api/types';
import { ConversationView } from './components/ConversationView';
import { ResultPanel } from './components/ResultPanel';
import { TaskPanel } from './components/TaskPanel';
import { useAgentStatus } from './hooks/useAgentStatus';
import './agent.css';

const initialParameters = (): PlanParameters => ({
  on_date: dayjs().add(1, 'day').format('YYYY-MM-DD'),
  meal_type: 'LUNCH',
  diner_count: null,
  budget_per_person: '8',
  excluded_dish_ids: [],
});
const errorText = (error: unknown) => (error instanceof Error ? error.message : '操作失败，请重试');

export function AgentPage() {
  const { modal, message } = App.useApp();
  const client = useQueryClient();
  const { data: user } = useCurrentUser();
  const [search, setSearch] = useSearchParams();
  const sessionId = search.get('session');
  const [parameters, setParameters] = useState<PlanParameters>(initialParameters);
  const [loadedSession, setLoadedSession] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [pendingContent, setPendingContent] = useState('');
  const [trace, setTrace] = useState<ToolTrace[]>([]);
  const [statusText, setStatusText] = useState('');
  const [runError, setRunError] = useState('');
  const [revision, setRevision] = useState<number | null>(null);
  const [resultTab, setResultTab] = useState('plan');
  const [mobilePanel, setMobilePanel] = useState<'chat' | 'result' | 'task'>('chat');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const key = (id: string) => ['agent', 'session', user?.id, id] as const;
  const status = useAgentStatus();
  const sessions = useQuery({
    queryKey: ['agent', 'sessions', user?.id],
    queryFn: agentApi.sessions,
    retry: false,
  });
  const dishes = useQuery({
    queryKey: ['agent', 'dishes', user?.id],
    queryFn: agentApi.dishes,
    retry: false,
  });
  const canPlan = status.data?.can_plan ?? false;
  const current = useQuery({
    queryKey: key(sessionId ?? ''),
    queryFn: () => agentApi.session(sessionId!),
    enabled: !!sessionId,
    retry: false,
  });
  const conversation = sessionId && current.data?.id === sessionId ? current.data : undefined;
  // 切换会话时恢复该会话最近方案的条件，避免把上个任务的排除条件带过来。
  if (conversation && loadedSession !== conversation.id) {
    setLoadedSession(conversation.id);
    setParameters(
      conversation.pending_task?.parameters ??
        conversation.plans.at(-1)?.parameters ??
        initialParameters(),
    );
    setRevision(null);
  }
  const pendingDinerQuestion =
    conversation?.pending_task?.field === 'diner_count' ||
    (conversation?.pending_task?.questions?.some((question) => question.field === 'diner_count') ??
      false);
  const dinerForecast = useQuery({
    queryKey: ['agent', 'diner-forecast', user?.id, parameters.on_date, parameters.meal_type],
    queryFn: () => agentApi.dinerForecast(parameters.on_date, parameters.meal_type),
    enabled: canPlan && parameters.diner_count == null && !pendingDinerQuestion,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  // 不把预测值写回 state：它是「当前条件下的默认值」，条件一变就应重新算。
  // 展示与发送都用这份合成参数，用户一改预算/菜品，TaskPanel 会把它固化成新条件。
  const effectiveParameters: PlanParameters = {
    ...parameters,
    diner_count:
      parameters.diner_count ??
      (pendingDinerQuestion ? null : (dinerForecast.data?.predicted_diner_count ?? null)),
  };

  const updateConversation = (value: Conversation) => {
    client.setQueryData(key(value.id), value);
    void client.invalidateQueries({ queryKey: ['agent', 'sessions'] });
    setSearch({ session: value.id }, { replace: true });
  };
  const run = useMutation({
    mutationFn: async (text: string) => {
      setPendingContent(text);
      setTrace([]);
      setRunError('');
      setStatusText('正在连接业务服务');
      const currentConversation = conversation ?? (await agentApi.create());
      if (!conversation) {
        setLoadedSession(currentConversation.id);
        updateConversation(currentConversation);
      }
      controller.current = new AbortController();
      return sendMessage(
        currentConversation.id,
        text,
        effectiveParameters,
        currentConversation.plans.length,
        (event) => {
          if (event.type === 'status') setStatusText(event.message);
          if (event.type === 'error') {
            setRunError(event.message);
            if (event.code === 'unauthorized')
              void client.invalidateQueries({ queryKey: ['auth', 'me'] });
          }
          if (event.type === 'trace') {
            if (event.trace.status === 'success' && event.trace.tool === 'review_operations')
              setResultTab('review');
            if (event.trace.status === 'success' && event.trace.tool === 'check_data_readiness')
              setResultTab('readiness');
            if (event.trace.status === 'success' && event.trace.tool === 'generate_menu_plan')
              setResultTab('plan');
            setStatusText(event.trace.label);
            setTrace((previous) => {
              const exists = previous.some((step) => step.id === event.trace.id);
              return exists
                ? previous.map((step) => (step.id === event.trace.id ? event.trace : step))
                : [...previous, event.trace];
            });
          }
        },
        controller.current.signal,
      );
    },
    onSuccess: (value) => {
      updateConversation(value);
      setInput('');
      setRevision(null);
      if (value.pending_task) setParameters(value.pending_task.parameters);
      else if (value.plans.length) setParameters(value.plans.at(-1)!.parameters);
    },
    onError: (error) => {
      setRunError(errorText(error));
      if (error instanceof ApiError && error.isUnauthorized)
        void client.invalidateQueries({ queryKey: ['auth', 'me'] });
      void client.invalidateQueries({ queryKey: ['agent', 'sessions'] });
      if (sessionId) void client.invalidateQueries({ queryKey: key(sessionId) });
    },
  });
  const publish = useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) => agentApi.publish(id, version),
    onSuccess: (value) => {
      updateConversation(value);
      void client.invalidateQueries({ queryKey: ['collection'] });
      void client.invalidateQueries({ queryKey: ['dashboard'] });
      void message.success('菜单已确认发布');
    },
    onError: (error) => {
      void message.error(errorText(error));
    },
  });
  const onPublish = (version: PlanVersion) => {
    if (!conversation) return;
    modal.confirm({
      title: `确认发布第 ${version.revision} 版菜单`,
      content: (
        <div>
          <p>
            {version.result.date} {version.result.meal_type_label}，{version.result.diner_count}{' '}
            人次。
          </p>
          <p>{version.result.dishes.map((dish) => dish.dish_name).join('、')}</p>
          <p>会写入正式菜单，并记录你的确认。请先核对采购金额、缺失单价及营养差距。</p>
          {version.result.gaps.some((gap) => gap.status !== 'ok') && (
            <p className="zw-agent-publish-warning">
              当前方案仍有指标偏离建议目标。请确认你已查看「菜单与营养」中的差距。
            </p>
          )}
        </div>
      ),
      okText: '确认并发布',
      cancelText: '继续核对',
      onOk: () =>
        publish.mutateAsync({ id: conversation.id, version: version.revision }).catch(() => {
          throw new Error('发布未完成，请核对错误提示');
        }),
    });
  };
  const undo = useMutation({
    mutationFn: (id: string) => agentApi.undoPublish(id),
    onSuccess: (value) => {
      updateConversation(value);
      void client.invalidateQueries({ queryKey: ['collection'] });
      void client.invalidateQueries({ queryKey: ['dashboard'] });
      void message.success('已撤回这次发布，菜单恢复成发布前的样子');
    },
    onError: (error) => {
      void message.error(errorText(error));
    },
  });
  const onUndo = (version: PlanVersion) => {
    if (!conversation) return;
    modal.confirm({
      title: `撤回第 ${version.revision} 版菜单的发布`,
      content: (
        <div>
          <p>
            {version.result.date} {version.result.meal_type_label}{' '}
            的菜单会恢复成发布前的样子，这一版方案回到「待确认」。
          </p>
          <p>
            发布之后菜单要是被别人改过、或者这餐已经录了采集，系统会拒绝撤回——
            它不会覆盖别人的改动。
          </p>
        </div>
      ),
      okText: '确认撤回',
      okButtonProps: { danger: true },
      cancelText: '先不撤',
      onOk: () =>
        undo.mutateAsync(conversation.id).catch(() => {
          throw new Error('撤回未完成，请核对错误提示');
        }),
    });
  };
  const busy = run.isPending || publish.isPending || undo.isPending;
  const unavailable = status.isError || status.isPending;
  const selectSession = (id: string) => {
    if (!busy) {
      setRunError('');
      setInput('');
      setSearch({ session: id });
    }
  };
  const newSession = () => {
    if (!busy) {
      setSearch({});
      setParameters(initialParameters());
      // 路由更新在过渡中提交；保留旧会话标记，避免旧数据在过渡帧覆盖刚重置的条件。
      setLoadedSession(conversation?.id ?? null);
      setRevision(null);
      setRunError('');
      setInput('');
    }
  };
  const send = (text: string) => {
    if (!busy && !unavailable) {
      setMobilePanel('chat');
      run.mutate(text);
    }
  };
  const updateParameters = (value: PlanParameters) => {
    const dateOrMealChanged =
      value.on_date !== effectiveParameters.on_date ||
      value.meal_type !== effectiveParameters.meal_type;
    // 换日期或餐次后，原人数不再有依据；清空后由系统重新预测。
    setParameters(dateOrMealChanged ? { ...value, diner_count: null } : value);
  };

  return (
    <main className="zw-agent">
      {status.isError && (
        <Alert
          type="error"
          showIcon
          title="膳食助手暂时不可用"
          description={
            <>
              {errorText(status.error)}。
              {status.error instanceof ApiError && status.error.isUnauthorized ? (
                <Link to="/login">重新登录</Link>
              ) : (
                '请启动 Agent 与业务服务后重试。'
              )}
            </>
          }
          action={<Button onClick={() => void status.refetch()}>重试</Button>}
        />
      )}
      {current.isError && (
        <Alert
          type="error"
          showIcon
          title={errorText(current.error)}
          action={<Button onClick={newSession}>新建任务</Button>}
        />
      )}
      {runError && conversation?.messages.at(-1)?.content !== runError && (
        <Alert type="warning" showIcon closable onClose={() => setRunError('')} title={runError} />
      )}
      <div className="zw-agent-mobile-nav" role="group" aria-label="移动端工作区">
        <button
          type="button"
          aria-pressed={mobilePanel === 'chat'}
          onClick={() => setMobilePanel('chat')}
        >
          对话
        </button>
        <button
          type="button"
          aria-pressed={mobilePanel === 'result'}
          onClick={() => setMobilePanel('result')}
        >
          结果{conversation?.plans.length ? <span>{conversation.plans.length}</span> : null}
        </button>
        <button
          type="button"
          aria-pressed={mobilePanel === 'task'}
          onClick={() => setMobilePanel('task')}
        >
          条件
        </button>
      </div>
      <div className="zw-agent-workbench" data-mobile-panel={mobilePanel}>
        <TaskPanel
          parameters={effectiveParameters}
          onChange={updateParameters}
          dishes={dishes.data ?? []}
          sessions={sessions.data ?? []}
          activeSession={sessionId}
          onSelectSession={selectSession}
          onNew={newSession}
          busy={busy}
          canPlan={canPlan}
          dinerForecast={dinerForecast.data ?? null}
          dinerForecastLoading={dinerForecast.isFetching}
          onCheckData={() => send('按当前任务条件做数据体检')}
          unavailable={unavailable}
        />
        {sessionId && current.isPending ? (
          <Skeleton active className="zw-agent-loading" />
        ) : (
          <ConversationView
            messages={conversation?.messages ?? []}
            input={input}
            setInput={setInput}
            onSend={send}
            busy={run.isPending}
            pendingContent={pendingContent}
            trace={trace}
            statusText={statusText}
            disabled={unavailable || current.isError || publish.isPending}
            canPlan={canPlan}
            pending={conversation?.pending_task ?? null}
          />
        )}
        <ResultPanel
          activeTab={resultTab}
          onTabChange={setResultTab}
          conversation={conversation}
          revision={revision}
          onRevision={setRevision}
          onReplace={(name) => send(`换掉${name}，其余条件不变，重新安排菜单与采购`)}
          onPublish={onPublish}
          onReuse={(version) => {
            setParameters(version.parameters);
            setInput('按当前任务条件重新安排菜单与采购');
            setMobilePanel('task');
            void message.info(`已载入第 ${version.revision} 版条件，请核对供餐日期后发送重算`);
          }}
          canPlan={status.data?.can_plan ?? false}
          busy={run.isPending}
          publishing={publish.isPending}
          onUndo={onUndo}
          undoing={undo.isPending}
        />
      </div>
    </main>
  );
}
