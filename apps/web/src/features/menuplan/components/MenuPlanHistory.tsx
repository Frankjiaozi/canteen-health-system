import { useQuery } from '@tanstack/react-query';
import { Alert, Collapse, Empty, Skeleton, Space, Table, Tag, Typography } from 'antd';
import { api } from '@/shared/api/client';
import { unwrap } from '@/shared/api/result';
import { PurchaseList } from './PurchaseList';

export function MenuPlanHistory({ onDate }: { onDate: string }) {
  const history = useQuery({
    queryKey: ['menu-plan', 'history', onDate],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/menu-plan/history', {
          params: { query: { on_date: onDate } },
        }),
      ),
  });
  if (history.isPending) return <Skeleton active />;
  if (history.isError) return <Alert type="error" showIcon title="菜单历史读取失败" />;
  if (!history.data.length) return <Empty description="这一天暂无已保存的菜单与采购方案" />;
  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Typography.Text type="secondary">
        显示所选日期最近 100
        份完整方案。以下采购量和金额为生成时的快照，当前供应以正式菜单和采集记录为准。
      </Typography.Text>
      <Collapse
        items={history.data.map((item) => ({
          key: item.plan.suggestion_id,
          label: (
            <Space wrap>
              <strong>
                {item.plan.date} · {item.plan.meal_type_label}
              </strong>
              <Tag>{item.status_label}</Tag>
              <span>{new Date(item.created_at).toLocaleString('zh-CN')}</span>
            </Space>
          ),
          children: (
            <Space orientation="vertical" style={{ width: '100%' }}>
              <Table
                pagination={false}
                size="small"
                rowKey="dish_id"
                dataSource={item.plan.dishes}
                columns={[
                  { title: '菜品', dataIndex: 'dish_name' },
                  {
                    title: '计划份数',
                    render: (_, dish) => dish.planned_servings ?? dish.predicted_servings ?? '—',
                  },
                ]}
              />
              <PurchaseList plan={item.plan} historical />
            </Space>
          ),
        }))}
      />
    </Space>
  );
}
