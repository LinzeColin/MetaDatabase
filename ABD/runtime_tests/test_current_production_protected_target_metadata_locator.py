from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_protected_target_metadata_locator as locator
from current_production_protected_target_metadata_locator import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionProtectedTargetMetadataLocatorError,
    build_receipt,
    evaluate_locator,
    locate_protected_target_metadata,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_protected_target_metadata_locator_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_protected_target_metadata_locator.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR",
        "observed_on": "2026-08-12",
        "protected_root_state": "AVAILABLE_READ_ONLY",
        "bounded_scan_state": "COMPLETED",
        "metadata_source_state": "RESOLVED_IN_MEMORY",
        "metadata_source_ready": True,
        "candidate_schema_keys_read_in_memory_only": True,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "protected_path_or_filename_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _write_candidate(root: Path, name: str, payload: dict[str, object], mode: int = 0o600) -> Path:
    root.mkdir(mode=0o700)
    candidate = root / name
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    candidate.chmod(mode)
    return candidate


def test_contract_preserves_bounded_key_only_and_zero_outbound_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["allowed_candidate_suffixes"] == [".json"]
    assert expected["maximum_tree_depth"] == 8
    assert expected["maximum_tree_entries"] == 4096
    assert expected["maximum_candidate_files_opened"] == 8
    assert expected["provider_api_requests"] == 0
    assert expected["ssh_connections_attempted"] == 0
    assert expected["github_api_requests"] == 0
    assert boundary["candidate_json_values_parsed_or_persisted"] is False
    assert boundary["credential_material_read_emitted_or_persisted"] is False
    assert boundary["target_value_read_emitted_or_persisted"] is False


def test_valid_metadata_source_is_ready_only_for_a_separate_compatibility_phase() -> None:
    result = evaluate_locator(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["protected_target_metadata_located"] is True
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False
    assert result["decision"] == "CURRENT_PRODUCTION_TARGET_METADATA_READY_FOR_SEPARATE_COMBINED_SOURCE_COMPATIBILITY_PHASE"


def test_no_source_is_a_complete_zero_outbound_locator() -> None:
    result = evaluate_locator(_contract(), _facts(
        metadata_source_state="NO_MANAGED_NONSECRET_SOURCE_REDACTED",
        metadata_source_ready=False,
        candidate_schema_keys_read_in_memory_only=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["protected_target_metadata_located"] is False
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_unavailable_root_is_redacted_and_fails_closed() -> None:
    facts = _facts(
        protected_root_state="UNAVAILABLE_REDACTED",
        bounded_scan_state="NOT_ATTEMPTED",
        metadata_source_state="UNAVAILABLE_REDACTED",
        metadata_source_ready=False,
        candidate_schema_keys_read_in_memory_only=False,
    )

    result = evaluate_locator(_contract(), facts)

    assert result["status"] == PASS_STATUS
    assert result["protected_target_metadata_located"] is False


def test_locator_accepts_restrictive_nonsecret_candidate_without_retaining_values(tmp_path: Path) -> None:
    root = tmp_path / "_protected"
    _write_candidate(root, "abd-current-production-target.json", {
        "schema_version": "1.0.0",
        "provider": "provider-alias",
        "environment": "production",
        "target_alias": "current-service",
    })

    facts = locate_protected_target_metadata(root, observed_on="2026-08-12")

    assert facts["protected_root_state"] == "AVAILABLE_READ_ONLY"
    assert facts["bounded_scan_state"] == "COMPLETED"
    assert facts["metadata_source_state"] == "RESOLVED_IN_MEMORY"
    assert facts["metadata_source_ready"] is True
    assert facts["candidate_schema_keys_read_in_memory_only"] is True
    assert facts["candidate_json_values_parsed_or_persisted"] is False
    assert facts["protected_path_or_filename_emitted_or_persisted"] is False


def test_locator_rejects_candidate_with_credential_key_without_outputting_it(tmp_path: Path) -> None:
    root = tmp_path / "_protected"
    _write_candidate(root, "abd-current-production-target.json", {
        "schema_version": "1.0.0",
        "provider": "provider-alias",
        "target_alias": "current-service",
        "application_secret": "synthetic-only",
    })

    facts = locate_protected_target_metadata(root, observed_on="2026-08-12")

    assert facts["metadata_source_state"] == "SCHEMA_INCOMPLETE_REDACTED"
    assert facts["metadata_source_ready"] is False
    assert "application_secret" not in json.dumps(facts, sort_keys=True)


def test_locator_rejects_group_or_world_readable_candidate(tmp_path: Path) -> None:
    root = tmp_path / "_protected"
    _write_candidate(root, "abd-current-production-target.json", {
        "schema_version": "1.0.0",
        "provider": "provider-alias",
        "target_alias": "current-service",
    }, mode=0o644)

    facts = locate_protected_target_metadata(root, observed_on="2026-08-12")

    assert facts["metadata_source_state"] == "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    assert facts["metadata_source_ready"] is False
    assert facts["candidate_schema_keys_read_in_memory_only"] is False


def test_locator_redacts_unavailable_root(tmp_path: Path) -> None:
    facts = locate_protected_target_metadata(tmp_path / "absent", observed_on="2026-08-12")

    assert facts["protected_root_state"] == "UNAVAILABLE_REDACTED"
    assert facts["bounded_scan_state"] == "NOT_ATTEMPTED"
    assert facts["metadata_source_state"] == "UNAVAILABLE_REDACTED"
    assert facts["metadata_source_ready"] is False


def test_locator_fails_closed_when_bounded_scan_is_truncated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "_protected"
    root.mkdir(mode=0o700)
    (root / "plain-a.txt").write_text("a", encoding="utf-8")
    (root / "plain-b.txt").write_text("b", encoding="utf-8")
    monkeypatch.setattr(locator, "MAX_TREE_ENTRIES", 1)

    facts = locate_protected_target_metadata(root, observed_on="2026-08-12")

    assert facts["bounded_scan_state"] == "TRUNCATED_REDACTED"
    assert facts["metadata_source_state"] == "SCAN_LIMIT_REACHED_REDACTED"
    assert facts["metadata_source_ready"] is False


def test_facts_reject_any_path_or_target_leakage() -> None:
    facts = _facts()
    facts["candidate_path"] = "not retained"

    with pytest.raises(CurrentProductionProtectedTargetMetadataLocatorError, match="field set"):
        validate_facts(facts)


def test_facts_reject_any_outbound_attempt() -> None:
    facts = _facts(provider_api_requests=1)

    with pytest.raises(CurrentProductionProtectedTargetMetadataLocatorError, match="outbound operation count"):
        validate_facts(facts)


def test_receipt_redacts_root_scan_and_candidate_details() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["core_start_authorized"] is False
    assert '"protected_root_state":' not in serialized
    assert '"bounded_scan_state":' not in serialized
    assert '"candidate_schema_keys_read_in_memory_only":' not in serialized


def test_contract_cannot_relax_outbound_or_value_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["provider_api_requests"] = 1

    with pytest.raises(CurrentProductionProtectedTargetMetadataLocatorError, match="locator expectations"):
        validate_contract(contract)


def test_runner_has_no_network_transport_or_host_mutation_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "--protected-root" in source
    assert "current_production_protected_target_metadata_locator.py" in source
    for forbidden in (
        "curl ",
        "wget ",
        "ssh ",
        "gh ",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in source


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionProtectedTargetMetadataLocatorError):
        evaluate_locator(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR"
