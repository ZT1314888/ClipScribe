# 抖音下载链路 —— 部署与联调说明

本文档说明如何启用真实抖音下载（解析单条公开视频 → 下载无水印视频 → 走转写/清洗/拆解/改写链路），以及能力边界与真机联调 checklist。

对应：补充计划第 2、3 节，`docs/adr/0002-use-evil0ctal-douyin-crawler-architecture.md`。

## 1. 架构

- 解析与签名（`a_bogus` 等）委托给开源库 **`douyin-tiktok-scraper`**（Evil0ctal），随 `uv sync` 安装。
- 本项目只在 `app/services/downloader.py` 做「适配 + 落盘 + 错误映射」，把库输出收敛为稳定的 `DownloadResult`。日后换库（如 `f2`）只改这一个文件，`pipeline` / API / 状态机不动。
- 下载的视频落到 `data/media/<task_id>/video.mp4`，与本地上传兜底同一约定，受 7 天保留策略清理。

## 2. 三个开关

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `MOCK_DOUYIN` | `true` 时不联网，生成 1 秒占位视频，仅验收链路连通性 | `true` |
| `DOUYIN_COOKIE` | 抖音 Cookie，提升公开视频解析成功率 | 空 |
| `DOUYIN_DOWNLOAD_TIMEOUT` | 解析+下载整体超时（秒） | `120` |

> **启用真实下载：把 `MOCK_DOUYIN` 设为 `false`，并配置 `DOUYIN_COOKIE`。**

## 3. Cookie 策略（重要）

- Cookie **只经环境变量注入**，绝不在 Web 页面填写、不写入数据库、不内置进 Docker 镜像。
- 部署时通过 `.env` 或容器环境变量传入 `DOUYIN_COOKIE`；`.env` 不提交 Git。

### 如何获取 Cookie

1. 浏览器登录 <https://www.douyin.com/>。
2. 打开开发者工具（F12）→ Network，刷新页面。
3. 任选一个 `www.douyin.com` 的请求，复制 Request Headers 里的整条 `Cookie` 值。
4. 填入 `.env`：`DOUYIN_COOKIE=<粘贴整条 cookie>`（不要带 `Cookie:` 前缀）。

Cookie 会过期，解析持续失败时优先换新 Cookie。

## 4. 能力边界

第一版**只支持**当前部署环境可访问、且 Cookie 有效的**单条公开视频链接**。

以下输入会被映射为清晰的失败信息，任务进入 `failed`，请改用本地上传兜底：

- 私密 / 已删除 / 当前 Cookie 无权限的视频
- 被平台风控、验证码或地区策略阻断的视频
- 图集 / 图文（非单条视频）
- 主页、合集、搜索页、批量链接

## 5. 真机联调 checklist（需真 Cookie + 外网）

> 当前开发环境无 Cookie、且抖音接口对签名/风控敏感，无法在 CI/离线环境端到端验证。以下步骤请在有 Cookie 的环境执行。

1. `.env` 配置：
   ```
   MOCK_DOUYIN=false
   DOUYIN_COOKIE=<有效 cookie>
   # 若要真实转写/改写，另配 MOCK_TRANSCRIBE=false / MOCK_LLM=false 与相应模型/Key
   ```
2. `uv sync` 确认 `douyin-tiktok-scraper`、`httpx` 已安装；`ffmpeg -version` 确认 ffmpeg 可用。
3. 启动：`uv run python main.py`，登录后在提交页粘贴一条**公开视频**分享链接（形如 `https://v.douyin.com/xxxx/` 或 `https://www.douyin.com/video/xxxx`）。
4. 任务列表应依次经过 `downloading → extracting_audio → transcribing → …`；详情页能看到标题、作者、转写稿。
5. 验证失败兜底：故意提交一条私密/失效链接，任务应转 `failed` 且错误信息提示改用本地上传；再用本地上传同一素材，应能跑通全链路。
6. 验证按步重试：从 `failed` 步骤点重试，应从该步继续。

## 6. 相关代码

- `app/services/downloader.py` — 适配层（`download(url, task_id)` / `_parse` / `_extract_meta` / `_stream_to_file`）。
- `app/services/pipeline.py::_step_download` — 调用方（UPLOAD 跳过，LINK 下载并写 `RAW_VIDEO`）。
- `tests/test_downloader.py`、`tests/test_pipeline_download.py` — mock 网络的单元测试（无需外网即可跑）。
