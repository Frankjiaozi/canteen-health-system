# 后端镜像：只装运行时依赖，数据库迁移在容器启动时执行
#
# 基础镜像做成构建参数：默认官方源，网络受限的环境（例如需要走 Docker Hub 镜像）
# 通过 --build-arg 覆盖即可，不必改这个文件。
ARG PYTHON_IMAGE=python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
FROM ${PYTHON_IMAGE}
ARG PIP_INDEX_URL

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先装依赖再拷代码：代码改动不会让依赖层缓存失效
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./

RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
