# 公开研究报告：股票商业机会拆解 Skill

> 研究快照：2026-07-19。范围为公开可访问的官方监管/交易所页面、项目官方 GitHub/文档和产品官方页面。产品功能、许可、价格和监管解释会变化，实际使用必须同次复核。本文只抽象公开模式，没有复制第三方代码、提示词、数据或付费内容。

## 1. 研究问题

本轮不问“有没有 AI 炒股软件”，而问七个更具体的问题：

1. 哪些系统能把公开披露和市场数据接入研究？
2. 哪些能从主题或行业变化发现候选？
3. 哪些能证明 theme → issuer exposure → financial capture，而不是只生成报告？
4. 哪些处理 current expectations、valuation、catalyst 和 falsifier？
5. 哪些系统把确定性计算与 LLM 叙事分开？
6. 哪些偏交易执行，因而不适合作为安全的 research-triage 基线？
7. 在公开、专有 MetaDatabase 中，什么可以合法、安全、低成本地保存？

检索分五轮：v1/v2 谱系审计；监管与官方披露入口；开源数据/财报工具；开源金融 Agent/交易系统；商业研究终端与反证。搜索摘要只做定位，核心结论来自打开后的页面。

## 2. 结论先行

没有发现一个公开项目同时以轻量 Codex Skill 形式强制执行以下完整门禁：

```text
商业价值池
→ 价值链受益者
→ 已核验上市证券
→ 可量化发行人敞口
→ 订单/收入/利润/现金流捕获
→ 当前预期和估值
→ 催化、下行和证伪
→ 只批准下一研究，不批准交易
```

这是基于下述样本的设计差异推断，不是“市场上绝不存在同类产品”的穷尽性证明。

现有系统大致分为四层：

- **披露/数据基础设施**：SEC EDGAR、ASX/company announcements、OpenBB、EdgarTools；擅长拿到数据，不替用户定义商业敞口证据门禁。
- **研究 Agent/报告生成**：FinRobot、AlphaSense 等；擅长聚合、分析和报告，但通常需要真实数据供应商、密钥、许可或更重运行时。
- **筛选/终端**：Koyfin、TIKR 等；擅长财务、估值、consensus、筛选和监控，数据很有价值但多为专有服务，不能把受限数据固化进公开 Skill。
- **交易型多 Agent**：TradingAgents 等；面向 ticker 级交易决定/记忆/回测，与本项目“无账户、无执行、只做研究门禁”的安全边界不同。

因此 v3 应是这些系统的**上游研究资格层和证据合同**，而不是复制终端、数据 API、估值引擎或交易 Agent。

## 3. 官方事实与监管边界

### 3.1 披露优先于搜索结果

