import type { NutritionSummary } from '../types';
import { formatNutrient } from '@/features/ingredient/lib/query';

export function DishNutrition({ nutrition }: { nutrition?: NutritionSummary | null }) {
  return (
    <dl className="zw-dish-nutrition" aria-label="单份营养">
      {(
        [
          ['energy_kcal', '能量', '千卡'],
          ['protein_g', '蛋白质', '克'],
          ['fat_g', '脂肪', '克'],
          ['carb_g', '碳水化合物', '克'],
          ['sodium_mg', '钠', '毫克'],
        ] as const
      ).map(([key, label, unit]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>
            {formatNutrient(nutrition?.[key], 1)} <small>{unit}</small>
          </dd>
        </div>
      ))}
    </dl>
  );
}
