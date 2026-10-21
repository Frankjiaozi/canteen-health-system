const LABELS: Record<string, string> = {
  meal_share: '本餐占全天份额',
  energy_target_kcal: '全天能量参考上限 / 千卡',
  energy_target_min_kcal: '全天能量参考下限 / 千卡',
  energy_source: '能量目标依据',
  energy_verified: '能量目标是否已核实',
  macro_source: '营养素换算口径',
  seasoning_source: '油盐糖求解口径',
  scope_notice: '适用范围提醒',
  scope_reference: '范围核对来源',
};

const HIDDEN_KEYS = new Set(['energy_source', 'energy_verified', 'scope_notice']);

export function basisRows(basis: Record<string, unknown>) {
  return Object.entries(basis)
    .filter(([key]) => !HIDDEN_KEYS.has(key))
    .map(([key, value]) => ({
      key,
      label: LABELS[key] ?? key,
      value:
        typeof value === 'boolean'
          ? value
            ? '已核实'
            : '尚未核实'
          : typeof value === 'object'
            ? JSON.stringify(value)
            : String(value),
    }));
}
