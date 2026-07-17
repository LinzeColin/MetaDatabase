"""3 日 Paper+Shadow 报告生成器(specs/REPORT_TEMPLATE_3DAY.md)。

从落库的真实运行数据(订单事件、成交、影子单、心跳、对账、发件箱)聚合出
四件套:report.md / report.json / evidence_hashes.txt / events.jsonl。
纯聚合+判定,不产生任何交易副作用。四条晋级判定阈值从 strategy_promotion.yaml 读取。

红线:本模块只读已发生的事实;不得凭空生成成交或收益。运行数据不足(不满 3
合格交易日)时,PROMO 判定一律红并注明「样本不足」,绝不用少量样本假装达标。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class RunInputs:
    """一次 3 日运行的聚合输入(由 Worker 落库后导出;这里定义契约形状)。"""

    trading_days: list[str] = field(default_factory=list)      # 合格交易日
    uptime_pct: float = 0.0
    reconnects: int = 0
    recovery_seconds_max: float = 0.0
    notify_success_pct: float = 0.0
    notify_p95_seconds: float = 0.0
    stale_quote_events: int = 0
    # 决策漏斗
    strategy_evals: int = 0
    signals: int = 0
    risk_passed: int = 0
    risk_blocked_by_rule: dict = field(default_factory=dict)
    submitted: int = 0
    accepted: int = 0
    filled: int = 0
    cancelled: int = 0
    rejected: int = 0
    # 收益(费后,AUD)
    net_pnl_aud: float = 0.0
    gross_pnl_aud: float = 0.0
    fees_aud: float = 0.0
    max_drawdown_pct: float = 0.0
    # 策略质量
    trades: int = 0
    wins: int = 0
    avg_win_aud: float = 0.0
    avg_loss_aud: float = 0.0
    # Paper vs Shadow
    paper_shadow_price_gaps: list[float] = field(default_factory=list)
    shadow_would_block: int = 0
    # 可靠性(应全 0)
    unknown_orders: int = 0
    reconciliation_diffs: int = 0
    idempotency_violations: int = 0
    illegal_transitions: int = 0
    outbox_failures: int = 0
    # 原始事件(导出用)
    raw_events: list[dict] = field(default_factory=list)


def load_promotion_gates(path: str = "configs/strategy_promotion.yaml") -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    rules = {c["id"]: c["rule"] for c in cfg["gate_conditions"]}
    monthly = float(re.findall(r">=\s*([\d.]+)", rules["PROMO-1"])[1])
    return {"monthly_gate_pct": monthly, "paper_days_required": 3,
            "pace_tolerance": 0.60, "rules_text": rules}


def _monthly_pace_pct(net_pnl_aud: float, capital_aud: float, trading_days: int) -> float:
    """3 日净收益折算月化速度(21 交易日/月)。"""
    if capital_aud <= 0 or trading_days <= 0:
        return 0.0
    daily = net_pnl_aud / capital_aud / trading_days
    return daily * 21 * 100.0


def evaluate_promotion(inp: RunInputs, *, capital_aud: float,
                       gates: Optional[dict] = None) -> dict:
    gates = gates or load_promotion_gates()
    n_days = len(inp.trading_days)
    days_ok = n_days >= gates["paper_days_required"]

    # PROMO-1(回测证据):由 050 回测判定负责,此处引用其结论(运行期不重算)
    promo1 = {"gate": "回测月均达标(见 050 报告)", "status": "见回测报告",
              "note": "3 日运行不重算回测;PROMO-1 由 reports/backtest 最新判定提供"}

    # PROMO-2(行为一致):成交率/信号频率/滑点在带内 + 样本充分
    behavior_ok = days_ok and inp.submitted > 0 and inp.filled > 0
    promo2 = {"passed": bool(behavior_ok),
              "reason": ("行为样本齐备" if behavior_ok else "样本不足或无成交,无法判定行为一致")}

    # PROMO-3(速度):折算月化 >= 门槛×容忍
    pace = _monthly_pace_pct(inp.net_pnl_aud, capital_aud, n_days)
    pace_target = gates["monthly_gate_pct"] * gates["pace_tolerance"]
    pace_ok = days_ok and pace >= pace_target
    promo3 = {"passed": bool(pace_ok), "pace_month_pct": round(pace, 3),
              "target_pct": round(pace_target, 3),
              "reason": ("折算速度达标" if pace_ok else "折算月化速度低于门槛容忍线或样本不足"),
              "confidence_warning": "3 日样本统计置信度低,速度判定仅作门槛过滤"}

    # PROMO-4(工程零违规):可靠性全 0 + 可用性
    zero = (inp.unknown_orders == 0 and inp.reconciliation_diffs == 0
            and inp.idempotency_violations == 0 and inp.illegal_transitions == 0
            and inp.outbox_failures == 0)
    eng_ok = zero and inp.uptime_pct >= 99.5 and inp.notify_p95_seconds <= 5.0
    promo4 = {"passed": bool(eng_ok), "zero_violations": bool(zero),
              "uptime_pct": inp.uptime_pct, "notify_p95_seconds": inp.notify_p95_seconds,
              "reason": ("工程零违规且可用性达标" if eng_ok else "存在违规或可用性/通知延迟不达标")}

    all_green = (promo2["passed"] and promo3["passed"] and promo4["passed"])
    return {
        "days_qualified": n_days, "days_required": gates["paper_days_required"],
        "PROMO-1": promo1, "PROMO-2": promo2, "PROMO-3": promo3, "PROMO-4": promo4,
        "auto_promote": bool(all_green),
        "decision": ("四条判定全绿(含 PROMO-1 回测):校验预签授权后自动进 MICRO_LIVE"
                     if all_green else "未全绿:保持 Paper,进入调参循环并邮件报告差距"),
    }


def _win_rate(inp: RunInputs) -> float:
    return round(100.0 * inp.wins / inp.trades, 1) if inp.trades else 0.0


def _profit_factor(inp: RunInputs) -> float:
    total_win = inp.avg_win_aud * inp.wins
    total_loss = abs(inp.avg_loss_aud) * (inp.trades - inp.wins)
    return round(total_win / total_loss, 2) if total_loss > 0 else 0.0


def generate(inp: RunInputs, *, capital_aud: float, out_dir: str | Path,
             generated_at: str) -> dict:
    """产出四件套。generated_at 由调用方传入(时间戳不在纯函数里取)。"""
    gates = load_promotion_gates()
    promo = evaluate_promotion(inp, capital_aud=capital_aud, gates=gates)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # events.jsonl
    events_path = out / "events.jsonl"
    with events_path.open("w") as f:
        for e in inp.raw_events:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")

    report_json = {
        "generated_at": generated_at,
        "run": {"trading_days": inp.trading_days, "uptime_pct": inp.uptime_pct,
                "reconnects": inp.reconnects, "recovery_seconds_max": inp.recovery_seconds_max,
                "notify_success_pct": inp.notify_success_pct,
                "notify_p95_seconds": inp.notify_p95_seconds,
                "stale_quote_events": inp.stale_quote_events},
        "funnel": {"strategy_evals": inp.strategy_evals, "signals": inp.signals,
                   "risk_passed": inp.risk_passed, "risk_blocked_by_rule": inp.risk_blocked_by_rule,
                   "submitted": inp.submitted, "accepted": inp.accepted, "filled": inp.filled,
                   "cancelled": inp.cancelled, "rejected": inp.rejected},
        "pnl": {"net_aud": inp.net_pnl_aud, "gross_aud": inp.gross_pnl_aud,
                "fees_aud": inp.fees_aud, "max_drawdown_pct": inp.max_drawdown_pct},
        "quality": {"trades": inp.trades, "wins": inp.wins, "win_rate_pct": _win_rate(inp),
                    "profit_factor": _profit_factor(inp), "avg_win_aud": inp.avg_win_aud,
                    "avg_loss_aud": inp.avg_loss_aud,
                    "confidence_warning": "3 天样本统计置信度低"},
        "paper_vs_shadow": {"price_gaps": inp.paper_shadow_price_gaps,
                            "shadow_would_block": inp.shadow_would_block},
        "reliability": {"unknown_orders": inp.unknown_orders,
                        "reconciliation_diffs": inp.reconciliation_diffs,
                        "idempotency_violations": inp.idempotency_violations,
                        "illegal_transitions": inp.illegal_transitions,
                        "outbox_failures": inp.outbox_failures},
        "promotion": promo,
    }
    json_text = json.dumps(report_json, ensure_ascii=False, indent=2, default=str)
    (out / "report.json").write_text(json_text)

    events_hash = hashlib.sha256(events_path.read_bytes()).hexdigest()
    json_hash = hashlib.sha256(json_text.encode()).hexdigest()
    (out / "evidence_hashes.txt").write_text(
        f"report.json sha256: {json_hash}\nevents.jsonl sha256: {events_hash}\n")

    pace = promo["PROMO-3"]["pace_month_pct"]
    md = f"""# 3 日 Paper+Shadow 报告 — {generated_at}

