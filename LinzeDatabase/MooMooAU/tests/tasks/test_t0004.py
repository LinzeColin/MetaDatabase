from __future__ import annotations

import json

from validate_evidence import validate_record
from validate_stage0 import PROJECT_ROOT, evaluate_stage0


def test_t0004_cost_metrics_and_kill_criteria_are_complete() -> None:
    result = evaluate_stage0(PROJECT_ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}
    metrics = json.loads((PROJECT_ROOT / "machine/facts/metrics.json").read_text(encoding="utf-8"))
    kills = json.loads((PROJECT_ROOT / "machine/contracts/kill_criteria.json").read_text(encoding="utf-8"))
    assert checks["baseline.cost_and_kill"] == "PASS"
    assert len(metrics["metrics"]) == 12
    assert len(kills["kill_criteria"]) == 10
    assert validate_record(PROJECT_ROOT / "evidence/tasks/T0004.json") == []
