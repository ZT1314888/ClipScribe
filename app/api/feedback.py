"""反馈 API：每条改写结果的 好用/不好用 + 原因标签。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Feedback, Task
from app.schemas.task import FeedbackRequest

router = APIRouter(prefix="/api")


@router.post("/tasks/{task_id}/feedback")
def submit_feedback(
    task_id: str,
    payload: FeedbackRequest,
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在。")
    session.add(
        Feedback(
            task_id=task_id,
            rewrite_kind=payload.rewrite_kind,
            verdict=payload.verdict,
            reason_tags=payload.reason_tags,
            comment=payload.comment,
        )
    )
    session.commit()
    return {"ok": True}
