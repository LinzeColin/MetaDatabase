from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_weights(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    weights = data.get("weights", {})
    if not isinstance(weights, dict):
        raise ValueError("INVALID_CALIBRATION_WEIGHTS")
    return {str(k): max(0.25, min(2.0, float(v))) for k, v in weights.items()}


def update_weights(current: dict[str, float], outcomes: list[dict[str, Any]], *, learning_rate: float = 0.10) -> dict[str, Any]:
    if not 0.0 < learning_rate <= 0.25:
        raise ValueError("INVALID_LEARNING_RATE")
    result = dict(current)
    evidence = []
    for row in outcomes:
        skill_id = str(row.get("skill_id", "")).strip()
        if not skill_id:
            raise ValueError("MISSING_SKILL_ID")
        prediction = float(row.get("predicted_probability", 0.5))
        outcome = float(row.get("outcome", 0.0))
        if not 0.0 <= prediction <= 1.0 or outcome not in (0.0, 1.0):
            raise ValueError("INVALID_CALIBRATION_OUTCOME")
        brier = (prediction - outcome) ** 2
        target = 0.5 + (1.0 - brier) * 1.5
        old = float(result.get(skill_id, 1.0))
        new = max(0.25, min(2.0, old * (1.0 - learning_rate) + target * learning_rate))
        result[skill_id] = round(new, 6)
        evidence.append({"skill_id": skill_id, "old": old, "new": new, "brier": round(brier, 6)})
    payload = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "weights": dict(sorted(result.items())),
        "updates": evidence,
        "immutable_constraints": ["ZERO_AGENT", "ZERO_LLM_TOKEN", "NO_AUTO_TRADING", "NO_UPSTREAM_WRITEBACK"],
    }
    payload["receipt_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload
