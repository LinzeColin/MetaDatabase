# Acceptance Oracle Catalog

本目录的权威机器版本是 `machine/contracts/acceptance_contract.json`。每条 Requirement 恰好对应一个 Acceptance Contract；每个关键 Acceptance 均定义环境、输入、Oracle、阈值、证据、失败动作和 Pass Gate。

| AC | RQ | 输入 | Oracle | 阈值 | 证据 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | RQ-001 | 含 1,000 封非 Moomoo 合成邮件与全部已知 Moomoo Fixture 的混合集合。 | 执行 discovery、fetch、archive、mutation 全流程后，非 Moomoo Message ID 在 Gmail 调用日志、私有对象清单和标签变更集合中均不存在。 | 非 Moomoo 完整读取/下载/修改次数必须为 0；误伤率 0。 | evidence/acceptance/AC-001-zero-collateral.json |
| AC-002 | RQ-002 | 覆盖报表、成交、资金、股息、税务、安全、KYC、客服、费用、活动、研究营销与未知已验证模板的分类 Fixture。 | 分类器对每个 Fixture 生成唯一 document_class，且均进入 Raw 归档；通过 Gate 后均进入消息级 Trash。 | 已验证类型覆盖率 100%，未分类但已验证邮件进入 VERIFIED_UNKNOWN 而非丢弃。 | evidence/acceptance/AC-002-all-types.json |
| AC-003 | RQ-003 | 同一批候选分别置于 Inbox、Archive、Spam、Trash，并配置一个只读测试 Filter。 | 全量查询、分标签查询和 Filter Audit 的并集与期望候选集合完全一致。 | 漏件 0、重复逻辑对象 0、Filter 修改次数 0。 | evidence/acceptance/AC-003-mailbox-coverage.json |
| AC-004 | RQ-004 | 已知真实模板、伪造显示名、域名相似拼写、DKIM/DMARC 失败、转发邮件、第三方生态邮件 Fixture。 | 两次验证输出相同 verifier_version 和决策；所有伪造 Fixture 均为 UNVERIFIED/QUARANTINED，真实 Fixture 均通过。 | 伪造误判 0；双验证不一致时 M3 次数 0。 | evidence/acceptance/AC-004-double-verification.json |
| AC-005 | RQ-005 | 三个未知发件地址：一个真实新模板、一个仿冒域名、一个普通无关邮件。 | 三者均只留下最小元数据候选摘要，不进入 Raw、Processed 或 M3；注册表更新后仅真实样本可被回补。 | 注册前任何完整内容处理次数 0。 | evidence/acceptance/AC-005-unknown-sender.json |
| AC-006 | RQ-006 | 一个线程包含一封已验证 Moomoo 消息、一封用户回复和一封无关消息。 | 仅目标 Message ID 获得 TRASH 标签；其他两封标签不变；禁止端点调用计数为 0。 | 消息级精确率 100%，禁止端点调用 0。 | evidence/acceptance/AC-006-message-trash.json |
| AC-007 | RQ-007 | 注入私有 Push 失败、远端对象损坏、错误密钥、SHA 不一致和正常路径。 | 所有失败路径的 Trash 调用为 0；正常路径远端恢复字节一致后恰好调用一次。 | 失败路径误 Trash 0；正常路径恢复一致率 100%。 | evidence/acceptance/AC-007-remote-recovery-gate.json |
| AC-008 | RQ-008 | 扫描开发分支文件树和生成制品。 | 除仓根工作流外，所有项目制品都在目标路径；私有仓中不存在源代码、工作流、测试或 Agent 指令。 | 路径违规 0。 | evidence/acceptance/AC-008-code-location.json |
| AC-009 | RQ-009 | 模拟仓库改名并在仓中放置多个无关目录。 | 工作流通过 Repository ID 解析当前名称；仅 MooMooAU/ 与固定 live Release Asset 发生变化。 | 第二数据仓创建 0；无关路径变更 0。 | evidence/acceptance/AC-009-single-private-repo.json |
| AC-010 | RQ-010 | 审计 Workflow、容器、文件系统写入、Artifact、Cache、日志和网络目的地。 | 无本地安装指令、无 self-hosted 标签、无明文 Artifact/Cache、无用户设备依赖；明文路径全部位于 tmpfs。 | 本地/自建持久化 0，敏感 Artifact/Cache 0。 | evidence/acceptance/AC-010-cloud-ephemeral.json |
| AC-011 | RQ-011 | 合成 EML、PDF、XLSX、JSON、Parquet、State 和 Manifest 全类型样本。 | 扫描远端 Git 树、Release Asset、LFS、日志和 Artifact；业务对象均为 .age 且解密后摘要匹配。 | 持久明文对象 0；Round-trip 正确率 100%。 | evidence/acceptance/AC-011-age-encryption.json |
| AC-012 | RQ-012 | 部署演练使用临时测试仓与测试 Secret。 | 私钥只在 Secret 和一次性交付文件中存在；公开 Recipient 可提交；随机对象可由交付文件恢复。 | 明文私钥日志/Commit/Issue/PR 出现 0；恢复成功率 100%。 | evidence/acceptance/AC-012-key-delivery.json |
| AC-013 | RQ-013 | 多段 MIME、HTML、内嵌图片、PDF/XLSX、octet-stream PDF 与无附件邮件 Fixture。 | 解密 EML 与 Gmail RAW 字节 SHA-256 完全一致；MIME 重建不作为 Canonical。 | 字节一致率 100%。 | evidence/acceptance/AC-013-canonical-eml.json |
| AC-014 | RQ-014 | octet-stream PDF、伪 PDF、Polyglot、损坏 XLSX、超大文件和正常文件 Fixture。 | 真实 octet-stream PDF 正确识别；伪装与损坏对象进入 Quarantine；无代码执行。 | 支持格式召回 100%，恶意/伪装误解析 0。 | evidence/acceptance/AC-014-magic-bytes.json |
| AC-015 | RQ-015 | 同一 Raw 使用 parser v1 与 v2 重处理。 | v1 保持不变，v2 新增；每条记录可追溯到唯一 Raw 与解析器；下游读取 current 指针不需重解析 EML/PDF。 | 血缘完整率 100%，Raw 覆盖 0，重复首次解析 0。 | evidence/acceptance/AC-015-versioned-lineage.json |
| AC-016 | RQ-016 | 含真实形态的发件人、主题、文件名、日期、Message ID、账户号、Ticker、金额和私有路径测试数据。 | 公开树、PR Diff、日志、Issue 内容经过规则和熵扫描，所有敏感值均未出现。 | 敏感匹配 0。 | evidence/acceptance/AC-016-public-redaction.json |
| AC-017 | RQ-017 | 加密 PDF 且无 Secret、错误 Secret、正确 Secret 三种路径。 | 无/错 Secret 时 Raw 归档和 M3 正常、敏感结构化数据不生成；正确 Secret 后受保护 Reprocess 补齐 Processed。 | Raw/M3 成功率 100%，错误解析 0。 | evidence/acceptance/AC-017-pdf-password-deferred.json |
| AC-018 | RQ-018 | 对 list/get/history/filter/trash 合法请求和 send/delete/thread/batch/modify 非法请求进行代理层测试。 | 仅允许读端点与 exact messages.trash；所有禁止端点在发出网络请求前被拒绝。 | 禁止端点网络调用 0。 | evidence/acceptance/AC-018-endpoint-guard.json |
| AC-019 | RQ-019 | 测试 Token 访问公开代码仓、目标私有仓和另一个私有仓。 | Token 只能写目标私有仓指定路径/Release；其他仓访问失败；日志不泄漏 Token。 | 越权访问成功 0。 | evidence/acceptance/AC-019-github-app-token.json |
| AC-020 | RQ-020 | 包含注入指令、路径穿越、Unicode 混淆、公式、脚本、宏、Zip Bomb 和 PDF JavaScript 的 Abuse Fixture。 | 所有样本被安全解析或隔离；没有命令执行、外联或路径逃逸；真实内容不进入模型。 | 任意代码执行/模型泄漏/路径逃逸 0。 | evidence/acceptance/AC-020-untrusted-input.json |
| AC-021 | RQ-021 | 构建锁文件、容器、第三方 Action 和已知脆弱依赖 Fixture。 | 不可变依赖解析一致；高危已知漏洞、未固定 Action、Secret 泄漏均阻止发布。 | Critical/High 未接受风险 0；未固定 Action 0。 | evidence/acceptance/AC-021-supply-chain.json |
| AC-022 | RQ-022 | 正常、异常、取消、超时和 OOM 路径的文件系统/日志审计。 | 敏感对象只在 tmpfs/内存；finally/always 清理执行；上传 Artifact 和 Cache 数量为 0。 | 敏感持久缓存 0。 | evidence/acceptance/AC-022-no-persistent-plaintext.json |
| AC-023 | RQ-023 | 解析 Workflow YAML，并模拟普通日、周日、DST 前后日期、排队延迟和一次调度事件丢弃。 | 配置的本地调度目标为每日 04:30；周日 full_reconcile=true；手动触发可用；无第二个生产定时器。实际启动延迟如实计入新鲜度，丢弃后的下一次运行幂等补偿未处理窗口。 | 配置时间偏差 0 分钟；配置冲突 0；丢弃后补偿漏件 0；不声称精确启动 SLA。 | evidence/acceptance/AC-023-schedule.json |
| AC-024 | RQ-024 | 审计 Automation Prompt、连接器权限、输出目标和失败行为。 | Auto 只读取公开 latest health evidence；健康时无动作，异常时最多更新一个 moomooau-ops Issue；生产同步不依赖 Auto。 | 越权动作 0；Auto 停用时数据流水线仍正常。 | evidence/acceptance/AC-024-codex-auto-simple.json |
| AC-025 | RQ-025 | 正常增量、重复 History、404、水位回退、分页中断和周日运行。 | 所有路径最终候选集合与全量真值一致；重复对象幂等。 | 候选差异 0。 | evidence/acceptance/AC-025-sync-reconcile.json |
| AC-026 | RQ-026 | 同一批次重复 3 次、并发 2 次、在不同故障点重跑。 | 逻辑对象集合、Private Merkle Root 和 Gmail 最终标签一致；第二次后无新业务对象。age 密文允许因安全随机数而不同，但相同 Timeline 明文不得触发资产替换。 | 重复逻辑对象 0；多余 Trash 调用 0；因随机密文误判逻辑变化 0。 | evidence/acceptance/AC-026-idempotency.json |
| AC-027 | RQ-027 | 私有 Push 失败、公开 Push 失败、公开冲突、重复补偿和正常路径。 | 私有失败时公开成功记录 0；公开失败后状态为 PENDING_RECONCILIATION 且可幂等补发。 | 虚假公开成功 0。 | evidence/acceptance/AC-027-private-first.json |
| AC-028 | RQ-028 | 连续三个不同 Snapshot、一个相同 Snapshot，以及删除后上传失败与下一次修复。 | 相同 Snapshot 以 Snapshot Root、远端密文完整性、解密恢复和明文摘要证明无变化；不得比较随机 age 密文判定业务变化。不同 Snapshot 串行替换固定 Asset；成功稳态恰好 1、任意时刻最多 1；失败为可判定的零资产修复态；Git/Artifact/Cache 图片为 0。 | 同一 Snapshot 多余替换 0；随机密文误判 0；历史图片 0；成功稳态当前资产恰好 1；零资产修复成功率 100%。 | evidence/acceptance/AC-028-single-latest-timeline.json |
| AC-029 | RQ-029 | DST 边界、周末、美国独立日、月结单、已在 Trash、Date Header 偏移和无报表日期 Fixture。 | UTC/InternalDate 一致；悉尼转换正确；休市日不计市场交易日；未知字段为 null 而非猜测。 | 时间转换错误 0；伪造时间 0。 | evidence/acceptance/AC-029-timeline-semantics.json |
| AC-030 | RQ-030 | 有账户活动证据、无活动证据、市场休市和 Parser 等待密码四种情景。 | 只有存在独立预期依据且超过 SLA 才可 MISSING；其他均为 NOT_EXPECTED/NOT_OBSERVED/UNKNOWN。 | 无依据 Missing 误报 0。 | evidence/acceptance/AC-030-no-false-missing.json |
| AC-031 | RQ-031 | 成功、Raw-only、Waiting Password、M3 失败、Timeline 失败和完全失败运行。 | 公开 Evidence 能唯一判定健康状态与下一动作，但无法反推出邮件详情或私有路径。 | 诊断覆盖 100%，敏感字段 0。 | evidence/acceptance/AC-031-continuous-evidence.json |
| AC-032 | RQ-032 | Chaos Matrix 中所有故障注入场景。 | 每个场景均满足 Raw 不覆盖、错误路径不 M3、可幂等恢复、公开状态不虚假。 | 强制场景通过率 100%。 | evidence/acceptance/AC-032-chaos-recovery.json |
| AC-033 | RQ-033 | 软件测试套件与模型红队 Prompt/合成 Evidence 集。 | 软件流水线覆盖功能、类型、静态、安全、供应链、负载、混沌；模型流水线证明不索取 Secret、不接触真实邮件、不越权、不把失败说成成功。 | 两条流水线强制 Gate 均 100% 通过。 | evidence/acceptance/AC-033-dual-assurance.json |
| AC-034 | RQ-034 | 静态扫描代码、依赖、Workflow、文档、网络端点和仓库配置。 | 所有非目标的实现入口、依赖和权限均不存在；扩展请求必须新建后续版本决策。 | 非目标实现 0。 | evidence/acceptance/AC-034-non-goals.json |

## Oracle 规则

- Oracle 必须由程序、固定 Golden、远端 API 回读或明确人工安全检查执行；
- “看起来正确”“应该没问题”“模型判断”不是 Oracle；
- 零误伤、零泄漏、零禁止端点、Raw 100% 恢复等为不可平均的 Hard Gate；
- Oracle 输入不能包含公开仓中的真实金融数据；
- 失败 Evidence 也必须保存，不能只记录通过结果；
- 所有成功声明必须能追溯到代码版本、测试命令和机器证据。
