"""管道编排 —— 串起状态机各步，支持按步重试（补充计划第 4、5 节）。

约定：
- 每一步执行前把 Task.status 置为该步状态，执行成功后写入对应 Artifact。
- 支持从任意步重跑：复用已存在的上游产物；清洗/拆解/改写优先用人工修订稿。
- 单 worker 串行调用，故这里用同步 SQLAlchemy session，不考虑并发。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models import (
    Artifact,
    ArtifactKind,
    InputType,
    Task,
    TaskStatus,
)
from app.services import audio, downloader, text_pipeline, transcriber

logger = logging.getLogger(__name__)

# 状态机顺序（不含终态）
STEP_ORDER = [
    TaskStatus.DOWNLOADING,
    TaskStatus.EXTRACTING_AUDIO,
    TaskStatus.TRANSCRIBING,
    TaskStatus.CLEANING,
    TaskStatus.ANALYZING,
    TaskStatus.REWRITING,
]

# 文本阶段（媒体清理后仍可重跑）
TEXT_STEPS = frozenset(
    {TaskStatus.CLEANING, TaskStatus.ANALYZING, TaskStatus.REWRITING}
)


def _get_artifact(
    session: Session, task_id: str, kind: ArtifactKind
) -> Artifact | None:
    return session.scalar(
        select(Artifact).where(Artifact.task_id == task_id, Artifact.kind == kind)
    )


def _upsert_text(session: Session, task_id: str, kind: ArtifactKind, text: str) -> None:
    art = _get_artifact(session, task_id, kind)
    if art is None:
        art = Artifact(task_id=task_id, kind=kind, text=text)
        session.add(art)
    else:
        art.text = text
    session.flush()


def _upsert_file(session: Session, task_id: str, kind: ArtifactKind, path: str) -> None:
    art = _get_artifact(session, task_id, kind)
    if art is None:
        art = Artifact(task_id=task_id, kind=kind, file_path=path)
        session.add(art)
    else:
        art.file_path = path
    session.flush()


def _effective_transcript(session: Session, task_id: str) -> str:
    """下游优先用人工修订稿，否则用原始转写稿。"""
    revised = _get_artifact(session, task_id, ArtifactKind.REVISED_TRANSCRIPT)
    if revised and revised.text:
        return revised.text
    raw = _get_artifact(session, task_id, ArtifactKind.RAW_TRANSCRIPT)
    return raw.text if raw and raw.text else ""


# ---- 各步实现 ----


def _step_download(session: Session, task: Task) -> None:
    if task.input_type == InputType.UPLOAD:
        return  # 上传兜底：跳过下载
    result = downloader.download(task.source_url or "", task.id)
    task.video_title = result.video_title or task.video_title
    task.author = result.author or task.author
    task.collected_at = utcnow()
    _upsert_file(session, task.id, ArtifactKind.RAW_VIDEO, result.video_path)


def _step_extract_audio(session: Session, task: Task) -> None:
    raw = _get_artifact(session, task.id, ArtifactKind.RAW_VIDEO)
    if raw is None or not raw.file_path:
        raise RuntimeError("缺少原始视频/媒体文件，无法抽取音频。")
    audio_path = audio.extract_audio(task.id, raw.file_path)
    _upsert_file(session, task.id, ArtifactKind.AUDIO, audio_path)


def _step_transcribe(session: Session, task: Task) -> None:
    audio_art = _get_artifact(session, task.id, ArtifactKind.AUDIO)
    if audio_art is None or not audio_art.file_path:
        raise RuntimeError("缺少音频文件，无法转写。")
    text = transcriber.transcribe(audio_art.file_path)
    _upsert_text(session, task.id, ArtifactKind.RAW_TRANSCRIPT, text)


def _step_clean(session: Session, task: Task) -> None:
    transcript = _effective_transcript(session, task.id)
    if not transcript:
        raise RuntimeError("缺少转写稿，无法清洗。")
    _upsert_text(
        session, task.id, ArtifactKind.CLEANED, text_pipeline.clean(transcript)
    )


def _step_analyze(session: Session, task: Task) -> None:
    cleaned = _get_artifact(session, task.id, ArtifactKind.CLEANED)
    source = _effective_transcript(session, task.id)
    if cleaned and cleaned.text:
        source = cleaned.text
    _upsert_text(
        session, task.id, ArtifactKind.BREAKDOWN, text_pipeline.analyze(source)
    )


def _step_rewrite(session: Session, task: Task) -> None:
    cleaned = _get_artifact(session, task.id, ArtifactKind.CLEANED)
    source = _effective_transcript(session, task.id)
    if cleaned and cleaned.text:
        source = cleaned.text
    results = text_pipeline.rewrite(source)
    _upsert_text(session, task.id, ArtifactKind.REWRITE_ORAL, results["oral"])
    _upsert_text(session, task.id, ArtifactKind.REWRITE_NOTE, results["note"])
    _upsert_text(session, task.id, ArtifactKind.REWRITE_TITLE, results["title"])


_STEP_IMPL = {
    TaskStatus.DOWNLOADING: _step_download,
    TaskStatus.EXTRACTING_AUDIO: _step_extract_audio,
    TaskStatus.TRANSCRIBING: _step_transcribe,
    TaskStatus.CLEANING: _step_clean,
    TaskStatus.ANALYZING: _step_analyze,
    TaskStatus.REWRITING: _step_rewrite,
}


def run(session: Session, task: Task, from_step: TaskStatus | None = None) -> None:
    """从 from_step（默认整条链路起点）开始串行推进任务。

    抛异常时把任务置 failed 并记录错误信息；调用方负责提交 session。
    """
    if from_step is None:
        start_idx = 0
    else:
        start_idx = STEP_ORDER.index(from_step)

    steps = STEP_ORDER[start_idx:]
    task.started_at = task.started_at or utcnow()
    task.error_message = None

    try:
        for step in steps:
            task.status = step
            session.flush()
            logger.info("task %s -> %s", task.id, step.value)
            _STEP_IMPL[step](session, task)
            session.flush()

        task.status = TaskStatus.COMPLETED
        task.completed_at = utcnow()
        if task.started_at:
            delta = task.completed_at - task.started_at
            task.duration_seconds = int(delta.total_seconds())
        session.flush()
    except Exception as e:  # noqa: BLE001  任一步失败统一转 failed，支持重试
        logger.exception("task %s failed at %s", task.id, task.status)
        task.status = TaskStatus.FAILED
        task.error_message = str(e)
        session.flush()
