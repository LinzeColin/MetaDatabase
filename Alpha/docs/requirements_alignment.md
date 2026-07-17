# Alpha Requirements Alignment

> 2026-07-17 起本表为历史存档:产品契约已由 `Alpha/AGENTS.md`(Live MVP v1,受控许可模型)
> 与 `Alpha/machine/facts/` 全面取代。下表仅记录旧 paper 阶段的需求对齐状态。

| Requirement | Status | Implementation Direction |
|---|---:|---|
| Agent 全自动 paper trading | Improved MVP implemented | FastAPI app-managed `AutoPaperAgentRuntime` runs immediately on dashboard startup, then every 300 seconds; `PaperTradingLoop.run_forever()` remains available for CLI |
| Agent 自动生成真实交易候选订单 | Improved MVP implemented | `OrderIntent` generated from tradable strategy tournament candidate |
| Agent 自动完成风险检查 | Improved MVP implemented | `pre_trade_risk_check()` before queue entry, with notional limit enforcement |
| Agent 自动进入审批队列 | MVP implemented | `ApprovalQueue.enqueue()` |
| Agent 自动生成 broker-ready order ticket | Improved MVP implemented | `BrokerReadyOrderTicket` includes `expires_at`; dashboard/API annotate fresh vs expired actionability |
| 每 5 分钟更新一次 | Improved MVP implemented | `refresh_interval_seconds: 300` in service, `configs/agent_loop.yaml`, app runtime, dashboard JS refresh, and ticket TTL |
| Web dashboard | Improved MVP implemented | `/dashboard`, `/dashboard/state`, `/agent/loop/status`, `/paper/portfolio`, `/strategy/tournament/run`; queue table shows actionability/freshness/seconds left; tournament table shows OOS return/hit rate/windows |
| 操作及时性和时间有效性 | Improved MVP implemented | `ApprovalQueue.summary()` counts only fresh pending tickets as owner-actionable; expired tickets remain for audit |
| 稳定 webpage 交互平台入口 | Improved MVP implemented | AppleScript `Alpha.app` installed to Downloads, user Applications, and system `/Applications`; command launchers remain as compatibility entries |
| 策略迭代 | Improved MVP implemented | `run_strategy_tournament()` ranks momentum candidates with walk-forward OOS return, hit rate, validation windows, and tradability selection |
| `live_trading.enabled:true` | Superseded 2026-07-17 | 仓库默认配置仍永远 DISABLED(失败关闭不变);实盘激活仅经 owner 预签授权 + 十一门禁自动发生,见 `Alpha/AGENTS.md` 第 3 节 |
| 全自动实盘真实下单 | Superseded 2026-07-17 | 旧「须 owner 逐单确认」规则废止;改为受控许可模型:唯一执行网关 + 十一门禁 + 预签授权范围内自动真实下单(`Alpha/AGENTS.md`、`docs/decision_log.md` 2026-07-17 条目) |
