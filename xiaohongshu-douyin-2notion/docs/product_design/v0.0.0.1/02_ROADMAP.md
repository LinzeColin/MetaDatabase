---
artifact: ROADMAP
project: xiaohongshu-douyin-2notion
project_token: x2n
version: v0.0.0.1
status: FINAL_PRODUCT_DESIGN_BASELINE
owner_change_event: CE-X2N-20260719-S00-P01
planning_unit: stage-phase-task
schedule_type: dependency-and-effort-range
calendar_commitment: none
---

# `xiaohongshu-douyin-2notion` Roadmap

## 1. Roadmap 总览

```text
Stage 0  Governance / Evidence / Baseline
   ↓ G0
Stage 1  Foundation / Contracts / Local Runtime
   ↓ G1
Stage 2  Walking Skeleton：两平台当前页闭环
   ↓ G2
Stage 3  Personal Likes/Favorites Batch Adapters
   ↓ G3
Stage 4  Multimodal / Taxonomy / Classification
   ↓ G4
Stage 5  Markdown / Notion / Review / Operations
   ↓ G5
Stage 6  Dual Assurance / Chaos / Owner Alpha
   ↓ G6
Optional Beta：OVH Control Plane、跨 OS 包装、扩展平台
```

## 1.1 状态与默认方案

| 项目 | 状态 |
|---|---|
| Product Design | 已定版 |
| Dev Taskpack | 已生成，等待 Owner 启动 Codex Dev |
| 架构 | Chrome Side Panel + Native Messaging + Local Companion/WebUI |
| 小红书 | Clean-room Adapter |
| 抖音 | Wrapped `douyin-downloader` Adapter |
| MediaCrawler | External Research Adapter，默认关闭 |
| Canonical | SQLite |
| Sinks | Markdown + Notion |
| 公开仓库 | 允许代码；禁止真实运行数据 |
| OVH VPS | Alpha 禁用 |
| Alpha 工程量区间 | 约 `280–600` 工程小时；取决于平台稳定性、目标 OS 和模型策略 |
| Walking Skeleton | 约 `40–90` 工程小时 |
| 日历承诺 | 无；必须以 Gate 和证据推进，不能用日期替代验收 |

工时口径：Stage 区间合计的机器基线为 `288–600h`，是考虑相关风险与排程后的组合规划包络；每个 Task 的 `high` 是该任务单独遇到风险时的上界，不能直接相加。工时只用于规划，不是 Acceptance；每个 Phase 完成后用实际工时校准，超出包络须记录 Change Event。

## 1.2 里程碑

| Milestone | 定义 | 必须证据 |
|---|---|---|
| M0 — Contract Ready | 项目注册、事实、范围、License、Threat Model 和 Owner Input Pack 就绪 | Governance receipts、ADR、Dependency Registry |
| M1 — Walking Skeleton | 两平台各一条当前页完成 Canonical→Markdown→Notion，媒体清理 | E2E Record、DB/Markdown/Notion Receipt、CDN Scan |
| M2 — Dual-platform Batch | 小红书/抖音点赞和收藏可 Canary、Checkpoint、Resume | 80 条对账、重复/丢失报告 |
| M3 — Governed Multimodal | ASR/OCR/Vision/Fusion＋一级分类＋复核 | Gold Set、System Card、模型评测 |
| M4 — Assured Alpha | 双流水线、混沌、安全、回滚和 Owner Alpha 通过 | Final Acceptance Bundle |
| M5 — Value Review | 连续两个月收益/维护数据 | Go/Pivot/Kill Review |
| M6 — Optional Beta | 仅在价值成立后评估控制平面和跨 OS | 新 PRD/ADR，不自动进入 |

---

# 2. Stage 0 — Governance、证据与 Baseline

**目标**：在写产品代码前消除仓库边界、许可证、运行数据、Owner 输入和不可逆风险。

**努力区间**：`18–35h`

## Phase 0.1 — 项目注册与 Canonical Governance

| Task | 输出 | Gate |
|---|---|---|
| `TSK.x2n.discovery.001` 仓库基线 | 读取根/项目 AGENTS、现有 Skill 结构、目录生命周期；生成 Changed Scope | 无越界路径、无运行数据写入 |
| `TSK.x2n.discovery.002` 项目注册 | `project.yaml`/roadmap/events 计划、ID Registry、Task Record 目录 | ID 唯一、单一事实源 |
| `TSK.x2n.discovery.003` Artifact Policy | 允许/禁止路径、尺寸、Receipt 和 CI Artifact 边界 | Public/Private Contract 可机器验证 |

