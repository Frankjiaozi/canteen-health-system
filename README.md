# 知味 · 校园智慧膳食平台

本地项目名：知味（Zhiwei）。基于 [Frankjiaozi/canteen-health-system](https://github.com/Frankjiaozi/canteen-health-system) 继续开发，保留原仓库历史与来源。

把食堂每天采购与投料的原始数据，变成每道菜的营养数据和第二天的采购与菜单决策，同时把学生餐的营养构成公开给学生。

完整需求见 [canteen-requirements.md](./canteen-requirements.md)。

## 系统形态

本系统只有三个可见终点，**没有学生端**——需求文档中的「学生端」对应的就是免登录的公开大屏：

| 界面 | 访问方式 | 内容 |
| --- | --- | --- |
| 食堂管理端 | 需登录（录入员 / 食堂管理员 / 学校管理方） | 每日采集、配方维护、看板与报表 |
| 公开大屏 | **免登录** | 今日菜单、每道菜营养指标、膳食指南对照条 |
| 管理端看板 | 需登录 | 油盐糖趋势、人均摄入对比、达标率、剩餐浪费率 |

## 技术选型

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.13 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 |
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
│   └── web/                 React 单页应用
│       ├── src/app/         路由、Provider、全局装配
│       ├── src/features/    业务域（auth / ingredient / display / dashboard / ...）
│       ├── src/layouts/     AdminLayout、DisplayLayout
│       └── src/shared/      UI、hooks、工具、常量
├── packages/api-client/     OpenAPI 生成的类型与请求客户端
├── infra/                   docker-compose、Dockerfile、nginx
├── scripts/                 生成 API 客户端等工程脚本
├── docs/                    架构、数据模型、开发指南
└── canteen-requirements.md  需求文档
```

设计与分层约定见 [docs/architecture.md](./docs/architecture.md)，数据模型见
[docs/data-model.md](./docs/data-model.md)，日常开发见 [docs/dev-guide.md](./docs/dev-guide.md)，
内网自部署见 [docs/deployment.md](./docs/deployment.md)。

## 快速开始

前置：Node ≥ 22.12、pnpm、Python 3.13、Docker。

```bash
# 1) 起数据库
pnpm db:up

# 2) 安装前后端依赖
pnpm install

# 后端依赖装在 apps/api/.venv 里；pnpm 脚本会自动使用该虚拟环境，无需手动激活
python -m venv apps/api/.venv
node scripts/py.mjs -m pip install -e "apps/api[dev]"

# 3) 准备后端环境变量
cp apps/api/.env.example apps/api/.env

# 4) 建表 + 灌入种子数据
pnpm db:migrate
pnpm db:seed

# 5) 按标准配方计算营养结果（营养引擎第一层）
pnpm db:compute

# 6) 启动前后端（api:8000 / web:5173）
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
| `pnpm dev` | 并行启动后端与前端 |
| `pnpm db:up` / `pnpm db:down` | 启停开发数据库 |
| `pnpm db:migrate` / `pnpm db:downgrade` | 应用 / 回滚迁移 |
| `pnpm db:seed` | 灌入种子数据（幂等，可重复执行） |
| `pnpm db:compute` | 按标准配方计算最近两周的营养结果（幂等） |
| `pnpm gen:api` | 导出后端 OpenAPI 并重新生成前端类型 |
| `pnpm lint` | ruff + eslint |
| `pnpm typecheck` | mypy + tsc |
| `pnpm test` | pytest + vitest |
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

13 个模块全部完成并通过验收。需求里的闭环「手机现场录入 → 大屏看到结果」在改为电脑端之后
已经真正闭合：登录 → 「每日采集」勾出当天供应的菜并填几组数字 → 保存即重算营养 →
免登录的公开大屏立刻看得见。
部署方式见 [docs/deployment.md](./docs/deployment.md)：

```bash
cp infra/.env.example infra/.env   # 改掉数据库口令与 JWT_SECRET
pnpm docker:up                     # 前端 :8080、后端与数据库在容器网络内
```

## 已知边界

本次交付的是**技术框架 + 打通的纵向切片**（食材库、菜品与配方库、每日采集、
三层校准、公开大屏与管理端看板），不是完整系统。以下内容尚未实现，
界面上一律显示「建设中」占位，不放看起来能用、其实是硬编码的假数据：

- **预测（M5）与菜单推荐（M6）**。数据表、模块目录与扩展点已就位，算法未实现。
- **PWA 的离线数据队列**。应用壳可离线打开、断网有明确提示，但「断网录入后自动同步」
  的排队逻辑还没做：采集页在断网时会明确提示无法保存，不会假装成功。
- 周报月报导出、多校区多租户、i18n 均不在本次范围。

另外，**种子数据里的食材营养数值是演示占位值**（`data_source` 字段已如实标注为
「演示占位值，待核对」）。正式参赛前必须逐条与《中国食物成分表（标准版第 6 版）》核对，
并把来源改成真实出处——系统要求任何营养数据都能点开看到来源与版本，这条要求在演示阶段
就必须成立，因此宁可标注「待核对」，也不填一个看起来权威却没有依据的出处。

## 合规边界

系统只做营养供给核算与群体级建议，不输出个体化诊断或治疗结论；不采集个人健康数据；公开大屏只展示菜品级营养与聚合数据。营养数据逐条标注来源与版本。
