# 输出合同

## 1. 公共头

每份输出先给：mandate/universe、as-of、jurisdiction/exchanges、source posture、current data gaps、`research triage—not investment advice`、候选 funnel 与最高 ROI 下一工作流。

## 2. Stock Opportunity Radar

0–8 个候选：

| Rank | Issuer/ticker/exchange | Beneficiary path | Exposure proof | Score/risk/confidence | E-level | Status | First rejection | Next diligence |
|---|---|---|---|---|---|---|---|---|

无量化 exposure 时必须显示 `NEEDS_EXPOSURE_ATTRIBUTION`。

## 3. Candidate Dossier

1. security identity；
2. commercial mechanism/value pool；
3. beneficiary pathway；
4. issuer segment/product/geography exposure + denominator；
5. orders/backlog/revenue/margin/cash-flow capture；
6. expectations/valuation/estimate path；
7. catalysts；
8. downside、first rejection、falsifiers；
9. score/risk/confidence/E-level；
10. status、why not stronger、one next workflow。

## 4. Research Priority Memo

```text
Decision: REJECT | SCREEN_FLAG | WATCHLIST | DILIGENCE_NEXT | ADVANCE_RESEARCH | NO_QUALIFIED_CANDIDATE
Selected candidate: <issuer/ticker or NONE>
Evidence maturity: E0-E5
Reason:
Why not stronger:
First rejection:
What changes the rank:
Next diligence/workflow:
Owner / review date:
Source and data limitations:
Financial boundary: research prioritization only
```

## 5. Evidence Audit

检查：issuer/ticker 错配、period/currency/unit 冲突、未打开/未登记 URL、snippet/social-only core claim、theme→issuer 断裂、无 denominator、过期 price/valuation/consensus、management marketing、price-action/crowding 混淆、无 falsifier、private/MNPI 泄漏、guarantee 或个性化 action。

## 6. 零结果

若无候选跨门禁：

- `Decision: NO_QUALIFIED_CANDIDATE`；
- 列搜索 universe、失败原因与最接近候选；
- 给可重开证据/价格/事件条件和 review date；
- 不补 filler、不把社交热度强行升级。

## 7. 结构化 JSON 顶层

```json
{
  "meta": {},
  "sources": [],
  "claims": [],
  "candidates": [],
  "assumptions": [],
  "diligence": [],
  "decision": {}
}
```

关键关系：candidate.claim_ids → claims；candidate.assumption_ids → assumptions；diligence 绑定 candidate/assumption；decision.selected_candidate_id 与状态一致。所有 URL 在 sources allowlist。

## 8. 写作纪律

- 结论先行、研究状态醒目；
- Fact/Inference/Estimate/Unverified 分开；
- current price/valuation/estimate 必须 timestamp/provider；
- 不使用“必涨、稳赚、确定翻倍、无风险、强烈买入”等；
- 不展示私人持仓/交易或疑似 MNPI；
- 不以 disclaimer 掩盖实质上的个性化建议。
