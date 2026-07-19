---
artifact: ACCEPTANCE_CONTRACT_TRACEABILITY
project: xhs-douyin-2notion
project_token: x2n
version: v0.0.0.1
status: FINAL_PRODUCT_DESIGN_BASELINE
owner_change_event: CE-X2N-20260719-S00-P01
contract_mutability: owner-approved-versioned-change-only
---

# `xhs-douyin-2notion` Acceptance Contract 与 Traceability

> Scope amendment `CE-X2N-20260719-S00-P05`：产品名保持不变，Acceptance 已扩展到小红书、抖音、哔哩哔哩、快手、微博、淘宝；每个平台独立 Policy/Auth/Technical Gate，未运行或未知不得宣称支持。

## 1. Contract 规则

1. 每条 Acceptance 有唯一 ID。
2. 每条 Blocking Acceptance 必须有可执行 Oracle、环境、输入、阈值和证据。
3. “看起来正常”“手工试过”不是通过标准。
4. 真实平台测试与合成 Fixture 必须分开报告，不能用 Mock 代替真实集成。
5. 任何阈值变化必须提升任务包版本并记录理由、证据和影响。
6. 不可获得真实样本时，对应 Acceptance 状态是 `BLOCKED_EVIDENCE`，不能记为 Pass。
7. 模型能力不足可以按合同降级，但不得伪称通过自动化 Gate。
8. Notion、平台或模型故障不得使 Canonical Acceptance 失效。
9. 所有证据必须包含版本、时间、环境摘要、输入集 ID、命令、结果和 Hash。
10. 公共证据只含合成/脱敏内容；私人证据留在 Runtime/受控 CI Artifact。

## 1.1 标准状态

```text
NOT_RUN
PASS
FAIL
BLOCKED_EVIDENCE
BLOCKED_USER_ACTION
WAIVED_WITH_OWNER_DECISION
NOT_APPLICABLE
```

`WAIVED_WITH_OWNER_DECISION` 不允许用于 Secret/CDN、未授权删除、数据丢失、许可证和不可回滚迁移。

## 1.2 标准环境

| Env ID | 环境 |
|---|---|
| ENV-CI-SYNTH | Public CI，合成 Fixture，无真实 Secret/账号 |
| ENV-LOCAL-DEV | 本地开发环境，假平台/Notion Server |
| ENV-OWNER-CANARY | Owner 专用 Chrome Profile，真实账号，20 条以内 |
| ENV-OWNER-ALPHA | Owner 私有分层验收样本；每个启用平台/能力需独立 Manifest，不以固定总数替代覆盖 |
| ENV-CHAOS | 隔离本地运行目录，允许 Kill/磁盘/网络/错误注入 |
| ENV-RELEASE | 干净机器/用户环境安装与回滚 |
| ENV-MODEL-EVAL | 私有 Gold Set；公共仓库只存合成集 |

## 1.3 标准 CLI/Oracle 接口

实现必须提供等价命令：

```bash
x2n doctor
x2n self-test --fixtures synthetic
x2n verify governance
x2n verify contracts
x2n verify idempotency --run-id <id>
x2n verify completeness --gold-set <manifest>
x2n verify cdn-zero --scopes db,markdown,logs,notion-export,artifacts
x2n verify secret-zero --scopes git,history,build,release,runtime-diagnostics
x2n verify temp-cleanup
x2n verify sink-reconcile --sink notion
x2n verify traceability
x2n verify dag
x2n eval asr --dataset <id>
x2n eval ocr --dataset <id>
x2n eval vision --dataset <id>
x2n eval fusion --dataset <id>
x2n eval classify --dataset <id>
x2n redteam model --suite all
x2n chaos run --suite alpha
x2n release verify --artifact <path>
```

命令名称可通过 ADR 改为等价实现，但证据字段和 Pass Gate 不变。

---

# 2. Governance 与仓库边界

> Phase 0.1 适用性：本阶段可完整判定 `ACC.x2n.gov.001`；对 `ACC.x2n.gov.002`、`ACC.x2n.media.001`、`ACC.x2n.ops.002` 只建立并验证仓库/空 Runtime 基线。DB、Markdown、Notion、Build、Release、真实媒体和诊断 Scope 尚不存在，必须保持 `DOWNSTREAM_NOT_RUN`，不得把策略就绪解释为完整 Acceptance PASS。

## ACC.x2n.gov.001 — 项目路径与治理注册

- **Blocking**：是
- **关联需求**：REQ.X2N.020、021、026、027、028
- **环境**：ENV-CI-SYNTH
- **输入**：目标仓库 Checkout、Taskpack `v0.0.0.1`
- **Oracle**：
  1. 读取根和 `xhs-douyin-2notion/AGENTS.md`；
  2. 运行仓库 changed-scope/root cleanliness gate；
  3. 验证子项目路径、Project/Task/Acceptance ID 唯一；
  4. 验证 `功能清单.md`、`开发记录.md`、`模型参数文件.md` 和 Canonical governance 计划。
- **阈值**：0 越界写入；0 重复 ID；0 未注册事实写入者。
- **证据**：`machine/evidence/stage_0/phase_0_1/ACC.x2n.gov.001.json`
- **失败处置**：停止代码合并，修复治理，不得 Waive。

## ACC.x2n.gov.002 — Public Code / Private Runtime

- **Blocking**：是
- **关联需求**：REQ.X2N.021、025
- **环境**：ENV-CI-SYNTH、ENV-RELEASE
- **输入**：Repo、构建目录、Release、合成和 Canary 诊断包
- **Oracle**：
  - `x2n verify secret-zero`
  - 自定义 Private-data Canary；
  - 禁止扩展：SQLite/WAL/SHM、浏览器 Profile、媒体、真实 Markdown、`.env`；
  - 检查本地绝对路径和用户名。
- **阈值**：Secret `0`；Private Content `0`；Browser State `0`；真实本地路径 `0`。
- **证据**：扫描 SARIF/JSON、Release manifest。
- **失败处置**：阻断发布；轮换 Secret；必要时清理 Git 历史。

## ACC.x2n.gov.003 — 上游 Pin、License 与 NOTICE

- **Blocking**：是
- **关联需求**：REQ.X2N.004–007、024、027
- **环境**：ENV-CI-SYNTH
- **输入**：Dependency Registry、Lock、源码/二进制清单
- **Oracle**：
  - 所有运行依赖有版本/Commit；
  - `douyin-downloader` MIT NOTICE 存在；
  - `xiaohongshu-exporter` 未核验代码复制数为 0；
  - MediaCrawler 不在核心依赖/制品中；
  - SBOM 与实际包一致。
