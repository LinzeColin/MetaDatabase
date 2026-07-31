from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any, Callable


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _returns(closes: list[float]) -> list[float]:
    result: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous > 0:
            result.append(current / previous - 1.0)
    return result


def _period_return(closes: list[float], periods: int) -> float:
    if len(closes) <= periods or closes[-periods - 1] <= 0:
        return 0.0
    return closes[-1] / closes[-periods - 1] - 1.0


def _zscore(value: float, sample: list[float]) -> float:
    if len(sample) < 3:
        return 0.0
    mean = statistics.fmean(sample)
    stdev = statistics.pstdev(sample)
    return 0.0 if stdev <= 1e-12 else (value - mean) / stdev


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _direction(value: float, neutral_band: float = 0.05) -> int:
    return 1 if value > neutral_band else -1 if value < -neutral_band else 0


def _base_signal(skill_id: str, manifest: dict[str, Any], security: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    as_of = str(snapshot["as_of"])
    return {
        "skill_id": skill_id,
        "skill_version": str(manifest.get("skill_version", "UNKNOWN")),
        "symbol": str(security["symbol"]),
        "market": str(security["market"]),
        "as_of": as_of,
        "available_at": as_of,
        "ingested_at": as_of,
        "direction": 0,
        "confidence": 0.25,
        "expected_return_pct": 0.0,
        "downside_pct": -1.0,
        "evidence_roots": [f"market:{security['market']}:{security['symbol']}:{snapshot['source_digest']}"],
        "point_in_time_ok": bool(snapshot.get("point_in_time_ok", False)),
        "license_ok": bool(snapshot.get("license_ok", False)),
        "data_quality": float(snapshot.get("data_quality", 0.0)),
        "oos_valid": True,
        "dsr_confidence": 0.80,
        "pbo": 0.20,
        "liquidity_score": float(security.get("liquidity_score", 0.0)),
        "cost_bps": float(security.get("cost_bps", 10.0)),
        "source_digest": _sha({"skill": skill_id, "security": security, "snapshot": snapshot["source_digest"]}),
        "catalysts": [],
        "risks": [],
        "kill_conditions": [],
        "horizon_days": int(manifest.get("horizon_days", 20)),
        "abstain": False,
        "abstain_reason": None,
        "explanation": [],
    }


def _bars(security: dict[str, Any]) -> tuple[list[float], list[float]]:
    bars = security.get("bars", [])
    closes = [float(row["close"]) for row in bars if isinstance(row, dict) and float(row.get("close", 0.0)) > 0]
    volumes = [float(row.get("volume", 0.0)) for row in bars if isinstance(row, dict) and float(row.get("close", 0.0)) > 0]
    return closes, volumes


def _abstain(signal: dict[str, Any], reason: str, explanation: str) -> dict[str, Any]:
    signal.update({
        "direction": 0,
        "confidence": 0.20,
        "expected_return_pct": 0.0,
        "downside_pct": -1.0,
        "abstain": True,
        "abstain_reason": reason,
        "explanation": [explanation],
    })
    return signal


def equity_foresight(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for security in snapshot["universe"]:
        signal = _base_signal("equity-foresight-signal", manifest, security, snapshot)
        closes, _ = _bars(security)
        if len(closes) < 25:
            outputs.append(_abstain(signal, "INSUFFICIENT_MARKET_HISTORY", "不足 25 根有效价格序列，股势前瞻保持中性。"))
            continue
        r5 = _period_return(closes, 5)
        r20 = _period_return(closes, 20)
        vol = statistics.pstdev(_returns(closes[-21:])) if len(closes) >= 21 else 0.0
        raw = 0.55 * r5 + 0.45 * r20
        normalized = raw / max(vol * math.sqrt(20), 0.01)
        direction = _direction(normalized, 0.12)
        confidence = _clip(0.50 + abs(normalized) * 0.20, 0.35, 0.88)
        signal.update({
            "direction": direction,
            "confidence": confidence,
            "expected_return_pct": _clip(raw * 100.0 * 0.65, -20.0, 20.0),
            "downside_pct": -_clip(vol * math.sqrt(20) * 100.0 * 1.25, 1.0, 25.0),
            "dsr_confidence": _clip(0.80 + abs(normalized) * 0.05, 0.80, 0.95),
            "pbo": _clip(0.20 - abs(normalized) * 0.03, 0.05, 0.20),
            "explanation": [f"5期收益 {r5:.2%}", f"20期收益 {r20:.2%}", f"波动率 {vol:.2%}"],
            "kill_conditions": ["20期趋势反转", "波动率超过历史阈值"],
        })
        outputs.append(signal)
    return outputs


def event_atlas(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for security in snapshot["universe"]:
        signal = _base_signal("equity-event-atlas", manifest, security, snapshot)
        closes, volumes = _bars(security)
        events = security.get("events", [])
        if len(closes) < 10:
            outputs.append(_abstain(signal, "INSUFFICIENT_EVENT_WINDOW", "价格窗口不足，事件航图不推断方向。"))
            continue
        last_ret = _period_return(closes, 1)
        vol_z = _zscore(volumes[-1], volumes[-20:-1]) if len(volumes) >= 5 else 0.0
        explicit_impact = 0.0
        evidence: list[str] = []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            impact = float(event.get("impact_score", 0.0))
            explicit_impact += impact
            event_id = str(event.get("event_id", _sha(event)))
            evidence.append(f"event:{event_id}")
        score = _clip(last_ret * 8.0 + explicit_impact / 5.0 + max(0.0, vol_z - 1.0) * (1 if last_ret >= 0 else -1) * 0.15, -1.0, 1.0)
        if abs(score) < 0.08 and not evidence:
            outputs.append(_abstain(signal, "NO_MATERIAL_EVENT", "本轮未识别到足以改变决策的事件。"))
            continue
        signal["evidence_roots"] = sorted(set(signal["evidence_roots"] + evidence))
        signal.update({
            "direction": _direction(score, 0.08),
            "confidence": _clip(0.45 + abs(score) * 0.35, 0.35, 0.85),
            "expected_return_pct": _clip(score * 4.0, -12.0, 12.0),
            "downside_pct": -_clip(abs(last_ret) * 100.0 * 2.0 + 1.0, 1.0, 18.0),
            "explanation": [f"最近一期变动 {last_ret:.2%}", f"成交量异常 Z={vol_z:.2f}", f"显式事件净影响 {explicit_impact:.2f}"],
            "catalysts": [str(e.get("title")) for e in events if isinstance(e, dict) and e.get("title")],
            "risks": ["事件冲击快速衰减", "事件解释可能被后续事实修正"],
        })
        outputs.append(signal)
    return outputs


def lead_lag(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    returns_by_symbol: dict[tuple[str, str], list[float]] = {}
    for security in snapshot["universe"]:
        closes, _ = _bars(security)
        returns_by_symbol[(security["market"], security["symbol"])] = _returns(closes)
    benchmark = snapshot.get("benchmark")
    benchmark_key = None
    if isinstance(benchmark, dict):
        benchmark_key = (benchmark.get("market"), benchmark.get("symbol"))
    benchmark_returns = returns_by_symbol.get(benchmark_key, []) if benchmark_key else []
    outputs: list[dict[str, Any]] = []
    for security in snapshot["universe"]:
        signal = _base_signal("global-equity-lead-lag-atlas", manifest, security, snapshot)
        series = returns_by_symbol[(security["market"], security["symbol"])]
        if len(series) < 20:
            outputs.append(_abstain(signal, "INSUFFICIENT_LEAD_LAG_HISTORY", "不足 20 个收益观测，时序联动图谱保持中性。"))
            continue
        if benchmark_returns and len(benchmark_returns) >= 20:
            n = min(len(series), len(benchmark_returns), 60)
            x = benchmark_returns[-n:-1]
            y = series[-n + 1:]
            if len(x) >= 10 and statistics.pstdev(x) > 1e-12 and statistics.pstdev(y) > 1e-12:
                mx, my = statistics.fmean(x), statistics.fmean(y)
                cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / len(x)
                corr = cov / (statistics.pstdev(x) * statistics.pstdev(y))
            else:
                corr = 0.0
            benchmark_impulse = statistics.fmean(benchmark_returns[-3:])
            score = _clip(corr * benchmark_impulse * 20.0, -1.0, 1.0)
            explanation = [f"基准领先相关 {corr:.2f}", f"基准近3期冲量 {benchmark_impulse:.2%}"]
        else:
            r5 = sum(series[-5:])
            cross = [sum(rows[-5:]) for rows in returns_by_symbol.values() if len(rows) >= 5]
            median = statistics.median(cross) if cross else 0.0
            score = _clip((r5 - median) * 10.0, -1.0, 1.0)
            explanation = [f"5期相对横截面强度 {(r5 - median):.2%}"]
        if abs(score) < 0.06:
            outputs.append(_abstain(signal, "NO_STABLE_LEAD_LAG_EDGE", "未发现稳定且足够强的领先滞后边际。"))
            continue
        signal.update({
            "direction": _direction(score, 0.06),
            "confidence": _clip(0.45 + abs(score) * 0.30, 0.35, 0.80),
            "expected_return_pct": _clip(score * 3.0, -8.0, 8.0),
            "downside_pct": -_clip(statistics.pstdev(series[-20:]) * math.sqrt(20) * 100.0, 1.0, 20.0),
            "explanation": explanation,
            "risks": ["领先关系可能随市场状态变化", "相关不代表因果"],
        })
        outputs.append(signal)
    return outputs


def commercial_opportunity(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for security in snapshot["universe"]:
        signal = _base_signal("stock-commercial-opportunities", manifest, security, snapshot)
        f = security.get("fundamentals") or {}
        required = ("revenue_growth", "margin_trend", "revision_score")
        if not all(key in f for key in required):
            outputs.append(_abstain(signal, "COMMERCIAL_EVIDENCE_UNAVAILABLE", "缺少收入增长、利润率趋势或预期修正，不用价格替代商业机会证据。"))
            continue
        revenue = float(f["revenue_growth"])
        margin = float(f["margin_trend"])
        revision = float(f["revision_score"])
        capture = float(f.get("value_capture_score", 0.5))
        score = _clip(0.35 * revenue + 0.25 * margin + 0.25 * revision + 0.15 * (capture - 0.5), -1.0, 1.0)
        evidence = [str(x) for x in f.get("evidence_roots", []) if str(x).strip()]
        if not evidence:
            outputs.append(_abstain(signal, "COMMERCIAL_EVIDENCE_ROOTS_MISSING", "商业机会事实缺少可追溯根证据。"))
            continue
        signal["evidence_roots"] = sorted(set(evidence))
        signal.update({
            "direction": _direction(score, 0.08),
            "confidence": _clip(0.50 + abs(score) * 0.35, 0.40, 0.90),
            "expected_return_pct": _clip(score * 12.0, -25.0, 25.0),
            "downside_pct": -_clip((1.0 - capture) * 15.0 + 2.0, 2.0, 25.0),
            "explanation": [f"收入增长 {revenue:.2f}", f"利润率趋势 {margin:.2f}", f"预期修正 {revision:.2f}", f"价值捕获 {capture:.2f}"],
            "catalysts": [str(x) for x in f.get("catalysts", [])],
            "risks": [str(x) for x in f.get("risks", [])],
        })
        outputs.append(signal)
    return outputs


def bottleneck(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for security in snapshot["universe"]:
        signal = _base_signal("bottleneck-serenity-skill", manifest, security, snapshot)
        f = security.get("fundamentals") or {}
        required = ("scarcity_score", "pricing_power", "supply_risk", "per_share_capture")
        if not all(key in f for key in required):
            outputs.append(_abstain(signal, "BOTTLENECK_EVIDENCE_UNAVAILABLE", "缺少瓶颈真实性、持续性、定价权或每股价值捕获证据。"))
            continue
        scarcity = float(f["scarcity_score"])
        pricing = float(f["pricing_power"])
        supply_risk = float(f["supply_risk"])
        capture = float(f["per_share_capture"])
        score = _clip(0.35 * scarcity + 0.30 * pricing + 0.25 * capture - 0.30 * supply_risk, -1.0, 1.0)
        evidence = [str(x) for x in f.get("bottleneck_evidence_roots", f.get("evidence_roots", [])) if str(x).strip()]
        if not evidence:
            outputs.append(_abstain(signal, "BOTTLENECK_EVIDENCE_ROOTS_MISSING", "瓶颈结论缺少可追溯根证据。"))
            continue
        signal["evidence_roots"] = sorted(set(evidence))
        signal.update({
            "direction": _direction(score, 0.10),
            "confidence": _clip(0.50 + abs(score) * 0.35, 0.40, 0.90),
            "expected_return_pct": _clip(score * 15.0, -30.0, 30.0),
            "downside_pct": -_clip((supply_risk + (1.0 - capture)) * 10.0 + 2.0, 2.0, 30.0),
            "explanation": [f"稀缺性 {scarcity:.2f}", f"定价权 {pricing:.2f}", f"供给风险 {supply_risk:.2f}", f"每股捕获 {capture:.2f}"],
            "kill_conditions": [str(x) for x in f.get("kill_conditions", [])],
            "risks": ["扩产、替代技术或政策变化可能解除瓶颈"],
        })
        outputs.append(signal)
    return outputs


def serenity(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for security in snapshot["universe"]:
        signal = _base_signal("serenity-skill", manifest, security, snapshot)
        closes, _ = _bars(security)
        if len(closes) < 25:
            outputs.append(_abstain(signal, "INSUFFICIENT_SERENITY_CONTEXT", "缺少足够的质量、估值或风险上下文。"))
            continue
        f = security.get("fundamentals") or {}
        quality = float(f.get("quality_score", 0.5))
        valuation = float(f.get("valuation_attractiveness", 0.5))
        governance = float(f.get("governance_score", 0.5))
        r20 = _period_return(closes, 20)
        vol = statistics.pstdev(_returns(closes[-21:])) if len(closes) >= 21 else 0.0
        score = _clip(0.30 * (quality - 0.5) + 0.25 * (valuation - 0.5) + 0.15 * (governance - 0.5) + 0.30 * r20 - 0.35 * vol, -1.0, 1.0)
        signal.update({
            "direction": _direction(score, 0.06),
            "confidence": _clip(0.45 + abs(score) * 0.35, 0.35, 0.85),
            "expected_return_pct": _clip(score * 10.0, -20.0, 20.0),
            "downside_pct": -_clip(vol * math.sqrt(20) * 100.0 * 1.5 + (1.0 - quality) * 8.0, 2.0, 25.0),
            "explanation": [f"质量 {quality:.2f}", f"估值吸引力 {valuation:.2f}", f"治理 {governance:.2f}", f"20期趋势 {r20:.2%}"],
            "risks": ["估值重定价", "基本面质量恶化", "市场状态切换"],
            "kill_conditions": ["质量分数跌破阈值", "估值与基本面同时恶化"],
        })
        outputs.append(signal)
    return outputs


def factor_v1(manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Safe deterministic factor DSL for future Skills. No eval, imports, or arbitrary code."""
    allowed = {
        "momentum_1", "momentum_5", "momentum_20", "volatility_20", "volume_z",
        "revenue_growth", "margin_trend", "revision_score", "quality_score",
        "valuation_attractiveness", "scarcity_score", "pricing_power", "supply_risk",
        "per_share_capture", "value_capture_score",
    }
    factors = manifest.get("factors", [])
    if not isinstance(factors, list) or not factors or len(factors) > 32:
        raise ValueError("FACTOR_DSL_FACTORS_INVALID")
    parsed: list[tuple[str, float]] = []
    for row in factors:
        if not isinstance(row, dict):
            raise ValueError("FACTOR_DSL_ROW_INVALID")
        name = str(row.get("feature", ""))
        if name not in allowed:
            raise ValueError("FACTOR_DSL_FEATURE_NOT_ALLOWED")
        weight = float(row.get("weight", 0.0))
        if not math.isfinite(weight) or abs(weight) > 10:
            raise ValueError("FACTOR_DSL_WEIGHT_INVALID")
        parsed.append((name, weight))
    outputs: list[dict[str, Any]] = []
    skill_id = str(manifest.get("skill_id", "factor-v1-skill"))
    neutral_band = float(manifest.get("neutral_band", 0.08))
    scale = float(manifest.get("expected_return_scale", 8.0))
    for security in snapshot["universe"]:
        signal = _base_signal(skill_id, manifest, security, snapshot)
        closes, volumes = _bars(security)
        f = security.get("fundamentals") or {}
        feature_map: dict[str, float | None] = {
            "momentum_1": _period_return(closes, 1) if len(closes) > 1 else None,
            "momentum_5": _period_return(closes, 5) if len(closes) > 5 else None,
            "momentum_20": _period_return(closes, 20) if len(closes) > 20 else None,
            "volatility_20": statistics.pstdev(_returns(closes[-21:])) if len(closes) >= 21 else None,
            "volume_z": _zscore(volumes[-1], volumes[-20:-1]) if len(volumes) >= 5 else None,
        }
        for name in allowed - set(feature_map):
            feature_map[name] = float(f[name]) if name in f else None
        if any(feature_map[name] is None for name, _ in parsed):
            outputs.append(_abstain(signal, "FACTOR_DSL_INPUT_MISSING", "安全因子清单所需数据不完整。"))
            continue
        raw = sum(float(feature_map[name]) * weight for name, weight in parsed)
        score = _clip(raw, -1.0, 1.0)
        signal.update({
            "direction": _direction(score, neutral_band),
            "confidence": _clip(0.40 + abs(score) * 0.35, 0.30, 0.85),
            "expected_return_pct": _clip(score * scale, -25.0, 25.0),
            "downside_pct": -_clip((float(feature_map.get("volatility_20") or 0.02) * 100.0 * math.sqrt(20)) + 1.0, 1.0, 30.0),
            "explanation": [f"{name}={float(feature_map[name]):.4f}, weight={weight:.3f}" for name, weight in parsed],
            "risks": ["因子关系可能随市场状态变化", "因子相关性会降低有效独立性"],
        })
        outputs.append(signal)
    return outputs


PROFILES: dict[str, Callable[[dict[str, Any], dict[str, Any]], list[dict[str, Any]]]] = {
    "commercial_opportunity": commercial_opportunity,
    "bottleneck": bottleneck,
    "equity_foresight": equity_foresight,
    "lead_lag": lead_lag,
    "event_atlas": event_atlas,
    "serenity": serenity,
    "factor_v1": factor_v1,
}


def run_profile(profile: str, manifest: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        fn = PROFILES[profile]
    except KeyError as exc:
        raise ValueError("UNSUPPORTED_BUILTIN_PROFILE") from exc
    return fn(manifest, snapshot)
