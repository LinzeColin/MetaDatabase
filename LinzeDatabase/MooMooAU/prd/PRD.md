# MooMooAU Archive 产品需求文档（PRD）

## 1. 产品摘要

Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.

该系统把 Gmail 中所有经确定性验证的 Moomoo AU 入站邮件作为一个可审计数据产品处理：完整 Raw 和敏感 Processed 在临时云端环境中先 age 加密，再写入唯一私有 GitHub 数据仓；公开 MetaDatabase 只保存代码、Schema 和脱敏 Evidence；远端恢复验证通过后，系统只把精确目标消息移入 Trash。用户日常只使用 Codex 开发线程，不安装本地脚本，不管理服务器，也不依赖复杂 Codex Automation。

## 2. 问题与证据

### 问题

1. Moomoo 会发送日/月结单、税务、股息、费用、安全、KYC、活动等多种邮件，分散在 Inbox、Trash、Spam 和归档位置。
2. Gmail 邮件和附件若只手工保存，难以形成完整 Raw、血缘、重复检测和跨项目复用。
3. Moomoo PDF 可能加密，附件 MIME 甚至可能是 `application/octet-stream`，简单脚本会漏件或解析错误。
4. 用户不接受本地常驻程序、自建服务器、重复手工下载、额外数据仓或复杂治理。
5. 自动移动邮件到 Trash 是破坏性动作，必须证明只命中 Moomoo、远端可恢复，并且只能按单封消息执行。

### 已有 Baseline

- 自动归档、远端恢复、结构化复用、公开 Evidence 和单一最新 Timeline 当前均未形成统一系统。
- 真实样本已证明 Moomoo 正式 PDF 可能以通用二进制 MIME 发送。
- 真实 Moomoo 邮件可位于 Trash；因此 `includeSpamTrash=true` 是硬需求。
- Moomoo PDF 密码当前可能未知，不能让密码阻塞完整 Raw 保存和 M3。

## 3. 用户与价值

### 主要用户

用户本人：只希望通过 Codex 开发线程解决问题，不接触本地脚本、服务器、Secrets 维护或例行操作。

### 下游用户

MetaDatabase 内经授权的项目：直接消费版本化加密 Processed 数据，通过血缘追溯 Raw，而不重新解析 Gmail/PDF。

### 价值

- 完整、可恢复的 Moomoo 邮件证据链；
- 明确的交易/报表/税务数据来源和解析版本；
- 跨项目复用，降低重复首次解析成本；
- 用户电脑零负担；
- 自动清理 Gmail 中全部已验证 Moomoo 邮件，同时零误伤其他邮件；
- 最新 Timeline 直观显示报表标称日期、悉尼到达时间与延迟。

## 4. 战略目标与 OKR

### Objective 1：零误伤地建立完整 Moomoo 数据库

- KR1：非 Moomoo 完整读取、附件下载和标签修改次数为 0。
- KR2：每周 Full Reconciliation 对已验证候选的差异为 0。
- KR3：Raw 远端恢复字节一致率 100%。

### Objective 2：让所有敏感数据可复用但不公开

- KR1：持久化 Raw/敏感 Processed 明文为 0。
- KR2：公开敏感泄漏为 0。
- KR3：Processed 血缘完整率 100%，下游重复首次解析为 0。

### Objective 3：把破坏性操作变成可证明的安全状态机

- KR1：失败路径 Trash 调用为 0。
- KR2：仅调用消息级 `users.messages.trash`，禁止端点调用为 0。
- KR3：M3 Canary 观察期内误伤和不可恢复事件为 0。

### Objective 4：长期运行简单、低成本、可自愈

- KR1：GA 后滚动 90 天正常例行人工操作为 0。
- KR2：数据新鲜度 P95 ≤24 小时。
- KR3：强制 Chaos/Recovery 演练通过率 100%。

## 5. 范围

### 范围内

- 所有经 verified sender + 身份验证对齐 + Moomoo AU 业务指纹双重验证的入站邮件；
- Inbox、All Mail、Spam、Trash 和 Filters 只读审计；
- Canonical RFC EML、附件、分类、结构化报表、血缘、私有状态和最新 Timeline；
- Raw/Processed age 加密；
- M3：远端恢复后精确消息 Trash；
- 公开 Schema、桶化 Inventory、脱敏 Evidence；
- GitHub Actions 以 04:30 Sydney 为时区感知调度目标；流水线语义确定且可幂等补偿，不声明平台精确启动 SLA；
- Codex 开发线程维护代码；简单 Codex Automation 被动看公开健康证据。

### 非目标