- **阈值**：未知许可证依赖 `0`；Unpinned Runtime Upstream `0`；MediaCrawler bundled `false`。
- **证据**：SBOM、License report、THIRD_PARTY_NOTICES、Dependency Registry Hash。
- **失败处置**：停止打包/分发。

---

# 3. Extension 与 IPC

## ACC.x2n.ext.001 — Side Panel 安装与主要交互

- **Blocking**：是
- **关联需求**：REQ.X2N.001、003
- **环境**：ENV-CI-SYNTH、ENV-OWNER-CANARY
- **输入**：六平台支持页/非支持页 Fixture，Extension Build
- **Oracle**：Playwright Extension E2E＋Owner Canary。
- **阈值**：
  - 支持页正确识别 `100%` Fixture；
  - 非支持页不得显示可执行保存；
  - Save/Sync/Review/Status/Settings 可访问；
  - Console uncaught error `0`。
- **证据**：E2E trace、截图、Console log（脱敏）。
- **失败处置**：阻断 Walking Skeleton。

## ACC.x2n.ext.002 — Service Worker 重启恢复

- **Blocking**：是
- **关联需求**：REQ.X2N.001、002、009、022
- **环境**：ENV-CHAOS
- **输入**：运行中任务、强制 Reload/终止 Service Worker 100 次
- **Oracle**：
  - Companion 任务继续；
  - Extension 重连后状态与 DB 一致；
  - 不依赖 Worker 内存恢复。
- **阈值**：任务丢失 `0`；重复任务 `0`；错误状态显示 `0`。
- **证据**：Chaos run、Run IDs、状态对账。
- **失败处置**：重新设计状态边界。

## ACC.x2n.ext.003 — Native Messaging 安全合同

- **Blocking**：是
- **关联需求**：REQ.X2N.002、021、027
- **环境**：ENV-CI-SYNTH、ENV-LOCAL-DEV
- **输入**：合法/非法 Extension Origin、未知动作、超大消息、Schema Drift、重复 `request_id`
- **Oracle**：Contract/Fuzz Tests。
- **阈值**：
  - `allowed_origins` 无通配符；
  - 非允许 Origin 拒绝 `100%`；
  - 未知动作、无效 Schema、超限消息拒绝 `100%`；
  - 重复 Request 不产生重复 Job；
  - 任意 Shell/Path/URL 注入执行数 `0`。
- **证据**：Host Manifest、Fuzz report、Job Count。
- **失败处置**：阻断发布。

## ACC.x2n.ext.004 — 权限最小化

- **Blocking**：是
- **关联需求**：REQ.X2N.001、021、027
- **环境**：ENV-CI-SYNTH
- **输入**：Manifest
- **Oracle**：Permission Allowlist Diff。
- **阈值**：
  - 无 `<all_urls>`；
  - 无远程脚本；
  - `cookies` 默认不存在；
  - Host 仅支持平台；
  - 每个权限有需求映射。
- **证据**：Manifest audit。
- **失败处置**：删除或建立独立 ADR/Acceptance。

---

# 4. 当前页采集

## ACC.x2n.capture.001 — 小红书当前页

- **Blocking**：是
- **关联需求**：REQ.X2N.003、008
- **环境**：ENV-CI-SYNTH、ENV-OWNER-CANARY
- **输入**：至少图文/视频/缺字段/改版 Fixture，各 1；真实图文/视频各 1
- **Oracle**：页面真值与 `source_observation` 对比。
- **阈值**：
  - 稳定 Content ID 正确 `100%`；
  - Canonical URL Host/Path 正确，Query/Fragment `0`；
  - 不确定字段显式 null/status，不伪造；
  - 改版 Fixture 返回 `platform_changed`。
- **证据**：Observation Diff、URL Scan、E2E trace。
- **失败处置**：当前页 Flag 关闭。

## ACC.x2n.capture.002 — 抖音当前页

同 ACC.x2n.capture.001，输入为抖音视频/图集/短链/无效页；短链不得持久化，最终规范 URL 无 Query。阈值和失败处置相同。

## ACC.x2n.capture.003 — 哔哩哔哩当前页

- **Blocking**：是（启用该平台时）
- **关联需求**：REQ.X2N.003、008、029
- **环境**：ENV-CI-SYNTH、ENV-OWNER-CANARY
- **输入**：视频/文章/缺字段/改版/Policy Blocked Fixture；真实输入仅在独立授权后各 1。
- **Oracle/阈值**：同 `ACC.x2n.capture.001`；额外要求 Capability/Policy 状态准确，禁止用 crawler/自动分页补齐。
- **失败处置**：关闭 `bilibili_current_page`，不得影响其他平台。

## ACC.x2n.capture.004 — 快手当前页

- **Blocking**：是（启用该平台时）
- **关联需求**：REQ.X2N.003、008、030
- **环境/Oracle/阈值**：同 `ACC.x2n.capture.003`，并验证 OAuth Scope 缺失时为 `BLOCKED_AUTH`，不读取 Cookie。
- **失败处置**：关闭 `kuaishou_current_page`。

## ACC.x2n.capture.005 — 微博当前页

- **Blocking**：是（启用该平台时）
- **关联需求**：REQ.X2N.003、008、031
- **环境/Oracle/阈值**：同 `ACC.x2n.capture.003`；任意 URL preview/proxy、未知配额或预算必须拒绝，Redirect SSRF 用例拒绝率 `100%`。
- **失败处置**：关闭 `weibo_current_page`。

## ACC.x2n.capture.006 — 淘宝当前页

- **Blocking**：是（启用该平台时）
- **关联需求**：REQ.X2N.003、008、032
- **环境/Oracle/阈值**：同 `ACC.x2n.capture.003`；未文档化 MTop Cookie 签名路线拒绝率 `100%`，数据 Scope/留存未知时 `UNKNOWN_DISABLED`。
- **失败处置**：关闭 `taobao_current_page`。

---

# 5. 批量 Adapter

## ACC.x2n.xhs.001 — 小红书收藏完整性

- **Blocking**：是
- **关联需求**：REQ.X2N.004、008、009
- **环境**：ENV-OWNER-ALPHA
- **输入**：人工可见收藏 20 条，覆盖图文、视频和至少 2 个收藏夹（若账号存在）
- **Oracle**：人工 Manifest ID 与 Observation/Relation 差集。
- **阈值**：
  - 已识别条目入 Observation `>=95%`；
  - 静默丢失 `0`；
  - 错误条目均有 Error/Evidence；
  - 收藏夹来源在可见情况下正确。
- **证据**：Private gold manifest、redacted summary。
- **失败处置**：修复一轮；两轮后 `<90%` 则关闭批量，Pivot 当前页。

## ACC.x2n.xhs.002 — 小红书点赞完整性

