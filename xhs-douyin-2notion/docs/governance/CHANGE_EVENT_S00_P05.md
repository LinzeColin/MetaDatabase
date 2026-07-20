# Change Event — CE-X2N-20260719-S00-P05

> 执行粒度条款已被 `CE-X2N-20260720-S00-REVIEW` 取代：平台/Task 数量变更不再授权“一 Run 一个 Phase”。

## Owner 指令

唯一母仓库为 `LinzeColin/MetaDatabase`，唯一子项目为 `xhs-douyin-2notion/`；所有下载位于 Owner 指定的 `MediaCrawler` 下载目的地。产品终态必须支持小红书、抖音、哔哩哔哩、快手、微博和淘宝，并补充对 `ShilongLee/Crawler` 的充分竞品研究；可借鉴思想必须 clean-room 重建。

## 变更解释

- Owner 短名 `xhs-douyin-2notion` 取代原始输入包沿用的长名；项目代号 `x2n` 与 `REQ/TSK/ACC` ID 不变。短名是产品名，不表示平台范围上限。
- 产品边界仍是“个人内容知识治理”，不是通用爬虫。文档中的“在线采集”仅指用户明确选择的当前内容或用户明确选择的个人列表批次，且必须通过当时有效的平台政策、授权、能力和账号安全门禁。
- 六平台都进入 Stage 2 当前页闭环和 Stage 3 用户选择的个人关系/列表适配；每个平台独立 Feature Flag、独立 Kill Switch、独立政策状态，不允许以一平台 PASS 推断其他平台。
- `ShilongLee/Crawler` 与 MediaCrawler 的受限许可证/通用爬虫边界阻止直接复制、合并、Vendor、安装、运行或作为文件输入/运行时依赖；仅保留不可执行的架构思想摘要与审计证据。本变更取代旧设计中“未来研究 Adapter”的产品授权含义，但不篡改 Phase 0.2 历史审计证据。
- 原始 roadmap/taskpack 未给任何 macOS 下载绝对路径；不得把后来推导的路径伪装成原始事实。Owner 指定目的地以 `X2N_DOWNLOAD_DESTINATION` 表示，`X2N_DATA_ROOT` 解析为其下 `xhs-douyin-2notion/` 隔离命名空间。目的地已有同级条目只做不回显名称的聚合数量/元数据指纹审计，不读取内容、不导入、不移动、不链接、不修改、不删除。下载父目录与上游项目同名仅是存储路由，不授权安装、运行或接入 `NanmiCoder/MediaCrawler`。

## DAG 影响

- Requirements：`28 → 32`；新增六平台范围、能力协商、合规采集与隔离下载要求。
- Tasks：`35 → 43`；Stage 2 与 Stage 3 各由 5 个 Task 扩为 9 个 Task，仍然每 Run 一个 Phase。
- Acceptance：`49 → 61`；新增 4 个当前页 Acceptance 与 8 个新平台关系/列表 Acceptance。
- 工时包络：作为范围变更重新估算；不是 Acceptance，也不能代替真实 Phase 校准。

## 兼容性与回滚

原 `REQ/TSK/ACC` ID 不重编号；新增 ID 只追加。回滚本 Change Event 不触及 Runtime 或真实数据，但会与 Owner 六平台终态要求冲突，因此只能由新的 Owner Change Event 取代。

## 2026-07-20 Owner 并行隔离补充

Owner 要求 x2n 与 MetaDatabase 内长期外部开发互不污染并继续并行。默认 clean-main 门禁不删除；新增显式 `--allow-external-main-dirty` 模式，仅在外部主树 dirty paths 与 x2n 项目路径零重叠、当前 worktree 零越界、主树仍在 `main` 时 PASS。该模式不授权修改、恢复、暂存或提交外部文件，Evidence 只保留计数，不保留外部路径或内容。详细契约见 `docs/governance/PARALLEL_WORKTREE_ISOLATION.md`。
