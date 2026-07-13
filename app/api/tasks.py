"""任务相关 API：提交、列表(搜索)、详情、编辑转写稿、按步重试、导出。"""

import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.paths import task_media_paths
from app.db import get_session
from app.models import Artifact, ArtifactKind, InputType, Task, TaskStatus
from app.schemas.task import (
    RetryRequest,
    SubmitResponse,
    TaskSummary,
    TranscriptUpdate,
)
from app.services import exporter
from app.services.audio import guess_is_media
from app.worker.queue import task_queue

router = APIRouter(prefix="/api")


@router.post("/tasks", response_model=SubmitResponse)
async def submit_task(
    source_url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    session: Session = Depends(get_session),
):
    """提交任务：抖音链接（本阶段留桩会失败）或本地上传兜底。"""
    if not source_url and file is None:
        raise HTTPException(400, "请提供抖音链接或上传本地视频/音频文件。")

    task_id = str(uuid.uuid4())
    input_type = InputType.UPLOAD if file is not None else InputType.LINK
    task = Task(id=task_id, status=TaskStatus.PENDING, input_type=input_type)

    if file is not None:
        media_dir, _audio_dir = task_media_paths(task_id)
        dest = media_dir / (file.filename or "upload.bin")
        size = 0
        async with aiofiles.open(dest, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.upload_max_mb * 1024 * 1024:
                    raise HTTPException(
                        413, f"文件超过 {settings.upload_max_mb}MB 上限。"
                    )
                await out.write(chunk)
        if not guess_is_media(file.filename or ""):
            raise HTTPException(400, "不支持的文件类型，请上传视频或音频。")
        task.video_title = file.filename
        session.add(task)
        session.flush()
        session.add(
            Artifact(
                task_id=task_id,
                kind=ArtifactKind.RAW_VIDEO,
                file_path=str(dest),
            )
        )
    else:
        task.source_url = source_url
        session.add(task)

    session.commit()
    await task_queue.submit(task_id)
    return SubmitResponse(task_id=task_id, status=task.status)


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(
    q: str | None = None,
    status: TaskStatus | None = None,
    session: Session = Depends(get_session),
):
    """时间倒序，按标题/链接/状态搜索。不记录提交人。"""
    stmt = select(Task).order_by(Task.created_at.desc())
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Task.video_title.like(like), Task.source_url.like(like)))
    return list(session.scalars(stmt).all())


@router.put("/tasks/{task_id}/transcript")
def edit_transcript(
    task_id: str,
    payload: TranscriptUpdate,
    session: Session = Depends(get_session),
):
    """保存人工修订转写稿（下游清洗/拆解/改写优先用它）。"""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在。")
    art = session.scalar(
        select(Artifact).where(
            Artifact.task_id == task_id,
            Artifact.kind == ArtifactKind.REVISED_TRANSCRIPT,
        )
    )
    if art is None:
        session.add(
            Artifact(
                task_id=task_id,
                kind=ArtifactKind.REVISED_TRANSCRIPT,
                text=payload.text,
            )
        )
    else:
        art.text = payload.text
    session.commit()
    return {"ok": True}


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    payload: RetryRequest,
    session: Session = Depends(get_session),
):
    """从指定步骤（或整链）重试。"""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在。")

    step = payload.step
    # 媒体已清理时不允许从需要媒体的步骤重跑
    if task.media_cleaned and step in {
        TaskStatus.DOWNLOADING,
        TaskStatus.EXTRACTING_AUDIO,
        TaskStatus.TRANSCRIBING,
    }:
        raise HTTPException(409, "原始媒体已按保留策略清理，请重新提交链接或上传文件。")

    task.status = TaskStatus.PENDING
    task.error_message = None
    session.commit()
    await task_queue.submit(task_id, from_step=step)
    return {"ok": True, "from_step": step}


@router.get("/tasks/{task_id}/export/{fmt}")
def export_task(
    task_id: str,
    fmt: str,
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在。")
    if fmt == "md":
        path = exporter.export_markdown(session, task)
        session.commit()
        return FileResponse(path, media_type="text/markdown", filename=f"{task_id}.md")
    if fmt == "docx":
        path = exporter.export_docx(session, task)
        session.commit()
        return FileResponse(
            path,
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            filename=f"{task_id}.docx",
        )
    raise HTTPException(400, "仅支持 md / docx。")
