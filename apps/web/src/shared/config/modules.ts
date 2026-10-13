/** 系统模块清单。侧边栏与总览页共用同一份数据，避免两处各维护一遍。 */

export type ModuleStatus = 'ready' | 'planned';

export interface SystemModule {
  /** 前端路由 */
  path: string;
  title: string;
  /** 一句话说明这个模块解决什么问题 */
  description: string;
  /** 是否需要登录；公开大屏是唯一的免登录页面 */
  requiresAuth: boolean;
  status: ModuleStatus;
}

export const SYSTEM_MODULES: SystemModule[] = [
  {
    path: '/admin',
    title: '总览',
    description: '系统入口与模块进度',
    requiresAuth: true,
    status: 'ready',
  },
  {
    path: '/admin/ingredients',
    title: '食材库',
    description: '食材及其营养成分数据，是全系统营养计算的基准',
    requiresAuth: true,
    status: 'ready',
  },
  {
    path: '/admin/dishes',
    title: '菜品与配方',
    description: '菜品定义与标准配方，单份营养由配方推算得出',
    requiresAuth: true,
    status: 'planned',
  },
  {
    path: '/admin/collection',
    title: '每日采集',
    description: '每天只填几个数字：份数、人次、油盐糖总量、剩餐量',
    requiresAuth: true,
    status: 'planned',
  },
  {
    path: '/admin/dashboard',
    title: '数据看板',
    description: '油盐糖趋势、人均摄入对比、达标率与剩餐浪费率',
    requiresAuth: true,
    status: 'planned',
  },
  {
    path: '/admin/forecast',
    title: '采购预测',
    description: '按同星期历史与校历事件预测次日份数与食材需求',
    requiresAuth: true,
    status: 'planned',
  },
  {
    path: '/admin/recommendation',
    title: '菜单推荐',
    description: '在营养目标约束下生成菜单与份量建议，每条都有理由',
    requiresAuth: true,
    status: 'planned',
  },
  {
    path: '/display',
    title: '公开大屏',
    description: '今日菜单与每道菜营养指标，免登录展示',
    requiresAuth: false,
    status: 'planned',
  },
];
