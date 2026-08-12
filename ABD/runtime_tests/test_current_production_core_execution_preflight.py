from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_core_execution_preflight import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionCoreExecutionPreflightError,
    build_receipt,
    evaluate_preflight,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_core_execution_preflight_contract.json"
VALIDATOR_PATH = RUNTIME / "current_production_core_execution_preflight.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**runtime_overrides: object) -> dict[str, object]:
    runtime_prerequisites: dict[str, object] = {
        "config_file_kind": "regular",
        "runtime_env_file_kind": "regular",
        "runtime_secret_file_kind": "regular",
        "current_release_link_kind": "symlink",
        "current_release_target_managed": True,
        "current_compose_file_kind": "regular",
        "current_rebuild_file_kind": "regular",
        "core_capacity_dropin_file_kind": "regular",
        "candidate_image_present": True,
    }
    runtime_prerequisites.update(runtime_overrides)
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT",
        "observed_on": "2026-08-12",
        "privileged_metadata_read": True,
        "runtime_prerequisites": runtime_prerequisites,
        "core_unit": {"load_state": "not-found", "active_state": "inactive"},
        "connector_unit": {"load_state": "not-found", "active_state": "inactive"},
    }


def test_contract_preserves_read_only_secret_and_activation_boundaries() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["runtime_secret_contents_read"] is False
    assert boundary["unit_created_enabled_or_started"] is False
    assert boundary["host_runtime_or_configuration_changed"] is False
    assert boundary["real_time_soak_waited"] is False


def test_complete_synthetic_input_is_ready_but_cannot_authorize_execution() -> None:
    result = evaluate_preflight(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["input_ready"] is True
    assert result["execution_authorized"] is False
    assert result["failure_codes"] == []


def test_current_missing_rebuild_file_fails_closed_without_authorizing_execution() -> None:
    result = evaluate_preflight(_contract(), _facts(current_rebuild_file_kind="missing"))

    assert result["status"] == FAIL_STATUS
    assert result["input_ready"] is False
    assert result["execution_authorized"] is False
    assert result["failure_codes"] == ["CURRENT_RELEASE_REBUILD_FILE_REGULAR"]


@pytest.mark.parametrize(
    ("key", "value", "failure_code"),
    [
        ("config_file_kind", "missing", "CONFIG_FILE_REGULAR"),
        ("runtime_env_file_kind", "missing", "RUNTIME_ENV_FILE_REGULAR"),
        ("runtime_secret_file_kind", "missing", "RUNTIME_SECRET_FILE_PRESENT"),
        ("current_release_link_kind", "regular", "CURRENT_RELEASE_LINK_MANAGED"),
        ("current_release_target_managed", False, "CURRENT_RELEASE_LINK_MANAGED"),
        ("current_compose_file_kind", "missing", "CURRENT_RELEASE_COMPOSE_FILE_REGULAR"),
        ("core_capacity_dropin_file_kind", "missing", "CORE_CAPACITY_DROPIN_FILE_REGULAR"),
        ("candidate_image_present", False, "CURRENT_CANDIDATE_IMAGE_PRESENT"),
    ],
)
def test_each_runtime_prerequisite_fails_closed(key: str, value: object, failure_code: str) -> None:
    result = evaluate_preflight(_contract(), _facts(**{key: value}))

    assert result["status"] == FAIL_STATUS
    assert result["input_ready"] is False
    assert result["execution_authorized"] is False
    assert failure_code in result["failure_codes"]


def test_unit_drift_fails_closed() -> None:
    facts = _facts()
    facts["core_unit"] = {"load_state": "loaded", "active_state": "active"}
    facts["connector_unit"] = {"load_state": "loaded", "active_state": "active"}

    result = evaluate_preflight(_contract(), facts)

    assert result["status"] == FAIL_STATUS
    assert result["failure_codes"] == ["CORE_UNIT_NOT_FOUND_AND_INACTIVE", "CONNECTOR_UNIT_NOT_FOUND_AND_INACTIVE"]


def test_malformed_fact_set_is_rejected() -> None:
    facts = _facts()
    facts["unexpected"] = True

    with pytest.raises(CurrentProductionCoreExecutionPreflightError, match="facts field set"):
        validate_facts(facts)


def test_contract_cannot_be_relaxed_to_authorize_a_start() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["unit_created_enabled_or_started"] = True

    with pytest.raises(CurrentProductionCoreExecutionPreflightError, match="source boundary"):
        validate_contract(contract)


def test_receipt_redacts_all_runtime_values_and_keeps_execution_unauthorized() -> None:
    facts = _facts(current_rebuild_file_kind="missing")
    receipt = build_receipt(_contract(), facts)
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == FAIL_STATUS
    assert receipt["execution_authorized"] is False
    assert all(set(check) == {"id", "passed"} for check in receipt["checks"])
    assert "runtime_prerequisites" not in serialized
    assert "current_rebuild_file_kind" not in serialized


def test_source_has_no_network_or_runtime_mutation_capability() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "import subprocess",
        "import requests",
        "import urllib",
        "time.sleep(",
        "docker load",
        "docker tag",
        "systemctl start",
        "systemctl enable",
        "cloudflared tunnel",
    ):
        assert forbidden not in source
