import { Spin, Typography } from 'antd';
import dayjs from 'dayjs';
import { useEffect } from 'react';
import { BaselineStage } from '../components/BaselineStage';
import { usePublicBoard } from '../hooks/usePublicBoard';
import { describeStatus, describeTarget, formatActual } from '../lib/standards';
import type { NutrientValue, PublicDishCard, StandardComparison } from '../types';

const CARD_BACKGROUND = 'rgba(255, 255, 255, 0.06)';
const CARD_BORDER = '1px solid rgba(120, 180, 255, 0.22)';

export function DisplayPage() {
  const { data, isPending, isError } = usePublicBoard();

  useEffect(() => {
    // 公开大屏是纯展示页，禁止误滚动与文本选中
    document.body.classList.add('is-display-mode');
    return () => document.body.classList.remove('is-display-mode');
  }, []);

  return (
    <BaselineStage>
      <div
        style={{
          width: '100%',
          height: '100%',
          padding: '40px 56px 32px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 24,
          color: '#eaf2ff',
        }}
      >
        <Header
          date={data?.date}
          mealLabel={data?.meal_label}
          dinerCount={data?.diner_count ?? null}
          loading={isPending}
        />

        <div style={{ flex: 1, minHeight: 0 }}>
          {isPending ? (
            <Centered>
              <Spin size="large" description="正在读取今日菜单…" />
            </Centered>
          ) : isError ? (
            <Centered>
              <Typography.Title level={3} style={{ color: '#ffc53d', margin: 0 }}>
                暂时读不到今日数据，请稍后自动重试
              </Typography.Title>
            </Centered>
          ) : data && data.dishes.length > 0 ? (
            <DishGrid dishes={data.dishes} />
          ) : (
            <Centered>
              <Typography.Title level={3} style={{ color: '#8fa6c4', margin: 0 }}>
                今日暂无已核算的菜品
              </Typography.Title>
            </Centered>
          )}
        </div>

        {data && data.standards.length > 0 ? <StandardBar standards={data.standards} /> : null}

        {data ? (
          <Typography.Text style={{ color: '#7f93ad', fontSize: 15, lineHeight: 1.5 }}>
            {data.disclaimer}
          </Typography.Text>
        ) : null}
      </div>
    </BaselineStage>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      {children}
    </div>
  );
}

interface HeaderProps {
  date?: string;
  mealLabel?: string;
  dinerCount: number | null;
  loading: boolean;
}

function Header({ date, mealLabel, dinerCount, loading }: HeaderProps) {
  const formatted = date ? dayjs(date).format('YYYY 年 M 月 D 日 dddd') : '——';

  return (
    <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
      <div>
        <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: 2 }}>食堂健康管理系统</div>
        <div style={{ fontSize: 52, fontWeight: 700, marginTop: 8, lineHeight: 1.1 }}>
          今日菜单与营养
        </div>
      </div>
      <div style={{ textAlign: 'right', lineHeight: 1.6 }}>
        <div style={{ fontSize: 26 }}>{formatted}</div>
        <div style={{ fontSize: 22, color: '#9fc0e8' }}>
          {loading ? '读取中…' : `${mealLabel ?? '未安排'} · 就餐 ${dinerCount ?? '—'} 人次`}
        </div>
      </div>
    </header>
  );
}

function DishGrid({ dishes }: { dishes: PublicDishCard[] }) {
  const columns = Math.min(dishes.length, 4);

  return (
    <div
      style={{
        height: '100%',
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gridAutoRows: '1fr',
        gap: 20,
      }}
    >
      {dishes.map((dish) => (
        <DishCard key={dish.dish_id} dish={dish} />
      ))}
    </div>
  );
}

function DishCard({ dish }: { dish: PublicDishCard }) {
  return (
    <section
      style={{
        background: CARD_BACKGROUND,
        border: CARD_BORDER,
        borderRadius: 16,
        padding: '22px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        backdropFilter: 'blur(2px)',
      }}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 34, fontWeight: 600 }}>{dish.name}</span>
          <span style={{ fontSize: 18, color: '#9fc0e8' }}>
            {dish.category_label} · {dish.cooking_method_label}
          </span>
        </div>
        <div style={{ fontSize: 17, color: '#8fa6c4', marginTop: 6 }}>
          每份 {formatServing(dish.standard_serving_g)} 克
          {dish.allergens.length > 0 ? ` · 含过敏原：${dish.allergens.join('、')}` : ''}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
        {dish.nutrients.map((nutrient) => (
          <NutrientRow key={nutrient.code} nutrient={nutrient} />
        ))}
      </div>

      {dish.missing_nutrients.length > 0 ? (
        <div style={{ fontSize: 14, color: '#ffc53d' }}>部分成分缺失，数值区间已相应放宽</div>
      ) : null}
    </section>
  );
}

function NutrientRow({ nutrient }: { nutrient: NutrientValue }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        borderBottom: '1px dashed rgba(120, 180, 255, 0.18)',
        paddingBottom: 6,
      }}
    >
      <span style={{ fontSize: 22, color: '#c7d8ee' }}>{nutrient.label}</span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontSize: 32, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
          {nutrient.value}
        </span>
        <span style={{ fontSize: 18, color: '#9fc0e8' }}>{nutrient.unit}</span>
      </span>
    </div>
  );
}

function StandardBar({ standards }: { standards: StandardComparison[] }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${standards.length}, 1fr)`,
        gap: 16,
      }}
    >
      {standards.map((standard) => {
        const style = describeStatus(standard.status);
        return (
          <div
            key={standard.code}
            style={{
              background: CARD_BACKGROUND,
              border: CARD_BORDER,
              borderLeft: `4px solid ${style.color}`,
              borderRadius: 12,
              padding: '14px 18px',
            }}
          >
            <div
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}
            >
              <span style={{ fontSize: 20, color: '#c7d8ee' }}>{standard.label}</span>
              <span style={{ fontSize: 18, color: style.color }}>{style.text}</span>
            </div>
            <div style={{ marginTop: 8, display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 34, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {formatActual(standard)}
              </span>
              <span style={{ fontSize: 18, color: '#9fc0e8' }}>{standard.unit}</span>
            </div>
            <div style={{ fontSize: 16, color: '#8fa6c4', marginTop: 4 }}>
              {describeTarget(standard)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function formatServing(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return value;
  return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(1);
}
