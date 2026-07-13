"""Feedback 模型 —— 每条改写结果的 好用/不好用 + 原因标签。

统计页好评率的唯一数据来源（补充计划第 6 节）。
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db import Base
from app.models.artifact import ArtifactKind


def _now() -> datetime:
    return utcnow()


class FeedbackVerdict(str, enum.Enum):
    GOOD = "good"  # 好用
    BAD = "bad"  # 不好用


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    # 针对哪一类改写产物
    rewrite_kind: Mapped[ArtifactKind] = mapped_column(
        Enum(ArtifactKind), nullable=False
    )
    verdict: Mapped[FeedbackVerdict] = mapped_column(
        Enum(FeedbackVerdict), nullable=False
    )
    # 原因标签，逗号分隔（第一版轻量存储，不单独建表）
    reason_tags: Mapped[str | None] = mapped_column(String(512), default=None)
    comment: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    task: Mapped["object"] = relationship("Task", back_populates="feedbacks")
