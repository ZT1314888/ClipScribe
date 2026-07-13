# 单容器部署（ADR-0003）。基于 uv 官方镜像，含 ffmpeg。
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# ffmpeg：抽音频/归一化必需
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用缓存层）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再拷贝源码
COPY . .
RUN uv sync --frozen --no-dev

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PRODUCTION_MODE=true \
    DATA_DIR=/app/data

EXPOSE 8000

# 单 worker 串行任务在应用内部运行，这里只起一个 uvicorn 进程
CMD ["uv", "run", "python", "main.py"]
