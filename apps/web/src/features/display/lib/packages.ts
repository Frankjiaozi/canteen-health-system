import type { PublicDishCard } from '../types';

export const PACKAGE_OPTIONS = [
  { value: 'A', label: '套餐 A' },
  { value: 'B', label: '套餐 B' },
] as const;

export type DisplayPackage = (typeof PACKAGE_OPTIONS)[number]['value'];

export function availablePackages(dishes: PublicDishCard[] | undefined) {
  return PACKAGE_OPTIONS.filter((option) =>
    dishes?.some((dish) => dish.package_codes?.includes(option.value)),
  );
}

export function dishesForPackage(
  dishes: PublicDishCard[] | undefined,
  packageCode: DisplayPackage | null,
): PublicDishCard[] {
  if (!dishes || !packageCode) return dishes ?? [];
  return dishes.filter(
    (dish) => dish.package_codes?.includes('COMMON') || dish.package_codes?.includes(packageCode),
  );
}
