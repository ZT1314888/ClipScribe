"""data/ 目录下的路径工具。

所有运行期文件（SQLite、媒体、音频、导出、模型缓存、下载器配置）都在 data_dir 下，
按补充计划第 7、8 节组织。目录按需创建。
"""

from pathlib import Path

from app.config import settings


def data_dir() -> Path:
    d = settings.data_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sub(name: str) -> Path:
    d = data_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def media_dir() -> Path:
    """原始视频（7 天后清理）。"""
    return _sub("media")


def audio_dir() -> Path:
    """提取后的音频（7 天后清理）。"""
    return _sub("audio")


def exports_dir() -> Path:
    """导出文件（md/docx，长期保留）。"""
    return _sub("exports")


def models_dir() -> Path:
    """faster-whisper 模型缓存。"""
    return _sub("models")


def task_media_paths(task_id: str) -> tuple[Path, Path]:
    """返回 (该任务原始视频目录, 该任务音频目录)。"""
    m = media_dir() / task_id
    a = audio_dir() / task_id
    m.mkdir(parents=True, exist_ok=True)
    a.mkdir(parents=True, exist_ok=True)
    return m, a
