# 双人开发共同契约

更新：2026-10-19；核对基线：当前主分支（含一天三餐、人数预测与 P0/P1 文案清理）。
本文件只约定双方接口和责任，详细任务分别见 [Ethan：前端与 Agent](ethan-frontend-agent.md)
和 [协作者：业务后端](partner-backend-data.md)。文中改进项是待开发要求；接口事实以当前路由与 Pydantic 模型为准。

> 2026-10-19 真实代码核对说明：已按当前路由修正 Agent 撤回接口的请求体描述与人数默认口径。
> 本次只改文档与路由说明，不改业务计算。

## 1. 单一职责与共享文件

- Ethan：`apps/web/**`、`apps/agent/**`，完整前端、模型编排、会话与 Agent 协议。
- 协作者：`apps/api/**`、业务迁移、算法、数据及业务生成类型。
- 唯一助手入口 `/admin/agent`；不恢复已删除的业务助手。
- Agent 通过固定 HTTP 地址转发当前账号 Cookie，不访问业务数据库，不 import 业务内部函数。业务运行不依赖模型和 Agent。
- 单食堂共享业务数据；Agent 对话按账号隔离。当前不承诺多租户或学生健康档案。
- 根依赖、锁文件、CI、Compose、启动脚本和本文每次指定一个编辑者。契约变更先说明消费者影响，再由各自所有者修改代码。
- 生成文件不手改。协作者运行 `pnpm gen:api` 维护 `packages/api-client/src/schema.d.ts`；Ethan 运行 `pnpm gen:agent` 维护前端 Agent schema。

## 2. 认证、角色和错误

前端与 Agent 使用现有 Cookie 登录态。模型不持有管理员身份。`RECORDER` 与 `CANTEEN_ADMIN` 可以生成、发布、撤回和执行允许的业务写操作；`SCHOOL_ADMIN` 只读分析。页面隐藏按钮不能替代后端鉴权。

常见 HTTP 状态：401 未登录、403 无权限、404 资源不存在、409 版本或并发冲突、422 参数/业务条件不满足。具体响应体遵循各接口现有模型，不假设所有错误都有同一层级的 `message` 字段。客户端统一转换成可读提示，同时保留可排查的错误代码。

日志、文档、样例和 Git 禁止包含真实模型密钥、完整 Cookie 或本地环境文件内容。演示数据与真实经营数据必须区分。

## 3. 业务菜单接口

以下路径统一位于 `/api/v1/menu-plan`：

| 方法与路径 | 输入 | 语义 |
| --- | --- | --- |
| GET `/readiness` | `on_date`、`meal_type`、重复的 `excluded_dish_ids` 查询参数 | 只读数据体检 |
| POST `/generate` | 日期、餐次、可选人数为查询参数；可选 JSON 约束体 | 生成并保存建议快照，不发布正式菜单 |
| POST `/{suggestion_id}/publish` | JSON：`snapshot_token`、`expected_menu_token` | 核验版本后人工发布 |
| POST `/{suggestion_id}/undo` | 无请求体 | 检查可恢复条件后撤回 |
| POST `/sync` | 日期、餐次、建议 ID 查询参数 | 复用统一发布保护 |
| POST `/batch/generate` | 起止日期、餐次查询参数 | 批量生成 |
| POST `/batch/sync` | 起止日期、餐次查询参数 | 批量同步，保留统一保护 |

生成请求的约束体示例：

```json
{"budget_per_person":"8.00","excluded_dish_ids":[]}
```

餐次枚举 `BREAKFAST`、`LUNCH`、`DINNER`。人数不填时运行逻辑采用系统预测；预测不可用时提示用户填写。`/menu-plan/generate` 的路由说明已同步为系统预测口径。

`MenuPlanResponse` 当前主要字段如下；完整必填性、类型与嵌套结构以生成类型为准：

```text
date, meal_type, meal_type_label, diner_count, suggestion_id
dishes, gaps, reasons, requirements
total_cost, budget, target_basis, missing_price_warning
excluded_dishes, calendar_notes, skipped_predictions, servings_note, notes
snapshot_token, expected_menu_token, budget_per_person
requested_excluded_dish_ids, calculation_version
```

菜品项包括菜品 ID/名称/类别/烹饪方式、`energy_kcal`、`salt_g`、`popularity`、`nutrition_basis`、`predicted_servings`、`predicted_basis_label`、`prediction_fallback`、`planned_servings`。金额和多项数值使用十进制字符串，前端不改变单位或自行补公式。

`snapshot_token` 和 `expected_menu_token` 均为 64 位小写十六进制字符串。发布请求不接受额外字段。不得在客户端伪造 token 或为了成功而绕过冲突。

## 4. 数据体检与人数预测

体检状态为 `blocked`、`attention`、`ready`；其中 `issues[].severity` 只有 `blocking`、`warning`，不能混用状态和严重程度。

