# Changelog

## v0.0.0.1 — Stage 2 / Skeleton 008

- 复核微博一手 API/CLI/协议：`statuses/show` 需要 OAuth 且只查询授权用户本人发布内容；应用/user/IP 有频率控制，额外容量可能涉及付费，但本应用价格、Scope、配额与付费层均未批准。
- 实现微博独立 CI-synthetic 当前页 detector/extractor：精确 `www.weibo.com`、合成 `/detail/<mid>`、location/canonical/OG/detail `data-mid` 交叉校验、净化标题/null、五类既有 ContentType 与 provenance；不读取 media `src`、raw DOM、Cookie 或浏览器状态。
- 新增 8 个 DOM Fixture（4 ready、4 platform-changed）、12 个 Policy Fixture、2 个真实形态预算拒绝、16 个任意 URL/Redirect-SSRF 拒绝及 7 个 schema-drift 拒绝；公开详情/用户状态路由只登记为未验证合成或预算拒绝假设。
- 预算默认 0；真实页、生产 API/CLI、OAuth/凭据输入、DOM fallback、任意 URL preview/proxy/redirect transport 与 Owner Canary 全部关闭或未运行。官方 CLI 只登记，未安装、未登录、未执行。
- 复用 4 权限、0 Host Permission 的 Side Panel/`activeTab`/ISOLATED world/Native v1/SQLite 链路；五平台真实按钮合成采集、Action 前各 2 个拒绝、各 100 次 Service Worker 重启均通过，平台调用、丢单、重单、错状态为 0。
- Skeleton007 历史 Task/State/Policy/Evidence 固定到 `17f1988b…`，旧验收只读取历史 blob；当前树继续 XHS/Douyin/Bilibili/Kuaishou 安全与行为回归，历史 Evidence 不重写。
- 根回归 140 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，59-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.capture.005` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.009`。

## v0.0.0.1 — Stage 2 / Skeleton 007

- 复核快手一手 Open Platform/协议：OAuth 需应用登记、动态用户同意与最小 Scope；`user_video_info` 只证明授权用户已发布作品列表和 `photoId` 详情，不证明任意公开当前页、点赞/收藏读取或自动化 DOM 采集权限。
- 实现快手独立 CI-synthetic 当前页 detector/extractor：精确 `www.kuaishou.com`、合成 `/short-video/<id>`、location/canonical/OG/detail `photoId` 交叉校验、净化标题/null、`video/unknown` 与 provenance；不读取 media `src`、raw DOM、hydration、Cookie 或浏览器状态。
- 新增 8 个 DOM Fixture（4 ready、4 platform-changed）、10 个 Policy Fixture、2 个真实形态 `BLOCKED_AUTH` 与 5 个 schema-drift 拒绝；公开短视频路由只登记为未验证的合成假设。
- 真实页保持 `BLOCKED_AUTH`，生产 API transport、Access Token/Cookie/Profile 输入、DOM fallback 与 Owner Canary 全部关闭或未运行；无真实账号、OAuth、平台请求或自动滚动/分页。
- 复用 4 权限、0 Host Permission 的 Side Panel/`activeTab`/ISOLATED world/Native v1/SQLite 链路；四平台真实按钮合成采集、Action 前各 2 个拒绝、各 100 次 Service Worker 重启均通过，平台调用、丢单、重单、错状态为 0。
- Skeleton006 历史 Task/State/Policy/Evidence 固定到 `a314a1d…`，旧验收只读取历史 blob；当前树继续 XHS/Douyin/Bilibili 安全与行为回归，历史 Evidence 不重写。
- 根回归 131 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，58-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.capture.004` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.008`。

## v0.0.0.1 — Stage 2 / Skeleton 006

