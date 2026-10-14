import { DeleteOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus';
import { flushOfflineQueue, useOfflineQueueStore } from '../hooks/useOfflineQueue';
import { describeEntry, type QueuedEntry } from '../lib/offlineQueue';

/**
 * 待同步的采集单。
 *
 * 断网时录入的东西必须看得见：只留一句「已存入队列」然后什么都不显示，
 * 录入员第二天不会知道到底交上去了没有。这里把每一条的时间、餐次与上次失败原因都列出来，
 * 并提供手动重试与放弃。
 */
export function PendingQueue() {
  const entries = useOfflineQueueStore((state) => state.entries);
  const drop = useOfflineQueueStore((state) => state.drop);
  const isOnline = useOnlineStatus();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const { data: enumOptions } = useEnumOptions();
  const [retrying, setRetrying] = useState(false);

  if (entries.length === 0) return null;

  const mealLabel = (value: string) =>
    enumOptions?.meal_type.find((option) => option.value === value)?.label ?? value;

  const retryNow = async () => {
    setRetrying(true);
    const result = await flushOfflineQueue(queryClient);
    setRetrying(false);
    if (result.failed) {
      void message.error(`补交失败：${result.failed.lastError ?? '未知原因'}`);
    } else {
      void message.success(`已补交 ${result.synced} 条采集记录`);
    }
  };

  return (
    <Card
      size="small"
      title={
        <Space>
          <span>待同步的采集单</span>
          <Tag color={isOnline ? 'blue' : 'orange'}>{entries.length} 条</Tag>
        </Space>
      }
      extra={
        <Space>
          <Typography.Text type="secondary">
            {isOnline ? '联网后会自动补交' : '恢复联网后自动补交'}
          </Typography.Text>
          {isOnline ? (
            <Button size="small" loading={retrying} onClick={() => void retryNow()}>
              立即补交
            </Button>
          ) : null}
        </Space>
      }
    >
      {entries.some((entry) => entry.lastError !== null) ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="有记录没能补交成功"
          description="多半是数据本身被服务端拒绝了。切到对应日期核对并重新保存，或放弃这条记录。"
        />
      ) : null}
      <Table<QueuedEntry>
        rowKey="id"
        size="small"
        pagination={false}
        dataSource={entries}
        columns={[
          { title: '日期', dataIndex: 'onDate', width: 120 },
          {
            title: '餐次',
            width: 90,
            render: (_, entry) => mealLabel(entry.mealType),
          },
          {
            title: '菜品数 / 人次',
            width: 140,
            render: (_, entry) =>
              `${entry.payload.dishes?.length ?? 0} 道 / ${entry.payload.diner_count} 人次`,
          },
          {
            title: '入队时间',
            width: 190,
            render: (_, entry) => new Date(entry.queuedAt).toLocaleString('zh-CN'),
          },
          {
            title: '状态',
            render: (_, entry) => (
              <Typography.Text type={entry.lastError ? 'danger' : 'secondary'}>
                {describeEntry(entry)}
              </Typography.Text>
            ),
          },
          {
            title: '操作',
            width: 110,
            render: (_, entry) => (
              <Popconfirm
                title="放弃这条记录？"
                description="放弃之后这份录入就没了，需要重新填一遍。"
                okText="放弃"
                cancelText="取消"
                onConfirm={() => drop(entry.id)}
              >
                <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                  放弃
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />
    </Card>
  );
}
