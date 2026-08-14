"""Package-local, path-pinned adapter for the task-pack root traceability oracle."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[1]
_MODULE = importlib.import_module("traceability_validator")
_EXPECTED_PATH = (_ROOT / "traceability_validator.py").resolve()
if Path(getattr(_MODULE, "__file__", "")).resolve() != _EXPECTED_PATH:
    raise ImportError("traceability validator must resolve to the ABD root artifact")


def _export(name: str) -> Any:
    return getattr(_MODULE, name)


def __getattr__(name: str) -> Any:
    return _export(name)


verify_existing_phase_evidence = _export("verify_existing_phase_evidence")
write_phase_evidence = _export("write_phase_evidence")
validate_candidate_preflight = _export("validate_candidate_preflight")


__all__ = [
    "BOUNDARY_SPEC",
    "CRITICAL_PHASE_IDS",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXPECTED_ARTIFACTS",
    "EXPECTED_TASK_IDS",
    "EXPECTED_TEST_IDS",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "GATE_IDS",
    "NEGATIVE_MUTATION_IDS",
    "ORACLE_PATH",
    "SOFTWARE_GATE_PATH",
    "TEST_PATH",
    "TraceabilityGateError",
    "evaluate_traceability_graph",
    "perform_rollback_drill",
    "validate_boundary_documents",
    "validate_candidate_preflight",
    "validate_fixture",
    "validate_signed_p03_receipt",
    "validate_software_gate",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