Phase 0.1 的固定路由：母仓库 `LinzeColin/MetaDatabase`、子项目 `xiaohongshu-douyin-2notion/`。Runtime 与所有 Adapter 下载共用仓库外 `X2N_DATA_ROOT`；真实绝对路径仅存在于 Owner 私有 marker，旧目录不自动迁移、链接或删除。

## Phase 0.2 — 上游、License 与 Evidence

| Task | 输出 | Gate |
|---|---|---|
| `TSK.x2n.discovery.004` 上游 Pin | xhs exporter、douyin downloader、MediaCrawler 的 Commit/License/Schema/能力登记 | 所有依赖状态不是隐式 `latest` |

## Phase 0.3 — Owner Input Pack（Phase 0.5 非独立准备域）

机器 DAG 未给 Phase 0.3 分配独立 Task；以下输入由 `TSK.x2n.discovery.005` 在 Phase 0.5 一次性收口，不得把本节单独标记为已执行的 Run。

一次性收集，不在开发中零散追问：

- 自动探测主 OS、Chrome 版本、CPU/GPU/RAM/磁盘；
- 记录收藏规模和首次同步范围；
- 建立 5–20 个一级分类、定义、别名和正反例；
- 配置 Notion Parent Page/Integration；
- 选择本地/云 Provider 和预算；
- 准备 40 条 Smoke Gold Set，后续扩至 100 条；
- 在专用 Chrome Profile 手工登录；
- 接受媒体成功即删、失败 24h 默认。

输出：`owner_input_contract.local.json`，只保存在 Runtime Root；Repo 只保存 Schema 和合成示例。

## Phase 0.4 — Security/Privacy/Threat Model（Phase 0.5 非独立准备域）

机器 DAG 未给 Phase 0.4 分配独立 Task；以下工作由 `TSK.x2n.discovery.005` 在 Phase 0.5 验收。

- DFD、STRIDE、Data Classification；
- Secret、Private Content、Ephemeral Media 的位置和生命周期；
- Native Messaging allowlist；
- SSRF、恶意媒体、Prompt Injection、XSS、Path Traversal；
- Public Release Threat；
- Incident/Rotation/History Rewrite Runbook。

## Phase 0.5 — G0 Closure：Owner Input、License、Threat Model 与 ADR

| Task | 输出 | Gate |
|---|---|---|
| `TSK.x2n.discovery.005` G0 Closure | Owner Input Schema、THIRD_PARTY/License Gate、Threat Model、ADR-001–010、Stop/Kill Register | 未核验依赖不复制；阻断风险为 0；G0 证据完整 |

Stage 0 的唯一可执行 Phase 顺序是 `PH.X2N.0.1 → PH.X2N.0.2 → PH.X2N.0.5`。0.3/0.4 是 0.5 的准备域，不是可单独声明 PASS 的 Run；这保持机器 DAG 的 35 个 Task 与 ID 不变。

必须定版：

- ADR-001 Local-first Hybrid；
- ADR-002 SQLite Canonical / Sink 可重建；
- ADR-003 URL/CDN Zero Persistence；
- ADR-004 User-owned Primary Taxonomy；
- ADR-005 XHS Clean-room / Douyin Wrapped / MediaCrawler External；
- ADR-006 Notion Outbox；
- ADR-007 Alpha VPS Disabled；
- ADR-008 Runtime Root Outside Repo；
- ADR-009 Model Provider-neutral；
- ADR-010 Canonical Markdown Stable Path＋Generated Category Index。

### Gate G0 — Ready to Build

必须同时通过：

- Governance 和 Task IDs 注册；
- LICENSE/NOTICE 可执行；
- Runtime/Public Repo Boundary 可机器验证；
- Threat Model 完成；
- 合成 Fixture 可用于无真实账号开发；
- Owner 未提供项均有可逆默认；
- 没有需要绕过平台控制的设计。

**Stop Condition**：许可证冲突、需要私密数据进入 Public Repo、需要绕过访问控制、无可回滚数据设计。

---

# 3. Stage 1 — Foundation、Contracts 与 Local Runtime

**目标**：建立可独立测试的项目骨架、契约、数据库、IPC 和双流水线基础。

