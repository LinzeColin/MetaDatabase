---
name: equity-event-atlas
description: 股票事件航图（Equity Event Atlas）用于分析股票的解禁、财报、融资稀释、内幕人与大股东、并购重组、指数调整、公司行动、监管法律或重大经营事件，把官方证据、事件状态、因果关系、历史基准、Bull/Base/Bear 概率路径、条件动作和可视化组织为可审计的中文分析；它是现有系统中的只读功能板块，不是独立软件、交易机器人或券商执行器。
compatibility: 宿主需能读取官方披露与市场数据并提供文件系统；Python 3.9+ 可执行确定性校验、能力门、离线测试与 SVG/Mermaid 渲染。Skill 自身不联网、不常驻运行、不依赖开发会话持续在线。
metadata:
  display_name_zh: "股票事件航图"
  version: "0.0.0.1"
---
# 股票事件航图（Equity Event Atlas）v0.0.0.1

## 使命

把影响股票价格与可交易供需的离散节点，转化为一条可验证、可复跑、可视化、可校准的研究链：

```text
证券身份 → 市场能力 → 官方证据 → 事件状态 → 因果关系
→ 历史与机制基准 → 概率路径 → 条件动作 → 可视化 → 事后校准
```

本 Skill 是其他股票、投资、研究或决策系统可调用的**无状态功能板块**。宿主负责调度、联网、认证、数据持久化、权限、状态汇总与备份；本 Skill 负责分析契约、失败关闭、结构化输出和确定性渲染。

## 适用与不适用

### 使用本 Skill

- IPO、锁定期、提前解禁、注册转售、二次发行。
- 财报、预告、指引、投资者日与重大业绩节点。
- ATM、增发、配股、可转债、回购等供给变化。
- Form 3/4/5、Form 144、13D/G 或其他市场的持股与拟售披露。
- 并购、分拆、要约、重组、监管决定、诉讼与产品审批。
- 指数纳入、剔除、权重调整、拆股、反向拆股与股息。
- 多事件重叠时，判断放大、抵消、依赖与失效条件。
- 需要事件时间轴、因果图、概率扇形图或供应瀑布图时。

### 不使用本 Skill

- 只问实时股价、普通公司介绍或纯技术指标。
- 要求保证收益、精确猜顶底或把单点价格包装成确定事实。
- 自动登录券商、读取账户、生成订单或执行交易。
- 缺少证券身份、官方证据或分析时点，却要求给出主动买卖动作。
- 把社交媒体、匿名消息或模型语言直接升级为事实。

## 不变量

1. **中文输出**：正式报告、结论、限制与动作解释均为中文；代码标识符保持稳定英文枚举。
2. **只读决策支持**：禁止券商、账户、订单、自动执行与收益保证。
3. **四层真相**：每条声明只能是 `FACT`、`INFERENCE`、`FORECAST` 或 `ACTION`；不得混写。
4. **官方优先**：事实优先使用监管机构、交易所、指数公司和发行人正式披露；低等级来源只能触发调查。
5. **时点正确**：保存 `published_at`、`observed_at`、`effective_at` 与 `as_of`；`observed_at > as_of` 时阻断时点分析。
6. **事件是状态机**：事件可为传闻、估计、计划、条件、确认、修订、完成、取消、争议或未知；日期变化不得静默覆盖。
7. **可售不等于实售**：法律可售股份、潜在供应、预期出售与观察到的出售必须分开。
8. **概率而非伪精确**：预测开放时必须输出 Bear/Base/Bull，概率和为 1，并包含区间、方法、样本数、置信度和失效条件。
9. **动作受门禁约束**：没有充分用户约束、证据、市场能力或预测时，只能输出 `WATCH`、`NO_ACTION` 或 `RESEARCH_ONLY`。
10. **失败关闭**：证据冲突、来源过期、市场不支持或数据不完整时，降低能力或停止，不补造数据。
11. **无后台承诺**：每次调用在当前运行内完成；持续监测由宿主 cron、CI、队列或调度器显式触发。
12. **无第二事实源**：Skill 输出是分析制品；长期事实由宿主写入用户指定的权威数据层。

## 全球市场模型

覆盖层级与本次运行能力必须分开：

| 维度 | 枚举 | 含义 |
|---|---|---|
| 静态覆盖层级 | `DEEP / STANDARD / GENERIC` | Skill 对该市场规则和事件的内置深度 |
| 动态运行能力 | `FULL / SUPPORTED_WITH_HOST_DATA / RESEARCH_ONLY / BLOCKED` | 本次调用是否已验证官方来源、交易日历和时点行情 |

- 美国主要市场与 ASX：`DEEP`，但每次调用仍需实时验证来源与数据。
- 其他市场：统一事件本体和输出契约可用，默认 `GENERIC`；只有宿主提供并验证官方披露、日历和时点行情，才能升为 `SUPPORTED_WITH_HOST_DATA`。
- 未登记 MIC 或无法确认监管规则：不得声称完整覆盖。

详细规则见 `references/market_capability_registry.md`。

## 标准输入

宿主先生成并校验请求：

```bash
EEA="python3 <skill-dir>/scripts/equity_event_atlas.py"
$EEA validate-request <request.json> --json
```

最低请求字段：

```json
{
  "schema": "equity-event-atlas/request-v1",
  "locale": "zh-CN",
  "as_of": "2026-07-26T12:00:00+10:00",
  "security": {
    "name": "证券名称",
    "ticker": "代码",
    "mic": "XNAS",
    "instrument_type": "COMMON_STOCK",
    "currency": "USD"
  },
  "horizon_trading_days": 90,
  "requested_mode": "DEEP_DIVE",
  "objective": "RESEARCH"
}
```

