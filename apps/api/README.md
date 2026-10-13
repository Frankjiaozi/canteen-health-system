# canteen-api

食堂健康管理系统后端服务。分层与目录约定见仓库根目录 `docs/architecture.md`。

## 本地启动

```bash
# 1) 起数据库（仓库根目录）
pnpm db:up

# 2) 安装依赖
cd apps/api
python -m pip install -e ".[dev]"

# 3) 准备环境变量
cp .env.example .env

# 4) 建表并灌入种子数据
python -m alembic upgrade head
python -m app.db.seed

# 5) 启动
python -m uvicorn app.main:app --reload --port 8000
```
