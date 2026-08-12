from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_readme_protected_source_pointer_resolver import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionReadmeProtectedSourcePointerResolverError,
    build_receipt,
    evaluate_resolver,
    resolve_readme_protected_source_pointer,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_readme_protected_source_pointer_resolver_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_readme_protected_source_pointer_resolver.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER",
        "observed_on": "2026-08-12",
        "root_readme_state": "AVAILABLE_READ_ONLY",
        "pointer_declaration_state": "RESOLVED_IN_MEMORY",
        "protected_metadata_source_state": "RESOLVED_IN_MEMORY",
        "pointer_target_source_ready": True,
        "candidate_schema_keys_read_in_memory_only": True,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "readme_text_pointer_or_protected_path_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _write_layout(tmp_path: Path, readme_text: str, payload: dict[str, object] | None = None, mode: int = 0o600) -> tuple[Path, Path]:
    readme = tmp_path / "README.md"
    protected = tmp_path / "_protected"
    protected.mkdir(mode=0o700)
    readme.write_text(readme_text, encoding="utf-8")
    if payload is not None:
        target = protected / "abd"
        target.mkdir(mode=0o700)
        source = target / "current-production-target.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        source.chmod(mode)
    return readme, protected


def test_contract_preserves_exact_readme_pointer_zero_outbound_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["pointer_encoding"] == "SINGLE_INLINE_CODE_RELATIVE_PROTECTED_JSON_PATH"
    assert expected["maximum_declared_pointers"] == 1
    assert expected["provider_api_requests"] == 0
    assert expected["ssh_connections_attempted"] == 0
    assert expected["github_api_requests"] == 0
    assert boundary["protected_source_opened_only_after_exact_readme_pointer"] is True
    assert boundary["candidate_json_values_parsed_or_persisted"] is False


