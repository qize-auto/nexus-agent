# NexusAgent v4.0+ — 多阶段构建 Dockerfile
# 设计参考:
# - Hermes Agent Docker 启动失败 Issue #36208 的教训
# - 生产级最佳实践: 非 root 用户、健康检查、最小镜像

# ═══════════════════════════════════════════════════════════════
# 阶段 1: 依赖构建
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim AS builder

WORKDIR /build

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml requirements.txt ./

# 创建虚拟环境并安装依赖
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ═══════════════════════════════════════════════════════════════
# 阶段 2: 运行镜像
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim AS runtime

LABEL maintainer="NexusAgent Team"
LABEL description="NexusAgent — 生产级 AI Agent 框架"

# 安全: 非 root 用户
RUN groupadd -r nexus && useradd -r -g nexus -m -d /home/nexus nexus

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 设置工作目录
WORKDIR /app

# 复制应用代码
COPY --chown=nexus:nexus . /app/

# 创建数据目录和运行时目录
RUN mkdir -p /app/data /app/uploads /app/chroma_db /app/backups && \
    chown -R nexus:nexus /app/data /app/uploads /app/chroma_db /app/backups

# 切换到非 root 用户
USER nexus

# 优雅关闭信号
STOPSIGNAL SIGTERM

# 健康检查（检查 /api/health 端点）
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

# 暴露端口
EXPOSE 8080

# 默认命令
CMD ["python", "-m", "nexusagent.run_web"]
