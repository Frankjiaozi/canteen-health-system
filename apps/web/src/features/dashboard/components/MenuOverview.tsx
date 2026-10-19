import { Card, Col, Empty, Row, Skeleton, Space, Tag, Typography } from 'antd';
import { useMenuOverview } from '../hooks/useDashboard';
import { trimDecimal } from '../lib/format';
import type { MenuOverviewMeal } from '../types';

const STATUS_COLOR = {
  ACTUAL: 'green',
  PLANNED: 'blue',
  NOT_PLANNED: 'default',
} as const;

function MealCard({ meal }: { meal: MenuOverviewMeal }) {
  return (
    <Card
      size="small"
      title={
        <Space size={6}>
          <span>{meal.meal_type_label}</span>
          <Tag color={STATUS_COLOR[meal.status]}>{meal.status_label}</Tag>
        </Space>
      }
      extra={
        meal.diner_count != null ? (
          <Typography.Text type="secondary">{meal.diner_count} 人次</Typography.Text>
        ) : null
      }
    >
      {meal.dishes.length ? (
        <Space orientation="vertical" size={7} style={{ width: '100%' }}>
          {meal.dishes.map((dish) => (
            <div
              key={dish.dish_id}
              style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}
            >
              <span>{dish.name}</span>
              <Typography.Text type="secondary">
                {dish.category_label} · {dish.cooking_method_label} ·{' '}
                {dish.planned_servings ? `${trimDecimal(dish.planned_servings)} 份` : '份数未填'}
              </Typography.Text>
            </div>
          ))}
        </Space>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={meal.status === 'NOT_PLANNED' ? '未安排' : '暂无菜品'}
        />
      )}
    </Card>
  );
}

export function MenuOverview() {
  const { data, isPending, isError } = useMenuOverview();

  if (isPending) return <Skeleton active />;
  if (isError) return <Empty description="菜单读取失败，请稍后重试" />;
  if (!data) return <Empty description="暂无菜单" />;

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={[16, 16]}>
        {data.days.map((day) => (
          <Col xs={24} key={day.date}>
            <Card size="small" title={`${day.day_label} · ${day.date}`}>
              <Row gutter={[12, 12]}>
                {day.meals.map((meal) => (
                  <Col xs={24} lg={8} key={meal.meal_type}>
                    <MealCard meal={meal} />
                  </Col>
                ))}
              </Row>
            </Card>
          </Col>
        ))}
      </Row>
    </Space>
  );
}
