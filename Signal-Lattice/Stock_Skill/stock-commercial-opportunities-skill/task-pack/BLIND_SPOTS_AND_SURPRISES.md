# 盲点与 Surprise 复核

## 已修正的高风险盲点

1. **Scope mismatch**：v1 是内容研究、v2 是泛商业资格；v3 才是 listed-equity research triage。
2. **Theme-to-ticker jump**：新增 beneficiary pathway、identity、exposure denominator 和 capture bridge。
3. **Good company = good stock**：新增 expectations/valuation/catalyst/downside 独立 Gate。
4. **Ticker collision**：issuer/exchange/share class/ADR/security/currency/as-of 先于排名。
5. **Current-data laundering**：price/valuation/consensus/catalyst 没 provider/timestamp 即 unknown/stale。
6. **Score as truth**：E0–E5、confidence 和 risk 与 score 分离；hard gate 覆盖高分。
7. **Management-marketing bias**：公司 IR 是一手但非独立；要求 filing/denominator/反证。
8. **TAM-to-earnings leap**：E3 要求 orders/backlog/revenue/margin/cash-flow capture。
9. **Social/price-action overclaim**：只能 lead，不证明 exposure、consensus 或 crowding。
10. **Forced candidate list**：cap/saturation/zero result，`NO_QUALIFIED_CANDIDATE` 是成功输出。
11. **Trading boundary**：研究状态不含 BUY/SELL；无仓位、目标价保证或 execution。
12. **Private/MNPI/license leak**：public/private/provider/MNPI plane 分离；fixtures 全合成。
13. **Agent/state bloat**：默认单 writer、无 ticker memory、无安装、无 provider cache。
14. **Archive loss**：v1/v2 不静默改写，以 SHA 谱系保存。

## Surprise

### 1. 最值钱的输出常是“这不是受益股”

产业主题研究容易奖励长名单，但真正节省研究成本的是在 identity、denominator 或 capture 处尽早拒绝伪受益者。`REJECT` 与零候选不是低质量结果。

### 2. 商业机会越好，股票机会不一定越好

价值池可以真实、发行人也能捕获，但市场可能已经定价更乐观情景；反之，低关注不等于便宜。v3 必须把 commercial 和 equity setup 分开。

### 3. 最关键的数据通常最不适合打进公开包

current consensus、premium transcripts、segment datasets、portfolio context 和 borrow 数据有许可、隐私或时效约束。公开 Skill 的耐久资产应是 schema、门禁、provider/timestamp 合同与合成 fixtures，而不是数据快照。

### 4. “多 Agent”不是默认性能优化

股票研究子任务高度共享相同 filings 和 identity context。没有明确分片时，多 Agent 会重复下载、放大 token 和产生冲突。默认单 writer + source/claim IDs 更快、更可审计。

### 5. 不安装反而提高了恢复要求

源码若不在 Skill 根，未来使用依赖项目级恢复。因而 release ZIP、两层 manifest、clean-room 验证和远端 main recoverability 成为交付核心，而不是附加文档。

## 尚未消除的盲点

| 盲点 | 风险 | 当前缓解 | 剩余状态 |
|---|---|---|---|
| 权重/阈值未用真实 outcome 校准 | 排名偏差 | 透明权重、敏感性、E-level hard gates | OPEN |
| Expectations/crowding 不可直接观察 | 把推断当事实 | verified/inferred 分离；provider/timestamp | OPEN |
| Segment 披露不一致 | denominator 错配 | filing locator、period/units、inconclusive branch | OPEN |
| 跨市场 identifier/corporate actions | 错证券/重复上市 | identity-first；需要未来 security master | OPEN |
| ASX/其他市场结构化数据较弱 | 人工成本高 | 官方公告优先；不假装自动解析 | OPEN |
| ETF/trust/ADR/convertible 经济权利 | 敞口与证券权利错配 | security_type/share class gate | PARTIAL |
| Short borrow/liquidity 易变 | 研究不可执行 | E5 liquidity check；不提供交易 | OPEN |
| Filing/IR 也可能错误或促销 | false confidence | contradictions、competitor/regulator check | PARTIAL |
| 法域和建议边界依情境 | 合规风险 | educational research-only + current official check | OPEN |
| 语义触发/质量未前向评估 | 实际调用未知 | eval cases/rubric 已备 | NOT_RUN |
| 官方 Skill 工具链可能变化 | 包兼容性漂移 | 本地 validator + future current official check | OPEN |
| 仓库 public-visible + proprietary | 误以为可自由复用 | root license/README 明示；无第三方代码 | PARTIAL |

## 最终红队问题

1. 删除所有热度和价格上涨叙事后，商业机制仍成立吗？
2. 研究的是正确 issuer/security/share class 吗？
3. exposure 占哪个 denominator、哪个 period、什么 units？
4. value pool 如何变成利润/现金流，而不是只变成订单或收入？
5. 什么已经 priced in，证据还是推断？
6. 哪个事实会首先 REJECT，哪个事件会改变 rank？
7. current fields 是否真的同次获取？
8. 来源实际打开了吗，许可允许当前输出吗？
9. 是否泄露 portfolio/account/paid data/MNPI/local path？
10. 结论是否仍允许零候选，并且没有暗含交易指令？
