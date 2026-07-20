# Architecture Decisions — Stage 0 / Phase 0.5

状态词：`ACCEPTED_DESIGN` 仅表示 Pre-Stage 00 设计确定，不表示实现或下游 Acceptance 已运行。

## ADR-001 — 个人知识治理边界

- 状态：`ACCEPTED_DESIGN`
- 决策：产品处理 Owner 明确选择的当前内容或明确选择的个人列表批次。所谓在线采集不是通用爬虫；全网搜索、评论网络、用户画像、无人值守扫描均不在 v0.0.0.1。
- 后果：每个动作都带 user-gesture/batch-scope Receipt；越界请求 Fail Closed。

## ADR-002 — SQLite Canonical Store 是唯一真相源

- 状态：`ACCEPTED_DESIGN`
- 决策：Observation、Content、Relation、Run、Checkpoint、Artifact、Outbox 与 Receipt 先进入本地 SQLite；Markdown/Notion 都是可删除重建的 Sink。
- 后果：平台 Adapter、模型和 Sink 无权互相直写；唯一键、事务、Migration/Backup/Rollback 是阻断门禁。

## ADR-003 — Chrome MV3 Side Panel＋Native Messaging＋Local Companion

- 状态：`ACCEPTED_DESIGN`
- 决策：Side Panel 是用户交互面；长期任务只在 Local Companion。Side Panel 打开和采集必须来自用户动作；扩展不加载远程 JS/WASM。Native Host 使用精确 `allowed_origins`，无通配符，消息按 Chrome 限制再收紧。
- 后果：扩展无凭据、无长任务、无任意命令/Path/URL；Worker 重启不丢任务。

## ADR-004 — 单一私有数据根与凭据边界

- 状态：`ACCEPTED_DESIGN`
- 决策：原始 taskpack 未指定本机绝对下载路径；Owner 指定 `X2N_DOWNLOAD_DESTINATION`，而 Runtime 和全部下载都位于其下的 `X2N_DATA_ROOT=xhs-douyin-2notion/` 隔离命名空间。每平台独立 `downloads/<platform>/runs` 与 `runtime/browser_profiles/<platform>`。Secret 仅存系统 Keychain 引用；Cookie/浏览器状态不导出。
- 后果：下载目的地已有同级条目只做不回显名称的聚合数量/元数据指纹审计，不读取内容、不导入、不链接、不修改、不删除；Repo/Build/Artifact/Diagnostic 扫描私有内容和绝对路径。

## ADR-005 — 六平台独立策略与 clean-room 来源治理

- 状态：`ACCEPTED_DESIGN`
- 决策：小红书、抖音、哔哩哔哩、快手、微博、淘宝分别有政策登记、Capability Manifest、Feature Flag 和 Kill Switch。官方 API/OAuth 优先；当前页 clean-room fallback 需独立授权。`ShilongLee/Crawler`、MediaCrawler 与未知/受限 License 项目只作不可执行研究参考：不复制、不 Vendor、不安装、不运行、不接收其输出、不作 Runtime Dependency。
- 后果：一平台失败只熔断该平台；未文档化 Cookie/签名/代理/指纹路线保持 `UNKNOWN_DISABLED`。

## ADR-006 — 能力协商而非虚假平台一致性

- 状态：`ACCEPTED_DESIGN`
- 决策：统一能力为 `current_page`、`selected_collection`、`preview`、`ephemeral_download`、`classify`，状态为 `SUPPORTED/BLOCKED_POLICY/BLOCKED_AUTH/BLOCKED_TECHNICAL/UNKNOWN_DISABLED`。
- 后果：UI 必须展示真实状态和替代路径；不存在或未授权的“点赞/收藏”概念不能伪造映射。

## ADR-007 — 用户手势与有界批次

- 状态：`ACCEPTED_DESIGN`
- 决策：永久禁止自动滚动。当前页为一次手势一次内容；列表批次由 Owner 明确选择可见范围/分页动作，具最大条数、Deadline、并发 1、Checkpoint 和取消。
- 后果：达到 CAPTCHA、验证、限流、DOM Drift 或 Scope 边界即停止，绝不模拟鼠标/设备或改变账号状态。

## ADR-008 — 安全预览/下载与媒体 Lease

- 状态：`ACCEPTED_DESIGN`
- 决策：平台媒体 URL 只存在进程内短生命周期对象；安全下载器逐跳校验 HTTPS、平台 Host Allowlist、解析 IP、Redirect、Port、MIME、长度、Timeout 和资源预算。成功立即删除原始媒体，失败最长 24h。
- 后果：拒绝 loopback、RFC1918、link-local、metadata、IPv6 local、DNS rebinding、用户信息 URL、非 HTTP(S) 和任意输出路径；Notion 使用本地处理后的直接文件上传，不写平台 CDN 外链。

## ADR-009 — Owner 拥有一级分类

- 状态：`ACCEPTED_DESIGN`
- 决策：初始只有 `Unclassified`。AI 只能从 Owner 允许的一级分类中选择，可提出候选但不能创建/重命名/删除分类。
- 后果：分类有模型/规则 Provenance、置信阈值和人工复核；模型不可调用采集、文件或配置工具。

## ADR-010 — 证据、恢复与发布门禁

- 状态：`ACCEPTED_DESIGN`
- 决策：每个 Phase 只执行一个 Task/Phase Contract；每个 Stage 完成后独立做全 Stage Review/Fix/Re-acceptance，之后才可 push 整个 Stage。UNKNOWN/NOT_RUN 不等于 PASS。
- 后果：运行必须有 Intent、Checkpoint、Receipt、Error、Rollback 证据；发布必须通过 Secret/CDN/Private、License/SBOM、迁移/恢复、Chaos 与 Owner Alpha 门禁。
