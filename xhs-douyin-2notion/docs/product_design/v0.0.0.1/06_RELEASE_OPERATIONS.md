---
artifact: RELEASE_OPERATIONS
project: xhs-douyin-2notion
project_token: x2n
version: v0.0.0.1
status: FINAL_PRODUCT_DESIGN_BASELINE
owner_change_event: CE-X2N-20260719-S00-P01
release_target: owner-alpha
distribution: local-developer-mode
vps_data_plane: prohibited
---

# `xhs-douyin-2notion` Release、Operations 与 Codex 执行手册

> Scope amendment `CE-X2N-20260719-S00-P05`：终态平台范围为六平台，每个平台/能力独立 Gate；固定“80 条两平台样本”已改为逐能力私有 Manifest，不允许用一个平台的通过外推其他平台。

## 1. 交付边界

本文件定义从 Codex Dev 启动到 Owner Alpha 的安全执行、构建、发布、运维和回滚方式。

### 当前已授权

- Product Design `v0.0.0.1` 定版；
- 双平面七文件任务包交付；
- Roadmap 和机器任务 DAG。
- Stage 0 / Phase 0.1、0.2、0.5 的治理准备、竞品/政策研究、Artifact/Runtime Policy 与仓库外私有数据根契约。

### 当前未授权

- 修改产品代码或进入 Stage 1；
- 使用真实六平台账号或发起平台请求；
- 写入真实 Notion；
- 调用付费模型；
- 发布扩展或安装器；
- 部署 OVH；
- 抓取或处理私人内容。

Owner 启动新的 Codex Dev 线程后，执行者必须重新读取：

1. 仓库根 `AGENTS.md`；
2. `xhs-douyin-2notion/AGENTS.md`；
3. 本任务包七文件；
4. 对应 Task Record；
5. 该 Task 的 Acceptance、依赖、风险、回滚和 Stop Condition。

---

# 2. Codex Dev 启动协议

## 2.1 Pursuing Goal Prompt

> 始终以“个人内容知识治理而非通用爬虫”为边界，以本地 SQLite Canonical Store 为真相源，以 Chrome 为交互面、Local Companion 为执行面，任何实现都不得持久化平台媒体 CDN URL、凭据或原始媒体，不得让 AI 擅自创建一级分类，也不得以牺牲幂等、证据、恢复和公开仓库隐私边界换取功能速度。

## 2.2 单 Phase 执行模板

```yaml
run:
  project: xhs-douyin-2notion
  version: v0.0.0.1
  phase_id: PH.X2N.<stage>.<phase>
  ordered_task_ids: []
  allowed_paths: []
  forbidden_paths: []
  inputs: []
  expected_outputs: []
  dependencies:
    satisfied: []
    unresolved: []
  acceptance_ids: []
  tests: []
  evidence: []
  risks: []
  rollback: []
  stop_conditions: []
  feature_flags: []
  real_data_authorized: false
  external_writes_authorized: false
```

一次运行最多执行一个 Phase，Phase 内 Task 必须严格按 DAG 依赖顺序逐个验收。除非任务明确声明，禁止顺手修改无关项目、数据、文档或工具。每个 Stage 完成后必须先全 Stage Review、修复和重验，才允许上传整个 Stage；Phase 中间不得 push。

## 2.3 开始前 Read-only Gate

```text
git status --short
git rev-parse HEAD
read root/project AGENTS
read taskpack
read Task Record
resolve changed scope
verify dependencies
verify runtime root is outside repo
verify no real secrets are loaded
verify rollback
```

输出一个 compact start receipt。若有未满足依赖但存在安全可逆默认，应使用默认继续；只有 YAML 中的 Mandatory Pause Condition 才暂停。

## 2.4 暂停协议

任何暂停必须输出：

| 字段 | 要求 |
|---|---|
| 最小决策问题 | 一个可以直接选择的具体问题 |
| 证据 | 复现、日志引用、合同冲突或外部限制 |
| 默认建议 | 最安全、最可逆且不扩范围的选项 |
| 备选 | 最多 2 个，说明代价 |
| 不决策后果 | 哪个 Task/Gate 被阻断 |
| 回滚性 | 可逆/不可逆和回滚方法 |
| 需要的 Owner 动作 | 最小一步，不索取 Secret 值 |

