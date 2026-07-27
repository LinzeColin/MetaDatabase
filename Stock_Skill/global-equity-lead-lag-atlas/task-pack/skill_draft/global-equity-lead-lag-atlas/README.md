# GELA v0.0.0.1

全球股市时序联动图谱是一个**可嵌入 Skill 模块**，不是独立软件或常驻服务。它同时生成：

1. 多尺度同期相关；
2. 严格使用目标开盘前信息的会话感知时延关系；
3. 自包含中文全球图谱与机器可读证据。

## 运行与可选安装

默认推荐零安装运行，进入 Skill 根目录后执行：

```bash
PYTHONPATH=src python3 -B -m gela doctor
PYTHONPATH=src python3 -B -m gela selftest
```

核心运行仅依赖 Python 3.10+ 标准库，无需网络、数据库、浏览器构建工具或第三方运行依赖。若宿主环境已经提供 `setuptools>=61`，可选进行 editable 安装：

```bash
python3 -m pip install --no-build-isolation --no-deps -e .
gela doctor
```

editable 安装只是宿主便利入口，不是核心运行前置条件；离线、最小 Python 环境应使用零安装路径。

## 输入

CSV 每行代表一个市场会话，必填列：

```text
market_id,country_iso3,country_name_zh,index_name,instrument_type,return_type,currency,timezone,latitude,longitude,session_date,open_ts_utc,close_ts_utc,close,source,source_symbol,source_retrieved_at
```

`instrument_type` 在本版本必须为 `cash_index`；`return_type` 仅允许 `price`、`total_return` 或 `net_total_return`，且一次分析不得混用。`source_retrieved_at` 不得早于该会话收盘。

配置格式见 `examples/config.synthetic.json`。`currency_mode=usd` 时，宿主必须先把全部序列换算为 USD；Skill 不现场获取汇率。

## 输出

一次分析生成：

- `analysis.json`
- `co_movement.csv`
- `correlation_matrix.csv`
- `hypotheses.csv`
- `matrix.csv`
- `edges.csv`
- `quality_report.json`
- `provenance.json`
- `visualization_spec.json`
- `summary.md`
- `atlas.html`

真实历史数据、缓存和运行结果不得提交到 AgentDatabase 代码仓，长期结果由宿主按既有治理写入 Private-Database 或其对象存储引用层。运行 `examples/config.synthetic.json` 会在被忽略的 `examples/out/` 生成确定性合成演示；运行结果不得提交代码仓。

## 验证

```bash
python3 -B scripts/check_syntax.py
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m gela selftest
```
