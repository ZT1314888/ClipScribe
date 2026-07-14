# douyin_vendor —— 上游来源与同步说明

本目录是 **vendored 第三方代码**，非本仓编写。请勿套用本项目的编码规范去
「清理 / 重构」它——改动越少，跟随上游越省事。项目门禁（black/isort/flake8、
重复检测、架构规则）已在 `scripts/checks/` 中对 `/douyin_vendor/` 路径豁免。

## 来源

- 项目：`jiji262/douyin-downloader`
- 许可：MIT（Copyright (c) 2026 jiji262）
- 同步时上游 commit：`e224c81b9f0a1f8ce88c15818cb8b0fc295d2bdc`
- 同步日期：2026-07-14

## 抽取了哪些文件（单条视频解析所需的最小集）

| 本目录文件 | 上游路径 |
|---|---|
| `api_client.py` | `core/api_client.py` |
| `url_parser.py` | `core/url_parser.py` |
| `abogus.py` | `utils/abogus.py` |
| `xbogus.py` | `utils/xbogus.py` |
| `cookie_utils.py` | `utils/cookie_utils.py` |
| `validators.py` | `utils/validators.py` |
| `logger.py` | `utils/logger.py` |
| `ms_token_manager.py` | `auth/ms_token_manager.py` |

未抽取上游的 storage / transcript / downloader_factory / Playwright 兜底等，
本项目单条视频解析用不到（Playwright 主页批量兜底也不在本 MVP 范围内）。

## 相对本仓做的唯一改动：内部 import 改为相对导入

为了让这几个文件脱离上游包结构独立运行，仅把跨模块 import 改成包内相对导入，
**逻辑零改动**：

- `api_client.py`：`from auth import MsTokenManager` → `from .ms_token_manager import MsTokenManager`；
  `from utils.xxx` / `from utils.abogus` → `from .xxx` / `from .abogus`
- `url_parser.py`：`from utils.logger|validators` → `from .logger|.validators`
- `ms_token_manager.py`：`from utils.logger` → `from .logger`

`ms_token_manager` 的联网取真实 msToken 逻辑保持原样；本项目在适配层
（`app/services/downloader.py`）预先注入一个占位 msToken，使
`ensure_ms_token` 直接命中已有值、不发外部请求（离线/国内网络更稳）。

## 如何同步上游

抖音改签名时，通常只需同步 `abogus.py`（必要时连带 `api_client.py` 的
`_default_query` 参数）。同步步骤：

1. `git clone --depth 1 https://github.com/jiji262/douyin-downloader` 到临时目录。
2. 覆盖对应文件，重做上面「相对导入」那几处改动。
3. 更新本文件的上游 commit 与日期。
4. 跑 `uv run pytest tests/test_downloader.py`，并用真实 cookie 做一次端到端。
