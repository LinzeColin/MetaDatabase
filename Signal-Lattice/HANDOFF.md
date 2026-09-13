# Signal Lattice V2 重建交接

更新时间：2026-09-13 Australia/Sydney

## 当前目标

以免费免密钥真实数据建立只读多分支投资结论系统；先完成并验收 Stage 1。

## 当前状态

`STAGE_1_CODE_COMPLETE_EXTERNAL_ACCEPTANCE_BLOCKED`。新 V2 运行时不读取旧行情路径，默认运行时目录是 `/var/lib/signal-lattice-v2`。本机受限网络无法访问四个公开数据源，也不能连接已授权 OVH SSH，因此尚未取得真实行情和 API curl 验收。

## 关键决定

- 新生产入口为 `signal_lattice.cli` 的 `once`、`loop`、`serve`，版本 `0.0.0.2.0`。
- 行情 provider 是新浪报价、腾讯报价备份、天天基金净值，以及新浪美股/A 股日线。美股日线用新浪 `US_MinKService.getDailyK`，A 股/场内 ETF 用新浪 `CN_MarketData.getKLineData` 的 `datalen=3000`；A 股新浪失败时才回退腾讯。港股继续走腾讯 `hkfqkline`，请求上限 2000 条但来源实际最多约 640 条（约自 2024-02 起），这个上限尚未消除。
- 新浪报价按 `instrument.market` 读取 US[1]、CN[3]、HK[6]；腾讯报价逐条去除换行空白后解析。腾讯日线优先 `qfqday`，指数缺该键时使用 `day`。
- 报价缺失/超龄、来源时间过旧、任一最新日线超龄或上游失败时，报告唯一状态是 `SYSTEM_BLOCKED`，`decision.action` 为 `null`，页面文案是“数据链路不完整，不出结论”。
- 观察宇宙包含美股/ETF、A 股/场内 ETF、港股/ETF、场外基金；不含 ASX；`automatic_trading` 始终是 `false`。

## 已改文件

- `src/signal_lattice/marketdata/`：真实 provider 和统一 `Quote` / `Bar` 模型；新浪日线覆盖美股/A 股，腾讯日线作为港股主源与 A 股备源。
- `src/signal_lattice/live_config.py`、`live_runtime.py`、`live_api.py`、`cli.py`：V2 数据循环、只读 API、状态存储和硬编码诚实门。
- `web/index.html`：阻断态和真实数据状态页面。
- `pyproject.toml`：版本升级为 `0.0.0.2.0`。
- `tests/test_marketdata_providers.py`、`tests/test_live_api.py`：解析和阻断语义测试。

## 已验证

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_marketdata_providers.py tests/test_live_api.py
```

结果：`8 passed in 0.05s`。覆盖新浪 US/CN/HK 现价字段、腾讯多标的分行、美国日线 JSONP 剥壳和类型转换、指数 `day` 回退，以及阻断态无动作语义。腾讯美股日线不再作为生产源。

```bash
PYTHONPATH=src python3 -m pytest -q
```

结果：当前工作树的全量收集被嵌套的 `Stock_Skill/.../tests` 和 `v19_release/tests` 阻断；它们需要独立包并与顶层有同名测试模块。仅收集顶层 `tests/` 时，另有既有发布/状态机/本地监听测试在 sandbox 与当前历史交付状态下失败。本轮两份测试已单独通过。

```bash
PYTHONPYCACHEPREFIX=/private/tmp/... PYTHONPATH=Signal-Lattice/src python3 -m py_compile ...
```

结果：`PY_COMPILE_PASS`。

本机真实调用的结果为 `SYSTEM_BLOCKED`，原因是 sandbox 的外网请求均为 `HTTP_REQUEST_FAILED:URLError`；这证明失败路径，不证明数据源可用。

## 未解决风险

- 未部署到 OVH；未执行远端真实 source/API/public curl。
- 美股与 A 股新浪日线的新端点、A 股腾讯备源，以及港股 640 条实际深度仍需由具备网络出口的验收方复核。
- Stage 2 的分支结论、Stage 3 贡献度权重、Stage 4 回测、Stage 5 新 unit/历史冗余清理均未开始。
- 旧 v19 目录仍是历史回滚资产，尚未改动；新生产入口不引用它。

## 下一步

在具备 SSH/网络出口的环境执行 Stage 1 目标机验收：将当前 worktree 的 V2 代码放入隔离临时目录，使用真实数据跑 `once`，确认 `DATA_READY`、数据截止为当天或最近交易日，再由 API `curl` 验证；再测试不可达 host 返回 `SYSTEM_BLOCKED`。仅这两项通过后开始 Stage 2。