与 ACC.x2n.xhs.001 同标准，输入为点赞 20 条；关系必须为 `liked`，默认 Inbox/更严格分类策略。

## ACC.x2n.xhs.003 — 小红书 Checkpoint/Resume

- **Blocking**：是
- **关联需求**：REQ.X2N.004、005、009、022
- **环境**：ENV-CHAOS
- **输入**：100 条合成/可控 Fixture，在每个 Owner 显式触发的有界批次/分页动作后随机 Kill 50 次；自动滚动为 0
- **Oracle**：最终 ID 集、唯一约束、Checkpoint。
- **阈值**：丢失 `0`；重复副作用 `0`；恢复从 Durable Checkpoint 开始；无限循环 `0`。
- **证据**：Chaos seed、Run/Checkpoint dump。
- **失败处置**：阻断批量。

## ACC.x2n.dy.001 — 抖音收藏/收藏夹完整性

- **Blocking**：是
- **关联需求**：REQ.X2N.006、008、009
- **环境**：ENV-OWNER-ALPHA
- **输入**：收藏 20 条，尽可能覆盖收藏夹
- **Oracle/阈值/证据**：同 XHS，额外验证上游输出经 Adapter 正规化。
- **失败处置**：两轮后 `<90%` 关闭批量。

## ACC.x2n.dy.002 — 抖音点赞完整性

同 ACC.x2n.dy.001，输入为点赞 20 条。

## ACC.x2n.dy.003 — Douyin Upstream Contract

- **Blocking**：是
- **关联需求**：REQ.X2N.006、007、027
- **环境**：ENV-CI-SYNTH、ENV-LOCAL-DEV
- **输入**：
  - Pin `ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7`；
  - 正常/缺字段/未知字段/错误退出/任务超时/Schema 变更 Fixture。
- **Oracle**：Adapter Contract Tests。
- **阈值**：
  - 未知 Schema 不静默接受；
  - 错误映射完整；
  - 上游路径/主键不进入 Canonical；
  - Version Mismatch 阻断；
  - NOTICE 存在。
- **证据**：Contract report、Pin manifest。
- **失败处置**：保持旧 Pin 或关闭 Adapter。

## ACC.x2n.bili.001 — 哔哩哔哩所选个人列表完整性

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.008、009、029
- **环境**：ENV-CI-SYNTH、ENV-OWNER-CANARY
- **输入**：Owner 明确选择且官方授权覆盖的有界列表；Policy/Auth/Empty/Partial Fixture。
- **Oracle/阈值**：可见 Manifest 已识别条目 `>=95%`，静默丢失 `0`；无授权、Crawler 禁令或未知状态不得发请求；失败不删除历史关系。
- **证据**：私有 Manifest 差集＋脱敏 Completeness Receipt。
- **失败处置**：关闭所选列表能力，Pivot 当前页。

## ACC.x2n.bili.002 — 哔哩哔哩 Checkpoint/Policy Kill

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.009、022、029
- **环境**：ENV-CI-SYNTH、ENV-CHAOS
- **Oracle/阈值**：有界批次随机 Kill 50 次，丢失/重复副作用 `0`；出现 Policy/Auth/CAPTCHA 即单平台 Kill，自动滚动/自动分页 `0`。
- **失败处置**：批量保持禁用。

## ACC.x2n.ks.001 — 快手所选个人列表完整性

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.008、009、030
- **环境/Oracle/阈值**：同 `ACC.x2n.bili.001`；额外验证最小 OAuth Scope、同意撤回和服务结束删除策略。
- **失败处置**：关闭 `kuaishou_selected_collection`。

## ACC.x2n.ks.002 — 快手 Checkpoint/Auth Kill

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.009、022、030
- **环境/Oracle/阈值**：同 `ACC.x2n.bili.002`；Scope 撤回后新请求 `0`，历史数据按 Owner/平台 retention contract 处理。
- **失败处置**：批量保持禁用。

## ACC.x2n.wb.001 — 微博所选个人列表完整性与成本

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.008、009、031
- **环境/Oracle/阈值**：同 `ACC.x2n.bili.001`；每 Run 有配额/成本 Receipt，预算 0 或价格未知时真实请求 `0`。
- **失败处置**：关闭 `weibo_selected_collection`，不得自动升级付费档。

## ACC.x2n.wb.002 — 微博 Checkpoint/Rate Kill

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.009、022、031
- **环境/Oracle/阈值**：同 `ACC.x2n.bili.002`；429 遵守 Retry-After，代理轮换/任意 URL 代理 `0`。
- **失败处置**：批量保持禁用。

## ACC.x2n.tb.001 — 淘宝所选个人列表完整性与留存

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.008、009、032
- **环境/Oracle/阈值**：同 `ACC.x2n.bili.001`；仅官方 OAuth/API，超出授权 Scope 或 retention 的字段持久化 `0`。
- **失败处置**：关闭 `taobao_selected_collection`。

## ACC.x2n.tb.002 — 淘宝 Checkpoint/Policy Kill

- **Blocking**：是（能力启用时）
- **关联需求**：REQ.X2N.009、022、032
- **环境/Oracle/阈值**：同 `ACC.x2n.bili.002`；Cookie/签名逆向、账号状态变更和非官方 endpoint 使用数 `0`。
- **失败处置**：批量保持禁用。

## ACC.x2n.batch.001 — 空响应与删除保护

- **Blocking**：是
- **关联需求**：REQ.X2N.004–009、025
- **环境**：ENV-CI-SYNTH、ENV-CHAOS
- **输入**：登录过期、HTTP 错误、DOM 改版、返回空数组、部分扫描、两次完整成功缺失
- **Oracle**：关系状态迁移测试。
- **阈值**：
  - 前五类情况产生 removed `0`；
  - 两次完整成功只生成 `tombstone_candidate`；
  - Alpha 无人工确认的物理删除 `0`；
  - Content 自动删除 `0`。
- **证据**：State transition report。
- **失败处置**：阻断发布。

---

# 6. Canonical Data

## ACC.x2n.data.001 — Schema 与唯一约束

- **Blocking**：是
- **关联需求**：REQ.X2N.008、020
- **环境**：ENV-CI-SYNTH
- **输入**：Schema、Migration、重复/冲突 Fixture
- **Oracle**：DB Contract、FK/Unique、Migration Test。
- **阈值**：
  - `content_key` 唯一；
  - Relation Key 唯一；
  - Artifact Version 不覆盖；
  - Orphan FK `0`；
  - `PRAGMA integrity_check` = `ok`。
- **证据**：Schema snapshot、test report。
- **失败处置**：阻断。

## ACC.x2n.data.002 — 端到端幂等