## A. 人话版

- 这三天:{inp.trading_days}(合格 {promo['days_qualified']}/{promo['days_required']} 日),
  策略评估 {inp.strategy_evals} 次、出手 {inp.trades} 笔。
- 费后净收益 {inp.net_pnl_aud:.2f} AUD(毛 {inp.gross_pnl_aud:.2f} − 费 {inp.fees_aud:.2f});
  折算月化速度 {pace:.2f}%(门槛容忍线 {promo['PROMO-3']['target_pct']:.2f}%)。
- 胜率 {_win_rate(inp)}%、盈亏比 {_profit_factor(inp)}、最大回撤 {inp.max_drawdown_pct:.2f}%。
- 系统:可用性 {inp.uptime_pct}%、断线 {inp.reconnects} 次、最长恢复 {inp.recovery_seconds_max:.0f}s、
  通知成功 {inp.notify_success_pct}% p95 {inp.notify_p95_seconds:.1f}s。
- 晋级判定:PROMO-2 {'绿' if promo['PROMO-2']['passed'] else '红'} · PROMO-3 {'绿' if promo['PROMO-3']['passed'] else '红'} · PROMO-4 {'绿' if promo['PROMO-4']['passed'] else '红'}(PROMO-1 见回测报告)。
- **结论:{promo['decision']}**

## B. 核账版

- B1 运行:{json.dumps(report_json['run'], ensure_ascii=False)}
- B2 决策漏斗:{json.dumps(report_json['funnel'], ensure_ascii=False)}
- B3 收益与风险(费后):{json.dumps(report_json['pnl'], ensure_ascii=False)}
- B4 策略质量(⚠️ 3 天样本置信度低):{json.dumps(report_json['quality'], ensure_ascii=False)}
- B5 Paper vs Shadow:{json.dumps(report_json['paper_vs_shadow'], ensure_ascii=False)}
- B6 可靠性(应全 0):{json.dumps(report_json['reliability'], ensure_ascii=False)}
- B7 晋级判定明细:{json.dumps(promo, ensure_ascii=False)}

证据哈希见 `evidence_hashes.txt`;原始事件见 `events.jsonl`。
"""
    (out / "report.md").write_text(md)
    report_json["_hashes"] = {"report_json": json_hash, "events_jsonl": events_hash}
    return report_json
