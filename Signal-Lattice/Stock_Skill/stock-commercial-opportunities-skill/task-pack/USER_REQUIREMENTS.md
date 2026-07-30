# 用户需求与痛点定义

## 1. 核心 Job

用户接受新 ID `stock-commercial-opportunities`，中文名“股票商业机会拆解”，要求把 v1/v2 完整备份与股票专用 v3 一起保存在 MetaDatabase，且本地不安装。核心问题是：

> 一个产业、政策、技术或价值链变化创造了什么商业价值池，哪些上市发行人真正拥有可量化敞口，如何传导到订单/收入/利润/现金流，当前市场预期与估值是否留下研究空间，哪些催化与证伪条件决定是否投入下一单位研究时间？

## 2. 痛点—失败—验收

| 痛点 | 常见失败 | v3 必须做到 | 可验证信号 |
|---|---|---|---|
| 主题等于股票 | 热门赛道直接列受益股 | 建 value-chain beneficiary path | 每个箭头有 claim/source |
| 公司提到即有敞口 | 管理层一句话当 materiality | product/segment/geography + denominator | filing/IR + 量化 exposure |
| TAM 等于收入 | 忽略份额、capacity、价格和转化 | orders/backlog/revenue/margin/cash-flow bridge | capture signal 与 period/units |
| Ticker/证券错配 | 同名 ticker、ADR/local line 混淆 | issuer/exchange/share class/security identity | identity gate 先于排名 |
| 高分伪确定 | 单分数直接“买入” | score/risk/confidence/E-level 分开 | E0/E1 不高于 SCREEN_FLAG |
| 忽略 priced-in | 好公司等于好股票 | expectations、valuation、revision path | provider/timestamp + variant wedge |
| 催化剂装饰 | 没日期/来源/传导 | confirmed catalyst 与 fail branch | event/KPI → estimates/thesis |
| 强制 Top N | 证据不足仍补名单 | caps + saturation + zero result | `NO_QUALIFIED_CANDIDATE` |
| 时效错误 | 过期价格/估值/共识 | current fields 同次 timestamp/provider | stale/unknown 触发降级 |
| 社交/动量洗证据 | 热度冒充共识、敞口 | lead-only | core claim 不接受 social/snippet/synthetic-only |
| 金融越界 | 个性化买卖/仓位/收益保证 | research-only status 与安全门禁 | validator 阻断敏感指令 |
| 私密/MNPI 泄漏 | 持仓、账户、付费研究进入公开包 | public/private/license/MNPI gate | public-safe scan 通过 |
| 研究成本失控 | 全 universe 深研、多代理重复 | SCREEN/ATTRIBUTE/UNDERWRITE + 饱和停止 | source/time/data cap |

## 3. 用户与决策对象

- 操作者：公开股票研究者、行业研究者、投资团队前端筛选、战略/竞争情报人员。
- 决策对象：是否把某上市证券放入下一研究队列，不是是否交易。
- 默认输入：商业驱动/主题、universe/交易所、horizon、as-of、liquidity/exclusion、公开来源姿态。
- 默认输出：Radar、0–3 个 Candidate Dossiers、claim/source register、一个 Diligence Card、Research Priority Memo。
- 默认语言：中文；ticker、filing、API、字段和来源标题保留英文。

## 4. 四层必须分开

1. 商业机会：payer、预算、value pool、bottleneck、capacity、substitutes、durability。
2. 发行人敞口：security identity、product/segment/geography、denominator、period。
3. 股票设置：expectations、valuation、catalyst、downside、liquidity、falsifiers。
4. 证据成熟度：E0 Theme → E5 Thesis-ready。

E5 仍不是投资建议或交易批准。

## 5. 成功与非目标

成功：更早拒绝伪受益者、让最重要的敞口断点可见、把研究时间投向会改变排序的证据，并可独立恢复/验证源码。

非目标：真实投资组合管理、个性化财务建议、目标价承诺、自动交易、付费数据抓取、MNPI 工作流、完整 Bloomberg/FactSet 替代、持续市场数据平台、私人公司/信用优先研究，以及本地安装。