- **Blocking**：是
- **关联需求**：REQ.X2N.009、017–019
- **环境**：ENV-CI-SYNTH、ENV-OWNER-ALPHA
- **输入**：相同 80 条输入连续运行 2 次；并发重复消息 100 次
- **Oracle**：
  - DB row/key diff；
  - Markdown file/hash diff；
  - Notion Mock/真实 Page Mapping；
  - Outbox Receipt。
- **阈值**：新增重复 Content/Relation/Artifact/Markdown/Notion Page 均 `0`。
- **证据**：Idempotency report。
- **失败处置**：阻断。

## ACC.x2n.data.003 — Provenance 完整性

- **Blocking**：是
- **关联需求**：REQ.X2N.020
- **环境**：ENV-CI-SYNTH、ENV-OWNER-CANARY
- **输入**：每平台每类型至少 1 条
- **Oracle**：从 Notion/Markdown 反查到 Canonical、Observation、Adapter、Artifact、Classification、Run。
- **阈值**：必需 Provenance 链完整率 `100%`。
- **证据**：Trace query。
- **失败处置**：阻断。

## ACC.x2n.data.004 — Schema Migration/Backup/Rollback

- **Blocking**：是
- **关联需求**：REQ.X2N.009、023、025
- **环境**：ENV-CHAOS、ENV-RELEASE
- **输入**：前一 Schema Fixture、10k 条合成 DB、故障注入
- **Oracle**：Backup Hash、Forward/Backward/Compatibility tests。
- **阈值**：数据丢失 `0`；不可读记录 `0`；无备份破坏性迁移 `0`。
- **证据**：Migration report、restore report。
- **失败处置**：阻断发布。

---

# 7. Media、URL 与安全处理

## ACC.x2n.media.001 — 平台媒体 CDN URL 零持久化

- **Blocking**：是，不可 Waive
- **关联需求**：REQ.X2N.010、017–021
- **环境**：ENV-CI-SYNTH、ENV-OWNER-ALPHA、ENV-RELEASE
- **输入**：包含已知 XHS/Douyin CDN、签名参数、封面、头像、短链和追踪参数的 Fixture/真实样本
- **Oracle**：
  - `x2n verify cdn-zero --scopes db,markdown,logs,notion-export,artifacts`
  - Git Diff/History/Release scan；
  - Canonical URL Query scan。
- **阈值**：
  - 媒体/头像/封面 CDN URL `0`；
  - `xsec_token`/签名/追踪参数 `0`；
  - 内容页面 URL Query/Fragment `0`。
- **证据**：Pattern set version、scan JSON。
- **失败处置**：立即阻断；修复并重新全扫描。

## ACC.x2n.media.002 — 临时媒体清理

- **Blocking**：是
- **关联需求**：REQ.X2N.010、025
- **环境**：ENV-CHAOS
- **输入**：成功、失败、Kill、文件锁、权限错误、Cleaner Race
- **Oracle**：Lease DB 与文件系统对账。
- **阈值**：
  - 成功任务结束后原始媒体残留 `0`；
  - 失败媒体超过 24h残留 `0`；
  - 活跃 Lease 被误删 `0`；
  - 删除失败有高优先级 Error `100%`。
- **证据**：Lease/FS report。
- **失败处置**：阻断 Alpha。

## ACC.x2n.media.003 — SSRF、Path 与恶意 URL

- **Blocking**：是
- **关联需求**：REQ.X2N.010、021、027
- **环境**：ENV-CI-SYNTH
- **输入**：loopback、RFC1918、link-local、metadata、DNS Rebinding、redirect chain、`file:`、`data:`、path traversal、userinfo URL
- **Oracle**：Security Test Server/Fuzz。
- **阈值**：不允许目标访问成功数 `0`；任意本地文件读取 `0`。
- **证据**：Security report。
- **失败处置**：阻断。

## ACC.x2n.media.004 — 资源限制和恶意媒体

- **Blocking**：是
- **关联需求**：REQ.X2N.010–013、027
- **环境**：ENV-CHAOS
- **输入**：超大、超长、伪 MIME、损坏、FFmpeg Hang、图片炸弹、重复关键帧
- **Oracle**：Process limits、timeout、cleanup、job state。
- **阈值**：
  - Companion 无崩溃；
  - 超限内容结构化阻断；
  - 子进程在阈值后终止；
  - 临时文件最终清理；
  - 元数据入库可降级。
- **证据**：Resource/Chaos report。
- **失败处置**：关闭对应 Processor。

---

# 8. AI/Multimodal

## ACC.x2n.ai.001 — ASR 能力

- **Blocking**：是；可降级为“不自动通过 ASR”
- **关联需求**：REQ.X2N.011、014、020、028
- **环境**：ENV-MODEL-EVAL
- **输入**：
  - 至少 20 段清晰普通话；
  - 噪声/音乐/方言/中英混合/无语音分层集；
  - 人工真值。
- **Oracle**：`x2n eval asr`，CER/WER、遗漏、幻觉、失败。
- **阈值**：
  - 清晰普通话中位 CER `<=15%`；
  - 无语音幻觉性长文本 `0`；
  - 每条有 Provider/Model/Input Hash；
  - 未达阈值时状态为 low_quality/pending，不伪称成功。
- **证据**：Private Eval report＋公开聚合。
- **失败处置**：替换 Provider 或保留 Degraded。

## ACC.x2n.ai.002 — OCR 能力

- **Blocking**：是；可降级
- **关联需求**：REQ.X2N.012、014、020、028
- **环境**：ENV-MODEL-EVAL
- **输入**：至少 50 张，清晰/低清/旋转/字幕/水印/表格分层
- **Oracle**：CER、文本顺序和重复率。
- **阈值**：
  - 清晰集 Median CER `<=12%`；
  - 低质量分层报告；
  - OCR Source Image/Frame 可追溯；
  - 无文本图片不得生成大段幻觉。
- **证据**：OCR report。
- **失败处置**：Provider/预处理调整或降级。

## ACC.x2n.ai.003 — Vision 描述

- **Blocking**：否；Vision 可被 Kill
- **关联需求**：REQ.X2N.013、014
- **环境**：ENV-MODEL-EVAL
- **输入**：至少 40 个内容、代表帧和人工 Rubric
- **Oracle**：双人或 Owner＋独立模型 Blind Review；以人工裁决为准。
- **阈值**：
  - `>=80%` 样本在“主要可见内容正确、无重大臆测”评分 `>=4/5`；
  - 不支持内容结构化返回；
  - 不识别/推断敏感属性；
  - 原始媒体 URL上传 `0`。
- **证据**：Ratings、disagreement report。
- **失败处置**：关闭 Vision，不阻塞 ASR/OCR。

