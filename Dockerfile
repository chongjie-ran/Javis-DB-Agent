# ============================================================
# Javis-DB-Agent Dockerfile
# 多阶段构建：builder + runtime
# 支持: amd64, arm64
# ============================================================

# ---- Builder Stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖（用户级安装，避免 root）
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Runtime Stage ----
FROM python:3.11-slim AS runtime

LABEL maintainer="Chongjie Ran <chongjie.ran@enmotech.com>"
LABEL version="1.3.1"
LABEL description="Javis-DB-Agent - 数据库运维智能体系统"

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATA_DIR=/app/data \
    LOG_DIR=/app/logs \
    OLLAMA_BASE_URL=http://localhost:11434

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash javis

WORKDIR /app

# 从 builder 复制已安装的 Python 包
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 复制应用代码
COPY --chown=javis:javis . .

# 创建数据目录
RUN mkdir -p /app/data /app/logs && \
    chown -R javis:javis /app

# 切换到非 root 用户
USER javis

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || \
       curl -f http://localhost:8000/docs || \
       exit 1

# ---- Ollama Stage (可选) ----
# 如需在容器内运行 Ollama，使用此镜像
# FROM ollama/ollama:latest AS ollama
# 此配置假设 Ollama 在宿主机或单独容器运行

# 默认启动命令
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