禁止用“需要更多信息”作为没有最小问题的暂停理由。

---

# 3. 分支、版本和制品

## 3.1 Version

- Product Design：`v0.0.0.1`
- 开发预发布建议：`v0.0.0.1-alpha.N`
- 修复不改变范围：增加 Alpha Build/Tag；
- PRD/Acceptance/边界改变：提升 Taskpack Patch；
- 破坏性 Contract：提升更高版本并提供迁移。

## 3.2 Branch

建议：

```text
main
codex/xhs-douyin-2notion-<version>-s<stage>-p<phase>
codex/xhs-douyin-2notion-<version>-s<stage>-integration
release/v0.0.0.1-alpha.N
hotfix/<incident-id>
```

Phase 分支只作为本地、可恢复的隔离检查点。Stage 内所有 Phase 完成后，汇入 Stage integration 分支，执行全 Stage Review、修复与重验；只有通过后才可 push 并创建一个整 Stage PR。不得上传中间 Phase 或把未运行的 Gate 包装成 PR 进度。

## 3.3 Commit

Commit 应引用：

- Task ID；
- 主要 Acceptance；
- 变更类型；
- 不包含运行状态或 Secret。

示例：

```text
feat(x2n): add versioned native messaging contract

Task: TSK.x2n.foundation.002
Acceptance: ACC.x2n.ext.003
```

## 3.4 Public Release Artifact Allowlist

允许：

- Extension 源码/构建包；
- Companion 源码/经核验安装包；
- Contracts；
- 合成 Fixture；
- SKILL/文档；
- SBOM；
- THIRD_PARTY_NOTICES；
- Release Notes/System Card；
- 脱敏 compact acceptance receipt。

禁止：

- Runtime DB/WAL/SHM；
- Cookie、Session、Token、Key；
- Browser Profile；
- 真实正文/ASR/OCR/Vision/摘要；
- 原始 JSONL；
- 媒体；
- Notion Export；
- `.env`；
- 本地绝对路径；
- 完整日志；
- Provider Cache；
- MediaCrawler 代码/二进制。

Release 采用 Allowlist 构建，不从工作树“排除几个目录”后整体打包。

---

# 4. Feature Flag 运行策略

| Flag | Dev | Walking | Canary | Alpha |
|---|---:|---:|---:|---:|
| `xhs_current_page` | 合成 | 开 | 开 | 开 |
| `douyin_current_page` | 合成 | 开 | 开 | 开 |
| `xhs_favorites` | 关 | 关 | 20 条 | Gate 后开 |
| `xhs_likes` | 关 | 关 | 20 条 | Gate 后开 |
| `douyin_favorites` | 关 | 关 | 20 条 | Gate 后开 |
| `douyin_likes` | 关 | 关 | 20 条 | Gate 后开 |
| `multimodal_asr` | 合成 | 可选 | Model Gate | Gate 后开 |
| `multimodal_ocr` | 合成 | 可选 | Model Gate | Gate 后开 |
| `multimodal_vision` | 关 | 关 | Shadow | `ACC.x2n.ai.003` 后开 |
| `fusion_summary` | 合成 | 可选 | Shadow | Injection Gate 后开 |
| `auto_classify` | 关 | 关 | Suggestion | `ACC.x2n.ai.006` 后开 |
| `notion_sink` | Mock | 可选 | 小批量 | 三个 Notion Gate 后开 |
| `mediacrawler_adapter` | 关 | 关 | 关 | 关 |
| `retain_local_media` | 关 | 关 | 关 | 关 |
| `physical_delete` | 关 | 关 | 关 | 仅逐次确认 |
| `vps_control_plane` | 关 | 关 | 关 | 关 |

Flag 状态属于配置事实，有版本和证据。默认值不能通过 UI/模型静默改变。

---

# 5. CI/CD：软件正确性流水线

## 5.1 Pull Request Fast Gate

