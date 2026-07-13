# 3. 第一版采用单容器单 worker

- 状态：已接受
- 日期：2026-07-13

## 背景

内部团队工具，用户量小，本机/单机 Docker 部署。转写与下载是重资源操作，本机并发多个
Whisper/下载任务会打满资源。

## 决策

单 Docker 容器内运行 FastAPI/Web、抖音解析下载、FFmpeg、faster-whisper、LLM 调用与
后台任务。后台任务用进程内单 worker 串行执行（`app/worker/queue.py`：asyncio.Queue +
单消费协程 + 线程池跑阻塞步骤），**不引入 Redis/Celery/Postgres/S3**。

任务状态与中间产物持久化到 SQLite + `data/`。容器重启时运行中任务统一标记失败
（`app/core/lifecycle.py`），由用户手动重试。7 天媒体清理由启动时 + 每次任务结束机会式
触发（`app/services/retention.py`），无独立调度器。

## 后果

- 部署与运维极简，符合内部工具定位。
- 吞吐受限于单 worker 串行；确认有并发需求时，再更新方案与 ADR 后引入队列。
- 无外部依赖（Redis/broker），单文件 SQLite 便于备份与迁移。
