import { Alert, Button, Card, Space, Table, Tag, Typography } from 'antd';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { useHolidays, useVerifyHoliday } from '../hooks/useForecast';
import { summarizeHolidays } from '../lib/format';
import type { HolidayRead } from '../types';

/** 节假日日历的核对入口。内置日历逐条标了「待核对」，这里是把它们落实的地方。 */
export function HolidayTable({ year }: { year: number }) {
  const holidays = useHolidays(year);
  const verifyMutation = useVerifyHoliday(year);
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);

  const items = holidays.data?.items ?? [];
  const summary = summarizeHolidays(items);

  return (
    <Card size="small" title={`${year} 年法定节假日日历`}>
      <Alert
        type={summary.unverified.length > 0 ? 'warning' : 'success'}
        showIcon
        style={{ marginBottom: 12 }}
        message={summary.text}
        description="放假当天下调份数、调休上班的周末按工作日算。以国务院办公厅通知为唯一依据。"
      />
      <Table<HolidayRead>
        rowKey="id"
        size="small"
        loading={holidays.isLoading}
        dataSource={items}
        pagination={false}
        columns={[
          { title: '日期', dataIndex: 'date', width: 130 },
          { title: '名称', dataIndex: 'name', width: 110 },
          {
            title: '类型',
            width: 110,
            render: (_, row) => (
              <Tag color={row.kind === 'HOLIDAY' ? 'red' : 'blue'}>{row.kind_label}</Tag>
            ),
          },
          {
            title: '核对状态',
            width: 120,
            render: (_, row) =>
              row.is_verified ? <Tag color="green">已核对</Tag> : <Tag color="orange">待核对</Tag>,
          },
          {
            title: '来源说明',
            render: (_, row) => (
              <Typography.Text type="secondary">{row.source_note ?? '—'}</Typography.Text>
            ),
          },
          {
            title: '操作',
            width: 130,
            render: (_, row) =>
              canWrite && !row.is_verified ? (
                <Button
                  type="link"
                  size="small"
                  loading={verifyMutation.isPending}
                  onClick={() =>
                    verifyMutation.mutate({ id: row.id, payload: { is_verified: true } })
                  }
                >
                  标记为已核对
                </Button>
              ) : (
                <Typography.Text type="secondary">—</Typography.Text>
              ),
          },
        ]}
      />
      <Space style={{ marginTop: 12 }}>
        <Typography.Text type="secondary">
          核对时请同时确认「放假区间」与「调休上班日」——目前内置的只有节日当天，
          连休与调休需要按通知补进来。
        </Typography.Text>
      </Space>
    </Card>
  );
}
