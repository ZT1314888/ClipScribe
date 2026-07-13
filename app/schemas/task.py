"""Pydantic DTO：提交/详情/编辑/反馈请求响应。"""

from datetime import datetime

from pydantic import BaseModel

from app.models.artifact import ArtifactKind
from app.models.feedback import FeedbackVerdict
from app.models.task import InputType, TaskStatus


class SubmitResponse(BaseModel):
    task_id: str
    status: TaskStatus


class TaskSummary(BaseModel):
    id: str
    status: TaskStatus
    input_type: InputType
    source_url: str | None
    video_title: str | None
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None


class TranscriptUpdate(BaseModel):
    text: str


class RetryRequest(BaseModel):
    step: TaskStatus | None = None  # 缺省从失败步骤/整链重跑


class FeedbackRequest(BaseModel):
    rewrite_kind: ArtifactKind
    verdict: FeedbackVerdict
    reason_tags: str | None = None
    comment: str | None = None


class StatsResponse(BaseModel):
    total_tasks: int
    success_rate: float
    avg_duration_seconds: float | None
    feedback_positive_rate: float | None
