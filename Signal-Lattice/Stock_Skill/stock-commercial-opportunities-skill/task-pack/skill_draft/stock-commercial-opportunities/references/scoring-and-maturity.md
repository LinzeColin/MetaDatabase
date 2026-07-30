# 评分、E0–E5 与研究门禁

## 1. 四个独立输出

1. `base_score`：商业与股票研究吸引力，0–100；
2. `risk_deduction`：风险扣分，0–40；
3. `evidence_confidence`：来源覆盖和直接性，0–100；
4. `evidence_maturity`：E0–E5 离散门禁。

`decision_score = clamp(base_score - risk_deduction - 0.15 × (100-confidence), 0, 100)`。这是研究优先级启发式，不是预期收益、目标价或成功概率。

## 2. Research ROI（0–10）

- R1 Learning：能否快速关闭关键知识缺口；
- R2 Thesis：是否可能形成可证伪 variant wedge；
- R3 Catalyst：是否有可跟踪 revision/event path；
- R4 Decision：下一研究能否改变 advance/watch/reject。

## 3. 基础分（权重合计 100）

| 维度 | 权重 | 评分锚点 |
|---|---:|---|
| commercial_value_pool | 12 | payer、预算、瓶颈、利润池、持续性 |
| issuer_exposure_attribution | 16 | product/segment/geography 与 denominator 可证 |
| financial_capture_path | 12 | orders/backlog/revenue/margin/cash flow 路径 |
| beneficiary_position | 10 | 竞争、份额、capacity、pricing power |
| expectations_variant | 12 | what-is-priced-in 与可证伪差异 |
| valuation_support | 10 | 当前口径、历史/peer/earnings 支撑与 downside |
| catalyst_revision_path | 10 | 事件/KPI 到 estimates 或 thesis 的路径 |
| durability_balance_sheet | 7 | 周期、资本、融资和执行韧性 |
| liquidity_instrument_fit | 5 | security、流动性、share class/borrow（如适用） |
| research_edge_speed | 6 | 可在有限成本内获得决定性证据 |

## 4. 风险扣分（最大 40）

| 风险 | 最大扣分 | 含义 |
|---|---:|---|
| exposure_gap | 8 | 主题与发行人经济敞口断裂 |
| expectations_priced_in | 7 | 需要极端 beat 才成立 |
| valuation_downside | 6 | multiple/earnings 双重下行 |
| earnings_cyclicality | 5 | 周期、客户集中、一次性或口径风险 |
| balance_sheet_funding | 4 | capex、杠杆、稀释或融资约束 |
| regulatory_geopolitical | 4 | 法规、许可、制裁、补贴/关税依赖 |
| liquidity_shortability | 3 | 流动性、borrow、ADR/share-class 风险 |
| freshness_source_gap | 3 | 过期、冲突、snippet 或缺 primary source |

0 表示未观察到该风险，不表示风险不存在。未知且关键时应提高风险或降低 confidence。

## 5. 置信度（权重合计 100）

| 维度 | 权重 |
|---|---:|
| claim_coverage | 20 |
| primary_source_quality | 20 |
| exposure_directness | 20 |
| metric_period_normalization | 15 |
| source_diversity | 10 |
| recency | 10 |
| contradiction_resolution | 5 |

## 6. E0–E5

| Code | Label | 最低保守证据 |
|---|---|---|
| E0 | Theme | 只有叙事/新闻/价格/social/synthetic |
| E1 | Desk-screened | ≥3 独立公开来源家族；身份和机制初筛 |
| E2 | Exposure-attributed | ≥1 company filing/official IR + ≥1 量化 segment/product/geography exposure |
| E3 | Commercial-capture | E2 + ≥1 orders/backlog/revenue/margin/cash-flow capture signal |
| E4 | Equity-setup | E3 + 当前 valuation observation + confirmed catalyst/estimate link |
| E5 | Thesis-ready | E4 + ≥2 falsifiers/first rejection + 完整 downside/liquidity/source freshness |

脚本 signals 是小团队 gate，不是统计模型。缺口一律取更低 maturity。

## 7. 研究状态

| Status | 默认门槛 | 含义 |
|---|---|---|
| REJECT | hard stop 或 score <40 | 从当前研究队列移除 |
| SCREEN_FLAG | score 40–54 或 E0/E1 | 仅保留线索；需要敞口归因 |
| WATCHLIST | score 55–64 | 等待价格/事件/证据触发 |
| DILIGENCE_NEXT | score ≥65、confidence ≥55、E2+ | 只批准一个下一尽调 |
| ADVANCE_RESEARCH | score ≥75、confidence ≥65、E4+ | 进入 pitch/model/valuation 等深研；不是交易批准 |
| NO_QUALIFIED_CANDIDATE | 无候选跨门禁 | 有效零结果 |

Hard gates：无 security identity 不排名；无 exposure attribution 不高于 SCREEN_FLAG；无 E4 不得 ADVANCE_RESEARCH；任何状态都不得解释为 buy/sell/hold。

## 8. Value of Information

`VOI = impact × uncertainty × reversibility ÷ (time + data cost + coordination + legal/privacy risk)`。优先验证会改变状态的关键断点：exposure denominator、capture、expectations、valuation、catalyst、falsifier。只给一个默认 next diligence。

## 9. 敏感性

对 top candidate 至少重算：exposure -2、expectations risk +2、confidence -20。若排名/状态翻转，披露“结论对 X 高敏感”，不得隐藏在小数精度中。
