# 1. 一次性导入 AI-Video-Transcriber 作为 MVP 底座

- 状态：已接受
- 日期：2026-07-13

## 背景

第一版需要 Web、上传、转写、文本优化、Docker 部署等基础能力。从零自建成本高，
社区已有 `AI-Video-Transcriber`（FastAPI + faster-whisper + OpenAI-compatible + 静态前端）覆盖了这些能力。

## 决策

一次性导入 `AI-Video-Transcriber` 作为底座，不以持续同步上游更新为目标。导入后以本项目
「短视频文案工作台」需求为主二开：上游散落的 env 读取收敛进 `app/config.py`；上游文件化
`tasks.json` 任务存储替换为 SQLite + SQLAlchemy；上游 `backend/` 拆分为
`app/{api,services,models,...}`；上游 `static/` 前端保留作提交页，其余页面用 Jinja2 新建。

## 后果

- 快速获得可用底座与前端交互经验。
- 放弃上游后续更新，接受一次性分叉的维护成本。
- 上游非核心功能（多平台、翻译、摘要）在产品入口上弱化，代码可保留。
