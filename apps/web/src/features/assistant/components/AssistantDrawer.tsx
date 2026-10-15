import { RobotOutlined, SendOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Empty, Input, Space, Spin, Tag, Typography } from 'antd';
import { useRef, useState } from 'react';
import { useAssistantStatus, useAskAssistant } from '../hooks/useAssistant';
import { AnswerBody } from './AnswerBody';
import {
  SUGGESTIONS,
  buildHistory,
  describeToolRun,
  nextMessageId,
  type ChatMessage,
} from '../lib/chat';

/**
 * AI 助手抽屉（阶段一：只读问答）。

 * 回答里会带上「刚才查了什么」——只给一段像模像样的话，用户没法核对；
 * 而这一版的分界线就是**不编数据**，所以查询过程要摆在明面上。
 */
export function AssistantDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const status = useAssistantStatus();
  const ask = useAskAssistant();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const seed = useRef(0);

  const enabled = status.data?.enabled === true;

  const send = async (question: string) => {
    const text = question.trim();
    if (!text || ask.isPending) return;
    const history = buildHistory(messages);
    seed.current += 1;
    const userMessage: ChatMessage = {
      id: nextMessageId(seed.current),
      role: 'user',
      content: text,
    };
    setMessages((current) => [...current, userMessage]);
    setDraft('');
    try {
      const reply = await ask.mutateAsync({ question: text, history });
      seed.current += 1;
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId(seed.current),
          role: 'assistant',
          content: reply.reply,
          toolCalls: reply.tool_calls ?? [],
          truncated: reply.truncated,
        },
      ]);
    } catch {
      // 失败提示已经在 mutation 里给了；把刚才那句话留在对话里，方便改一改再问
    }
  };

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
      size={460}
      open={open}
      onClose={onClose}
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

      {status.data && enabled ? (
        <Typography.Text type="secondary">
          目前只能查数据（食材、菜品配方、某天的菜单、看板指标、最近采集），还不能替你录入或修改。
        </Typography.Text>
      ) : null}

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {messages.length === 0 ? (
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
            {ask.isPending ? (
              <Typography.Text type="secondary">
                <Spin size="small" /> 正在查……
              </Typography.Text>
            ) : null}
          </Space>
        )}
      </div>

      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={draft}
          disabled={!enabled || ask.isPending}
          placeholder={enabled ? '例如：最近两周盐用超了吗？' : '助手未接模型'}
          onChange={(event) => setDraft(event.target.value)}
          onPressEnter={() => void send(draft)}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          disabled={!enabled || draft.trim().length === 0}
          loading={ask.isPending}
          onClick={() => void send(draft)}
        >
          问
        </Button>
      </Space.Compact>
    </Drawer>
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
    </div>
  );
}
