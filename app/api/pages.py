"""Jinja2 页面路由：登录、提交、列表、详情、统计。

提交页优先复用上游 static 单页；此处也提供一个 Jinja2 提交页作为统一入口。
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.stats import compute_stats
from app.db import get_session
from app.models import Artifact, Task, TaskStatus
from app.models.artifact import REWRITE_KINDS, ArtifactKind

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: int | None = None):
    return templates.TemplateResponse(request, "login.html", {"error": bool(error)})


@router.get("/", response_class=HTMLResponse)
def submit_page(request: Request):
    return templates.TemplateResponse(request, "submit.html", {})


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
):
    stmt = select(Task).order_by(Task.created_at.desc())
    if status:
        stmt = stmt.where(Task.status == TaskStatus(status))
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_

        stmt = stmt.where(or_(Task.video_title.like(like), Task.source_url.like(like)))
    tasks = list(session.scalars(stmt).all())
    return templates.TemplateResponse(
        request,
        "tasks.html",
        {"tasks": tasks, "q": q or "", "status": status or "", "statuses": TaskStatus},
    )


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail_page(
    request: Request,
    task_id: str,
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if task is None:
        return HTMLResponse("任务不存在", status_code=404)
    arts = {
        a.kind: a
        for a in session.scalars(
            select(Artifact).where(Artifact.task_id == task_id)
        ).all()
    }
    rewrite_labels = {
        ArtifactKind.REWRITE_ORAL: "口播稿",
        ArtifactKind.REWRITE_NOTE: "种草笔记",
        ArtifactKind.REWRITE_TITLE: "标题与开头钩子",
    }
    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "task": task,
            "arts": arts,
            "K": ArtifactKind,
            "rewrite_kinds": REWRITE_KINDS,
            "rewrite_labels": rewrite_labels,
            "statuses": TaskStatus,
        },
    )


@router.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, session: Session = Depends(get_session)):
    stats = compute_stats(session)
    return templates.TemplateResponse(request, "stats.html", {"stats": stats})
