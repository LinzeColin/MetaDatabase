from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_blue_release_repair import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionBlueReleaseRepairError,
    build_receipt,
    evaluate_preflight,
    evaluate_repair,
    source_bundle_paths,
    validate_completion_facts,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "current_production_blue_release_repair_contract.json"
EXECUTOR_PATH = RUNTIME / "install_current_production_blue_release_repair.sh"
BOOTSTRAP_PATH = RUNTIME / "current_production_blue_release_acceptance_init.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _preflight(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_PREFLIGHT",
        "observed_on": "2026-08-12",
        "current_target": "BLUE_SHADOW_RELEASE",
        "shadow_blue_project_present": True,
        "core_unit": {"load_state": "not-found", "active_state": "inactive"},
        "existing_files": {"compose_file_kind": "regular"},
        "missing_before_repair": {
            "config_schema_file_kind": "missing",
            "rebuild_file_kind": "missing",
            "abd_acceptance_directory_kind": "missing",
        },
        "host_python_major_minor": "3.12",
        "host_python_jsonschema_import": "present",
    }
    values.update(overrides)
    return values


def _completion(contract: dict[str, object], **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_COMPLETION",
        "observed_on": "2026-08-12",
        "current_target": "BLUE_SHADOW_RELEASE",
        "shadow_blue_project_present": True,
        "core_unit": {"load_state": "not-found", "active_state": "inactive"},
        "compose_file_kind": "regular",
        "installed_infra_file_kinds": {path: "regular" for path in source_bundle_paths(contract)},
        "installed_acceptance_package": {
            "python_file_count": 5,
            "nonpython_file_count": 0,
            "all_python_regular": True,
        },
        "python_import": "PASS",
    }
    values.update(overrides)
    return values


def test_contract_preserves_blue_shadow_and_no_activation_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["current_symlink_changed"] is False
    assert boundary["shadow_container_changed"] is False
    assert boundary["unit_created_enabled_or_started"] is False
    assert boundary["runtime_secret_contents_read"] is False


def test_bundle_requires_exact_infrastructure_micro_package() -> None:
    assert source_bundle_paths(_contract()) == [
        "infra/config.schema.json",
        "infra/rebuild.sh",
    ]
    profile = _contract()["expected"]["source_bundle_profile"]
    assert profile == {
        "infra_paths": source_bundle_paths(_contract()),
        "bootstrap_initializer_source": "runtime/current_production_blue_release_acceptance_init.py",
        "acceptance_module_paths": [
            "abd_acceptance/infrastructure_iac.py",
            "abd_acceptance/canonical_facts.py",
            "abd_acceptance/legacy_receipt_compatibility.py",
            "abd_acceptance/stage3_delivery.py",
        ],
        "acceptance_package_python_file_count": 5,
        "acceptance_package_nonpython_file_count": 0,
    }


def test_bootstrap_initializer_cannot_import_the_full_acceptance_aggregator() -> None:
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert "from ." not in source
    assert "importlib" not in source
    assert "scheduler" not in source


def test_preflight_authorizes_repair_but_never_core_start() -> None:
    result = evaluate_preflight(_contract(), _preflight())

    assert result["status"] == PASS_STATUS
    assert result["repair_authorized"] is True
    assert result["core_start_authorized"] is False


@pytest.mark.parametrize(
    ("key", "value", "failure_code"),
    [
        ("current_target", "OTHER_MANAGED_RELEASE", "CURRENT_TARGET_IS_BLUE_SHADOW_RELEASE"),
        ("shadow_blue_project_present", False, "BLUE_SHADOW_PROJECT_PRESENT"),
        ("host_python_major_minor", "unknown", "HOST_PYTHON_312"),
        ("host_python_jsonschema_import", "missing", "HOST_JSONSCHEMA_IMPORT_PRESENT"),
    ],
)
def test_preflight_fails_closed_on_runtime_drift(key: str, value: object, failure_code: str) -> None:
    result = evaluate_preflight(_contract(), _preflight(**{key: value}))

    assert result["status"] == FAIL_STATUS
    assert result["repair_authorized"] is False
    assert result["core_start_authorized"] is False
    assert failure_code in result["failure_codes"]