```text
Governance changed-scope
→ Format
→ Lint
→ Type
→ Unit
→ Contract
→ Migration smoke
→ Extension build
→ Synthetic current-page E2E
→ Secret/Private/CDN diff scan
→ Dependency delta/license
```

目标：快速、只读、与 Changed Scope 相称。不得为了速度跳过与变更直接相关的 Blocking Gate。

## 5.2 Full Release Gate

```text
All fast gates
→ DB forward/back/compatibility
→ Adapter full fixtures
→ Native Messaging fuzz
→ Browser E2E
→ Idempotency/property
→ Markdown 10k rebuild
→ Notion mock fault matrix
→ Security/SSRF/media
→ SAST/OSV/SBOM/license
→ Performance
→ Chaos/recovery
→ Model pipeline
→ Artifact allowlist scan
→ Fresh install
→ Rollback rehearsal
```

## 5.3 CI Secret 原则

- Public CI 不使用真实平台账号；
- 不使用 Owner Notion Workspace；
- Provider 测试采用 Mock 或专用无私人内容测试 Key；
- 真实 Canary 只在 Owner Local Runtime；
- CI Secret 即使存在也不能使私人内容可达；
- Fork PR 不获得 Secret。

## 5.4 Flaky Policy

Blocking Test 不能标记 Retry-until-green。若 Flaky：

1. 标记 Release Blocked；
2. 保留失败 Seed/Trace；
3. 修复确定性；
4. 重新运行；
5. 不用通过率掩盖。

---

# 6. 模型能力与安全流水线

## 6.1 Dataset Registry

每个数据集：

```yaml
dataset_id:
version:
purpose:
owner:
visibility: private|synthetic-public
source:
consent:
item_count:
strata:
label_schema:
quality_review:
leakage_checks:
hash:
retention:
```

真实收藏数据集永不进入 Public Repo。公共 CI 使用合成和许可明确的测试内容。

## 6.2 Pipeline

```text
Dataset Contract
→ Leak/Label QA
→ ASR
→ OCR
→ Vision
→ Fusion
→ Classification
→ Calibration
→ Prompt Injection/Abuse
→ Cost/Latency
→ Cross-model disagreement
→ System Card diff
→ Feature gate decision
```

## 6.3 Promote/Degrade

- ASR/OCR 未达 Gate：显示低质量、可替换 Provider，不阻断元数据。
- Vision 未达 Gate：关闭。
- Fusion Injection Fail：关闭 Fusion。
- Classification 未达 Precision：Suggestion-only。
- Cloud Budget/Policy Fail：Cloud off。
- 任一模型能访问工具/Secret/配置：Release Blocked。

## 6.4 模型升级

```text
Pin new snapshot
→ Shadow old/new on same private set
→ Quality/safety/cost diff
→ Human review disagreements
→ Canary
→ Promote with flag
→ Retain prior provider for rollback
```

不在没有同输入对照和 System Card 更新时升级。

---

# 7. Build 与安装

## 7.1 Build Inputs

- Clean source checkout；
- Lock files；
- pinned upstream manifest；
- verified toolchain；
- no Runtime Root；
- no local `.env`；
- reproducible build metadata。

## 7.2 Extension

- MV3；
- strict CSP；
- fixed permissions；
- fixed Extension ID strategy for Native Host；
- source map policy不泄露本机路径；
- dev/release build分离；
- Build Manifest 含 Git SHA、Contract Version。

## 7.3 Companion

- Python env 使用锁文件；
- 不把虚拟环境提交；
- Native Host launcher路径由安装器写入；
- Companion 仅 loopback；
- 使用已由 Owner 配置的 `X2N_DATA_ROOT`；新设备只能在用户确认后创建，不得静默回退到默认路径；
- OS Keychain Capability检查；
- FFmpeg检测而非盲目捆绑；
- local models按需下载到 `X2N_DATA_ROOT/runtime/models/`，不进 Repo/Release；
- 卸载不默认删除私人数据。

## 7.4 Fresh Install Oracle

在干净用户环境：

