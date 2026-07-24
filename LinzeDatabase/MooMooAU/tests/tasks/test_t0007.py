from __future__ import annotations

from validate_evidence import validate_record
from validate_stage0 import PROJECT_ROOT, evaluate_stage0


def test_t0007_setup_is_documented_without_protected_actions() -> None:
    result = evaluate_stage0(PROJECT_ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}
    assert checks["baseline.one_time_setup"] == "PASS"
    assert checks["scope.no_stage1_or_deployment"] == "PASS"
    assert result["signals"]["deployment_actions"] == 0
    assert result["signals"]["secrets_read"] == 0
    assert result["signals"]["remote_writes"] == 0
    assert validate_record(PROJECT_ROOT / "evidence/tasks/T0007.json") == []
