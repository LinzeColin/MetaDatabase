from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_core_config_semantic_preflight import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionCoreConfigSemanticPreflightError,
    build_receipt,
    evaluate_preflight,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_core_config_semantic_preflight_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_core_config_semantic_preflight.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    frozen_check: dict[str, object] = {
        "invoked": True,
        "status": "PASS",
        "activation_gate": "BLOCKED_RUNTIME_PREREQUISITES_NOT_VERIFIED",
        "secret_values_read": False,
        "error_category": "NONE",
    }
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT",
        "observed_on": "2026-08-12",
        "current_target": "BLUE_SHADOW_RELEASE",
        "config_file_kind": "regular",
        "rebuild_file_kind": "regular",
        "frozen_check": frozen_check,
    }
    values.update(overrides)
    return values


def test_contract_preserves_read_only_redaction_and_no_core_start_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["config_contents_emitted_or_persisted"] is False
    assert boundary["runtime_secret_contents_read"] is False
    assert boundary["unit_created_enabled_or_started"] is False
    assert boundary["real_time_soak_waited"] is False


@pytest.mark.parametrize("activation_gate", ["BLOCKED_RUNTIME_PREREQUISITES_NOT_VERIFIED", "READY_FOR_EXPLICIT_P03_ACTIVATION"])
def test_valid_frozen_check_is_semantically_valid_but_never_authorizes_core_start(activation_gate: str) -> None:
    result = evaluate_preflight(_contract(), _facts(frozen_check={
        "invoked": True,
        "status": "PASS",
        "activation_gate": activation_gate,
        "secret_values_read": False,
        "error_category": "NONE",
    }))

    assert result["status"] == PASS_STATUS
    assert result["config_semantic_valid"] is True
    assert result["core_start_authorized"] is False
    assert result["activation_gate"] == activation_gate


@pytest.mark.parametrize(
    ("key", "value", "failure_code"),
    [
        ("current_target", "OTHER_MANAGED_RELEASE", "CURRENT_TARGET_IS_BLUE_SHADOW_RELEASE"),
        ("config_file_kind", "missing", "CONFIG_FILE_REGULAR"),
        ("rebuild_file_kind", "missing", "CURRENT_RELEASE_REBUILD_FILE_REGULAR"),
    ],
)
def test_metadata_drift_fails_closed(key: str, value: object, failure_code: str) -> None:
    result = evaluate_preflight(_contract(), _facts(**{key: value}))

    assert result["status"] == FAIL_STATUS
    assert result["config_semantic_valid"] is False
    assert result["core_start_authorized"] is False
    assert failure_code in result["failure_codes"]


@pytest.mark.parametrize(
    "frozen_check",
    [
        {
            "invoked": True,
            "status": "FAIL",
            "activation_gate": "NOT_EMITTED",
            "secret_values_read": "NOT_EMITTED",
            "error_category": "FROZEN_CHECK_FAILED_REDACTED",
        },
        {
            "invoked": False,
            "status": "NOT_RUN",
            "activation_gate": "NOT_EMITTED",
            "secret_values_read": "NOT_EMITTED",
            "error_category": "FROZEN_CHECK_TRANSPORT_UNAVAILABLE_REDACTED",
        },
    ],
)
def test_safe_frozen_check_failure_stays_redacted_and_fails_closed(frozen_check: dict[str, object]) -> None:
    result = evaluate_preflight(_contract(), _facts(frozen_check=frozen_check))

    assert result["status"] == FAIL_STATUS
    assert result["config_semantic_valid"] is False
    assert result["activation_gate"] == "UNKNOWN"
    assert "FROZEN_CHECK_PASSED" in result["failure_codes"]


def test_facts_reject_raw_error_or_extra_output_field() -> None:
    facts = _facts()
    frozen_check = facts["frozen_check"]
    assert isinstance(frozen_check, dict)
    frozen_check["errors"] = ["not retained"]

    with pytest.raises(CurrentProductionCoreConfigSemanticPreflightError, match="field set"):
        validate_facts(facts)


def test_receipt_only_contains_the_redacted_gate_and_authorization_is_false() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["config_semantic_valid"] is True
    assert receipt["core_start_authorized"] is False
    assert receipt["activation_gate"] == "BLOCKED_RUNTIME_PREREQUISITES_NOT_VERIFIED"
    assert '"frozen_check":' not in serialized
    assert '"config_file_kind":' not in serialized
    assert '"rebuild_file_kind":' not in serialized


def test_contract_cannot_relax_config_output_or_core_start_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["config_contents_emitted_or_persisted"] = True

    with pytest.raises(CurrentProductionCoreConfigSemanticPreflightError, match="source boundary"):
        validate_contract(contract)


def test_runner_has_no_runtime_mutation_or_raw_error_forwarding() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "PYTHONDONTWRITEBYTECODE=1" in source
    assert '"check", "--config", CONFIG' in source
    assert "FROZEN_CHECK_OUTPUT_MALFORMED_REDACTED" in source
    assert "completed.stderr" not in source
    for forbidden in (
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
        "curl ",
        "wget ",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in source
