# 开发指南

## 环境准备

| 依赖 | 版本 |
| --- | --- |
| Node | ≥ 22.12（Vite 8 要求） |
| pnpm | 11.x |
| Python | 3.13 |
| Docker | 用于本地 PostgreSQL |

## 首次搭建

```bash
pnpm db:up
pnpm install
python -m venv apps/api/.venv
node scripts/py.mjs -m pip install -e "apps/api[dev]"
cp apps/api/.env.example apps/api/.env
pnpm db:migrate
pnpm db:seed
pnpm db:compute
pnpm dev
```

后端依赖统一装在 `apps/api/.venv`。`scripts/py.mjs` 会自动优先使用该虚拟环境里的解释器，
因此所有 `pnpm` 脚本无需事先激活虚拟环境即可运行；在 IDE 里请把解释器指向
`apps/api/.venv`。

## 日常命令

| 命令 | 说明 |
| --- | --- |
| `pnpm dev` | 并行启动后端（8000）与前端（5173） |
| `pnpm lint` / `pnpm format` | 风格检查 / 自动格式化 |
| `pnpm typecheck` | mypy + tsc |
| `pnpm test` | pytest + vitest |
| `pnpm e2e` | Playwright 端到端 |
| `pnpm gen:api` | 后端接口变更后重新生成前端类型 |

### 端到端测试的前置条件

端到端跑的是真实的「前端 + 后端 + PostgreSQL」，需要先准备数据库与浏览器：

```bash
pnpm db:up && pnpm db:migrate && pnpm db:seed
cd apps/web && npx playwright install chromium
```

国内网络下载 Chromium 往往极慢甚至卡死。若 `playwright install` 长时间没有进展，
改用镜像（Playwright 的浏览器包在 npmmirror 上有同步）：

```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST = "https://cdn.npmmirror.com/binaries/playwright"
npx playwright install chromium
```

前后端服务由 Playwright 的 `webServer` 自动拉起，不用手工开终端；
本地已经开着 `pnpm dev` 时它会直接复用。

## 新增一个业务域

这一步是标准动作，照抄 `app/modules/ingredient` 即可：

1. 建目录 `app/modules/<域>/`，放 `models.py`、`schemas.py`、`repository.py`、`service.py`、`router.py`。
2. 在 `app/db/registry.py` 中导入该域的 `models`，让 Alembic 能感知到新表。
3. 生成迁移：`pnpm db:revision -m "add <域>"`，检查生成的迁移脚本后 `pnpm db:migrate`。
4. 在 `app/main.py` 的 `api_router` 中注册该域的 router。
5. 写 service 层单测；接口层测试复用 `tests/conftest.py` 里的客户端与登录夹具。
6. 前端在 `src/features/<域>/` 下按同样结构建目录，导出路由片段。
7. 跑 `pnpm gen:api` 更新前端类型，再跑 `pnpm lint && pnpm typecheck && pnpm test`。

## 数据库迁移

- 迁移脚本由 Alembic autogenerate 生成草稿，**必须人工检查**后再提交：枚举 CHECK 约束、
  索引、`server_default`、非空列的新增顺序都需要确认。
- 迁移要能回滚：`pnpm db:downgrade` 必须能退回上一版本，CI 会验证这一点。

## 提交规范

- 每个模块一个提交，提交信息用中文或英文均可，格式为 `类型(范围): 描述`，例如
  `feat(ingredient): 食材库增删改查与权限校验`。
- 提交前 husky 会自动跑 lint-staged 格式化暂存文件。

## 编码约定

- 标识符用英文，注释、文档、界面文案用中文。
- 后端类型注解写全（mypy 开了 `disallow_untyped_defs`）。
- 不允许用 `print`，统一走 `app.core.logging` 提供的 logger。
- 时间相关的值必须显式带时区，禁止 naive datetime。
- 枚举的中文文案集中在 `app/shared/enums.py` 的 `ENUM_LABELS`，新增取值必须同步补充；
  `tests/core/test_enum_labels.py` 会检查遗漏。
- 新增枚举取值后必须重新生成迁移——取值约束是数据库里的 CHECK 约束，不改迁移就不生效。
- AntD 的「两字按钮自动加空格」已在 `AppProviders` 中关闭，界面文案与源码保持一致。
