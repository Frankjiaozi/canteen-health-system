/**
 * 侧边栏导航结构。
 *
 * 分成三段是照着**使用动线**来的，不是按模块名归类：
 *
 * 1. 首页是数据看板：打开系统第一个问题是「今天怎么样」，而不是「我要去哪个模块」，
 *    看到缺口再点进对应模块处理。
 * 2. 「基础数据」是一次性建库：食材与调味料是原料，菜品与配方把它们组装成菜。
 *    三者有先后依赖，而且建好之后很少动——不该每天在侧边栏里占位置。
 * 3. 「日常运行」按时间顺序排：事前定菜单与采购、当天采集、每周抽样。
 *
 * 路径刻意保持扁平（`/admin/ingredients` 这类）：分组只影响导航怎么呈现，
 * 不影响地址，已有的收藏与深层链接不会失效。
 */

export interface NavLeaf {
  path: string;
  title: string;
  description: string;
}

export interface NavGroup {
  key: string;
  title: string;
  /** 这个分组回答的是哪一类问题。写清楚，免得以后往里塞不对的东西 */
  hint: string;
  children: NavLeaf[];
}

/** 首页。登录后落在这里。 */
export const HOME_NAV: NavLeaf = {
  path: '/admin',
  title: '数据看板',
  description: '当日供应结构与营养达成率、油盐糖趋势、人均摄入与浪费率',
};

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'basics',
    title: '基础数据',
    hint: '一次性建库，之后定期维护',
    children: [
      {
        path: '/admin/ingredients',
        title: '食材库',
        description: '食材及其营养成分数据，是全系统营养计算的基准',
      },
      {
        path: '/admin/seasonings',
        title: '调味料库',
        description: '油、盐、糖单独管理，它们是营养计算的关键变量与每日采集对象',
      },
      {
        path: '/admin/dishes',
        title: '菜品与配方',
        description: '菜品定义与标准配方，单份营养由配方推算得出',
      },
    ],
  },
  {
    key: 'routine',
    title: '日常运行',
    hint: '按时间顺序：事前定菜单与采购、当天采集、每周抽样',
    children: [
      {
        path: '/admin/recommendation',
        title: '菜单推荐',
        description: '在营养目标约束下生成菜单与份量建议，每条都有理由',
      },
      {
        path: '/admin/forecast',
        title: '采购预测',
        description: '按同星期历史与校历事件预测次日份数与食材需求',
      },
      {
        path: '/admin/collection',
        title: '每日采集',
        description: '每天只填几个数字：份数、人次、油盐糖总量、剩餐量',
      },
      {
        path: '/admin/calibration',
        title: '抽样纠偏',
        description: '每周挑几道菜称重实测，用实测与推算的差额修正调味料系数',
      },
    ],
  },
];

const ALL_LEAVES: NavLeaf[] = NAV_GROUPS.flatMap((group) => group.children);

/** 按路径找导航项；找不到返回 undefined（例如公开大屏不在导航里）。 */
export function findNavLeaf(path: string): NavLeaf | undefined {
  if (path === HOME_NAV.path) return HOME_NAV;
  return ALL_LEAVES.find((leaf) => leaf.path === path);
}

/** 某个路径属于哪个分组；首页不属于任何分组，返回 null。 */
export function findNavGroupKey(path: string): string | null {
  for (const group of NAV_GROUPS) {
    if (group.children.some((leaf) => leaf.path === path)) return group.key;
  }
  return null;
}
