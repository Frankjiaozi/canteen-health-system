# 知味 Agent 后端交付

本轮依据 `docs/upgrades/ethan-frontend-agent.md` 的 A01—A06 完善已有独立服务。代码基线为 `3e6ddeb`，Agent 业务开发仅修改 `apps/agent/**`；后续 CI 修复另同步了前端消费的自动生成类型，未修改页面、交互、业务 API、数据库迁移或共享启动配置。

## 本轮行为

| 任务 | 实现与验证范围 |
| --- | --- |
| A01 条件与上下文 | 以当前消息和条件面板为准；用户明确的日期、餐次、人数、预算、排除项优先于模型参数；未明确的变更先澄清。澄清工具也不能把模型猜测写成已知条件。沿用原有多轮澄清、条件保留和账号隔离。 |
| A02 工具与依据 | 保留 11 个工具；新增排除 ID 的业务记录核验；固定业务地址下的相对路径校验；兼容业务错误的 `message`、字符串 `detail` 和字段错误列表；当日供应截断结果显式标记。 |
| A03 执行与恢复 | 校验模型回答、工具调用结构、唯一调用 ID 和参数；区分模型/业务超时；参数错误可在原循环修正；连续空回复、轮次耗尽明确失败。断流及意外异常保存已有结果与失败记录，同请求重放不重新执行。仍保留 5 轮、180 秒和会话锁。 |
| A04 发布与撤回 | 撤回可传版本号并严格核对；已撤回版本不能重新发布；摘要、CSV、HTML 统一展示撤回状态，报告保留原发布与撤回信息。业务事务和冲突检查仍全部交给业务 API。 |
| A05 模型、隔离与导出 | 默认测试均模拟模型及业务 HTTP；新增独立的人工模型协议冒烟入口；意外异常日志只写会话与异常类型，避免回显异常原文；Markdown 保留核查当时的数据说明；零成本与缺成本分开显示。 |
| A06 契约 | `/diner-forecast` 新增显式响应模型及响应校验；预测人数、上下界保留空值，零值不会变成缺失。生成类型保留在本目录，并同步正式消费文件。 |

`parameters` 继续是请求中完整的当前条件。连续修改时，客户端应携带上一版或待澄清任务的条件；服务不会从其他会话借用条件。难以确认的自然语言、中文数字或特殊膳食要求会要求补充明确条件，不猜测执行。

## 兼容与后续前端接入

- `POST /agent-api/v1/sessions/{id}/undo` 新增可选请求体 `{"revision": 1}`，版本指向待撤回的已发布版本，不一定等于最新草案版本。错误版本返回 409。
- 无请求体调用暂时保留现有“撤回最近有效发布”的行为，使当前前端继续可用。后续前端应传入用户确认的发布版本。
- 已撤回版本再次发布返回 409，需要重新生成；不把业务历史回执误当成重新发布成功。
- `ReviewReport.data_notice` 为新增可选字段，旧 SQLite 记录可直接读取，无需迁移。
- 新增错误码包括 `business_timeout`、`model_timeout`、`invalid_model_response`、`model_empty_response`、`tool_limit`。`error` 后仍可能有保存状态的 `done`；断流时没有 `done`，应刷新会话。重放原请求仅取保存结果，需要继续执行时使用新请求 ID。
- 生成类型：`contracts/schema.d.ts`。后续 CI 修复已将同一份生成结果同步到 `apps/web/src/features/agent/api/schema.d.ts`，满足仓库契约一致性检查；只同步类型，不改页面或交互。

## 检查与契约生成

在仓库根目录执行 Agent 专用导出：

```powershell
node apps/agent/scripts/export-contracts.mjs
```

导出时强制使用规则模式、空模型配置和临时 SQLite，不连接模型、不触碰现有会话库。`contracts/openapi.json` 沿用仓库约定不入库，TypeScript 类型需要保留。工作区 Node 依赖正常时不需要额外配置。

本机工作区的 Node 依赖链接仍指向旧路径。此次只在忽略提交的 `output/agent-contract-tooling-20261019` 安装了 `openapi-typescript@7.13.0`、`prettier@3.9.10`、`typescript@5.9.3` 用于契约检查，没有重装工作区依赖。此时导出可使用：

```powershell
$env:AGENT_CONTRACT_TOOLING = (Resolve-Path 'output/agent-contract-tooling-20261019').Path
node apps/agent/scripts/export-contracts.mjs
```

Python 检查在 `apps/agent` 目录执行，使用项目已有解释器入口：

```powershell
node ../../scripts/py.mjs -m ruff check .
node ../../scripts/py.mjs -m ruff format --check .
node ../../scripts/py.mjs -m pytest
```

这三条对应原 `pnpm lint:agent`、`pnpm test:agent` 的实际命令；直接执行可避开本机 pnpm 自动尝试修复依赖链接的步骤。

## 人工真实模型检查

测试使用显式的测试配置和模拟响应，不调用模型供应商。需要人工检查时，在本地环境配置支持 Chat Completions tools 的真实服务，然后在 `apps/agent` 执行：

```powershell
node ../../scripts/py.mjs -m zhiwei_agent.smoke --run
```

该命令只发送一次可能计费的模型请求，检查 `list_dishes` 的工具协议，不执行业务查询或发布，也不输出供应商回答原文。未加 `--run` 时不联网。该检查不能代替真实模型多轮对话和完整业务演示。

## 验收记录与边界

2026-10-19：原有 52 项测试加新增 51 项，共 **103 passed**。新增回归覆盖连续修改条件、账号隔离、空预测及空区间、错误契约、模型参数越权覆盖、歧义菜名、未知 ID、参数修正、空响应、超时、请求重放、会话锁、撤回版本、快照导出、日志脱敏、事实回答及只读请求识别。自动测试的 SQLite 使用临时文件，业务 HTTP 与模型均为模拟响应。

随后已完成真实 `deepseek-flash`、业务 FastAPI 和独立演示 PostgreSQL 联调，详见 [真实联调记录](LIVE-VERIFICATION.md)。新增事实回答模板，修复模型混淆单份与人均、补算预算占比的问题；并修复“只检查数据，不要生成菜单”被误判为取消的问题。

未运行浏览器、完整 Playwright E2E 或生产部署；没有据此宣称业务计算完全正确或营养达标。真实供应商超时/断流本轮未自然出现，对应恢复行为仍以模拟回归为依据。现有 Starlette/HTTPX 弃用提示保留，未扩大依赖升级范围。

CI 补充：开发提交 `b3a4dd6` 的 Agent、业务后端、前端和 Playwright 作业均通过，仅契约作业因正式消费的生成类型未同步而失败；后续修复保留该检查并补齐生成文件。
