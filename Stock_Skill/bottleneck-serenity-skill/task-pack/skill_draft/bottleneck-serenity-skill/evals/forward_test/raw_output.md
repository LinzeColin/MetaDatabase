## 1. 决策

**`BOTTLENECK_NOT_EQUITY`** —— 无菌注射 fill-finish 与给药组件仍是必要且高监管门槛的产业能力，但截至 2026-07-23，**当前稀缺、24 个月持续性、上市公司租金转化、预期差**四个非补偿闸门没有同时通过。

研究窗口为 2026-07-23 至 2028-07-23；流动性入口为全球普通股/ADR、市值至少 20 亿美元、近 30 日平均成交额至少 1,000 万美元。无法可靠验证流动性的公司按未通过处理。比较基准为 MSCI ACWI Net Return USD。结论置信度：**medium**。

## 2. Funded demand

已确认的增量支付来源包括 Medicare GLP-1 Bridge：2026-07-01 至 2027-12-31，为符合条件的 Part D 受益人提供部分 GLP-1 药物，患者月 copay 50 美元，由中央处理器完成事前授权、理赔和药房付款。它是实际投入运行、但在本研究期结束前到期的短期项目，而不是永久覆盖承诺。[CMS Medicare GLP-1 Bridge](https://www.cms.gov/medicare/coverage/prescription-drug-coverage/medicare-glp-1-bridge)

支付链为：

`资格/适应症 → 事前授权 → 处方 → 中央理赔或保险结算 → 药房 → 患者`

需求失败条件包括：资格范围收紧、项目不延期、支付方以更低净价换取覆盖、口服制剂吸收新增患者，以及处方增长未能转化为注射剂量增长。

## 3. Role-neutral system map

`支付方 → 处方 → API/制剂 → 给药路径选择`

- 注射路径：`无菌配液 → aseptic fill-finish → 容器/密封件 → 药筒或预充针 → 笔/自动注射器 → 组装包装 → 分销`
- 口服路径：`片剂制造 → 瓶装/泡罩 → 分销`

角色映射：

- `owner`：分子、品牌、适应症和定价权。
- `unlocker`：合格无菌产能、验证工艺与监管批准。
- `tollbooth`：高价值弹性体、药筒、预充针和已验证器械平台。
- `absorber`：承担扩产资本、启动损失、营运资金及价格压缩的节点。
- `substitute`：口服制剂、多剂量装置、替代给药方式和双供。
- `public_proxy`：高度多元化、但主题收入无法单独识别的上市 CDMO 或医疗器械公司。

无菌 fill-finish 和注射组件对“注射路径”是强制的，但对整个 incretin 治疗系统并非不可绕开。[FDA aseptic-processing guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/sterile-drug-products-produced-aseptic-processing-current-good-manufacturing-practice)、[FDA combination products](https://www.fda.gov/combination-products)

## 4. Constraint proof

| 约束检验 | 结论 | 证据 |
|---|---|---|
| 架构必要性 | 通过，仅限注射路径 | 无菌 CGMP、容器完整性及 drug-device 组合要求形成真实资格壁垒。 |
| 当前紧缺 | **不通过** | FDA 分别认定 semaglutide 和 tirzepatide 注射剂供应满足或超过当前及预计需求；EMA 也把 Ozempic 标为 shortage resolved。[FDA semaglutide decision](https://www.fda.gov/media/185526/download)、[FDA tirzepatide decision](https://www.fda.gov/media/185577/download)、[EMA Ozempic shortage register](https://www.ema.europa.eu/en/medicines/human/shortages/ozempic) |
| 难替代性 | 部分通过 | 已验证组件不能随意切换，但整个节点可被口服制剂绕过。 |
| 24 个月持续性 | **未通过** | 已获批口服 GLP-1 直接消除每位口服患者的无菌灌装、注射容器和器械含量。[FDA oral GLP-1 approval](https://www.fda.gov/news-events/press-announcements/fda-approves-first-new-molecular-entity-under-national-priority-voucher-program)、[EMA oral Wegovy opinion](https://www.ema.europa.eu/en/news/meeting-highlights-committee-medicinal-products-human-use-chmp-18-21-may-2026) |

因此，证据证明了“能力重要、资格困难”，没有证明“未来 24 个月仍供不应求并能持续提价”。

## 5. Security map

以下按角色列示，不代表证券排序或交易指令。

| 证券 | 角色与主题证据 | 流动性/股东价值结论 |
|---|---|---|
| AptarGroup（NYSE: ATR） | `tollbooth`；2025 Q4 注射业务增长 24%，主要由 GLP-1 弹性体和服务驱动；2026 Q1 注射业务继续双位数增长。[季度披露](https://investors.aptar.com/financials/quarterly-results/default.aspx) | 近 30 日成交额约 6,100 万美元，过流动性门；但未披露 GLP-1 收入占比、增量利润或主题 FCF，严格标签仍是 `BOTTLENECK_NOT_EQUITY`。[市场快照，二手](https://chartexchange.com/symbol/nyse-atr/) |
| West Pharmaceutical Services（NYSE: WST） | `tollbooth`；GLP-1 弹性体占 2025 Q2 公司收入 8%，2026 Q1 GLP-1 收入双位数增长。[Q2 2025](https://www.sec.gov/Archives/edgar/data/105770/000010577025000062/westq22025presentation-f.htm)、[Q1 2026](https://investor.westpharma.com/news-releases/news-release-details/west-reports-first-quarter-2026-results) | 流动性充足、披露最好，但 8% 只是单季比例，无法桥接到全年每股 FCF；估值已反映较强增长。 |
| Stevanato Group（NYSE: STVN） | `tollbooth`；2026 Q1 GLP-1 约占收入 21%–22%，是最高纯度上市证据之一。[Q1 2026](https://ir.stevanatogroup.com/news-events/press-releases/detail/178/stevanato-group-delivers-7-revenue-growth-10-at-constant) | Q1 FCF 仅 550 万欧元，净债务 3.377 亿欧元且仍在重资本扩产；本轮未验证通过成交额门槛，排除严格流动性名单。 |
| Ypsomed（SIX: YPSN） | `tollbooth`；长期大批量自动注射器合同、客户参与扩产；2025/26 Delivery Systems 收入 6.015 亿瑞郎、EBIT margin 32.5%。[合同](https://www.ypsomed.com/en/investors/ad-hoc-announcements/ad-hoc-detail-page/ypsomed-concludes-a-long-term-supply-agreement-for-large-quantities-of-autoinjectors)、[FY2025/26](https://www.ypsomed.com/en/investors/ad-hoc-announcements/ad-hoc-detail-page/ypsomed-grows-20-in-core-business-and-wins-record-number-of-customer-projects) | 商业质量强，但 GLP-1 收入占比未披露，固定资产投资达 2.956 亿瑞郎；未验证通过成交额门槛。 |
| SCHOTT Pharma（Xetra: 1SXP） | `tollbooth`；GLP-1 预充玻璃针需求强。 | 同期 DDS 收入反而下降 5.4%，并出现聚合物针筒产能利用不足和客户专用玻璃针减值，构成“需求强但不稀缺”的直接反证。[H1 2026](https://ir.schott-pharma.com/investor-relations/news/schott-pharma-with-robust-first-half-of-the-year-and-strong-cash-flow/9602030d-565b-41c2-b4f1-2613e694b0e8) |
| TMO、LONN、SFZN、BDX、4543、8086 | `public_proxy`；具备 fill-finish、预充针或注射器能力。 | 主题收入没有单独披露，业务多元化稀释敏感度；均无法完成 incretin 约束到每股 FCF 的桥。 |
| LLY、NOVO-B/NVO | `owner/absorber/substitute` | 是直接药物 IP、销量、价格和管线敞口，而非供应链瓶颈证券。 |
| Catalent | 原上市 fill-finish 纯度较高的入口 | 2024 年被收购并退市，三个 fill-finish 工厂随后转入药物所有者体系，已无上市证券入口。[Catalent completion](https://www.catalent.com/catalent-news/novo-holdings-completes-acquisition-of-catalent/) |

## 6. Equity capture

四闸门结果：

| 闸门 | 结果 |
|---|---|
| 约束真实 | **部分通过**：必要且高门槛，但当前紧缺不成立。 |
| 持续时间 | **失败**：扩产、内生化及口服路径均在 24 个月内发生。 |
| 股权租金捕获 | **失败**：没有流动性上市供应商提供完整的主题收入→利润→FCF→完全摊薄每股 FCF 桥。 |
| 预期差 | **失败/未证实**：披露最好的代理估值较高；估值较温和的代理又缺少主题收入占比。 |

以 WST 作为“披露最充分的流动性代理”进行严格桥接：

- 2025 年公司整体 CFO 7.548 亿美元、capex 2.859 亿美元，整体 FCF 为 4.689 亿美元；摊薄股数 7,270 万股，整体 FCF/股约 6.45 美元。[WST 2025 10-K](https://www.sec.gov/Archives/edgar/data/105770/000010577026000010/wst-20251231.htm)
- 这些是**集团数据**，不能替代 GLP-1 主题 FCF。
- 未验证乘数：全年主题收入、增量毛利、专属 capex、营运资金、合同价格/数量承诺。
- 因此 `equity_bridge.complete=false`，并触发 `hard_flags.no_material_revenue_bridge=true`。

Skill 评分结果：constraint 67.5、capture 77.0、mispricing 32.0、evidence 92.5、investability 83.5；最终 42.29/100。硬闸门覆盖数值评分，标签仍为 `BOTTLENECK_NOT_EQUITY`。

## 7. Three clocks

以下为模型判断区间，不是假精确预测：

| 时钟 | P10 / P50 / P90 | 解读 |
|---|---:|---|
| 物理稀缺持续期 | 0 / 6 / 24 个月 | P50 仅反映可能出现的局部、阶段性组件摩擦；没有当前全国性短缺起点。 |
| 货币化滞后 | 0–3 个月 | 流动性组件代理已经在收入中体现 GLP-1 增长。 |
| 市场发现 | 0–3 个月 | GLP-1 已被公司明确披露，主题并不隐蔽。 |
| P50 可货币化 runway | 约 6 个月 | 不足以支撑一个清晰的 24 个月结构性稀缺交易。 |

## 8. Valuation

MSCI ACWI 在 2026-06-30 有 2,461 个成分股、覆盖约 85% 全球可投资股票，forward P/E 17.78 倍。[MSCI ACWI](https://www.msci.com/indexes/index/892400/msci-acwi-index)

WST 在 2026-07-22 的二手市场价格快照为 358.41 美元：[价格快照](https://public.com/stocks/wst/after-hours)。

- 集团 trailing P/FCF：约 55.6 倍。
- 以 2026 adjusted EPS 指引 8.40–8.75 美元计算：约 41.0–42.7 倍。
- 与 ACWI forward P/E 仅作方向性比较，因为 adjusted EPS 与指数口径并不完全一致。

ATR 的 2025 GAAP EPS 为 5.89 美元，按约 128.88 美元价格约 21.9 倍 trailing P/E；估值明显温和于 WST，但缺失主题收入和 FCF 桥。[ATR FY2025](https://investors.aptar.com/news/news-details/2026/Aptar-Reports-Fourth-Quarter-and-Annual-2025-Results/default.aspx)

WST 24 个月分析情景，不是目标价：

| 情景 | 概率 | 总回报假设 | 因果路径 |
|---|---:|---:|---|
| Bear | 30% | -35% | 供应正常化、口服替代、估值压缩。 |
| Base | 50% | +5% | 组件增长被估值回归抵消。 |
| Bull | 20% | +30% | 注射销量与高价值组件 mix 显著超预期。 |

概率加权回报为 **-2%**；当前价格不提供已验证的正向非对称性。

## 9. Catalysts

- **2026-07-23**：WST 已安排发布 Q2 结果；截至本次抓取尚未检索到正式结果页，应立即核对是否新增 GLP-1 收入占比、订单、利用率和 capex 披露。[发布安排](https://investor.westpharma.com/news-releases/news-release-details/west-host-second-quarter-2026-conference-call)
- **2026-08-04**：STVN Q2 2026，重点检查 GLP-1 占比、Fishers/Latina 利用率、FCF。[公告](https://ir.stevanatogroup.com/news-events/press-releases/detail/181/stevanato-group-to-report-second-quarter-2026-financial)
- **2026-08-12**：SCHOTT Pharma 9M 更新，检查 DDS 利用率和减值是否延续。
- **2027-01-31**：首次正式复核短缺状态、口服份额和 FY2026 主题桥。
- **2027-12-31**：现行 Medicare Bridge 到期，是 funded-demand 持续性的硬检查点。

## 10. Red team 与负面检索

最强相反论点是：药品短缺消失不等于合格组件不紧；新增 fill-finish 线可能快于弹性体、药筒和自动注射器资格扩张；口服产品可能扩大总体市场而非蚕食注射。支持该论点的证据包括 WST/ATR 双位数增长、STVN 21%–22% GLP-1 收入和 Ypsomed 的长期器械合同。

但负面检索发现：

- 领先药物所有者已把 fill-finish 和器械产能内生化。一个所有者 2025 年 PP&E capex 达 601 亿丹麦克朗，2026 年预计 550 亿丹麦克朗，并整合三个原 Catalent 工厂。[供应链扩产](https://annualreport.novonordisk.com/2025/strategic-aspirations/commercial-execution.html)、[资本支出](https://annualreport.novonordisk.com/2025/strategic-aspirations/financial-performance.html)
- 另一所有者在 10-K 中列出多地扩产，并于 2026 年宣布超过 35 亿美元的新注射药物及器械厂。[10-K](https://www.sec.gov/Archives/edgar/data/59478/000005947826000013/lly-20251231.htm)、[Pennsylvania facility](https://investor.lilly.com/news-releases/news-release-details/lilly-selects-pennsylvania-home-its-newest-injectable-medicine)
- 口服产品已有真实放量：Wegovy pill 上市五个月超过 300 万张处方，且公司披露超过 80% 新处方来自此前未使用 GLP-1 的患者。后者支持“扩大市场”，同时也证明口服路径已具规模，净替代率仍未解决。[口服处方披露](https://www.novonordisk.com/news-and-media/news-and-ir-materials/news-details.html?id=916566)
- SCHOTT 已出现产能利用不足和客户专用资产减值。
- Gerresheimer 曾因收入确认调查推迟年报；即使后来完成审计和更正，也不满足低治理风险入口。[Gerresheimer 2026 update](https://www.gerresheimer.com/en/customer/company/news/detail/gerresheimer-publishes-2025-annual-and-consolidated-financial-statements-stable-revenue-in-a-challenging-financial-year)

因此，反方情形可信但尚未越过“组件销量增长”到“稀缺租金及每股价值”的关键断点。

## 11. Kill switches

推翻当前否定结论、升级研究，必须至少满足：

1. FDA 或 EMA 因**制造产能**而非分销摩擦重新列入主要 incretin 注射剂短缺，并连续两个按月快照维持。
2. 某个通过流动性门槛的供应商披露主题收入至少 15%，并给出可重建的主题毛利、capex、营运资金、税息和完全摊薄每股 FCF。
3. 同一供应商拥有至少 18 个月合同需求，并同时披露利用率超过 90%、交付期超过 12 个月或连续两个季度价格提升超过 5%。
4. 在上述基本面成立后，估值不超过 ACWI forward P/E 的 1.25 倍，或建模预期回报超过 15%且无需 bull case 才避免损失。

停止跟踪的条件：

- 2027-01-31 前没有制造型短缺复发，且 FY2026 后主题每股 FCF仍不可重建；
- 口服产品连续两个季度超过新增 incretin starts 的 25%，且总市场扩张不足以抵消注射份额下降；
- 组件利用率、交付期或价格转弱，同时供应商继续以负 FCF 扩产。

上述比例是预先声明的研究阈值，不是已观察事实。

## 12. Portfolio fit

这是因果重叠矩阵，不是仓位建议：

|  | ATR | WST | STVN/YPSN | TMO/LONN |
|---|---:|---:|---:|---:|
| ATR | — | 高 | 高 | 中 |
| WST | 高 | — | 高 | 中 |
| STVN/YPSN | 高 | 高 | — | 中 |
| TMO/LONN | 中 | 中 | 中 | — |

共同根驱动是“有支付能力的注射剂量”；共同次级风险是口服替代、客户内生化、GLP-1 净价下降和头部客户集中。持有多个组件代码不会自然形成独立分散。

## 13. Open questions / unresolved claims

- WST 和 ATR 的全年 incretin 收入、增量毛利、专属 capex 与营运资金是多少？
- 组件交付期、产能利用率和合格供应商份额是否真的紧张？
- 口服新增患者中，多少最终转为维持治疗，多少替代注射？
- 药物所有者的 fill-finish、器械和组件外包比例正在上升还是下降？
- STVN、YPSN、SCHOTT Pharma 是否能以主要上市地数据稳定通过成交额门槛？
- 2026-07-23 当日 WST Q2 正式披露是否在本次抓取之后发布？

“组件存在独立短缺”“口服会净蚕食注射”“供应商拥有可持续提价权”三项仍属未解决主张，不应被当作事实。

## 14. 核心证据索引

- C-001 funded demand：[CMS](https://www.cms.gov/medicare/coverage/prescription-drug-coverage/medicare-glp-1-bridge)、[Q1 volume/price evidence 1](https://investor.lilly.com/node/54176)、[Q1 volume/price evidence 2](https://www.novonordisk.com/content/nncorp/global/en/news-and-media/news-and-ir-materials/news-details.html?id=916542)
- C-002 shortage resolution：[FDA semaglutide](https://www.fda.gov/media/185526/download)、[FDA tirzepatide](https://www.fda.gov/media/185577/download)、[EMA Ozempic](https://www.ema.europa.eu/en/medicines/human/shortages/ozempic)
- C-003 qualification barrier：[FDA aseptic CGMP](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/sterile-drug-products-produced-aseptic-processing-current-good-manufacturing-practice)、[EU EudraLex Volume 4](https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en)
- C-004 capacity response：[Novo 2025 annual report](https://annualreport.novonordisk.com/2025/strategic-aspirations/commercial-execution.html)、[Lilly 2025 10-K](https://www.sec.gov/Archives/edgar/data/59478/000005947826000013/lly-20251231.htm)
- C-005 oral bypass：[FDA](https://www.fda.gov/news-events/press-announcements/fda-approves-first-new-molecular-entity-under-national-priority-voucher-program)、[EMA](https://www.ema.europa.eu/en/news/meeting-highlights-committee-medicinal-products-human-use-chmp-18-21-may-2026)
- C-006 liquid proxy disclosure：[WST Q2 2025](https://www.sec.gov/Archives/edgar/data/105770/000010577025000062/westq22025presentation-f.htm)、[WST Q1 2026](https://investor.westpharma.com/news-releases/news-release-details/west-reports-first-quarter-2026-results)
- C-007 benchmark：[MSCI ACWI](https://www.msci.com/indexes/index/892400/msci-acwi-index)

## Inline machine-readable decision object

```json
{
  "schema_version": "1.0",
  "skill_version": "0.0.0.1",
  "thesis_id": "incretin-fill-finish-devices-global-20260723",
  "as_of": "2026-07-23",
  "source_cutoff": "2026-07-23",
  "previous_version": null,
  "mode": "scan",
  "research_contract": {
    "horizon_months": 24,
    "universe": "Global listed common shares and ADRs; market cap >= USD 2bn and trailing-30-day average daily traded value >= USD 10m; unverifiable liquidity treated as a fail",
    "benchmark": "MSCI ACWI Net Return USD",
    "research_only": true,
    "leverage": false,
    "derivatives": false,
    "automatic_trading": false
  },
  "decision": {
    "label": "BOTTLENECK_NOT_EQUITY",
    "one_sentence": "Sterile fill-finish and delivery components remain mandatory regulated capabilities, but current scarcity, 24-month duration, liquid-equity rent capture and expectation-gap gates do not all pass.",
    "confidence": "medium",
    "final_score": 42.29,
    "hard_gates_passed": false
  },
  "theme": {
    "funded_demand": "Funded volume is expanding, including a time-limited Medicare bridge, while realized prices are falling.",
    "payer": "Public programs, commercial insurance and self-pay; only the Medicare bridge is treated as a dated committed program.",
    "horizon_months": 24
  },
  "constraint": {
    "function": "Qualified aseptic fill-finish plus injectable container-closure and self-injection-device components",
    "archetype": "unlocker_and_tollbooth",
    "proof": ["C-002", "C-003"],
    "resolution_paths": [
      "owner insourcing and capacity expansion",
      "additional qualified suppliers",
      "oral formulations",
      "device redesign and dual sourcing"
    ]
  },
  "candidate": {
    "ticker": "WST",
    "company": "West Pharmaceutical Services, Inc.",
    "market": "NYSE",
    "role": "tollbooth",
    "exposure_materiality": "GLP-1 elastomer products were 8% of Q2 2025 company revenue; full-year theme revenue and theme FCF are undisclosed"
  },
  "clocks": {
    "scarcity_p10_months": 0,
    "scarcity_p50_months": 6,
    "scarcity_p90_months": 24,
    "monetization_lag_months": 0,
    "market_discovery_months": 0,
    "monetizable_runway_months": 6
  },
  "valuation": {
    "currency": "USD",
    "price_snapshot": 358.41,
    "price_snapshot_date": "2026-07-22",
    "group_trailing_fcf_per_share": 6.45,
    "group_trailing_price_to_fcf": 55.6,
    "guided_2026_adjusted_eps_multiple_low": 41.0,
    "guided_2026_adjusted_eps_multiple_high": 42.7,
    "benchmark_forward_pe": 17.78,
    "scenario_probabilities": {
      "bear": 0.3,
      "base": 0.5,
      "bull": 0.2
    },
    "bear_return_pct": -35,
    "base_return_pct": 5,
    "bull_return_pct": 30,
    "expected_return_pct": -2
  },
  "equity_bridge": {
    "complete": false,
    "revenue": null,
    "free_cash_flow": null,
    "fully_diluted_shares": 72.7,
    "per_share_fcf": null,
    "cash_conversion_checks": {
      "capex": false,
      "working_capital": false,
      "interest": true,
      "tax": true
    },
    "dilution_checks": {
      "stock_based_compensation": true,
      "convertibles": true,
      "warrants": true,
      "other_contingent_shares": true
    },
    "unverified_critical_multipliers": [
      "full-year incretin-component revenue",
      "incremental margin and cash conversion",
      "capacity-specific capex and working-capital allocation",
      "contract pricing and volume commitments"
    ]
  },
  "scores": {
    "constraint": 67.5,
    "capture": 77.0,
    "mispricing": 32.0,
    "evidence": 92.5,
    "investability": 83.5
  },
  "hard_flags": {
    "no_material_revenue_bridge": true
  },
  "catalysts": [
    {
      "date": "2026-08-04",
      "event": "Stevanato Q2 2026 results"
    },
    {
      "date": "2026-08-12",
      "event": "SCHOTT Pharma 9M 2026 update"
    },
    {
      "date": "2027-01-31",
      "event": "First formal thesis review"
    },
    {
      "date": "2027-12-31",
      "event": "Current Medicare GLP-1 Bridge end date"
    }
  ],
  "kill_switches": [
    "Upgrade only if a regulator-verified manufacturing-capacity shortage recurs for two consecutive monthly snapshots.",
    "Upgrade only if a liquid supplier discloses at least 15% theme revenue and a reconstructable theme-specific per-share FCF bridge backed by at least 18 months of contracted demand.",
    "Close monitoring if no qualifying shortage recurs by 2027-01-31 and theme-specific per-share FCF remains non-reconstructable after FY2026 filings.",
    "Close the injectable-bottleneck thesis if oral products exceed 25% of new incretin starts for two consecutive quarters without faster total-market expansion."
  ],
  "portfolio_tags": {
    "root_driver": "funded incretin treatment volume",
    "secondary_drivers": [
      "injectable share",
      "qualification barriers",
      "capacity utilization",
      "payer price",
      "oral substitution"
    ],
    "overlap_warning": "WST, ATR, STVN and YPSN share the same injectable-volume and top-customer root drivers; multiple tickers do not create independent diversification.",
    "position_or_order": null
  },
  "open_questions": [
    "What are full-year incretin-specific revenue, gross margin, capex and working-capital requirements for WST and ATR?",
    "Are qualified component lead times and utilization actually tight, and for how long?",
    "What share of new starts and maintenance therapy will be oral versus injectable after four reported quarters?",
    "What portion of owner fill-finish and device volume remains externally sourced?",
    "Which higher-purity names satisfy the stated liquidity floor on primary-market data?"
  ],
  "evidence_file": null,
  "evidence": {
    "validation": {
      "valid": true,
      "claim_count": 8,
      "errors": 0,
      "warnings": 0
    },
    "claims": [
      {"id": "C-001", "type": "fact", "critical": true, "status": "supported"},
      {"id": "C-002", "type": "fact", "critical": true, "status": "supported"},
      {"id": "C-003", "type": "fact", "critical": true, "status": "supported"},
      {"id": "C-004", "type": "fact", "critical": true, "status": "supported"},
      {"id": "C-005", "type": "fact", "critical": true, "status": "supported"},
      {"id": "C-006", "type": "fact", "critical": false, "status": "supported"},
      {"id": "C-007", "type": "fact", "critical": false, "status": "supported"},
      {
        "id": "C-008",
        "type": "inference",
        "critical": true,
        "status": "supported",
        "depends_on": ["C-001", "C-002", "C-003", "C-004", "C-005", "C-006", "C-007"]
      }
    ]
  }
}
```

仅供研究；不构成买卖、杠杆、衍生品或自动交易指令。

交付状态：**100%**。已完成来源截止、四闸门、三时钟、上市证券映射、估值、反证、kill switches、机器对象及校验；未完成项：无。预计剩余迭代：0；整体置信度：中高。推荐下一步：在正式取得 2026-07-23 WST Q2 披露后，仅更新 C-006、equity bridge 和估值，不重跑无关研究。

## Execution trace

- Skill-relative files read:
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
  - `scripts/score_opportunity.py`
  - `scripts/validate_evidence.py`
  - `scripts/analyze_portfolio_clusters.py`

- Scripts/commands run and outputs:
  - `find ...` / `wc -l ...` / `sed ...` / `tail ...`: Skill inventory and full relevant instruction/schema inspection completed.
  - `python3 scripts/score_opportunity.py - --format json`: `BOTTLENECK_NOT_EQUITY`; final score `42.29`; hard gates `false`; warnings `[]`.
  - `python3 scripts/validate_evidence.py - --strict-warnings`: `valid=true`; 8 claims; 0 errors; 0 warnings.
  - Inline decision JSON syntax check: `decision_json_valid BOTTLENECK_NOT_EQUITY 42.29 8`.

- Web searches:
  - FDA/EMA semaglutide, tirzepatide and GLP-1 shortage resolution/status.
  - CMS Medicare GLP-1 Bridge and BALANCE payer mechanics.
  - FDA aseptic-processing, combination-product and device qualification rules.
  - Oral GLP-1 approvals, launches and prescription uptake.
  - Incretin-owner volume/price, capex, fill-finish and device expansion.
  - Catalent ownership, fill-finish asset transfer and delisting.
  - WST, ATR, STVN, YPSN, SCHOTT Pharma and Gerresheimer exposure/financials.
  - TMO, Lonza, Siegfried, BDX, Terumo and Nipro public-proxy exposure.
  - WST/ATR/STVN/SCHOTT Q2–Q3 2026 reporting schedules.
  - WST, ATR, STVN, TMO, BDX and ACWI market-data snapshots.
  - MSCI ACWI benchmark composition and valuation.

- Public pages opened:
  - CMS GLP-1 Bridge and BALANCE pages.
  - FDA semaglutide and tirzepatide shortage decisions; aseptic CGMP, combination-product, early-development and Foundayo approval pages.
  - EMA Ozempic shortage register, January 2026 SPOC materials and May 2026 CHMP update.
  - Novo Nordisk 2025 annual-report financial/commercial pages, Q1 2026, oral approval and prescription-update pages.
  - Lilly 2025 10-K, Q1 2026, oral approval and Pennsylvania/Indiana capacity announcements.
  - Catalent acquisition completion and 2026 ownership clarification.
  - WST 2025 10-K, Q2 2025 presentation, Q1 2026 results, proxy, press-release index and Q2 reporting notice.
  - Aptar FY2025 and Q1 2026 results.
  - STVN FY2025/Q1 2026 materials and Q2 reporting notice.
  - Ypsomed supply agreement and FY2025/26 results.
  - SCHOTT Pharma FY2025/H1 2026 results.
  - Gerresheimer 2026 financial-statement updates.
  - TMO 2025 filing, Lonza 2025 annual-report pages and Siegfried 2025 materials.
  - MSCI ACWI index/fact-sheet and iShares ACWI pages.
  - Secondary WST and ATR price/liquidity pages.

- Files written: none.
