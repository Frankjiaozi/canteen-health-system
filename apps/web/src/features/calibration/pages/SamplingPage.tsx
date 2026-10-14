import { Button, Card, DatePicker, Segmented, Space, Table, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { useDateMealSelection } from '@/shared/hooks/useDateMealSelection';
import { SampleDrawer } from '../components/SampleDrawer';
import { useRunDailyClosure, useSamplingCandidates } from '../hooks/useCalibration';
import { NUTRIENT_ROWS, formatNumber, hasThreeValues } from '../lib/compare';
import type { MealType, SamplingCandidate } from '../types';

export function SamplingPage() {
  const { date: onDate, meal, setDate, setMeal } = useDateMealSelection('LUNCH');
  const mealType = meal as MealType;
  const [sampling, setSampling] = useState<SamplingCandidate | null>(null);
  const candidatesQuery = useSamplingCandidates(onDate, mealType);
  const closureMutation = useRunDailyClosure(onDate);
  const { data: user } = useCurrentUser();
  const { data: enumOptions } = useEnumOptions();
  const canWrite = canWriteBusinessData(user);

  const dishes = candidatesQuery.data?.dishes ?? [];
  const sampledCount = dishes.filter((dish) => dish.sampled !== null).length;

  return (
    <Card
      title="抽样纠偏"
      extra={
        <Space>
          <DatePicker
            value={dayjs(onDate)}
            allowClear={false}
            onChange={(value) => value && setDate(value.format('YYYY-MM-DD'))}
          />
          <Segmented<MealType>
            value={mealType}
            onChange={(value) => setMeal(value)}
            options={(enumOptions?.meal_type ?? []).map((option) => ({
              value: option.value as MealType,
              label: option.label,
            }))}
          />
          {canWrite ? (
            <Button
              loading={closureMutation.isPending}
              onClick={() => closureMutation.mutate(mealType)}
            >
              重跑当日校准
            </Button>
          ) : null}
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">
        每周挑三到五道菜称重实测。实测只修正**调味料的贡献**，食材部分来自配方、保持不变；
        三个值（理论 / 校准 / 实测）并存，便于对照与回溯。
        {candidatesQuery.data && candidatesQuery.data.recent_corrections.length > 0 ? (
          <> 当前已有 {sampledCount} 道菜记过实测，最近一次修正见下表。</>
        ) : null}
      </Typography.Paragraph>

      <Table<SamplingCandidate>
        rowKey="dish_id"
        size="small"
        loading={candidatesQuery.isLoading}
        dataSource={dishes}
        pagination={false}
        locale={{ emptyText: '这一天还没有确认菜单，先到「每日采集」勾出当天供应的菜品' }}
        columns={[
          {
            title: '菜品',
            width: 190,
            fixed: 'left',
            render: (_, dish) => (
              <Space orientation="vertical" size={0}>
                <Typography.Text strong>{dish.dish_name}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {dish.category_label} · {dish.cooking_method_label}
                </Typography.Text>
              </Space>
            ),
          },
          ...NUTRIENT_ROWS.map((row) => ({
            title: `${row.label}（${row.unit}）`,
            width: 200,
            align: 'right' as const,
            render: (_: unknown, dish: SamplingCandidate) => (
              <Space orientation="vertical" size={2} style={{ textAlign: 'right' }}>
                <Typography.Text>
                  理论 {formatNumber(dish.theoretical?.[row.field], row.digits)}
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  校准 {formatNumber(dish.calibrated?.[row.field], row.digits)}
                </Typography.Text>
                <Typography.Text
                  type={dish.sampled ? 'success' : 'secondary'}
                  style={{ fontSize: 12 }}
                >
                  实测 {formatNumber(dish.sampled?.[row.field], row.digits)}
                </Typography.Text>
              </Space>
            ),
          })),
          {
            title: '状态',
            width: 150,
            fixed: 'right',
            render: (_, dish) => (
              <Space orientation="vertical" size={4}>
                {dish.sampled === null ? (
                  <Tag>未称重</Tag>
                ) : dish.suspect_recipe ? (
                  <Tag color="orange">疑似配方有误</Tag>
                ) : (
                  <Tag color="green">已套用修正</Tag>
                )}
                {hasThreeValues(dish) ? (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    三值齐备
                  </Typography.Text>
                ) : null}
                {canWrite ? (
                  <Button type="link" size="small" onClick={() => setSampling(dish)}>
                    {dish.sampled === null ? '录入实测' : '重新录入'}
                  </Button>
                ) : null}
              </Space>
            ),
          },
        ]}
      />

      {sampling ? (
        <SampleDrawer
          candidate={sampling}
          onDate={onDate}
          mealType={mealType}
          onClose={() => setSampling(null)}
        />
      ) : null}
    </Card>
  );
}
