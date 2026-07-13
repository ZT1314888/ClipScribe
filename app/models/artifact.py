"""Artifact 模型 —— 各阶段中间产物。

文本产物入库（text 字段）；媒体/导出文件存路径（file_path 字段）。
7 天媒体清理只删 raw_video/audio 的 file_path 指向文件，文本产物保留。
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db import Base


def _now() -> datetime:
    return utcnow()


class ArtifactKind(str, enum.Enum):
    RAW_VIDEO = "raw_video"  # 原始视频（media，7 天清理）
    AUDIO = "audio"  # 提取音频（audio，7 天清理）
    RAW_TRANSCRIPT = "raw_transcript"  # 原始 Whisper 转写稿
    REVISED_TRANSCRIPT = "revised_transcript"  # 人工修订转写稿（下游优先用）
    CLEANED = "cleaned"  # 清洗稿
    BREAKDOWN = "breakdown"  # 结构拆解
    REWRITE_ORAL = "rewrite_oral"  # 口播稿
    REWRITE_NOTE = "rewrite_note"  # 种草笔记文案
    REWRITE_TITLE = "rewrite_title"  # 标题和开头钩子
    EXPORT_MD = "export_md"  # Markdown 导出
    EXPORT_DOCX = "export_docx"  # Docx 导出


# 属于媒体、受 7 天保留策略约束的产物
MEDIA_KINDS = frozenset({ArtifactKind.RAW_VIDEO, ArtifactKind.AUDIO})

# 三类改写产物
REWRITE_KINDS = (
    ArtifactKind.REWRITE_ORAL,
    ArtifactKind.REWRITE_NOTE,
    ArtifactKind.REWRITE_TITLE,
)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        # 每个任务每种产物最多一条（重跑时覆盖更新）
        UniqueConstraint("task_id", "kind", name="uq_artifact_task_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ArtifactKind] = mapped_column(Enum(ArtifactKind), nullable=False)

    text: Mapped[str | None] = mapped_column(Text, default=None)  # 文本产物
    file_path: Mapped[str | None] = mapped_column(
        String(1024), default=None
    )  # 媒体/导出文件

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    task: Mapped["object"] = relationship("Task", back_populates="artifacts")
