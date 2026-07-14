"""抖音下载 —— 解析单条公开视频并落盘（补充计划第 2、3 节，ADR-0002）。

架构取舍：a_bogus 签名与接口细节委托给 vendored 的 douyin-downloader API 层
（`app/services/douyin_vendor/`，见其 UPSTREAM.md）。本模块只做
「适配 + 落盘 + 错误映射」，把上游输出收敛成稳定的 `DownloadResult`。
日后换库只改本文件与 vendor 目录。

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


# vendored douyin-downloader 的 get_video_detail 返回 aweme_detail 结构（节选）：
#   { aweme_id, desc(标题), author{nickname,...},
#     video{ play_addr{url_list:[...]}, play_addr_h264{...},
#            download_addr{...}, bit_rate:[{play_addr{url_list}}] },
#     image_post_info / images(图集时存在) }
# 无水印地址优先 play_addr，回退 h264 / download_addr / bit_rate。


def _extract_meta(detail: dict) -> tuple[str, str | None, str | None]:
    """从 aweme_detail 提取 (无水印视频地址, 标题, 作者)。

    对能力边界外的输入（图集/私密/风控/空结构等）给出清晰中文错误。
    """
    if not isinstance(detail, dict) or not detail:
        raise DownloadError(
            "未取到视频信息，可能是私密/已删除/无权限/被风控的视频。请改用本地上传兜底。"
        )

    # 图集（image_post_info/images）不是单条视频，明确拒绝
    if detail.get("image_post_info") or detail.get("images"):
        raise DownloadError("该内容为图集，第一版仅支持单条视频。请改用本地上传兜底。")

    video = detail.get("video")
    if not isinstance(video, dict):
        raise DownloadError(
            "解析结果不含视频数据，可能是私密/已删除/被风控的视频。请改用本地上传兜底。"
        )

    video_url = _pick_video_url(video)
    if not video_url:
        raise DownloadError(
            "未取到可下载的视频地址，可能是私密/已删除/无权限/被风控的视频。"
            "请改用本地上传兜底。"
        )

    title = detail.get("desc")
    title = title.strip() if isinstance(title, str) and title.strip() else None

    author = None
    author_obj = detail.get("author")
    if isinstance(author_obj, dict):
        nickname = author_obj.get("nickname")
        if isinstance(nickname, str) and nickname.strip():
            author = nickname.strip()

    return video_url, title, author


def _pick_video_url(video: dict) -> str | None:
    """从 aweme_detail.video 抠一个可下载的无水印地址。

    优先 play_addr（无水印），依次回退 h264 / download_addr / bit_rate。
    """
    for key in ("play_addr", "play_addr_h264", "download_addr"):
        addr = video.get(key)
        if isinstance(addr, dict):
            url_list = addr.get("url_list") or []
            if url_list and isinstance(url_list[0], str) and url_list[0].strip():
                return url_list[0].strip()

    bit_rate = video.get("bit_rate") or []
    if isinstance(bit_rate, list) and bit_rate:
        play_addr = (bit_rate[0] or {}).get("play_addr") or {}
        url_list = play_addr.get("url_list") or []
        if url_list and isinstance(url_list[0], str) and url_list[0].strip():
            return url_list[0].strip()

    return None


async def _parse(url: str, cookie: str) -> dict:
    """用 vendored douyin-downloader API 层解析链接 → aweme_detail。

    流程：短链跟随重定向 → URLParser 取 aweme_id → get_video_detail。
    不开浏览器，纯 HTTP + a_bogus 签名。
    """
    try:
        from app.services.douyin_vendor import (
            DouyinAPIClient,
            URLParser,
            parse_cookie_header,
        )
    except ImportError as e:  # pragma: no cover - 依赖缺失时的清晰提示
        raise DownloadError(
            "抖音解析组件缺少依赖（aiohttp/gmssl）。请执行 `uv sync` 后重试。"
        ) from e

    resolved = await _resolve_share_url(url)
    parsed = URLParser.parse(resolved)
    aweme_id = (parsed or {}).get("aweme_id")
    if not aweme_id:
        raise DownloadError(
            "无法从链接解析出视频 ID，可能是主页/合集/直播等非单视频链接。"
            "第一版仅支持单条视频，请改用本地上传兜底。"
        )

    cookies = parse_cookie_header(cookie)
    # 预置一个占位 msToken：避免 vendored 层为补 msToken 去发外部请求
    # （githubusercontent + mssdk）。实测占位 token + a_bogus 即可成功解析。
    cookies.setdefault("msToken", _placeholder_ms_token())

    try:
        async with DouyinAPIClient(cookies) as client:
            detail = await client.get_video_detail(str(aweme_id))
    except DownloadError:
        raise
    except Exception as e:  # noqa: BLE001  vendored 层异常统一转 DownloadError
        raise DownloadError(f"抖音解析失败：{e}") from e

    return detail or {}


def _placeholder_ms_token() -> str:
    """生成长度合规的占位 msToken（避免 vendored 层联网补 token）。"""
    import random
    import string

    body = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(182))
    return body + "=="


async def _resolve_share_url(url: str) -> str:
    """跟随重定向把 v.douyin.com 短链换成含 aweme_id 的真链。

    非短链（已含 /video/ 或 modal_id=）直接返回，避免多余请求。
    """
    if "v.douyin.com" not in url:
        return url

    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise DownloadError("未安装 httpx。请执行 `uv sync` 后重试。") from e

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        ),
    }
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=settings.douyin_download_timeout
        ) as client:
            resp = await client.get(url, headers=headers)
            return str(resp.url)
    except Exception as e:  # noqa: BLE001
        raise DownloadError(f"短链跳转解析失败：{e}") from e


def _real_download(url: str, task_id: str) -> DownloadResult:
    detail = asyncio.run(_parse(url, settings.douyin_cookie))
    video_url, title, author = _extract_meta(detail)

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