[SEC EDGAR](https://www.sec.gov/search-filings) 是美国公司法定披露的官方检索入口；[SEC 关于 EDGAR](https://www.sec.gov/submit-filings/about-edgar)说明其用于接收、验证、索引和公开公司提交。美国发行人身份、10-K/10-Q/8-K 和 XBRL 相关核心事实应从此类一手披露开始。

澳洲发行人应优先核对 [ASX company announcements](https://www.asx.com.au/asx/v2/statistics/todayAnns.do)、公司正式公告和 ASIC 材料。ASX 页面/公告可能带商业使用限制，v3 只保存链接、source metadata、最小释义和用户自己生成的 claim，不批量再分发公告正文。

设计映射：`source register` 要记录 source_type、access_level、issuer、period、currency/units 和 retrieved_at；snippet-only 不能支持 core exposure claim。

### 3.2 “研究”措辞不能自动规避金融服务边界

[ASIC INFO 269](https://asic.gov.au/regulatory-resources/financial-services/giving-financial-product-advice/discussing-financial-products-and-services-online/)指出，在线讨论金融产品可能因内容和情境构成金融产品建议或其他受监管服务。免责声明不能修复实质上的个性化交易指令或误导陈述。

[Investor.gov 的社交媒体股票骗局提示](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/social-media-stock-scams)把社交荐股和保证收益等作为风险信号。设计上，social/price momentum 只能发现线索；个性化 buy/sell/hold、仓位、保证收益、自动下单和疑似 MNPI 一律阻断。

## 4. 开源项目研究

### 4.1 OpenBB：数据连接层，不是机会归因门禁

[OpenBB](https://github.com/OpenBB-finance/OpenBB)把 Open Data Platform 描述为连接 proprietary/licensed/public data、供 Python、REST、Excel、研究 dashboard 和 AI agent 使用的基础设施；官方开发文档也将 core/providers/toolkits 分层。它说明“数据 provider 可插拔”是正确的平台方向。

可借鉴：provider provenance、标准化输出、数据层和研究层分离。不能直接搬入：OpenBB 是重依赖平台且仓库当日为 AGPLv3；本包不复制其代码，也不把数据连接作为 v3 的必要运行时。当前用户还明确要求不安装。

### 4.2 EdgarTools：SEC 解析可增强 E2/E3，但不替代商业逻辑

[EdgarTools](https://github.com/dgunning/edgartools)提供 SEC filing、XBRL、ticker/CIK、exchange 和多期财务的 Python 结构化访问，并强调 rate-limit/caching 和 typed objects。它非常适合作为未来美国发行人 exposure/capture 的可选数据适配层。

差距：结构化 filing 仍不能自动证明某产品/segment 与主题的经济关联，也不能替代 expectations/valuation/catalyst 判断。v3 只定义所需字段和门禁；不增加第三方依赖。其当日仓库标示 MIT，但任何未来集成都必须固定版本并复核 SEC user-agent/rate policy。

### 4.3 FinRobot：确定性数字与 LLM 叙事分工值得吸收

[FinRobot](https://github.com/AI4Finance-Foundation/FinRobot)公开描述了财务数据获取、预测/DCF/peer、多个专业 Agent 和报告生成；当前 README 还强调财务数字由 Python 计算、LLM 用于推理/综合/解释并保留 provenance。

可借鉴：numbers-by-code、narrative-by-LLM、role separation、provenance。差距：它是完整应用，需要 API keys/providers 和更重依赖，且覆盖模型/估值/报告/交易等更广范围。v3 保留纯标准库 scorer 与 validator，只把候选路由到下游模型，不伪装成已运行估值。仓库当日标示 Apache-2.0；本包没有复制其实现。

### 4.4 TradingAgents：多角色红队有用，交易决定和持久记忆不适用

[TradingAgents](https://github.com/TauricResearch/TradingAgents)是基于 LangGraph 的多 Agent 金融交易框架，可按 ticker 运行并形成决定，还支持持久 decision log/checkpoint。多角色 analyst/bull/bear/risk debate 对 countercase 有启发。

但直接采用会引入三个错位：输出趋向交易决定；需要 LLM/data provider 运行时；默认持久化 ticker memory/cache，违背本任务“本地无安装/无负担”和最小数据保留边界。v3 只保留 first rejection、falsifiers 和单写者综合，不创建交易记忆。仓库当日标示 Apache-2.0；无代码复用。

## 5. 商业研究软件研究

### 5.1 AlphaSense

[AlphaSense 平台](https://www.alpha-sense.com/platform/)公开展示了跨公司/主题文档搜索、cited generative research、monitoring、financial data 和 workflow agents。其产品形态说明 source-backed synthesis、持续监控和企业内部知识整合具有真实价值。

边界：这是专有服务与内容库。v3 只抽象“source-backed answer、monitoring trigger、public/private plane”，不复制内容、数据或 Agent 配置，也不声称免费 Skill 能替代其覆盖。

### 5.2 Koyfin

[Koyfin equity research](https://www.koyfin.com/for-investors/equity-research/)强调财务、估值指标、图表、screening、news、alerts 和 watchlists。它说明 current market fields 与持续 watch condition 是股票研究不可省略的一层。

边界：实时/历史数据和下载分享受产品条款约束；公开 v3 不打包 Koyfin 数据。无 provider/timestamp 时只允许 `UNKNOWN/STALE` 和降级。

### 5.3 TIKR

[TIKR stock analysis](https://www.tikr.com/analyze-stocks)覆盖全球 screening、财务、估值、analyst forecasts、filings/transcripts、portfolio monitoring 和 valuation builder；其 [Estimates 说明](https://support.tikr.com/hc/en-us/articles/39071375390235-How-do-I-use-TIKR-s-Estimates-feature)还区分历史 actuals 与聚合 forward estimates，并展示 analyst count 和 revision trends。

可借鉴：consensus provider/as-of、analyst count、actual-vs-estimate、revision path。边界：数据深度与订阅层相关，且 forward estimates 不是事实。v3 要把 provider、timestamp、GAAP/adjusted 口径和 estimate 类型显式记录，不复制受限数据。

## 6. 为什么 v3 不直接构建更重系统

本任务的最高 ROI 是建立**错误不可悄悄通过的合同**，而不是先接几十个 provider：

1. 无 identity 先停，避免研究错证券。
2. 无 filing-backed quantified exposure 不高于 E1/SCREEN_FLAG。
3. 无 financial capture 不把主题受益写成 earnings 受益。
4. 无 current expectations/valuation/catalyst 不进入 ADVANCE_RESEARCH。
5. 无 falsifier/liquidity/source freshness 不到 E5。
6. 所有状态都是 research priority，不是 trade action。

这使任务颗粒度从“写一篇深度报告”缩小为可并行但不重复的 source/claim/security/diligence 单元，并通过标准库脚本在低成本环境复核。

## 7. 设计落地

| 研究发现 | v3 决策 |
|---|---|
| 数据接入与研究判断是两层 | Skill 定义证据合同，provider 作为可选下游 |
| 数字计算应确定性 | scorer/validator 纯 Python；LLM 不生成权重结果 |
| 披露不自动等于 exposure | 强制 product/segment/geography + denominator |
| 商业受益不自动等于好股票 | 独立 expectations/valuation/catalyst/downside gates |
| 多 Agent 易重复和放大上下文 | 默认单写者；只在明确授权且任务独立时并行 |
| 交易框架扩大风险与本地状态 | 无账户、无执行、无持久 ticker memory |
| 商业终端数据不可公开再分发 | 只保存 schema、provider/timestamp 和最小引用 |
| 高热度易强制填充 | 0–N + saturation + `NO_QUALIFIED_CANDIDATE` |

## 8. 研究限制

- 这是设计样本，不是全球所有 equity-research 软件的完整普查。
- 产品官方页面是供应商自述，不能证明准确率或投资绩效。
- 未购买或登录商业平台，也未验证其付费层真实数据质量。
- 未运行真实 ticker、current price/consensus 或模型，因此没有股票结论。
- 监管和数据许可会变化；任何 live run 要重开当前官方来源。
- v2 的泛商业机会/GitHub 研究仍完整保存在历史 ZIP 与研究摘要中；v3 不重复复制全部旧材料。
