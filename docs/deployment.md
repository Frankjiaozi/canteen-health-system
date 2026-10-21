# 部署指南

系统面向**学校内网自部署**：程序与数据库都在校内，数据由学校自己保管。
唯一对外的调用是知味膳食助手（把对话内容与菜品级数据发给所配置的模型服务方），
不配置模型即为规则模式，数据不出校。
编排文件在 `infra/`，一条命令拉起数据库、后端与前端。

## 一、单机部署

前置：一台能跑 Docker 的服务器，对外只需要暴露一个端口。

```bash
# 1) 准备编排变量
cp infra/.env.example infra/.env
#    改掉 POSTGRES_PASSWORD 与 JWT_SECRET —— 这两个是唯一的防线

# 2) 构建并启动
pnpm docker:up           # 等价于 docker compose -f infra/docker-compose.yml up -d --build

# 3) 首次部署灌入初始化样本数据（生产环境需要显式允许）
docker compose -f infra/docker-compose.yml exec -e ALLOW_DEMO_SEED=true api python -m app.db.seed
docker compose -f infra/docker-compose.yml exec api python -m app.modules.nutrition.compute
```

完成后：

| 地址 | 内容 |
| --- | --- |
| `http://<服务器>:8080/` | 管理端（需登录） |
| `http://<服务器>:8080/display` | 公开大屏（免登录） |
| `http://<服务器>:8080/docs` | 交互式 API 文档 |
| `http://<服务器>:8080/health` | 探活 |

## 二、编排结构

```
浏览器
  │  :8080
  ▼
web（nginx：静态文件 + /api → api + /agent-api → agent）
  │
  ├── 容器网络内 :8000 ──► api（FastAPI；启动时自动执行 alembic upgrade head）
  │                          │  :5432
  │                          ▼
  │                       postgres（数据卷 canteen-pg）
  │
  └── 容器网络内 :8001 ──► agent（知味膳食助手）
                             │  数据卷 agent-state（对话与方案快照的 SQLite）
                             └─ 用当前用户 Cookie 调 api:8000/api/v1
```

- **只对外暴露 web 的端口**。数据库与两个后端都在容器网络内，不映射到宿主机。
- **前后端同源**。登录凭证是 httpOnly Cookie，`SameSite=Lax`，同源才走得通，
  也就不用为跨域凭证做额外配置。
- **迁移随服务启动执行**。单机自部署场景下，这样最不容易漏步骤。
- `api`、`agent`、`postgres` 都配了健康检查；`agent` 等 `api` 健康后再起，`web` 等两者都健康。
- **agent 是独立进程、独立镜像**，它没有业务库的写权限，只能以当前用户身份走 HTTP。

## 三、网络受限的环境

`registry-1.docker.io` 在部分网络下不可达。基础镜像全部做成了编排变量，
指到可用的 Docker Hub 镜像即可，**不需要改 Dockerfile**：

```dotenv
# infra/.env
POSTGRES_IMAGE=dockerproxy.net/library/postgres:17-alpine
PYTHON_IMAGE=dockerproxy.net/library/python:3.13-slim
NODE_IMAGE=dockerproxy.net/library/node:24-alpine
NGINX_IMAGE=dockerproxy.net/library/nginx:alpine
```

如果 `pypi.org` 本身也不稳定，可以单独指定 Python 包索引，不需要改 Dockerfile：

```dotenv
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

## 四、启用 HTTPS

登录 Cookie 默认不要求加密连接（`COOKIE_SECURE=false`），便于内网先用起来。
一旦前面挂了 HTTPS（例如 Caddy 或 Nginx 配证书），务必改成：

```dotenv
COOKIE_SECURE=true
```

否则浏览器不会在加密连接上回传登录凭证，表现为「登录成功但一刷新就掉线」。

## 五、自助注册开关

系统支持访客自行注册账号，但**学校内网正式部署必须关掉**。

```dotenv
# infra/.env
# false = 关闭自助注册，账号一律由管理员开通（内网正式部署用这个）
# true  = 开放注册，访客可自行注册「食堂录入员」账号（功能验证用）
ALLOW_OPEN_REGISTRATION=false
```

关闭时 `POST /api/v1/auth/register` 返回 403，并明确提示「系统已关闭自助注册，请找管理员开通账号」——注册页面在页面上把这句原样显示给使用者，不会只剩一个看不懂的报错。

**为什么默认关。** 自助注册出来的账号角色是「食堂录入员」，而这个角色能写食材库、菜品配方、调味料库，还能批量导入 Excel。也就是说，只要拿到网址，任何人都能给自己开一个能改**配方库**的账号——而配方库是全系统最需要人工投入、也最不能出错的数据。所以这一项的默认值是 `false`（fail-closed）：忘了配，也不会把写权限敞出去。

**功能验证时怎么开。** 把上面那个值改成 `true`，或者启动时直接给容器传环境变量：

```bash
ALLOW_OPEN_REGISTRATION=true docker compose -f infra/docker-compose.yml up -d
```

改完不需要重建镜像，重启 `api` 容器即可生效。

## 六、日常运维

```bash
pnpm docker:logs                       # 看日志
pnpm docker:down                       # 停止（数据卷保留）
docker compose -f infra/docker-compose.yml exec api python -m alembic upgrade head
docker compose -f infra/docker-compose.yml exec api python -m app.modules.nutrition.compute
```

**要备份两个卷**：`canteen-pg`（业务数据）与 `agent-state`（助手的对话与方案快照）。
只备前者的话，恢复之后业务还在，但助手的历史对话和方案版本全没了——那些是
「当时为什么这么排」的证据，不是可再生的缓存。

```bash
for volume in canteen-pg agent-state; do
  docker run --rm -v "$volume":/data -v "$PWD:/backup" alpine \
    tar czf "/backup/$volume-$(date +%F).tar.gz" -C /data .
