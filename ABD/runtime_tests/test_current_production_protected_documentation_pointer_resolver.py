from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_protected_documentation_pointer_resolver as resolver
from current_production_protected_documentation_pointer_resolver import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionProtectedDocumentationPointerResolverError,
    build_receipt,
    evaluate_resolver,
    resolve_protected_documentation_pointer,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_protected_documentation_pointer_resolver_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_protected_documentation_pointer_resolver.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER",
        "observed_on": "2026-08-12",
        "protected_root_state": "AVAILABLE_READ_ONLY",
        "document_scan_state": "COMPLETED",
        "documentation_pointer_state": "RESOLVED_IN_MEMORY",
        "protected_metadata_source_state": "RESOLVED_IN_MEMORY",
        "documentation_target_source_ready": True,
        "document_text_read_in_memory_only": True,
        "candidate_schema_keys_read_in_memory_only": True,
        "document_text_pointer_or_protected_path_emitted_or_persisted": False,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "_protected"
    root.mkdir(mode=0o700)
    return root


def _write_document(root: Path, name: str, text: str, mode: int = 0o600) -> Path:
    document = root / name
    document.write_text(text, encoding="utf-8")
    document.chmod(mode)
    return document


def _write_target(root: Path, payload: dict[str, object], mode: int = 0o600) -> Path:
    directory = root / "abd"
    directory.mkdir(mode=0o700)
    target = directory / "current-production-target.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    target.chmod(mode)
    return target


def test_contract_preserves_bounded_document_set_and_zero_outbound_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["allowed_document_name_tokens"] == ["architecture", "deployment", "handoff", "inventory", "operations", "readme", "runbook", "topology"]
    assert expected["maximum_tree_depth"] == 8
    assert expected["maximum_tree_entries"] == 10000
    assert expected["maximum_documents_opened"] == 16
    assert expected["document_file_permission_rule"] == "NO_GROUP_OR_WORLD_WRITE"
    assert expected["provider_api_requests"] == 0
    assert expected["ssh_connections_attempted"] == 0
    assert expected["github_api_requests"] == 0
    assert boundary["protected_source_opened_only_after_unique_document_pointer"] is True


