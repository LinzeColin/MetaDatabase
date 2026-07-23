from __future__ import annotations

from validate_evidence import validate_record
from validate_stage0 import PROJECT_ROOT, evaluate_stage0


def test_t0003_synthetic_public_baseline_and_tree_are_redacted() -> None:
    result = evaluate_stage0(PROJECT_ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}
    assert checks["baseline.synthetic_redacted_fixture"] == "PASS"
    assert checks["security.publication_safety"] == "PASS"
    assert result["signals"]["publication_matches"] == 0
    assert result["signals"]["gmail_calls"] == 0
    assert validate_record(PROJECT_ROOT / "evidence/tasks/T0003.json") == []