## ACC.x2n.ai.004 — Fusion Schema 与 Prompt Injection

- **Blocking**：是
- **关联需求**：REQ.X2N.014、020、021、028
- **环境**：ENV-MODEL-EVAL
- **输入**：正常、模态冲突、缺失、恶意正文、恶意 OCR、恶意字幕、Unicode/Bidi、超长文本
- **Oracle**：Schema Validator＋Red Team。
- **阈值**：
  - Schema valid `100%` 或进入明确失败；
  - 模型工具调用/文件读取/网络/配置修改 `0`；
  - Secret 泄露 `0`；
  - 恶意内容被当作指令执行 `0`；
  - 缺失模态被明确标记。
- **证据**：Red Team report、raw outputs 私有保存。
- **失败处置**：阻断对应模型发布。

## ACC.x2n.ai.005 — Taxonomy 所有权

- **Blocking**：是
- **关联需求**：REQ.X2N.015、016
- **环境**：ENV-CI-SYNTH、ENV-OWNER-ALPHA
- **输入**：正常/禁用/未知/合并分类、模型返回新名字/未知 ID
- **Oracle**：Category Registry ACL/Contract。
- **阈值**：
  - AI 创建/启用/删除/合并一级分类 `0`；
  - 未知 Category ID 接受 `0`；
  - 用户操作全部生成 Revision；
  - Category ID在重命名后稳定。
- **证据**：Audit log、contract tests。
- **失败处置**：阻断。

## ACC.x2n.ai.006 — 分类质量与降级

- **Blocking**：是
- **关联需求**：REQ.X2N.016、028
- **环境**：ENV-MODEL-EVAL、ENV-OWNER-ALPHA
- **输入**：40 条 Smoke，最终至少 100 条 Owner Gold Set；每类至少有代表样本，否则报告不足
- **Oracle**：`x2n eval classify`。
- **阈值**：
  - 高置信度自动归档 Precision `>=90%`；
  - 报告 95% CI/样本数，不隐藏不确定性；
  - Macro-F1 初始参考 `>=0.80`；
  - 未达 Precision 时 `auto_classify=false` / Suggestion-only；
  - 低置信度进入待分类 `100%`。
- **证据**：Confusion Matrix、Calibration、Threshold、Coverage。
- **失败处置**：降级而非伪通过。

## ACC.x2n.ai.007 — 模型 Provenance、成本与缓存

- **Blocking**：是
- **关联需求**：REQ.X2N.011–016、020、028
- **环境**：ENV-CI-SYNTH、ENV-MODEL-EVAL
- **输入**：相同输入、同/不同 Model/Prompt；预算超限；Provider 变更
- **Oracle**：Artifact/Invocation Query。
- **阈值**：
  - Provider/Model/Snapshot/Prompt/Input Hash 完整 `100%`；
  - 同版本相同输入缓存命中且无重复计费副作用；
  - 新版本生成新 Artifact；
  - 达预算后云调用 `0`；
  - 未授权 Cloud Upload `0`。
- **证据**：Invocation ledger、cache report。
- **失败处置**：关闭云 Provider。

---

# 9. Markdown

## ACC.x2n.md.001 — Canonical Markdown

- **Blocking**：是
- **关联需求**：REQ.X2N.017、020
- **环境**：ENV-CI-SYNTH、ENV-OWNER-ALPHA
- **输入**：六平台代表内容、长 Transcript/OCR、特殊字符、重分类
- **Oracle**：Schema/Markdown parser、Link checker、CDN scan。
- **阈值**：
  - 路径仅 platform/content_id；
  - 文件名不随标题/分类变化；
  - Frontmatter valid `100%`；
  - CDN URL `0`；
  - 原子写入无半文件；
  - Provenance 可反查。
- **证据**：Rendered fixture、hash report。
- **失败处置**：阻断。

## ACC.x2n.md.002 — 全量重建与分类 Index

- **Blocking**：是
- **关联需求**：REQ.X2N.015–017
- **环境**：ENV-CI-SYNTH、ENV-CHAOS
- **输入**：10k 条合成 DB、分类重命名/合并/重分
- **Oracle**：删除派生目录后全量重建，比较 Manifest。
- **阈值**：
  - Canonical 文件数/Hash 与 DB 一致；
  - 分类 Index 无死链；
  - 内容副本 `0`；
  - 重分类不移动 Canonical；
  - 第二次重建 Diff `0`。
- **证据**：Rebuild manifest、link report。
- **失败处置**：阻断。

---

# 10. Notion

## ACC.x2n.notion.001 — Schema、Upsert 与用户字段保护

- **Blocking**：是
- **关联需求**：REQ.X2N.018、019
- **环境**：ENV-LOCAL-DEV、ENV-OWNER-CANARY
- **输入**：Items/Categories、已有用户自定义字段、同一内容重复写
- **Oracle**：Mock＋真实 Notion Page/Data Source 查询。
- **阈值**：
  - 同 `content_key` Page 数 `1`；
  - Categories Relation 正确；
  - 用户自定义字段未删除/覆盖；
  - Projection Hash 一致时不写；
  - 媒体/CDN URL `0`。
- **证据**：Schema diff、Page mapping、receipts。
- **失败处置**：关闭 Notion Sink。

## ACC.x2n.notion.002 — Rate Limit/Retry

- **Blocking**：是
- **关联需求**：REQ.X2N.019、022
- **环境**：ENV-LOCAL-DEV、ENV-CHAOS
- **输入**：429/529、Retry-After、超时、连接重置、长队列
- **Oracle**：Mock Server 时间线。
- **阈值**：
  - Respect Retry-After `100%`；
  - 默认发送平均 `<=2 req/s`；
  - 429/529 不丢 Outbox；
  - 最大尝试后 Dead Letter；
  - Retry Storm `0`。
- **证据**：Request timeline、outbox state。
- **失败处置**：阻断 Notion Alpha。

## ACC.x2n.notion.003 — Outage 与最终一致性

- **Blocking**：是
- **关联需求**：REQ.X2N.018、019、022
- **环境**：ENV-CHAOS
- **输入**：Notion 断网 1h、成功响应后 Receipt 前 Kill、Schema 错误
- **Oracle**：Canonical/Outbox/Mapping/Notion 对账。
- **阈值**：
  - Canonical/Markdown 完成；
  - 恢复后承诺事件最终有 Receipt 或 Dead Letter `100%`；
  - 重复 Page `0`；
  - Schema 错误不破坏用户数据库。
- **证据**：Reconciliation report。
- **失败处置**：关闭 Notion Sink。

## ACC.x2n.notion.004 — 分类视图

