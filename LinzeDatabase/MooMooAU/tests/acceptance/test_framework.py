from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from machine.acceptance.evidence import (
    EXPECTED_ACCEPTANCE_IDS,
    ORACLE_SCHEMA,
    PROJECT_ROOT,
    RECORD_SCHEMA,
    SUMMARY_PATH,
    AcceptanceEvidenceError,
    ContractBinding,
    _assert_test_entry,
    evaluate_all,
    validate_bundle,
)


def _load(relative: object) -> dict[str, object]:
    value = json.loads((PROJECT_ROOT / str(relative)).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _valid_local_observation() -> dict[str, object]:
    return {
        "schema_version": "moomooau.oracle-observation.v1",
        "oracle_id": "AC-001-SYNTHETIC",
        "acceptance_id": "AC-001",
        "environment": "LOCAL_SYNTHETIC",
        "observed_at_utc": "2026-07-22T05:00:00Z",
        "source_commit": "0" * 40,
        "contract_binding": {
            "acceptance_contract_sha256": "0" * 64,
            "environment_sha256": "0" * 64,
            "input_sha256": "0" * 64,
            "oracle_sha256": "0" * 64,
            "threshold_sha256": "0" * 64,
            "pass_gate_sha256": "0" * 64,
        },
        "status": "PASS",
        "threshold_checks": [
            {"id": "zero_collateral", "expected": "0", "observed": "0", "status": "PASS"}
        ],
        "evidence_refs": [{"path": "evidence/example.json", "sha256": "0" * 64}],
        "attestation": {"type": "LOCAL_COMMAND", "run_locator_sha256": None},
    }


def test_acceptance_bundle_is_exact_valid_and_truthfully_blocked() -> None:
    assert validate_bundle(PROJECT_ROOT) == ()
    results = evaluate_all(PROJECT_ROOT)
    assert tuple(item.acceptance_id for item in results) == EXPECTED_ACCEPTANCE_IDS
    assert all(item.valid for item in results)
    assert all(not item.passed for item in results)
    assert all(item.acceptance_status == "BLOCKED" for item in results)
    assert all("FINAL_ORACLE_NOT_EXECUTED" in item.blockers for item in results)

    summary = _load(SUMMARY_PATH)
    assert summary["status"] == "BLOCKED"
    assert summary["final_acceptances_passed"] == 0
    assert summary["final_acceptances_blocked"] == 34
    assert summary["blocked_acceptance_ids"] == list(EXPECTED_ACCEPTANCE_IDS)


def test_structural_cli_passes_while_final_gate_fails_closed() -> None:
    command = [sys.executable, "machine/acceptance/validate_acceptance.py"]
    structural = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert structural.returncode == 0
    structural_value = json.loads(structural.stdout)
    assert structural_value["status"] == "BLOCKED"
    assert structural_value["structurally_valid"] == 34
    assert structural_value["passed"] == 0

    final = subprocess.run(
        [*command, "--require-pass"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert final.returncode == 1
    assert json.loads(final.stdout)["blocked"] == 34


def test_builder_check_is_byte_deterministic() -> None:
    summary = _load(SUMMARY_PATH)
    completed = subprocess.run(
        [
            sys.executable,
            "machine/acceptance/build_evidence.py",
            "--observed-at-utc",
            str(summary["observed_at_utc"]),
            "--remediation-base-commit",
            str(summary["remediation_base_commit"]),
            "--check",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["mismatches"] == []


def test_test_entry_gate_rejects_a_decorator(tmp_path: Path) -> None:
    relative = Path("tests/acceptance/test_ac_001.py")
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(
        "from _assertions import assert_final_acceptance\n\n"
        "@staticmethod\n"
        "def test_ac_001_pass_gate() -> None:\n"
        '    assert_final_acceptance("AC-001")\n',
        encoding="utf-8",
    )
    binding = ContractBinding(
        acceptance={"id": "AC-001"},
        requirement={},
        traceability={},
        test_path=relative,
        evidence_path=Path("evidence/acceptance/AC-001-example.json"),
    )
    with pytest.raises(AcceptanceEvidenceError, match="does not enforce its pass gate"):
        _assert_test_entry(tmp_path, binding)


def test_record_schema_rejects_a_fabricated_pass() -> None:
    summary = _load(SUMMARY_PATH)
    blocked_ids = summary["blocked_acceptance_ids"]
    assert isinstance(blocked_ids, list) and blocked_ids
    first_path = str(blocked_ids[0])
    record_path = next((PROJECT_ROOT / "evidence/acceptance").glob(f"{first_path}-*.json"))
    record = _load(record_path.relative_to(PROJECT_ROOT))
    record["acceptance_status"] = "PASS"
    record["pass_gate"] = True
    record["blockers"] = []
    schema = _load(RECORD_SCHEMA)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record))
    assert errors
    assert any("PASS" in error.message for error in errors)


def test_oracle_schema_rejects_pass_with_a_failed_threshold() -> None:
    schema = _load(ORACLE_SCHEMA)
    observation = _valid_local_observation()
    observation["threshold_checks"] = [
        {"id": "zero_collateral", "expected": "0", "observed": "1", "status": "FAIL"}
    ]
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(observation)
    )
    assert errors
    assert any("PASS" in error.message for error in errors)


def test_oracle_schema_requires_a_protected_run_locator() -> None:
    schema = _load(ORACLE_SCHEMA)
    observation = _valid_local_observation()
    observation["environment"] = "GITHUB_ACTIONS_PROTECTED"
    observation["attestation"] = {
        "type": "GITHUB_ACTIONS_PROTECTED",
        "run_locator_sha256": None,
    }
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(observation)
    )
    assert errors
    assert any("run_locator_sha256" in tuple(error.absolute_path) for error in errors)
