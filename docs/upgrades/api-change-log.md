# 接口变更清单

## 2026-10-21 · A/B 双套餐

- `MenuSuggestionRead` 新增 `packages`、`package_shares`；`PlannedDishRead` 新增
  `package_codes/package_labels`。
- `MenuPlanResponse` 新增 `packages`、`package_shares`；`MenuPlanDish` 新增
  `package_codes/package_labels/is_shared`，同时保留扁平 `dishes` 供旧调用方读取。
- 后续采购口径修正：`MenuPlanResponse.package_shares` 已移除。`predicted_servings` 与
  `planned_servings` 对每道菜都是该菜自己的同星期销量预测，不再乘 A/B 占比。
- `MenuOverviewDish`、`LoggedDish`、`PublicDishCard` 新增套餐归属字段。
- 扁平 `dishes` 中同一道共用主食只出现一次；套餐视图通过 `dish_ids` 引用它。
- 采购份数以 `planned_servings` 为准；`predicted_servings` 仍是该菜在整餐的预测总份数。

更新：2026-10-19。记录当前主分支相对既有契约新增或改语义的接口。
字段的完整类型仍以 Pydantic/OpenAPI 和 `packages/api-client/src/schema.d.ts` 为准。

## 变更总览

| 编号 | 接口/模型 | 类型 | 兼容性 |
| --- | --- | --- | --- |
| API-01 | `POST /api/v1/menu-plan/generate-day` | 新增接口 | 不影响旧调用 |
| API-02 | `GET /api/v1/forecast/diner-count` | 新增接口 | 不影响旧调用 |
| API-03 | `/api/v1/menu-plan/generate` 的 `diner_count` 语义 | 语义变更 | 参数形状不变，结果口径变化 |
| API-04 | `PlanReadiness` 人数预测字段 | 新增可选字段 | 向后兼容 |
| API-05 | `GET /agent-api/v1/diner-forecast` | Agent 只读代理 | 新增 |
| API-06 | Agent 撤回接口请求体 | 兼容扩展 | 可选 `{"revision": N}`；不传兼容旧调用 |

## API-01：一天三餐生成

```text
POST /api/v1/menu-plan/generate-day
权限：RECORDER / CANTEEN_ADMIN
查询：on_date=YYYY-MM-DD
可选查询：budget_per_person、重复的 excluded_dish_ids
成功响应：DailyMenuPlanResponse
```

`DailyMenuPlanResponse`：

```text
date
meals[]                    每餐一个 MenuPlanResponse，顺序为早餐、午餐、晚餐
requirements[]             三餐相同食材/调味料合并后的采购项
total_cost                 合并采购金额
budget                     三餐预算之和
servings_note              采购量口径
fallback_dishes[]          份数回退的菜名
notes[]
suggestion_ids{}           餐次 -> suggestion_id
calculation_version
```

兼容性：新增路径，不改旧 `/generate` 的请求或响应结构。前端「一天三餐」模式消费本接口。

副作用：仍然只生成待确认建议；不会写正式菜单。正式写入仍走 `/sync` 或
`/{suggestion_id}/publish`。

## API-02：系统人数预测

```text
GET /api/v1/forecast/diner-count
权限：三个已登录角色
查询：on_date、meal_type
成功响应：DinerForecast
```

主要字段：

```text
on_date, meal_type, meal_type_label
predicted_diner_count: int | null
lower: int | null
upper: int | null
basis, basis_label
samples[{date, diner_count}]
calendar_note, note
```

语义：

- 取目标日期之前、同一餐次的最近历史；
- 排除异常日和法定假日；
- 取最近 6 个同星期几的中位数；
- 法定假日按日历系数折减，调休上班日按工作日基线；
- 样本不足才退回最近一次有效采集，并明确标记参考值；
- 不包含目标日及未来记录。

兼容性：新增只读接口。

## API-03：`/menu-plan/generate` 的 `diner_count` 语义

请求形状不变：

```text
POST /api/v1/menu-plan/generate?on_date=...&meal_type=...&diner_count=...
```

变化：

- **不填 `diner_count`**：以前按最近一次同餐次实际采集；现在按
  `/forecast/diner-count` 的系统预测。
- **显式填写 `diner_count`**：保留用户输入；单菜预测份数按
  `指定人次 ÷ 系统预计人次` 缩放；系统预计不可用时才退回最近同餐次有效采集。
- 返回的 `diner_count` 是本次实际用于计算的规模。
- `notes` 会说明使用了系统预计，并给出依据/区间（如果可用）。

兼容性：

- 字段名、类型、路径不变；
- 调用方不需要改参数；
- 但**相同请求在相同历史下可能得到不同的默认人数和采购量**，这是有意的语义变更。

消费方：

- 前端「明日菜单与采购」的生成结果；
- Agent `check_data_readiness` / `generate_menu_plan`；
- 任务条件面板的系统人数预测。

## API-04：`PlanReadiness` 新增人数预测字段

新增字段：

```text
predicted_diner_count: int | null
diner_count_lower: int | null
diner_count_upper: int | null
diner_count_basis: str | null
diner_count_basis_label: str | null
```

原有 `latest_diner_count` 仍保留，表示“最近一条有效采集”，不再冒充默认人数。

注意：体检字段是 `diner_count_lower` / `diner_count_upper`，
预测接口是 `lower` / `upper`，不要混用。

## API-05：Agent 人数预测代理

```text
GET /agent-api/v1/diner-forecast?on_date=...&meal_type=...
```

这是 Agent 对业务预测接口的只读透传，供任务条件面板预填人数。
当前 Agent 端没有显式 Pydantic 响应模型，前端仍使用手写 `DinerForecast` 类型；
这是已知待补齐项，不得因此伪造返回字段。

## API-06：Agent 撤回接口

```text
POST /agent-api/v1/sessions/{session_id}/undo
```

请求体可选：

```json
{"revision": 1}
```

传入时必须等于待撤回的已发布版本；不传则兼容旧行为，撤回最近一次有效发布。
业务侧 `POST /api/v1/menu-plan/{suggestion_id}/undo` 仍不接收请求体。

## 生成类型与消费位置

- 业务类型：`packages/api-client/src/schema.d.ts`，运行 `pnpm gen:api`。
- Agent 类型：`apps/web/src/features/agent/api/schema.d.ts`，运行 `pnpm gen:agent`。
- 生成文件不手改；契约变化先改 Pydantic/路由，再重新生成。

## 测试与样例

- S01–S06 样例位于 `apps/api/tests/contracts/`，使用当前 Pydantic 模型校验。
- 运行：`cd apps/api && python -m pytest tests/contracts`。
- 相关回归：`tests/modules/menuplan/`、`tests/modules/forecast/`、
  `tests/modules/recommendation/`、`tests/modules/nutrition/`。

## 计算版本

默认人数与情景缩放分母发生变化，属于计算语义变化。当前
`CALCULATION_VERSION` 已升级为 `menu-plan-20261019.1`。

- 旧待确认方案保留用于查看，但不能再直接发布；必须重新生成。
- 已发布旧版本保留历史回执，不因版本升级删除。
- S01 样例、接口变更清单和报告已同步新版本字符串。