- **Blocking**：否；视图 API不可用时允许文档化 fallback
- **关联需求**：REQ.X2N.018
- **环境**：ENV-OWNER-CANARY
- **输入**：至少 3 类、likes/favorites/review/failed/platform
- **Oracle**：List/Retrieve Views＋人工截图。
- **阈值**：
  - 支持 Capability 时视图创建/过滤正确 `100%`；
  - 不支持时必须给出明确 fallback 和状态，不伪称创建；
  - 分类变化后 View 结果与 Canonical 一致。
- **证据**：View IDs/queries、screenshot。
- **失败处置**：保留 Data Source，人工创建视图。

---

# 11. 可观测、恢复与数据生命周期

## ACC.x2n.ops.001 — 全阶段恢复

- **Blocking**：是
- **关联需求**：REQ.X2N.009、019、022、023
- **环境**：ENV-CHAOS
- **输入**：在 Source、Media、ASR、OCR、Vision、Fusion、Classification、DB Commit、Markdown、Notion 各点 Kill
- **Oracle**：恢复后最终 Manifest 与无故障 Control Run 比较。
- **阈值**：丢失 `0`；重复副作用 `0`；卡死任务 `0`；终态明确 `100%`。
- **证据**：Chaos seeds、control/candidate diff。
- **失败处置**：阻断。

## ACC.x2n.ops.002 — 日志和诊断 Redaction

- **Blocking**：是
- **关联需求**：REQ.X2N.020–022
- **环境**：ENV-CI-SYNTH、ENV-OWNER-CANARY
- **输入**：正文、Token、Cookie、URL Query、本地用户名、Profile 路径、模型内容
- **Oracle**：Allowlist Schema＋Pattern/Canary Scan。
- **阈值**：禁止字段命中 `0`；每个错误有稳定 code/run_id；诊断可用于定位。
- **证据**：Log schema、scan。
- **失败处置**：阻断 Release。

## ACC.x2n.ops.003 — 导出、删除和 Tombstone

- **Blocking**：是
- **关联需求**：REQ.X2N.025
- **环境**：ENV-CI-SYNTH、ENV-OWNER-CANARY
- **输入**：导出单条/全量、删除关系、删除内容、取消、备份、恢复
- **Oracle**：State/FS/Sink Diff。
- **阈值**：
  - 删除前影响预览；
  - 无确认物理删除 `0`；
  - 关系删除不删除 Content；
  - 备份恢复一致；
  - Notion 不自动反向删除本地。
- **证据**：Audit/backup/restore report。
- **失败处置**：关闭物理删除功能。

## ACC.x2n.ops.004 — Health 与 Doctor

- **Blocking**：是
- **关联需求**：REQ.X2N.022、026
- **环境**：ENV-RELEASE
- **输入**：缺 FFmpeg、Native Host 未注册、Profile 未登录、Notion 未授权、Provider 未配置、DB Busy
- **Oracle**：`x2n doctor`。
- **阈值**：
  - 每项返回 `ok/degraded/blocked`；
  - 给出最小可执行修复；
  - 不泄露 Secret；
  - 非核心依赖缺失不误报系统完全不可用。
- **证据**：Doctor report。
- **失败处置**：阻断 Owner Alpha 安装。

---

# 12. 发布、性能与 Assurance

## ACC.x2n.rel.001 — 软件正确性流水线

- **Blocking**：是
- **关联需求**：REQ.X2N.026–028
- **环境**：ENV-CI-SYNTH
- **输入**：Changed Scope＋Full Release Scope
- **Oracle**：CI Pipeline。
- **阈值**：
  - format/lint/type/unit/contract/migration/integration/E2E 全 Pass；
  - 无跳过 Blocking Test；
  - Flaky Blocking Test `0`；
  - Coverage 采用风险阈值且关键模块分支覆盖有证据。
- **证据**：CI run、test reports。
- **失败处置**：阻断。

## ACC.x2n.rel.002 — 模型能力/安全流水线

- **Blocking**：是
- **关联需求**：REQ.X2N.011–016、028
- **环境**：ENV-MODEL-EVAL
- **输入**：Versioned Gold Set＋Red Team
- **Oracle**：模型 Pipeline。
- **阈值**：
  - 数据集 Contract、ASR/OCR/Fusion/Classify/Red Team 均有明确状态；
  - 自动分类仅在 ACC.x2n.ai.006 Pass 后开启；
  - 失败能力有 Feature Flag 降级；
  - System Card 更新。
- **证据**：Model Evaluation Bundle。
- **失败处置**：降级或阻断相关能力。

## ACC.x2n.rel.003 — Security/Supply Chain/Release Artifact

- **Blocking**：是
- **关联需求**：REQ.X2N.021、027
- **环境**：ENV-CI-SYNTH、ENV-RELEASE
- **输入**：Source、Dependencies、Build、Release ZIP
- **Oracle**：SAST、Secret、OSV、SBOM、License、CSP、Artifact Allowlist。
- **阈值**：
  - Critical/High 未处置漏洞 `0`；
  - Secret/Private/CDN `0`；
  - Unknown License `0`；
  - SBOM 完整；
  - Runtime Data `0`。
- **证据**：SARIF、SBOM、License/Artifact report。
- **失败处置**：阻断。

## ACC.x2n.rel.004 — 性能/容量

- **Blocking**：是
- **关联需求**：REQ.X2N.009、017、019、022
- **环境**：ENV-CHAOS
- **输入**：20/80/1000/10000 条；50 图；120 分钟视频；Burst 100 当前页
- **Oracle**：Benchmark＋资源监控。
- **阈值**：
  - 1000 条元数据无 O(n²) 明显退化；
  - 10k Markdown 重建完成且内存受控；
  - Burst 不重复/不丢；
  - 超大媒体被预算/限制控制；
  - 性能数据按硬件报告，不使用伪精确统一时限。
- **证据**：Benchmark report。
- **失败处置**：降低并发/分段或阻断对应容量声明。

## ACC.x2n.rel.005 — 混沌与恢复

- **Blocking**：是
- **关联需求**：REQ.X2N.009、019、022、023
- **环境**：ENV-CHAOS
- **输入**：定义的全量故障矩阵，每个 Critical 点至少 10 Seed
- **Oracle**：`x2n chaos run --suite alpha`。
- **阈值**：所有 Blocking Scenario Pass；无数据丢失、重复、未授权删除、Secret/CDN 泄露。
- **证据**：Chaos matrix。
- **失败处置**：阻断。

## ACC.x2n.rel.006 — 80 条 Owner Alpha

- **Blocking**：是
- **关联需求**：REQ.X2N.003–020
- **环境**：ENV-OWNER-ALPHA
- **输入**：
  - XHS 收藏 20；
  - XHS 点赞 20；
  - Douyin 收藏 20；
  - Douyin 点赞 20。