def test_valid_document_declared_source_is_ready_only_for_a_separate_phase() -> None:
    result = evaluate_resolver(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["document_declared_target_source_located"] is True
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_no_pointer_is_a_complete_zero_outbound_result() -> None:
    result = evaluate_resolver(_contract(), _facts(
        documentation_pointer_state="NOT_DECLARED_REDACTED",
        protected_metadata_source_state="NOT_ATTEMPTED",
        documentation_target_source_ready=False,
        candidate_schema_keys_read_in_memory_only=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["document_declared_target_source_located"] is False
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_resolver_opens_one_restrictive_nonsecret_document_and_its_unique_target(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_document(root, "RUNBOOK.md", "`_protected/abd/current-production-target.json`\n")
    _write_target(root, {
        "schema_version": "1.0.0",
        "provider": "provider-alias",
        "environment": "production",
        "target_alias": "current-service",
    })

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["protected_root_state"] == "AVAILABLE_READ_ONLY"
    assert facts["document_scan_state"] == "COMPLETED"
    assert facts["documentation_pointer_state"] == "RESOLVED_IN_MEMORY"
    assert facts["protected_metadata_source_state"] == "RESOLVED_IN_MEMORY"
    assert facts["documentation_target_source_ready"] is True
    assert facts["document_text_read_in_memory_only"] is True
    assert facts["candidate_schema_keys_read_in_memory_only"] is True


def test_resolver_does_not_open_target_when_documents_declare_no_pointer(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_document(root, "README.md", "No pointer is declared.\n")

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["documentation_pointer_state"] == "NOT_DECLARED_REDACTED"
    assert facts["protected_metadata_source_state"] == "NOT_ATTEMPTED"
    assert facts["candidate_schema_keys_read_in_memory_only"] is False


def test_resolver_rejects_multiple_unique_document_pointers_without_opening_target(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_document(root, "README.md", "`_protected/abd/current-production-target.json`\n")
    _write_document(root, "RUNBOOK.md", "`_protected/abd/production-target.json`\n")

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["documentation_pointer_state"] == "AMBIGUOUS_REDACTED"
    assert facts["protected_metadata_source_state"] == "NOT_ATTEMPTED"
    assert facts["candidate_schema_keys_read_in_memory_only"] is False


def test_resolver_ignores_document_filename_with_sensitive_token(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_document(root, "secret-runbook.md", "`_protected/abd/current-production-target.json`\n")

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["documentation_pointer_state"] == "NOT_DECLARED_REDACTED"
    assert facts["document_text_read_in_memory_only"] is False


def test_resolver_rejects_group_or_world_writable_document(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_document(root, "RUNBOOK.md", "`_protected/abd/current-production-target.json`\n", mode=0o666)

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["documentation_pointer_state"] == "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    assert facts["protected_metadata_source_state"] == "NOT_ATTEMPTED"
    assert facts["document_text_read_in_memory_only"] is False


def test_resolver_rejects_sensitive_pointer_before_source_lookup(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_document(root, "RUNBOOK.md", "`_protected/abd/current-production-target-secret.json`\n")

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["documentation_pointer_state"] == "INVALID_DECLARATION_REDACTED"
    assert facts["protected_metadata_source_state"] == "NOT_ATTEMPTED"


def test_resolver_rejects_nonmetadata_schema_without_retaining_key(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_document(root, "RUNBOOK.md", "`_protected/abd/current-production-target.json`\n")
    _write_target(root, {
        "schema_version": "1.0.0",
        "provider": "provider-alias",
        "target_alias": "current-service",
        "application_secret": "synthetic-only",
    })

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["documentation_pointer_state"] == "RESOLVED_IN_MEMORY"
    assert facts["protected_metadata_source_state"] == "SCHEMA_INCOMPLETE_REDACTED"
    assert "application_secret" not in json.dumps(facts, sort_keys=True)


def test_resolver_fails_closed_when_document_scan_is_truncated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    _write_document(root, "README.md", "No pointer.\n")
    (root / "plain.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(resolver, "MAX_TREE_ENTRIES", 1)

    facts = resolve_protected_documentation_pointer(root, observed_on="2026-08-12")

    assert facts["document_scan_state"] == "TRUNCATED_REDACTED"
    assert facts["documentation_pointer_state"] == "SCAN_LIMIT_REACHED_REDACTED"
    assert facts["documentation_target_source_ready"] is False


def test_facts_reject_document_or_pointer_leakage() -> None:
    facts = _facts()
    facts["document_path"] = "not retained"

    with pytest.raises(CurrentProductionProtectedDocumentationPointerResolverError, match="field set"):
        validate_facts(facts)


def test_facts_reject_any_outbound_attempt() -> None:
    facts = _facts(provider_api_requests=1)

    with pytest.raises(CurrentProductionProtectedDocumentationPointerResolverError, match="outbound operation count"):
        validate_facts(facts)


def test_receipt_redacts_document_scan_pointer_and_source_details() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["core_start_authorized"] is False
    assert '"document_scan_state":' not in serialized
    assert '"documentation_pointer_state":' not in serialized
    assert '"document_text_read_in_memory_only":' not in serialized


def test_contract_cannot_relax_zero_outbound_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["github_api_requests"] = 1

    with pytest.raises(CurrentProductionProtectedDocumentationPointerResolverError, match="resolver expectations"):
        validate_contract(contract)


def test_runner_has_no_network_transport_or_host_mutation_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "--protected-root" in source
    assert "current_production_protected_documentation_pointer_resolver.py" in source
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

    with pytest.raises(CurrentProductionProtectedDocumentationPointerResolverError):
        evaluate_resolver(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER"
