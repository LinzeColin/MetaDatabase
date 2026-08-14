from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_local_outbound_policy_classification_diagnostic as diagnostic
from current_production_local_outbound_policy_classification_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionLocalOutboundPolicyClassificationDiagnosticError,
    _packet_filter_state,
    _proxy_state,
    _route_state,
    build_receipt,
    discover_local_outbound_policy,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_local_outbound_policy_classification_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_local_outbound_policy_classification_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_local_outbound_policy_classification_diagnostic.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "default_route_state": "AVAILABLE",
        "proxy_policy_state": "DIRECT_OR_DISABLED",
        "packet_filter_state": "DISABLED",
        "local_outbound_policy_state": "NO_LOCAL_POLICY_CAUSE_OBSERVED_REDACTED",
        "policy_diagnosed": True,
        "current_tcp_failure_explained": False,
        "route_command_attempts": 1,
        "proxy_command_attempts": 1,
        "packet_filter_command_attempts": 1,
        "dns_resolution_attempts": 0,
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
        "route_proxy_or_packet_filter_value_emitted_or_persisted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_three_local_command_and_zero_network_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["local_commands"] == ["route -n get default", "scutil --proxy", "pfctl -s info"]
    assert expected["maximum_each_local_command_timeout_seconds"] == 2
    assert expected["route_command_attempts_at_most"] == 1
    assert expected["proxy_command_attempts_at_most"] == 1
    assert expected["packet_filter_command_attempts_at_most"] == 1
    assert expected["dns_resolution_attempts"] == 0
    assert expected["socket_connection_attempts"] == 0
    assert expected["ssh_connection_attempts"] == 0
    assert boundary["packet_filter_rules_read"] is False
    assert boundary["socket_connection_attempted"] is False
    assert boundary["ssh_connection_attempted"] is False


def test_absence_of_observed_local_policy_is_not_a_remote_cause_claim() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["policy_diagnosed"] is True
    assert result["current_tcp_failure_explained"] is False
    assert result["core_start_authorized"] is False
    assert result["local_outbound_policy_state"] == "NO_LOCAL_POLICY_CAUSE_OBSERVED_REDACTED"
    assert result["decision"] == "CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFIED_NO_CAUSAL_ATTRIBUTION_OR_REMOTE_ACTION_AUTHORIZED"


def test_proxy_and_packet_filter_presence_remains_noncausal() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        proxy_policy_state="PROXY_CONFIGURED",
        packet_filter_state="ENABLED",
        local_outbound_policy_state="PROXY_AND_PACKET_FILTER_PRESENT_NONCAUSAL_REDACTED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["policy_diagnosed"] is True
    assert result["current_tcp_failure_explained"] is False
    assert result["core_start_authorized"] is False


def test_unavailable_local_source_is_classified_unknown_without_causal_claim() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        default_route_state="UNAVAILABLE_REDACTED",
        local_outbound_policy_state="LOCAL_POLICY_UNKNOWN_REDACTED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["policy_diagnosed"] is True
    assert result["current_tcp_failure_explained"] is False
    assert result["local_outbound_policy_state"] == "LOCAL_POLICY_UNKNOWN_REDACTED"


def test_not_attempted_policy_source_fails_closed() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        default_route_state="NOT_ATTEMPTED",
        local_outbound_policy_state="LOCAL_POLICY_UNKNOWN_REDACTED",
        policy_diagnosed=False,
        route_command_attempts=0,
    ))

    assert result["status"] == FAIL_STATUS
    assert result["policy_diagnosed"] is False
    assert result["core_start_authorized"] is False


def test_facts_reject_causal_claim_or_any_network_operation() -> None:
    with pytest.raises(CurrentProductionLocalOutboundPolicyClassificationDiagnosticError, match="causal claim boundary"):
        validate_facts(_facts(current_tcp_failure_explained=True))

    with pytest.raises(CurrentProductionLocalOutboundPolicyClassificationDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(socket_connection_attempts=1))


def test_facts_reject_wrong_command_count_or_raw_policy_leakage() -> None:
    with pytest.raises(CurrentProductionLocalOutboundPolicyClassificationDiagnosticError, match="local command attempt count"):
        validate_facts(_facts(proxy_command_attempts=0))

    facts = _facts()
    facts["proxy_url"] = "not retained"
    with pytest.raises(CurrentProductionLocalOutboundPolicyClassificationDiagnosticError, match="field set"):
        validate_facts(facts)


