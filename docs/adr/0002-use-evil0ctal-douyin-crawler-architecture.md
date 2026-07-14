# 2. 抖音下载参考 Evil0ctal 爬虫架构

- 状态：已接受（第一版留桩，接口先行）
- 日期：2026-07-13

## 背景

第一版垂直骨架优先跑通「本地上传兜底」全链路，真实抖音解析下载延后。但需要预留
干净的接口与 Cookie 注入策略，避免后续接入时反向改动调用方。

## 决策

抖音解析下载能力参考高 star 项目 `Evil0ctal/Douyin_TikTok_Download_API` 的架构思路：
`FastAPI + crawlers + config` 的组织方式、通过 Cookie 提升公开视频解析成功率、Docker
下的配置与依赖组织。原方案 `jiji262/douyin-downloader` 降级为后续备选。

第一版 `app/services/downloader.py` 固定 `download(url) -> DownloadResult` 接口并抛
`DownloadNotImplemented`，提示改用本地上传。Cookie 从 `settings.douyin_cookie`（环境注入）
读取，不在 Web 页面填写，镜像不内置个人 Cookie。

## 后果

- 下载阶段只需替换 `downloader.download` 实现，pipeline 与 API 不变。
- Cookie 策略从一开始就正确（环境注入、不入库、不入镜像）。
- 能力边界明确：仅单条公开视频，不含私密/已删/无权限/风控/主页合集批量。

## 修订（2026-07-14）：改用 vendored `jiji262/douyin-downloader` API 层

### 起因

真实链路接入后，实测 `douyin-tiktok-scraper`（Evil0ctal，1.2.9）解析必失败：
它停在旧的 `X-Bogus` 签名，而抖音 `aweme/v1/web/aweme/detail/` 接口现已要求
`a_bogus` 签名。库拿不到 `aweme_detail` 字段 → 内部 `ValueError` → `@retry` 4 次后
抛 `RetryError`（前端表现为「抖音解析失败」）。该库已长期不跟进签名更新。

### 新决策

1. **改用 `jiji262/douyin-downloader`（MIT，2026-07 仍活跃）的 API 层**，因其自带
   一份纯 Python 的 `a_bogus` 实现（`utils/abogus.py`，SM3+RC4+浏览器指纹）。
2. **vendored 而非 pip 安装**：上游是应用不是库，安装会拖入 imageio-ffmpeg / rich /
   aiosqlite 等无关重依赖。只抽取「单条视频解析」所需的 8 个文件到
   `app/services/douyin_vendor/`（来源 commit 与同步方法见该目录 `UPSTREAM.md`），
   第三方依赖收敛为 `aiohttp` + `gmssl`(+`pyyaml`)。
3. **单视频只走纯 HTTP + a_bogus 签名，不引入 Playwright**：上游的浏览器兜底
   （`collect_user_post_ids_via_browser`，有头模式）仅用于主页批量翻页，本项目
   单视频链路不触及。因此**不突破「单容器、不加重」边界**（见 ADR-0003），无需新 ADR。
4. **模块边界不变**：`downloader.download(url, task_id) -> DownloadResult` 对外接口、
   Cookie 环境注入策略、能力边界、mock 开关全部保持。vendored 结构收敛在 `_parse`
   / `_extract_meta`，换实现仍只改 `downloader.py` 与 vendor 目录。
5. **msToken 处理**：适配层预置占位 msToken，避免 vendored 层为补 token 去发外部
   请求（githubusercontent + mssdk）；实测占位 token + a_bogus 即可成功解析。

### 影响

- 依赖从 `douyin-tiktok-scraper` 换为 vendored `douyin_vendor` + `gmssl`。
- vendored 代码不受本仓 lint / 重复 / 架构门禁约束（已在 `scripts/checks/` 排除
  `douyin_vendor/`），需跟随上游同步；抖音改签名时从上游更新 `abogus.py`。
- 仍不承诺绕过所有反爬：cookie 过期需重贴 `.env`；风控/图集/私密仍降级到本地上传。

### 备选方案（本次复核）

- **yt-dlp**：认识抖音链接且社区活跃，但 `--cookies-from-browser` 在新版 Edge 上
  撞 App-Bound Encryption（DPAPI 解密失败），需手动导 `cookies.txt`，交互成本更高。
  保留为后备。
- **调用第三方下载站接口**：受制于对方反爬与可用性，比依赖大社区项目更脆弱，放弃。
- **服务器无头浏览器全自动**：突破 MVP 边界，需另立 ADR，暂不采用。