1. 安装 Companion；
2. 注册 Native Host；
3. 加载 Extension；
4. `x2n doctor`；
5. 合成 Self-test；
6. 打开 Side Panel；
7. 运行 Walking Fixture；
8. 升级；
9. 回滚；
10. 卸载并选择保留/删除 Runtime。

所有步骤可复制执行，错误给出最小修复。

---

# 8. Canary 与 Alpha

## 8.1 Canary 顺序

```text
Synthetic
→ XHS 当前页 1 图文 + 1 视频
→ Douyin 当前页 1 图集 + 1 视频
→ 每平台/关系最多 5 条
→ 总计 20 条
→ 每个启用平台/能力的独立完整验收
```

不得从 0 直接跑全部历史收藏。

## 8.2 Canary 预检

- Backup；
- Runtime 磁盘；
- Profile 登录；
- Adapter Health；
- FFmpeg/Provider；
- Notion Capability；
- Flags；
- Privacy/Cloud Upload；
- 预计条目、媒体时长和成本；
- Stop Button；
- CDN/Secret Scanner；
- Rollback Version。

## 8.3 Canary 通过

- 0 静默丢失；
- 0 重复；
- 0 CDN/Secret；
- 0 未授权删除；
- 每条终态明确；
- 临时媒体清理；
- Owner 可理解分类/错误；
- Notion 和 Markdown可追溯；
- 失败可恢复。

## 8.4 分层 Owner Alpha

每个实际启用的平台/能力必须有独立私有 Manifest；以下是每能力上限 20 条的初始 Canary，不是用总数替代覆盖：

- 小红书收藏 20；
- 小红书点赞 20；
- 抖音收藏 20；
- 抖音点赞 20。
- 哔哩哔哩所选列表 20（独立授权后）；
- 快手所选列表 20（独立授权后）；
- 微博所选列表 20（独立授权和预算后）；
- 淘宝所选列表 20（独立授权后）。

如某关系实际不足 20 条，Owner 记录事实并用所有可用条目＋合成补充，但不得用合成数据声称真实完整性。任何未授权平台保持 `NOT_RUN`，不得为了凑总数启动。

---

# 9. Blue-Green 本地发布

## 9.1 目录

```text
install/
├── versions/
│   ├── v0.0.0.1-alpha.1/
│   └── v0.0.0.1-alpha.2/
├── current -> versions/<green>
└── previous -> versions/<blue>
```

Windows 使用等价 launcher/version registry，不依赖不稳定 Symlink 权限。

## 9.2 切换

1. 安装 Green 到新目录；
2. 不覆盖 Blue；
3. 运行 Contract/Doctor；
4. DB Backup；
5. Migration Dry-run；
6. Green 读取兼容；
7. 20 条 Canary；
8. 切换 `current`；
9. 保留 Blue；
10. 观察；
11. 再清理旧版本。

## 9.3 DB Expand-Migrate-Contract

- Expand：新增可空字段/表；
- Migrate：后台 Backfill；
- Dual Read/Write 如需要；
- Switch；
- 验证；
- Contract 仅在旧版本不再需要时；
- `v0.0.0.1` Alpha 不做无法回滚的 Contract Migration。

## 9.4 Extension/Host 兼容

Extension、Native Host、Companion 都带 Contract Version。若不兼容：

- Side Panel 显示明确版本错误；
- 不提交任务；
- 不尝试猜测字段；
- 提供升级/回滚命令。

---

# 10. 回滚 Runbook

## 10.1 通用回滚

```text
Stop accepting new jobs
→ mark active jobs paused
→ flush durable receipts
→ snapshot DB
→ switch feature flags off
→ switch code to previous version
→ verify DB compatibility
→ run doctor/self-test
→ reconcile outbox
→ resume safe jobs
→ emit rollback evidence
```

## 10.2 Adapter 回滚

- 恢复前一 Pin；
- 清除仅属于 Staging 的输出；
- Canonical 不回滚；
- 重新运行受影响 Observation；
- 禁止用旧 Adapter 的空结果删除关系。

## 10.3 Model 回滚