- 复核 Bilibili 一手 Open Platform/协议：官方能力要求应用入驻、OAuth、具体 Scope 与关联 UP 主授权，只证明授权稿件管理，不证明任意当前页、点赞或收藏读取；真实页面/API 和 Owner Canary 保持 `UNKNOWN_DISABLED / NOT_RUN`。
- 实现 Bilibili 独立 CI-synthetic 当前页 detector/extractor：视频与文章稳定 ID、规范 Host/Path、净化标题/null、`video/text/image_gallery/mixed/unknown` 与 provenance；不读取 media `src`、hydration、raw DOM、Cookie 或浏览器状态。
- 新增 10 个 DOM Fixture（5 ready、5 platform-changed）、8 个 Policy Fixture 与 5 个 schema-drift 拒绝；文章 `/read/cv…` 明确登记为未验证现实路由，只是合成 Oracle。
- 对 `?p=<n>` 分 P 语义 Fail Closed；当前 v1 Canonical Contract 不保存 Query，禁止把所选分 P 错折叠成顶层视频。
- 复用 4 权限、0 Host Permission 的 Side Panel/`activeTab`/ISOLATED world/Native v1/SQLite 链路；真实按钮采集、Action 前 2 个拒绝、100 次 Service Worker 重启均通过，平台调用、丢单、重单、错状态为 0。
- Skeleton002 历史 Task/State/Policy/Evidence 固定到 `2a91efbc…`，旧验收只读取历史 blob，同时保留当前 XHS/Douyin 行为回归；历史 Evidence 不重写。
- 根回归 122 tests PASS、3 个显式可选 Owner-private input skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，57-member source candidate 无 Runtime Data 且可确定性重建。
- `ACC.x2n.capture.003` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`、Stage 2 上传禁止，下一独立 Run 为 `TSK.x2n.skeleton.007`。

## v0.0.0.1 — Stage 2 / Skeleton 002

- 实现抖音当前详情页 clean-room 合成检测/提取：稳定字符串 ID、无 Query/Fragment 的 canonical 重建、净化标题/null、视频/图集/unknown 类型与 provenance；身份冲突、feed card、多详情根和非合成短链身份均 `X2N_PLATFORM_CHANGED`。
- 新增 8 个公共安全 DOM Fixture（4 ready、4 platform-changed）与 16 个短链安全用例（3 resolved、13 blocked）；覆盖五类 Redirect status、相对跳转、精确请求 URL、非允许 Host/Path、IP、lookalike、userinfo、port、loop、limit、额外响应字段、非 Redirect status 与 transport failure。
- 短链实现严格是 network-free、transport-injected 的 CI synthetic core；Extension/Service Worker/Companion 均无生产 requester，真实短链和真实页面保持 `UNKNOWN_DISABLED`，没有新增 Host Permission、Native Action 或 v1.0 Contract 字段。
- Service Worker 在注入前后复核 focused active tab 与完整 URL，阻止导航竞态；Side Panel 增加 stale refresh generation 与 in-flight guard，不再把迟到成功误报为“未执行”或允许重复提交。
- XHS/Douyin 两条 Playwright 链路均通过真实 Side Panel 按钮进入 Native Host/SQLite；所有平台形态请求被 catch-all route 拦截，实测平台调用 0；各 100 次 Worker restart 均 0 丢单/重单/错状态。
- Skeleton001 历史 Task/State/Policy/Evidence 固定到 `894553c6…`，当前树只做追加式 XHS 行为回归；历史 acceptance receipt 保持逐字节不变。
- 根回归 112 tests PASS、3 个显式可选私有输入 skip；两轮 full lane 24/24 Blocking Gate PASS，0 failure/flaky/silent skip，overall combined coverage 70.95%，33 dependencies 的 OSV vulnerability 0，56-member source candidate 无 Runtime Data。
- `ACC.x2n.capture.002` 与 `ACC.x2n.ext.001` 仅 CI-SYNTH scoped pass；Owner Canary、真实账号/平台、生产网络、G2 与 Stage 2 上传均 `NOT_RUN/DISABLED`，下一独立 Run 为 `TSK.x2n.skeleton.006`。

## v0.0.0.1 — Stage 2 / Skeleton 001

- 实现小红书当前详情页 clean-room 检测与提取：稳定 ID、无 Query/Fragment 的规范 URL、净化标题或显式 null、图文/视频/unknown 类型及字段状态；身份冲突和 feed card 均返回 `X2N_PLATFORM_CHANGED`。
- 新增 5 个公共安全合成 DOM Fixture；3 个 ready 与 2 个 platform-changed Observation Diff 全部通过，媒体/raw DOM/Query/Fragment 返回或持久化为 0。
- Extension 增加最小 `scripting` 权限，但仍无 Host Permission、静态 Content Script、Storage/Cookie/Tabs/Downloads 或远程代码；默认 Action 前注入和采集均拒绝，Action 后仅凭临时 `activeTab` 执行隔离世界提取。
- Playwright 通过 Chromium 官方 CDP 默认 Action 触发测试真实权限语义；合成当前页进入 Native Host/SQLite skeleton Job 后，100 次 Service Worker 重启 0 丢单/重单/错状态。
- 两轮 full lane 共 24/24 Blocking Gate 通过，blocking failure/flaky/silent skip 为 0；新增的并发回归测试修复 SQLite `-wal/-shm` 在连接关闭期间消失引发的 chmod 竞态，Canonical DB 文件仍严格 Fail Closed。
- 历史 Foundation/Review verifier 改为固定提交取证并对 live tree 做追加式验证；历史测试数、权限与 Gate 事实不改写，当前新增测试不再被误判为历史漂移。
- 当前能力位为 `ci_synth_only`；小红书一手开放资料未提供可验证的个人内容读取能力，真实页面与 Owner Canary 保持 `UNKNOWN_DISABLED / NOT_RUN`。
- `ACC.x2n.capture.001` 仅 CI-SYNTH scoped pass；`G2=NOT_RUN`，Stage 2 禁止上传，下一独立 Run 为 `TSK.x2n.skeleton.002`。

## v0.0.0.1 — Stage 1 Review / G1

- 独立复核 Foundation001–005 的 Task、Acceptance、固定提交与历史证据；Review 不执行新 DAG Task，下一产品 Task 固定为 `TSK.x2n.skeleton.001`。
- 修复 8 个 Review finding：DAG/状态漂移、full lane 缺少逐执行身份、Stage 1 历史扫描缺口、重复 JSON 键、Runtime CLI 过期 Gate 输出、生成依赖/Build 树造成的零接触扫描误报、缺少 Task Pack 固定版本精确差分，以及 PR 合成 merge commit 误纳入 `main` 并行改动。
- 两轮 full lane 共 24/24 阻塞执行通过，silent skip/failure/flaky 为 0；整体风险覆盖率 70.88%，7 个关键模块均过阈值，33 个依赖的 OSV 漏洞为 0。
- Stage 1 逐提交变更 blob、提交消息、当前 Source 与 workflow 的 Secret/Private/CDN 扫描为 0；53-member 候选制品无 Runtime Data，确定性复现一致。
- 当前结论为 `REVIEW_COMPLETE / G1_PASS / STAGE_2_AUTHORIZED / STAGE_1_REMOTE_UPLOAD_AUTHORIZED`；远端 x2n CI 仍为 `PENDING_POST_G1_UPLOAD`，真实账号、平台、Notion、模型、媒体与 Sink 均 `NOT_RUN`。

## v0.0.0.1 — Stage 1 / Foundation 005

- 新增根级 `x2n-ci.yml`：changed-scope 快速门禁与 macOS full-release 候选门禁；Actions 全 SHA pin、`contents: read`、checkout 不持久化凭据，阻断项不可 `continue-on-error`。
- 软件门禁覆盖 format/lint/type/unit/contract/migration/integration/Extension E2E；full lane 两次重放，风险覆盖阈值登记到机器 policy，关键 Store/Host/Runtime/Contract 模块提供 branch evidence。
- 新增合成 seeded-failure 自测、Secret/Private/CDN/Fixture scan、SAST/SARIF、CSP、匿名 OSV、License、33-component Foundation005 SBOM 与确定性 source candidate allowlist；Runtime Data 和 Unknown License 阈值均为 0。
- 新增 `x2n-synthetic-model-contract-v1@1.0.0` 与模型 System Card；Dataset Contract 通过，但 ASR/OCR/Fusion/Classify/真实 Red Team 均未运行且 Feature Flag 关闭，自动分类等待 `ACC.x2n.ai.006`。
- 该 Foundation005 Run 当时只证明本地合成 CI baseline；远端 GitHub Actions、正式 Release、真实模型、账号、平台、Notion 和媒体均 `NOT_RUN`。其历史证据保持 `G1=NOT_RUN`，下一独立 Run 当时只能做 Stage 1 Review。

## v0.0.0.1 — Stage 1 / Foundation 004

- 新增固定开发 Extension ID 的 Chrome MV3 Side Panel，权限精确为 `activeTab`、`nativeMessaging`、`sidePanel`，无 `host_permissions`、Content Script、远程代码或 Extension Storage。
- Save/Sync/Review/Status/Settings 五区可访问；20 个公共合成 URL 覆盖六平台支持/非支持识别，所有平台动作仍 `executable=false`。
- 新增短进程 Native Messaging Host：精确 Origin、1 MiB 上限、未知动作/字段/版本与 Shell/Path/任意 URL 注入拒绝；重复 Request 只返回同一个 SQLite skeleton Job。
- 用户级 installer 默认 `plan`，写操作需要固定确认词；依赖从 frozen `uv.lock` 导出并强制 hash 校验，私有 Runtime 在 staging 中验证后原子替换；首次/升级失败均清理临时目录并保留旧 Runtime，安装/卸载用内容 hash 拒绝被篡改或非自有文件。
- Playwright 在临时 HOME/Profile/Runtime 中完成真实 Extension E2E：20/20 识别、五区导航、0 uncaught console error、100 次 Service Worker 终止/重启、任务丢失/重复/错状态均为 0；截图与 trace 只保留聚合 hash。
- 新增当前 30-component SBOM 与 Playwright/fsevents NOTICE；`.npmrc` 强制禁用 install scripts，验收执行数为 0。历史 Foundation002 的 26-component SBOM 保持原事实。
- Owner Chrome 安装/Canary、真实账号、平台调用、自动滚动、账号状态改变、Markdown/Notion、模型和媒体均未运行；该 Foundation004 Run 的历史状态为 `G1=NOT_RUN`，下一独立 Run 当时为 `TSK.x2n.foundation.005`。

## v0.0.0.1 — Stage 1 / Foundation 003

- 新增只接受显式 `X2N_DOWNLOAD_DESTINATION`/`X2N_DATA_ROOT` 的 Owner-only Private Runtime；无默认目录、任意路径参数或符号链接逃逸。
- 落地 SQLite Schema v2：17 tables、9 indexes、15 triggers，启用 WAL、FK、FULL synchronous、busy timeout 与启动完整性检查。
- Content/Relation/Artifact/Observation/Classification、Owner Taxonomy、Checkpoint、Request Ledger、Outbox/Receipt、Notion Mapping、Media Lease 和 Recovery Event 进入同一 Canonical Store；Artifact 等追加记录禁止更新/删除。
- 迁移支持前进与强制备份后降级；Backup/Restore 校验文件 Hash、Schema、完整性、表计数与逻辑摘要并原子替换。当前同盘副本不冒充异地灾备。
- 纯合成门禁覆盖 80 条连续两次、100 个并发重复消息和 10k DB；重复副作用、数据丢失、不可读记录和 orphan FK 均为 0，`integrity_check=ok`。
- Owner 私有根只初始化 Schema v2 空库，不含账号、平台内容、媒体或 Sink 数据。该 Foundation003 Run 的历史状态为 `G1=NOT_RUN`，下一独立 Run 当时为 `TSK.x2n.foundation.004`。

## v0.0.0.1 — Stage 1 / Foundation 002

- 冻结 `1.0` IPC、Canonical、Relation、Observation、Artifact、Taxonomy、Classification、Sink、Health、Error、Provenance 与 Compatibility Contract；Pydantic 是 JSON Schema、错误 Registry 和 TypeScript shared enums 的生成真源。
- 默认拒绝未知字段/版本/动作；固定 Native Origin 无通配符，消息有大小与动作边界，不存在 Shell、任意路径、任意 URL、Cookie/Header/Token 输入面。
- 用 opaque ephemeral media refs 表达临时媒体，Canonical Contract 无平台媒体 URL 字段；四类 key 确定性校验，Artifact append-only，一级分类仅 `created_by=owner`。
- Markdown/Notion 合成 Provenance 从最终节点连通 Canonical、Observation、Adapter、Artifact、Classification、Run 与 Renderer；真实 Sink/Canary 未运行。
- 新增 16 个有效 round-trip、22 个负向 fixture 和 106 个 Native fuzz；生成物 `--check` 与 TypeScript strict compile 通过。
- 精确锁定 5 个 Python Runtime registry packages 与 21 个 TypeScript build-only registry packages，生成 26-component CycloneDX SBOM；npm install script 为 0。
- 三项 Acceptance 仅在当时 Contract/合成范围 PASS；真实 Host/Job、SQLite/Migration/Integrity、Markdown/Notion 均为 `DOWNSTREAM_NOT_RUN`。该 Foundation002 Run 未运行 G1，下一独立 Run 当时为 `TSK.x2n.foundation.003`。

## v0.0.0.1 — Stage 1 / Foundation 001

- 新增受治理 Skill 入口、OpenAI agent metadata、npm/uv workspace 与冻结 lock；当前第三方 package 和 install script 均为 0。
- 建立无权限、无 Side Panel/Background/Host Permission 的 MV3 Extension scaffold，以及不含 Server、IPC、DB、Adapter、模型、媒体或 Sink 的 Python Companion scaffold。
- 增加纯合成 lifecycle rehearsal：install、self-test、synthetic Canary、upgrade/rollback dry-run、diagnose、uninstall dry-run，全部明确真实产品 lifecycle 为 `DOWNSTREAM_NOT_RUN`。
- 在隔离临时 HOME 的新副本验证 frozen locks、Extension 与正/负 lifecycle；证据不含私有路径、URL、凭据或内容。
- `TSK.x2n.foundation.001` 当时范围 PASS；该 Run 未运行 G1，下一独立 Run 当时为 `TSK.x2n.foundation.002`。

## v0.0.0.1 — Stage 0 Review Resume / G0 PASS

- 依据 `CE-X2N-20260720-S00-REVIEW-RESUME` 将共享认证材料限定为 x2n 外部、Owner 管理的并行基础设施；x2n 不读取、使用、改变或显示它，也不修改全局 Git 配置或 Credential Helper。
- 保留 Secret/CDN 不可 Owner waiver 的全局规则；新增匿名公开 GitHub Snapshot 工具与 11 项零接触控制。
- 用闭合 `0600` 私有回执记录 Owner 决策；公开证据不含回执 ID、时间、哈希、账号、URL、本机路径或材料值。
- 完整重跑当前树、项目历史、私有根、Local Remote、原始输入、Phase 0.1/0.2/0.5、历史证据与 G0；所有敏感形态扫描为 0，cutoff 后 x2n overlap 为 0。
- 首次 Review 的 `BLOCKED_OWNER_ACTION` 证据保持不变；新 `review_resume/` 证据签发 `G0 PASS`。
- Stage 0 整阶段上传与下一独立 Run 的 `TSK.x2n.foundation.001` 已授权；本 Resume Run 未执行产品代码、账号、平台、Notion、模型或媒体操作。

## v0.0.0.1 — Stage 0 Review

- 基于 `origin/main` 明确 cutoff 完成独立 Review/Fix/Re-acceptance；cutoff 后无关长期开发不吸收，触及 x2n 才阻断。
- 修复三个旧 Phase verifier 不接受独立 Review 分支的问题，并完整重跑 Phase 0.1/0.2/0.5。
- 将 Owner 执行约束从“每 Run 一个 Phase”收紧为“每普通 Run 一个 DAG Task 及其 Acceptance”；Stage Review 是不执行新 Task 的专用例外。
- 删除残留 `MediaCrawler` 产品 Adapter Feature Flag 和“外部安装”措辞；下载父目录名仍只代表存储路由，受限上游保持零安装、零执行、零输出接收。
- 复核原始 roadmap/ZIP 固定哈希；确认原输入没有指定 macOS 下载绝对路径。
- 重新核对 `ShilongLee/Crawler` 固定提交与 Chrome/Notion/六平台一手来源；竞品提交未漂移，六平台仍全部 `UNKNOWN_DISABLED`。
- 28 个单测通过（2 个私有可选输入测试按设计跳过），20 份历史 Phase receipt 保持未改，产品/账号/平台/Notion/模型/媒体均 `NOT_RUN`。
- 本地自动门禁通过，但 `INC-X2N-S00-P05-001` Owner Action 未完成；真实结论为 `G0_BLOCKED_OWNER_ACTION`，Stage 1 与远端上传继续禁止。
- Review Follow-up 修复了 Owner Recovery 仅有文字要求的盲点：新增闭合 Schema、合成 Fixture、不可覆盖的私有生成器和缺失/恶意/越权负向 verifier；没有生成真实回执，G0 状态不变。

## v0.0.0.1 — Stage 0 / Phase 0.5

- 通过 Owner Change Event 将终态范围扩为六平台，保留稳定项目名；DAG 从 35 增至 43 Task、需求从 28 增至 32、Acceptance 从 49 增至 61。
- 按 Owner 指令把子项目统一为 `xhs-douyin-2notion/`；记录原始 taskpack 未指定本机绝对下载路径，并将私有根固定为 Owner 下载目的地下同名隔离命名空间，既有同级条目触碰数为 0。
- 固化六平台 Capability/Policy/Auth 独立门禁、Feature Flag、Kill Switch 与所有下载统一 `X2N_DATA_ROOT` 契约。
- 完成 Chrome/CWS、Notion 和六平台一手政策快照、ADR-001–010、DFD/STRIDE、20 条 Stop/Kill 与 50 条合成治理用例。
- 深审 `ShilongLee/Crawler` 固定 Commit；因自定义非商业 License 与安全/隐私差距，限定为 clean-room ideas only，0 copy/vendor/runtime dependency。
- 收紧受限上游边界：ShilongLee/Crawler 与 MediaCrawler 仅为不可执行审计参考，不安装、不运行、不接收输出，也不是产品 Adapter。
- Owner 未提供值全部采用可逆保守默认；六平台、Notion、云模型、真实同步均保持关闭。
- 临时研究 remote 的凭据形态 URL 已按 `INC-X2N-S00-P05-001` 隔离：临时副本删除、项目/私有根文件扫描 0 命中；G0 前仍需轮换/重新认证或过期证明。
- 新增 Owner 指定的长期并行 worktree 隔离：默认仍要求 clean main，显式 override 仅在外部 dirty paths 与 x2n 零重叠时通过，公开证据只记录计数。
- 未进入产品代码、真实账号、平台/Notion/模型请求、Stage Gate 或远端上传。

## v0.0.0.1 — Stage 0 / Phase 0.2

- 精确登记 xiaohongshu-exporter、douyin-downloader 与 MediaCrawler 的 Commit/tree/关键文件哈希。
- 建立 Dependency Registry、Capability Matrix、License/NOTICE、SBOM dry run 与 Shadow-upgrade Plan。
- 将 xhs exporter 限定为 clean-room reference，将 MediaCrawler 限定为 external non-commercial research；douyin wrapper 保持关闭并等待 exact lock 与 Adapter contract。
- 平台个人点赞/收藏官方能力未确认时保持 `UNKNOWN / DISABLED`。
- 未运行上游或产品代码，未访问真实账号，未进入 Phase 0.5、Stage Gate 或远端上传。

## v0.0.0.1 — Stage 0 / Phase 0.1

- 注册唯一母仓库、子项目和 Stage 0–6 Task DAG。
- 将 Runtime 与全部 Adapter 下载统一到私有逻辑根 `X2N_DATA_ROOT`。
- 建立 Public Artifact / Private Runtime 路径契约、合成 Fixture 清单和机器验证入口。
- 保存原始输入 SHA-256，并以 Owner Change Event 记录路由与路径修正。
- 未进入产品代码、真实账号、浏览器、Notion、模型或媒体执行。
