# 运行合同

## 1. 角色

股票事件航图是宿主系统中的无状态分析 Skill。宿主提交请求、证据与时点数据；Skill 生成结构化分析包并执行确定性验证与渲染。

## 2. 请求合同

Schema：`equity-event-atlas/request-v1`

必要字段：

| 字段 | 约束 |
|---|---|
| `locale` | 必须以 `zh` 开头 |
| `as_of` | 带时区 ISO 8601 |
| `security.name` | 证券正式名称 |
| `security.ticker` | 当前代码 |
| `security.mic` | 四位 MIC |
| `security.instrument_type` | 普通股、ADR 等明确类型 |
| `security.currency` | 三位币种 |
| `horizon_trading_days` | 1–756 |
| `requested_mode` | 六种运行模式之一 |
| `objective` | `RESEARCH` 或 `RISK_ADJUSTED_DECISION_SUPPORT` |

动作支持还需要：

- 当前是否持仓、计划建仓或受限股份；
- 风险预算；
- 最大事件敞口；
- 影响动作的流动性、税务或权限限制应显式标为已验证或未知。

## 3. 分析包合同

Schema：`equity-event-atlas/analysis-bundle-v1`

核心对象：

```text
security
market_capability
gates
evidence[]
claims[]
events[]
scenarios[]
user_context
actions[]
supply_waterfall[]
calibration
disclosures[]
```

## 4. 四层声明

| 层级 | 定义 | 最低要求 |
|---|---|---|
| `FACT` | 来源直接证明 | 至少一项有效证据 |
| `INFERENCE` | 从事实推导 | 说明推导与不确定性 |
| `FORECAST` | 带概率的未来判断 | 情景、期限、方法、失效条件 |
| `ACTION` | 结合用户约束的条件策略 | 触发、规模、风险上限、失效条件 |

## 5. 运行门

```text
identity: PASS | RESEARCH_ONLY | BLOCK
evidence: PASS | RESEARCH_ONLY | BLOCK
forecast: PASS | RESEARCH_ONLY | BLOCK
action: PASS | RESEARCH_ONLY | BLOCK
```

低级门不能被高级门绕过。身份或证据未通过时，预测不得为 `PASS`；动作必须同时满足用户约束、市场能力和预测门。

## 6. 输出稳定性

- JSON 枚举、Schema 和文件名属于稳定接口。
- Markdown 解释可以增强，但不得改变四层真相或门禁语义。
- SVG 和 Mermaid 是派生视图；结构化 JSON 仍是宿主集成接口。
- 相同分析包与相同脚本版本应产生字节一致的渲染结果。
