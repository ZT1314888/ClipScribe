"""抖音下载 —— 解析单条公开视频并落盘（补充计划第 2、3 节，ADR-0002）。

架构取舍：解析签名（a_bogus）与接口细节委托给开源库
`douyin-tiktok-scraper`（Evil0ctal），本模块只做「适配 + 落盘 + 错误映射」，
把库的输出收敛成稳定的 `DownloadResult`。日后换库（如 f2）只改本文件。

能力边界：仅单条公开视频。私密 / 已删除 / 无权限 / 风控 / 主页合集批量
一律映射为 `DownloadError`，由 pipeline 统一转 failed，提示改用本地上传兜底。

Cookie：从 `settings.douyin_cookie`（环境注入）读取，绝不在 UI 填、不入库、
不内置进镜像。`mock_douyin=True` 时不发网络请求，生成占位视频，保证无网络也能验收链路。
"""

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.core.paths import task_media_paths

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    video_path: str
    video_title: str | None = None
    author: str | None = None


class DownloadError(RuntimeError):
    """抖音解析或下载失败（含能力边界外的输入）。"""


class DownloadNotImplemented(DownloadError):
    """历史信号：保留以兼容旧引用，现继承 DownloadError。"""


def download(url: str, task_id: str) -> DownloadResult:
    """解析并下载单条抖音公开视频，返回落盘后的 DownloadResult。

    - `mock_douyin=True`：生成占位视频（不联网），用于链路连通性验收。
    - 否则：走真实解析 + 流式下载；任何失败抛 DownloadError。

    落盘目录复用 `media/<task_id>/` 约定，与上传兜底一致，供 7 天保留清理。

    注意：本函数为同步接口，由单 worker 在工作线程中调用；线程内无运行中的
    事件循环，故内部用 asyncio.run 驱动异步解析是安全的。
    """
    text = (url or "").strip()
    if not text:
        raise DownloadError("未提供抖音链接。")

    if settings.mock_douyin:
        return _mock_download(task_id)
    return _real_download(text, task_id)


def _dest_dir(task_id: str) -> Path:
    """任务的原始视频目录：media/<task_id>/，与上传兜底同约定。"""
    media_dir, _audio_dir = task_media_paths(task_id)
    return media_dir


def _mock_download(task_id: str) -> DownloadResult:
    """生成 1 秒黑屏静音 mp4 作为占位，无需外部素材，仅验收链路连通性。"""
    out_path = _dest_dir(task_id) / "video.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x240:d=1",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=16000:cl=mono",
        "-shortest",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise DownloadError("MOCK_DOUYIN 占位视频生成失败（需要 ffmpeg）：" + tail)
    return DownloadResult(
        video_path=str(out_path),
        video_title="[MOCK] 抖音占位视频",
        author="[MOCK] 占位作者",
    )


# douyin-tiktok-scraper 的 hybrid_parsing 返回结构（v1.2.x）：
#   { status, message, type('video'/'image'), platform, aweme_id,
#     desc(标题), author{nickname,...},
#     video_data{ nwm_video_url, nwm_video_url_HQ, wm_video_url, ... } }
# 无水印地址优先 HQ，回退普通清晰度。


def _extract_meta(data: dict) -> tuple[str, str | None, str | None]:
    """从库返回的解析结果里提取 (无水印视频地址, 标题, 作者)。

    对能力边界外的输入（失败/图集/私密等）给出清晰中文错误。
    """
    if not isinstance(data, dict):
        raise DownloadError("解析结果为空或格式异常，可能是私密/已删除/被风控的视频。")

    if data.get("status") != "success":
        msg = (
            data.get("message") or "解析失败，可能是私密/已删除/无权限或被风控的视频。"
        )
        raise DownloadError(f"抖音解析未成功：{msg}")

    media_type = str(data.get("type") or "").lower()
    if media_type != "video":
        raise DownloadError(
            f"该内容类型为「{media_type or '未知'}」，第一版仅支持单条视频。"
        )

    video_data = data.get("video_data")
    video_url = None
    if isinstance(video_data, dict):
        video_url = (
            video_data.get("nwm_video_url_HQ")
            or video_data.get("nwm_video_url")
            or video_data.get("wm_video_url")
        )
    if not isinstance(video_url, str) or not video_url.strip():
        raise DownloadError(
            "未取到可下载的视频地址，可能是私密/已删除/无权限/被风控的视频。"
            "请改用本地上传兜底。"
        )

    title = data.get("desc")
    title = title.strip() if isinstance(title, str) and title.strip() else None

    author = None
    author_obj = data.get("author")
    if isinstance(author_obj, dict):
        nickname = author_obj.get("nickname")
        if isinstance(nickname, str) and nickname.strip():
            author = nickname.strip()
    elif isinstance(author_obj, str) and author_obj.strip():
        author = author_obj.strip()

    return video_url.strip(), title, author


async def _parse(url: str, cookie: str) -> dict:
    """调用开源库解析分享链接 → 结构化数据。"""
    try:
        from douyin_tiktok_scraper.scraper import Scraper
    except ImportError as e:  # pragma: no cover - 依赖缺失时的清晰提示
        raise DownloadError(
            "未安装抖音解析库 douyin-tiktok-scraper。请执行 `uv sync` 后重试。"
        ) from e

    api = Scraper()
    if cookie:
        # 通过抖音 API 请求头注入 Cookie，提升公开视频解析成功率
        api.douyin_api_headers["Cookie"] = cookie
    try:
        return await api.hybrid_parsing(url)
    except DownloadError:
        raise
    except Exception as e:  # noqa: BLE001  库内异常统一转 DownloadError
        raise DownloadError(f"抖音解析失败：{e}") from e


def _real_download(url: str, task_id: str) -> DownloadResult:
    data = asyncio.run(_parse(url, settings.douyin_cookie))
    video_url, title, author = _extract_meta(data)

    out_path = _dest_dir(task_id) / "video.mp4"
    _stream_to_file(video_url, out_path)

    return DownloadResult(video_path=str(out_path), video_title=title, author=author)


def _stream_to_file(video_url: str, out_path: Path) -> None:
    """流式把无水印视频下载到本地。"""
    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise DownloadError("未安装 httpx。请执行 `uv sync` 后重试。") from e

    headers = {
        # 抖音 CDN 对 UA/Referer 敏感，带上常见头提升成功率
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
    }
    if settings.douyin_cookie:
        headers["Cookie"] = settings.douyin_cookie

    timeout = settings.douyin_download_timeout
    try:
        with httpx.stream(
            "GET", video_url, headers=headers, timeout=timeout, follow_redirects=True
        ) as resp:
            if resp.status_code != 200:
                raise DownloadError(
                    f"下载视频失败：HTTP {resp.status_code}（可能被风控或地址过期）。"
                )
            with open(out_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    f.write(chunk)
    except DownloadError:
        raise
    except Exception as e:  # noqa: BLE001
        raise DownloadError(f"下载视频时网络错误：{e}") from e

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise DownloadError("下载到的视频为空，可能地址已过期或被风控。")
