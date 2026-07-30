from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Iterable

ALLOWED_DIRECTIONS = {-1, 0, 1}
ALLOWED_ACTIONS = {"BUY", "ADD", "HOLD", "REDUCE", "SELL", "WATCH", "AVOID", "NO_ACTION"}


def canonical_sha256(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_time(value: str) -> datetime:
    value = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _number(value: Any, name: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"INVALID_{name.upper()}")
    number = float(value)
    if low is not None and number < low:
        raise ValueError(f"INVALID_{name.upper()}")
    if high is not None and number > high:
        raise ValueError(f"INVALID_{name.upper()}")
    return number


def validate_skill_signal(signal: dict[str, Any]) -> dict[str, Any]:
    required = {
        "skill_id", "skill_version", "symbol", "market", "as_of", "available_at", "ingested_at",
        "direction", "confidence", "expected_return_pct", "downside_pct", "evidence_roots",
        "point_in_time_ok", "license_ok", "data_quality", "oos_valid", "dsr_confidence", "pbo",
        "liquidity_score", "cost_bps", "source_digest",
    }
    missing = sorted(required - set(signal))
    if missing:
        raise ValueError("MISSING_SIGNAL_FIELDS:" + ",".join(missing))
    result = dict(signal)
    for key in ("skill_id", "skill_version", "symbol", "market", "source_digest"):
        value = str(result[key]).strip()
        if not value or len(value) > 256:
            raise ValueError(f"INVALID_{key.upper()}")
        result[key] = value
    direction = result["direction"]
    if isinstance(direction, bool) or direction not in ALLOWED_DIRECTIONS:
        raise ValueError("INVALID_DIRECTION")
    result["confidence"] = _number(result["confidence"], "confidence", 0.0, 1.0)
    result["expected_return_pct"] = _number(result["expected_return_pct"], "expected_return_pct", -100.0, 1000.0)
    result["downside_pct"] = _number(result["downside_pct"], "downside_pct", -100.0, 0.0)
    result["data_quality"] = _number(result["data_quality"], "data_quality", 0.0, 1.0)
    result["dsr_confidence"] = _number(result["dsr_confidence"], "dsr_confidence", 0.0, 1.0)
    result["pbo"] = _number(result["pbo"], "pbo", 0.0, 1.0)
    result["liquidity_score"] = _number(result["liquidity_score"], "liquidity_score", 0.0, 1.0)
    result["cost_bps"] = _number(result["cost_bps"], "cost_bps", 0.0, 10000.0)
    for key in ("point_in_time_ok", "license_ok", "oos_valid"):
        if result[key] is not True and result[key] is not False:
            raise ValueError(f"INVALID_{key.upper()}")
    roots = result["evidence_roots"]
    if not isinstance(roots, list) or not roots or any(not isinstance(x, str) or not x.strip() for x in roots):
        raise ValueError("INVALID_EVIDENCE_ROOTS")
    result["evidence_roots"] = sorted(set(x.strip() for x in roots))
    as_of = parse_time(str(result["as_of"]))
    available_at = parse_time(str(result["available_at"]))
    ingested_at = parse_time(str(result["ingested_at"]))
    if available_at > as_of or ingested_at > as_of or ingested_at < available_at:
        result["point_in_time_ok"] = False
    result["as_of"] = as_of.isoformat()
    result["available_at"] = available_at.isoformat()
    result["ingested_at"] = ingested_at.isoformat()
    result.setdefault("catalysts", [])
    result.setdefault("risks", [])
    result.setdefault("kill_conditions", [])
    result.setdefault("horizon_days", 20)
    result.setdefault("reliability_weight", 1.0)
    result["reliability_weight"] = _number(result["reliability_weight"], "reliability_weight", 0.25, 2.0)
    return result


def validate_market_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    required = {
        "symbol", "market", "as_of", "available_at", "ingested_at", "price", "currency",
        "daily_value_traded_usd", "capacity_usd", "point_in_time_ok", "license_ok", "freshness_seconds",
        "source", "source_digest", "upstream_seal_pass",
    }
    missing = sorted(required - set(snapshot))
    if missing:
        raise ValueError("MISSING_MARKET_FIELDS:" + ",".join(missing))
    result = dict(snapshot)
    for key in ("symbol", "market", "currency", "source", "source_digest"):
        value = str(result[key]).strip()
        if not value or len(value) > 256:
            raise ValueError(f"INVALID_{key.upper()}")
        result[key] = value
    result["price"] = _number(result["price"], "price", 0.0000001)
    result["daily_value_traded_usd"] = _number(result["daily_value_traded_usd"], "daily_value_traded_usd", 0.0)
    result["capacity_usd"] = _number(result["capacity_usd"], "capacity_usd", 0.0)
    result["freshness_seconds"] = _number(result["freshness_seconds"], "freshness_seconds", 0.0)
    for key in ("point_in_time_ok", "license_ok", "upstream_seal_pass"):
        if result[key] is not True and result[key] is not False:
            raise ValueError(f"INVALID_{key.upper()}")
    as_of = parse_time(str(result["as_of"]))
    available_at = parse_time(str(result["available_at"]))
    ingested_at = parse_time(str(result["ingested_at"]))
    if available_at > as_of or ingested_at > as_of or ingested_at < available_at:
        result["point_in_time_ok"] = False
    result["as_of"] = as_of.isoformat()
    result["available_at"] = available_at.isoformat()
    result["ingested_at"] = ingested_at.isoformat()
    return result


def _weighted_average(items: Iterable[tuple[float, float]]) -> float:
    pairs = list(items)
    total = sum(weight for _, weight in pairs)
    return 0.0 if total <= 0 else sum(value * weight for value, weight in pairs) / total


def build_trusted_snapshot(
    signals: list[dict[str, Any]],
    market_snapshot: dict[str, Any],
    policy: dict[str, Any],
    *,
    current_position_pct: float = 0.0,
    requested_position_value_usd: float = 0.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not signals:
        raise ValueError("NO_SKILL_SIGNALS")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    sigs = [validate_skill_signal(x) for x in signals]
    market = validate_market_snapshot(market_snapshot)
    symbol = market["symbol"].upper()
    market_id = market["market"].upper()
    if any(s["symbol"].upper() != symbol or s["market"].upper() != market_id for s in sigs):
        raise ValueError("SIGNAL_MARKET_IDENTITY_MISMATCH")

    min_skills = int(policy.get("minimum_independent_skills", 2))
    min_roots = int(policy.get("minimum_independent_evidence_roots", 2))
    min_independence = float(policy.get("minimum_evidence_independence_ratio", 0.60))
    max_freshness = int(policy.get("maximum_freshness_seconds", 86400))
    min_net_edge = float(policy.get("minimum_net_expected_return_pct", 1.0))
    min_dsr = float(policy.get("minimum_dsr_confidence", 0.80))
    max_pbo = float(policy.get("maximum_pbo", 0.20))
    min_liquidity = float(policy.get("minimum_liquidity_score", 0.60))
    min_daily_value = float(policy.get("minimum_daily_value_traded_usd", 5_000_000))
    max_position_pct = float(policy.get("maximum_position_pct", 0.05))
    buy_threshold = float(policy.get("buy_score_threshold", 0.35))
    sell_threshold = float(policy.get("sell_score_threshold", -0.35))
    conflict_threshold = float(policy.get("critical_conflict_weight_ratio", 0.35))

    total_refs = sum(len(s["evidence_roots"]) for s in sigs)
    unique_roots = sorted({root for s in sigs for root in s["evidence_roots"]})
    independence_ratio = len(unique_roots) / max(total_refs, 1)
    weights = [s["confidence"] * s["data_quality"] * s["reliability_weight"] for s in sigs]
    score = _weighted_average((float(s["direction"]), w) for s, w in zip(sigs, weights))
    gross_expected = _weighted_average((s["expected_return_pct"], w) for s, w in zip(sigs, weights))
    downside = _weighted_average((s["downside_pct"], w) for s, w in zip(sigs, weights))
    cost_pct = max(s["cost_bps"] for s in sigs) / 100.0
    net_expected = gross_expected - cost_pct
    positive_weight = sum(w for s, w in zip(sigs, weights) if s["direction"] > 0)
    negative_weight = sum(w for s, w in zip(sigs, weights) if s["direction"] < 0)
    directional_weight = positive_weight + negative_weight
    conflict_ratio = min(positive_weight, negative_weight) / max(directional_weight, 1e-9)
    confidence = min(0.95, abs(score) * _weighted_average((s["confidence"], w) for s, w in zip(sigs, weights)) * min(1.0, independence_ratio / max(min_independence, 1e-9)))

    latest_ingested = max(parse_time(s["ingested_at"]) for s in sigs)
    age_seconds = max(0.0, (now - latest_ingested).total_seconds())
    gates = {
        "upstream_seal": bool(market["upstream_seal_pass"] and all(bool(s.get("source_digest")) for s in sigs)),
        "point_in_time": bool(market["point_in_time_ok"] and all(s["point_in_time_ok"] for s in sigs)),
        "freshness": bool(market["freshness_seconds"] <= max_freshness and age_seconds <= max_freshness),
        "license": bool(market["license_ok"] and all(s["license_ok"] for s in sigs)),
        "evidence": bool(len({s["skill_id"] for s in sigs}) >= min_skills and len(unique_roots) >= min_roots),
        "evidence_independence": bool(independence_ratio >= min_independence),
        "critical_conflict": bool(conflict_ratio < conflict_threshold),
        "oos_edge": bool(all(s["oos_valid"] for s in sigs) and net_expected >= min_net_edge),
        "overfit": bool(min(s["dsr_confidence"] for s in sigs) >= min_dsr and max(s["pbo"] for s in sigs) <= max_pbo),
        "cost": bool(net_expected > 0),
        "liquidity": bool(min(s["liquidity_score"] for s in sigs) >= min_liquidity and market["daily_value_traded_usd"] >= min_daily_value),
        "capacity": bool(requested_position_value_usd <= market["capacity_usd"]),
        "portfolio_risk": bool(0.0 <= current_position_pct <= max_position_pct),
        "runtime_zero_token": True,
    }

    if score >= buy_threshold:
        recommended = "ADD" if current_position_pct > 0 else "BUY"
    elif score <= sell_threshold:
        recommended = "SELL" if current_position_pct > 0 else "AVOID"
    elif current_position_pct > 0:
        recommended = "HOLD"
    else:
        recommended = "WATCH"

    position_high = min(max_position_pct, max(0.01, confidence * max_position_pct))
    position_low = min(position_high, max(0.0, position_high * 0.5))
    price = market["price"]
    entry_zone = [round(price * 0.99, 4), round(price * 1.01, 4)] if recommended in {"BUY", "ADD", "WATCH"} else None
    valid_until = min(parse_time(market["as_of"]), now).timestamp() + min(max_freshness, 86400)
    valid_until_dt = datetime.fromtimestamp(valid_until, tz=timezone.utc)
    catalysts = sorted({str(x) for s in sigs for x in s.get("catalysts", []) if str(x).strip()})
    risks = sorted({str(x) for s in sigs for x in s.get("risks", []) if str(x).strip()})
    kill_conditions = sorted({str(x) for s in sigs for x in s.get("kill_conditions", []) if str(x).strip()})

    recommendation = {
        "symbol": symbol,
        "market": market_id,
        "currency": market["currency"],
        "recommended_action": recommended,
        "entry_zone": entry_zone,
        "position_pct_range": [round(position_low, 4), round(position_high, 4)],
        "horizon_days": int(round(_weighted_average((float(s.get("horizon_days", 20)), w) for s, w in zip(sigs, weights)))),
        "expected_return_net_pct": round(net_expected, 4),
        "expected_return_gross_pct": round(gross_expected, 4),
        "downside_pct": round(downside, 4),
        "confidence": round(confidence, 4),
        "consensus_score": round(score, 4),
        "independent_skill_count": len({s["skill_id"] for s in sigs}),
        "independent_evidence_root_count": len(unique_roots),
        "evidence_independence_ratio": round(independence_ratio, 4),
        "critical_conflict_ratio": round(conflict_ratio, 4),
        "catalysts": catalysts,
        "risks": risks,
        "kill_conditions": kill_conditions,
        "evidence_refs": unique_roots,
        "skill_refs": sorted({f"{s['skill_id']}@{s['skill_version']}" for s in sigs}),
        "as_of": market["as_of"],
        "valid_until": valid_until_dt.isoformat(),
        "human_execution_only": True,
        "automatic_execution_allowed": False,
    }
    payload = {
        "schema_version": "1.0.0",
        "state": "PASS" if all(gates.values()) else "BLOCKED",
        "symbol": symbol,
        "market": market_id,
        "generated_at": now.isoformat(),
        "gates": gates,
        "recommendation": recommendation,
        "market_snapshot_digest": market["source_digest"],
        "signal_digests": sorted(s["source_digest"] for s in sigs),
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    return payload
