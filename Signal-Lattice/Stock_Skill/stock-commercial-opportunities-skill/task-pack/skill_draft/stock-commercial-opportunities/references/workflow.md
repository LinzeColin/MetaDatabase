# 工作流、Lane 与停止门禁

## 1. 默认运行合同

先写决定对象与研究边界，再搜索。缺失会改变证券身份、法域、时点或验收的输入时，最多问 3 个编号问题；其余作为假设并降级。

| 输入 | 默认 | 阻断/改变条件 |
|---|---|---|
| use | research triage / watchlist | 用户要求个性化交易、自动执行或受监管建议 |
| universe | liquid listed common equities | 用户给定交易所、指数、sector 或名单 |
| geography | global public sources | 法域、交易所或披露制度决定来源 |
| horizon | 6–18 months | 事件/财报/短期催化任务 |
| as_of | 同次运行日期 | 历史回溯 |
| source posture | filings/exchange/IR first | 只有二手/社交来源时降级 |
| output | research-priority queue | 用户明确要 quick inline 或特定 artifact |
| visibility | private | 要公开且完成 disclosure/MNPI/redaction 检查 |

## 2. 三条 Lane：上限不是配额

| Lane | 用途 | 候选 cap | 深拆 cap | 来源家族 cap | 退出条件 |
|---|---|---:|---:|---:|---|
| SCREEN | 构建 universe、排除伪受益 | 8 | 0–2 | 3–6 | 可 Reject/Screen flag，或身份/来源不可得 |
| ATTRIBUTE | 默认；证明受益路径和发行人敞口 | 5 | 1–3 | 5–10 | E2/E3 可判，或连续两轮无新关键证据 |
| UNDERWRITE | 加入预期、估值、催化、下行 | 3 | 1–3 | 按关键主张 | E4/E5 可判或数据缺口阻断 |

固定候选数会制造 filler。允许 `NO_QUALIFIED_CANDIDATE`。

## 3. 阶段状态机

### S0 — Mandate and security contract

记录 issuer/ticker/exchange/share class/security type/currency、universe、horizon、liquidity、benchmark、as-of 和非目标。身份不清不得进入排序。

### S1 — Commercial mechanism

明确 payer、预算/需求触发、价值池、瓶颈、替代、供需约束、利润池、持续性和反论点。

### S2 — Beneficiary pathway

先画 direct beneficiary、supplier、enabler、substitute、laggard、false positive，再匹配上市公司，避免“先有 ticker 后找故事”。

### S3 — Source and claim register

登记 opened source、filing period、publication/retrieval time、currency/unit、claim IDs 与冲突。snippet/social 只能发现线索。

### S4 — Exposure attribution

至少回答：哪个 segment/product/geography 暴露？对 orders/backlog/revenue/margins/capex/cash flow 的路径是什么？没有证据时标 `NEEDS_EXPOSURE_ATTRIBUTION`。

### S5 — Equity setup

检查当前价格时间戳、估值口径、consensus/expectations 可得性、revision path、催化、downside、liquidity、first rejection 和 falsifiers。价格上涨本身不是 crowded 证据。

### S6 — Score and maturity

输出 attractiveness、risk deduction、confidence、decision score 与 E0–E5。高分不提升 maturity。

### S7 — Decision and route

状态：`REJECT / SCREEN_FLAG / WATCHLIST / DILIGENCE_NEXT / ADVANCE_RESEARCH / NO_QUALIFIED_CANDIDATE`。只给一个最高 ROI 下一工作流。

### S8 — QA and handoff

验证 schema、URL allowlist、来源访问、时效、证券身份、maturity、金融边界与零结果。披露未完成项。

## 4. 饱和与停止

满足任一即停：

- 连续两轮检索未新增核心 claim、冲突或 falsifier；
- E0–E5 已可保守判定，继续搜索不改变状态；
- 核心来源不可公开访问；
- 当前价格/估值/consensus 无可靠时间戳，只能停在 screen-grade；
- 触发 MNPI、账户、个人建议或自动交易边界；
- 候选无法证明发行人敞口；
- time/source/token cap 达到。

## 5. 失败闭环

| 失败 | 输出 |
|---|---|
| Security identity unknown | 身份解析计划，不排名 |
| Primary source unavailable | 标注缺口，最高 E1 |
| Exposure link missing | `SCREEN_FLAG / NEEDS_EXPOSURE_ATTRIBUTION` |
| Valuation/expectations stale | 不进入 E4/E5；给刷新字段 |
| Social-only signal | lead only；不得 advanced |
| No survivor | `NO_QUALIFIED_CANDIDATE` + 重开条件 |
| Personalized action requested | 限定为一般教育研究或停止 |

## 6. 性能记录

记录 elapsed time、opened sources、source families、candidate funnel、input/output tokens、stale fields、unsupported claims、exposure gaps、saturation reason 与 next workflow。不要用多代理数量冒充效率。
