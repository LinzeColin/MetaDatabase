# ABD 客户常见问题（目标合同稿）

内部目标稿：用于冻结关键疑问、证据状态和安全默认，不是上线公告、投资建议或收益承诺。

## FAQ-S01-P02-01｜为什么把月度 30% 作为目标？

**答案：** 这是用来持续检验产品是否值得继续的高难度目标，目标曲线为 `A$300 × 1.3^n`。它不会因为开发完成而自动成立。

**当前证据状态：** 未验证。90天和1000个独立等效影子信号只够评估“可能可行”；只有至少12个完整自然月、现金流调整后的月度几何收益达到30%、证据完整且对账差异为0，才允许标记为“已验证”。

**默认：** 每月如实报告目标差距；目标落后只报告，不放宽证据、价值、时效、数值、风险、安全或来源合同门，也不追损。

**证据：** `machine/facts/canonical_facts.json#/product`、`machine/facts/parameters.json#/target_30pct`、`machine/facts/release_policy.json#/alpha_beta_ga`。

**不成立时：** 满足预注册证伪门就标记“已证伪”并停止把30%作为可行目标；证据不足时保持“未证明”，不得改写成成功。

## FAQ-S01-P02-02｜ABD 会保证收益或保证本金增长吗？

**答案：** 不会。投注结果具有随机性，ABD只做分析和建议，不提交订单；真实收益必须由用户实际执行、现金流和对账证据证明。

**当前证据状态：** 未验证、无保证。本 phase 没有真实订单、真实收益或生产运行证据。

**默认：** 任何缺失、过期、不稳定、未校准、未对账或无法核验的证据都输出“不建议”；绝不把建议、回测、影子结果或目标曲线写成真实收益。

**证据：** `machine/facts/canonical_facts.json#/scope`、`machine/facts/canonical_facts.json#/truth_and_evidence`、`machine/facts/parameters.json#/target_30pct`、`machine/facts/costs.json#/benefit_model`。

**不成立时：** 如果有人声称保证收益、自动下单或已实现真实回报，立即阻断该声明并要求可重放的实际执行与对账证据。

## FAQ-S01-P02-03｜“A$0 新增现金预算”是不是说整个系统免费？

**答案：** 不是。A$0只约束 ABD 0.0.0.1 在既有承诺之外新增的现金支出；A$300是受风险合同约束的本金，不是开发预算。既有OVH、账户成本、人工和机会成本都不能被伪装成零。

**当前证据状态：** 本地合同把新增现金上限冻结为A$0；本 phase 未检查外部账单，也没有产生购买、升级或超额计费承诺。

**默认：** 新增成本只要大于A$0或未知，就阻断对应能力；继续不产生新增现金的本地工作或安全降级，绝不自动购买、升级或启用付费接口。

**证据：** `machine/facts/canonical_facts.json#/product/incremental_cash_budget_aud`、`machine/facts/costs.json#/cost_semantics`、`machine/facts/costs.json#/incremental_cash_gate`。

**不成立时：** 发现任何正新增成本、未知账单风险或免费额度不足时，标记 `INCREMENTAL_CASH_BUDGET_EXCEEDED`，关闭相关路径并保留证据。

## FAQ-S01-P02-04｜“全部可观察市场”是不是每个市场都会给建议？

**答案：** 不是。系统目标是发现并登记全部可观察市场，但只有通过来源、身份、时效、模型、万分之一不利扰动和风险门的市场才可能得到建议。

**当前证据状态：** 这是范围与缺口治理合同，不是已经完成全市场覆盖的证明；外部来源能力、实时新鲜度和生产覆盖仍未验证。

**默认：** 看得到但证据不足就明确标为“已发现但不可建议”；看不到就登记“不可观察”；不得静默丢弃、猜测数据或用单一免费端点冒充全覆盖。

**证据：** `machine/facts/canonical_facts.json#/scope`、`machine/facts/canonical_facts.json#/truth_and_evidence/silent_coverage_gap_target`、`machine/facts/costs.json#/future_source_admission_policy`、`machine/facts/parameters.json#/numeric_determinism`。

