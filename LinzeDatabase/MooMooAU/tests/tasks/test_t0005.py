from __future__ import annotations

from validate_evidence import validate_record
from validate_stage0 import PROJECT_ROOT, evaluate_stage0


def test_t0005_shared_governance_is_external_and_pinned() -> None:
    result = evaluate_stage0(PROJECT_ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}
    assert checks["governance.no_framework_copy"] == "PASS"
    assert checks["governance.external_determinism"] == "PASS"
    assert result["signals"]["governance_failures"] == 0
    assert validate_record(PROJECT_ROOT / "evidence/tasks/T0005.json") == []
