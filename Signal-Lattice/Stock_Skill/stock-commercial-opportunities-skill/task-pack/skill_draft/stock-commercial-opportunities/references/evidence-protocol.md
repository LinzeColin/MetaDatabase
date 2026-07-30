# 股票研究证据协议

## 1. Source Register

每个来源至少记录：`source_id, title, url_or_locator, source_type, origin, access_level, evidence_class, issuer, ticker, filing_or_period, published_at, retrieved_at, currency_unit, redacted, claim_ids`。

枚举：

- source_type：`regulator_exchange / company_filing / company_ir / primary_dataset / market_data / consensus_estimates / transcript / reputable_media / community_social / user_material / internal_research / synthetic`；
- origin：`public / private / synthetic`；
- access_level：`opened_fulltext / opened_partial / snippet_only / user_provided / internal_private / synthetic`；
- evidence_class：`identity / commercial_mechanism / issuer_exposure / financial_capture / expectations_valuation / catalyst / risk_falsifier`。

## 2. 来源优先级

1. 交易所/监管机构、法定 filings、正式公司公告；
2. 公司 earnings release、presentation、IR、transcript；
3. 可追溯 primary dataset、当前 market data/consensus provider；
4. 高质量行业/媒体研究；
5. 社区、社交、搜索趋势；
6. synthetic outputs。

低层来源可发现线索，不能替代高层来源。Company IR 是第一方但有营销偏差，必须查 filings、period denominator 和反证。

## 3. 市场/法域入口

- 美国发行人优先 SEC EDGAR 与公司 filings；
- 澳洲发行人优先 ASX/company announcements 与 ASIC/公司披露；
- 其他市场使用对应交易所/监管披露系统；
- ASX 页面/公告可能带使用限制，只引用必要事实和链接，不批量复制或再分发内容；
- 价格、market cap、multiples、consensus 与事件日期必须记录 timestamp/provider。

## 4. 访问门禁

- 搜索结果和 snippet 只用于定位来源；
- core exposure claim 不能只靠 `snippet_only`、social 或 synthetic；
- 付费墙不可绕过；可用用户合法提供摘录并标 `user_provided`；
- URL 必须进入 register，输出不得出现未登记 URL；
- 同一新闻的转载不算独立来源家族。

## 5. Claim Register

每个 claim：`claim_id, statement, type, importance, source_ids, issuer, period, freshness, confidence, supports_or_challenges`。

类型：Fact / Inference / Estimate / Opinion / Unverified。核心链应原子化：

```text
商业驱动成立
-> 发行人产品/segment 暴露
-> 暴露占公司 denominator 的规模
-> 订单/收入/利润/现金流捕获
-> 预期/估值/催化形成股票研究设置
```

## 6. 证据成熟度上限

- 只有 theme/news/social：`E0`；
- ≥3 个独立公开来源家族且身份/机制初筛：最高 `E1`；
- filing/IR/primary evidence 量化 issuer exposure：可达 `E2`；
- orders/backlog/revenue/margin/cash-flow capture 可追踪：可达 `E3`；
- 当前 expectations/valuation/catalyst/downside 有时间戳：可达 `E4`；
- E4 + 完整 falsifiers、first rejection、source freshness、liquidity 与下一模型/研究路径：可达 `E5`。

E5 仍只是 thesis-ready research package，不是投资建议。

## 7. 新鲜度

| 字段 | 默认要求 |
|---|---|
| price/market cap/multiples | 同次运行时间戳 |
| consensus/estimates | provider + as-of；不可得则明确 |
| filings/earnings/guidance | 最新 period，并核对后续更新 |
| catalysts | confirmed/inferred 分开，记录日期来源 |
| regulation/policy | 当前官方来源、法域和生效日期 |
| stable mechanism | 可使用较旧原始材料，但核对结构变化 |

## 8. 冲突与反证

至少进行一轮反证查询：订单取消、backlog 转化、客户集中、产能/资本约束、利润率稀释、替代技术、价格战、监管变化、管理层激励、会计口径、估值压缩、催化延迟、流动性/borrow 限制。

冲突不能用平均 confidence 隐藏。标 `Conflicting`，说明采用口径和会改变结论的证据。

## 9. Private/MNPI

- 组合、持仓、交易、账户、内部研究、专家访谈、客户名单和未公开公司信息默认 private；
- 不请求、储存、推断或传播 MNPI；疑似非公开重大信息即停止并隔离；
- public output 只含公开来源或获授权脱敏摘要；
- synthetic evidence 不代表真实投资者、consensus、positioning 或 demand。

## 10. 完成定义

所有核心 claim 有可打开来源；证券身份和 period/units 一致；exposure denominator 明确；当前字段有 timestamp；强反证已处理；未注册 URL/私有泄漏/guarantee 为零；maturity 由证据导出。
