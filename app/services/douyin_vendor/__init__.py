"""douyin-downloader API 层的 vendored 子集（仅单条视频解析所需）。

来源：https://github.com/jiji262/douyin-downloader （MIT，见 UPSTREAM.md）。

为什么 vendored 而非 pip 安装：上游是应用而非库，直接安装会拖入
imageio-ffmpeg / rich / aiosqlite 等与本 MVP 无关的重依赖，并触发上游
`core/__init__` 的重 import 链。这里只抽取「单条公开视频解析」真正需要的
8 个文件，第三方依赖收敛为 aiohttp + gmssl(+pyyaml)。

本包只做「原样抽取 + 相对导入修正」，逻辑不改，以便跟随上游同步。业务适配
（cookie 注入、错误映射、落盘）在上层 `app/services/downloader.py`，不在此处。

对外只暴露单视频解析需要的两个符号。
"""

from .api_client import DouyinAPIClient, LoginRequiredError
from .cookie_utils import parse_cookie_header
from .url_parser import URLParser

__all__ = [
    "DouyinAPIClient",
    "LoginRequiredError",
    "URLParser",
    "parse_cookie_header",
]
