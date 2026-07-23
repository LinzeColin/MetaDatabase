from __future__ import annotations

from validate_evidence import validate_record
from validate_stage0 import PROJECT_ROOT, evaluate_stage0


def test_t0002_invariants_and_platform_protocol_are_frozen() -> None:
    result = evaluate_stage0(PROJECT_ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}
    assert checks["invariants.frozen_values"] == "PASS"
    assert checks["invariants.schedule_platform_semantics"] == "PASS"
    assert checks["invariants.timeline_platform_protocol"] == "PASS"
    assert checks["contracts.stage_local_acceptance"] == "PASS"
    assert result["blocking_issue_ids"] == []
    assert validate_record(PROJECT_ROOT / "evidence/tasks/T0002.json") == []
