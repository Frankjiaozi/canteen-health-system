# 食堂健康管理系统

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
[docs/data-model.md](./docs/data-model.md)，日常开发见 [docs/dev-guide.md](./docs/dev-guide.md)。

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

# 5) 启动前后端（api:8000 / web:5173）
pnpm dev
```

访问 <http://127.0.0.1:5173> 进入管理端，<http://127.0.0.1:5173/display> 进入免登录公开大屏。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `pnpm dev` | 并行启动后端与前端 |
| `pnpm db:up` / `pnpm db:down` | 启停开发数据库 |
| `pnpm db:migrate` / `pnpm db:downgrade` | 应用 / 回滚迁移 |
| `pnpm db:seed` | 灌入种子数据（幂等，可重复执行） |
| `pnpm gen:api` | 导出后端 OpenAPI 并重新生成前端类型 |
| `pnpm lint` | ruff + eslint |
| `pnpm typecheck` | mypy + tsc |
| `pnpm test` | pytest + vitest |
| `pnpm e2e` | Playwright 端到端 |

## 交付进度

| # | 模块 | 状态 |
| --- | --- | --- |
| 1 | 仓库与工程基建 | ✅ 已完成 |
| 2 | 后端核心骨架 | ✅ 已完成 |
| 3 | 完整数据模型 + 迁移 | ✅ 已完成 |
| 4 | 种子数据 | ✅ 已完成 |
| 5 | 认证与 RBAC | ⏳ 待开始 |
| 6 | 营养引擎第一层 | ⏳ 待开始 |
| 7 | 食材库端到端切片 | ⏳ 待开始 |
| 8 | 公开大屏 | ⏳ 待开始 |
| 9 | 管理端看板 | ⏳ 待开始 |
| 10 | 部署编排与文档 | ⏳ 待开始 |

## 已知边界

- 本次不做每日采集录入页，公开大屏的当日菜单来自种子数据；需求文档验收标准里「手机现场录入 → 大屏看到结果」的完整闭环要等 M2 模块实现后才真正闭合，当前用「登录 → 新增食材 → 大屏」验证链路可用。
- 菜品与配方库本次只做只读查询与营养计算，写界面留到 M1 阶段。
- 预测与推荐、周报月报导出、多校区、i18n 均不在本次范围。

## 合规边界

系统只做营养供给核算与群体级建议，不输出个体化诊断或治疗结论；不采集个人健康数据；公开大屏只展示菜品级营养与聚合数据。营养数据逐条标注来源与版本。
