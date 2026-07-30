# 宿主集成契约

## 调用边界

宿主负责：

- 获取和合法使用市场数据；
- 将交易所日历、夏令时、节假日、半日市和特殊会话标准化为 UTC；
- 维护本地现金指数身份，避免用异地上市 ETF 静默替代；
- 决定分析历史区间和币种口径；
- USD 模式下提前完成汇率换算，并把全部输入 `currency` 标记为 `USD`；
- 调用 Skill、限制资源、收集状态；
- 保存长期结果、对象哈希和恢复信息；
- 向用户展示免责声明和数据来源。

Skill 负责：

- 严格输入与配置验证；
- 按共同 `session_date` 计算对称同期相关；
- 按目标开盘信息集计算方向时延；
- 执行有界统计筛选、FDR、稳定性和样本外确认；
- 生成固定格式的研究制品与离线中文图谱；
- 输出明确失败、拒绝或样本不足状态。

## 稳定 CLI

```text
gela doctor
gela validate --config CONFIG_PATH
gela analyze --config CONFIG_PATH
gela verify-output OUTPUT_DIR
gela selftest
```

退出码 `0` 表示命令合同通过；非 `0` 必须由宿主记录 stdout JSON，不得自动无限重试。

## 输入契约

CSV 必须且只能包含 Skill README 中列出的 17 个字段。`instrument_type` 必须为 `cash_index`；`return_type` 必须在一次分析内统一；`source_retrieved_at` 不得早于会话收盘。每个 `market_id` 在一次样本内的国家、指数、收益类型、币种、时区、坐标、供应商和代码必须稳定。`session_date` 用于同期相关；UTC 开收盘用于方向时延，两套语义不得互相替代。

配置不接受未知字段。默认基础来源陈旧上限 `max_base_staleness_hours=96`；宿主可按市场日历显式收窄，但不得为了增加结果而静默放宽。

## 输出契约

宿主优先消费：

- `analysis.json`：完整事实；
- `co_movement.csv` / `correlation_matrix.csv`：同期相关；
- `matrix.csv` / `edges.csv`：时延候选与确认边；
- `quality_report.json` / `provenance.json`：质量与身份；
- `atlas.html`：可直接嵌入或独立打开的离线可视化。

## 运行数据

真实输入、缓存和输出不属于 AgentDatabase 代码仓。宿主需要长期保存时，应按既有 Private-Database / R2 治理写入结构化事实、对象引用、哈希、版本和恢复信息。Skill 不直接连接、克隆、提交或修改这些权威源。

## 幂等

相同输入 CSV、配置和 Skill 版本应产生相同统计内容；`generated_at` 未冻结时仅时间字段可变化。宿主可显式提供固定 `generated_at` 以获得字节级可重复输出。
