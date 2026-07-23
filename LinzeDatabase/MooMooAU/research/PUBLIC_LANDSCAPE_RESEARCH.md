# 非用户仓库的 GitHub 与公开网络调研

## 调研范围

本轮只研究公开项目和官方文档，目标是减少从零开发、识别成熟模式和拒绝不符合约束的架构；没有把用户的全仓全项目作为竞品调研对象。

| 来源 | 项目 | 类型 | 可借鉴 |
| --- | --- | --- | --- |
| SRC-001 | GitHub Spec Kit | public_project | 借鉴 Spec → Plan → Tasks → Implement、结构化模板、跨制品一致性检查；不引入其 CLI 作为运行时依赖。 |
| SRC-002 | BMAD Method | public_project | 借鉴 Working Backwards、PRD/PRFAQ、按复杂度自适应、测试架构和多角色互审；不复制多代理运行时。 |
| SRC-003 | Got Your Back (GYB) | public_project | 借鉴 Gmail API 全量/增量备份、RFC 邮件原件保留和恢复思路；拒绝本地持久化与本地 cron。 |
| SRC-004 | Paperless-ngx | public_project | 借鉴邮件规则、processed-mail 去重、未知类型隔离和文档生命周期；不部署常驻服务。 |
| SRC-005 | age | public_project | 采用流式 X25519 Recipient 加密；运行时只需公开 Recipient，恢复身份不写入 Git。 |
| SRC-006 | SOPS | public_project | 借鉴密钥轮换、云 KMS 与加密配置治理；本项目大对象仍直接使用 age，避免引入多余格式层。 |
| SRC-007 | OpenMetadata | public_project | 借鉴目录、所有权、质量和血缘模型；只实现无常驻服务的轻量公开 Inventory/Schema/Evidence。 |
| SRC-008 | DataHub | public_project | 借鉴数据产品、版本化 Schema 和跨项目消费契约；不部署数据库、搜索或消息中间件。 |
| SRC-009 | OpenLineage | public_project | 借鉴输入、运行、输出三元血缘模型和可重放 Run Event；实现精简私有 lineage manifest。 |
| SRC-010 | in-toto | public_project | 借鉴供应链步骤声明、材料/产物摘要和可验证证据；公开面只发布脱敏声明。 |
| SRC-011 | Pandera | public_project | 借鉴 DataFrame/Parquet 字段、类型和统计约束；同时保留 JSON Schema 作为交换契约。 |
| SRC-012 | Gmail messages.list | official_doc | 使用 includeSpamTrash=true，分页遍历消息级候选。 |
| SRC-013 | Gmail message format RAW | official_doc | Canonical Raw 使用完整 RFC 2822/RAW，而非仅附件。 |
| SRC-014 | Gmail sync guide | official_doc | 增量 History 水位失效或 404 时执行 Full Reconciliation。 |
| SRC-015 | Gmail filters.list | official_doc | 只读审计 Filters；不声称标准 API 可直接列出 Blocked Addresses。 |
| SRC-016 | Gmail messages.trash | official_doc | M3 只允许精确消息级 Trash。 |
| SRC-017 | Gmail threads.trash | official_doc | 作为明确禁用接口；线程级会移动线程内所有消息。 |
| SRC-018 | Gmail messages.delete | official_doc | 作为明确禁用的不可逆接口。 |
| SRC-019 | GitHub Actions schedule | official_doc | 使用 IANA timezone 与 04:30 Australia/Sydney；官方允许延迟或丢弃，因此保留 workflow_dispatch、水位补偿和周日对账，不声明精确启动 SLA。 |
| SRC-020 | GitHub App installation token | official_doc | 跨仓写入使用短时、仓库限定 Token，适应私有仓改名。 |
| SRC-021 | GitHub Release assets | official_doc | 固定 live Release 只保留一张 timeline-latest.png.age，避免 Git 历史污染。 |
| SRC-022 | GitHub repository limits | official_doc | 建立仓库/LFS 容量阈值与停止门，拒绝无界增长。 |
| SRC-023 | Codex Automations | official_doc | 仅配置普通、被动、非关键的健康检查；不让 Auto 接触 Gmail、私有数据、Secret 或执行修复。 |
| SRC-024 | Moomoo statement manual | official_doc | 确认 Statement 类型、下载入口与 PDF 密码规则；密码未知时 Raw 仍归档。 |
| SRC-025 | Moomoo Financial Year Summary | official_doc | 作为报表分类和 Processed Schema 的参考，不设计 Portal 自动下载。 |
| SRC-026 | Moomoo ASX statements and contract notes | official_doc | 覆盖 Daily/Monthly/Contract Note 生态分类，但只有邮件中实际存在的内容进入范围。 |
| SRC-027 | Moomoo AU support contact | official_doc | 建立初始 verified sender 候选和人工证据源，不能单靠显示名或主题。 |

