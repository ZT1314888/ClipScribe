"""downloader 边界测试：解析结果映射、能力边界错误、Cookie 透传、落盘。

全部 mock 网络与外部库，无需外网 / Cookie / ffmpeg 即可运行。
真实抖音链路的端到端联调见 docs/douyin-download.md（需真 Cookie+外网）。
"""

import pytest

from app.config import settings
from app.services import downloader
from app.services.downloader import DownloadError, DownloadResult

# ---- download() 入口 ----


def test_empty_url_raises():
    with pytest.raises(DownloadError, match="未提供"):
        downloader.download("", "task-1")


def test_mock_branch_generates_placeholder(monkeypatch):
    """mock_douyin=True 时不走真实解析，直接生成占位视频。"""
    monkeypatch.setattr(settings, "mock_douyin", True)

    calls = {}

    def fake_run(cmd, capture_output, text):
        # 假装 ffmpeg 成功：建出目标文件
        out = cmd[-1]
        with open(out, "wb") as f:
            f.write(b"\x00" * 16)
        calls["cmd"] = cmd

        class P:
            returncode = 0
            stderr = ""
            stdout = ""

        return P()

    monkeypatch.setattr(downloader.subprocess, "run", fake_run)

    result = downloader.download("https://v.douyin.com/abc/", "task-mock")
    assert isinstance(result, DownloadResult)
    assert result.video_path.endswith("video.mp4")
    assert "task-mock" in result.video_path
    assert "MOCK" in (result.video_title or "")
    assert "ffmpeg" in calls["cmd"][0]


def test_mock_branch_ffmpeg_failure(monkeypatch):
    monkeypatch.setattr(settings, "mock_douyin", True)

    def fake_run(cmd, capture_output, text):
        class P:
            returncode = 1
            stderr = "ffmpeg boom"
            stdout = ""

        return P()

    monkeypatch.setattr(downloader.subprocess, "run", fake_run)
    with pytest.raises(DownloadError, match="占位视频生成失败"):
        downloader.download("https://v.douyin.com/abc/", "task-mock-fail")


# ---- _extract_meta()：解析结果 → 字段映射 ----


def _ok_payload():
    return {
        "status": "success",
        "type": "video",
        "desc": "  标题文案  ",
        "author": {"nickname": "  作者昵称 "},
        "video_data": {
            "nwm_video_url": "https://cdn/normal.mp4",
            "nwm_video_url_HQ": "https://cdn/hq.mp4",
            "wm_video_url": "https://cdn/wm.mp4",
        },
    }


def test_extract_meta_prefers_hq_and_trims():
    url, title, author = downloader._extract_meta(_ok_payload())
    assert url == "https://cdn/hq.mp4"
    assert title == "标题文案"
    assert author == "作者昵称"


def test_extract_meta_falls_back_to_normal_url():
    data = _ok_payload()
    data["video_data"].pop("nwm_video_url_HQ")
    url, _, _ = downloader._extract_meta(data)
    assert url == "https://cdn/normal.mp4"


def test_extract_meta_status_failed():
    with pytest.raises(DownloadError, match="解析未成功"):
        downloader._extract_meta({"status": "failed", "message": "私密视频"})


def test_extract_meta_image_type_rejected():
    with pytest.raises(DownloadError, match="仅支持单条视频"):
        downloader._extract_meta({"status": "success", "type": "image"})


def test_extract_meta_no_video_url():
    data = _ok_payload()
    data["video_data"] = {}
    with pytest.raises(DownloadError, match="未取到可下载的视频地址"):
        downloader._extract_meta(data)


def test_extract_meta_non_dict():
    with pytest.raises(DownloadError):
        downloader._extract_meta(None)  # type: ignore[arg-type]


def test_extract_meta_author_as_string():
    data = _ok_payload()
    data["author"] = "纯字符串作者"
    _, _, author = downloader._extract_meta(data)
    assert author == "纯字符串作者"


# ---- _real_download()：串起解析 + 落盘 ----


def test_real_download_maps_fields_and_writes(monkeypatch):
    monkeypatch.setattr(settings, "mock_douyin", False)

    async def fake_parse(url, cookie):
        assert url == "https://v.douyin.com/real/"
        return _ok_payload()

    captured = {}

    def fake_stream(video_url, out_path):
        captured["video_url"] = video_url
        captured["out_path"] = out_path
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 32)

    monkeypatch.setattr(downloader, "_parse", fake_parse)
    monkeypatch.setattr(downloader, "_stream_to_file", fake_stream)

    result = downloader.download("https://v.douyin.com/real/", "task-real")
    assert result.video_title == "标题文案"
    assert result.author == "作者昵称"
    assert result.video_path.endswith("video.mp4")
    assert "task-real" in result.video_path
    # 下载的是 HQ 无水印地址
    assert captured["video_url"] == "https://cdn/hq.mp4"


def test_real_download_propagates_parse_error(monkeypatch):
    monkeypatch.setattr(settings, "mock_douyin", False)

    async def fake_parse(url, cookie):
        raise DownloadError("解析失败：风控")

    monkeypatch.setattr(downloader, "_parse", fake_parse)
    with pytest.raises(DownloadError, match="风控"):
        downloader.download("https://v.douyin.com/x/", "task-err")


# ---- _parse()：Cookie 透传 ----


def test_parse_injects_cookie_into_headers(monkeypatch):
    import asyncio

    seen = {}

    class FakeScraper:
        def __init__(self):
            self.douyin_api_headers = {}

        async def hybrid_parsing(self, url):
            seen["cookie"] = self.douyin_api_headers.get("Cookie")
            seen["url"] = url
            return _ok_payload()

    import douyin_tiktok_scraper.scraper as scraper_mod

    monkeypatch.setattr(scraper_mod, "Scraper", FakeScraper)

    asyncio.run(downloader._parse("https://v.douyin.com/c/", "sessionid=abc123"))
    assert seen["cookie"] == "sessionid=abc123"
    assert seen["url"] == "https://v.douyin.com/c/"


def test_parse_no_cookie_when_empty(monkeypatch):
    import asyncio

    seen = {}

    class FakeScraper:
        def __init__(self):
            self.douyin_api_headers = {}

        async def hybrid_parsing(self, url):
            seen["has_cookie"] = "Cookie" in self.douyin_api_headers
            return _ok_payload()

    import douyin_tiktok_scraper.scraper as scraper_mod

    monkeypatch.setattr(scraper_mod, "Scraper", FakeScraper)

    asyncio.run(downloader._parse("https://v.douyin.com/c/", ""))
    assert seen["has_cookie"] is False


def test_parse_wraps_library_exception(monkeypatch):
    import asyncio

    class FakeScraper:
        def __init__(self):
            self.douyin_api_headers = {}

        async def hybrid_parsing(self, url):
            raise ValueError("库内部炸了")

    import douyin_tiktok_scraper.scraper as scraper_mod

    monkeypatch.setattr(scraper_mod, "Scraper", FakeScraper)

    with pytest.raises(DownloadError, match="抖音解析失败"):
        asyncio.run(downloader._parse("https://v.douyin.com/c/", ""))
