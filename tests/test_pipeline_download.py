"""pipeline._step_download 测试：UPLOAD 跳过下载，LINK 调 downloader 并落 artifact。

用独立内存 SQLite，避免依赖模块级 engine。
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Artifact, ArtifactKind, InputType, Task, TaskStatus
from app.services import pipeline
from app.services.downloader import DownloadResult


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    import app.models  # noqa: F401  注册 model 到 Base.metadata

    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, expire_on_commit=False)
    s = Local()
    try:
        yield s
    finally:
        s.close()


def test_step_download_skips_upload(session, monkeypatch):
    """上传兜底：_step_download 直接返回，不调 downloader。"""
    called = {"n": 0}

    def fake_download(url, task_id):
        called["n"] += 1
        return DownloadResult(video_path="x")

    monkeypatch.setattr(pipeline.downloader, "download", fake_download)

    task = Task(id="t-up", status=TaskStatus.PENDING, input_type=InputType.UPLOAD)
    session.add(task)
    session.flush()

    pipeline._step_download(session, task)
    assert called["n"] == 0


def test_step_download_link_writes_artifact(session, monkeypatch):
    """链接任务：调 downloader，写 RAW_VIDEO artifact 并回填标题/作者。"""

    def fake_download(url, task_id):
        assert task_id == "t-link"
        return DownloadResult(
            video_path="/data/media/t-link/video.mp4",
            video_title="真实标题",
            author="真实作者",
        )

    monkeypatch.setattr(pipeline.downloader, "download", fake_download)

    task = Task(
        id="t-link",
        status=TaskStatus.PENDING,
        input_type=InputType.LINK,
        source_url="https://v.douyin.com/abc/",
    )
    session.add(task)
    session.flush()

    pipeline._step_download(session, task)

    assert task.video_title == "真实标题"
    assert task.author == "真实作者"
    assert task.collected_at is not None

    art = session.scalar(
        select(Artifact).where(
            Artifact.task_id == "t-link",
            Artifact.kind == ArtifactKind.RAW_VIDEO,
        )
    )
    assert art is not None
    assert art.file_path == "/data/media/t-link/video.mp4"


def test_step_download_propagates_error(session, monkeypatch):
    from app.services.downloader import DownloadError

    def fake_download(url, task_id):
        raise DownloadError("私密视频")

    monkeypatch.setattr(pipeline.downloader, "download", fake_download)

    task = Task(
        id="t-fail",
        status=TaskStatus.PENDING,
        input_type=InputType.LINK,
        source_url="https://v.douyin.com/x/",
    )
    session.add(task)
    session.flush()

    with pytest.raises(DownloadError, match="私密视频"):
        pipeline._step_download(session, task)