## 1. 规格驱动与任务包

### GitHub Spec Kit

成熟点：Spec → Plan → Tasks → Implement、模板、质量清单、跨制品分析和多 Agent 集成。适合借鉴“Intent 先于实现”和机器可读制品链。

超越点：本 Skill 增加唯一 Acceptance、可执行 Oracle、Evidence、Kill Criteria、双 assurance 流水线、Stage/Phase/Task 子项上限、Stop Condition 和 Safe Release，不只生成 spec/plan/tasks。

### BMAD Method

成熟点：PRFAQ/PRD、分析/架构/测试多角色、按复杂度自适应和完整生命周期。适合 Working Backwards 和不同模型互审。

超越点：避免把多 Agent 角色变成生产运行依赖；所有关键事实集中到 Canonical Facts，防角色输出互相冲突。

## 2. Gmail 备份与文档处理

### Got Your Back

成熟点：Gmail API、完整邮件备份、全量/增量、恢复导向。

不直接采用：面向本地计算机和本地持久目录，与用户零本地要求冲突。

借鉴后改造：完整 RFC EML、History/Full Sync、幂等；运行环境改为 GitHub-hosted 临时 Runner，持久数据先 age 加密。

### Paperless-ngx

成熟点：邮件规则、文档分类、processed mail 去重、未知邮件隔离、文档生命周期。

不直接采用：需要常驻服务、数据库、文档目录和运维，超出单用户项目成本。

借鉴后改造：Sender Registry、VERIFIED_UNKNOWN、Quarantine、状态机；以 Git/加密对象和公开 Schema 替代常驻平台。

## 3. 加密与 Secret

### age

成熟点：简单、流式、现代 X25519 Recipient，适合大对象在持久化前加密。

采用：直接 age 加密 Raw/Processed；任务包不含真实 Identity；部署临时生成并一次性交付 Recovery Key。

### SOPS

成熟点：结构化配置、KMS/age、多接收者和轮换治理。

不作为大对象主格式：EML/PDF/Parquet 直接 age 更简单；SOPS 思路用于 Secret/Key Epoch 和配置治理。

## 4. 数据目录、Schema 和血缘

### OpenMetadata / DataHub

成熟点：Dataset、Owner、Schema、Quality、Lineage、Version、Domain。

不直接部署：常驻服务、搜索、数据库和消息基础设施对本项目过重。

借鉴后改造：公开轻量 Dataset Catalog、Schema Version、Quality Status、Opaque Evidence Root；私有精确 Inventory 和 Lineage 加密。

### OpenLineage

成熟点：Job/Run/Input/Output 事件模型和可重放血缘。

采用：每次批次记录 source、run、parser、output 和版本；公开只暴露脱敏结果。

### Pandera

成熟点：对 Parquet/DataFrame 字段、类型、范围和统计做可执行验证。

采用：Processed 分析表用 Pandera，交换与公开契约用 JSON Schema，形成双层数据质量。

## 5. 供应链证据

### in-toto

成熟点：材料、步骤、产物和摘要声明。

采用：构建、测试、私有提交、恢复和公开发布形成可追踪 Evidence；真实数据摘要只存在私有 Manifest，公开用 Opaque Root。

## 6. 官方 API 约束的设计影响

- Gmail `messages.list` 需显式 `includeSpamTrash=true` 才覆盖 Spam/Trash；
- Canonical Raw 应使用 `format=RAW`；
- History 水位失效必须 Full Sync；
- Filters 可只读列出，但没有独立 Blocked Addresses API；
- `messages.trash` 是消息级，`threads.trash` 会影响线程内所有消息，后者禁用；
- 永久 delete 不可逆，禁用；
- GitHub Actions 支持 IANA timezone，使用 04:30 Australia/Sydney；schedule 可能延迟或丢弃，后续运行必须自动补偿；
- Release Asset 适合固定单一 Timeline，避免 Git 二进制历史；
- Codex Automation 适合简单重复检查，但不应成为金融数据生产控制面。

## 7. 结论

没有一个公开项目同时满足：零误伤 Gmail、云端临时运行、单一私有 GitHub 数据仓、Raw/Processed 全 age、消息级 M3、单一最新 Timeline、公开脱敏 Evidence、Codex 开发线程治理。因此采用“借鉴成熟模式、拒绝常驻/本地/过重平台、实现最小确定性流水线”的组合方案。