**努力区间**：`35–65h`

## Phase 1.1 — Skill/Monorepo Scaffold

建议目录：

```text
xiaohongshu-douyin-2notion/
├── SKILL.md
├── agents/openai.yaml
├── apps/
│   ├── extension/
│   └── companion/
├── packages/
│   ├── contracts/
│   └── test-fixtures/
├── references/
├── scripts/
├── tests/
└── THIRD_PARTY_NOTICES.md
```

禁止提交：`dist/`、`node_modules/`、虚拟环境、Runtime DB、Profile、媒体、私人 Markdown 和完整日志。

## Phase 1.2 — Versioned Contracts

- Native Messaging Request/Response；
- Adapter Input/Output；
- Canonical Entity；
- Artifact/Model Invocation；
- Taxonomy/Classification；
- Sink Outbox/Receipt；
- Error Taxonomy；
- Health/Diagnostics；
- Config/Feature Flag。

Contract 以 JSON Schema/Pydantic/TypeScript 类型生成或交叉验证。

## Phase 1.3 — Runtime Root 与 Canonical DB

- 使用 Owner 预先配置的 `X2N_DATA_ROOT`，不得回退到上游或 OS 默认下载/应用数据目录；
- SQLite WAL；
- Alembic/等价迁移；
- 唯一约束、Foreign Key；
- Transaction/Outbox；
- Backup/Restore；
- DB integrity check；
- 合成数据 seed。

## Phase 1.4 — Extension / Native Host Skeleton

- MV3 Side Panel；
- 最小权限；
- Native Host Manifest 精确 Extension ID；
- IPC Schema 校验；
- Companion Health；
- Service Worker 重启恢复 UI 状态；
- CSP 和输出净化。

## Phase 1.5 — CI Baseline

软件流水线初版：

- format/lint/type；
- unit/contract；
- migration test；
- extension build；
- synthetic E2E；
- secret/private/CDN scan；
- dependency/license/SBOM；
- changed-scope governance。

模型流水线占位：

- Fixture Registry；
- Dataset Version；
- Evaluation Runner；
- System Card 模板；
- Prompt Injection Suite。

### Gate G1 — Foundation

- 全部 Contract 可验证；
- DB 迁移正向/回滚通过；
- Extension 可连接 Native Host；
- Service Worker 重启不丢后端任务；
- Repo 扫描 0 Secret/Private/CDN；
- CI 在无真实账号和无真实 Secret 下通过。

---

# 4. Stage 2 — Walking Skeleton

**目标**：用最小闭环证明架构，而不是先做大规模采集。

**努力区间**：`35–65h`

## Phase 2.1 — 小红书当前页

- 只支持明确详情页；
- 提取 ID、规范 URL、标题、作者、正文、类型；
- 选择关系/分类；
- Fixture＋真实 Canary 各验证；
- 页面变化返回结构化错误，不猜测。

## Phase 2.2 — 抖音当前页

- 同等 Contract；
- 优先页面事实，必要时调用 Adapter；
- 短链先解析为规范允许路径；
- 过滤 Query/Tracking/Token；
- 与小红书共享 Canonical，不共享脆弱解析器。

## Phase 2.3 — Temp Media / URL Scrubber

- 受控媒体 Lease；
- HTTPS＋Host allowlist；
- Redirect/SSRF 防护；
- MIME/大小/时长；
- 内容 Hash；
- 成功清理；
- 失败 24h 清理；
- 持久层 CDN Scanner。

## Phase 2.4 — Canonical Processing

- `content`＋`user_relation`；
- Observation；
- Artifact 状态；
- Run/Evidence；
- 重跑幂等；
- 原子 Transaction；
- 错误分层。

## Phase 2.5 — Minimal Markdown + Notion

- 固定 ID 文件；
- 生成一个分类 Index；
- Notion Items/Categories 最小 Schema；
- Outbox/Receipt；
- 429 Mock；
- Notion 关闭时本地继续。

### Gate G2 — Walking Skeleton

输入：

- 小红书当前页 1 条图文＋1 条视频；
- 抖音当前页 1 条图集＋1 条视频；
- 合成恶意 URL/Prompt/大文件。

通过：

- 4 条均生成唯一 Canonical；
- 第二次运行 0 重复；
- Markdown/Notion 可追溯；
- 0 CDN URL；
- 成功媒体 0 残留；
- Kill Extension/Companion 后可恢复；
- Notion 故障不影响本地结果。

