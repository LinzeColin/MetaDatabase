from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

REQUIRED_GATES = (
    "upstream_seal",
    "point_in_time",
    "freshness",
    "license",
    "evidence",
    "evidence_independence",
    "critical_conflict",
    "oos_edge",
    "overfit",
    "cost",
    "liquidity",
    "capacity",
    "portfolio_risk",
    "runtime_zero_token",
)


def decide(
    request: dict[str, Any],
    trusted: dict[str, Any],
    now: datetime | None = None,
    *,
    recommendation_enabled: bool = False,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    symbol = str(request.get("symbol", "UNKNOWN")).upper()[:24]
    market = str(request.get("market", "UNKNOWN")).upper()[:24]
    gates = trusted.get("gates", trusted if all(isinstance(v, bool) for v in trusted.values()) else {})
    failed = [gate for gate in REQUIRED_GATES if gates.get(gate) is not True]
    recommendation = trusted.get("recommendation") if isinstance(trusted.get("recommendation"), dict) else None
    if failed or not recommendation_enabled or not recommendation:
        return {
            "symbol": symbol,
            "market": market,
            "action": "NO_ACTION",
            "reasons": failed or (["HUMAN_RECOMMENDATION_MODE_DISABLED"] if not recommendation_enabled else ["TRUSTED_RECOMMENDATION_MISSING"]),
            "valid_until": (now + timedelta(hours=1)).isoformat(),
            "human_execution_only": True,
            "automatic_execution_allowed": False,
            "runtime_agent_dependency": 0,
            "runtime_llm_tokens": 0,
            "as_of": now.isoformat(),
            "confidence_namespace": "not_actionable",
            "evidence_refs": [],
        }
    action = str(recommendation.get("recommended_action", "NO_ACTION")).upper()
    if action not in {"BUY", "ADD", "HOLD", "REDUCE", "SELL", "WATCH", "AVOID"}:
        action = "NO_ACTION"
    packet = dict(recommendation)
    packet["action"] = action
    packet.pop("recommended_action", None)
    packet["reasons"] = [] if action != "NO_ACTION" else ["INVALID_RECOMMENDATION_ACTION"]
    packet["human_execution_only"] = True
    packet["automatic_execution_allowed"] = False
    packet["runtime_agent_dependency"] = 0
    packet["runtime_llm_tokens"] = 0
    return packet
