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
