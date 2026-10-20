import { Spin, Typography } from 'antd';
import dayjs from 'dayjs';
import { useEffect } from 'react';
import { BaselineStage } from '../components/BaselineStage';
import { usePublicBoard } from '../hooks/usePublicBoard';
import { describeStatus, describeTarget, formatActual } from '../lib/standards';
import type { NutrientValue, PublicDishCard, StandardComparison } from '../types';

const COLORS = {
  ink: '#22312a',
  green: '#2f5a48',
  subtle: '#5f7166',
  muted: '#647268',
  line: '#e3dfd2',
  card: 'rgba(255, 253, 248, 0.9)',
  cardBorder: '1px solid rgba(47, 90, 72, 0.14)',
  cardShadow: '0 14px 38px rgba(34, 49, 42, 0.07)',
  warning: '#b07b32',
  error: '#ad4f3e',
} as const;

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
          color: COLORS.ink,
        }}
      >
        <Header
          date={data?.date}
          mealLabel={data?.meal_label}
          dinerCount={data?.diner_count ?? null}
          loading={isPending}
          isToday={data === undefined || data.date === dayjs().format('YYYY-MM-DD')}
        />

        <div style={{ flex: 1, minHeight: 0 }}>
          {isPending ? (
            <Centered>
              <Spin size="large" description="正在读取今日菜单…" />
            </Centered>
          ) : isError ? (
            <Centered>
              <Typography.Title level={3} style={{ color: COLORS.error, margin: 0 }}>
                暂时读不到今日数据，请稍后自动重试
              </Typography.Title>
            </Centered>
          ) : data && data.dishes.length > 0 ? (
            <DishGrid dishes={data.dishes} />
          ) : (
            <Centered>
              <Typography.Title level={3} style={{ color: COLORS.muted, margin: 0 }}>
                今日暂无已核算的菜品
              </Typography.Title>
            </Centered>
          )}
        </div>

        {data && data.standards.length > 0 ? <StandardBar standards={data.standards} /> : null}

        {data ? (
          <Typography.Text style={{ color: COLORS.muted, fontSize: 15, lineHeight: 1.5 }}>
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
  /** 看的是不是今天。带 ?date= 回看时标题不再写「今日」，免得自相矛盾 */
  isToday: boolean;
}

function Header({ date, mealLabel, dinerCount, loading, isToday }: HeaderProps) {
  const formatted = date ? dayjs(date).format('YYYY 年 M 月 D 日 dddd') : '——';

  return (
    <header
      style={{
        flexShrink: 0,
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
      }}
    >
      <div>
        <div
          style={{
            fontFamily: 'var(--zw-brand)',
            fontSize: 29,
            fontWeight: 600,
            letterSpacing: 3,
            color: COLORS.green,
          }}
        >
          知味 · 校园智慧膳食平台
        </div>
        <div
          style={{
            fontSize: 54,
            fontWeight: 600,
            fontFamily: 'var(--zw-serif)',
            letterSpacing: 2,
            marginTop: 8,
            lineHeight: 1.14,
            color: COLORS.ink,
          }}
        >
          {isToday ? '今日菜单与营养' : '菜单与营养'}
        </div>
      </div>
      <div style={{ textAlign: 'right', lineHeight: 1.6 }}>
        <div style={{ fontSize: 25, fontVariantNumeric: 'tabular-nums' }}>{formatted}</div>
        <div style={{ fontSize: 21, color: COLORS.subtle }}>
          {loading ? '读取中…' : `${mealLabel ?? '未安排'} · 就餐 ${dinerCount ?? '—'} 人次`}
        </div>
      </div>
    </header>
  );
}

function DishGrid({ dishes }: { dishes: PublicDishCard[] }) {
  // 一餐通常是五道菜（主食/汤/荤/半荤/素）。原来封顶 4 列，第五道会折到第二行，
  // 每张卡只剩一半高度，内容就压到下面的指南对照条上了。改成按实际菜数分列，
  // 够宽就一直是一行；真超过 6 道才折行，且行高由容器兜住、卡片自己裁剪。
  const columns = Math.max(1, Math.min(dishes.length, 6));

  return (
    <div
      data-testid="dish-grid"
      style={{
        height: '100%',
        // minHeight:0 + overflow:hidden：即使内容偏高也只裁卡片，绝不压到下面的对照条上
        minHeight: 0,
        overflow: 'hidden',
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
      data-testid="dish-card"
      style={{
        background: COLORS.card,
        border: COLORS.cardBorder,
        boxShadow: COLORS.cardShadow,
        borderRadius: 16,
        padding: '22px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        backdropFilter: 'blur(2px)',
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 34, fontWeight: 600, fontFamily: 'var(--zw-serif)' }}>
            {dish.name}
          </span>
          <span style={{ fontSize: 18, color: COLORS.subtle }}>
            {dish.category_label} · {dish.cooking_method_label}
          </span>
        </div>
        <div style={{ fontSize: 17, color: COLORS.muted, marginTop: 6 }}>
          每份 {formatServing(dish.standard_serving_g)} 克
          {dish.allergens.length > 0 ? ` · 含过敏原：${dish.allergens.join('、')}` : ''}
        </div>
        {/* 把数值来自哪一层写在卡面上：公示的数字要能自证口径，
            否则「抽样称重实测」和「按配方推算」在大屏上看起来一模一样 */}
        <div
          style={{
            display: 'inline-block',
            marginTop: 8,
            padding: '2px 10px',
            borderRadius: 999,
            fontSize: 15,
            color: dish.value_type === 'THEORETICAL' ? COLORS.subtle : COLORS.green,
            border: `1px solid ${
              dish.value_type === 'THEORETICAL'
                ? 'rgba(49, 92, 76, 0.24)'
                : 'rgba(49, 92, 76, 0.42)'
            }`,
          }}
        >
          {dish.value_type_label}
        </div>
      </div>

      {/* 五项指标在卡片内均匀铺开，避免下半部分留一大片空白 */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: 10,
          flex: 1,
        }}
      >
        {dish.nutrients.map((nutrient) => (
          <NutrientRow key={nutrient.code} nutrient={nutrient} />
        ))}
      </div>

      {dish.missing_nutrients.length > 0 ? (
        <div style={{ fontSize: 14, color: COLORS.warning }}>部分成分缺失，数值区间已相应放宽</div>
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
        borderBottom: `1px dashed ${COLORS.line}`,
        paddingBottom: 6,
      }}
    >
      <span style={{ fontSize: 22, color: COLORS.subtle }}>{nutrient.label}</span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontSize: 32, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
          {formatNutrientValue(nutrient)}
        </span>
        <span style={{ fontSize: 18, color: COLORS.subtle }}>{nutrient.unit}</span>
      </span>
    </div>
  );
}

function StandardBar({ standards }: { standards: StandardComparison[] }) {
  return (
    <div
      data-testid="standards-bar"
      style={{
        flexShrink: 0,
        display: 'grid',
        gridTemplateColumns: `repeat(${standards.length}, 1fr)`,
        gap: 16,
      }}
    >
      {standards.map((standard) => {
        const style = describeStatus(standard.status);
        const isUnknown = standard.status === 'unknown';
        return (
          <div
            key={standard.code}
            style={{
              background: COLORS.card,
              border: COLORS.cardBorder,
              boxShadow: COLORS.cardShadow,
              borderRadius: 12,
              padding: '14px 18px',
            }}
          >
            <div
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}
            >
              <span style={{ fontSize: 20, color: COLORS.subtle }}>{standard.label}</span>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 7,
                  fontSize: 18,
                  color: style.color,
                }}
              >
                <i
                  aria-hidden="true"
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: style.color,
                    opacity: isUnknown ? 0.5 : 1,
                  }}
                />
                {style.text}
              </span>
            </div>
            <div style={{ marginTop: 8, display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 34, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {formatActual(standard)}
              </span>
              {isUnknown ? null : (
                <span style={{ fontSize: 18, color: COLORS.subtle }}>{standard.unit}</span>
              )}
            </div>
            <div style={{ fontSize: 16, color: COLORS.muted, marginTop: 4 }}>
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

// 公示屏只保留读得出来的精度：克保留一位，毫克取整，避免 7.721 克这种冗余小数
function formatNutrientValue(nutrient: NutrientValue): string {
  const parsed = Number(nutrient.value);
  if (Number.isNaN(parsed)) return nutrient.value;
  const digits = nutrient.unit === '毫克' ? 0 : 1;
  return parsed.toFixed(digits).replace(/\.0$/, '');
}
