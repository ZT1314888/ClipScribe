# 短视频文案系统（MVP）

团队内部工具：把抖音单条公开视频链接（或本地上传的音视频）转成转写稿、清洗稿、结构拆解与改写版本，仅作**内部创作参考**。

方案文档见 `docs/`（含补充计划与 `docs/adr/`）。领域术语见 [CONTEXT.md](./CONTEXT.md)。工程与协作规范见 **[AGENTS.md](./AGENTS.md)**。

> 第一版跑通 `抖音链接/上传音视频 → 抽音频 → 转写 → 清洗 → 结构拆解 → 改写 → 导出` 全流程。抖音下载解析委托开源库 `douyin-tiktok-scraper`，适配层在 `app/services/downloader.py`；真实下载需配置 Cookie，详见 [docs/douyin-download.md](./docs/douyin-download.md)。无 Cookie/离线时用本地上传兜底。

## 环境准备

本项目用 [uv](https://docs.astral.sh/uv/) 管理 Python。**不要用 pip / venv。** 另需系统安装 **ffmpeg**（抽音频用）。

```bash
uv sync                 # 同步依赖（含 dev 工具）
cp .env.example .env    # 按需修改：口令、LLM、mock 开关等
uv run python main.py   # 启动服务，默认 http://localhost:8000
```

默认 `MOCK_LLM=true` / `MOCK_TRANSCRIBE=true` / `MOCK_DOUYIN=true`，无 GPU / 无 API Key / 无 Cookie 也能端到端跑通（产出占位内容）。

## 使用

1. 浏览器打开 `http://localhost:8000`，用 `.env` 中的 `SHARED_PASSPHRASE` 登录。
2. 提交页：粘贴抖音单条公开视频链接（需配 Cookie），或上传本地视频/音频兜底。
3. 任务列表页：时间倒序查看，按标题/链接/状态搜索。
4. 任务详情页：编辑转写稿（下游优先用修订稿）、查看清洗/拆解/三类改写、按步重试、导出 Markdown/Docx、一键复制、对改写结果反馈。
5. 统计页：任务总数、成功率、平均耗时、反馈好评率。

## 接入真实转写 / LLM

编辑 `.env`：

```bash
MOCK_TRANSCRIBE=false           # 用 faster-whisper（默认 small，首次会下模型到 data/models）
MOCK_LLM=false
LLM_API_KEY=sk-...              # OpenAI-compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

## 接入真实抖音下载

```bash
MOCK_DOUYIN=false               # 关掉占位视频，走真实解析+下载
DOUYIN_COOKIE=<有效 cookie>      # 环境注入，不在 UI 填、不进镜像
```

能力边界（仅单条公开视频）、Cookie 获取方式与真机联调 checklist 见 [docs/douyin-download.md](./docs/douyin-download.md)。

## Docker 部署（单容器单 worker，ADR-0003）

```bash
cp .env.example .env            # 生产建议设强口令与 SESSION_SECRET
docker compose up -d --build
```

`data/` 挂载到宿主，持久化 SQLite、媒体、中间产物、导出与模型缓存。抖音 Cookie 通过 `.env` 的 `DOUYIN_COOKIE` 注入，**不在 UI 填、不进镜像**。

## 启用 git 提交检查（每个克隆执行一次）

```bash
git config core.hooksPath .githooks
```

启用后 `git commit` 会对暂存的 `.py` 自动跑质量检查（black / isort / flake8）；critical 错误会阻断提交。同一套逻辑在 `scripts/checks/`，Claude Code 与 Codex 共用。

手动检查：

```bash
uv run python scripts/checks/core_quality.py path/to/file.py
```

## 目录

```
app/              应用代码
  config.py       ★集中读环境变量（唯一处）
  main.py         FastAPI 装配 + lifespan（建表/自愈/清理/启动 worker）
  api/            路由：auth / tasks / feedback / stats / pages(Jinja2)
  services/       pipeline / downloader(桩) / audio / transcriber / llm / text_pipeline / exporter / retention
  worker/         单 worker 串行执行器
  models/         Task / Artifact / Feedback（SQLite）
  core/           security / middleware / paths / timeutil / lifecycle
templates/        Jinja2 页面
static/           上游前端（提交页可复用）
scripts/checks/   共享检查核心（工具无关，单一事实源）
docs/             方案、补充计划、ADR
data/             运行期数据（不提交 Git）
```
