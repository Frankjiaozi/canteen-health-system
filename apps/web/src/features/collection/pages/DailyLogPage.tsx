import { Alert, DatePicker, Segmented, Skeleton, Space, Typography } from 'antd';
import dayjs from 'dayjs';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { useDateMealSelection } from '@/shared/hooks/useDateMealSelection';
import { PagePanel } from '@/shared/components/PagePanel';
import { DailyLogForm } from '../components/DailyLogForm';
import { PendingQueue } from '../components/PendingQueue';
import { RecentLogs } from '../components/RecentLogs';
import { useDailyLogSheet } from '../hooks/useCollection';
import type { MealType } from '../types';

export function DailyLogPage() {
  const { date: onDate, meal, setDate, setMeal } = useDateMealSelection('LUNCH');
  const mealType = meal as MealType;
  const sheetQuery = useDailyLogSheet(onDate, mealType);
  const { data: enumOptions } = useEnumOptions();

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <PendingQueue />
      <PagePanel
        filters={
          <>
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
          </>
        }
        bodyClassName="is-padded"
      >
        <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 18 }}>
          每天只需要填几个数字：勾出今天供应的菜、份数、人次、油盐糖实际用量、剩餐。
          保存后当餐营养立即重算，公开大屏随即可见。
        </Typography.Paragraph>

        {sheetQuery.isPending ? (
          <Skeleton active />
        ) : sheetQuery.isError ? (
          <Alert
            type="error"
            showIcon
            message="读不到这一天的采集单"
            description="请确认后端服务可用，或换一个日期再试。"
          />
        ) : sheetQuery.data ? (
          <DailyLogForm
            // 换日期时整份重建，表单初始值直接来自新数据
            key={`${onDate}-${mealType}`}
            onDate={onDate}
            sheet={sheetQuery.data}
          />
        ) : null}
      </PagePanel>
      <RecentLogs />
    </Space>
  );
}
