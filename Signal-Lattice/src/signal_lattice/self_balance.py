from __future__ import annotations

import math
from typing import Any

from .db import RuntimeDB


def score_matured_outcomes(db: RuntimeDB, snapshot: dict[str, Any]) -> dict[str, Any]:
    price_by_key = {
        (str(row["market"]).upper(), str(row["symbol"]).upper()): float(row["price"])
        for row in snapshot.get("universe", []) if isinstance(row, dict) and float(row.get("price", 0.0)) > 0
    }
    now = str(snapshot["as_of"])
    scored = 0
    affected: set[tuple[str, str]] = set()
    for row in db.matured_outcomes(now):
        key = (str(row["market"]).upper(), str(row["symbol"]).upper())
        current = price_by_key.get(key)
        if current is None:
            continue
        reference = float(row["reference_price"])
        realized = current / reference - 1.0 if reference > 0 else 0.0
        actual_direction = 1 if realized > 0.002 else -1 if realized < -0.002 else 0
        forecast_direction = int(row["direction"])
        confidence = float(row["confidence"])
        predicted_probability_up = 0.5 + 0.5 * confidence * forecast_direction
        actual_up = 1.0 if actual_direction > 0 else 0.0
        brier = (predicted_probability_up - actual_up) ** 2
        correct = forecast_direction == actual_direction or (forecast_direction == 0 and actual_direction == 0)
        outcome = {
            "current_price": current,
            "realized_return": realized,
            "actual_direction": actual_direction,
            "forecast_direction": forecast_direction,
            "correct": correct,
            "brier_score": brier,
            "scored_at": now,
        }
        db.score_outcome(row, current, outcome)
        scored += 1
        affected.add((str(row["skill_id"]), key[0]))
    for skill_id, market in affected:
        rows = db.scored_outcomes(skill_id, market)
        if not rows:
            continue
        brier = sum(float(x["outcome"]["brier_score"]) for x in rows) / len(rows)
        accuracy = sum(1.0 for x in rows if x["outcome"]["correct"]) / len(rows)
        # Conservative bounded reliability; no skill can dominate or disappear.
        weight = max(0.50, min(1.50, 0.50 + accuracy - brier * 0.50))
        db.upsert_reliability(skill_id, market, 20, weight, len(rows), brier, accuracy)
    return {"state": "PASS", "scored": scored, "affected_skill_markets": len(affected)}


def queue_current_signals(db: RuntimeDB, cycle_id: str, snapshot: dict[str, Any], skill_results: list[dict[str, Any]]) -> int:
    prices = {
        (str(row["market"]).upper(), str(row["symbol"]).upper()): float(row["price"])
        for row in snapshot.get("universe", []) if isinstance(row, dict) and float(row.get("price", 0.0)) > 0
    }
    count = 0
    for result in skill_results:
        output = result.get("output")
        if not isinstance(output, dict):
            continue
        skill_id = str(result.get("skill_id", output.get("skill_id", "")))
        for signal in output.get("signals", []):
            if not isinstance(signal, dict) or signal.get("abstain") is True:
                continue
            key = (str(signal.get("market", "")).upper(), str(signal.get("symbol", "")).upper())
            price = prices.get(key)
            if price is None:
                continue
            db.queue_skill_outcome(cycle_id, skill_id, signal, price)
            count += 1
    return count
