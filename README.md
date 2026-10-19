# 知味 · 校园智慧膳食平台

本地项目名：知味（Zhiwei）。基于 [Frankjiaozi/canteen-health-system](https://github.com/Frankjiaozi/canteen-health-system) 继续开发，保留原仓库历史与来源。

把食堂每天采购与投料的原始数据，变成每道菜的营养数据和第二天的采购与菜单决策，同时把学生餐的营养构成公开给学生。

完整需求见 [canteen-requirements.md](./canteen-requirements.md)。

## Agent 升级与双人协作

新增 `/admin/agent` 知味膳食助手：生成前数据体检、多轮补充条件、安排菜单和采购、调整人数/预算与排除菜品、多版比较、记录核查、人工确认发布、CSV/Markdown 与完整离线 HTML 报告导出。所有业务数字由业务算法与接口计算。无模型密钥时明确显示规则模式；真实模型接入需配置后验收。

- [Ethan：前端、视觉与 Agent 开发指南](docs/upgrades/ethan-frontend-agent.md)
- [协作者：业务后端与数据开发指南](docs/upgrades/partner-backend-data.md)
- [共同接口契约](docs/upgrades/shared-contract.md)
- [本次验证记录](docs/upgrades/verification.md)
- [五分钟演示与后续优先级](docs/upgrades/demo-script.md)

已有台账时，推荐 `pnpm dev:demo` 在**独立演示库**体验完整流程，不在原开发库执行种子重灌。演示数据均为合成，不代表真实食堂经营结果。`pnpm test:py` 也自动使用独立测试库。

## 系统形态

本系统只有三个可见终点，**没有学生端**——需求文档中的「学生端」对应的就是免登录的公开大屏：

| 界面 | 访问方式 | 内容 |
| --- | --- | --- |
| 食堂管理端 | 需登录（录入员 / 食堂管理员 / 学校管理方） | 基础数据建库、明日菜单与采购、每日采集、抽样纠偏、看板，以及一个助手：左侧「知味膳食助手」（数据体检 → 生成方案 → 版本对比 → 人工发布 / 撤回） |
| 公开大屏 | **免登录** | 今日菜单、每道菜营养指标、膳食指南对照条 |
| 管理端看板 | 需登录 | 油盐糖趋势、人均摄入对比、达标率、剩餐浪费率 |

## 技术选型

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.13 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 |
| 独立 Agent | Python 3.13 · FastAPI（独立进程与镜像）· 自己的 SQLite · Chat Completions 兼容的模型适配 |
| 数据库 | PostgreSQL 17 |
| 前端 | React 19 · Vite 8 · TypeScript 5.9 · Ant Design 6 · TanStack Query · Zustand · React Router 7 · ECharts |
| 接口契约 | FastAPI OpenAPI → 自动生成 TypeScript 类型与客户端 |
| 认证 | JWT + httpOnly Cookie，三角色 RBAC |
| 工程 | pnpm workspace 单仓多包 · ruff / mypy / eslint / prettier · GitHub Actions |

> TypeScript 固定在 5.9.x：`typescript-eslint` 与 `openapi-typescript` 当前均不支持 TS 7。

## 目录结构

```
canteen_project/
├── apps/
│   ├── api/                 FastAPI 模块化单体
│   │   ├── app/
│   │   │   ├── core/        配置、安全、通用依赖、异常、日志
│   │   │   ├── db/          引擎会话、声明基类、迁移、种子数据
│   │   │   └── modules/     按业务域垂直切分（auth / ingredient / dish / ...）
│   │   ├── alembic/         数据库迁移
│   │   └── tests/
│   ├── agent/               独立 Agent 服务；只通过 HTTP 调业务 API
│   └── web/                 React 单页应用
│       ├── src/app/         路由、Provider、全局装配
│       ├── src/features/    业务域（auth / ingredient / display / dashboard / ...）
│       ├── src/layouts/     AdminLayout、DisplayLayout
│       └── src/shared/      UI、hooks、工具、常量
├── packages/api-client/     OpenAPI 生成的类型与请求客户端
├── infra/                   docker-compose、Dockerfile、nginx
├── scripts/                 生成 API 客户端等工程脚本
├── docs/                    架构、数据模型、开发指南、实施记录
└── canteen-requirements.md  需求文档
```

设计与分层约定见 [docs/architecture.md](./docs/architecture.md)，数据模型见
[docs/data-model.md](./docs/data-model.md)，日常开发见 [docs/dev-guide.md](./docs/dev-guide.md)，
内网自部署见 [docs/deployment.md](./docs/deployment.md)；
「哪一步为什么这么做、踩过什么坑」按模块记在
[docs/implementation-log.md](./docs/implementation-log.md)。

## 快速开始

前置：Node ≥ 22.12、pnpm、Python 3.13、Docker。

```bash
# 1) 起数据库
pnpm db:up

# 2) 安装前后端依赖
pnpm install

# 后端依赖装在 apps/api/.venv 里；pnpm 脚本会自动使用该虚拟环境，无需手动激活
python -m venv apps/api/.venv
node scripts/py.mjs -m pip install -e "apps/api[dev]" -e "apps/agent[dev]"

# 3) 准备后端环境变量
cp apps/api/.env.example apps/api/.env

# 4) 建表；仅全新空库执行种子准备，已有台账请用 pnpm dev:demo
pnpm db:migrate
pnpm db:seed

# 5) 按标准配方计算营养结果（营养引擎第一层）
pnpm db:compute

# 6) 启动三项服务（api:8000 / agent:8001 / web:5173）
pnpm dev
```

访问 <http://127.0.0.1:5173> 进入管理端，<http://127.0.0.1:5173/display> 进入免登录公开大屏。

## 账号注册与登录

- `/login`：登录已有账号；`/register`：开放注册，注册成功后自动登录。
- 新注册账号固定为食堂录入员，不允许在注册请求中指定管理员角色。现有三个演示角色继续可用。
- 登录名为 3–32 位字母、数字或下划线，不区分大小写；显示名称不能为空。
- 密码至少 8 个字符，包含字母和数字，UTF-8 编码长度不超过 72 字节；数据库只保存密码哈希。
- 刷新页面保留登录态；退出后清除登录态与前端缓存。未登录访问管理页面会先跳到登录页，登录或注册后返回原目标页面。
- 账号共享当前食堂的数据与现有角色权限，本版不提供多租户隔离、邮箱验证或找回密码。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `pnpm dev` | 检查环境并启动业务 API、Agent 与前端 |
| `pnpm dev:demo` | 用独立合成演示库启动，业务 API 为 8002 |
| `pnpm dev:check` | 只检查依赖、数据库和迁移，不改数据 |
| `pnpm dev:agent` | 只启动 Agent（改 Python 助手代码时用） |
| `pnpm test:agent` | 独立 Agent 协议、权限与失败恢复测试 |
| `pnpm gen:agent` | 生成 Agent 前端类型 |
| `pnpm db:up` / `pnpm db:down` | 启停开发数据库 |
| `pnpm db:migrate` / `pnpm db:downgrade` | 应用 / 回滚迁移 |
| `pnpm db:seed` | 灌入种子数据（幂等，可重复执行） |
| `pnpm db:compute` | 按标准配方重算最近 8 周的营养结果（幂等） |
| `pnpm nutrition:fetch` / `pnpm nutrition:verify` | 从食物成分查询平台取数并刷新营养快照 / 重新取数比对 |
| `pnpm nutrition:list 大白菜` | 列平台候选条目（人工挑条目时用） |
| `pnpm gen:api` | 导出后端 OpenAPI 并重新生成前端类型 |
| `pnpm lint` | ruff（API + Agent）+ eslint |
| `pnpm typecheck` | mypy + tsc |
| `pnpm test` | pytest（API，独立测试库）+ Agent pytest + vitest |
| `pnpm e2e` | Playwright 端到端 |
| `pnpm docker:up` | 构建并启动整套容器（内网自部署） |

## 交付进度

| # | 模块 | 状态 |
| --- | --- | --- |
| 1 | 仓库与工程基建 | ✅ 已完成 |
| 2 | 后端核心骨架 | ✅ 已完成 |
| 3 | 完整数据模型 + 迁移 | ✅ 已完成 |
| 4 | 种子数据 | ✅ 已完成 |
| 5 | 认证与 RBAC | ✅ 已完成 |
| 6 | 营养引擎第一层 | ✅ 已完成 |
| 7 | 食材库端到端切片 | ✅ 已完成 |
| 8 | 公开大屏 | ✅ 已完成 |
| 9 | 管理端看板 | ✅ 已完成 |
| 10 | 部署编排与文档 | ✅ 已完成 |
| 11 | 菜品与配方库写界面、调味料库、Excel 批量导入（M1） | ✅ 已完成 |
| 12 | 三层校准第二层（当日闭环）与第三层（抽样纠偏），并接入大屏与看板 | ✅ 已完成 |
| 13 | 每日采集录入页、抽样纠偏录入页、校准残差回写异常标记（M2 / M3） | ✅ 已完成 |
| 14 | 采集页离线队列：断网提交进本地队列，联网自动补交（M2 完整） | ✅ 已完成 |
| 15 | 消耗量预测：同星期移动平均 × 日历修正、采购建议单、MAPE 回测（M5） | ✅ 已完成 |
| 16 | 菜单推荐：整数规划求解、硬约束可验证、营养差距与推荐理由、人工可否决（M6） | ✅ 已完成 |
| 17 | 明日菜单与采购：把「菜单推荐」与「采购预测」合成一页，份数由预测给出，采购量按公斤与金额出单 | ✅ 已完成 |
| 18 | 同步至当日数据：次日采集的供应菜品按计划勾好、公开大屏当天早上即显示，采集提交后按实际覆盖 | ✅ 已完成 |
| 19 | 批量排菜单与一键导入：一次排一段（最长 31 天），逐日生成、整段轮换，确认后一键写进各天的当日数据 | ✅ 已完成 |
| 20 | AI 助手（阶段一）：管理端对话入口 + 只读工具集（食材/配方/菜单/指标/采集）+ 可切换的模型接入 | ✅ 已完成 |
| 21 | AI 助手（阶段二）：新增食材、新增菜品与配方两个写操作 + 确认卡片 + 对话留痕（审计） | ✅ 已完成 |
| 22 | AI 助手流式输出：模型侧真增量，边查边回（工具进度实时显示，回答逐字出现） | ✅ 已完成 |
| 23 | 助手写操作扩到改/停用/撤回：六个写工具都走确认卡片，已执行可一键撤回（带影响面与冲突保护） | ✅ 已完成 |
| 24 | 一句话录一餐（录入采集 / 调整菜单，可撤回）+ 通用只读出口 call_api（白名单 17 条只读接口，以本人身份调用） | ✅ 已完成 |
| 25 | 成本闸：单次调用输出上限 + 单轮对话 token 预算，超限停下来并说明；回答里附本轮用量 | ✅ 已完成 |
| 26 | 补上「排菜单」工具：一句话出方案（只算不改），确认后可写进当日数据并支持撤回 | ✅ 已完成 |
| 27 | 排菜单后直接把确认卡片摆出来（不用再补一句「同步」），并修掉「卡片被挤到看不见」的两处毛病 | ✅ 已完成 |
| 28 | 营养数据来源核对与重构：36 条食材/调味料逐条对齐《中国食物成分表》查询平台，落成可追溯快照 | ✅ 已完成 |
| 29 | 三餐分开：早餐固定供应（不走选菜）、午餐与晚餐不重样、补 5 道早餐菜与三餐历史 | ✅ 已完成 |
| 30 | 知味膳食助手（同伴实现，已合并）：独立 Agent 进程 + 数据体检 + 快照发布保护 + 报告导出 + 水墨进场 | ✅ 已完成 |
| 31 | 只保留一个 AI 入口：撤回从旧助手搬到 `menu-plan/{id}/undo` 并接进知味膳食助手，业务侧「AI 助手」整套下线（代码、路由、三张表、配置） | ✅ 已完成 |
| 32 | 对话末尾快捷气泡 + 接上真实模型后的纯文本回答与空消息重试修正 | ✅ 已完成 |
| 33 | 助手第一批只读工具：看板指标、某天某餐供应与营养、菜品配方、食材营养、节假日与调休，并写进开场提示菜单 | ✅ 已完成 |
| 34 | 助手页顶部收拢：模型状态进标题栏，移除数据来源通栏，工作区整体上移 | ✅ 已完成 |

34 个模块全部完成并通过验收。需求里的闭环「手机现场录入 → 大屏看到结果」在改为电脑端之后
已经真正闭合：登录 → 「每日采集」勾出当天供应的菜并填几组数字 → 保存即重算营养 →
免登录的公开大屏立刻看得见。

> 第 20–27 行记录的「AI 助手」是业务侧那个抽屉，**已在第 31 行整体下线**；
> 撤回能力保留，换成了 `POST /api/v1/menu-plan/{id}/undo`，由知味膳食助手调用。

系统现在是**两个后端进程**（业务 API + 独立 Agent 服务），进程拓扑、三种启动方式与
数据存放位置见 [架构说明 · 总体形态](./docs/architecture.md#一总体形态)。

部署方式见 [docs/deployment.md](./docs/deployment.md)：

```bash
cp infra/.env.example infra/.env   # 改掉数据库口令与 JWT_SECRET
pnpm docker:up                     # 前端 :8080；api / agent / postgres 在容器网络内
```

## 已知边界

本次交付的是**技术框架 + 打通的纵向切片**（食材库、菜品与配方库、每日采集、
三层校准、公开大屏与管理端看板），不是完整系统。以下内容尚未实现，
界面上一律显示「建设中」占位，不放看起来能用、其实是硬编码的假数据：

- **周报月报导出与差距分析（M7）**。看板已有的四类指标可直接复用，导出与差距分析尚未实现。
- 周报月报导出、多校区多租户、i18n 均不在本次范围。

**食材与调味料的营养值已经换成真实来源**：37 条取自「食物营养成分查询平台」
（中国疾病预防控制中心营养与健康所），逐条记下平台条目名与条目 ID；每条数值都能点开看到
来源、版本、原始 kJ 值、换算方式与查询日期。取数与校验的工具在
[apps/api/tools/nutrition_reference.py](./apps/api/tools/nutrition_reference.py)，
数据源是随仓库提交的快照 `apps/api/app/db/nutrition_reference.json`，**运行期不联网**。

仍然待办的是**单价**：平台没有价格数据，成本相关的结论在换成真实进货价之前只能作为口径演示。
唯一没有平台条目的是**蚝油**，它保留演示值并如实标注为「待核对」，没有借相邻条目的名字冒充。

## 合规边界

系统只做营养供给核算与群体级建议，不输出个体化诊断或治疗结论；不采集个人健康数据；公开大屏只展示菜品级营养与聚合数据。营养数据逐条标注来源与版本。

数据流向：程序与数据库部署在学校自己的机器上；**唯一对外的调用是知味膳食助手**——
它会把对话内容与查到的菜品级数据（菜名、营养、成本、指标）发给所配置的模型服务方
（可以是云端，也可以是校内的 vLLM / Ollama）。按学校要求选择模型提供方并告知使用者；
不配模型即为规则模式，数据不出校。
