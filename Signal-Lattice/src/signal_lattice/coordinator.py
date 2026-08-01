from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .recommendation import build_trusted_snapshot


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _market_record(snapshot: dict[str, Any], security: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "symbol": security["symbol"],
        "market": security["market"],
        "as_of": snapshot["as_of"],
        "available_at": snapshot.get("available_at", snapshot["as_of"]),
        "ingested_at": snapshot.get("ingested_at", snapshot["as_of"]),
        "price": float(security["price"]),
        "currency": str(security.get("currency", "USD")),
        "daily_value_traded_usd": float(security.get("daily_value_traded_usd", 0.0)),
        "capacity_usd": float(security.get("capacity_usd", 0.0)),
        "point_in_time_ok": bool(snapshot.get("point_in_time_ok", False)),
        "license_ok": bool(snapshot.get("license_ok", False)),
        "freshness_seconds": max(0.0, (now - datetime.fromisoformat(str(snapshot["as_of"]).replace("Z", "+00:00"))).total_seconds()),
        "source": str(snapshot.get("source", "UNKNOWN")),
        "source_digest": str(snapshot["source_digest"]),
        "upstream_seal_pass": bool(snapshot.get("upstream_seal_pass", False)),
    }


def coordinate_unique_recommendation(
    cycle_id: str,
    scheduled_for: str,
    snapshot: dict[str, Any],
    skill_results: list[dict[str, Any]],
    policy: dict[str, Any],
    reliability: dict[str, float],
    recommendation_enabled: bool,
    minimum_active_skills: int,
    minimum_completed_skills: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    active_count = len(skill_results)
    completed = [row for row in skill_results if row.get("state") in {"PASS", "ABSTAIN"}]
    effective_runs = [row for row in skill_results if row.get("state") == "PASS" and isinstance(row.get("output"), dict)]
    full_cycle = active_count >= minimum_active_skills and len(completed) == active_count
    signals_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in effective_runs:
        output = row.get("output") or {}
        for signal in output.get("signals", []):
            if not isinstance(signal, dict) or signal.get("abstain") is True:
                continue
            value = dict(signal)
            value["reliability_weight"] = float(reliability.get(str(value.get("skill_id")), 1.0))
            key = (str(value.get("market", "")).upper(), str(value.get("symbol", "")).upper())
            signals_by_key.setdefault(key, []).append(value)
    per_symbol: list[dict[str, Any]] = []
    security_by_key = {
        (str(item["market"]).upper(), str(item["symbol"]).upper()): item
        for item in snapshot.get("universe", []) if isinstance(item, dict)
    }
    for key, signals in sorted(signals_by_key.items()):
        security = security_by_key.get(key)
        if not security:
            continue
        metadata = security.get("portfolio") if isinstance(security.get("portfolio"), dict) else {}
        try:
            trusted = build_trusted_snapshot(
                signals,
                _market_record(snapshot, security, now),
                policy,
                current_position_pct=float(metadata.get("current_position_pct", 0.0)),
                requested_position_value_usd=float(metadata.get("requested_position_value_usd", 0.0)),
                now=now,
            )
        except (ValueError, KeyError, TypeError) as exc:
            per_symbol.append({
                "symbol": key[1], "market": key[0], "state": "BLOCKED",
                "gates": {}, "error": str(exc), "signals": len(signals),
            })
            continue
        per_symbol.append({**trusted, "signals": len(signals)})

    actionable: list[dict[str, Any]] = []
    for item in per_symbol:
        rec = item.get("recommendation")
        if item.get("state") != "PASS" or not isinstance(rec, dict):
            continue
        action = str(rec.get("recommended_action", "")).upper()
        if action not in {"BUY", "ADD", "HOLD", "REDUCE", "SELL", "WATCH", "AVOID"}:
            continue
        utility = abs(float(rec.get("expected_return_net_pct", 0.0))) * float(rec.get("confidence", 0.0))
        # Prefer actionable buy/sell decisions over passive watch when utility ties.
        priority = {"BUY": 5, "ADD": 5, "SELL": 4, "REDUCE": 4, "AVOID": 3, "HOLD": 2, "WATCH": 1}.get(action, 0)
        actionable.append({"item": item, "utility": utility, "priority": priority})
    actionable.sort(
        key=lambda row: (
            row["utility"], row["priority"],
            str(row["item"]["recommendation"].get("market", "")),
            str(row["item"]["recommendation"].get("symbol", "")),
        ),
        reverse=True,
    )

    system_blockers: list[str] = []
    if active_count < minimum_active_skills:
        system_blockers.append("ACTIVE_SKILL_COUNT_BELOW_NORTHSTAR_MINIMUM")
    if len(completed) < minimum_completed_skills:
        system_blockers.append("COMPLETED_SKILL_COUNT_BELOW_NORTHSTAR_MINIMUM")
    if not snapshot.get("universe"):
        system_blockers.append("MARKET_UNIVERSE_EMPTY")
    if not full_cycle:
        system_blockers.append("NOT_ALL_ACTIVE_SKILLS_RETURNED_THIS_MINUTE")

    if system_blockers:
        recommendation = {
            "action": "SYSTEM_BLOCKED",
            "symbol": None,
            "market": None,
            "reasons": sorted(set(system_blockers)),
            "message": "本分钟完整链路未完成，系统不把空数据伪装成投资建议。",
            "valid_until": (now + timedelta(seconds=60)).isoformat(),
        }
        state = "SYSTEM_BLOCKED"
    elif actionable and recommendation_enabled:
        winner = actionable[0]["item"]["recommendation"]
        recommendation = dict(winner)
        recommendation["action"] = recommendation.pop("recommended_action")
        recommendation["reasons"] = []
        recommendation["selected_from_symbol_count"] = len(per_symbol)
        recommendation["selection_utility"] = round(actionable[0]["utility"], 6)
        state = "RECOMMENDATION"
    else:
        failed_gates: set[str] = set()
        for item in per_symbol:
            for gate, passed in (item.get("gates") or {}).items():
                if passed is not True:
                    failed_gates.add(str(gate))
        reasons = [f"INVESTMENT_GATE_FAILED:{gate}" for gate in sorted(failed_gates)]
        if not per_symbol:
            reasons.append("ALL_SKILLS_ABSTAINED_AFTER_COMPLETE_EXECUTION")
        if not recommendation_enabled:
            reasons.append("HUMAN_DECISION_SUPPORT_DISABLED")
        recommendation = {
            "action": "NO_ACTION",
            "symbol": None,
            "market": None,
            "reasons": reasons or ["NO_CANDIDATE_PASSED_COORDINATION"],
            "message": "所有子 Skill 已独立完成判断，中枢协调后决定本分钟不行动。",
            "valid_until": (now + timedelta(seconds=60)).isoformat(),
        }
        state = "NO_ACTION"

    recommendation.update({
        "schema_version": "2.0.0",
        "cycle_id": cycle_id,
        "scheduled_for": scheduled_for,
        "generated_at": now.isoformat(),
        "next_cycle_at": (now.replace(second=0, microsecond=0) + timedelta(minutes=1)).isoformat(),
        "full_cycle_completed": full_cycle,
        "active_skill_count": active_count,
        "completed_skill_count": len(completed),
        "effective_skill_count": len(effective_runs),
        "failed_skill_count": len([x for x in skill_results if x.get("state") not in {"PASS", "ABSTAIN"}]),
        "candidate_symbol_count": len(per_symbol),
        "per_symbol": per_symbol,
        "skill_judgements": [
            {
                "skill_id": row.get("skill_id"),
                "state": row.get("state"),
                "duration_ms": row.get("duration_ms"),
                "effective_signal_count": (row.get("output") or {}).get("effective_signal_count", 0),
                "abstain_count": (row.get("output") or {}).get("abstain_count", 0),
                "error_code": row.get("error_code"),
            }
            for row in sorted(skill_results, key=lambda x: str(x.get("skill_id")))
        ],
        "human_execution_only": True,
        "automatic_execution_allowed": False,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "state": state,
        "market_data_source": snapshot.get("source", "UNKNOWN"),
        "market_data_production_eligible": bool(snapshot.get("production_eligible", False)),
        "market_data_license_ok": bool(snapshot.get("license_ok", False)),
        "market_snapshot_sha256": snapshot.get("source_digest"),
    })
    recommendation["receipt_sha256"] = canonical_sha256(recommendation)
    return recommendation
