# 部署指南

系统面向**学校内网自部署**：程序与数据库都在校内，数据由学校自己保管。
唯一对外的调用是 AI 助手（把菜品级数据发给所配置的模型服务方），不配置模型即为关闭。
编排文件在 `infra/`，一条命令拉起数据库、后端与前端。

## 一、单机部署

前置：一台能跑 Docker 的服务器，对外只需要暴露一个端口。

```bash
# 1) 准备编排变量
cp infra/.env.example infra/.env
#    改掉 POSTGRES_PASSWORD 与 JWT_SECRET —— 这两个是唯一的防线

# 2) 构建并启动
pnpm docker:up           # 等价于 docker compose -f infra/docker-compose.yml up -d --build

# 3) 首次部署灌入演示数据（生产环境需要显式允许）
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
web（nginx：静态文件 + /api 反代）
  │  容器网络内 :8000
  ▼
api（FastAPI；启动时自动执行 alembic upgrade head）
  │  :5432
  ▼
postgres（数据卷 canteen-pg）
```

- **只对外暴露 web 的端口**。数据库与后端都在容器网络内，不映射到宿主机。
- **前后端同源**。登录凭证是 httpOnly Cookie，`SameSite=Lax`，同源才走得通，
  也就不用为跨域凭证做额外配置。
- **迁移随服务启动执行**。单机自部署场景下，这样最不容易漏步骤。
- `api` 与 `postgres` 都配了健康检查，`web` 会等 `api` 健康后才启动。

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
# true  = 开放注册，访客可自行注册「食堂录入员」账号（演示用）
ALLOW_OPEN_REGISTRATION=false
```

关闭时 `POST /api/v1/auth/register` 返回 403，并明确提示「系统已关闭自助注册，请找管理员开通账号」——注册页面在页面上把这句原样显示给使用者，不会只剩一个看不懂的报错。

**为什么默认关。** 自助注册出来的账号角色是「食堂录入员」，而这个角色能写食材库、菜品配方、调味料库，还能批量导入 Excel。也就是说，只要拿到网址，任何人都能给自己开一个能改**配方库**的账号——而配方库是全系统最需要人工投入、也最不能出错的数据。所以这一项的默认值是 `false`（fail-closed）：忘了配，也不会把写权限敞出去。

**演示时怎么开。** 把上面那个值改成 `true`，或者启动时直接给容器传环境变量：

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

**备份**只需要备份 `canteen-pg` 数据卷：

```bash
docker run --rm -v canteen-pg:/data -v "$PWD:/backup" alpine \
  tar czf /backup/canteen-pg-$(date +%F).tar.gz -C /data .
```

## 七、演示环境与生产环境的差异

| 项 | 演示 | 生产 |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` |
| `DEBUG` | `true`（打印 SQL 与详细日志） | `false` |
| `POSTGRES_PASSWORD` / `JWT_SECRET` | 内置默认值 | 必须替换 |
| `COOKIE_SECURE` | `false` | 有 HTTPS 时必须为 `true` |
| `ALLOW_OPEN_REGISTRATION` | `true`（方便现场注册试用） | **必须为 `false`**，账号由管理员开通 |
| `ASSISTANT_*`（AI 助手） | 可以留空（助手显示「未接模型」） | 用云端端点也行；按学校要求选提供方，并把数据流向告知使用者 |
| 种子脚本 | 可直接执行 | 需要 `ALLOW_DEMO_SEED=true` 显式放行 |

种子脚本会写入口令已知的演示账号，因此生产环境默认拒绝执行；
内网首次部署确实需要初始化演示数据时，按上面的命令显式放行一次即可。

## 八、AI 助手接哪个模型

助手（管理端右上角「AI 助手」）走**任何 OpenAI 兼容的 `/chat/completions`**，因此接哪一家由环境变量决定：

```bash
# 云端端点（默认用法）
ASSISTANT_BASE_URL=https://api.example.com/v1
ASSISTANT_API_KEY=sk-...
ASSISTANT_MODEL=example-model

# 或者校内自部署的模型（vLLM / Ollama）
ASSISTANT_BASE_URL=http://127.0.0.1:8001/v1
ASSISTANT_MODEL=Qwen3-8B-Instruct
ASSISTANT_API_KEY=              # 内网端点通常不需要
```

**数据流向要说清楚**：助手提问时会把查出来的菜品级数据（菜名、营养、成本、指标）
随请求发给所配置的模型服务方。选云端就意味着这些内容会出校——按学校的要求选提供方，
并在使用说明里告知使用者。不需要助手时把这三项留空即可，界面上会显示「未接模型」。

可选：`ASSISTANT_TIMEOUT_SECONDS`（默认 60）、`ASSISTANT_MAX_TOOL_ROUNDS`（默认 **8**，
一次提问里最多来回几轮工具调用；助手会用「调只读接口」去试没包成工具的查询，试探需要轮次）、
`ASSISTANT_TEMPERATURE`（默认 0.2）。

**不配也能部署**：接口返回 503 并说明该配什么，界面上显示「未接模型」，
不会出现「点了没反应」的输入框。想验证链路是否通，配好之后点一次助手问「今天吃什么」即可——
它会调用只读工具去查库，回答里会列出查了哪些工具。

**阶段一只能查、不能写。** 录入与修改类操作要等下一阶段（配确认卡片与审计）才开放。