问题项包含 `code`、`title`、`detail`、`action`、`link` 和可选实体 ID。当前还返回候选数量、历史范围、缺价格/营养数量、预测人数与区间、问题截断信息等。`ready` 仅说明体检条件，不证明求解一定可行或全部营养达标。

业务人数接口：`GET /api/v1/forecast/diner-count?on_date=...&meal_type=...`。

```text
on_date, meal_type, meal_type_label
predicted_diner_count: integer | null
lower: integer | null, upper: integer | null
basis, basis_label, samples[{date,diner_count}], calendar_note, note
```

体检中的区间字段名是 `diner_count_lower` / `diner_count_upper`，不能直接套用预测接口的 `lower` / `upper`。实际最近人数与预测人数分别表达。

其他当前预测路由：GET `/api/v1/forecast/backtest`（`days` 7—180）；POST `/api/v1/forecast/run`（会保存预测，不作为普通只读查询）；GET `/api/v1/forecast/holidays`；PATCH `/api/v1/forecast/holidays/{holiday_id}`。写接口仍按角色校验。

## 5. Agent 接口与事件

以下路径统一位于 `/agent-api/v1`，除独立健康检查外均需登录：

| 方法与路径 | 说明 |
| --- | --- |
| GET `/status` | 模式、模型名、能力、数据提示和是否允许排餐 |
| GET `/dishes` | 用于条件选择的菜品 |
| GET `/diner-forecast` | 日期、餐次人数预测；待补显式 Agent 响应模型 |
| GET / POST `/sessions` | 列会话 / 新建会话 |
| GET `/sessions/{session_id}` | 当前账号的会话 |
| POST `/sessions/{session_id}/messages` | NDJSON 任务执行 |
| POST `/sessions/{session_id}/publish` | JSON `{ "revision": N }` |
| POST `/sessions/{session_id}/undo` | 可选 JSON `{ "revision": N }`；不传兼容旧调用，撤回最近一次有效发布 |
| GET `/sessions/{session_id}/purchase.csv?revision=N` | 指定版本采购导出 |
| GET `/sessions/{session_id}/review.md` | 核查报告 |
| GET `/sessions/{session_id}/report.html?revision=N&download=false` | 指定版本完整报告 |

消息请求包含 `content`、`parameters`、UUID `request_id`、非负整数 `expected_revision`。`parameters` 包含日期、餐次、可空人数、每人预算、排除菜品 ID。人数范围 1—100000，预算大于 0 且不超过 1000、最多两位小数，排除项最多 50；请求禁止未声明顶层字段。

流事件结构：

```text
status { message, mode }
trace  { trace: { id, tool, label, status, detail } }
error  { message, code }
done   { conversation }
```

轨迹状态 `running`、`success`、`error`。`error` 之后可能仍有 `done`；只有最终会话能确认保存状态。断流不能直接当任务成功。同 UUID 同内容可重放，不同内容冲突；同会话任务、发布与撤回须有并发保护。

当前 11 个模型工具和 5 轮循环见 Ethan 文档。模型没有直接发布、撤回或任意 SQL/HTTP 写入工具。若未来新增工具，应先说明权限、参数、失败和审计，再扩展白名单。

## 6. 方案与业务一致性

Agent 方案版本包含 `revision`、`created_at`、`parameters`、`result`、`publication`、`undone`、`readiness`、`data_notice`。撤回不删除原发布收据；展示需共同判断 `publication` 与 `undone`。

业务发布在同日期餐次锁内核验目录和正式菜单版本，拒绝覆盖实际采集。撤回必须拒绝覆盖后续编辑或实际记录。重复发布应幂等；当前不额外承诺撤回重复成功，也不虚构 `already_undone` 字段。

当前计算版本字符串为 `menu-plan-20261019.1`。默认人数与情景缩放分母变化后，旧待确认方案需重新生成才能发布；已发布旧版本的历史回执保留。

## 7. 共同样例与变更流程

双方使用六类样例：S01 正常生成、S02 缺历史/无菜、S03 缺价格/营养、S04 参数/权限错误、S05 发布与冲突、S06 撤回与冲突。样例由协作者按实际模型交付，Ethan 在模拟测试及页面验收中复用。样例路径和版本写入交付记录，不声称本文已创建样例代码。

接口变更按以下顺序进行：提出字段、类型、单位、空值、角色、错误和兼容方案 → 双方确认消费影响 → 业务或 Agent 所有者修改模型及测试 → 生成类型并交付样例 → 消费者适配 → 联合验收。

不兼容变更不得仅改生成文件。分支独立提交，集成者统一合并，共享文件一次只由一人修改。不得用强制覆盖主分支或清空数据库解决联调问题。

完成记录区分模拟测试、真实模型冒烟和业务数据库回归。没有运行的检查如实标明；历史验证结果不自动证明新代码通过。生产配置、迁移或实际数据操作按真实影响另行处理，文档不构成发布授权。
