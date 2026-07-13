"""SQLite 数据库装配：engine + SessionLocal + Base。

补充计划要求用 SQLite（不用 Postgres 异步引擎）。这里用同步 SQLAlchemy，
配合单 worker 串行执行，避免异步引擎与并发复杂度。
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings
from app.core.paths import data_dir


class Base(DeclarativeBase):
    pass


# data/ 需先存在，SQLite 才能建库文件
data_dir()

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """建表。导入所有 model 后调用（放在 lifespan 启动）。"""
    from app import models  # noqa: F401  确保 model 注册到 Base.metadata

    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：请求级 session。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
