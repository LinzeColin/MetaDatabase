from __future__ import annotations

import hashlib
import json
from typing import Any

from .recommendation import validate_skill_signal

KNOWN_SKILLS = {
    "stock-commercial-opportunities",
    "bottleneck-serenity-skill",
    "equity-foresight-signal",
    "global-equity-lead-lag-atlas",
    "equity-event-atlas",
    "serenity-skill",
}


def _digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _value(payload: dict[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        current: Any = payload
        ok = True
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                ok = False
                break
            current = current[part]
        if ok:
            return current
    return default


def _direction(value: Any) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return 1 if value > 0 else -1 if value < 0 else 0
    text = str(value or "").strip().upper()
    positive = {"BUY", "ADD", "BULLISH", "POSITIVE", "CANDIDATE", "RESEARCH_PRIORITY", "FORECAST_UP", "ADVANCE_RESEARCH"}
    negative = {"SELL", "REDUCE", "BEARISH", "NEGATIVE", "AVOID", "BROKEN", "REJECT", "FORECAST_DOWN"}
    return 1 if text in positive else -1 if text in negative else 0


def normalize_skill_artifact(payload: dict[str, Any], *, skill_id: str | None = None) -> dict[str, Any]:
    if "skill_id" in payload and "expected_return_pct" in payload and "evidence_roots" in payload:
        return validate_skill_signal(payload)

    sid = str(skill_id or _value(payload, "skill_id", "skill.id", "name", default="")).strip()
    if not sid:
        raise ValueError("SKILL_ID_REQUIRED")
    if sid not in KNOWN_SKILLS and not sid.startswith("custom-"):
        raise ValueError("UNREGISTERED_SKILL_ADAPTER")
    symbol = str(_value(payload, "symbol", "security.symbol", "ticker", default="")).strip()
    market = str(_value(payload, "market", "security.market", "exchange", default="")).strip()
    as_of = str(_value(payload, "as_of", "generated_at", "forecast.as_of", default="")).strip()
    available_at = str(_value(payload, "available_at", "published_at", "forecast.available_at", default=as_of)).strip()
    ingested_at = str(_value(payload, "ingested_at", "observed_at", default=as_of)).strip()
    if not all((symbol, market, as_of)):
        raise ValueError("SKILL_ARTIFACT_IDENTITY_OR_TIME_MISSING")

    abstain = bool(_value(payload, "abstain", "forecast.abstain", default=False))
    label = _value(payload, "direction", "decision.label", "decision", "forecast.direction", default=0)
    direction = 0 if abstain else _direction(label)
    confidence = float(_value(payload, "confidence", "reliability", "forecast.reliability", default=0.5))
    if confidence > 1.0:
        confidence /= 100.0
    data_quality = float(_value(payload, "data_quality", "forecast.data_quality", "evidence_confidence", default=0.5))
    if data_quality > 1.0:
        data_quality /= 100.0
    expected = float(_value(payload, "expected_return_pct", "economic_edge", "forecast.economic_edge", "scenario.expected_return_pct", default=0.0))
    downside = float(_value(payload, "downside_pct", "scenario.downside_pct", default=min(0.0, -abs(expected) * 0.75)))
    if downside > 0:
        downside = -downside
    roots = _value(payload, "evidence_roots", "evidence.root_ids", "claim_evidence_roots", default=[])
    if not isinstance(roots, list) or not roots:
        roots = [f"artifact:{_digest(payload)}"]
    pbo = float(_value(payload, "pbo", "quant.pbo", default=0.0 if bool(_value(payload, "oos_valid", default=False)) else 1.0))
    dsr = float(_value(payload, "dsr_confidence", "quant.dsr_confidence", default=0.0))
    liquidity = float(_value(payload, "liquidity_score", "investability.liquidity_score", default=0.0))
    cost_bps = float(_value(payload, "cost_bps", "quant.cost_bps", default=0.0))
    signal = {
        "skill_id": sid,
        "skill_version": str(_value(payload, "skill_version", "version", default="UNKNOWN")),
        "symbol": symbol,
        "market": market,
        "as_of": as_of,
        "available_at": available_at,
        "ingested_at": ingested_at,
        "direction": direction,
        "confidence": confidence,
        "expected_return_pct": expected,
        "downside_pct": downside,
        "evidence_roots": roots,
        "point_in_time_ok": bool(_value(payload, "point_in_time_ok", "quant.point_in_time_ok", default=False)),
        "license_ok": bool(_value(payload, "license_ok", "provenance.license_ok", default=False)),
        "data_quality": data_quality,
        "oos_valid": bool(_value(payload, "oos_valid", "quant.oos_valid", default=False)),
        "dsr_confidence": dsr,
        "pbo": pbo,
        "liquidity_score": liquidity,
        "cost_bps": cost_bps,
        "source_digest": str(_value(payload, "source_digest", "artifact_sha256", default=_digest(payload))),
        "catalysts": _value(payload, "catalysts", "decision.catalysts", default=[]),
        "risks": _value(payload, "risks", "decision.risks", default=[]),
        "kill_conditions": _value(payload, "kill_conditions", "decision.kill_switches", default=[]),
        "horizon_days": int(_value(payload, "horizon_days", "forecast.horizon_days", default=20)),
    }
    return validate_skill_signal(signal)
