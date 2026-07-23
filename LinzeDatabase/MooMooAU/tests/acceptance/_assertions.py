from __future__ import annotations

from machine.acceptance.evidence import PROJECT_ROOT, evaluate_acceptance


def assert_final_acceptance(acceptance_id: str) -> None:
    result = evaluate_acceptance(acceptance_id, PROJECT_ROOT)
    assert result.valid, result.failure_message()
    assert result.passed, result.failure_message()