done
```

## 七、开发环境与生产环境的差异

| 项 | 功能验证 | 生产 |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` |
| `DEBUG` | `true`（打印 SQL 与详细日志） | `false` |
| `POSTGRES_PASSWORD` / `JWT_SECRET` | 内置默认值 | 必须替换 |
| `COOKIE_SECURE` | `false` | 有 HTTPS 时必须为 `true` |
| `ALLOW_OPEN_REGISTRATION` | `true`（方便现场注册试用） | **必须为 `false`**，账号由管理员开通 |
| `PACKAGE_SHARE_A` / `PACKAGE_SHARE_B` | `0.5` / `0.5` | 仅为推荐域套餐成本估算保留；**不参与采购量计算**，两项合计必须为 1 |
| `AGENT_MODEL_*` / `AGENT_MODE`（知味膳食助手） | 可以留空（规则模式，数据不出校） | 用云端端点也行；按学校要求选提供方，并把数据流向告知使用者 |
| 种子脚本 | 可直接执行 | 需要 `ALLOW_DEMO_SEED=true` 显式放行 |

种子脚本会写入口令已知的初始化账号，因此生产环境默认拒绝执行；
内网首次部署确实需要初始化初始化样本数据时，按上面的命令显式放行一次即可。

### 营养数据的来源

食材与调味料的营养值来自随仓库提交的快照 `apps/api/app/db/nutrition_reference.json`，
**部署与运行时都不需要访问外部网站**，也不需要任何外网权限。容器构建时把它打进镜像，
`pnpm db:seed` 直接读它。

快照是从「食物营养成分查询平台」离线取数后生成的，只有**刷新或核对数据**时才需要联网：

```bash
pnpm nutrition:list 大白菜   # 列平台候选条目，人工挑条目
pnpm nutrition:fetch         # 取数并重写快照
pnpm nutrition:verify        # 重新取数与快照逐条比对（数据有没有被改过）
```

刷新快照后需要重算已落库的营养结果，否则大屏与看板读到的还是按旧值算出来的数：

```bash
pnpm db:seed && pnpm db:compute
```

这套设计是有意的：那个平台是第三方公共服务，不给可用性承诺。取数时它就出现过 502，
若把系统做成运行期依赖，那段时间整套营养核算都会跟着停摆。

## 八、知味膳食助手接哪个模型

助手（管理端左侧「知味膳食助手」，独立容器 `agent`）走**任何 OpenAI 兼容的
`/chat/completions`**，因此接哪一家由环境变量决定：

```bash
# 云端端点（默认用法）
AGENT_MODEL_BASE_URL=https://api.example.com/v1
AGENT_MODEL_API_KEY=sk-...
AGENT_MODEL_NAME=example-model

# 或者校内自部署的模型（vLLM / Ollama）
AGENT_MODEL_BASE_URL=http://127.0.0.1:8001/v1
AGENT_MODEL_NAME=Qwen3-8B-Instruct
AGENT_MODEL_API_KEY=              # 内网端点通常不需要
```

`AGENT_MODE` 决定用哪种模式：

| 取值 | 行为 |
| --- | --- |
| `auto`（默认） | 三项都配齐就用模型，否则退回规则模式 |
| `rules` | 只用规则识别有限说法，仍然调真实业务工具 |
| `model` | 没配就**启动失败**，避免静默假装连上 |

界面上会写明当前是哪种模式——**规则模式不会被说成「大模型」**。

**数据流向要说清楚**：助手提问时会把对话内容与查出来的菜品级数据（菜名、营养、成本、指标）
随请求发给所配置的模型服务方。选云端就意味着这些内容会出校——按学校的要求选提供方，
并在使用说明里告知使用者。三项留空即为规则模式，数据不出校。

另外两项：`AGENT_DATA_PATH`（会话与方案快照的 SQLite 位置，容器里是 `agent-state` 卷）、
`AGENT_DATA_NOTICE`（界面上那句数据来源提示，可按学校口径改写）。

**不配也能部署**：以规则模式运行，仍能完成体检、生成、改条件重算、发布与撤回；
只是「用自然语言描述任意条件」的能力变弱，需要按界面给的句式说。
