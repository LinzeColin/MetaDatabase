# 股票研究下游路由

## 1. 路由原则

本 Skill 负责回答“这个商业机会是否能归因到某只上市证券，并值得投入下一单位研究时间”。它不替代完整股票研究，也不自动调用外部系统。只有候选跨过相应证据门禁，才路由到一个下游工作流。

## 2. 状态到动作

| 状态 | 允许的下一步 | 禁止解释 |
|---|---|---|
| REJECT | 记录拒绝原因与重开条件 | 永久无价值或必跌 |
| SCREEN_FLAG | 身份/敞口归因检查 | 已是受益股 |
| WATCHLIST | 等待价格、披露、事件或 KPI 条件 | 当前应交易 |
| DILIGENCE_NEXT | 执行一个最高 VOI 的证据门禁 | 研究团队认可买入 |
| ADVANCE_RESEARCH | 路由到模型、估值、业绩、催化或论点整合 | buy/sell/hold 批准 |
| NO_QUALIFIED_CANDIDATE | 保存 universe、失败原因和重开条件 | 为了完整性补候选 |

## 3. 缺口路由矩阵

| 当前关键缺口 | 默认下一工作流 | 最低输入 | 完成证据 |
|---|---|---|---|
| 证券身份 | issuer/security master 核验 | 名称、市场、疑似 ticker | exchange/filing identity + as-of |
| 主题边界 | 行业/价值链地图 | demand driver、payer、bottleneck | beneficiary/loser/false-positive map |
| 发行人敞口 | filing/segment attribution | issuer、产品/segment 假设 | denominator、period、source locator |
| 商业捕获 | revenue/backlog/margin bridge | E2 敞口 | capture KPI 与财务口径 |
| 预期差 | expectations/variant 分析 | E3 + current estimates/positioning proxies | 可证伪 variant wedge |
| 估值 | valuation/comps/DCF | 正常化财务、价格、share count | as-of、口径、敏感性、downside |
| 催化 | catalyst calendar | confirmed event/KPI | 日期来源、revision path、fail branch |
| 业绩窗口 | earnings review/preview | filing history、consensus、KPI | beat/miss/guide 情景与证伪 |
| 下行与风险 | countercase/red-team | top thesis claims | first rejection、falsifiers、stress case |
| 论点整合 | long/short research memo | E4+，来源与模型完整 | thesis/countercase/monitoring plan |

若环境中没有对应工具，只交付可执行输入合同和验证命令，不虚构已运行状态。

## 4. 从商业机会到股票论点的桥

```text
Demand driver
→ payer/budget/value pool
→ value-chain bottleneck
→ issuer product/segment/geography
→ exposure denominator
→ orders/backlog/revenue/margin/cash flow
→ estimates and market expectations
→ valuation/downside
→ catalyst and falsifier
→ deeper research queue
```

每个箭头至少一个 claim/source。断点决定下一工作流；不能用叙事补齐。

## 5. Long/short 与 watchlist 边界

- Long 候选仍需证明预期尚未完全计价、商业捕获和估值下行边界。
- Short 候选仍需合法、可得、当前的 liquidity/borrow 信息；“概念过热”本身不是做空论点。
- Watchlist 必须有可观察触发器、provider、阈值和 review date；没有触发器的名单是存储负担。
- 用户未给方向时，不推断 long/short；输出中性 research-priority queue。

## 6. 下游交接合同

每次只交接：

1. selected candidate/security identity；
2. 当前 E-level/status 与不更强的原因；
3. 已验证 claim IDs/source IDs；
4. 关键 period/currency/units/as-of；
5. 一个最高 VOI 缺口；
6. pass/fail/inconclusive 分支；
7. privacy/license/MNPI 边界；
8. 预期产物和验证命令。

未运行下游工作流时标 `NOT_RUN`，不得写成 PASS。
