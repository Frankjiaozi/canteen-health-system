import { Card, Space, Table, Tag, Typography } from 'antd';
import { useDailyLogList } from '../hooks/useCollection';
import type { DailyLogSummary } from '../types';

const PAGE_SIZE = 8;

/** 最近采集记录。录入时最常问的是「前天录了没有」，一张小表比翻日期框快。 */
export function RecentLogs() {
  const listQuery = useDailyLogList(1, PAGE_SIZE);

  return (
    <Card size="small" title="最近采集">
      <Table<DailyLogSummary>
        rowKey={(row) => `${row.date}-${row.meal_type}`}
        size="small"
        loading={listQuery.isLoading}
        dataSource={listQuery.data?.items ?? []}
        pagination={false}
        scroll={{ x: 960 }}
        columns={[
          { title: '日期', dataIndex: 'date', width: 120, fixed: 'left' },
          { title: '餐次', dataIndex: 'meal_type_label', width: 80 },
          {
            title: '就餐人次',
            dataIndex: 'diner_count',
            width: 100,
            align: 'right',
          },
          {
            title: '油 / 盐 / 糖（克）',
            width: 220,
            align: 'right',
            render: (_, row) =>
              [row.oil_total_g, row.salt_total_g, row.sugar_total_g]
                .map((value) => (value === null ? '未测' : Number(value).toFixed(1)))
                .join(' / '),
          },
          { title: '菜品数', dataIndex: 'dish_count', width: 90, align: 'right' },
          {
            title: '浪费率',
            dataIndex: 'waste_ratio',
            width: 100,
            align: 'right',
            render: (value: string | null) =>
              value === null ? (
                <Typography.Text type="secondary">—</Typography.Text>
              ) : (
                `${(Number(value) * 100).toFixed(1)}%`
              ),
          },
          {
            title: '异常',
            width: 200,
            render: (_, row) =>
              row.anomaly_flags.length === 0 ? (
                <Typography.Text type="secondary">—</Typography.Text>
              ) : (
                <Space size={4} wrap>
                  {row.anomaly_flags.map((flag) => (
                    <Tag key={flag.value} color={flag.system ? 'orange' : 'red'}>
                      {flag.label}
                    </Tag>
                  ))}
                </Space>
              ),
          },
          {
            title: '录入人',
            dataIndex: 'submitted_by_name',
            width: 100,
            render: (value: string | null) =>
              value ?? <Typography.Text type="secondary">—</Typography.Text>,
          },
        ]}
      />
    </Card>
  );
}