- 关闭新 Provider/Prompt；
- 恢复旧版本；
- 新 Artifact保留但标记 superseded/invalid；
- 不改写 Owner 已确认分类；
- 按输入 Hash 选择性重跑。

## 10.4 Notion 回滚

- 关闭 Outbox Worker；
- 不删除已创建 Page；
- 恢复旧 Projection；
- Reconcile Mapping；
- 用户字段不回滚；
- Canonical/Markdown继续。

## 10.5 Schema 回滚

- 使用已测试 downgrade或 restore；
- 保留原 DB只读副本；
- 不手工编辑生产 SQLite；
- 验证 Content/Relation/Artifact/Outbox counts和 Hash；
- 若新数据无法被旧版本读取，使用兼容导出/新补丁，不盲目 downgrade。

## 10.6 Security 回滚/Incident

- 立即停止 Release和外部写入；
- 识别 Secret/数据范围；
- 轮换 Token/Cookie/Profile；
- 删除本地暴露制品；
- Git History/Release Asset 清理；
- 通知 Owner；
- 根因和预防；
- 全量重新扫描；
- 新版本前完成 Incident Acceptance。

---

# 11. 常态运维

## 11.1 启动

```text
x2n doctor
→ DB integrity
→ migration compatibility
→ expired media lease cleanup
→ interrupted run recovery
→ outbox lease recovery
→ adapter/provider/sink health
→ side panel status
```

## 11.2 每次同步

- Dry-run/estimate；
- Canary（上游/页面/版本变化后强制）；
- Checkpoint；
- Item counts；
- Error taxonomy；
- Cleanup；
- Outbox；
- Reconciliation；
- Compact run receipt。

## 11.3 每日/每次启动

- Temp Lease；
- Dead Letter；
- Disk；
- DB Backup Policy；
- Upstream version warning；
- Cloud budget；
- Notion queue；
- Security scan summary。

## 11.4 每月

- 实际节省时间；
- 维护时间；
- 新增/复用量；
- 分类修正率；
- Adapter失败；
- 模型成本；
- Gold Set抽样；
- Dependency/License；
- Backup Restore Drill；
- Kill Criteria Review。

## 11.5 上游更新

不自动跟随 `main`：

```text
Detect new upstream
→ read changelog/source/license
→ update candidate pin
→ contract fixtures
→ security/license/SBOM
→ shadow on same inputs
→ canary
→ promote
```

MediaCrawler 即使更新也不进入核心更新流程；它有独立研究工具生命周期。

---

# 12. 监控与告警

## 12.1 本地告警等级

| Level | 示例 | 动作 |
|---|---|---|
| INFO | 同步完成、跳过重复 | UI/Receipt |
| WARNING | 某模态失败、Notion重试、分类低置信 | 不阻塞 Canonical |
| ACTION_REQUIRED | 登录过期、Notion授权、磁盘不足 | 最小用户动作 |
| BLOCKED | Contract/Schema/License不兼容 | 关闭 Feature |
| SECURITY | Secret/CDN泄露、SSRF、Prompt工具行为 | 停止外部写入/Release |
| DATA_INTEGRITY | DB损坏、静默丢失、误删风险 | 停止所有变更，恢复 |

## 12.2 Alert Contract

告警不得包含原始正文、Transcript、URL Query、Secret或 Profile Path。可包含：

- Run ID；
- Error Code；
- Platform；
- Stage；
- Count；
- Safe Action；
- Internal Evidence Ref。

## 12.3 自愈

允许自动：

- 重试可重试网络/429；
- 过期 Outbox Lease恢复；
- Temp Lease清理；
- Worker重启；
- Sink Reconcile；
- Provider降级；
- Feature Flag临时关闭；
- 恢复旧 Pin。

禁止自动：

- 重新登录/验证码；
- 轮换 Secret；
- 物理删除；
- 修改一级分类；
- 上传到新 Provider；
- 扩大 Chrome权限；
- 破坏性迁移；
- VPS启用。

---

# 13. 数据生命周期

## 13.1 Retention

