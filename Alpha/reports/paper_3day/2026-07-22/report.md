# 3 日 Paper+Shadow 报告 — 2026-07-22T21:27:09.838050+00:00

## A. 人话版

- 这三天:['2026-07-20', '2026-07-21', '2026-07-22'](合格 3/3 日),
  策略评估 2 次、出手 0 笔。
- 费后净收益 -10.63 AUD(毛 -10.63 − 费 0.00);
  折算月化速度 -2.48%(门槛容忍线 0.36%)。
- 胜率 0.0%、盈亏比 0.0、最大回撤 0.35%。
- 系统:可用性 99.91%、断线 0 次、最长恢复 0s、
  通知成功 100.0% p95 5.0s。
- 晋级判定:PROMO-2 绿 · PROMO-3 红 · PROMO-4 绿(PROMO-1 见回测报告)。
- **结论:未全绿:保持 Paper,进入调参循环并邮件报告差距**

## B. 核账版

- B1 运行:{"trading_days": ["2026-07-20", "2026-07-21", "2026-07-22"], "uptime_pct": 99.91, "reconnects": 0, "recovery_seconds_max": 0.0, "notify_success_pct": 100.0, "notify_p95_seconds": 4.98, "stale_quote_events": 0}
- B2 决策漏斗:{"strategy_evals": 2, "signals": 5, "risk_passed": 3, "risk_blocked_by_rule": {"RULE_MARKET_DATA_STALE": 2, "RULE_FAT_FINGER_SINGLE_ORDER": 1}, "submitted": 3, "accepted": 3, "filled": 3, "cancelled": 0, "rejected": 2}
- B3 收益与风险(费后):{"net_aud": -10.63, "gross_aud": -10.63, "fees_aud": 0.0, "max_drawdown_pct": 0.35}
- B4 策略质量(⚠️ 3 天样本置信度低):{"trades": 0, "wins": 0, "win_rate_pct": 0.0, "profit_factor": 0.0, "avg_win_aud": 0.0, "avg_loss_aud": 0.0, "confidence_warning": "3 天样本统计置信度低"}
- B5 Paper vs Shadow:{"price_gaps": [], "shadow_would_block": 0}
- B6 可靠性(应全 0):{"unknown_orders": 0, "reconciliation_diffs": 0, "idempotency_violations": 0, "illegal_transitions": 0, "outbox_failures": 0}
- B7 晋级判定明细:{"days_qualified": 3, "days_required": 3, "PROMO-1": {"gate": "回测月均达标(见 050 报告)", "status": "见回测报告", "note": "3 日运行不重算回测;PROMO-1 由 reports/backtest 最新判定提供"}, "PROMO-2": {"passed": true, "reason": "行为样本齐备"}, "PROMO-3": {"passed": false, "pace_month_pct": -2.48, "target_pct": 0.36, "reason": "折算月化速度低于门槛容忍线或样本不足", "confidence_warning": "3 日样本统计置信度低,速度判定仅作门槛过滤"}, "PROMO-4": {"passed": true, "zero_violations": true, "uptime_pct": 99.91, "notify_p95_seconds": 4.98, "reason": "工程零违规且可用性达标"}, "auto_promote": false, "decision": "未全绿:保持 Paper,进入调参循环并邮件报告差距"}

证据哈希见 `evidence_hashes.txt`;原始事件见 `events.jsonl`。
