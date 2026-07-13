"""文件保留策略（补充计划第 8 节）。

完成超 media_retention_days 天的任务，删除其原始视频/音频文件，
但保留全部文本产物、导出文件、反馈与任务元信息。清理后仍可重跑文本阶段。

无独立调度器：由 lifespan 启动时 + 每次任务结束机会式触发（见 worker）。
"""

import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.core.timeutil import utcnow
from app.db import SessionLocal
from app.models import Artifact, Task, TaskStatus
from app.models.artifact import MEDIA_KINDS

logger = logging.getLogger(__name__)


def cleanup_old_media() -> int:
    """清理超期媒体，返回清理的任务数。"""
    cutoff = utcnow() - timedelta(days=settings.media_retention_days)
    session = SessionLocal()
    cleaned = 0
    try:
        tasks = session.scalars(
            select(Task).where(
                Task.status == TaskStatus.COMPLETED,
                Task.media_cleaned.is_(False),
                Task.completed_at.is_not(None),
                Task.completed_at < cutoff,
            )
        ).all()

        for task in tasks:
            media = session.scalars(
                select(Artifact).where(
                    Artifact.task_id == task.id,
                    Artifact.kind.in_(MEDIA_KINDS),
                )
            ).all()
            for art in media:
                _remove_file(art.file_path)
                art.file_path = None
            task.media_cleaned = True
            cleaned += 1

        session.commit()
        if cleaned:
            logger.info("media cleanup: %d task(s) cleaned", cleaned)
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("media cleanup failed")
    finally:
        session.close()
    return cleaned


def _remove_file(path: str | None) -> None:
    if not path:
        return
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except OSError:
        logger.warning("failed to remove media file: %s", path)
