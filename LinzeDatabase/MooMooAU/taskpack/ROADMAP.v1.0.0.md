# MooMooAU Archive Roadmap v1.0.0

## Pursuing Goal

Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.

## 固定发布原则

- 用户只通过 Codex 开发线程提出修改、查看状态或要求修复；Codex Automation 是独立、简单、非关键的被动健康检查，用户不需要与其交互。
- 生产数据平面是确定性 GitHub Actions，每日 04:30 `Australia/Sydney`；周日同一次执行增加 Full Reconciliation。
- 每一阶段都必须小批量、可逆、以机器证据通过后才提升 Feature Flag；任何 Kill Criteria 立即降级或停机。
- Raw append-only；Processed 版本化；公开面只含脱敏 Evidence；M3 在远端恢复验证后才可执行。

## Stage 0 — 契约冻结与开发入口（预计 1–2 个开发日）

**目标：** Codex 开发线程准确导入本任务包，不发生范围漂移。

交付：Canonical Facts、双平面七文件、34 条唯一需求、34 个 Acceptance Contract、无环 Task DAG、追踪矩阵、一次性部署清单。

Pass Gate：任务包验证器全绿；04:30、单一私有仓、消息级 Trash、单一 Timeline 等不变量无冲突。

## Stage 1 — Walking Skeleton 与公共代码骨架（预计 2–4 个开发日）

**目标：** 不接触真实 Gmail，用合成邮件跑通 Raw → age → 私有测试远端 → 恢复 → 公开 Evidence。

交付：项目骨架、合成 Fixture 工厂、Schema、基础 CI、无 Secret 的端到端 Skeleton。

Pass Gate：合成 Raw 字节往返 100%；公开敏感值 0；无本地/自建运行依赖。

## Stage 2 — 身份、加密与供应链（预计 2–4 个开发日）

**目标：** 先把权限、密钥和供应链做对，再接真实数据。

交付：Gmail endpoint guard、短时 GitHub App Token、Repository ID 改名兼容、age 流式加密、Recovery Key 一次性交付机制、SBOM 与固定依赖。

Pass Gate：禁止 Gmail 端点网络调用 0；私钥不进入 Git/日志；跨仓权限只覆盖目标私有仓。

## Stage 3 — Gmail 发现与 Canonical Raw（预计 3–5 个开发日）

**目标：** 全标签发现 Moomoo 候选，同时绝不读取或修改其他邮件。

交付：Inbox/All Mail/Spam/Trash 扫描、Filters 只读审计、History+Full Reconcile、verified sender 注册表、双重验证、完整 RFC EML Raw、附件安全分类。

Pass Gate：非 Moomoo 完整读取/下载/修改为 0；已验证候选差异为 0；Raw Round-trip 100%。

## Stage 4 — Processed 数据产品（预计 4–8 个开发日）

**目标：** 形成 MetaDatabase 下游可直接消费的加密 JSON/Parquet，不重复首次解析。

交付：邮件全类型分类、Document Envelope、Daily/Monthly/Contract Note/FY Summary Parser、WAITING_FOR_PDF_PASSWORD、Blue-Green Parser、公开 Schema/Inventory/Evidence。

Pass Gate：血缘完整 100%；错误密码不生成错误数据；公开敏感值 0；不访问 Moomoo Portal。

## Stage 5 — M3 与单一最新 Timeline（预计 3–5 个开发日）

**目标：** 远端可恢复后精确移动单封消息到 Trash，并只保留一张最新加密 Timeline。

交付：远端恢复 Gate、messages.trash、Mutation Budget、Timeline Event、Sydney/DST 与美国交易日口径、固定 live Release Asset、04:30 Workflow。

Pass Gate：线程内其他消息标签不变；失败路径 Trash 调用 0；Release Asset 恰好 1；Git/Artifact/Cache 历史图片 0。

## Stage 6 — 安全、模型、压力与混沌（预计 4–7 个开发日）

**目标：** 在上线前主动制造故障、攻击和极限负载，证明系统不会误伤且能恢复。

交付：软件正确性与安全流水线、Codex 能力与安全流水线、Fuzz/Property/Load、Prompt Injection 与文件攻击红队、429/5xx/冲突/损坏/取消混沌演练、不同模型互审。

Pass Gate：全部强制 Chaos/Recovery 场景通过；真实数据不进入模型；所有 Kill Criteria 演练可触发和恢复。

## Stage 7 — Alpha / Beta / Canary / GA（建议最少 21–30 天观察）

**Alpha：** 合成数据，所有生产 Feature Flag 关闭。

**Beta：** 少量真实已验证邮件，Raw-only，不执行 M3、Parser 或 Timeline。

**M3 Canary：** Mutation Budget=1，逐封远端恢复后 Trash，观察至少 7 天。

**Parser/Timeline Blue-Green：** 并行比较 14 天，只保留一张 live Timeline。

**GA：** 连续满足零误伤、零公开泄漏、零逻辑重复、Full Reconcile 差异 0、恢复 100% 后，启用每日 04:30 全流程。

## 长期运行节奏

| 频率 | 确定性 GitHub Actions | Codex 开发线程 / Auto |
|---|---|---|
| 每日 04:30 Sydney | 增量发现、归档、处理、M3、更新单一 Timeline | Auto 仅被动读取上一份公开健康证据；正常无动作，异常最多更新一个 `moomooau-ops` Issue |
| 每周日 04:30 Sydney | 同一任务增加 Full Reconciliation | 开发线程按 Issue 需要修复，不依赖 Auto |
| 每次发布 | 软件、安全、模型、负载、混沌和恢复 Gate | 开发线程审查证据并合并 |
| 每季度 | Recovery Key 随机恢复演练、容量复核 | 开发线程处理异常或依赖升级 |

## 最终完成定义

1. 所有 34 个 Acceptance Contract 有可执行 Oracle、证据和 Pass Gate。
2. Task DAG 无循环，每个 Stage/Phase 直接子项不超过 5。
3. 用户电脑和自建服务器零运行、零持久化、零缓存。
4. 只处理确定性验证的 Moomoo 入站邮件，其他邮件误伤为 0。
5. 所有敏感 Raw/Processed 在 GitHub 持久化前 age 加密。
6. 只有一个私有数据仓和一张最新加密 Timeline。
7. M3 只在远端恢复成功后调用 exact `users.messages.trash`。
8. 用户只需使用 Codex 开发线程；Auto 可失效而不影响生产数据流水线。
