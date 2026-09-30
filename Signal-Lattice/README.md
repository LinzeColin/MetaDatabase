# Signal Lattice

## 做什么

永久只读的美股中小盘投研看板。研究层从 SEC 一手申报出发，Owner 的 5 个股票 Skill（瓶颈、商业机会、事件航图、股势前瞻、全球联动）各自在独立子进程里对候选池打分；中枢汇成**唯一一只**研究跟进标的，附 SEC 原文链接、失效条件和前向记分。规则没有证明自己有信息量（规则自证门）时，结论是 `NO_ACTION`「本轮不给建议」，同时给观察名单和影子候选；数据链不全是 `SYSTEM_BLOCKED`。不下单、不登录券商，`SIGNAL_LATTICE_ENABLE_TRADING=1` 会直接报错。运行期零 Agent、零模型 Token。

候选池：美国上市普通股、市值 3–50 亿美元、近 18 个月有 10-K/10-Q 的本土申报人、价格 ≥ 3 美元、20 日成交额中位数 ≥ 300 万美元；IWM 与大盘只作基准，不得进入建议。

两层运行：研究层 `signal-lattice research`（美东工作日盘中与收盘后各一次，休市日自动退出）；实时层 `signal-lattice once`（每 60 秒，读最新研究快照 + shortlist 与 IWM 行情，行情超过 180 秒按交易时段未推进即阻断）。旧版（≤ 0.0.0.3.5）的 ETF 动量 / 均值回归 / 15 只指数候选已从决策路径移除。

## 怎么跑

```bash
cd Signal-Lattice
PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests      # 需 pytest、setuptools，离线
# 生产机两段式部署（先在新版本上跑一次研究层，再切实时层）见 文档/06_运维手册.md 第 6 节
```

线上核查、业务判据、缓存上限与回滚命令见 `文档/06_运维手册.md`。代码在 `src/signal_lattice/`（入口 `cli.py`，研究层 `research_cycle.py`，中枢 `hub.py`，记分簿 `ledger.py`），页面在 `web/`，systemd 单元在 `deploy/systemd-v2/`。需求与取舍依据见 `重建/`，交接见 `HANDOFF.md`。

## 数据在哪

- 运行状态：生产机 `/var/lib/signal-lattice-v2`（`research/` 研究层事实库与证据快照、`ledger.sqlite` 记分簿、`backtest/` 中枢回测），不进仓库。
- SEC User-Agent 只在服务器 `/etc/signal-lattice-v2/research.env`（root 0600），不进仓库。
- v1 停机归档（2026-08-04，VPS-1，v2 不读取）：`LinzeColin/Private-Database` Release `signal-lattice-archive-20260804`。
- 股票 Skill 源码与参数：`Stock_Skill/`（由 `stock-skill-validation.yml` 校验）。
