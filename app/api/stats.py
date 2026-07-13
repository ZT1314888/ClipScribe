"""统计聚合：任务总数、成功率、平均耗时、反馈好评率（补充计划第 6、9 节）。"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Feedback, Task, TaskStatus
from app.models.feedback import FeedbackVerdict
from app.schemas.task import StatsResponse


def compute_stats(session: Session) -> StatsResponse:
    total = session.scalar(select(func.count()).select_from(Task)) or 0
    completed = (
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status == TaskStatus.COMPLETED)
        )
        or 0
    )
    avg_duration = session.scalar(
        select(func.avg(Task.duration_seconds)).where(
            Task.duration_seconds.is_not(None)
        )
    )

    fb_total = session.scalar(select(func.count()).select_from(Feedback)) or 0
    fb_good = (
        session.scalar(
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.verdict == FeedbackVerdict.GOOD)
        )
        or 0
    )

    return StatsResponse(
        total_tasks=total,
        success_rate=(completed / total) if total else 0.0,
        avg_duration_seconds=float(avg_duration) if avg_duration is not None else None,
        feedback_positive_rate=(fb_good / fb_total) if fb_total else None,
    )


router = APIRouter(prefix="/api")


@router.get("/stats", response_model=StatsResponse)
def get_stats(session: Session = Depends(get_session)):
    return compute_stats(session)
