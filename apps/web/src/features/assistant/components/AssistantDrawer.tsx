import { HistoryOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Empty, Input, Space, Spin, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import {
  useAskAssistant,
  useAssistantStatus,
  useConversation,
  useConversations,
  useDecideProposal,
} from '../hooks/useAssistant';
import {
  SUGGESTIONS,
  describeTokens,
  describeToolRun,
  nextMessageId,
  type ChatMessage,
} from '../lib/chat';
import type { ProposalRead } from '../types';
import { AnswerBody } from './AnswerBody';
import { ProposalCard } from './ProposalCard';

/**
 * AI 助手抽屉。

 * 三件事在这里交汇：对话（历史由服务端存，审计要查得到）、工具调用痕迹（答案从哪来）、
 * 以及写操作的**确认卡片**——助手只能提方案，真正写库要用户点一下。
 */
export function AssistantDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const status = useAssistantStatus();
  const [showHistory, setShowHistory] = useState(false);
  //: 要看哪次历史对话；`newToken` 用来强制换一块新对话面板
  const [openId, setOpenId] = useState<string | null>(null);
  const [newToken, setNewToken] = useState(0);

  const conversations = useConversations(open && showHistory);
  const opened = useConversation(openId);
  const enabled = status.data?.enabled === true;

  return (
    <Drawer
      title={
        <Space>
          <RobotOutlined />
          <span>AI 助手</span>
          {status.data ? (
            <Tag color={enabled ? 'green' : 'orange'}>
              {enabled ? `已接模型 ${status.data.model ?? ''}` : '未接模型'}
            </Tag>
          ) : null}
        </Space>
      }
      placement="right"
      size={480}
      open={open}
      onClose={onClose}
      extra={
        <Space>
          <Button
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => setShowHistory((value) => !value)}
          >
            历史对话
          </Button>
          <Button
            size="small"
            onClick={() => {
              setOpenId(null);
              setNewToken((value) => value + 1);
              setShowHistory(false);
            }}
          >
            新对话
          </Button>
        </Space>
      }
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 12 } }}
    >
      {status.isPending ? <Spin description="正在检查助手状态…" /> : null}

      {status.data && !enabled ? (
        <Alert
          type="warning"
          showIcon
          message="助手还没有接模型"
          description={status.data.note ?? '请在部署时配置模型端点。'}
        />
      ) : null}

      {showHistory ? (
        // 自己摆而不是用 antd 的 List：那个组件在当前版本已标记废弃，
        // 为一个「几条历史」引一个待替换的组件不划算
        <div
          style={{
            border: '1px solid #f0f0f0',
            borderRadius: 8,
            maxHeight: 240,
            overflowY: 'auto',
          }}
        >
          <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>
            <Typography.Text type="secondary">最近对话（含助手做过的操作）</Typography.Text>
          </div>
          {conversations.isLoading ? (
            <div style={{ padding: 12 }}>
              <Spin size="small" />
            </div>
          ) : (conversations.data ?? []).length === 0 ? (
            <div style={{ padding: 12 }}>
              <Typography.Text type="secondary">还没有对话记录</Typography.Text>
            </div>
          ) : (
            (conversations.data ?? []).map((row) => (
              <div
                key={row.id}
                style={{
                  display: 'flex',
                  gap: 8,
                  alignItems: 'center',
                  padding: '8px 12px',
                  borderBottom: '1px solid #fafafa',
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Typography.Text ellipsis style={{ display: 'block' }}>
                    {row.title}
                  </Typography.Text>
                  <Space size={8} wrap>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {dayjs(row.last_message_at).format('MM-DD HH:mm')}
                    </Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {row.user_name ?? '—'} · {row.message_count} 条消息
                    </Typography.Text>
                    {row.pending_proposals > 0 ? (
                      <Tag color="orange">{row.pending_proposals} 条待确认</Tag>
                    ) : null}
                  </Space>
                </div>
                <Button
                  type="link"
                  size="small"
                  onClick={() => {
                    setOpenId(row.id);
                    setShowHistory(false);
                  }}
                >
                  打开
                </Button>
              </div>
            ))
          )}
        </div>
      ) : null}

      {openId && opened.isPending ? (
        <Spin description="正在读这次对话…" />
      ) : (
        <ConversationPane
          // 换一次对话就换一块面板：初始值直接来自 props，省掉 effect 里同步状态那一次级联渲染
          key={openId ?? `new-${newToken}`}
          conversationId={openId}
          initialMessages={(opened.data?.messages ?? []).map((message) => ({
            id: message.id,
            role: message.role === 'USER' ? 'user' : 'assistant',
            content: message.content,
            toolCalls: message.tool_calls ?? [],
            truncated: message.truncated,
          }))}
          initialProposals={opened.data?.proposals ?? []}
          enabled={enabled}
          onTurnFinished={() => void conversations.refetch()}
        />
      )}
    </Drawer>
  );
}

interface PaneProps {
  conversationId: string | null;
  initialMessages: ChatMessage[];
  initialProposals: ProposalRead[];
  enabled: boolean;
  onTurnFinished: () => void;
}

