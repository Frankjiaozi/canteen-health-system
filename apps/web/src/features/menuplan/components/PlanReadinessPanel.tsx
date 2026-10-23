import { ReloadOutlined } from '@ant-design/icons';
import { useQueries } from '@tanstack/react-query';
import { Alert, Button, Card, Collapse, Skeleton, Space, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { ApiError } from '@/shared/api/errors';
import { useMenuDataRevision } from '@/shared/hooks/useMenuDataRevision';
import { fetchPlanReadiness } from '../api/menuPlanApi';
import type { MealType, PlanReadiness } from '../types';
import './plan-readiness.css';

const MEALS: { value: MealType; label: string }[] = [
  { value: 'BREAKFAST', label: '早餐' },
  { value: 'LUNCH', label: '午餐' },
  { value: 'DINNER', label: '晚餐' },
];
const STATES = {
  ready: { color: 'success', label: '未见数据缺口' },
  attention: { color: 'warning', label: '有待核对' },
  blocked: { color: 'error', label: '需要补齐数据' },
};

function Report({ report }: { report: PlanReadiness }) {
  const state = STATES[report.state];
  return (
    <>
      <Tag color={state.color}>{state.label}</Tag>
      <dl className="zw-plan-readiness-facts">
        <div>
          <dt>可用菜品</dt>
          <dd>
            {report.available_count}
            <small> 道</small>
          </dd>
        </div>
        <div>
          <dt>可预测份数</dt>
          <dd>
            {report.predicted_count}
            <small> 道</small>
          </dd>
        </div>
        <div>
          <dt>有效历史</dt>
          <dd>
            {report.days_with_records}
            <small> 天</small>
          </dd>
        </div>
      </dl>
      <Typography.Paragraph type="secondary">
        {report.predicted_diner_count != null
          ? `预计就餐 ${report.predicted_diner_count} 人次`
          : '尚无就餐人次预测'}
        {report.missing_price_count > 0 ? ` · ${report.missing_price_count} 项原料缺单价` : ''}
      </Typography.Paragraph>
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: 'detail',
            label: report.issue_count ? `查看 ${report.issue_count} 项待办与依据` : '查看检查依据',
            children: (
              <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                {report.issues.map((issue, index) => (
                  <Alert
                    key={`${issue.code}-${issue.entity_id ?? index}`}
                    type={issue.severity === 'blocking' ? 'error' : 'warning'}
                    showIcon
                    title={issue.title}
                    description={
                      <>
                        <p>{issue.detail}</p>
                        <p>{issue.action}</p>
                        <Link to={issue.link}>前往核对</Link>
                      </>
                    }
                  />
                ))}
                {report.truncated && (
                  <Typography.Text type="secondary">
                    当前显示前 {report.issues.length} 项，处理后请重新检查。
                  </Typography.Text>
                )}
                <Typography.Text type="secondary">
                  历史范围：{report.history_start} 至 {report.history_end}
                </Typography.Text>
                {report.diner_count_basis_label && (
                  <Typography.Text type="secondary">
                    人次依据：{report.diner_count_basis_label}
                  </Typography.Text>
                )}
                <Typography.Text type="secondary">{report.note}</Typography.Text>
                <Typography.Text type="secondary">
                  检查时间：{new Date(report.checked_at).toLocaleString('zh-CN')}
                </Typography.Text>
              </Space>
            ),
          },
        ]}
      />
    </>
  );
}

/** 复用业务服务的只读检查，不在前端另设生成门槛。 */
export function PlanReadinessPanel({ onDate, mealType }: { onDate: string; mealType?: MealType }) {
  const revision = useMenuDataRevision();
  const meals = MEALS.filter((row) => !mealType || row.value === mealType);
  const queries = useQueries({
    queries: meals.map((row) => ({
      queryKey: ['menu-plan', 'readiness', onDate, row.value, revision],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        fetchPlanReadiness(onDate, row.value, signal),
      staleTime: 0,
      refetchOnWindowFocus: true,
    })),
  });
  return (
    <section className="zw-plan-readiness" aria-label="排餐前数据检查">
      <div className="zw-plan-readiness-heading">
        <div>
          <Typography.Title level={5}>排餐前，先看数据是否齐备</Typography.Title>
          <Typography.Text type="secondary">
            {onDate} · 检查菜品、配方、单价与本餐次历史；最终方案仍以实际生成校验为准。
          </Typography.Text>
        </div>
        <Button
          icon={<ReloadOutlined aria-hidden />}
          loading={queries.some((query) => query.isFetching)}
          onClick={() => void Promise.all(queries.map((query) => query.refetch()))}
        >
          重新检查
        </Button>
      </div>
      <div className="zw-plan-readiness-grid">
        {meals.map((row, index) => {
          const query = queries[index];
          return (
            <Card key={`${onDate}-${row.value}`} size="small" title={row.label}>
              {query.isPending ? (
                <Skeleton active paragraph={{ rows: 2 }} title={false} />
              ) : query.isError ? (
                <Alert
                  type="warning"
                  showIcon
                  title="本次检查未完成"
                  description={
                    query.error instanceof ApiError
                      ? query.error.message
                      : '暂时无法读取数据，请重新检查。'
                  }
                />
              ) : query.data ? (
                <Report report={query.data} />
              ) : null}
            </Card>
          );
        })}
      </div>
    </section>
  );
}
