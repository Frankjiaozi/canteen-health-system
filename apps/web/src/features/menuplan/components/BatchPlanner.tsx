import {
  Alert,
  Button,
  Card,
  DatePicker,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { formatAmount } from '@/features/forecast/lib/format';
import { useGenerateMenuPlanBatch, useSyncMenuPlanBatch } from '../hooks/useMenuPlan';
import { batchStatusTone, mergeBatchStatuses } from '../lib/present';
import type { MealType, MenuPlanBatchDay } from '../types';

const TONE_COLOR = { ok: 'green', skipped: 'default', bad: 'red' } as const;

/**
 * 批量排菜单：一次排一段（例如 12 月 7 日到 17 日），确认后采纳并同步当日菜单。
 *
 * 为什么走「先生成、再导入」两步而不是一步到位：这一批菜单值得先看一眼再落库——
 * 排出来的是十来天的菜单，落库之后每一天都会被采集页与大屏读到，想改要一天天改。
 */
export function BatchPlanner({ mealType }: { mealType: MealType }) {
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);
  const [range, setRange] = useState<[Dayjs, Dayjs]>(() => [
    dayjs().add(1, 'day'),
    dayjs().add(7, 'day'),
  ]);

  const generate = useGenerateMenuPlanBatch();
  const importBatch = useSyncMenuPlanBatch();
  const [days, setDays] = useState<MenuPlanBatchDay[]>([]);

  const start = range[0].format('YYYY-MM-DD');
  const end = range[1].format('YYYY-MM-DD');

  const handleGenerate = () => {
    generate.mutate(
      { startDate: start, endDate: end, mealType },
      { onSuccess: (result) => setDays(result.rows) },
    );
  };

  const handleImport = () => {
    importBatch.mutate(
      {
        startDate: start,
        endDate: end,
        mealType,
        suggestionIds: Object.fromEntries(
          days
            .filter((row) => row.suggestion_id && ['GENERATED', 'IMPORTED'].includes(row.status))
            .map((row) => [row.date, row.suggestion_id!]),
        ),
      },
      { onSuccess: (result) => setDays((current) => mergeBatchStatuses(current, result.rows)) },
    );
  };

  const generated = days.filter((row) => row.status === 'GENERATED').length;
  const imported = days.filter((row) => row.status === 'IMPORTED').length;
  const skipped = days.filter((row) => row.status === 'SKIPPED').length;
  const failed = days.filter((row) => row.status === 'FAILED').length;

  if (!canWrite) {
    return (
      <Alert
        type="info"
        showIcon
        message="批量排菜单由食堂录入员或管理员操作"
        description="已发布菜品请到首页菜单和供餐记录查看，此页不提供跨账号的批量方案历史。"
      />
    );
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card
        size="small"
        title="批量排菜单"
        extra={
          <Space wrap>
            <DatePicker.RangePicker
              disabled={generate.isPending || importBatch.isPending}
              value={range}
              allowClear={false}
              onChange={(value) => {
                if (value?.[0] && value[1]) {
                  setRange([value[0], value[1]]);
                  setDays([]);
                }
              }}
            />
            <Button
              type="primary"
              loading={generate.isPending}
              disabled={importBatch.isPending}
              onClick={handleGenerate}
            >
              批量生成
            </Button>
          </Space>
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          一次排一段，最长 31 天。每天的菜由推荐选出，份数按当天的同星期历史与节假日日历预测；
          「同一道菜不连续两日重复」在整段里都成立，已经录过采集的日子会跳过。
          生成只是算出来，确认无误后点下面的「采纳并同步」才写进各天的当日数据
          ——采纳之后，每一天的采集页按它勾好、公开大屏和看板也看得到。
        </Typography.Paragraph>

        {days.length === 0 ? (
          <Typography.Text type="secondary">
            选好日期区间（餐次用页面上方那个）后点「批量生成」。
          </Typography.Text>
        ) : (
          <>
            <Alert
              type={failed > 0 ? 'warning' : 'success'}
              showIcon
              style={{ marginBottom: 12 }}
              message={
                imported > 0
                  ? `${days.length} 天里已采纳 ${imported} 天${
                      skipped ? `，跳过 ${skipped} 天` : ''
                    }${failed ? `，${failed} 天没成功` : ''}`
                  : `${days.length} 天里排出 ${generated} 天${
                      skipped ? `，跳过 ${skipped} 天` : ''
                    }${failed ? `，${failed} 天排不出来` : ''}`
              }
              description={
                imported > 0
                  ? '这些天已同步至当日数据，采集页、公开大屏和看板已更新。'
                  : '这一步还没有采纳：点下面的「采纳并同步」才会生效。'
              }
            />
            <Table<MenuPlanBatchDay>
              rowKey="date"
              size="small"
              pagination={false}
              scroll={{ y: 360 }}
              dataSource={days}
              columns={[
                {
                  title: '日期',
                  dataIndex: 'date',
                  width: 130,
                  render: (value: string) => (
                    <Space size={6}>
                      <span>{value}</span>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {dayjs(value).format('ddd')}
                      </Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: '状态',
                  width: 100,
                  render: (_, row) => (
                    <Tag color={TONE_COLOR[batchStatusTone(row.status)]}>{row.status_label}</Tag>
                  ),
                },
                {
                  title: '菜品',
                  render: (_, row) => {
                    const names = row.dish_names ?? [];
                    return names.length > 0 ? (
                      <Tooltip title={names.join('、')}>
                        <Typography.Text>{names.join('、')}</Typography.Text>
                      </Tooltip>
                    ) : (
                      <Typography.Text type="secondary">{row.reason ?? '—'}</Typography.Text>
                    );
                  },
                },
                {
                  title: '道数',
                  width: 70,
                  align: 'right',
                  render: (_, row) => row.dish_count || '—',
                },
                {
                  title: '人均成本',
                  width: 110,
                  align: 'right',
                  render: (_, row) =>
                    row.cost_per_person ? `${formatAmount(row.cost_per_person)} 元` : '—',
                },
                {
                  title: '说明',
                  width: 200,
                  render: (_, row) =>
                    row.status === 'FAILED' ? (
                      <Typography.Text type="danger">{row.reason}</Typography.Text>
                    ) : (
                      <Typography.Text type="secondary">{row.calendar_note ?? '—'}</Typography.Text>
                    ),
                },
              ]}
            />

            <Space style={{ marginTop: 16 }} wrap>
              <Popconfirm
                title={`采纳并同步 ${start} 至 ${end} 的菜单？`}
                description="只采纳当前列表中已核对的方案；若数据已变化，会拒绝并提示原因。"
                okText="确认采纳"
                cancelText="继续核对"
                onConfirm={handleImport}
                disabled={generated + imported === 0 || generate.isPending || importBatch.isPending}
              >
                <Button
                  type="primary"
                  disabled={generated + imported === 0 || generate.isPending}
                  loading={importBatch.isPending}
                >
                  采纳并同步
                </Button>
              </Popconfirm>
              <Typography.Text type="secondary">
                采纳会把当前列表中已核对的方案写进各天的当日数据；
                已经录过采集的日子会跳过并说明原因。
              </Typography.Text>
            </Space>
          </>
        )}
      </Card>
    </Space>
  );
}
