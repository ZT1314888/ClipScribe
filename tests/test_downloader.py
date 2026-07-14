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


# ---- _extract_meta()：aweme_detail → 字段映射 ----


def _ok_detail():
    """vendored get_video_detail 返回的 aweme_detail 形状（节选）。"""
    return {
        "aweme_id": "7658630307536506162",
        "desc": "  标题文案  ",
        "author": {"nickname": "  作者昵称 "},
        "video": {
            "play_addr": {"url_list": ["https://cdn/play.mp4"]},
            "play_addr_h264": {"url_list": ["https://cdn/h264.mp4"]},
            "download_addr": {"url_list": ["https://cdn/download.mp4"]},
            "bit_rate": [
                {"play_addr": {"url_list": ["https://cdn/bitrate.mp4"]}},
            ],
        },
    }


def test_extract_meta_prefers_play_addr_and_trims():
    url, title, author = downloader._extract_meta(_ok_detail())
    assert url == "https://cdn/play.mp4"
    assert title == "标题文案"
    assert author == "作者昵称"


def test_extract_meta_falls_back_to_h264():
    detail = _ok_detail()
    detail["video"].pop("play_addr")
    url, _, _ = downloader._extract_meta(detail)
    assert url == "https://cdn/h264.mp4"


def test_extract_meta_falls_back_to_download_addr():
    detail = _ok_detail()
    detail["video"].pop("play_addr")
    detail["video"].pop("play_addr_h264")
    url, _, _ = downloader._extract_meta(detail)
    assert url == "https://cdn/download.mp4"


def test_extract_meta_falls_back_to_bit_rate():
    detail = _ok_detail()
    detail["video"].pop("play_addr")
    detail["video"].pop("play_addr_h264")
    detail["video"].pop("download_addr")
    url, _, _ = downloader._extract_meta(detail)
    assert url == "https://cdn/bitrate.mp4"


def test_extract_meta_empty_detail_rejected():
    with pytest.raises(DownloadError, match="未取到视频信息"):
        downloader._extract_meta({})


def test_extract_meta_non_dict():
    with pytest.raises(DownloadError, match="未取到视频信息"):
        downloader._extract_meta(None)  # type: ignore[arg-type]


def test_extract_meta_image_post_rejected():
    detail = _ok_detail()
    detail["image_post_info"] = {"images": [{"url": "x"}]}
    with pytest.raises(DownloadError, match="图集"):
        downloader._extract_meta(detail)


def test_extract_meta_no_video_data_rejected():
    detail = _ok_detail()
    detail.pop("video")
    with pytest.raises(DownloadError, match="不含视频数据"):
        downloader._extract_meta(detail)


def test_extract_meta_no_video_url():
    detail = _ok_detail()
    detail["video"] = {"play_addr": {"url_list": []}}
    with pytest.raises(DownloadError, match="未取到可下载的视频地址"):
        downloader._extract_meta(detail)


def test_extract_meta_title_missing_ok():
    detail = _ok_detail()
    detail.pop("desc")
    _, title, _ = downloader._extract_meta(detail)
    assert title is None


# ---- _real_download()：串起解析 + 落盘 ----


def test_real_download_maps_fields_and_writes(monkeypatch):
    monkeypatch.setattr(settings, "mock_douyin", False)

    async def fake_parse(url, cookie):
        assert url == "https://v.douyin.com/real/"
        return _ok_detail()

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
    # 下载的是 play_addr 无水印地址
    assert captured["video_url"] == "https://cdn/play.mp4"


def test_real_download_propagates_parse_error(monkeypatch):
    monkeypatch.setattr(settings, "mock_douyin", False)

    async def fake_parse(url, cookie):
        raise DownloadError("解析失败：风控")

    monkeypatch.setattr(downloader, "_parse", fake_parse)
    with pytest.raises(DownloadError, match="风控"):
        downloader.download("https://v.douyin.com/x/", "task-err")


# ---- _parse()：链接解析 + cookie 转 dict + vendored 调用 ----


class _FakeClient:
    """替身 DouyinAPIClient：记录构造它的 cookies，返回预置 detail。"""

    last_cookies: dict = {}
    detail_to_return: dict = {}
    raise_exc: Exception | None = None

    def __init__(self, cookies, proxy=None):
        type(self).last_cookies = cookies

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_video_detail(self, aweme_id):
        type(self).last_aweme_id = aweme_id
        if type(self).raise_exc:
            raise type(self).raise_exc
        return type(self).detail_to_return


def _patch_vendor(monkeypatch, detail=None, raise_exc=None):
    """把 downloader 里 import 的 vendored 符号替换为可控替身。"""
    import app.services.douyin_vendor as vendor

    _FakeClient.detail_to_return = detail if detail is not None else _ok_detail()
    _FakeClient.raise_exc = raise_exc
    monkeypatch.setattr(vendor, "DouyinAPIClient", _FakeClient)


def test_parse_resolves_id_and_passes_cookie(monkeypatch):
    import asyncio

    _patch_vendor(monkeypatch)

    # 不联网：短链解析直接返回原 url（本例用长链，不触发重定向）
    async def fake_resolve(url):
        return url

    monkeypatch.setattr(downloader, "_resolve_share_url", fake_resolve)

    detail = asyncio.run(
        downloader._parse(
            "https://www.douyin.com/video/7658630307536506162",
            "ttwid=abc; sessionid=xyz",
        )
    )
    assert detail["aweme_id"] == "7658630307536506162"
    assert _FakeClient.last_aweme_id == "7658630307536506162"
    # cookie 头被转成 dict 传入
    assert _FakeClient.last_cookies["ttwid"] == "abc"
    assert _FakeClient.last_cookies["sessionid"] == "xyz"
    # 预置了占位 msToken，避免 vendored 层联网补 token
    assert "msToken" in _FakeClient.last_cookies


def test_parse_modal_id_link(monkeypatch):
    import asyncio

    _patch_vendor(monkeypatch)

    async def fake_resolve(url):
        return url

    monkeypatch.setattr(downloader, "_resolve_share_url", fake_resolve)

    detail = asyncio.run(
        downloader._parse(
            "https://www.douyin.com/jingxuan?modal_id=7658630307536506162", ""
        )
    )
    assert detail["aweme_id"] == "7658630307536506162"
    assert _FakeClient.last_aweme_id == "7658630307536506162"


def test_parse_unresolvable_link_raises(monkeypatch):
    import asyncio

    _patch_vendor(monkeypatch)

    async def fake_resolve(url):
        return url

    monkeypatch.setattr(downloader, "_resolve_share_url", fake_resolve)

    # 主页链接解析不出 aweme_id
    with pytest.raises(DownloadError, match="仅支持单条视频"):
        asyncio.run(
            downloader._parse("https://www.douyin.com/user/MS4wLjABAAAA", "")
        )


def test_parse_wraps_client_exception(monkeypatch):
    import asyncio

    _patch_vendor(monkeypatch, raise_exc=ValueError("vendored 层炸了"))

    async def fake_resolve(url):
        return url

    monkeypatch.setattr(downloader, "_resolve_share_url", fake_resolve)

    with pytest.raises(DownloadError, match="抖音解析失败"):
        asyncio.run(
            downloader._parse(
                "https://www.douyin.com/video/7658630307536506162", ""
            )
        )