**Pivot 条件**：如果 Native Messaging/Local Companion 的安装复杂度无法接受，可改为 Local WebUI＋浏览器 Bookmarklet/Extension Trigger；Canonical Contract 不变。

---

# 5. Stage 3 — Personal Likes/Favorites Batch Adapters

**目标**：实现两平台个人关系批量同步，同时保持当前页降级路径。

**努力区间**：`50–110h`

## Phase 3.1 — 专用 Browser Profile 与会话健康

- 用户手工登录；
- 不导出 Cookie；
- Profile 路径在 Runtime Root；
- Session Health；
- 验证码/过期状态；
- 最小用户动作提示；
- Adapter 互斥和低频控制。

## Phase 3.2 — 小红书收藏 Adapter

- Clean-room 行为实现；
- 收藏夹/专辑关系；
- 受控滚动/分页；
- 每批 Durable Checkpoint；
- 页面布局 Fixture；
- 20 条 Canary；
- 空列表保护。

## Phase 3.3 — 小红书点赞 Adapter

- 与收藏共享内容，不复制；
- `liked` Relation；
- 点赞默认 Inbox/更高自动分类阈值；
- 增量和完整扫描模式；
- 同步范围预览；
- 取消关系只生成候选 Tombstone。

## Phase 3.4 — 抖音 Wrapped Adapter

- Pin `ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7` 起步；
- 子进程/REST Contract；
- likes、favorites、收藏夹；
- 输出 Schema 验证；
- Upstream Error Mapping；
- Health；
- Version Notice；
- 升级 Shadow Test。

## Phase 3.5 — Relation Reconciliation

- `content` 与 `user_relation` 分离；
- 多收藏夹、多关系；
- 首次/最后见到；
- Full Scan Completeness Receipt；
- 双成功扫描后 Tombstone Candidate；
- Alpha 人工确认；
- 绝不因空结果自动删除。

### Gate G3 — Batch

测试样本：

```text
小红书 收藏 20
小红书 点赞 20
抖音 收藏 20
抖音 点赞 20
```

通过：

- 页面/平台可见样本与 Observation ID 对账；
- 必填字段完整率 `>=95%`；
- 静默丢失 `0`；
- 二次同步新增重复 `0`；
- 新增一条只处理新增/变化；
- 登录过期不改变历史关系；
- 中途 Kill 可从 Checkpoint 继续；
- 不出现 CDN URL、Cookie 或 Profile 路径。

**Pivot 条件**：任一平台批量 Adapter 两轮修复后仍低于 `90%` 已识别条目成功率，则关闭其批量 Flag，保留当前页保存。

---

# 6. Stage 4 — Multimodal、Taxonomy 与 Classification

**目标**：把原始媒体转为可检索文本并受用户分类约束。

**努力区间**：`55–120h`

## Phase 4.1 — Media Preprocessor

- FFprobe；
- 音频提取；
- 场景检测；
- 关键帧；
- 相似帧去重；
- 大小/时长/帧数预算；
- 子进程超时和资源限制。

## Phase 4.2 — ASR Provider

- Local Provider；
- Optional Cloud Provider；
- 文本/时间段/语言；
- CER Runner；
- Prompt/Domain Hint；
- 成本和缓存；
- 失败降级。

## Phase 4.3 — OCR / Vision Providers

- OCR 图片/关键帧；
- Vision 描述代表帧；
- 输入文件而非 CDN URL；
- Provider Capability Discovery；
- 输出质量；
- 安全/不支持内容；
- 缓存与预算。

## Phase 4.4 — Multimodal Fusion

- 模态缺失容忍；
- 摘要、观点、实体、搜索文本；
- Prompt Template Version；
- 引用 Artifact ID；
- 内容/指令隔离；
- Injection Red Team；
- 不允许工具调用。

## Phase 4.5 — Taxonomy / Classification / Review

- Category Registry；
- 正反例；
- 规则＋模型路由；
- Primary Category＋Tags；
- 证据和校准；
- Suggestion-only；
- 复核 Revision；
- Gold Set 40→100；
- 模型漂移报告。

### Gate G4 — Governed Multimodal

