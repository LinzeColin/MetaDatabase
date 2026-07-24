# AI 数据中心液冷基础设施：24 个月全球上市权益决策备忘录

**截至及来源截止：2026-07-23**  
**模式：scan**  
**决策：`WATCH_PRICED`**

研究边界：**仅研究；不使用杠杆；不自动交易。**

## 决策摘要

液冷是一个真实、已获资金支持的产业约束，但截至截止日，尚不足以构成高置信度、具备合理安全边际的全球上市权益瓶颈机会。

核心原因：

- 高密度 AI 机架确实需要液冷。NVIDIA Vera Rubin 使用 45°C 进水、闭环液冷，并可配合无冷水机的 dry cooler；这证明液冷功能不可缺，但也说明价值可能从传统冷水机转移到其他组件。[NVIDIA Vera Rubin](https://blogs.nvidia.com/blog/vera-rubin/)
- 付款人资金真实。Microsoft 单季资本开支为 319 亿美元且需求继续超过可用容量；Alphabet 2026 年资本开支指引为 1,750–1,850 亿美元；Amazon 最近十二个月净 PPE 采购为 1,472.99 亿美元。[Microsoft](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3)、[Alphabet](https://abc.xyz/investor/events/event-details/2026/2025-Q4-Earnings-Call-2026-Dr_C033hS6/default.aspx)、[Amazon](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-First-Quarter-Results/default.aspx)
- 但公开证据没有证明“液冷设备本身”是唯一或最持久的约束。电力、并网、许可、GPU 和场址可能先成为绑定条件；Alphabet 斥资约 47.5 亿美元收购 Intersect 来加快电力与数据中心容量上线就是反证之一。[Alphabet–Intersect](https://abc.xyz/investor/news/news-details/2025/Alphabet-Announces-Agreement-to-Acquire-Intersect-to-Advance-U-S--Energy-Innovation-2025-DVIuVDM9wW/default.aspx)
- 供给响应已启动：Vertiv 的 Ohio 项目计划在 2027 年第二季度把相关液冷及冷冻水系统产能提高约 45%；nVent 两年内第二次扩产；Schneider/Motivair 也在扩充产品及制造体系。[Vertiv](https://investors.vertiv.com/news/news-details/2026/Vertiv-to-Expand-Ohio-Manufacturing-to-Boost-U-S--Production-of-Critical-Thermal-Management-Technologies-for-AI-Data-Centers/)、[nVent](https://investors.nvent.com/press-releases/press-release-details/2025/nVent-Expands-Data-Center-Solutions-Manufacturing-with-New-U-S--Production-Facility/default.aspx)、[Schneider](https://www.se.com/ww/en/about-us/newsroom/news/press-releases/Schneider-Electric-Unveils-Liquid-Cooling-Portfolio-with-Motivair-Featuring-Dedicated-Solutions-and-Services-for-HPC-and-AI-Workloads-68d69e595c9dbb622505caf3/)
- OCP 与 ASHRAE 正在协调设施水路、CDU、direct-to-chip 和 immersion 标准。标准化利于市场扩张，却通常削弱单一供应商的接口垄断和长期定价权。[OCP/ASHRAE](https://www.opencompute.org/blog/open-compute-project-foundation-and-ashrae-form-new-alliance)
- 最重要的是，市场已经发现这一主题。直接标的估值较高，收购方也为私营液冷资产支付了约 5.6–8.6 倍销售额，部分稀缺租金已转移给卖方，而非留给收购方股东。

因此：

> **行业约束成立；上市权益租金捕获不充分；预期差门槛失败。**

## 范围与基准

全球筛选规则：

- 普通股及可验证的主要上市证券；
- 市值不低于 20 亿美元；
- 20 日中位日成交额不低于 1,000 万美元；
- 排除 OTC、重复上市、杠杆产品及衍生品；
- 缺少可复核流动性、法律实体或财务拆分的证券不进入可行动研究名单。

基准采用 **MSCI ACWI Net USD**，ACWI ETF 作为可观察代理。MSCI 官方指数截至 2026-06-30 的市盈率为 23.64 倍；iShares ACWI 截至 2026-07-17 持有约 2,237 只证券，市盈率为 25.24 倍。两者口径和日期不同，不能机械等同。[MSCI ACWI](https://www.msci.com/indexes/index/892400/msci-acwi-index)、[iShares ACWI](https://www.ishares.com/us/products/239600/ishares-msci-acwi-etf)

模型采用 24 个月 ACWI 总回报 **15%–19%** 作为规划门槛；这是估值假设，不是指数预测。

## 系统和证券映射

产业链为：

`超大规模云厂商资金 → GPU/机架架构 → 数据中心/EPC → CDU、冷板、冷水机、dry cooler、热交换及服务 → 每股自由现金流`

没有发现一个同时具备专有接口、不可替代资格认证和长期供给垄断的上市“收费站”。

| 标的 | 角色 | 主要证据与限制 | 决策 |
|---|---|---|---|
| MOD | unlocker | 数据中心占 FY2026 销售约 35%；存在 2027–2029 年超过 40 亿美元的冷却销售预期协议，但客户未命名、可取消，液冷收入未单列 | `WATCH_PRICED` |
| VRT | unlocker/full-stack | 订单和整体 FCF 强，但液冷收入、毛利和产能利用率未单列；约 47 倍 FY2026 EPS 指引 | `WATCH_PRICED` |
| NVT | unlocker | 已部署液冷容量并扩产，但“基础设施”同时包含数据中心和公用事业；约 35 倍 FY2026 调整 EPS 指引 | `WATCH_EVIDENCE` |
| ETN | absorber | Boyd 提供直接暴露，但约 95.5 亿美元收购价相当于约 5.6 倍 2026E 销售，且在 Eaton 集团内材料性有限 | `BOTTLENECK_NOT_EQUITY` |
| ECL | absorber | CoolIT 为纯液冷资产，但约 47.5 亿美元收购价约为 NTM 销售的 8.6 倍，增加杠杆并拖累近期 EPS | `BOTTLENECK_NOT_EQUITY` |
| SU.PA | absorber | Motivair 提供液冷平台，但相对 Schneider 集团规模过小，主题收益被稀释 | `BOTTLENECK_NOT_EQUITY` |
| 2308.TW | unlocker/full-stack | Delta 称液冷为增长驱动，但没有审计后的液冷分部数据；二手市场数据指向很高的隐含预期 | `WATCH_PRICED` |
| 3017.TW、3324.TWO | owner/unlocker | 产品相关性较高，但缺少足够英文一手财务拆分、客户与独立估值验证 | `WATCH_EVIDENCE` |
| JCI、LR.PA、MTRS.ST、ALFA.ST、6367.T、6273.T | public proxy | 业务过于多元或液冷材料性未证明 | `BOTTLENECK_NOT_EQUITY` |

Innventure/Accelsius 的公开代理 INV 因约 2.6 亿美元市值和约 420 万美元的观察日成交额未通过流动性门槛。[Accelsius](https://accelsius.com/series-b-announcement/)

## 代表性标的：MOD

Modine 是筛选中收入材料性最清楚的标的：

- FY2026 销售约 32 亿美元，数据中心约占 35%，即约 11.2 亿美元；
- FY2026 调整 EBITDA 为 4.71 亿美元、调整 EPS 为 5.02 美元、自由现金流约 1.054 亿美元；
- FY2027 调整 EBITDA 指引为 6.5–6.8 亿美元；
- 公司披露了 2027–2029 年超过 40 亿美元的冷却销售预期协议及 1.65 亿美元预付款，但同时披露取消、削减和部件短缺风险。[Modine 10-K](https://www.sec.gov/Archives/edgar/data/67347/000110465926066795/mod-20260331x10k.htm)、[FY2026 results](https://investors.modine.com/news/news-details/2026/Modine-Reports-Fourth-Quarter-Fiscal-2026-Results/default.aspx)

以 2026-07-22 约 249.6 美元价格计：

- 约为 FY2026 调整 EPS 的 49.7 倍；
- 约为股权价值/FY2027 EBITDA 指引中点的 19.8 倍，且这不是 EV/EBITDA；
- 公司正在进行业务分拆/组合交易，24 个月每股价值桥存在额外不确定性。

筛选级情景模型把继续经营业务与可能分配价值合并计算：

| 情景 | 概率 | 假设的 24 个月总价值 | 回报 |
|---|---:|---:|---:|
| Bear | 30% | 约 140 美元 | -44% |
| Base | 50% | 约 260 美元 | +4% |
| Bull | 20% | 约 416 美元 | +67% |

概率加权预期回报约 **2.2%**，明显低于 15%–19% 的 ACWI 规划门槛；且预期收益/熊市下行比仅约 0.05。

Skill 评分结果：

| 维度 | 得分 | 门槛 |
|---|---:|---:|
| 产业约束 | 68.0 | 60 |
| 股东价值捕获 | 66.5 | 55 |
| 错价/时点 | **42.0** | **45** |
| 证据 | 78.0 | 60 |
| 可投资性 | 71.0 | 50 |
| 最终分数 | 55.291 | — |

没有硬性 kill flag，但错价门槛未通过，因此不是 `CANDIDATE`。

## 三个时钟

- 物理稀缺期 P10/P50/P90：**9/18/36 个月**
- 供应商变现滞后：**6 个月**
- 市场发现：**约 3 个月，实质上已经发生**
- P50 可变现窗口：**约 12 个月**

24 个月持有期超过 P50 稀缺窗口，意味着后半段可能面对新增产能、标准化和估值正常化。

## 反方和否证条件

产业瓶颈论将被以下事实否证：

- 下一代最高密度机架在可比 TCO 和可靠性下大规模通过纯风冷或其他非液体方案认证；
- 三家以上主要供应商交付周期恢复至正常水平，同时订单/出货低于 1；
- 电力、许可或 GPU 延迟使已规划机房长期无法上线，液冷设备转为闲置或库存；
- 标准化设计允许客户无摩擦替换 CDU、冷板或冷水机供应商，稀缺租金消失。

股东价值论将被以下事实否证：

- MOD 的相关协议被削减或取消超过 25%；
- 连续两个季度数据中心增长低于 20%，同时利润率同比下降；
- 收入增长没有转化为每股 FCF，原因是工作资本、资本开支、收购、SBC 或稀释；
- VRT、NVT、Delta 等继续拒绝披露液冷收入和利润，而市场估值仍假设高材料性；
- 收购资产的协同无法抵消 Eaton/Ecolab 已支付的高销售倍数。

主要未解决主张：

1. 行业统一口径的液冷产能、利用率、交付周期和取消率不存在公开可靠数据。
2. MOD 的大客户身份、合同强制性、价格条款及液冷占比没有独立来源确认。
3. VRT、NVT、Delta 均缺少液冷收入、毛利和 FCF 拆分。
4. 超大规模客户的双供应商和自研设计比例未知。
5. MOD 公司交易完成后的完全稀释每股价值桥仍需重建。
6. 台湾标的的实体、流动性和审计口径需要本地一手资料复核。

## 机器可读决策对象

```json
{
  "schema_version": "1.0",
  "skill_version": "0.0.0.1",
  "as_of": "2026-07-23",
  "source_cutoff": "2026-07-23",
  "previous_version": null,
  "thesis_id": "ai-data-center-liquid-cooling-mod-20260723",
  "mode": "scan",
  "research_boundary": [
    "research only",
    "no leverage",
    "no automatic trading"
  ],
  "universe": {
    "scope": "global listed common equities",
    "horizon_months": 24,
    "minimum_market_cap_usd": 2000000000,
    "minimum_20d_median_advt_usd": 10000000,
    "exclusions": [
      "OTC",
      "duplicate listings",
      "leveraged products",
      "derivatives",
      "unverified legal entity or liquidity"
    ]
  },
  "benchmark": {
    "index": "MSCI ACWI Net USD",
    "observable_proxy": "ACWI",
    "index_pe_2026_06_30": 23.64,
    "etf_pe_2026_07_17": 25.24,
    "planning_hurdle_24m_pct": [15, 19],
    "planning_hurdle_is_assumption": true
  },
  "candidate": {
    "ticker": "MOD",
    "company": "Modine Manufacturing Company",
    "market": "NYSE",
    "currency": "USD",
    "role": "unlocker",
    "lifecycle_stage": "CONTRACTED_RAMP"
  },
  "decision": {
    "label": "WATCH_PRICED",
    "hard_gates_passed": true,
    "default_score_gates_passed": false,
    "failed_gate": "mispricing",
    "reason": "Mispricing score 42.0 is below 45 and the 24-month probability-weighted return is 2.2%."
  },
  "scores": {
    "constraint": {
      "funded_demand": 5.0,
      "architectural_necessity": 4.5,
      "current_tightness": 3.5,
      "supplier_concentration": 2.0,
      "qualification_barrier": 3.0,
      "substitution_difficulty": 2.5,
      "expansion_lead_time": 3.0,
      "policy_resilience": 3.0
    },
    "capture": {
      "exposure_materiality": 4.5,
      "pricing_power": 2.5,
      "capacity_to_ship": 2.5,
      "unit_economics": 3.0,
      "contract_counterparty": 3.5,
      "appropriability": 3.0,
      "balance_sheet": 4.0,
      "dilution_discipline": 4.0,
      "capital_allocation": 3.0
    },
    "mispricing": {
      "expectations_gap": 1.5,
      "valuation_asymmetry": 1.5,
      "coverage_gap": 2.0,
      "catalyst_clarity": 4.0,
      "estimate_revision_potential": 3.0,
      "crowding_headroom": 1.5,
      "entry_setup": 1.0
    },
    "evidence": {
      "primary_source_coverage": 4.5,
      "independent_corroboration": 3.0,
      "numerical_traceability": 4.0,
      "freshness": 4.5,
      "contradiction_search": 4.0,
      "source_independence": 3.0
    },
    "investability": {
      "liquidity": 4.0,
      "governance_accounting": 4.0,
      "geopolitical_regulatory": 4.0,
      "customer_diversification": 2.0,
      "technology_resilience": 3.5,
      "balance_sheet_survival": 4.0,
      "float_gap_risk": 4.0,
      "portfolio_fit": 2.0
    }
  },
  "dimension_scores": {
    "constraint": 68.0,
    "capture": 66.5,
    "mispricing": 42.0,
    "evidence": 78.0,
    "investability": 71.0
  },
  "core_geometric_score": 63.736,
  "final_score": 55.291,
  "clocks": {
    "scarcity_p10_months": 9,
    "scarcity_p50_months": 18,
    "scarcity_p90_months": 36,
    "monetization_lag_months": 6,
    "market_discovery_months": 3,
    "monetizable_runway_months": 12,
    "contracted_forward_ramp": true
  },
  "scenarios": {
    "bear": {
      "probability": 0.3,
      "return_pct": -44,
      "summary": "Aggregate continuing-business and distributed value approximately USD140."
    },
    "base": {
      "probability": 0.5,
      "return_pct": 4,
      "summary": "Aggregate continuing-business and distributed value approximately USD260."
    },
    "bull": {
      "probability": 0.2,
      "return_pct": 67,
      "summary": "Aggregate continuing-business and distributed value approximately USD416."
    }
  },
  "scenario_metrics": {
    "expected_return_pct": 2.2,
    "bear_downside_reference_pct": 44.0,
    "asymmetry_ratio": 0.05
  },
  "hard_flags": {
    "no_primary_evidence": false,
    "wrong_entity_or_ticker": false,
    "no_material_revenue_bridge": false,
    "substitution_before_monetization": false,
    "unfunded_financing_gap": false,
    "kill_switch_triggered": false,
    "bull_case_required_to_avoid_loss": false
  },
  "kill_switches": [
    {
      "condition": "Named capacity agreement is cancelled or reduced by more than 25%.",
      "metric": "Contracted expected sales or reserved capacity",
      "source": "Modine SEC filings and any counterparty disclosure",
      "review_date": "2026-10-31",
      "triggered": false
    },
    {
      "condition": "Data-center growth is below 20% for two consecutive quarters while adjusted margin contracts year over year.",
      "metric": "Data-center sales growth and adjusted EBITDA margin",
      "source": "Modine quarterly filings",
      "review_date": "2027-02-28",
      "triggered": false
    },
    {
      "condition": "Three major suppliers report normalized lead times, book-to-bill below 1, or excess inventory.",
      "metric": "Lead time, book-to-bill and inventory",
      "source": "Issuer filings and customer procurement disclosures",
      "review_date": "2027-03-31",
      "triggered": false
    },
    {
      "condition": "Highest-density production racks qualify non-liquid cooling at comparable TCO and reliability.",
      "metric": "Production qualification and cooling architecture",
      "source": "NVIDIA, OCP, hyperscaler and OEM technical disclosures",
      "review_date": "2027-07-23",
      "triggered": false
    }
  ],
  "screen_results": [
    {"ticker": "MOD", "label": "WATCH_PRICED"},
    {"ticker": "VRT", "label": "WATCH_PRICED"},
    {"ticker": "NVT", "label": "WATCH_EVIDENCE"},
    {"ticker": "ETN", "label": "BOTTLENECK_NOT_EQUITY"},
    {"ticker": "ECL", "label": "BOTTLENECK_NOT_EQUITY"},
    {"ticker": "SU.PA", "label": "BOTTLENECK_NOT_EQUITY"},
    {"ticker": "2308.TW", "label": "WATCH_PRICED"},
    {"ticker": "3017.TW", "label": "WATCH_EVIDENCE"},
    {"ticker": "3324.TWO", "label": "WATCH_EVIDENCE"}
  ],
  "excluded": [
    {
      "ticker": "INV",
      "reason": "Fails USD10m 20-day median ADVT research floor."
    }
  ],
  "unresolved_claims": [
    "System-wide liquid-cooling capacity, utilization and lead-time data are unavailable.",
    "MOD liquid-only revenue and contract enforceability lack independent corroboration.",
    "VRT, NVT and Delta do not disclose liquid-cooling revenue and free-cash-flow bridges.",
    "Hyperscaler dual-sourcing and in-house design shares are unknown.",
    "MOD post-transaction fully diluted per-share value requires re-underwriting.",
    "Taiwan candidate legal-entity, liquidity and audited exposure checks remain incomplete."
  ],
  "evidence_validation": {
    "valid": true,
    "claim_count": 7,
    "errors": 0,
    "warnings": 0,
    "open_claim_id": "C-004"
  },
  "notes": [
    "Industry constraint is not equivalent to shareholder rent capture.",
    "Scenario and benchmark returns are forecasts or assumptions, not facts.",
    "No position, order or automatic execution is authorized or implied."
  ]
}
```

## 完成状态

- 进度：100%
- 已完成：全球筛选、基准选择、产业与权益约束分离、三时钟、评分、估值情景、反证、kill switches、证据校验和机器对象。
- 未完成：无必需交付；六项未解决主张已保留，未用推测填补。
- 预计剩余迭代：0；下一次有价值的迭代应在下一轮季度披露、MOD 公司交易条款或独立客户证据出现后进行。
- 置信度：0.86。
- 推荐下一步：维持研究观察；只有在液冷收入/FCF 拆分得到验证且错价分超过 45 后，才重新评估 `CANDIDATE`，这不是价格指令或订单建议。

## Execution trace

**Skill-relative files read**

- `SKILL.md`
- `references/methodology.md`
- `references/research_workflow.md`
- `references/source_policy.md`
- `references/scoring_model.md`
- `references/portfolio_risk.md`
- `references/output_contract.md`
- `references/failure_modes.md`
- `schemas/evidence.schema.json`
- `schemas/opportunity.schema.json`
- `schemas/portfolio.schema.json`

**Commands/scripts run and observed outputs**

- Skill 路径查找：定位到 `.forward-sandbox-T002/bottleneck-serenity-skill`；没有读取父仓或兄弟项目内容。
- `python3 scripts/score_opportunity.py --help`：成功，显示 input、template、json/md/both 参数。
- `python3 scripts/validate_evidence.py --help`：成功，显示 stdin 与 strict-warnings 参数。
- `python3 scripts/score_opportunity.py --template`：成功，返回 Skill 1.0 输入模板。
- `python3 scripts/score_opportunity.py - --format both`：成功；输出 `WATCH_PRICED`、最终分数 55.291、错价 42.0、预期回报 2.2%、无 active hard flags。
- 第一次 `python3 scripts/validate_evidence.py -`：退出码 1；发现 MOD 关键事实只有一个独立来源，并提示两个 inference 缺少 `depends_on`。
- 修订后再次运行 `python3 scripts/validate_evidence.py -`：退出码 0；7 项 claims、`valid=true`、0 errors、0 warnings。
- 文件写入：**none**。

**Web searches performed，按查询族归并**

- Microsoft、Alphabet、Amazon、Meta 的 2026 AI/data-center capex、capacity constraints 与 committed spend。
- NVIDIA GB200/GB300/Vera Rubin 的 liquid cooling、rack density、45°C inlet、dry-cooler 架构。
- OCP/ASHRAE liquid-cooling standards、CDU、TCS/FWS、direct-to-chip 与 immersion。
- Modine FY2026 10-K、data-center revenue、USD4bn capacity agreement、USD165m deposit、component shortages、price history。
- Vertiv FY2025/FY2026 earnings、backlog、FCF、liquid-cooling revenue、Ohio capacity expansion。
- nVent Q1 2026、backlog、infrastructure vertical、liquid-cooling deployments、Blaine expansion。
- Eaton/Boyd 和 Ecolab/CoolIT 的交易价格、销售额、杠杆及 accretion。
- Schneider/Motivair 的交易条款、产品组合和制造扩张。
- Delta、Asia Vital Components、Auras 的液冷产品、财务披露、上市实体、价格和流动性。
- Accelsius、Innventure、Johnson Controls、Legrand 等私营/公开代理。
- MSCI ACWI 与 iShares ACWI 的成分、估值和基准口径。
- 当前价格精确查询包括：`NYSE MOD historical stock price July 22 2026 249.64`、`Vertiv VRT stock price July 22 2026 301.16`、`nVent NVT stock price July 22 2026 158.47`、`Eaton ETN stock price July 22 2026 406.91`。

**Public pages opened/consulted**

- [Microsoft FY2026 Q3](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3)
- [Alphabet 2025 Q4](https://abc.xyz/investor/events/event-details/2026/2025-Q4-Earnings-Call-2026-Dr_C033hS6/default.aspx)
- [Amazon Q1 2026](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-First-Quarter-Results/default.aspx)
- [Alphabet–Intersect](https://abc.xyz/investor/news/news-details/2025/Alphabet-Announces-Agreement-to-Acquire-Intersect-to-Advance-U-S--Energy-Innovation-2025-DVIuVDM9wW/default.aspx)
- [NVIDIA GB200 NVL72](https://www.nvidia.com/en-us/data-center/gb200-nvl72/)
- [NVIDIA GB200 cooling technical blog](https://developer.nvidia.com/blog/?p=90182)
- [NVIDIA Vera Rubin](https://blogs.nvidia.com/blog/vera-rubin/)
- [NVIDIA Computex 2026](https://blogs.nvidia.com/blog/nvidia-gtc-taipei-computex-2026-news/)
- [NVIDIA/nVent GTC session](https://www.nvidia.com/en-us/on-demand/session/gtc26-ex82328/)
- [OCP/ASHRAE alliance](https://www.opencompute.org/blog/open-compute-project-foundation-and-ashrae-form-new-alliance)
- [Modine FY2026 10-K](https://www.sec.gov/Archives/edgar/data/67347/000110465926066795/mod-20260331x10k.htm)
- [Modine FY2026 results](https://investors.modine.com/news/news-details/2026/Modine-Reports-Fourth-Quarter-Fiscal-2026-Results/default.aspx)
- [Modine annual report PDF](https://www.sec.gov/Archives/edgar/data/67347/000110465926075698/mod-20260331xars.pdf)
- [Vertiv Q1 2026](https://investors.vertiv.com/news/news-details/2026/Vertiv-Reports-Strong-First-Quarter-with-Diluted-EPS-Growth-of-136-Adjusted-Diluted-EPS-Growth-of-83-Raises-Full-Year-Guidance/default.aspx)
- [Vertiv FY2025 results](https://investors.vertiv.com/news/news-details/2026/Vertiv-Reports-Strong-Fourth-Quarter-with-Organic-Orders-Growth-of-252-and-Diluted-EPS-Growth-of-200-Adjusted-Diluted-EPS-37/)
- [Vertiv Q1 10-Q](https://www.sec.gov/Archives/edgar/data/1674101/000162828026026556/vrt-20260331.htm)
- [Vertiv Ohio expansion](https://investors.vertiv.com/news/news-details/2026/Vertiv-to-Expand-Ohio-Manufacturing-to-Boost-U-S--Production-of-Critical-Thermal-Management-Technologies-for-AI-Data-Centers/)
- [nVent Q1 exhibit](https://www.sec.gov/Archives/edgar/data/1720635/000162828026029098/q12026nvtpressrelease.htm)
- [nVent Q1 10-Q](https://www.sec.gov/Archives/edgar/data/1720635/000162828026029370/nvt-20260331.htm)
- [nVent Blaine facility](https://investors.nvent.com/press-releases/press-release-details/2025/nVent-Expands-Data-Center-Solutions-Manufacturing-with-New-U-S--Production-Facility/default.aspx)
- [nVent/Siemens reference architecture](https://investors.nvent.com/press-releases/press-release-details/2026/Siemens-and-partners-develop-reference--architecture-purpose-built-for-NVIDIA-AI-data-centers-/default.aspx)
- [nVent cooling portfolio](https://www.nvent.com/en-mk/data-solutions/next-generation-liquid-cooling-and-power-portfolios-coming-2026)
- [Eaton completes Boyd acquisition](https://www.eaton.com/us/en-us/company/news-insights/news-releases/2026/eaton-completes-acquisition-of-leading-liquid-cooling-solutions-provider-boyd-thermal.html)
- [Eaton Q1 financials](https://www.eaton.com/content/dam/eaton/company/investor-relations/quarterly-earnings/filings/2026/q1/q1-2026-financials-only.pdf)
- [Eaton Q1 analyst presentation](https://www.eaton.com/content/dam/eaton/company/investor-relations/quarterly-earnings/filings/2026/q1/q1-2026-analyst-presentation.pdf)
- [Ecolab/CoolIT transaction exhibit](https://www.sec.gov/Archives/edgar/data/31462/000110465926032446/tm269446d1_ex99-1.htm)
- [Ecolab closes CoolIT](https://investor.ecolab.com/news/news-details/2026/Ecolab-Closes-CoolIT-Acquisition-and-Expands-AI-Cooling-Platform-as-Global-High-Tech-Business-Targets-4-Billion-by-2030/default.aspx)
- [Ecolab Q1 10-Q](https://www.sec.gov/Archives/edgar/data/31462/000110465926056737/ecl-20260331x10q.htm)
- [Schneider/Motivair transaction PDF](https://www.se.com/ww/en/assets/564/document/492190/Schneider-Electric-acquires-Motivair-Corporation.pdf)
- [Schneider liquid-cooling portfolio](https://www.se.com/ww/en/about-us/newsroom/news/press-releases/Schneider-Electric-Unveils-Liquid-Cooling-Portfolio-with-Motivair-Featuring-Dedicated-Solutions-and-Services-for-HPC-and-AI-Workloads-68d69e595c9dbb622505caf3/)
- [Schneider/Motivair 2.5MW CDU](https://www.se.com/ww/fr/about-us/newsroom/news/press-releases/motivair-by-schneider-electric-annonce-un-nouveau-cdu-avec-une-capacit%C3%A9-d%E2%80%99extension-%C3%A0-10-mw-et-plus-697204a671fa0adfeb07812b/)
- [Delta chairman statement](https://www.deltaww.com/en-US/investors/chairman-statement)
- [Delta liquid-cooling product release](https://landing.deltaww.com/en-US/news/39632)
- [Delta press release](https://www.deltaww.com/en-US/press/40334)
- [Auras product disclosure](https://www.auras.com.tw/News/NewsContent/14-10)
- [Accelsius Series B](https://accelsius.com/series-b-announcement/)
- [MSCI ACWI](https://www.msci.com/indexes/index/892400/msci-acwi-index)
- [iShares ACWI](https://www.ishares.com/us/products/239600/ishares-msci-acwi-etf)
- [MOD market data](https://www.financialcontent.com/quote/NY%3AMOD/historical)
- [VRT market data](https://www.ktiv.marketminute.com/quote/NY%3AVRT/historical)
- [NVT market data](https://www.macrotrends.net/stocks/charts/NVT/nvent-electric/stock-price-history)
- [Delta historical data](https://ms.investing.com/equities/delta-electron-historical-data)
- [Delta market capitalization](https://companiesmarketcap.com/delta-electronics/marketcap/)
