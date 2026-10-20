import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { Button, Input, Steps } from 'antd';
import { useEffect, useRef } from 'react';
import type { ChatMessage, PendingTask, ToolTrace } from '../api/types';

/**
 * 三句最常用的开场白。
 *
 * 同一个清单用在两个地方：空对话时是大卡片（说明每句能干什么），
 * 聊过之后变成句末的小气泡（随手再点一次）。分成两份文案的话，
 * 改了一处忘了另一处，两边就说的不是同一件事了。
 */
const STARTERS: { label: string; prompt: string; hint: string; needsPlan?: boolean }[] = [
  {
    label: '安排菜单与采购',
    prompt: '请按任务条件安排菜单与采购',
    hint: '按人数、预算和供餐记录计算',
    needsPlan: true,
  },
  {
    label: '先检查数据',
    prompt: '按当前任务条件做数据体检',
    hint: '配方、单价和供餐历史是否准备好',
  },
  {
    label: '核查近期记录',
    prompt: '核查最近7天供应记录',
    hint: '找出需要人工核对的记录',
  },
  {
    label: '看最近 7 天数据',
    prompt: '看一下最近7天的食堂数据',
    hint: '油盐糖、人均摄入、达标与剩餐',
  },
  {
    label: '查今日供应与营养',
    prompt: '查一下今天午餐供应了哪些菜，每道菜的单份营养是多少',
    hint: '当日菜单、份数与五项营养',
  },
  {
    label: '查菜品配方',
    prompt: '查一下番茄炒蛋的配方',
    hint: '每份食材、调味料与单份营养',
  },
  {
    label: '查食材营养',
    prompt: '查一下大白菜的营养成分',
    hint: '每100克可食部的五项指标',
  },
  {
    label: '查节假日与调休',
    prompt: '查一下2026年10月的节假日和调休',
    hint: '按日期核对放假与上班',
  },
];

export function TraceList({ trace }: { trace: ToolTrace[] }) {
  if (!trace.length) return null;
  return (
    <div className="zw-agent-execution-steps" aria-label="实际执行步骤">
      <Steps
        orientation="vertical"
        size="small"
        items={trace.map((step) => ({
          key: step.id,
          title: step.label,
          content: step.detail,
          status:
            step.status === 'running' ? 'process' : step.status === 'error' ? 'error' : 'finish',
          icon:
            step.status === 'running' ? (
              <LoadingOutlined spin />
            ) : step.status === 'error' ? (
              <CloseCircleOutlined />
            ) : (
              <CheckCircleOutlined />
            ),
        }))}
      />
    </div>
  );
}

interface Props {
  messages: ChatMessage[];
  input: string;
  setInput: (value: string) => void;
  onSend: (text: string) => void;
  busy: boolean;
  pendingContent: string;
  trace: ToolTrace[];
  statusText: string;
  disabled: boolean;
  canPlan: boolean;
  pending: PendingTask | null;
}

