# 股票事件本体

## 1. 十个事件家族

| 枚举 | 范围 |
|---|---|
| `IPO_LOCKUP` | IPO、锁定期、豁免、注册转售、二次发行 |
| `EARNINGS_GUIDANCE` | 财报、预告、指引、投资者日 |
| `FINANCING_DILUTION` | ATM、增发、配股、可转债、回购 |
| `INSIDER_OWNERSHIP` | 内部人、大股东、持股变动、拟售通知 |
| `MNA_RESTRUCTURING` | 并购、出售、分拆、要约、重组 |
| `INDEX_REBALANCE` | 纳入、剔除、权重与季度调整 |
| `CORPORATE_ACTION` | 拆股、反向拆股、股息、换股与代码变化 |
| `REGULATORY_LEGAL` | 监管、诉讼、调查、许可和审批 |
| `PRODUCT_OPERATIONAL` | 重大产品、产能、事故、运营与合同节点 |
| `LIQUIDITY_POSITIONING` | 借券、期权、流通盘、成交能力与拥挤度 |

## 2. 十个状态

```text
RUMORED → ESTIMATED → SCHEDULED → CONDITIONAL → CONFIRMED
                                             ↘ AMENDED
CONFIRMED / AMENDED → COMPLETED
任意未完成状态 → CANCELLED | DISPUTED | UNKNOWN
```

含义：

- `RUMORED`：只有未经确认的线索。
- `ESTIMATED`：依据规则估算，但无正式日期。
- `SCHEDULED`：有计划日期，仍可能改变。
- `CONDITIONAL`：生效取决于价格、投票、监管或其他条件。
- `CONFIRMED`：权威来源确认当前条款和日期。
- `AMENDED`：正式条款或日期发生修订，必须保留前版本关联。
- `COMPLETED`：事件已发生，并有完成证据。
- `CANCELLED`：正式取消。
- `DISPUTED`：权威来源互相冲突，未裁定。
- `UNKNOWN`：证据不足，不能推断状态。

## 3. 八种关系

| 枚举 | 用途 |
|---|---|
| `TRIGGERS` | 一事件触发另一事件 |
| `DEPENDS_ON` | 生效依赖另一事件或条件 |
| `AMENDS` | 新事件修订旧事件 |
| `PRECEDES` | 时间上明确先于 |
| `OVERLAPS` | 事件窗重叠 |
| `COMPOUNDS` | 同方向放大 |
| `OFFSETS` | 方向抵消 |
| `CONFLICTS_WITH` | 来源或结论冲突 |

关系必须引用已存在事件，不允许自环。

## 4. 影响机制

```text
SUPPLY / DEMAND / FUNDAMENTALS / EXPECTATIONS / LIQUIDITY / POSITIONING / REGULATORY
```

每个事件至少绑定一种机制。事件名称本身不决定涨跌；输出应解释机制、已定价程度、流动性吸收和相互作用。

## 5. 解禁专用拆分

```text
Legal Float           法律允许出售
Potential Float       可能进入交易的股份
Expected Sell Supply  基于动机和限制估计的出售
Observed Sell Supply  已观察到的出售或流通变化
```

四层不得合并。Form 144、注册声明、锁定期届满或内部人计划只能证明各自明确表达的状态。