- ASR/OCR 分层 Gold Set 报告；
- 清晰普通话 ASR 中位 CER 初始 `<=15%`，或明确降级；
- 清晰 OCR 中位 CER初始 `<=12%`，或明确降级；
- 自动归档高置信度精度 `>=90%`，否则 Suggestion-only；
- AI 新建一级分类 `0`；
- Prompt Injection 不得改变配置/路径/Secret；
- 模态失败不阻塞 Canonical；
- 处理后媒体清理符合 TTL；
- 新模型重跑生成新 Artifact，不覆盖旧证据。

---

# 7. Stage 5 — Sinks、Review 与 Operations

**目标**：让结果可浏览、可复核、可运维、可重建。

**努力区间**：`40–90h`

## Phase 5.1 — Notion Production Sink

- Current Data Source Contract；
- Items/Categories；
- View 创建和更新；
- User Field Preservation；
- `content_key` Upsert；
- 长文本 Chunk；
- 429/529/Retry-After；
- Dead Letter；
- Reconciliation；
- Schema Migration。

## Phase 5.2 — Markdown Library

- Stable Canonical Path；
- Frontmatter Schema；
- Transcript/OCR/Vision Sections；
- Category `INDEX.md`；
- Atomic Write；
- Full Rebuild；
- Link Integrity；
- 分类变化不移动 Canonical。

## Phase 5.3 — Local WebUI / Review

- Queue/Health；
- Taxonomy；
- Low-confidence Review；
- Failed Jobs；
- Artifact Detail；
- Notion Status；
- Model Budget；
- Data Lifecycle；
- Diagnostics Export。

## Phase 5.4 — Observability / Recovery

- Redacted structured logs；
- Metrics；
- Health；
- Run Timeline；
- Checkpoint Resume；
- Outbox Replay；
- DB Integrity；
- Sink Rebuild；
- Recovery Drill。

## Phase 5.5 — Export / Delete / Retention

- Canonical JSONL；
- Markdown Export；
- Data Deletion；
- Relation Tombstone；
- Backup；
- Temp/Log TTL；
- Runtime Wipe；
- Notion Delete 的明确非默认行为。

### Gate G5 — Operable Product

- Notion 故障矩阵通过；
- Markdown 可全量重建且 Hash 稳定；
- 分类视图和 Notion View 一致；
- 低置信度可在一个流程完成复核；
- 脱敏诊断包不含私人正文/Secret/CDN；
- 数据清理可预览、可取消、可审计；
- 恢复后 Sink 与 Canonical 对账一致。

---

# 8. Stage 6 — Assurance、Chaos 与 Owner Alpha

**目标**：主动制造故障，验证正确性、安全、模型能力和发布恢复。

**努力区间**：`55–115h`

## Phase 6.1 — 软件正确性流水线

- Lint/Type；
- Unit；
- Contract；
- Adapter Fixture；
- DB Migration；
- E2E；
- Property-based Idempotency；
- Cross-platform Smoke；
- Coverage 和 Mutation 的风险重点策略。

## Phase 6.2 — 模型能力与安全流水线

- Dataset Registry；
- ASR/OCR；
- Fusion Human Rating；
- Classification Precision/Coverage/F1；
- Prompt Injection；
- Adversarial OCR；
- Language/Noise/Empty Media；
- Cost/Latency；
- Model/Prompt Drift；
- System Card。

## Phase 6.3 — Security / Supply Chain

- SAST；
- Secret Scan；
- Dependency/OSV；
- SBOM；
- License；
- CSP；
- SSRF；
- Path Traversal；
- Malicious Media；
- Release Artifact Scan；
- Upstream Pin Verification。

## Phase 6.4 — Performance / Chaos / Recovery

主动注入：

- Companion Kill；
- Extension Reload；
- Chrome Close；
- SQLite Busy/WAL Recovery；
- Disk Full；
- Temp Cleaner Race；
- FFmpeg Missing/Hang；
- Provider Timeout/429；
- Notion 429/529/Schema Error；
- Network Offline；
- Cookie Expired；
- DOM Selector Drift；
- Upstream Output Schema Change；
- Duplicate Events；
- Oversized/Corrupt Media；
- Prompt Injection；
- Clock Skew；
- Process Restart Loop。

## Phase 6.5 — Canary / Blue-Green / Alpha

1. 合成 Fixture；
2. 两平台各一条真实当前页；
3. 20 条 Canary；
4. 80 条 Acceptance；
5. Shadow 新版本；
6. Backup；
7. Green Install；
8. Schema Migration Dry-run；
9. Owner Alpha；
10. Rollback Drill；
11. Final Acceptance Bundle；
12. Release Tag `v0.0.0.1-alpha.1` 或项目约定等价标签。