def test_preflight_fails_closed_if_target_is_not_cleanly_missing() -> None:
    facts = _preflight()
    facts["missing_before_repair"] = {
        "config_schema_file_kind": "regular",
        "rebuild_file_kind": "missing",
        "abd_acceptance_directory_kind": "missing",
    }

    result = evaluate_preflight(_contract(), facts)

    assert result["status"] == FAIL_STATUS
    assert result["failure_codes"] == ["REPAIR_TARGET_FILES_ALL_MISSING"]


def test_completion_passes_with_all_added_files_and_preserved_shadow() -> None:
    contract = _contract()
    result = evaluate_repair(contract, _preflight(), _completion(contract))

    assert result["status"] == PASS_STATUS
    assert result["release_repaired"] is True
    assert result["core_start_authorized"] is False


def test_completion_fails_closed_for_one_missing_bundle_file() -> None:
    contract = _contract()
    completion = _completion(contract)
    installed = completion["installed_infra_file_kinds"]
    assert isinstance(installed, dict)
    installed["infra/rebuild.sh"] = "missing"

    result = evaluate_repair(contract, _preflight(), completion)

    assert result["status"] == FAIL_STATUS
    assert result["release_repaired"] is False
    assert result["failure_codes"] == ["SOURCE_BUNDLE_FILES_ALL_REGULAR"]


def test_completion_fails_closed_for_incomplete_acceptance_package() -> None:
    contract = _contract()
    completion = _completion(contract)
    package = completion["installed_acceptance_package"]
    assert isinstance(package, dict)
    package["python_file_count"] = 4

    result = evaluate_repair(contract, _preflight(), completion)

    assert result["status"] == FAIL_STATUS
    assert result["failure_codes"] == ["FULL_ACCEPTANCE_PACKAGE_PRESENT"]


def test_completion_fails_closed_if_core_becomes_active() -> None:
    contract = _contract()
    completion = _completion(contract, core_unit={"load_state": "loaded", "active_state": "active"})

    result = evaluate_repair(contract, _preflight(), completion)

    assert result["status"] == FAIL_STATUS
    assert "CORE_UNIT_REMAINS_NOT_FOUND_AND_INACTIVE" in result["failure_codes"]


def test_completion_shape_rejects_unexpected_path() -> None:
    contract = _contract()
    completion = _completion(contract)
    installed = completion["installed_infra_file_kinds"]
    assert isinstance(installed, dict)
    installed["unexpected.py"] = "regular"

    with pytest.raises(CurrentProductionBlueReleaseRepairError, match="infra bundle state"):
        validate_completion_facts(contract, completion)


def test_receipt_redacts_source_paths_and_never_authorizes_core_start() -> None:
    contract = _contract()
    receipt = build_receipt(contract, _preflight(), _completion(contract))
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["core_start_authorized"] is False
    assert all(set(check) == {"id", "passed"} for check in receipt["checks"])
    assert "installed_infra_file_kinds" not in serialized
    assert "installed_acceptance_package" not in serialized
    assert "infra/rebuild.sh" not in serialized


def test_contract_cannot_be_relaxed_to_start_a_unit() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["unit_created_enabled_or_started"] = True

    with pytest.raises(CurrentProductionBlueReleaseRepairError, match="source boundary"):
        validate_contract(contract)


def test_executor_has_no_core_start_connector_or_cloudflare_action() -> None:
    source = EXECUTOR_PATH.read_text(encoding="utf-8")

    assert "COPYFILE_DISABLE=1 tar --format ustar" in source
    assert 'rm -f -- "$stage/infra/config.schema.json" "$stage/infra/rebuild.sh"' in source

    for forbidden in (
        "systemctl start",
        "systemctl enable",
        "docker compose",
        "docker run",
        "cloudflared",
        "curl ",
        "wget ",
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in source