def test_receipt_redacts_all_policy_source_values() -> None:
    receipt = build_receipt(_contract(), _facts(
        proxy_policy_state="PROXY_CONFIGURED",
        packet_filter_state="ENABLED",
        local_outbound_policy_state="PROXY_AND_PACKET_FILTER_PRESENT_NONCAUSAL_REDACTED",
    ))
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["current_tcp_failure_explained"] is False
    assert receipt["core_start_authorized"] is False
    assert '"default_route_state":' not in serialized
    assert '"proxy_policy_state":' not in serialized
    assert '"packet_filter_state":' not in serialized
    assert '"route_command_attempts":' not in serialized


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("   interface: en0\n", "AVAILABLE"),
        ("gateway: ignored\n", "UNAVAILABLE_REDACTED"),
        (None, "UNAVAILABLE_REDACTED"),
    ],
)
def test_default_route_parser_retains_only_availability(output: str | None, expected: str) -> None:
    assert _route_state(output) == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("HTTPEnable : 1\nHTTPProxy : ignored\n", "PROXY_CONFIGURED"),
        ("HTTPEnable : 0\nHTTPSEnable : 0\n", "DIRECT_OR_DISABLED"),
        (None, "UNAVAILABLE_REDACTED"),
    ],
)
def test_proxy_parser_retains_only_enabled_presence(output: str | None, expected: str) -> None:
    assert _proxy_state(output) == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("Status: Enabled for 1 days\n", "ENABLED"),
        ("Status: Disabled\n", "DISABLED"),
        ("rules: ignored\n", "UNAVAILABLE_REDACTED"),
        (None, "UNAVAILABLE_REDACTED"),
    ],
)
def test_packet_filter_parser_reads_status_not_rules(output: str | None, expected: str) -> None:
    assert _packet_filter_state(output) == expected


def test_discovery_invokes_only_three_local_policy_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, tuple[str, ...]]] = []
    outputs = {
        ("-n", "get", "default"): "interface: en0\n",
        ("--proxy",): "HTTPEnable : 1\n",
        ("-s", "info"): "Status: Enabled for 1 days\n",
    }

    monkeypatch.setattr(diagnostic, "_tool_available", lambda path: True)

    def fake_run(path: Path, args: tuple[str, ...]) -> str:
        calls.append((path, args))
        return outputs[args]

    monkeypatch.setattr(diagnostic, "_run_local_command", fake_run)
    facts = discover_local_outbound_policy(observed_on="2026-08-12")

    assert len(calls) == 3
    assert facts["default_route_state"] == "AVAILABLE"
    assert facts["proxy_policy_state"] == "PROXY_CONFIGURED"
    assert facts["packet_filter_state"] == "ENABLED"
    assert facts["local_outbound_policy_state"] == "PROXY_AND_PACKET_FILTER_PRESENT_NONCAUSAL_REDACTED"
    assert facts["dns_resolution_attempts"] == 0
    assert facts["socket_connection_attempts"] == 0
    assert facts["ssh_connection_attempts"] == 0
    assert facts["provider_api_requests"] == 0
    assert facts["github_api_requests"] == 0


def test_missing_tools_are_reported_without_command_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostic, "_tool_available", lambda path: False)
    facts = discover_local_outbound_policy(observed_on="2026-08-12")

    assert facts["default_route_state"] == "ROUTE_TOOL_UNAVAILABLE_REDACTED"
    assert facts["proxy_policy_state"] == "PROXY_TOOL_UNAVAILABLE_REDACTED"
    assert facts["packet_filter_state"] == "PF_TOOL_UNAVAILABLE_REDACTED"
    assert facts["route_command_attempts"] == 0
    assert facts["proxy_command_attempts"] == 0
    assert facts["packet_filter_command_attempts"] == 0
    assert facts["policy_diagnosed"] is True
    assert facts["local_outbound_policy_state"] == "LOCAL_POLICY_UNKNOWN_REDACTED"


def test_contract_cannot_relax_zero_socket_or_rule_read_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["socket_connection_attempts"] = 1

    with pytest.raises(CurrentProductionLocalOutboundPolicyClassificationDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_and_module_have_no_external_network_or_packet_filter_rule_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--contract" in runner
    assert "current_production_local_outbound_policy_classification_diagnostic.py" in runner
    assert 'PACKET_FILTER_COMMAND = (Path("/sbin/pfctl"), ("-s", "info"))' in module
    for forbidden in (
        "socket.",
        "getaddrinfo",
        "connect_ex",
        "ssh ",
        "sshpass",
        "curl ",
        "wget ",
        "gh ",
        "pfctl -sr",
        "pfctl -sa",
        "pfctl -sr",
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

    with pytest.raises(CurrentProductionLocalOutboundPolicyClassificationDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_DIAGNOSTIC"