### Gate G6 — Assured Alpha

- `04_ACCEPTANCE_CONTRACT_TRACEABILITY.md` 所有 Blocking Acceptance 通过；
- 双流水线通过；
- Task DAG 完成且证据齐全；
- 0 Secret/Private/CDN Leak；
- 0 未授权删除；
- 0 重复副作用；
- Owner Sign-off；
- 回滚演练成功；
- 已知限制进入 System Card 和 Release Notes；
- Release Artifact 不包含 Runtime 数据。

---

# 9. Optional Beta Roadmap（非当前授权）

## Beta A — 跨 OS 包装

进入条件：

- Owner Alpha 连续稳定 30 天；
- 核心价值成立；
- 有第二目标 OS 的真实需求和测试设备。

内容：

- Windows/macOS/Linux Native Host 安装器；
- Signed Package；
- 自动升级；
- OS-specific Keychain 和权限；
- Cross-platform Recovery。

## Beta B — OVH VPS-1 Control Plane

进入条件：

- 明确需要远程触发；
- Threat Model、成本和隐私复核通过；
- Alpha 本地 Agent 已稳定；
- Owner 另行授权。

允许：

- 脱敏 Agent 在线状态；
- 请求同步；
- 版本清单；
- 告警 Webhook；
- 加密最小 Receipt。

禁止：

- 平台 Cookie/Profile；
- 私人内容/Transcript/OCR；
- 原始媒体；
- Notion/Model Key；
- VPS 直接采集；
- 远程任意命令。

## Beta C — 新来源

通过相同 Adapter Contract 增加其他平台，必须独立 PRD、License 和 Acceptance；不得降低现有两平台质量。

---

# 10. 决策树

```text
批量 Adapter 稳定？
├── 是 → 继续全量同步
└── 否
    ├── 当前页保存稳定？→ Pivot 为 Save Current / Import Queue
    └── 否 → Kill 对应平台能力

自动分类达高精度？
├── 是 → 高置信度自动归档
└── 否 → Suggestion-only

Vision 有可测增益？
├── 是 → 保留
└── 否 → 关闭 Vision，保留 ASR/OCR

Notion 可靠且有价值？
├── 是 → 保留 Sink
└── 否 → Markdown-only

月净收益为正？
├── 是 → 维护/迭代
└── 连续两月为负 → Pivot/Kill Review
```

---

# 11. Critical Path

```text
Governance + License
→ Contracts
→ Runtime DB
→ Native Messaging
→ Current-page Skeleton
→ Media Lease/Scrubber
→ Canonical/Outbox
→ Batch Adapters
→ Multimodal
→ Taxonomy/Review
→ Notion/Markdown Production
→ Dual Assurance
→ Owner Alpha
```

非 Critical Path：

- MediaCrawler Adapter；
- VPS；
- Chrome Web Store；
- 多平台；
- 永久媒体；
- 高级 Dashboard。

---

# 12. Owner Touchpoints

为了避免开发被频繁 Block，只保留四个 Owner Touchpoint：

| Touchpoint | 时点 | 最小决策 |
|---|---|---|
| O1 | Stage 0 | 登录、Notion、分类、Provider/预算、保留默认 |
| O2 | G2 | 查看 4 条 Walking Skeleton 结果，确认信息结构 |
| O3 | G4 | 标注/确认 Gold Set 和分类阈值 |
| O4 | G6 | 80 条验收、回滚演练和 Alpha Sign-off |

其他可逆工程决策由任务包预授权；暂停时必须输出：

```text
最小决策问题
现有证据
默认建议
可选项
不决策后果
是否可回滚
```

---

# 13. Roadmap 验收

Roadmap 本身通过条件：

- Stage→Phase→Task 层级清晰；
- 每个 Phase 不超过 5 个主要子任务；
- 所有 Critical Task 在 YAML DAG 中有唯一 ID；
- 依赖无循环；
- 每个 Gate 有输入、Oracle、证据和 Stop Condition；
- P0 需求全部映射到任务；
- Beta 不被误当作 Alpha 授权；
- 工程量是区间，不是伪精确日期；
- Owner 输入集中在开发前；
- Pivot/Kill 路径可执行。
