# syntax=docker/dockerfile:1.4
# BuildKit：DOCKER_BUILDKIT=1 docker compose build（或默认已开启）以使用 RUN --mount=type=cache
# CI: 验证 GITHUB_TOKEN 发布流程可用（首次以新 workflow 发布 latest）

# 多阶段构建：第一阶段 - 前端构建（在构建机架构上运行）
FROM --platform=$BUILDPLATFORM node:20.18.0-slim AS frontend-builder

WORKDIR /app
RUN npm install -g pnpm

COPY web_ui/package.json web_ui/pnpm-lock.yaml* web_ui/
WORKDIR /app/web_ui
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

COPY web_ui/ .
RUN pnpm build

# 多阶段构建：第二阶段 - Python 应用（在目标架构上运行）
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    PIP_DEFAULT_TIMEOUT=100 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

WORKDIR /app

# 安装 Python 依赖（slim 版：无 umap/psycopg2/minio 等可选重型依赖）
COPY requirements.slim.txt .
RUN pip install uv --no-cache-dir
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.slim.txt || \
    pip install --no-cache-dir -r requirements.slim.txt

# 安装 Playwright 浏览器（打包进镜像，避免服务器网络受限无法下载）
# 注意：放在「复制业务代码」之前，仅 playwright 版本变更才重跑本层
ARG BROWSER_TYPE=firefox
ENV BROWSER_TYPE=${BROWSER_TYPE} \
    PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000

RUN export PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000 && \
    ( python3 -m playwright install ${BROWSER_TYPE} --with-deps || \
      ( echo "官方 CDN 失败，尝试 npmmirror..." && \
        PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright \
        python3 -m playwright install ${BROWSER_TYPE} --with-deps ) \
    ) && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cache /tmp/* /var/tmp/*

# 复制业务代码
COPY config.example.yaml config.yaml
COPY apis/ apis/
COPY core/ core/
COPY driver/ driver/
COPY tools/ tools/
COPY jobs/ jobs/
COPY schemas/ schemas/
COPY migrations/ migrations/
COPY web.py .
COPY main.py .
COPY job.py .
COPY tool.py .
COPY init_sys.py .
COPY install.sh .
COPY start.sh .

COPY --from=frontend-builder /app/web_ui/dist ./static

RUN chmod +x install.sh start.sh && \
    find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

EXPOSE 8001
CMD ["bash", "start.sh"]