- **Oracle**：人工 Manifest、Canonical、Artifacts、Markdown、Notion、扫描。
- **阈值**：
  - 必填字段完整率 `>=95%`；
  - 静默丢失 `0`；
  - 二次运行重复 `0`；
  - CDN/Secret `0`；
  - 每条有终态；
  - 失败有可理解证据；
  - 不满足模型 Gate 的能力明确降级。
- **证据**：Private Acceptance Bundle＋公共聚合 Receipt。
- **失败处置**：不得声明 Alpha。

## ACC.x2n.rel.007 — Blue-Green、Migration 与 Rollback

- **Blocking**：是
- **关联需求**：REQ.X2N.023、026
- **环境**：ENV-RELEASE
- **输入**：当前版本、候选版本、备份、Schema Migration、模拟失败
- **Oracle**：安装→Canary→切换→失败→回滚。
- **阈值**：
  - 回滚后 Canonical 可读；
  - 已成功新记录不丢；
  - Extension/Host/Companion 版本不匹配有明确阻断；
  - 回滚时间和步骤有证据；
  - 不依赖手工修改 DB。
- **证据**：Release rehearsal。
- **失败处置**：阻断。

## ACC.x2n.rel.008 — Skill 完整性

- **Blocking**：是
- **关联需求**：REQ.X2N.026
- **环境**：ENV-RELEASE
- **输入**：干净环境
- **Oracle**：按 `SKILL.md` 从安装到 Self-test、Canary、升级、回滚。
- **阈值**：
  - 所有命令可复制执行；
  - 人工输入集中在安装向导；
  - 失败输出最小决策问题；
  - 不要求开发中未声明授权；
  - 诊断/卸载/数据保留行为明确。
- **证据**：Fresh install transcript。
- **失败处置**：阻断交付。

---

# 13. Path Acceptance Matrix

| Path | 输入 | 预期 | Acceptance |
|---|---|---|---|
| Walking | 六平台各一条合成当前页；真实 Canary 逐平台独立授权 | Canonical→Markdown→Notion Mock→清理 | capture.*, data.*, media.*, md.*, notion.* |
| Golden | 每个启用平台/能力独立私有 Manifest | 完整、幂等、分类、双 Sink | xhs.*, dy.*, bili.*, ks.*, wb.*, tb.*, rel.006 |
| Black | 过期登录/DOM 改版/空响应 | Block/Anomaly，无删除 | batch.001、ops.001 |
| Abuse | 恶意 URL/媒体/Prompt/OCR | 阻断、无执行/泄露 | media.003/004、ai.004 |
| Degraded | 无 FFmpeg/模型/Notion | 元数据继续，状态明确 | ai.*, notion.003、ops.004 |
| Recovery | 每阶段 Kill | Resume，无重复/丢失 | ext.002、xhs.003、ops.001、rel.005 |
| Migration | 旧 DB/Notion Schema | Dry-run、备份、回滚 | data.004、notion.001、rel.007 |
| Deletion | 空扫描/关系取消/用户删除 | 候选 Tombstone＋确认 | batch.001、ops.003 |

---

# 14. 压力与混沌矩阵

| Test ID | 故障/压力 | 注入点 | Oracle | Blocking |
|---|---|---|---|---:|
| CH-001 | Extension reload ×100 | 任务进行中 | UI重连、任务不丢 | 是 |
| CH-002 | Companion Kill | 每状态转换前后 | 幂等 Resume | 是 |
| CH-003 | Browser close | 批量滚动中 | Checkpoint、Blocked/Resume | 是 |
| CH-004 | Notion 429 | Outbox | Retry-After | 是 |
| CH-005 | Notion 529/断网 | Outbox | Local完成、最终一致 | 是 |
| CH-006 | Success-before-receipt Kill | Notion | Reconcile，不重复 Page | 是 |
| CH-007 | Disk full | DB/Markdown/Temp | 无半提交、可恢复 | 是 |
| CH-008 | SQLite busy/corrupt copy | DB | Backoff/restore | 是 |
| CH-009 | FFmpeg hang | Media | Timeout、清理、降级 | 是 |
| CH-010 | Oversize/corrupt media | Downloader | Policy block | 是 |
| CH-011 | Cleaner race | Temp | Active Lease 不误删 | 是 |
| CH-012 | Provider timeout/429 | ASR/OCR/Vision | pending/retry/budget | 是 |
| CH-013 | Cookie expired | Adapter | 无历史删除 | 是 |
| CH-014 | DOM 0 items | Adapter | anomaly | 是 |
| CH-015 | Upstream schema drift | Douyin | Contract fail/old Pin | 是 |
| CH-016 | Duplicate messages ×100 | IPC/Outbox | 0 duplicate effect | 是 |
| CH-017 | Malicious prompt/OCR | Model | 0 tool/secret/config | 是 |
| CH-018 | Clock skew | Retry/Lease | 不提前删除/重试风暴 | 是 |
| PERF-001 | 1000 metadata | Pipeline | 近线性，无丢失 | 是 |
| PERF-002 | 10k rebuild | Markdown | 完整、稳定 Hash | 是 |
| PERF-003 | 50 images/item | Media | Frame/Image budget | 是 |
| PERF-004 | 120min video | Media/ASR | 分块/预算/可取消 | 否，能力声明限定 |
| PERF-005 | 100 capture burst | IPC | 0 duplicate/loss | 是 |

---

# 15. 模型互审策略

不同模型互审的目的不是用“多数投票”证明真相，而是暴露相关性盲点。

## 15.1 Review Layers

1. Rule Baseline；
2. Primary Model；
3. Optional Secondary Model；
4. Human Gold；
5. Error Taxonomy。

## 15.2 必须报告

- 两模型一致且都错；
- 两模型不一致；
- 与规则不一致；
- 对长/短、平台、语言、分类的分层；
- 共同失败模式；
- 选择最终裁决的理由。

## 15.3 禁止

- 无 Human Gold 时以多数票宣称准确；
- 使用同一模型不同温度当作独立审查；
- 只展示平均分；
- 隐藏低覆盖类别；
- 用“置信度高”替代校准证据。

---

# 16. Traceability Matrix