- Moomoo Document Portal/H2；
- 交易、下单、融资融券、期权或任何券商 API；
- Sent、Drafts；
- 永久删除、Thread Trash、Batch Delete；
- 本地脚本、launchd、cron、Windows Task Scheduler、自建服务器；
- 第二私有仓；
- Timeline 历史图片；
- 将真实邮件、附件、PDF 密码或 age 私钥提供给模型。

## 6. 产品模块

| 模块 | 职责 | 核心 Gate |
|---|---|---|
| Discovery | 全标签消息级候选、History 和 Full Reconcile、Filter Audit | 候选差异 0 |
| Verification | 版本化 Sender Registry、认证对齐、业务指纹、双重验证 | 误判 0 |
| Raw Archive | Gmail RAW EML、附件、哈希、age、远端私有提交 | 字节恢复 100% |
| Processing | 分类、JSON/Parquet、血缘、密码等待、Parser Blue-Green | 错误结构化 0 |
| M3 | 私有远端恢复 Gate、消息级 Trash、Mutation Budget | 失败路径 Trash 0 |
| Timeline | internalDate、Sydney、美国交易日延迟、单一 live Asset | 历史图片 0、最新 1 |
| Public Evidence | Schema、桶化状态、Opaque Root、测试和恢复结论 | 公开敏感值 0 |
| Operations | 04:30 Workflow、周日对账、开发线程、简单 Auto | Auto 故障不影响数据面 |

## 7. 关键业务流

### Golden Path

`发现 → 第一次验证 → 获取 Gmail RAW → 计算摘要 → 安全拆附件 → Processed/等待密码 → age 加密 → 私有远端提交 → 远端重取解密比对 → 第二次验证 → messages.trash → 确认 TRASH → 单 Timeline 串行替换/修复 → 公开脱敏 Evidence`

### Black Path

未知发件人、认证失败、业务指纹不匹配、损坏附件：不读取完整未知内容或保留加密 Raw（取决于验证阶段），不 M3，不生成可信 Processed，输出最小脱敏状态。

### Abuse Path

Prompt Injection、路径穿越、宏、PDF JavaScript、CSV 公式、Zip Bomb、伪造 Moomoo：不得执行、外联、进入模型或越界写入。

### Degraded Path

PDF 密码缺失、Parser 不支持、GitHub 公开 Push 失败、Timeline 渲染失败：Raw 归档继续；M3 仅依赖完整 Raw 远端恢复与显式 Processed 延迟状态；公开 Evidence 可补偿。

### Recovery Path

History 404 → Full Reconcile；私有 Commit 成功公开失败 → 补偿；错误 Parser → current 指针回退；错误 Secret → Raw 保留、等待；密文损坏 → 禁止 M3、从 Gmail 原件重取。

## 8. 需求索引

| Requirement | 标题 | 模块 | 优先级 | Acceptance |
| --- | --- | --- | --- | --- |
| RQ-001 | 对象零误伤边界 | scope | P0 | AC-001 |
| RQ-002 | 全部已验证邮件类型覆盖 | scope | P0 | AC-002 |
| RQ-003 | 全邮箱位置覆盖 | discovery | P0 | AC-003 |
| RQ-004 | 发件人确定性双重验证 | classification | P0 | AC-004 |
| RQ-005 | 新发件人安全默认 | classification | P0 | AC-005 |
| RQ-006 | 消息级 M3 | gmail-mutation | P0 | AC-006 |
| RQ-007 | M3 远端恢复 Gate | gmail-mutation | P0 | AC-007 |
| RQ-008 | 单一公开代码位置 | repository | P0 | AC-008 |
| RQ-009 | 单一私有数据仓 | repository | P0 | AC-009 |
| RQ-010 | 云端临时执行 | runtime | P0 | AC-010 |
| RQ-011 | 全部敏感数据 age 加密 | encryption | P0 | AC-011 |
| RQ-012 | 恢复钥匙一次性交付 | encryption | P0 | AC-012 |
| RQ-013 | Canonical Raw 完整邮件 | data | P0 | AC-013 |
| RQ-014 | 附件 Magic Bytes 识别 | data | P0 | AC-014 |
| RQ-015 | Processed 版本化与血缘 | data | P0 | AC-015 |
| RQ-016 | 公开面严格脱敏 | privacy | P0 | AC-016 |
| RQ-017 | PDF 密码未知不阻塞 Raw/M3 | processing | P0 | AC-017 |
| RQ-018 | 单一 Gmail OAuth 与端点守卫 | identity | P0 | AC-018 |
| RQ-019 | 私有仓短时最小权限 | identity | P0 | AC-019 |
| RQ-020 | 不可信内容隔离 | security | P0 | AC-020 |
| RQ-021 | 供应链可复现与治理 | security | P0 | AC-021 |
| RQ-022 | 明文零持久缓存 | runtime | P0 | AC-022 |
| RQ-023 | 04:30 悉尼时区运行 | operations | P0 | AC-023 |
| RQ-024 | Codex 职责简单稳定 | operations | P0 | AC-024 |
| RQ-025 | Gmail History 与全量补偿 | discovery | P0 | AC-025 |
| RQ-026 | 端到端幂等 | reliability | P0 | AC-026 |
| RQ-027 | 私有优先跨仓一致性 | reliability | P0 | AC-027 |
| RQ-028 | 单一最新 Timeline | timeline | P0 | AC-028 |
| RQ-029 | Timeline 时间语义正确 | timeline | P0 | AC-029 |
| RQ-030 | 不误报报表缺失 | timeline | P0 | AC-030 |
| RQ-031 | 公开持续证据 | evidence | P0 | AC-031 |
| RQ-032 | 主动恢复与混沌验证 | reliability | P0 | AC-032 |
| RQ-033 | 双 assurance 流水线 | assurance | P0 | AC-033 |
| RQ-034 | 严格范围与非目标 | scope | P0 | AC-034 |

