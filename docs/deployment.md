# 部署指南

系统面向**学校内网自部署**：数据不出校，是方案与云端产品的核心差异点。
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

## 五、日常运维

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

## 六、演示环境与生产环境的差异

| 项 | 演示 | 生产 |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` |
| `DEBUG` | `true`（打印 SQL 与详细日志） | `false` |
| `POSTGRES_PASSWORD` / `JWT_SECRET` | 内置默认值 | 必须替换 |
| `COOKIE_SECURE` | `false` | 有 HTTPS 时必须为 `true` |
| 种子脚本 | 可直接执行 | 需要 `ALLOW_DEMO_SEED=true` 显式放行 |

种子脚本会写入口令已知的演示账号，因此生产环境默认拒绝执行；
内网首次部署确实需要初始化演示数据时，按上面的命令显式放行一次即可。
