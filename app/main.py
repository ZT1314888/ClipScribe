"""FastAPI 应用装配。

lifespan：建表 → 启动自愈（运行中任务标记失败）→ 启动媒体清理 → 启动单 worker。
挂载：认证中间件、静态资源、页面路由与 API 路由。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import auth, feedback, pages, stats, tasks
from app.core.lifecycle import fail_running_tasks
from app.core.middleware import AuthMiddleware
from app.db import init_db
from app.services.retention import cleanup_old_media
from app.worker.queue import task_queue

logging.basicConfig(level=logging.INFO)

_STATIC_DIR = Path("static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    fail_running_tasks()  # 容器重启：运行中任务统一失败
    cleanup_old_media()  # 启动时跑一次 7 天媒体清理
    task_queue.start()
    try:
        yield
    finally:
        await task_queue.stop()


app = FastAPI(title="短视频文案系统 MVP", version="0.1.0", lifespan=lifespan)

app.add_middleware(AuthMiddleware)

# 上游前端静态资源（提交页可复用）；目录不存在时跳过挂载
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# 页面路由
app.include_router(pages.router)
# API 路由
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(feedback.router)
app.include_router(stats.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
