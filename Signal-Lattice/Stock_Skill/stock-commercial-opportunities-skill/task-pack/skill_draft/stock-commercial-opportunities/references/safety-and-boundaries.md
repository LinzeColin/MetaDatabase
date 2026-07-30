# 金融研究、安全与发布边界

## 1. 这项 Skill 批准什么

只批准公开信息研究、候选筛选、证据审计和下一尽调路由。输出是 `research triage—not investment advice`，不能被解释为：

- 针对个人财务状况的买入、卖出、持有或仓位建议；
- 目标价、预期收益、胜率或回撤保证；
- 自动下单、跟单、账户操作、营销荐股或拉抬价格；
- 对未公开重大信息（MNPI）的搜集、推断、存储或传播。

`ADVANCE_RESEARCH` 只表示进入模型、估值、业绩或投资论点等更深研究。它不是交易批准。

## 2. 法域与沟通风险

股票和其他金融产品属于高风险领域。每次工作都应记录法域、对象、as-of 和输出可见性，并核验当前监管/交易所一手来源。

- 在澳洲，在线讨论金融产品可能构成金融产品建议或其他受监管金融服务；是否需要牌照取决于内容与情境。参考 [ASIC INFO 269](https://asic.gov.au/regulatory-resources/financial-services/giving-financial-product-advice/discussing-financial-products-and-services-online/)。
- 对美国上市公司，法定披露优先从 [SEC EDGAR](https://www.sec.gov/search-filings) 获取。
- 对澳洲上市公司，优先使用 ASX/公司公告；遵守页面、公告和数据提供商的版权与商业使用限制，不批量再分发正文或受限数据。

免责声明不能修复实质上的个性化建议、误导陈述、无牌服务或证据缺陷。不确定是否越界时，降低为教育性研究方法、事实核验问题和应向持牌专业人士确认的事项。

## 3. 禁止语言与动作

禁止：`稳赚`、`保本`、`必涨`、`确定翻倍`、`无风险`、`强烈买入`、`满仓`、`马上卖出`、虚构目标价、伪造共识或用历史价格表现承诺未来结果。

不得：

- 请求或操作券商、银行、交易、研究供应商账户；
- 自动交易、建仓、平仓、借券或改变任何真实组合；
- 代表用户公开发布荐股、私信推广、协调交易或制造虚假热度；
- 把社交媒体、价格动量、搜索热度或 AI 合成观点当作需求、共识、持仓或敞口证据。

可做：列出可证伪假设、当前事实、估算区间、风险、停止规则和哪些公开证据会改变研究优先级。

## 4. 证券身份和时效

在排名前核对 issuer、ticker、exchange、share class、ADR/local line、security type、currency、fiscal period 和 as-of。价格、market cap、multiples、consensus、borrow、流动性和事件日期属于易变字段，必须同次获取 provider/timestamp；没有当前数据就标 `UNKNOWN/STALE`，不得补写。

Ticker 冲突、反向并购、改名、退市、双重上市、存托凭证比例或币种不清时先停止排名。

## 5. 公开、私密与 MNPI

- 持仓、成本、订单、账户号、交易历史、客户名单、内部模型、付费研究、专家访谈和公司内部信息默认 private。
- `output_visibility=public` 时只允许公开来源、获授权材料的最小脱敏摘要和合成测试夹具；原始私密数据不得进入公开仓库。
- 不请求“内部消息”、未公开业绩、客户订单或其他疑似 MNPI。收到疑似 MNPI 时停止使用、隔离内容并建议合规处理。
- 不把 private 来源转换成看似公开的无来源结论；脱敏不等于获得发布许可。
- 不在仓库中保存 token、cookie、session、API key、账户截图、付费数据导出或本机绝对路径。

## 6. 来源、许可与访问

- 不绕过登录、验证码、付费墙、robots、rate limit、地域限制或技术访问控制；
- 不使用未授权 cookie/session/token、私有 API 或他人账户；
- 只引用支持结论所需的最小事实，优先释义和指向原始链接；
- 市场数据与 consensus 的许可可能不允许再分发。公开产物保留 schema、方法、少量可引用事实和 provider 指针，不复制受限数据集；
- 搜索 snippet 只用于发现来源，不能支持 core claim。

## 7. 操纵、骗局与社交信号

社交热度、群聊“内幕”、保证收益、催促立刻交易和无法核验的业绩是风险信号，不是 alpha 证据。可用 [Investor.gov 的社交媒体股票骗局提示](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/social-media-stock-scams) 做安全校验。

如果请求涉及拉抬、协同行动、虚假陈述、隐藏利益冲突、规避披露或利用非公开信息，直接拒绝相应动作；只可给合规与风险说明。

## 8. Fail-closed 清单

提交前逐项回答：

1. 核心敞口是否有已打开的 filing、交易所公告或公司正式披露？
2. issuer/security/period/currency/units 是否一致？
3. theme → product/segment → denominator → orders/revenue/margin/cash flow 是否存在断点？
4. expectations、valuation、catalyst 是否有当前 timestamp/provider？
5. 是否把 management marketing、social、price action 或 synthetic 写成事实？
6. 是否存在未登记 URL、snippet-only core claim、受限数据再分发或许可证未知？
7. 是否泄露组合、账户、内部材料、凭据、本机路径或疑似 MNPI？
8. 是否给出个性化交易动作、仓位、目标价或收益保证？
9. 是否记录最强反例、first rejection、falsifiers 和数据冲突？
10. 是否允许 `NO_QUALIFIED_CANDIDATE`？

任一关键答案不安全时，降低 maturity/status、输出最小核验计划，或停止。