| 数据 | 默认 |
|---|---|
| Canonical Content/Relation | 直到用户删除 |
| Artifacts | 版本化保留，用户可清理旧版 |
| Source Observation | 保留必要 Hash/字段证据，不含 CDN |
| Temp Media 成功 | 立即删除 |
| Temp Media 失败 | 最长 24h |
| Full Private Logs | 短期、可配置、默认最小 |
| Compact Receipt | 长期，小型、脱敏 |
| Browser Profile | 用户控制，不进入普通备份 |
| Secret | Keychain，直到撤销 |
| Backups | 数量/时长由容量策略，默认加密/私有 |
| Notion Projection | 用户控制；本地不从 Notion 自动删除 |

## 13.2 Export

支持：

- Canonical JSONL；
- Markdown Library；
- Taxonomy；
- Model/Processor Manifest；
- Sink Mapping/Receipt；
- 脱敏运行摘要。

导出私人内容只能写入用户选择的本地路径，不进入 Repo。

## 13.3 Delete

- Dry-run；
- 影响清单；
- 可选 Backup；
- 明确关系 vs 内容；
- Owner Confirm；
- Transaction；
- 派生重建；
- Notion动作单独确认；
- Audit；
- 不可恢复时再次确认。

---

# 14. 事故响应

## 14.1 Secret 泄露

1. Stop；
2. 保存不含 Secret 的证据；
3. 识别 Token/Cookie/Key；
4. 撤销/轮换；
5. 删除 Release/Artifact；
6. Git history清理（若进入）；
7. Profile重建；
8. 全范围扫描；
9. 根因；
10. Owner批准恢复。

## 14.2 私人内容进入 Public Repo

- 停止公开分发；
- 删除/历史清理；
- 评估 Fork/Cache/Release；
- 必要时更换仓库；
- 增加 Canary Pattern；
- 不在公开 Issue复制内容。

## 14.3 CDN URL 泄露

虽不一定等同 Secret，但违反核心合同：

- 阻断；
- 定位持久层；
- 删除/重建 Markdown/Notion/日志；
- 更新 Scrubber/Pattern；
- 全量扫描；
- 重新验收 ACC.x2n.media.001。

## 14.4 误删/静默丢失

- 停止同步；
- 保留 DB/日志快照；
- 从 Backup/Observation/平台清单恢复；
- 关闭 Tombstone/Physical Delete；
- 差异报告；
- 修复 State Machine；
- 全量回归；
- Owner确认后恢复。

## 14.5 模型安全

- 关闭相关 Model Flag；
- 保留输入/输出私有证据；
- 检查是否发生工具/Secret/配置影响；
- 轮换受影响 Secret；
- 增加 Red Team；
- 更新 System Card；
- Suggestion-only或停用。

---

# 15. 成本和预算运维

## 15.1 预算控制

```text
monthly_cloud_budget
daily_cloud_budget
max_video_minutes_per_job
max_images_per_item
max_vision_frames
max_model_retries
max_parallel_media_jobs
```

达到预算：

- 不继续云调用；
- 任务状态 `degraded_budget`；
- 保存可用本地结果；
- 可排队等待下周期或 Owner显式一次性提高；
- 不在后台自动购买/升级。

## 15.2 价值复盘

每月：

```text
net_time_saved
= reused_items × (manual_minutes - review_minutes)
- maintenance_minutes
- calibration_minutes
```

连续两个月：

- `net_time_saved <= 0` → Product Pivot/Kill Review；
- Adapter维护 > 节省 → 关闭批量，当前页模式；
- Vision无增益 → 关闭；
- Notion无增益 → Markdown-only；
- 分类复核过重 → 提高阈值/规则优先。

---

# 16. Alpha → Beta → GA

## Alpha

- 单用户；
- Owner主 OS；
- 开发者模式 Extension；
- 本地 Runtime；
- 六平台终态范围；实际启用取决于各自 Policy/Auth/Technical/Canary Gate；
- Media不持久化；
- VPS关闭；
- 功能 Flag；
- 私有 Gold Set；
- Known Limitations明确。

## Beta Entry

- Owner Alpha稳定 30 天；
- 至少两个月价值数据；
- 关键 Adapter维护可接受；
- 0未解决 Security/Data Integrity Incident；
- 第二 OS/VPS/Store有真实需求；
- 新 PRD。

