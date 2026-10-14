import { Alert, Button, Card, DatePicker, Segmented, Space, Table, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { useDateMealSelection } from '@/shared/hooks/useDateMealSelection';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { SuggestionDetail } from '../components/SuggestionDetail';
import {
  useGenerateSuggestion,
  useSuggestionDetail,
  useSuggestionHistory,
} from '../hooks/useRecommendation';
import { decisionLabel } from '../lib/present';
import type { MealType } from '../types';

export function RecommendationPage() {
  const { date: onDate, meal, setDate, setMeal } = useDateMealSelection('LUNCH');
  const mealType = meal as MealType;
  const { data: enumOptions } = useEnumOptions();
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);

  const generateMutation = useGenerateSuggestion();
  const history = useSuggestionHistory(onDate);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 展示以「详情查询」为唯一来源：生成只是选中新的一版。
  // 否则采纳/否决之后，界面上还是生成那一刻的旧状态。
  const activeId = selectedId ?? generateMutation.data?.id ?? null;
  const detail = useSuggestionDetail(activeId);

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title="菜单推荐"
        extra={
          <Space>
            <DatePicker
              value={dayjs(onDate)}
              allowClear={false}
              onChange={(value) => {
                if (value) {
                  setDate(value.format('YYYY-MM-DD'));
                  setSelectedId(null);
                }
              }}
            />
            <Segmented<MealType>
              value={mealType}
              onChange={(value) => {
                setMeal(value);
                setSelectedId(null);
              }}
              options={(enumOptions?.meal_type ?? []).map((option) => ({
                value: option.value as MealType,
                label: option.label,
              }))}
            />
            {canWrite ? (
              <Button
                type="primary"
                loading={generateMutation.isPending}
                onClick={() =>
                  generateMutation.mutate(
                    { onDate, mealType },
                    { onSuccess: (result) => setSelectedId(result.id) },
                  )
                }
              >
                生成建议
              </Button>
            ) : null}
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          在营养目标、成本预算、菜品数量与烹饪方式比例等硬约束下，用整数规划求一份菜单。
          推荐只作为建议，最终由食堂管理员确认；否决要写明原因。
        </Typography.Paragraph>
        <Alert
          type="info"
          showIcon
          message="这是求解结果，不是凭空生成的文案"
          description="每条建议都附带营养差距（差多少、往哪个方向）、贴边的约束与受欢迎度依据，可以逐条核对。"
        />

        {history.data && history.data.length > 0 ? (
          <Card size="small" title="这一天的历史版本" style={{ marginTop: 16 }}>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={history.data}
              columns={[
                {
                  title: '结论',
                  width: 110,
                  render: (_, row) => {
                    const decision = decisionLabel(row.status);
                    const color =
                      decision.tone === 'ok'
                        ? 'green'
                        : decision.tone === 'bad'
                          ? 'red'
                          : 'default';
                    return <Tag color={color}>{decision.text}</Tag>;
                  },
                },
                { title: '道数', dataIndex: 'dish_count', width: 80, align: 'right' },
                {
                  title: '成本（元）',
                  dataIndex: 'cost_estimate',
                  width: 110,
                  align: 'right',
                },
                {
                  title: '生成时间',
                  dataIndex: 'created_at',
                  width: 150,
                  render: (value: string) => dayjs(value).format('MM-DD HH:mm'),
                },
                {
                  title: '否决原因',
                  render: (_, row) =>
                    row.rejected_reason ?? <Typography.Text type="secondary">—</Typography.Text>,
                },
                {
                  title: '操作',
                  width: 80,
                  render: (_, row) => (
                    <Button type="link" size="small" onClick={() => setSelectedId(row.id)}>
                      查看
                    </Button>
                  ),
                },
              ]}
            />
          </Card>
        ) : null}
      </Card>

      {detail.data ? (
        <SuggestionDetail suggestion={detail.data} />
      ) : (
        <Card size="small">
          <Typography.Text type="secondary">
            选好日期与餐次后点「生成建议」，这里会给出菜单、营养差距与推荐理由。
          </Typography.Text>
        </Card>
      )}
    </Space>
  );
}
