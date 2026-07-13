# CLAUDE.md

工程约定的规范源在 **[AGENTS.md](./AGENTS.md)**，请先阅读该文件（环境用 uv、代码检查、架构边界均在其中）。本文件只补充 Claude Code 特有的说明。

## 关键约定（摘要，详见 AGENTS.md）

- Python 环境统一用 **uv**：`uv sync` / `uv add --dev` / `uv run`，不要裸用 pip。
- 代码检查逻辑集中在 `scripts/checks/`，是所有工具共用的单一事实源。
- MVP 边界：FastAPI + SQLite + 本地存储 + 单容器单 worker，**不引入** Redis/Celery/Postgres/S3。

## Claude Code 集成会自动运行检查

`.claude/hooks/` 下有两个**薄适配器**，Write/Edit `.py` 文件时自动触发，内部调用 `scripts/checks/` 的共享核心：

- `pre-write-intelligent.py` → `core_duplication.py`：重复检测 + 架构规则（高相似度或规则冲突时会请求确认）。
- `post-write.py` → `core_quality.py`：black / isort / flake8（critical 错误会阻断）。

hook 通过 `uv run` 调用，自动使用项目 `.venv`。若 hook 报 "uv not found"，先执行 `uv sync`。

要临时停用 hook：注释掉 `.claude/settings.json` 中对应的 PreToolUse / PostToolUse 配置。
