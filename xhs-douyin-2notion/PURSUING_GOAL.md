# Pursuing Goal

始终以“个人内容知识治理而非通用爬虫”为边界，以活跃本地 SQLite Canonical Store 为逻辑真相源，以 Chrome 为交互面、Local Companion 为执行面；任何实现都不得持久化平台媒体 CDN URL、凭据或原始媒体，不得让 AI 擅自创建一级分类，也不得以牺牲幂等、证据、恢复能力和公开仓库隐私边界换取功能速度。

在 `LinzeColin/MetaDatabase` 的 `xhs-douyin-2notion/` 中严格按照 v0.0.0.1 Task DAG Stage 0–6 推进。每个普通 Run 最多执行一个 DAG Task 及其 Acceptance；Stage Review 是不执行新 Task 的专用 Run。Stage 完成后必须先完成全阶段 Review、修复与重验，才可上传整个 Stage。

目标产品是账号安全与 Chrome Web Store 合规优先的 Chrome Side Panel＋本地 UI Skill：仅处理用户明确选择的小红书、抖音、哔哩哔哩、快手、微博和淘宝当前内容或个人列表批次；不自动滚动、不改变账号状态。`X2N_DATA_ROOT` 只作下载、执行和活跃 SQLite working copy；耐久资产只经 `KMOS/KMDatabase/machine/tools/private_db_client.py` 的 `ingest/get/list/verify` 写入 `LinzeColin/Private-Database` 的 `Private-MetaDatabase` area，以 manifest `domain=xhs-douyin-2notion` 归属，禁止 clone。SQLite 不直接以 `.sqlite/.db` 上传，而以一致性非运行时归档、≤90 MiB 内容寻址分片和 restore manifest 持久化。在 Public Code / Private Runtime 的前提下，生成可恢复、可分类、包含 ASR、OCR、关键帧证据的 Markdown 与 Notion 知识资产。每个平台独立 Capability/Policy/Auth Gate，任何安全、政策、证据、验收或回滚门禁未知时一律 Fail Closed。

发布目标是唯一 `v0.0.0.1` MVP：不设置预发布阶段、固定健康观察或 soak；`G0–G5`、前四个 Assurance/UXOps005 与最终任务精确自有 Acceptance 集合之外的 Blocking Acceptance 通过后启动 `assurance.005`，再在该任务内完成 80 条 XHS/Douyin Owner MVP 基线、每个额外实际启用能力各自不超过 20 条的独立激活、安全门必须通过、模型能力通过或明确关闭/降级为仅建议模式、回滚、签字、部署、运行和在线 smoke，成功后才签发 `G6 PASS`。合法外部门能力可关闭结算，技术阻断不可结算；安全未知或失败不得以降级结算；任务内 Oracle 不得反向成为启动前置；上线后监控不阻断正常开发，只触发修复、降级或回滚。
