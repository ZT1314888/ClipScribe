"""启动自愈：容器重启时把运行中任务统一标记 failed（补充计划第 4 节）。

单容器单 worker，重启即中断。运行中任务不会自动恢复，
统一置为 failed 并提示用户手动重试，避免永久卡在运行态。
"""

import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Task
from app.models.task import RUNNING_STATUSES, TaskStatus

logger = logging.getLogger(__name__)


def fail_running_tasks() -> int:
    """把所有非终态任务标记 failed，返回处理数量。"""
    session = SessionLocal()
    count = 0
    try:
        tasks = session.scalars(
            select(Task).where(Task.status.in_(RUNNING_STATUSES))
        ).all()
        for task in tasks:
            task.status = TaskStatus.FAILED
            task.error_message = "服务重启导致任务中断，请从失败步骤手动重试。"
            count += 1
        session.commit()
        if count:
            logger.info("startup self-heal: marked %d running task(s) failed", count)
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("startup self-heal failed")
    finally:
        session.close()
    return count
