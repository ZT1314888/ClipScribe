"""抖音下载 —— 【本阶段留桩】。

补充计划：第一版垂直骨架先跑通"本地上传兜底"全链路，真实抖音解析下载延后。
这里固定接口与 Cookie 注入 seam（从 config 读，绝不在 UI 填），
导入下载阶段只替换实现，不改调用方。
"""

from dataclasses import dataclass

from app.config import settings


@dataclass
class DownloadResult:
    video_path: str
    video_title: str | None = None
    author: str | None = None


class DownloadNotImplemented(RuntimeError):
    """抖音下载尚未实现的信号，调用方据此提示改用本地上传。"""


def download(url: str) -> DownloadResult:
    """解析并下载单条抖音公开视频。

    本阶段未实现：抛 DownloadNotImplemented，pipeline 会把任务置为 failed，
    并提示用户改用本地上传兜底。
    """
    # Cookie seam：真实实现从 settings.douyin_cookie 读取（环境注入，不入 UI）。
    _cookie = settings.douyin_cookie  # noqa: F841  预留，导入下载阶段使用
    raise DownloadNotImplemented(
        "抖音链接下载尚未实现（第一版垂直骨架）。请改用本地上传视频/音频兜底。"
    )
