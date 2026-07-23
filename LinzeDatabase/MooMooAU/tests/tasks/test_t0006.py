from __future__ import annotations

from validate_evidence import validate_record
from validate_stage0 import PROJECT_ROOT, evaluate_stage0


def test_t0006_seven_files_are_byte_deterministic_and_pass_shared_gates() -> None:
    result = evaluate_stage0(PROJECT_ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}
    assert checks["governance.seven_files_generated"] == "PASS"
    assert checks["governance.external_determinism"] == "PASS"
    assert result["verifier_status"] == "PASS"
    assert validate_record(PROJECT_ROOT / "evidence/tasks/T0006.json") == []
