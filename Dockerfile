# syntax=docker/dockerfile:1.4

# 第一阶段：前端构建（在构建机平台上运行，不影响最终镜像）
FROM --platform=$BUILDPLATFORM node:20.18.0-slim AS frontend-builder

WORKDIR /app
RUN npm install -g pnpm

COPY web_ui/package.json web_ui/pnpm-lock.yaml* web_ui/
WORKDIR /app/web_ui
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

COPY web_ui/ .
RUN pnpm build

# 第二阶段：Python 应用（使用目标平台镜像，支持 amd64/arm64 多平台）
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    PIP_DEFAULT_TIMEOUT=100 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

WORKDIR /app

COPY requirements.txt .

RUN pip install uv --no-cache-dir

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt || \
    pip install -r requirements.txt

# 构建时在 CI 环境下载浏览器并打入镜像（CI 可访问 Playwright CDN）
# 路径固定为 /app/playwright，不依赖运行时网络，不受服务器网络限制影响
ARG BROWSER_TYPE=firefox
ENV BROWSER_TYPE=${BROWSER_TYPE} \
    PLAYWRIGHT_BROWSERS_PATH=/app/playwright

RUN python3 -m playwright install ${BROWSER_TYPE} --with-deps \
    && rm -rf /var/lib/apt/lists/*

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
