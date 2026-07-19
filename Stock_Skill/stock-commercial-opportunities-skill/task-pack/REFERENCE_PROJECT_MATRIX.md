# 类似项目与软件系统矩阵

> 2026-07-19 只读快照。License/功能/价格/访问条款会变化；表中“采用”均指抽象设计模式，不代表复制代码或购买/安装产品。

| 项目/系统 | 类型 | 最强能力 | 对本任务的缺口 | v3 采用/拒绝 | 当日公开边界 |
|---|---|---|---|---|---|
| [SEC EDGAR](https://www.sec.gov/search-filings) | 官方披露系统 | 美国 issuer filings、身份、XBRL/事件入口 | 不做 theme→beneficiary 或投资判断 | 采用为美国 primary-source 起点 | 官方公开；遵守 SEC access policy |
| [ASX announcements](https://www.asx.com.au/asx/v2/statistics/todayAnns.do) | 官方交易所披露 | 澳洲公告与证券事件 | 内容/数据再使用可能受限；不做归因 | 采用链接/最小事实/locator，拒绝批量复制 | 交易所条款需同次核验 |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | 开源数据平台 | provider 标准化、Python/REST/AI/Workspace 集成 | 重依赖；数据层不证明商业敞口 | 采用 provider/provenance 分层；v3 不集成 | AGPLv3；数据 provider 另有许可 |
| [EdgarTools](https://github.com/dgunning/edgartools) | 开源 filing 解析库 | SEC forms、XBRL、ticker/CIK、typed data | 美国为主；不会自动证明经济关联 | 未来 E2/E3 可选 adapter；当前零依赖 | MIT；SEC access/rate 仍需遵守 |
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 开源金融研究 Agent | deterministic finance + LLM synthesis、估值/报告 | API keys/providers/重运行时；范围含更深模型/交易 | 采用 numbers-by-code 与 provenance；拒绝直接依赖 | Apache-2.0；provider/模型成本另计 |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 开源多 Agent 交易框架 | analyst debate、risk roles、ticker workflow | 输出交易决定并持久化 memory/cache | 采用 bull/bear/falsifier 思路；拒绝交易与持久状态 | Apache-2.0；LLM/data provider 另计 |
| [AlphaSense](https://www.alpha-sense.com/platform/) | 商业研究/情报平台 | cited search、deep research、monitoring、premium content | 专有内容/数据；不可作为公共包依赖 | 采用 source-backed synthesis/monitoring contract | 专有服务/内容许可 |
| [Koyfin](https://www.koyfin.com/for-investors/equity-research/) | 商业市场数据终端 | financials、valuation、screening、alerts/watchlists | 不透明数据许可；终端不自动证明 exposure chain | 采用 current provider/timestamp/watch triggers | 专有/分层服务，条款需核验 |
| [TIKR](https://www.tikr.com/analyze-stocks) | 商业股票研究平台 | 全球筛选、financials、estimates、transcripts、valuation | forward estimates 是聚合估算；深度与订阅相关 | 采用 actual/estimate/revision/analyst-count 区分 | 专有数据/订阅层 |
| [ASIC INFO 269](https://asic.gov.au/regulatory-resources/financial-services/giving-financial-product-advice/discussing-financial-products-and-services-online/) | 官方行为边界 | 在线金融产品讨论的监管风险 | 不是研究工具 | 采用 personal-advice/promotion fail-closed | 官方指导；具体情境需专业判断 |
| [Investor.gov stock-scam alert](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/social-media-stock-scams) | 官方投资者保护 | 社交荐股和保证收益风险提示 | 不是 research engine | 采用 social lead-only/guarantee block | 官方教育材料 |

## 能力覆盖

| 能力 | 数据/披露工具 | 研究 Agent | 商业终端 | Trading Agent | v3 |
|---|---:|---:|---:|---:|---:|
| Security identity | 强 | 中 | 强 | 中 | 强制门禁 |
| Commercial value pool | 弱 | 中 | 弱/中 | 弱 | 强制模型 |
| Beneficiary pathway | 弱 | 可生成 | 部分主题筛选 | 弱 | 强制 claim chain |
| Quantified issuer exposure | 提供原料 | 可分析 | 提供数据 | 中 | E2 hard gate |
| Financial capture | 提供 filings/data | 强 | 强 | 中 | E3 hard gate |
| Expectations/valuation | provider-dependent | 强 | 强 | 强 | E4 hard gate，但不自带数据 |
| Catalyst/falsifier | 提供事件 | 中/强 | monitoring | debate | 强制双向分支 |
| Deterministic validation | 数据层 | 项目依实现 | 不透明 | 项目依实现 | 标准库脚本 |
| Zero-candidate result | 不适用 | 不一定 | 筛选可能为空 | 通常给决定 | 明确允许 |
| No trade/personal advice | 不适用 | disclaimer-dependent | 用户工作流 | 不符合 | 结构性禁止 |
| No local install/state | 不适用 | 不符合 | SaaS 账户 | 不符合 | 符合当前要求 |

## Build / Buy / Integrate 决策

- **Build now**：轻量证据模型、状态机、templates、fixtures、scorer、validators、evals、manifest。
- **Integrate later only if authorized**：SEC/ASX adapter、OpenBB/EdgarTools、licensed market/consensus provider、valuation/model workflow。
- **Do not build now**：实时行情仓库、全文抓取、portfolio/OMS、自动交易、付费内容镜像、多 Agent ticker memory。
- **Do not claim**：替代 AlphaSense/Koyfin/TIKR/OpenBB/FinRobot，或从公开桌面资料产生投资绩效。

## 版本谱系说明

v1 的高 ROI 内容研究和 v2 的通用商业机会系统包含更广的产品发现/验证参考。它们以不可变 ZIP 保存在项目 `archives/`，本矩阵只记录 v3 新增的股票研究专用样本。