export function ConversationView({
  messages,
  input,
  setInput,
  onSend,
  busy,
  pendingContent,
  trace,
  statusText,
  disabled,
  canPlan,
  pending,
}: Props) {
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // 空对话的开场卡本身就是内容，不该在挂载时被滚到底部、把标题和印章切掉。
    if (scroll.current && (messages.length > 0 || busy)) {
      scroll.current.scrollTop = scroll.current.scrollHeight;
    }
  }, [messages.length, trace.length, busy]);
  return (
    <section className="zw-agent-conversation" aria-label="与知味对话">
      <div className="zw-agent-chat-scroll" ref={scroll}>
        {messages.length === 0 && !busy ? (
          <div className="zw-agent-welcome">
            <div className="zw-agent-ink-mark" aria-hidden="true">
              知
            </div>
            <h2>
              明天的这一餐，
              <br />
              一起安排妥当。
            </h2>
            <p>
              从菜单到采购，把依据摊开看。
              <br />
              你提出条件，知味调用现有数据计算，最后由你确认。
            </p>
            <div className={`zw-agent-starters${STARTERS.length > 3 ? ' is-extended' : ''}`}>
              {STARTERS.filter((starter) => canPlan || !starter.needsPlan).map((starter) => (
                <button
                  type="button"
                  key={starter.label}
                  disabled={disabled}
                  onClick={() => onSend(starter.prompt)}
                >
                  {starter.label}
                  <span>{starter.hint}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={`zw-agent-message is-${message.role} is-${message.kind ?? 'message'}`}
            >
              <div className="zw-agent-message-by">
                {message.role === 'user' ? '你' : '知味'}
                <time dateTime={message.created_at}>
                  {new Date(message.created_at).toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </time>
              </div>
              <div className="zw-agent-message-content">{message.content}</div>
              {(message.suggestions?.length ?? 0) > 0 && (
                <div className="zw-agent-suggested-replies" aria-label="可选的补充回复">
                  {message.suggestions!.map((reply, index) => (
                    <button
                      type="button"
                      key={index}
                      disabled={disabled || busy || !pending || message.id !== messages.at(-1)?.id}
                      onClick={() => onSend(reply.content)}
                    >
                      {reply.label}
                    </button>
                  ))}
                  <small>选择后才会继续；你也可以直接回复。</small>
                </div>
              )}
              {message.trace.length > 0 && (
                <details className="zw-agent-message-trace">
                  <summary>查看 {message.trace.length} 个执行步骤</summary>
                  <TraceList trace={message.trace} />
                </details>
              )}
            </article>
          ))
        )}
        {busy && (
          <>
            <article className="zw-agent-message is-user">
              <div className="zw-agent-message-by">你</div>
              <div className="zw-agent-message-content">{pendingContent}</div>
            </article>
            <div className="zw-agent-live" role="status" aria-live="polite">
              <div>
                <LoadingOutlined spin /> {statusText || '正在处理'}
              </div>
              <TraceList trace={trace} />
            </div>
          </>
        )}
        {/* 聊过之后，这三句缩成句末的小气泡：不用回头翻、也不用重新打字 */}
        {messages.length > 0 && !busy && !pending && (
          <div className="zw-agent-quick-replies" aria-label="继续对话">
            <span>还可以这样问</span>
            {STARTERS.filter((starter) => canPlan || !starter.needsPlan).map((starter) => (
              <button
                type="button"
                key={starter.label}
                disabled={disabled}
                title={starter.hint}
                onClick={() => onSend(starter.prompt)}
              >
                {starter.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <form
        className="zw-agent-composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (input.trim() && !busy) onSend(input.trim());
        }}
      >
        {pending && !busy && (
          <div className="zw-agent-pending-note" role="status">
            <span>等待补充条件，尚未执行新的安排</span>
            <button type="button" disabled={busy || disabled} onClick={() => onSend('取消补充')}>
              取消补充
            </button>
          </div>
        )}
        <label className="zw-agent-sr-only" htmlFor="agent-message">
          告诉知味你的安排
        </label>
        <Input.TextArea
          id="agent-message"
          value={input}
          disabled={disabled || busy}
          onChange={(event) => setInput(event.target.value)}
          maxLength={2000}
          autoSize={{ minRows: 2, maxRows: 5 }}
          placeholder={
            pending?.field === 'budget_per_person'
              ? '例如：7元。其他已明确的条件会保留。'
              : pending
                ? '补充具体条件，或取消后重新安排。'
                : '例如：明天午餐800人，每人预算8元；或核查最近7天记录'
          }
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (input.trim() && !busy && !disabled) onSend(input.trim());
            }
          }}
        />
        <div className="zw-agent-composer-bottom">
          <span>Enter 发送 · Shift + Enter 换行</span>
          <Button
            htmlType="submit"
            type="primary"
            icon={<SendOutlined />}
            loading={busy}
            disabled={disabled || !input.trim()}
            aria-label="发送任务"
          >
            发送
          </Button>
        </div>
      </form>
    </section>
  );
}
