"""Task 模型 —— 采集/处理任务，含状态机。

状态机（补充计划第 4 节）：
    pending → downloading → extracting_audio → transcribing
            → cleaning → analyzing → rewriting → completed
    任一步可转 failed。
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db import Base


def _now() -> datetime:
    return utcnow()


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING_AUDIO = "extracting_audio"
    TRANSCRIBING = "transcribing"
    CLEANING = "cleaning"
    ANALYZING = "analyzing"
    REWRITING = "rewriting"
    COMPLETED = "completed"
    FAILED = "failed"


# 非终态集合：容器重启时这些任务统一标记 failed
RUNNING_STATUSES = frozenset(
    {
        TaskStatus.PENDING,
        TaskStatus.DOWNLOADING,
        TaskStatus.EXTRACTING_AUDIO,
        TaskStatus.TRANSCRIBING,
        TaskStatus.CLEANING,
        TaskStatus.ANALYZING,
        TaskStatus.REWRITING,
    }
)


class InputType(str, enum.Enum):
    LINK = "link"  # 抖音链接（本阶段留桩）
    UPLOAD = "upload"  # 本地上传兜底


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False, index=True
    )
    input_type: Mapped[InputType] = mapped_column(Enum(InputType), nullable=False)

    # 来源信息
    source_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    video_title: Mapped[str | None] = mapped_column(String(512), default=None)
    author: Mapped[str | None] = mapped_column(String(256), default=None)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    # 时间戳与耗时（供统计页）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)

    # 媒体是否已按保留策略清理（清理后仍可重跑文本阶段）
    media_cleaned: Mapped[bool] = mapped_column(default=False)

    artifacts: Mapped[list["object"]] = relationship(
        "Artifact",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    feedbacks: Mapped[list["object"]] = relationship(
        "Feedback",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
