from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_protected_provider_auth_route_resolver as resolver
from current_production_protected_provider_auth_route_resolver import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionProtectedProviderAuthRouteResolverError,
    _route_related,
    _valid_auth_target,
    build_receipt,
    evaluate_resolver,
    locate_provider_auth_recovery_route,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_protected_provider_auth_route_resolver_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_protected_provider_auth_route_resolver.sh"
MODULE_PATH = RUNTIME / "current_production_protected_provider_auth_route_resolver.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER",
        "observed_on": "2026-08-12",
        "protected_root_state": "AVAILABLE_READ_ONLY",
        "bounded_scan_state": "COMPLETED",
        "provider_auth_route_source_state": "RESOLVED_IN_MEMORY",
        "provider_auth_route_source_ready": True,
        "candidate_credential_values_used_in_memory_only": True,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "protected_path_or_filename_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _auth_target() -> dict[str, str]:
    return {
        "endpoint": "https://api.ovh.com/1.0",
        "application_key": "test-application-key",
        "application_secret": "test-application-secret",
        "consumer_key": "test-consumer-key",
        "service_name": "test-vps-01",
    }


def _write_candidate(root: Path, relative: str, payload: object, mode: int = 0o600) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(mode)
    return path


def test_contract_preserves_bounded_in_memory_only_and_zero_external_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["required_auth_source_keys"] == ["application_key", "application_secret", "consumer_key", "endpoint", "service_name"]
    assert expected["required_path_tokens"] == ["abd"]
    assert expected["maximum_tree_depth"] == 8
    assert expected["maximum_tree_entries"] == 16384
    assert expected["maximum_json_schema_files_checked"] == 64
    assert expected["maximum_auth_value_candidates_opened"] == 12
    assert expected["provider_api_requests"] == 0
    assert expected["ssh_connections_attempted"] == 0
    assert boundary["candidate_credential_values_used_in_memory_only"] is True
    assert boundary["candidate_json_schema_keys_read_in_memory_only"] is True
    assert boundary["credential_material_emitted_or_persisted"] is False
    assert boundary["provider_api_request_sent"] is False