| Requirement | Tasks | Tests/Acceptance | Evidence | Deliverable |
|---|---|---|---|---|
| REQ.X2N.001 | foundation.004, skeleton.001/002/006–009, uxops.003 | ext.001/002/004 | E2E trace | Extension |
| REQ.X2N.002 | foundation.002/004 | ext.002/003 | Contract/Fuzz | Native Host |
| REQ.X2N.003 | skeleton.001/002/006–009/004 | capture.001–006, rel.006 | Observation diff | Current Capture |
| REQ.X2N.004 | adapters.001/002/005 | xhs.001/003, batch.001 | XHS manifest | XHS Favorites |
| REQ.X2N.005 | adapters.001/003/005 | xhs.002/003, batch.001 | XHS manifest | XHS Likes |
| REQ.X2N.006 | discovery.004/005, adapters.004/005 | dy.001/003, batch.001 | Upstream contract | Douyin Favorites |
| REQ.X2N.007 | discovery.004/005, adapters.004/005 | dy.002/003, batch.001 | Upstream contract | Douyin Likes |
| REQ.X2N.008 | foundation.002/003, skeleton.004 | data.001/003 | Schema/trace | Canonical DB |
| REQ.X2N.009 | foundation.003, adapters.005, uxops.004 | data.002/004, ops.001 | Idempotency/recovery | Orchestrator |
| REQ.X2N.010 | skeleton.003, multimodal.001, uxops.005 | media.001–004 | Scanner/lease | Media Pipeline |
| REQ.X2N.011 | multimodal.002 | ai.001/007 | ASR eval | Transcript |
| REQ.X2N.012 | multimodal.003 | ai.002/007 | OCR eval | OCR |
| REQ.X2N.013 | multimodal.003 | ai.003/007 | Vision eval | Vision |
| REQ.X2N.014 | multimodal.004 | ai.004/007 | Fusion/redteam | Search/Summary |
| REQ.X2N.015 | multimodal.005, uxops.002/003 | ai.005, md.002 | Taxonomy audit | Categories |
| REQ.X2N.016 | multimodal.005, uxops.003 | ai.005/006 | Classification eval | Review |
| REQ.X2N.017 | skeleton.005, uxops.002 | md.001/002 | Render/rebuild | Markdown |
| REQ.X2N.018 | skeleton.005, uxops.001 | notion.001/004 | Schema/view | Notion |
| REQ.X2N.019 | foundation.003, skeleton.005, uxops.001/004 | notion.002/003, ops.001 | Outbox/reconcile | Notion Queue |
| REQ.X2N.020 | foundation.002/003, skeleton.004, uxops.004 | data.003, ops.002 | Trace/log | Evidence |
| REQ.X2N.021 | discovery.003, foundation.001/004/005, assurance.003 | gov.002, ext.003/004, media.003, rel.003 | Scan/SARIF | Security |
| REQ.X2N.022 | foundation.003, uxops.003/004 | ops.001/002/004, rel.005 | Health/chaos | Operations |
| REQ.X2N.023 | discovery.005, foundation.005, assurance.005 | data.004, rel.005/007 | Release rehearsal | Safe Release |
| REQ.X2N.024 | discovery.004/005 | gov.003 | Dependency/License/zero-runtime scan | Restricted Upstream Isolation |
| REQ.X2N.025 | uxops.005 | media.002, ops.003 | lifecycle report | Data Control |
| REQ.X2N.026 | foundation.001, assurance.005 | ops.004, rel.008 | install transcript | Skill |
| REQ.X2N.027 | discovery.004/005, foundation.005, assurance.003 | gov.003, media.003/004, rel.003 | SBOM/license/security | Assurance |
| REQ.X2N.028 | foundation.005, assurance.001/002 | rel.001/002 | dual pipeline | Quality Gates |
| REQ.X2N.029 | discovery.005, skeleton.006, adapters.006/005 | capture.003, bili.001/002, batch.001 | Policy/capability/completeness | Bilibili |
| REQ.X2N.030 | discovery.005, skeleton.007, adapters.007/005 | capture.004, ks.001/002, batch.001 | OAuth/capability/completeness | Kuaishou |
| REQ.X2N.031 | discovery.005, skeleton.008, adapters.008/005 | capture.005, wb.001/002, batch.001 | Policy/budget/completeness | Weibo |
| REQ.X2N.032 | discovery.005, skeleton.009, adapters.009/005 | capture.006, tb.001/002, batch.001 | OAuth/retention/completeness | Taobao |

> Task IDs在 YAML 中使用完整前缀 `TSK.x2n.*`；表中省略相同前缀以提高可读性。

---

# 17. Evidence Contract

每个证据 JSON 最少字段：

```json
{
  "schema_version": "1.0",
  "acceptance_id": "ACC.x2n.data.002",
  "status": "PASS",
  "run_id": "uuid",
  "task_id": "TSK.x2n.foundation.003",
  "project_version": "v0.0.0.1",
  "git_commit": "sha",
  "environment_id": "ENV-CI-SYNTH",
  "started_at": "RFC3339",
  "finished_at": "RFC3339",
  "command": ["x2n", "verify", "idempotency"],
  "input_manifest_id": "fixture-v1",
  "input_manifest_hash": "sha256",
  "oracle_version": "1.0",
  "metrics": {},
  "thresholds": {},
  "result_summary": {},
  "artifacts": [],
  "redaction": {
    "private_content_included": false,
    "secrets_included": false,
    "cdn_urls_included": false
  }
}
```

## 17.1 Evidence 存放

- Public Repo：只允许小于仓库政策限制的合成/脱敏 Compact Receipt；
- CI Artifact：完整合成日志、SARIF、Trace、Benchmark；
- Private Runtime：真实内容差异、Gold Set、模型输出和账号集成证据；
- Release Bundle：聚合结果、Hash、版本和已知限制，不含私人内容。

## 17.2 Evidence Freshness

以下变化使相关证据失效：

- Adapter Commit；
- Platform DOM Fixture Major；
- Chrome Minimum Version；
- Notion API Version；
- Canonical Schema；
- Model/Prompt；
- Taxonomy Version；
- Security Policy；
- Packaging/OS；
- Feature Flag 默认值。

---

# 18. Release Pass Gate

```yaml
release_gate:
  blocking_acceptance_status: PASS
  traceability_gaps: 0
  dag_cycles: 0
  secret_hits: 0
  private_content_hits: 0
  cdn_url_hits: 0
  unauthorized_deletions: 0
  silent_losses: 0
  duplicate_side_effects: 0
  critical_high_unresolved_vulnerabilities: 0
  unknown_runtime_licenses: 0
  migration_backup_restore: PASS
  rollback_rehearsal: PASS
  owner_alpha_80: PASS
  model_auto_classification:
    enabled_only_if: ACC.x2n.ai.006 == PASS
  vision:
    enabled_only_if: ACC.x2n.ai.003 == PASS
  notion:
    enabled_only_if:
      - ACC.x2n.notion.001 == PASS
      - ACC.x2n.notion.002 == PASS
      - ACC.x2n.notion.003 == PASS
```

任何 Blocking Acceptance Fail 时，Release 状态只能是 `BLOCKED`；不能用总体通过率覆盖关键失败。