def test_valid_readme_declared_source_is_ready_only_for_a_separate_phase() -> None:
    result = evaluate_resolver(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["readme_declared_target_source_located"] is True
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_no_declared_pointer_is_a_complete_zero_outbound_result() -> None:
    result = evaluate_resolver(_contract(), _facts(
        pointer_declaration_state="NOT_DECLARED_REDACTED",
        protected_metadata_source_state="NOT_ATTEMPTED",
        pointer_target_source_ready=False,
        candidate_schema_keys_read_in_memory_only=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["readme_declared_target_source_located"] is False
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_resolver_opens_exactly_one_readme_declared_restrictive_nonsecret_source(tmp_path: Path) -> None:
    readme, protected = _write_layout(
        tmp_path,
        "Pointer: `_protected/abd/current-production-target.json`\n",
        {
            "schema_version": "1.0.0",
            "provider": "provider-alias",
            "environment": "production",
            "target_alias": "current-service",
        },
    )

    facts = resolve_readme_protected_source_pointer(readme, protected, observed_on="2026-08-12")

    assert facts["root_readme_state"] == "AVAILABLE_READ_ONLY"
    assert facts["pointer_declaration_state"] == "RESOLVED_IN_MEMORY"
    assert facts["protected_metadata_source_state"] == "RESOLVED_IN_MEMORY"
    assert facts["pointer_target_source_ready"] is True
    assert facts["candidate_schema_keys_read_in_memory_only"] is True
    assert facts["readme_text_pointer_or_protected_path_emitted_or_persisted"] is False


def test_resolver_does_not_open_protected_root_when_readme_declares_no_pointer(tmp_path: Path) -> None:
    readme, protected = _write_layout(tmp_path, "No pointer is declared here.\n")

    facts = resolve_readme_protected_source_pointer(readme, protected, observed_on="2026-08-12")

    assert facts["pointer_declaration_state"] == "NOT_DECLARED_REDACTED"
    assert facts["protected_metadata_source_state"] == "NOT_ATTEMPTED"
    assert facts["candidate_schema_keys_read_in_memory_only"] is False


def test_resolver_reports_declared_pointer_source_unavailable_without_expanding_scope(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    protected = tmp_path / "_protected"
    readme.write_text("`_protected/abd/current-production-target.json`\n", encoding="utf-8")

    facts = resolve_readme_protected_source_pointer(readme, protected, observed_on="2026-08-12")

    assert facts["pointer_declaration_state"] == "RESOLVED_IN_MEMORY"
    assert facts["protected_metadata_source_state"] == "UNAVAILABLE_REDACTED"
    assert facts["pointer_target_source_ready"] is False
    assert facts["candidate_schema_keys_read_in_memory_only"] is False


def test_resolver_rejects_multiple_declared_pointers_without_opening_any_source(tmp_path: Path) -> None:
    readme, protected = _write_layout(
        tmp_path,
        "`_protected/abd/current-production-target.json` and `_protected/abd/production-target.json`\n",
    )

    facts = resolve_readme_protected_source_pointer(readme, protected, observed_on="2026-08-12")

    assert facts["pointer_declaration_state"] == "AMBIGUOUS_REDACTED"
    assert facts["protected_metadata_source_state"] == "NOT_ATTEMPTED"
    assert facts["candidate_schema_keys_read_in_memory_only"] is False


def test_resolver_rejects_nonsecret_boundary_violation_in_declared_pointer(tmp_path: Path) -> None:
    readme, protected = _write_layout(tmp_path, "`_protected/abd/current-production-target-secret.json`\n")

    facts = resolve_readme_protected_source_pointer(readme, protected, observed_on="2026-08-12")

    assert facts["pointer_declaration_state"] == "INVALID_DECLARATION_REDACTED"
    assert facts["protected_metadata_source_state"] == "NOT_ATTEMPTED"


def test_resolver_rejects_group_or_world_readable_declared_source(tmp_path: Path) -> None:
    readme, protected = _write_layout(
        tmp_path,
        "`_protected/abd/current-production-target.json`\n",
        {
            "schema_version": "1.0.0",
            "provider": "provider-alias",
            "target_alias": "current-service",
        },
        mode=0o644,
    )

    facts = resolve_readme_protected_source_pointer(readme, protected, observed_on="2026-08-12")

    assert facts["pointer_declaration_state"] == "RESOLVED_IN_MEMORY"
    assert facts["protected_metadata_source_state"] == "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    assert facts["pointer_target_source_ready"] is False


def test_resolver_rejects_schema_with_nonmetadata_key_without_retaining_it(tmp_path: Path) -> None:
    readme, protected = _write_layout(
        tmp_path,
        "`_protected/abd/current-production-target.json`\n",
        {
            "schema_version": "1.0.0",
            "provider": "provider-alias",
            "target_alias": "current-service",
            "application_secret": "synthetic-only",
        },
    )

    facts = resolve_readme_protected_source_pointer(readme, protected, observed_on="2026-08-12")

    assert facts["pointer_declaration_state"] == "RESOLVED_IN_MEMORY"
    assert facts["protected_metadata_source_state"] == "SCHEMA_INCOMPLETE_REDACTED"
    assert "application_secret" not in json.dumps(facts, sort_keys=True)


def test_facts_reject_pointer_or_path_leakage() -> None:
    facts = _facts()
    facts["pointer"] = "not retained"

    with pytest.raises(CurrentProductionReadmeProtectedSourcePointerResolverError, match="field set"):
        validate_facts(facts)


def test_facts_reject_any_outbound_attempt() -> None:
    facts = _facts(github_api_requests=1)

    with pytest.raises(CurrentProductionReadmeProtectedSourcePointerResolverError, match="outbound operation count"):
        validate_facts(facts)


def test_receipt_redacts_readme_pointer_and_source_details() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["core_start_authorized"] is False
    assert '"root_readme_state":' not in serialized
    assert '"pointer_declaration_state":' not in serialized
    assert '"candidate_schema_keys_read_in_memory_only":' not in serialized


def test_contract_cannot_relax_zero_outbound_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["ssh_connections_attempted"] = 1

    with pytest.raises(CurrentProductionReadmeProtectedSourcePointerResolverError, match="resolver expectations"):
        validate_contract(contract)


def test_runner_has_no_network_transport_or_host_mutation_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "--readme" in source
    assert "--protected-root" in source
    assert "current_production_readme_protected_source_pointer_resolver.py" in source
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

    with pytest.raises(CurrentProductionReadmeProtectedSourcePointerResolverError):
        evaluate_resolver(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER"