**不成立时：** 任一来源合同、身份、时效、稳定性或风险门失败，输出“不建议”并记录可见缺口；目标压力不得改变该动作。

## FAQ-S01-P02-05｜TAB/Gmail 邮件会怎样保存和清理？

**答案：** 规划中的收集器会保存原始 `.eml`、全部附件和SHA-256清单，完成发件认证、恶意文件扫描、解析和本地读回后，才把可信邮件移入Gmail垃圾箱；产品没有永久删除能力。TAB账单和交易邮件用于对账，不是实时赔率来源。

**当前证据状态：** Gmail尚未连接、未授权、未实现或启用；没有OAuth链接、令牌、邮箱地址、账户标识或真实邮件进入本 phase。

**默认：** 未授权时只关闭Gmail模块，核心任务继续；未知发件人、认证失败、附件缺失、扫描失败、读回失败或任何未知状态都保留邮件并隔离/告警，不移入垃圾箱。

**证据：** `machine/facts/canonical_facts.json#/email`、`machine/facts/email_ingestion.json#/trash_gate`、`machine/facts/degraded_mode_contract.json#/current_state`、`machine/facts/decision_prerequisites.json#/current_phase_observation`。

**不成立时：** 任一保存或恢复门失败就关闭垃圾箱动作；授权撤销或scope不精确时立即禁用Gmail模块，且不自动反复提示用户授权。

## FAQ-S01-P02-06｜OVH、Cloudflare、来源或模型故障时会怎样？

**答案：** 系统不会用旧建议、猜测值或降低门槛维持“看起来在线”。能安全降级的能力会回退到可信来源、上一签名制品、市场基线或本地模式；不能安全降级就停止新增建议。

**当前证据状态：** OVH和Cloudflare是规划目标，当前账户能力与生产就绪状态未验证；单主机零停机不作保证。

**默认：** 证据、账本、身份、数值、安全或恢复失败时输出“不建议”并自动回滚；Cloudflare不可用不等于核心数据可继续对外发布，OVH不可用则不声称7×24运行，过期建议一律失效。

**证据：** `machine/facts/canonical_facts.json#/runtime`、`machine/facts/release_policy.json#/auto_rollback_on`、`machine/facts/decision_prerequisites.json#/items`、`machine/facts/parameters.json#/numeric_determinism/unstable_action`。

**不成立时：** 无安全回退、严重安全事故、证据完整性失败或不可逆操作会暂停受影响范围并形成最小决策包。

## FAQ-S01-P02-07｜账户、邮件和隐私数据如何保护？

**答案：** 外部内容一律按不可信数据处理；代码仓和验收收据不得保存令牌、授权码、client secret、邮箱地址、账户ID或真实订单资料。将来启用Gmail时只请求精确的 `gmail.modify`，令牌必须加密保存，应用层方法白名单禁止发送、导入和永久删除邮件。

**当前证据状态：** 本 phase 只使用本地合同和确定性夹具；未访问外部账户或控制台，未取得或保存秘密、个人标识和真实邮件。

**默认：** scope不精确、令牌存储未就绪、方法未知或账户状态未知时，拒绝并禁用Gmail；持久验收证据只保留哈希、状态和脱敏元数据，不把秘密或账户数据写入仓库。

**证据：** `machine/facts/security_assurance.json#/design_controls`、`machine/facts/degraded_mode_contract.json#/scope_policy`、`machine/facts/degraded_mode_contract.json#/method_policy`、`machine/facts/degraded_mode_contract.json#/consent_receipt_contract`、`machine/facts/costs.json#/future_source_admission_policy/admission_requirements`。

**不成立时：** 一旦发现秘密泄漏、越权方法或账户数据进入持久证据，立即隔离受影响能力、停止建议、轮换/撤销秘密并保全审计证据。

## 当前交付边界

本文件与 `assumption_register.json` 只冻结 Working Backwards 的问题、默认和证据合同。它们不证明 ABD 已部署、已接入 Gmail/TAB、已覆盖全部市场、已产生真实建议或已达到任何收益目标。用户正常仍只完成最终下单；系统不具备订单提交能力。