详细唯一需求和 Oracle 见：

- `machine/contracts/requirements.json`
- `machine/contracts/acceptance_contract.json`
- `machine/contracts/traceability_matrix.csv`

## 9. Baseline 与目标指标

| Metric | 名称 | Baseline | 目标 | 观察周期 |
| --- | --- | --- | --- | --- |
| MET-001 | 非 Moomoo 误伤次数 | 未自动化 | 0 | 每次运行/持续 |
| MET-002 | 已验证 Moomoo Raw 捕获率 | 手工、不可审计 | 100% | 每周 |
| MET-003 | Raw 字节恢复正确率 | 0 | 100% | 每封消息 |
| MET-004 | 错误 M3 次数 | 0 自动操作 | 0 | 每次运行 |
| MET-005 | 公开敏感泄漏 | 无项目 | 0 | 每个 PR/运行 |
| MET-006 | 逻辑重复对象 | 未知 | 0 | 每次运行 |
| MET-007 | 数据新鲜度 | 手动 | P95 ≤ 24h | 滚动 30 天 |
| MET-008 | Timeline 历史图片 | 1 张手工图 | 0 历史、1 最新 | 每次运行 |
| MET-009 | 正常例行人工操作 | 手工下载整理 | GA 后 90 天为 0 | 滚动 90 天 |
| MET-010 | 主动恢复演练通过率 | 0 | 100% | 每次发布与季度 |
| MET-011 | 本地设备资源使用 | 潜在手工下载 | 0 | 持续 |
| MET-012 | 重复首次解析 | 跨项目潜在重复 | 0 | 每个下游集成 |

## 10. 约束与容量

- GitHub 是唯一允许的持久数据平台；只使用一个私有数据仓。
- 私有仓所有业务对象在 Git/LFS/Release 持久化前加密。
- `timeline-latest.png.age` 只在固定 live Release 中存在一个，不进入 Git 历史。
- 容量 Green：LFS <70%、`.git` <5GB；Yellow：70–85% 或 5–8GB；Red：≥85% 或 ≥8GB，停止回填和非必要衍生数据。
- GitHub-hosted Runner 底层物理擦除由平台负责；本项目可验证的是无用户侧持久化、无项目控制范围内云端持久明文。

## 11. 成本收益与证伪

成本收益采用区间而非伪精确金额：当前邮件量低时，直接节省时间可能有限；随着历史数据、邮件类型和 MetaDatabase 下游项目增加，避免重复解析、完整证据链和自动清理的收益提高。最大成本变量是 OAuth/密钥一次性配置、Parser 模板变化、Git/LFS 容量、依赖补丁和恢复演练。

证伪实验：

1. Beta 仅 Raw，观察是否真正消除手工归档且没有误读其他邮件；
2. M3 Mutation Budget=1，证明远端恢复和消息级精确性；
3. 下游消费者读取 Processed，比较重复解析资源；
4. 90 天运维统计验证是否接近零例行人工操作；
5. 若连续 90 天维护成本显著高于收益，保留 Raw、暂停 Processed/Timeline。

## 12. 发布与成功定义

Walking Skeleton → Alpha 合成 → Beta Raw-only → M3 Canary → Parser/Timeline Blue-Green → GA。任何强制 Acceptance、Security、Model、Chaos 或 Recovery Gate 不通过均不得升级。

GA 成功定义：全部 34 个 AC 通过；零误伤、零泄漏、零逻辑重复、候选差异 0、Raw 恢复 100%、Timeline 仅一张、用户电脑零运行、Auto 停用不影响生产。
