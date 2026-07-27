---
name: global-equity-lead-lag-atlas
description: 分析多个国家或地区股指在 1、5、10、15、21、63、126 个交易时段上的同期相关与会话感知领先—滞后关系，严格区分收益尺度、回看区间、会话滞后和真实小时差，并输出机器可读证据、中文研究摘要与自包含全球联动图谱 HTML。用于“国家股市相关性”“谁领先谁”“领先多久”“全球股市传导图”等任务；不是交易信号、因果证明、行情供应商、独立软件系统或常驻服务。
license: MIT
compatibility: Python 3.10+；核心运行仅使用标准库。宿主负责数据授权、日历标准化、调度、长期存储、鉴权和监控。
metadata:
  author: LinzeColin
  version: "0.0.0.1"
  language: "zh-CN"
  display_name_zh: "全球股市时序联动图谱"
  english_brand: "Global Equity Lead–Lag Atlas"
  acronym: "GELA"
  architecture: "embeddable-skill-module"
---
# 全球股市时序联动图谱

**Global Equity Lead–Lag Atlas（GELA）**

## 结论先行

本 Skill 是接入现有 Agent、研究平台或投资分析系统的功能板块，不是独立产品。它读取宿主提供的会话级股指 CSV 和冻结配置，分别计算：

1. **同期相关**：双方相同 `session_date` 下的多尺度历史收益相关，只描述共同变动；
2. **会话感知时延**：只使用目标市场开盘前已经完成的来源市场收盘信息，判断是否存在稳定样本外预测增量。

一次运行生成：

- `analysis.json`：运行身份、市场摘要、同期相关、全部时延假设和确认结果；
- `co_movement.csv` 与 `correlation_matrix.csv`：同期相关长表和矩阵；
- `hypotheses.csv`：每个来源、目标、收益尺度和额外滞后的完整统计结果；
- `matrix.csv` 与 `edges.csv`：每个有向市场对的最佳候选和确认方向边；
- `quality_report.json` 与 `provenance.json`：质量、输入哈希和运行边界；
- `visualization_spec.json`、`summary.md`、`atlas.html`：可嵌入宿主的中文解释和离线图谱。

Skill 不创建数据库、账户、API 服务、调度器、常驻进程或独立部署面。宿主拥有调用、权限、缓存、长期记录、状态采集和备份职责。

## 何时调用

调用本 Skill，当用户需要：

1. 比较多个国家或地区股指在不同收益尺度上的历史相关性；
2. 判断 A 市场收盘信息是否在 B 市场开盘前可得，并检验 A 是否对 B 有稳定预测增量；
3. 区分普通共同变动、时区造成的信息先后和通过证据门的方向关系；
4. 生成全球同期相关图、时延方向图、矩阵和可追溯研究文件。

不要调用本 Skill 直接产生买卖指令、保证收益、宣称现实因果、代替受许可行情源，或对缺乏会话时间戳的数据强行判断领先者。

## 硬边界

- `horizon` 是累计收益尺度；`lookback` 是宿主提供的数据历史长度；`source_lag` 是额外来源会话滞后；三者不得混用。
- 同期相关按双方声明的 `session_date` 对齐，是对称关系，不用于判断谁领先谁。
- 时延检验严格要求 `source_close < target_open`，并以 `max_base_staleness_hours` 拒绝过度陈旧的基础来源收盘。
- 默认结论只允许：`同会话日期收益相关`、`会话感知预测领先`、`未发现可靠关系证据`。
- 相关、预测增量或时间先后均不等于现实因果；本版本不输出因果结论。
- `currency_mode=local` 与 `currency_mode=usd` 不得静默混用；USD 模式要求宿主先统一换算且所有输入标记为 USD。
- 输入 `instrument_type` 必须为 `cash_index`；国家 ETF 不得替代本地现金股指来判断本地市场交易时序。
- `return_type` 必须显式声明为 `price`、`total_return` 或 `net_total_return`，一次分析不得混用。
- `source_retrieved_at` 不得早于对应会话收盘，避免使用来源时间不可能成立的数据。
- 所有未运行、样本不足、质量不足或证据门失败的项目保持明确状态，不得折算为通过。

## 最短调用路径

从 Skill 根目录执行：

```bash
python3 -B scripts/check_syntax.py
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m gela doctor
PYTHONPATH=src python3 -B -m gela validate --config examples/config.synthetic.json
PYTHONPATH=src python3 -B -m gela analyze --config examples/config.synthetic.json
PYTHONPATH=src python3 -B -m gela verify-output examples/out/synthetic-demo
```

默认采用上面的零安装 `PYTHONPATH=src` 调用；若宿主已具备 `setuptools>=61`，可选执行 `python3 -m pip install --no-build-isolation --no-deps -e .`，随后直接使用 `gela` 命令。核心运行不依赖 setuptools。

## 宿主集成

宿主应按 [`references/integration-contract.md`](references/integration-contract.md) 提供输入并消费输出。数据接入、交易日历修复、真实数据许可、长期保存和界面嵌入均通过薄 Adapter 完成，核心 Skill 不依赖具体 Provider。

## 解释与证据

先读：

- [`references/methodology.md`](references/methodology.md)
- [`references/interpretation-guardrails.md`](references/interpretation-guardrails.md)
- [`references/provider-policy.md`](references/provider-policy.md)
- [`references/visualization-contract.md`](references/visualization-contract.md)

## 停止条件

遇到以下任一条件，返回结构化失败或不足状态，不继续制造结论：

- 配置包含未知字段、危险阈值或未确认数据使用权；
- 会话开盘、收盘或抓取时间缺失、非 UTC 或顺序错误；
- 同一市场同一会话重复、身份漂移、价格非正或经纬度非法；
- USD 模式下输入未统一为 USD；
- 市场不足两个或有效样本低于冻结阈值；
- 输出完整性验证失败。