需要主动动作时，`objective` 改为 `RISK_ADJUSTED_DECISION_SUPPORT`，并提供仓位状态、风险预算和最大事件敞口；否则保持研究模式。

## 标准执行流程

### 1. 证券身份门

冻结证券名称、ticker、MIC、证券类型、币种、公司行动调整状态和 `as_of`。代码复用、ADR/普通股混淆、拆股后代码漂移或身份不确定时，标记 `BLOCK`。

### 2. 市场能力门

执行：

```bash
$EEA capability <MIC> \
  --official-sources-verified \
  --calendar-verified \
  --market-data-verified
```

这些参数只能在宿主实际完成验证后添加，不是默认真值。

### 3. 证据采集

按 T0→T4 搜索：

- `T0`：监管机构、交易所、指数公司、发行人正式披露。
- `T1`：可信结构化数据库与经过锁定版本的解析器。
- `T2`：行情与公司行动数据提供商。
- `T3`：专业财经媒体。
- `T4`：论坛、社交媒体、匿名消息。

每项证据保存标题、来源类型、URL 或本地定位、发布时间、观察时间、内容哈希和等级。T4 不得单独支撑 `FACT`。

### 4. 事件状态与关系

使用 `references/event_ontology.md` 的十个事件家族、十个状态和八种关系。条件触发、日期修订、相互抵消与证据冲突必须显式表达。

### 5. 影响机制与预期差

至少评估：供应、需求、基本面、市场预期、流动性、仓位拥挤与监管。事件方向不得由名称直接推断；先比较“实际或最新证据”与“此前市场预期”。

### 6. 概率路径

只有身份门、证据门和数据质量满足时才生成 Bear/Base/Bull。历史同类事件需说明筛选条件、样本数、市场环境、异常收益基准和局限；样本不足时降低置信度，不扩大语言确定性。

### 7. 条件动作

动作词汇：

```text
WATCH / AVOID / HOLD / REDUCE / ACCUMULATE / HEDGE / EXIT / NO_ACTION / RESEARCH_ONLY
```

主动动作必须包含：前置条件、规模百分比、触发、风险上限、失效条件与声明依据。默认目标是风险约束下的风险调整收益，而不是最大杠杆或最高理论利润。

### 8. 机器校验与渲染

```bash
$EEA validate-bundle <analysis_bundle.json> --json
$EEA render <analysis_bundle.json> --output <output-dir>
```

固定输出：

```text
REPORT.md
STATUS_FRAGMENT.json
render_manifest.json
event_timeline.mmd
event_graph.mmd
scenario_fan.svg
supply_waterfall.svg
```

### 9. 结算与校准

宿主在事件和预测期限结束后，使用当时冻结的 `as_of`、证据快照和预测 ID 结算。至少记录概率命中、区间覆盖、Brier 类概率误差、可靠性分桶、方向偏差与来源可靠性；不得用后见信息改写原预测。

## 宿主接入边界

| 宿主负责 | 本 Skill 负责 |
|---|---|
| 联网、供应商认证、速率限制 | 输入与分析包合同 |
| 调度、队列、幂等、重试 | 时点与证据门禁 |
| 用户与权限 | 事件状态和关系本体 |
| 长期事实、对象存储与备份 | 概率与动作不变量 |
| 状态页和告警 | `STATUS_FRAGMENT.json` |
| 模型调用与成本控制 | 模型输出的确定性复核 |

Skill 不要求独立域名、数据库、前端、systemd、容器或常驻服务。宿主可把 SVG、Mermaid、Markdown 和 JSON 嵌入现有 UI、报告、Notion、Obsidian 或状态系统。

## 读取路由

按需读取，不要一次加载全部参考文件：

- 输入输出与字段：`references/contract.md`
- 市场与 MIC：`references/market_capability_registry.md`
- 事件类型、状态、关系：`references/event_ontology.md`
- 证据与时间：`references/evidence_time_policy.md`
- 预测与动作：`references/forecast_action_policy.md`
- 图表与现有 UI：`references/visualization_integration.md`
- 宿主接入与数据治理：`references/host_integration.md`
- 安全、红队与限制：`references/safety_limits.md`

## 安装、自检与卸载

本 Skill 由目标仓库管理，标准落点：

```text
CodexSkills/registry/codex/equity-event-atlas/
```

即时离线自检：

```bash
python3 <skill-dir>/scripts/equity_event_atlas.py self-test \
  --fixtures <skill-dir>/fixtures \
  --repeat 3
python3 -m unittest discover \
  -s <skill-dir>/tests \
  -p 'test_*.py' -v
```

它没有启动或停止命令，因为不是服务。卸载由仓库提交回滚完成；不得删除宿主长期事实。

## 完成回复

默认只报告：

```text
skill: equity-event-atlas
mode: <SCAN | DEEP_DIVE | COMPARE | REFRESH | REVIEW | SIMULATE>
capability: <FULL | SUPPORTED_WITH_HOST_DATA | RESEARCH_ONLY | BLOCKED>
gates: identity=<...> evidence=<...> forecast=<...> action=<...>
artifacts: <实际生成路径>
validation: PASS | FAIL
next: <唯一下一步>
```

没有真实执行或证据时，使用 `NOT_RUN`、`UNKNOWN` 或 `RESEARCH_ONLY`，不得写成已验证或已证明。
