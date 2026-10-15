import { Alert, Button, Card, Space, Table, Tag, Typography } from 'antd';
import { describeProposalStatus, toPreviewBlocks } from '../lib/proposal';
import type { ProposalRead } from '../types';

const TONE_COLOR = { pending: 'orange', ok: 'green', bad: 'red', muted: 'default' } as const;

/**
 * 写操作的确认卡片。

 * 助手**不会**自己写库：它只提出方案，真正的写发生在这张卡片的「确认执行」上。
 * 所以卡片上必须把「要写什么」摆全——尤其是来源、用量这类事后追责要看的东西。
 */
export function ProposalCard({
  proposal,
  deciding,
  onDecide,
}: {
  proposal: ProposalRead;
  deciding: boolean;
  onDecide: (action: 'confirm' | 'cancel') => void;
}) {
  const verdict = describeProposalStatus(proposal.status, proposal.status_label);
  const blocks = toPreviewBlocks(proposal.preview ?? {});
  const pending = proposal.status === 'PENDING';

  return (
    <Card
      size="small"
      title={
        <Space>
          <span>{proposal.title}</span>
          <Tag color={TONE_COLOR[verdict.tone]}>{verdict.text}</Tag>
        </Space>
      }
      style={{ borderColor: pending ? '#ffd591' : undefined }}
    >
      <Typography.Paragraph style={{ marginBottom: 12 }}>{proposal.summary}</Typography.Paragraph>

      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        {blocks.map((block, index) => {
          if (block.kind === 'kv') {
            return (
              <div key={index}>
                {block.rows.map((row) => (
                  <div key={row.label} style={{ display: 'flex', gap: 8 }}>
                    <Typography.Text type="secondary" style={{ width: 150, flexShrink: 0 }}>
                      {row.label}
                    </Typography.Text>
                    <Typography.Text>{row.value}</Typography.Text>
                  </div>
                ))}
              </div>
            );
          }
          if (block.kind === 'table') {
            return (
              <div key={index}>
                <Typography.Text type="secondary">{block.title}</Typography.Text>
                <Table
                  size="small"
                  pagination={false}
                  rowKey="key"
                  dataSource={block.rows.map((cells, index) => ({
                    key: `row-${index}`,
                    cells,
                  }))}
                  columns={block.header.map((title, columnIndex) => ({
                    title,
                    dataIndex: ['cells', columnIndex],
                  }))}
                />
              </div>
            );
          }
          return (
            <Alert
              key={index}
              type="warning"
              showIcon
              message={block.title}
              description={
                <ul style={{ margin: 0, paddingInlineStart: 18 }}>
                  {block.items.map((item, itemIndex) => (
                    <li key={itemIndex}>{item}</li>
                  ))}
                </ul>
              }
            />
          );
        })}
      </Space>

      {pending ? (
        <Space style={{ marginTop: 12 }}>
          <Button type="primary" loading={deciding} onClick={() => onDecide('confirm')}>
            确认执行
          </Button>
          <Button onClick={() => onDecide('cancel')}>取消</Button>
          <Typography.Text type="secondary">确认之前什么也没有写进系统</Typography.Text>
        </Space>
      ) : null}

      {proposal.status === 'CONFIRMED' && proposal.result ? (
        <Alert
          type="success"
          showIcon
          style={{ marginTop: 12 }}
          message={`已执行：${Object.entries(proposal.result)
            .filter(([key]) => key !== 'id')
            .map(([key, value]) => `${key} ${String(value)}`)
            .join('，')}`}
          description={`由 ${proposal.created_by_name ?? '—'} 确认`}
        />
      ) : null}

      {proposal.status === 'FAILED' && proposal.error ? (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 12 }}
          message="执行失败，什么也没有写进去"
          description={proposal.error}
        />
      ) : null}
    </Card>
  );
}
