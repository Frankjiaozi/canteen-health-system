import { Card, Empty, Skeleton } from 'antd';
import { useMenuOverview } from '../hooks/useDashboard';
import { trimDecimal } from '../lib/format';
import type { MenuOverviewMeal } from '../types';

const STATUS_TONE = {
  ACTUAL: 'actual',
  PLANNED: 'planned',
  NOT_PLANNED: 'off',
} as const;

function MealColumn({ meal }: { meal: MenuOverviewMeal }) {
  return (
    <section className="zw-menu-meal">
      <header className="zw-menu-meal-head">
        <div className="zw-menu-meal-name">
          <h3>{meal.meal_type_label}</h3>
          <span className={`zw-menu-status is-${STATUS_TONE[meal.status]}`}>
            <i aria-hidden="true" />
            {meal.status_label}
          </span>
        </div>
        {meal.diner_count != null ? (
          <span className="zw-menu-diner">{meal.diner_count} 人次</span>
        ) : null}
      </header>

      {meal.dishes.length ? (
        <ul className="zw-menu-dishes">
          {meal.dishes.map((dish) => (
            <li className="zw-menu-dish" key={dish.dish_id}>
              <span className="zw-menu-dish-name">{dish.name}</span>
              <span className="zw-menu-dish-meta">
                <span>
                  {dish.category_label} · {dish.cooking_method_label}
                </span>
                <span className="zw-menu-dish-servings">
                  {dish.planned_servings ? `${trimDecimal(dish.planned_servings)} 份` : '份数未填'}
                </span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="zw-menu-empty">{meal.status === 'NOT_PLANNED' ? '待安排' : '暂无菜品'}</p>
      )}
    </section>
  );
}

export function MenuOverview() {
  const { data, isPending, isError } = useMenuOverview();

  if (isPending) return <Skeleton active />;
  if (isError) return <Empty description="菜单读取失败，请稍后重试" />;
  if (!data) return <Empty description="暂无菜单" />;

  return (
    <div className="zw-menu-overview">
      {data.days.map((day) => (
        <Card
          className={`zw-menu-day${day.date === data.today ? ' is-today' : ''}`}
          key={day.date}
          styles={{ body: { padding: 0 } }}
          title={
            <div className="zw-menu-day-title">
              <span className="zw-menu-day-label">{day.day_label}</span>
              <span className="zw-menu-day-date">{day.date}</span>
            </div>
          }
        >
          <div className="zw-menu-meals">
            {day.meals.map((meal) => (
              <MealColumn key={meal.meal_type} meal={meal} />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
