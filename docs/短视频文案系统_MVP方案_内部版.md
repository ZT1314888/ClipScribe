# 短视频文案系统 —— MVP 方案（内部团队使用版）

## 一、技术框架选型

| 层 | 选型 | 说明 | GitHub |
|---|---|---|---|
| 主项目底座 | AI-Video-Transcriber（二开） | Web + 转写 + 文本优化，改造成短视频文案工作台 | https://github.com/wendy7756/AI-Video-Transcriber |
| 抖音采集 | douyin-downloader | 单条链接解析 + 下载，主页/合集批量采集放后续版本 | https://github.com/jiji262/douyin-downloader |
| 语音转写 | faster-whisper | 中文场景可后续对比 FunASR，先用 Whisper 起步 | https://github.com/SYSTRAN/faster-whisper |
| 后端框架 | FastAPI | 轻量、Python 生态适配 AI 工具链 | https://github.com/fastapi/fastapi |
| 数据库 | SQLite | 内部团队用户量小，单文件数据库足够，无需一开始上 PostgreSQL | — |
| 文件存储 | 本地目录 | 无需 MinIO | — |
| 内容处理 | OpenAI-compatible LLM | 清洗、分析、改写 | — |
| 部署 | Docker Compose 单机部署 | 内部使用，不需要多环境/多副本 | — |

**因为是内部团队使用，砍掉的复杂度**：不需要 Redis/Celery 队列、不需要多租户权限系统、不需要 MinIO、不需要账号主页批量采集——这些留到确认真的有需求再加。

---

## 二、第一版 MVP 效果

只做通一条主链路，验证"能不能省时间、文案能不能直接用"：

```
团队成员粘贴抖音链接
  → 系统下载视频并转成音频
  → faster-whisper 转写成文字
  → 清洗润色（去口水词、加标点、分段）
  → 生成 2-3 个改写版本（如：口播版 / 种草笔记版）
  → 支持人工反馈后重新生成一版
  → 导出为 Markdown / Word
  → 历史任务可查看
```

不做：批量采集、复杂字幕编辑器、多用户权限体系、导出剪映格式。

---

## 三、成功指标

因为是内部工具，指标应该围绕"团队是否真的愿意用、比现在的方式快多少"来定：

| 指标类型 | 具体指标 | 参考目标 |
|---|---|---|
| 效率 | 从粘贴链接到拿到可用文案的耗时 | < 5 分钟 |
| 质量 | 生成文案不经过大改可直接用的比例（人工评估） | > 50%（第一版可放低标准） |
| 使用率 | 团队成员每周实际发起的任务数 | 有持续使用，而不是试一次就不用了 |
| 稳定性 | 任务从提交到完成的成功率（不因下载/转写报错中断） | > 90% |

建议每 2 周回顾一次这几个指标，用来判断是"继续往下做"还是"先修体验问题"。

---

## 四、建议补充的内容

即使是内部工具，以下几点仍建议在第一版里带上，成本很低但能避免后续麻烦：

1. **最基础的访问控制**：哪怕不做复杂权限系统，也建议加一个团队共享的登录口令或邀请链接，避免服务如果部署在可公网访问的机器上被外部访问到。
2. **媒体文件自动清理**：视频/音频文件会很快占满磁盘，建议定一条简单规则，比如"导出完成 7 天后自动清理原始视频音频,只保留文本"。
3. **一个轻量反馈入口**：在每个改写结果旁边加一个"好用 / 不好用"的简单反馈按钮，这是后续判断"质量指标"是否达标的唯一数据来源，不加的话两周后你会发现没有任何数据支撑迭代方向。
4. **明确"仅供内部参考"的使用规范**：抓取他人抖音内容做改写，即使只是内部使用，也建议明确一句话——生成内容仅作内部创作参考，不直接对外发布原内容的改写版本，避免团队成员误以为可以直接照搬发布。
5. **AI 输出需要人工过一遍的提醒**：转写和改写质量在第一版会有波动，建议在界面上提示"发布前请人工确认"，尤其是涉及广告用词（"最""第一"这类极限词）的场景。

---

## 五、相关开源项目链接

**第一版直接使用：**

| 项目 | 用途 | GitHub |
|---|---|---|
| AI-Video-Transcriber | 主项目底座 | https://github.com/wendy7756/AI-Video-Transcriber |
| douyin-downloader | 抖音链接解析与下载 | https://github.com/jiji262/douyin-downloader |
| faster-whisper | 语音转写 | https://github.com/SYSTRAN/faster-whisper |
| FastAPI | 后端框架 | https://github.com/fastapi/fastapi |

**后续可参考（非第一版必需）：**

| 项目 | 用途 | GitHub |
|---|---|---|
| Fast-Powerful-Whisper-AI-Services-API | 异步任务队列、ASR 服务封装、抖音爬虫模块的架构参考 | https://github.com/Evil0ctal/Fast-Powerful-Whisper-AI-Services-API |
| FunASR | 中文场景 ASR 备选方案，如果后续觉得 Whisper 中文识别不够准，可以对比测试 | https://github.com/modelscope/FunASR |
