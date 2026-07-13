"""单 worker 串行后台执行器（进程内，无 Celery/Redis）。

补充计划第 4 节：单 worker 串行执行，避免本机多个 Whisper/下载并发打满资源。

实现：一个 asyncio.Queue + 一个消费协程。提交任务只入队 task_id；
消费协程逐个取出，在线程池里跑同步 pipeline（SQLAlchemy 同步 + faster-whisper 阻塞）。
"""

import asyncio
import logging

from app.db import SessionLocal
from app.models import Task, TaskStatus
from app.services import pipeline

logger = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, TaskStatus | None]] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run_loop())
            logger.info("task worker started")

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def submit(self, task_id: str, from_step: TaskStatus | None = None) -> None:
        await self._queue.put((task_id, from_step))

    def submit_nowait(self, task_id: str, from_step: TaskStatus | None = None) -> None:
        self._queue.put_nowait((task_id, from_step))

    async def _run_loop(self) -> None:
        while True:
            task_id, from_step = await self._queue.get()
            try:
                await asyncio.to_thread(self._process, task_id, from_step)
            except Exception:  # noqa: BLE001  worker 循环必须存活
                logger.exception("worker failed processing %s", task_id)
            finally:
                self._queue.task_done()

    @staticmethod
    def _process(task_id: str, from_step: TaskStatus | None) -> None:
        session = SessionLocal()
        try:
            task = session.get(Task, task_id)
            if task is None:
                logger.warning("task %s not found, skip", task_id)
                return
            pipeline.run(session, task, from_step=from_step)
            session.commit()
            # 机会式触发媒体清理（无独立调度器）
            _opportunistic_cleanup()
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("processing %s raised", task_id)
        finally:
            session.close()


def _opportunistic_cleanup() -> None:
    """每次任务结束顺带跑一次 7 天媒体清理。延后实现，先留钩子。"""
    try:
        from app.services import retention

        retention.cleanup_old_media()
    except Exception:  # noqa: BLE001  清理失败不影响主流程
        logger.exception("opportunistic media cleanup failed")


# 全局单例
task_queue = TaskQueue()