## GA Entry

- 独立法律/平台/隐私复核；
- 跨 OS安装/升级；
- Store披露；
- 支持/事故响应；
- 更长观察；
- 模型和软件双流水线持续；
- 不因“功能完成”自动 GA。

---

# 17. 最终 Release Checklist

## Governance

- [ ] Project/Task/Acceptance ID唯一
- [ ] Changed Scope 合法
- [ ] Human Task Records 完整
- [ ] Canonical facts单一写入者
- [ ] Beta能力未误启用

## Source/Dependencies

- [ ] Upstream pins
- [ ] MIT NOTICE
- [ ] MediaCrawler未 bundled
- [ ] xhs exporter code未未经核验复制
- [ ] SBOM/License通过
- [ ] Unknown runtime license 0

## Security/Privacy

- [ ] Secret 0
- [ ] Private content 0
- [ ] CDN URL 0
- [ ] Browser state 0
- [ ] Local path/username 0
- [ ] CSP/Permissions
- [ ] Native origin allowlist
- [ ] SSRF/media
- [ ] Prompt injection
- [ ] Release allowlist

## Data

- [ ] DB integrity
- [ ] Unique constraints
- [ ] Idempotency
- [ ] Backup/restore
- [ ] Migration/rollback
- [ ] Empty-response deletion protection
- [ ] Temp cleanup
- [ ] Export/delete preview

## Product

- [ ] Walking Skeleton
- [ ] Four relation canaries
- [ ] 80-item Alpha
- [ ] Markdown rebuild
- [ ] Notion reconciliation
- [ ] Taxonomy ownership
- [ ] Review flow
- [ ] Doctor
- [ ] Degraded paths

## Models

- [ ] Dataset registry
- [ ] ASR report
- [ ] OCR report
- [ ] Vision gate/disabled
- [ ] Fusion red team
- [ ] Classification gate/suggestion-only
- [ ] Provider/Prompt provenance
- [ ] Budget
- [ ] System Card

## Reliability

- [ ] Extension restart
- [ ] Companion kill
- [ ] Disk/DB
- [ ] FFmpeg/media
- [ ] Provider
- [ ] Notion 429/529
- [ ] Cookie/DOM/upstream drift
- [ ] Blue-green
- [ ] Rollback

## Owner

- [ ] Real account authorization
- [ ] Notion authorization
- [ ] Cloud upload choice
- [ ] Taxonomy
- [ ] Gold Set
- [ ] 80-item review
- [ ] Known limitations
- [ ] Alpha Sign-off

---

# 18. Final Acceptance Bundle 结构

实现交付时建议生成：

```text
FINAL_ACCEPTANCE_BUNDLE/
├── release_manifest.json
├── governance_receipt.json
├── traceability_report.json
├── software_pipeline_summary.json
├── model_pipeline_summary.json
├── security_supply_chain_summary.json
├── chaos_recovery_summary.json
├── canary_summary.json
├── owner_alpha_summary.json
├── migration_rollback_summary.json
├── system_card.md
├── release_notes.md
└── checksums.sha256
```

公共 Bundle 只含聚合/脱敏结果。真实样本明细保存在 Owner Private Runtime，公共 Bundle通过 Hash和统计引用。

---

# 19. 运行线程防偏移规则

开发线程每次阶段转换前重新确认：

1. 这是不是个人知识治理能力，而非通用爬虫扩张？
2. 是否仍以 Canonical Store 为真相源？
3. 是否可能持久化 CDN URL、Secret、Profile 或媒体？
4. AI 是否越权创建分类或执行动作？
5. 是否可重放、可恢复、可回滚？
6. 是否有唯一 Acceptance 和 Oracle？
7. 是否需要真实 Owner输入，还是可用安全默认继续？
8. 是否将上游内部 Schema泄漏到核心？
9. 是否把 Notion/VPS变成新的单点？
10. 是否为了速度牺牲证据或删除保护？

任一答案违反合同，立即停止当前变更并回到对应 ADR/Task。