/** 一块对话面板：自己管消息与方案，可以接着上次的对话问下去。 */
function ConversationPane({
  conversationId,
  initialMessages,
  initialProposals,
  enabled,
  onTurnFinished,
}: PaneProps) {
  const ask = useAskAssistant();
  const decide = useDecideProposal();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [proposals, setProposals] = useState<ProposalRead[]>(initialProposals);
  const [activeId, setActiveId] = useState<string | null>(conversationId);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  //: 正在查什么。工具是逐个跑的，先把「在查」显示出来，再补上结果
  const [running, setRunning] = useState<string | null>(null);

  const send = async (question: string) => {
    const text = question.trim();
    if (!text || pending) return;
    setPending(true);
    setMessages((current) => [
      ...current,
      { id: nextMessageId(current.length + 1), role: 'user', content: text },
    ]);
    // 先摆一条空的助手消息，流式的文字与工具痕迹都往上叠
    setMessages((current) => [
      ...current,
      { id: nextMessageId(current.length + 1), role: 'assistant', content: '', toolCalls: [] },
    ]);
    const patchLast = (patch: (message: ChatMessage) => ChatMessage) =>
      setMessages((current) =>
        current.map((item, index) => (index === current.length - 1 ? patch(item) : item)),
      );
    setDraft('');
    try {
      const reply = await ask.ask(text, activeId, {
        onStart: (id) => setActiveId(id),
        onToolStart: (label) => setRunning(label),
        onTool: (trace) => {
          setRunning(null);
          patchLast((item) => ({ ...item, toolCalls: [...(item.toolCalls ?? []), trace] }));
        },
        onDelta: (chunk) => patchLast((item) => ({ ...item, content: item.content + chunk })),
      });
      patchLast((item) => ({
        ...item,
        truncated: reply.truncated,
        tokensUsed: reply.tokens_used,
      }));
      if ((reply.proposals ?? []).length > 0) {
        setProposals((current) => [...current, ...(reply.proposals ?? [])]);
      }
      onTurnFinished();
    } catch {
      // 失败提示已在 mutation 里给了；刚问的那句留在对话里，方便改一改再问
      patchLast((item) => ({
        ...item,
        content: item.content || '（这次没有拿到回答，请再试一次）',
      }));
    } finally {
      setPending(false);
      setRunning(null);
    }
  };

  return (
    <>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {messages.length === 0 && proposals.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={enabled ? '问点什么试试' : '接上模型后就能用了'}
          >
            {enabled ? (
              <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                {SUGGESTIONS.map((item) => (
                  <Button
                    key={item.title}
                    size="small"
                    block
                    onClick={() => void send(item.question)}
                  >
                    {item.title}
                  </Button>
                ))}
              </Space>
            ) : null}
          </Empty>
        ) : (
          <Space orientation="vertical" size={12} style={{ width: '100%' }}>
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {proposals.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                deciding={decide.isPending}
                onDecide={(action) =>
                  decide.mutate(
                    { id: proposal.id, action },
                    {
                      onSuccess: (updated) =>
                        setProposals((current) =>
                          current.map((row) => (row.id === updated.id ? updated : row)),
                        ),
                    },
                  )
                }
              />
            ))}
            {pending ? (
              <Typography.Text type="secondary">
                <Spin size="small" /> {running ? `正在查 ${running}……` : '正在思考……'}
              </Typography.Text>
            ) : null}
          </Space>
        )}
      </div>

      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={draft}
          disabled={!enabled || pending}
          placeholder={enabled ? '例如：最近两周盐用超了吗？' : '助手未接模型'}
          onChange={(event) => setDraft(event.target.value)}
          onPressEnter={() => void send(draft)}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          disabled={!enabled || draft.trim().length === 0}
          loading={pending}
          onClick={() => void send(draft)}
        >
          问
        </Button>
      </Space.Compact>
    </>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  return (
    <div
      style={{
        background: isUser ? '#e6f4ff' : '#fafafa',
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        padding: '8px 12px',
      }}
    >
      {(message.toolCalls ?? []).length > 0 ? (
        <Space orientation="vertical" size={2} style={{ width: '100%', marginBottom: 8 }}>
          {(message.toolCalls ?? []).map((trace, index) => (
            <Typography.Text
              key={`${trace.name}-${index}`}
              type="secondary"
              style={{ fontSize: 12 }}
            >
              · {describeToolRun(trace)}
            </Typography.Text>
          ))}
        </Space>
      ) : null}
      {isUser ? (
        <Typography.Text style={{ whiteSpace: 'pre-wrap' }}>{message.content}</Typography.Text>
      ) : (
        <AnswerBody text={message.content} />
      )}
      {message.truncated ? (
        <div style={{ marginTop: 6 }}>
          <Tag color="orange">没查完就停了，换个更具体的问法再试</Tag>
        </div>
      ) : null}
      {!isUser && describeTokens(message.tokensUsed) ? (
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
          {describeTokens(message.tokensUsed)}
        </Typography.Text>
      ) : null}
    </div>
  );
}