def test_resolved_source_allows_only_a_separate_management_plane_get_phase() -> None:
    result = evaluate_resolver(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["provider_auth_route_resolved"] is True
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False
    assert result["decision"] == "CURRENT_PRODUCTION_PROVIDER_AUTH_ROUTE_READY_FOR_SEPARATE_MANAGEMENT_PLANE_GET_PHASE"


@pytest.mark.parametrize("source_state", ["NOT_AVAILABLE_REDACTED", "SCHEMA_REJECTED_REDACTED", "PERMISSION_BOUNDARY_REJECTED_REDACTED", "AMBIGUOUS_REDACTED"])
def test_unready_source_is_diagnosed_but_never_authorizes_remote_action(source_state: str) -> None:
    result = evaluate_resolver(_contract(), _facts(
        provider_auth_route_source_state=source_state,
        provider_auth_route_source_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["provider_auth_route_resolved"] is False
    assert result["core_start_authorized"] is False
    assert result["decision"] == "CURRENT_PRODUCTION_PROVIDER_AUTH_ROUTE_NOT_AVAILABLE_NO_REMOTE_ACTION_AUTHORIZED"


def test_truncated_scan_fails_closed_even_when_a_candidate_was_seen() -> None:
    result = evaluate_resolver(_contract(), _facts(
        bounded_scan_state="TRUNCATED_REDACTED",
        provider_auth_route_source_state="SCAN_LIMIT_REACHED_REDACTED",
        provider_auth_route_source_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["provider_auth_route_resolved"] is False
    assert result["core_start_authorized"] is False


def test_unavailable_root_is_a_failed_input_state() -> None:
    result = evaluate_resolver(_contract(), _facts(
        protected_root_state="UNAVAILABLE_REDACTED",
        bounded_scan_state="NOT_ATTEMPTED",
        provider_auth_route_source_state="UNAVAILABLE_REDACTED",
        provider_auth_route_source_ready=False,
        candidate_credential_values_used_in_memory_only=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["provider_auth_route_resolved"] is False
    assert result["core_start_authorized"] is False


def test_facts_reject_secret_path_or_outbound_leakage() -> None:
    with pytest.raises(CurrentProductionProtectedProviderAuthRouteResolverError, match="outbound operation count"):
        validate_facts(_facts(provider_api_requests=1))

    facts = _facts()
    facts["candidate_path"] = "not retained"
    with pytest.raises(CurrentProductionProtectedProviderAuthRouteResolverError, match="field set"):
        validate_facts(facts)


def test_receipt_does_not_retain_source_path_or_credential_values() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["provider_auth_route_resolved"] is True
    assert receipt["core_start_authorized"] is False
    assert '"provider_auth_route_source_state":' not in serialized
    assert "test-application-key" not in serialized
    assert "test-application-secret" not in serialized
    assert "test-consumer-key" not in serialized
    assert "test-vps-01" not in serialized


def test_route_related_requires_abd_and_recovery_hint(tmp_path: Path) -> None:
    root = tmp_path / "protected"
    root.mkdir()
    assert _route_related(root, root / "abd" / "ovh" / "source.json") is True
    assert _route_related(root, root / "abd" / "plain" / "source.json") is False
    assert _route_related(root, root / "ovh" / "source.json") is False


def test_auth_target_schema_rejects_bad_endpoint_or_extra_field() -> None:
    assert _valid_auth_target(_auth_target()) is True

    bad_endpoint = _auth_target()
    bad_endpoint["endpoint"] = "https://api.ovh.com:bad/1.0"
    assert _valid_auth_target(bad_endpoint) is False

    extra = _auth_target()
    extra["extra"] = "no"
    assert _valid_auth_target(extra) is False


def test_single_safe_candidate_resolves_only_in_memory(tmp_path: Path) -> None:
    root = tmp_path / "protected"
    root.mkdir()
    _write_candidate(root, "ABD/recovery/ovh_route.json", _auth_target())

    facts = locate_provider_auth_recovery_route(root, observed_on="2026-08-12")

    assert facts["protected_root_state"] == "AVAILABLE_READ_ONLY"
    assert facts["bounded_scan_state"] == "COMPLETED"
    assert facts["provider_auth_route_source_state"] == "RESOLVED_IN_MEMORY"
    assert facts["provider_auth_route_source_ready"] is True
    assert facts["candidate_credential_values_used_in_memory_only"] is True
    assert facts["provider_api_requests"] == 0
    assert facts["ssh_connections_attempted"] == 0
    assert facts["github_api_requests"] == 0


def test_ambiguous_safe_candidates_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "protected"
    root.mkdir()
    _write_candidate(root, "ABD/ovh/one.json", _auth_target())
    _write_candidate(root, "ABD/ovh/two.json", _auth_target())

    facts = locate_provider_auth_recovery_route(root, observed_on="2026-08-12")

    assert facts["bounded_scan_state"] == "COMPLETED"
    assert facts["provider_auth_route_source_state"] == "AMBIGUOUS_REDACTED"
    assert facts["provider_auth_route_source_ready"] is False


def test_invalid_schema_and_unsafe_permission_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "protected"
    root.mkdir()
    _write_candidate(root, "ABD/ovh/invalid.json", {"provider": "ovh"})
    unsafe = _write_candidate(root, "ABD/ovh/unsafe.json", _auth_target(), mode=0o644)
    assert unsafe.stat().st_mode & stat.S_IROTH

    facts = locate_provider_auth_recovery_route(root, observed_on="2026-08-12")

    assert facts["provider_auth_route_source_state"] in {"SCHEMA_REJECTED_REDACTED", "PERMISSION_BOUNDARY_REJECTED_REDACTED"}
    assert facts["provider_auth_route_source_ready"] is False


def test_tree_limit_fails_closed_even_with_early_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "protected"
    root.mkdir()
    _write_candidate(root, "ABD/ovh/source.json", _auth_target())
    _write_candidate(root, "ABD/ovh/extra.json", {"provider": "ovh"})
    monkeypatch.setattr(resolver, "MAX_TREE_ENTRIES", 1)

    facts = locate_provider_auth_recovery_route(root, observed_on="2026-08-12")

    assert facts["bounded_scan_state"] == "TRUNCATED_REDACTED"
    assert facts["provider_auth_route_source_state"] == "SCAN_LIMIT_REACHED_REDACTED"
    assert facts["provider_auth_route_source_ready"] is False


def test_contract_cannot_relax_zero_provider_api_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["provider_api_requests"] = 1

    with pytest.raises(CurrentProductionProtectedProviderAuthRouteResolverError, match="resolver expectations"):
        validate_contract(contract)


def test_runner_and_module_have_no_network_or_remote_execution_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--protected-root" in runner
    assert "current_production_protected_provider_auth_route_resolver.py" in runner
    for forbidden in (
        "socket.",
        "urllib.request",
        "import requests",
        "requests.",
        "urlopen",
        "subprocess",
        "ssh ",
        "sshpass",
        "curl ",
        "wget ",
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
        assert forbidden not in runner
        assert forbidden not in module


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionProtectedProviderAuthRouteResolverError):
        evaluate_resolver(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER"
