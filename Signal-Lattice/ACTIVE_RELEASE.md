# Active release candidate

- Application: `0.0.0.2.7`
- Decision contract: `v0.0.0.2`
- Runtime: `/opt/signal-lattice-v2/current`（systemd `signal-lattice-v2-api` + `signal-lattice-v2-loop.timer`）
- Collection interval: `60 seconds`（`OnUnitInactiveSec=60`）
- UI refresh: `30 seconds`（页面轮询 `/api/v1/report/latest`）
- Quote max age: `180 seconds`
- Public URL: `https://signal-lattice.linzezhang.com`
- Whitebox ledger: `JSON state dir / 动态贡献权重已参与汇总`
- Profitability: `NOT_ISSUED`（样本外窗口未达 6 个时不输出收益数字）
- Market position: `NONE`（不持仓、不声明固定标的，每轮由实时行情重算）
- Production state: `V2_REBUILD_IN_REMEDIATION_NOT_RELEASED`

取代 v19：v19 运行时提供的是冻结 fixture 结论、死均分权重、从未计算的收益，其历史记录留在 `V19_CANONICAL_STATE.json` 与 `v19_release/`，仅作存档，不再描述在跑的系统。
