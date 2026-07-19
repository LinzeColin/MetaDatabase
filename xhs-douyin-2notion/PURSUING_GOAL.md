# Pursuing Goal

始终以“个人内容知识治理而非通用爬虫”为边界，以本地 SQLite Canonical Store 为真相源，以 Chrome 为交互面、Local Companion 为执行面；任何实现都不得持久化平台媒体 CDN URL、凭据或原始媒体，不得让 AI 擅自创建一级分类，也不得以牺牲幂等、证据、恢复能力和公开仓库隐私边界换取功能速度。

在 `LinzeColin/MetaDatabase` 的 `xhs-douyin-2notion/` 中严格按照 v0.0.0.1 Task DAG Stage 0–6 推进。每个普通 Run 最多执行一个 DAG Task 及其 Acceptance；Stage Review 是不执行新 Task 的专用 Run。Stage 完成后必须先完成全阶段 Review、修复与重验，才可上传整个 Stage。

目标产品是账号安全与 Chrome Web Store 合规优先的 Chrome Side Panel＋本地 UI Skill：仅处理用户明确选择的小红书、抖音、哔哩哔哩、快手、微博和淘宝当前内容或个人列表批次；不自动滚动、不改变账号状态；Runtime 与所有下载均进入同一私有数据根；在 Public Code / Private Runtime 的前提下，生成可恢复、可分类、包含 ASR、OCR、关键帧证据的 Markdown 与 Notion 知识资产。每个平台独立 Capability/Policy/Auth Gate，任何安全、政策、证据、验收或回滚门禁未知时一律 Fail Closed。
