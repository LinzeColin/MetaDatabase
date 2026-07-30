---
name: stock-commercial-opportunities
description: Research and triage listed-equity candidates by tracing a commercial opportunity through value-chain beneficiaries, issuer exposure, orders/revenue/margins or cash-flow capture, market expectations, valuation, catalysts, risks, and falsifiers. Use for 股票商业机会拆解、产业主题到上市公司映射、受益股筛选、股票研究候选排序、商业敞口核验、what-is-priced-in、催化剂与证伪条件，或审计“主题等于股票机会”的报告. Do not use for personalized financial advice, final buy/sell/hold recommendations, position sizing, automated trading, guaranteed returns, private-company diligence, credit-first analysis, or claims based only on social media, price momentum, synthetic personas, or unverified exposure.
---

# Stock Commercial Opportunities

Turn a theme, industry shift, policy, technology, value-chain bottleneck, or candidate list into a source-traceable public-equity research queue. The output prioritizes diligence; it does not approve a trade.

## Keep four layers separate

1. **Commercial opportunity** — who pays, value pool, bottleneck, alternatives, timing, margins and durability.
2. **Issuer exposure** — the source-backed path from the opportunity to a named listed issuer, segment, product, geography, orders, backlog, revenue, margins or cash flow.
3. **Equity setup** — what expectations appear embedded, valuation support, estimate sensitivity, catalysts, downside and liquidity.
4. **Evidence maturity** — `E0 Theme` → `E1 Desk-screened` → `E2 Exposure-attributed` → `E3 Commercial-capture` → `E4 Equity-setup` → `E5 Thesis-ready`.

A strong theme does not prove issuer exposure. Strong exposure does not prove an attractive stock setup. A high score never upgrades evidence maturity.

## Preserve these invariants

- Verify issuer, ticker, exchange, share class, currency, fiscal period, security type and as-of date.
- Prefer filings, exchange announcements, company IR and primary data. Open the source; a search snippet is not evidence.
- Trace the beneficiary pathway and distinguish direct beneficiaries, suppliers, enablers, substitutes, laggards and false positives.
- Do not advance a name solely because its price rose, management mentioned the theme, or social media calls it a beneficiary.
- Require quantified or source-backed exposure; otherwise label `NEEDS_EXPOSURE_ATTRIBUTION`.
- Keep commercial score, risk deduction, evidence confidence and maturity separate.
- Treat expectations, valuation and catalyst path as gates, not decorative appendices.
- Include the first rejection, strongest countercase, thesis disconfirmers and evidence that would change priority.
- Allow zero candidates. Never force a Top N when evidence is weak.
- Never provide personalized buy/sell/hold, position size, automated execution or guaranteed returns.

## Choose one lane

- **SCREEN** — define universe and eliminate obvious false positives; up to 8 candidates and 3–6 source families.
- **ATTRIBUTE** — default; prove value-chain and issuer exposure for up to 3 candidates.
- **UNDERWRITE** — add current expectations, valuation, catalysts, downside and falsifiers before routing to deeper equity work.

Read [workflow.md](references/workflow.md) for budgets, stages and saturation stops.

## Execute this sequence

1. **Normalize the mandate.** Record universe, region/exchange, security type, long/short/watchlist intent, benchmark if relevant, horizon, liquidity floor, as-of date, source posture and output visibility.
2. **Define the commercial mechanism.** Map payer, budget, demand trigger, bottleneck, value pool, pricing power, cost bearer, substitutes, capacity and window decay. Read [commercial-mechanism.md](references/commercial-mechanism.md).
3. **Build the beneficiary pathway.** Identify direct and indirect beneficiaries, suppliers, complements, substitutes and likely false positives before naming tickers.
4. **Normalize securities.** Resolve issuer, ticker, exchange, share class, ADR/local line, currency, fiscal calendar and duplicate listings.
5. **Build source and claim registers.** Follow [evidence-protocol.md](references/evidence-protocol.md). Record source access, timestamp, filing period and evidence class. Do not cite an unopened page.
6. **Prove exposure.** Link the driver to segment/product/geography and then to orders, backlog, revenue, margins, capex, guidance, estimates or cash flow. If the link is absent, stop at `E1`.
7. **Test the equity setup.** Separate verified positioning from inferred expectations. Check current valuation context, revision path, catalysts, downside, liquidity and what would make the candidate investable or rejectable.
8. **Score without laundering uncertainty.** Use [scoring-and-maturity.md](references/scoring-and-maturity.md) and `scripts/score_stock_opportunities.py`.
9. **Choose one next diligence gate.** Use [diligence-gates.md](references/diligence-gates.md). A next step must close the highest-impact evidence gap and state a stop condition.
10. **Produce a research-priority decision.** Follow [output-contracts.md](references/output-contracts.md) and [stock-research-routing.md](references/stock-research-routing.md). `ADVANCE_RESEARCH` means deeper work only, never a trade recommendation.
11. **Run final gates.** Use `scripts/validate_deliverable.py`; disclose data/source limits, conflicts, stale fields, first rejection, falsifiers and the single highest-ROI next workflow.

## Fail closed

- No verified issuer/ticker/security → return an identity-resolution plan.
- No opened primary or first-party source for core exposure → maturity cannot exceed `E1`.
- No source-backed exposure link → status cannot exceed `SCREEN_FLAG`.
- No current expectations/valuation/catalyst context → do not call the setup thesis-ready.
- Social posts, price momentum, search trends and synthetic respondents can generate leads only.
- Private portfolio, account, transaction or MNPI inputs stay private and are never placed in a public artifact.
- For Australia and other jurisdictions, follow [safety-and-boundaries.md](references/safety-and-boundaries.md); research language does not create permission to provide regulated personal advice.

## Use resources selectively

| Need | Read or run |
|---|---|
| Lanes, caps, stages, stops | [workflow.md](references/workflow.md) |
| Commercial mechanism and beneficiary path | [commercial-mechanism.md](references/commercial-mechanism.md) |
| Filings, exchange, IR, market data, source access | [evidence-protocol.md](references/evidence-protocol.md) |
| Scores, risks, confidence, E0–E5 | [scoring-and-maturity.md](references/scoring-and-maturity.md) |
| Next diligence and stop gates | [diligence-gates.md](references/diligence-gates.md) |
| Output schemas and zero-result contract | [output-contracts.md](references/output-contracts.md) |
| Financial, MNPI, publication and access safety | [safety-and-boundaries.md](references/safety-and-boundaries.md) |
| Downstream equity workflow routing | [stock-research-routing.md](references/stock-research-routing.md) |
| Trigger, quality, calibration and cost evals | [evaluation.md](references/evaluation.md) |
| Deterministic ranking | `python3 scripts/score_stock_opportunities.py --help` |
| Deliverable gate validation | `python3 scripts/validate_deliverable.py --help` |
| Package validation | `python3 scripts/validate_skill.py . --strict` |

End with: evidence maturity, research-priority status, why it is not stronger, first rejection, what would change the rank, and one next diligence workflow.
