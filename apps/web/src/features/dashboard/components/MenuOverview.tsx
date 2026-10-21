import { Button, Card, Empty, Skeleton } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { DishImage } from '@/features/dish/components/DishImage';
import '@/features/dish/dish.css';
import { useMenuOverview } from '../hooks/useDashboard';
import { trimDecimal } from '../lib/format';
import type { MenuOverviewMeal } from '../types';

const STATUS_TONE = {
  ACTUAL: 'actual',
  PLANNED: 'planned',
  NOT_PLANNED: 'off',
} as const;

function MealColumn({ meal }: { meal: MenuOverviewMeal }) {
  const groups = meal.dishes.reduce<Record<string, MenuOverviewMeal['dishes']>>((result, dish) => {
    const key = dish.package_labels?.join(' / ') || '当前套餐';
    (result[key] ??= []).push(dish);
    return result;
  }, {});

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
        <div className="zw-menu-package-groups">
          {Object.entries(groups).map(([label, dishes]) => {
            const displayLabel =
              label === 'A/B 共用' && Object.keys(groups).length === 1 ? '统一供应' : label;
            return (
              <section className="zw-menu-package-group" key={label}>
                <div className="zw-menu-package-label">
                  <span>{displayLabel}</span>
                  <small>{dishes.length} 道</small>
                </div>
                <ul className="zw-menu-dishes">
                  {dishes.map((dish) => (
                    <li className="zw-menu-dish" key={dish.dish_id}>
                      <DishImage url={dish.image_url} name={dish.name} compact />
                      <span className="zw-menu-dish-name">{dish.name}</span>
                      <span className="zw-menu-dish-meta">
                        <span>
                          {dish.category_label} · {dish.cooking_method_label}
                        </span>
                        <span className="zw-menu-dish-servings">
                          {dish.planned_servings
                            ? `${trimDecimal(dish.planned_servings)} 份`
                            : '份数未填'}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      ) : (
        <p className="zw-menu-empty">{meal.status === 'NOT_PLANNED' ? '待安排' : '暂无菜品'}</p>
      )}
    </section>
  );
}

export function MenuOverview() {
  const { data, isPending, isError } = useMenuOverview();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  if (isPending) return <Skeleton active />;
  if (isError) return <Empty description="菜单读取失败，请稍后重试" />;
  if (!data) return <Empty description="暂无菜单" />;

  const fallbackIndex = data.days.findIndex((day) => day.date === data.today);
  const selectedIndex = selectedDate
    ? data.days.findIndex((day) => day.date === selectedDate)
    : fallbackIndex;
  const safeIndex = selectedIndex >= 0 ? selectedIndex : 0;
  const activeDay = data.days[safeIndex];
  if (!activeDay) return <Empty description="暂无菜单" />;

  return (
    <div className="zw-menu-overview">
      <div className="zw-menu-pager">
        <Button
          type="text"
          shape="circle"
          aria-label="上一页"
          icon={<LeftOutlined />}
          disabled={safeIndex === 0}
          onClick={() => setSelectedDate(data.days[safeIndex - 1]?.date ?? activeDay.date)}
        />
        <div className="zw-menu-page-indicator">
          <small>
            第 {safeIndex + 1} / {data.days.length} 页
          </small>
        </div>
        <Button
          type="text"
          shape="circle"
          aria-label="下一页"
          icon={<RightOutlined />}
          disabled={safeIndex === data.days.length - 1}
          onClick={() => setSelectedDate(data.days[safeIndex + 1]?.date ?? activeDay.date)}
        />
      </div>

      <Card
        className={`zw-menu-day${activeDay.date === data.today ? ' is-today' : ''}`}
        key={activeDay.date}
        styles={{ body: { padding: 0 } }}
        title={
          <div className="zw-menu-day-title">
            <span className="zw-menu-day-label">{activeDay.day_label}</span>
            <span className="zw-menu-day-date">{activeDay.date}</span>
          </div>
        }
      >
        <div className="zw-menu-meals">
          {activeDay.meals.map((meal) => (
            <MealColumn key={meal.meal_type} meal={meal} />
          ))}
        </div>
      </Card>
    </div>
  );
}
