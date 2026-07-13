# AGENTS.md —— 开发与协作规范（Claude Code / Codex / CI 共用）

本文件是本仓库工程约定的**规范源**。Codex CLI 直接读取本文件；Claude Code 通过 `CLAUDE.md` 指向本文件。请所有自动化代理与人类开发者遵循以下约定。

## 项目概述

「短视频文案系统」MVP：团队内部工具，把抖音单条公开视频链接（或本地上传的音视频）转成转写稿、清洗稿、结构拆解与改写版本，仅作**内部创作参考**。

技术边界（详见 `docs/短视频文案系统_MVP方案_内部版.md` 与补充计划）：

- 后端：FastAPI
- 数据库：**SQLite**（不用 Postgres）
- 转写：faster-whisper
- 存储：本地目录（不用 MinIO/S3）
- 部署：Docker Compose 单容器、单 worker 串行任务
- **明确砍掉**：Redis、Celery 队列、多租户权限、S3、账号主页批量采集

新增代码若要把上述砍掉的复杂度加回来，请先更新方案文档与 ADR，再改代码。

## Python 环境：统一使用 uv

本仓库用 [uv](https://docs.astral.sh/uv/) 管理 Python 环境与依赖。**禁止裸用 `pip` / `python -m venv`。**

- Python：本地 3.13（`.python-version`），`pyproject.toml` 要求 `>=3.11`（whisper 生态兼容更稳）。
- 同步环境：`uv sync`
- 加依赖：`uv add <pkg>`；加开发依赖：`uv add --dev <pkg>`
- 运行命令：`uv run <cmd>`（自动使用项目 `.venv`，跨平台，无需手动 activate）
- 运行入口：`uv run python main.py`

开发依赖（dev group）：`black`、`isort`、`flake8`、`pytest`、`pytest-cov`。

## 代码质量检查

检查逻辑集中在 `scripts/checks/`，是所有工具共用的**单一事实源**：

- `scripts/checks/core_quality.py` —— black 格式化、isort 排序、flake8 critical 检查
- `scripts/checks/core_duplication.py` —— AST 重复检测 + 本 MVP 架构规则

三条触发路径调用的是同一份逻辑：

1. **Claude Code**：`.claude/hooks/` 下的 post-write / pre-write 适配器（写文件时自动跑）。
2. **git 提交**：`.githooks/pre-commit`（需执行一次 `git config core.hooksPath .githooks` 启用）。
3. **命令行 / Codex / CI**：直接跑
   ```bash
   uv run python scripts/checks/core_quality.py <file1.py> [file2.py ...]
   ```

**提交前建议**：对改动的 `.py` 手动跑一遍 `core_quality.py`，或依赖已启用的 pre-commit hook。critical flake8 错误（E9,F63,F7,F82）会阻断提交。

## 架构规则（由 core_duplication.py 校验，早期为 warning）

- 不引入 `redis` / `celery`（MVP 单容器单 worker）。
- 用 SQLite，不用 Postgres 异步引擎。
- 环境变量集中在 `config` / `settings` 模块读取，不散落各处。

> 底座 `AI-Video-Transcriber` 尚未导入，实际源码目录（`app/` 等）未定。重复检测对不存在的目录静默跳过；与具体路径强绑定的规则待导入底座后再细化。

## 目录约定

```
scripts/checks/     共享检查核心（工具无关）
.claude/            Claude Code 集成（hooks 为薄适配器，逻辑在 scripts/checks/）
.githooks/          git hooks（pre-commit 调共享核心）
docs/               方案与补充计划、后续 ADR
data/               运行期数据（SQLite/媒体/中间产物），不提交 Git
```
