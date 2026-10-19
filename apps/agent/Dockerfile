ARG PYTHON_IMAGE=python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
FROM ${PYTHON_IMAGE}
ARG PIP_INDEX_URL
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY apps/agent/pyproject.toml ./pyproject.toml
COPY apps/agent/zhiwei_agent ./zhiwei_agent
RUN python -m pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" . && useradd --uid 10001 --create-home agent && mkdir -p /app/data && chown -R agent:agent /app/data
USER agent
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "zhiwei_agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
