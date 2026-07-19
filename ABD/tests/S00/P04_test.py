from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.external_consent import (
    DEGRADED_PATH,
    FIXTURE_PATH,
    GMAIL_SCOPE,
    PREREQUISITES_PATH,
    RUNBOOK_PATH,
    build_evidence,
    evaluate_contract,
    perform_rollback_drill,
    resolve_consent_event,
    validate_consent_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _gmail_prerequisite(value):
    return next(item for item in value["items"] if item["id"] == "DP-004")


def _state(value, state_id: str):
    return next(item for item in value["states"] if item["id"] == state_id)


def _authorization_action(value, action_id: str):
    return next(item for item in value["actions"] if item["id"] == action_id)


def _default(value, condition_code: str):
    return next(item for item in value["defaults"] if item["condition_code"] == condition_code)


def test_baseline_external_consent_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 49
    assert result["gmail_connection_status"] == "NOT_CONNECTED"
    assert result["external_capability_status"] == "UNVERIFIED"
    assert result["release_status"] == "NOT_READY"
    assert result["stage_status"] == "S00_PHASES_COMPLETE_REVIEW_PENDING"
    assert result["next"] == "S00/STAGE_REVIEW_READY_NOT_STARTED"


@pytest.mark.parametrize("case", FIXTURE["scenario_cases"], ids=lambda case: case["id"])
def test_consent_state_machine_scenarios_are_deterministic(case) -> None:
    contract = strict_json_load(ROOT / DEGRADED_PATH)
    state = resolve_consent_event(contract, case["event"], case["proven_gate_ids"])
    assert state["id"] == case["expected_state"]
    assert state["gmail_enabled"] is case["expected_gmail_enabled"]
    assert state["core_task_graph"] == case["expected_core_task_graph"]


def test_active_event_with_extra_or_missing_gate_fails_to_unverified() -> None:
    contract = strict_json_load(ROOT / DEGRADED_PATH)
    required = [item["id"] for item in contract["activation_gates"]]
    for provided in (required[:-1], required + ["UNKNOWN-GATE"]):
        state = resolve_consent_event(contract, "ALL_ACTIVATION_GATES_PROVEN", provided)
        assert state["id"] == "CONSENT_GRANTED_UNVERIFIED"
        assert state["gmail_enabled"] is False


def test_missing_consent_disables_only_gmail_and_preserves_stage_review() -> None:
    prerequisites = strict_json_load(ROOT / PREREQUISITES_PATH)
    impact = prerequisites["gmail_missing_consent_impact"]
    assert impact["release_claim"] == "GMAIL_NOT_CONNECTED"
    assert impact["core_task_graph"] == "CONTINUE_SUBJECT_TO_INDEPENDENT_GATES"
    assert "GMAIL_POLL" in impact["disabled_components"]
    assert "STAGE_REVIEW" in impact["unaffected_components"]


@pytest.mark.parametrize("case", FIXTURE["cash_boundary_cases"], ids=lambda case: case["id"])
def test_gmail_incremental_cash_boundary_is_exactly_zero(tmp_path: Path, case) -> None:
    project = _clone_project(tmp_path)
    path = project / PREREQUISITES_PATH
    prerequisites = strict_json_load(path)
    _gmail_prerequisite(prerequisites)["incremental_cash_cost_aud"] = case["value"]
    _write_json(path, prerequisites)
    result = evaluate_contract(project, False)
    assert result["status"] == case["expected_status"]
    assert "CONSENT-GMAIL-PREREQUISITE-FAIL-CLOSED" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requested_scope_exact", "https://mail.google.com/"),
        ("blocking_for_current_core_task_graph", True),
        ("capability_status", "VERIFIED_AVAILABLE"),
        ("current_human_action", "APPROVE_NOW"),
        ("fallback", "PAUSE_ALL"),
        ("owner_reprompt_policy", "AUTOMATIC_DAILY"),
    ],
)
def test_gmail_prerequisite_unsafe_mutations_fail_closed(tmp_path: Path, field: str, value) -> None:
    project = _clone_project(tmp_path)
    path = project / PREREQUISITES_PATH
    prerequisites = strict_json_load(path)
    _gmail_prerequisite(prerequisites)[field] = value
    _write_json(path, prerequisites)
    result = evaluate_contract(project, False)
    expected = (
        "CONSENT-NO-EXTERNAL-CAPABILITY-OR-ACTION-CLAIM"
        if field in {"capability_status", "current_human_action"}
        else "CONSENT-GMAIL-PREREQUISITE-FAIL-CLOSED"
    )
    _failed(result, expected)


def test_missing_gmail_prerequisite_fails_structure(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / PREREQUISITES_PATH
    prerequisites = strict_json_load(path)
    prerequisites["items"] = [item for item in prerequisites["items"] if item["id"] != "DP-004"]
    _write_json(path, prerequisites)
    _failed(evaluate_contract(project, False), "CONSENT-PREREQUISITES-STRUCTURE")


def test_duplicate_prerequisite_id_fails_structure(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / PREREQUISITES_PATH
    prerequisites = strict_json_load(path)
    prerequisites["items"].append(deepcopy(prerequisites["items"][0]))
    _write_json(path, prerequisites)
    _failed(evaluate_contract(project, False), "CONSENT-PREREQUISITES-STRUCTURE")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_when_active", ["users.messages.send"]),
        ("always_denied", ["users.messages.trash"]),
        ("unknown_method_action", "ALLOW_AND_LOG"),
    ],
)
def test_method_boundary_mutations_fail_closed(tmp_path: Path, field: str, value) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["method_policy"][field] = value
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-SCOPE-AND-METHOD-BOUNDARY")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gmail_enabled", True),
        ("gmail_external_calls_allowed", True),
        ("core_task_graph", "PAUSE_ALL"),
    ],
)
def test_ordinary_degraded_state_cannot_enable_or_block_core(tmp_path: Path, field: str, value) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    _state(contract, "CONSENT_DENIED")[field] = value
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-ORDINARY-STATES-DISABLE-ONLY-GMAIL")


def test_current_state_cannot_claim_active(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["current_state"] = "ACTIVE"
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-STATES-STRUCTURE")


def test_direct_pending_to_active_transition_is_forbidden(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["allowed_transitions"].append("CONSENT_PENDING->ACTIVE")
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-TRANSITIONS-NO-DIRECT-ACTIVATION")


def test_current_activation_gate_cannot_be_claimed_proven(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["activation_gates"][0]["current_status"] = "PROVEN"
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-ACTIVATION-GATES-CURRENTLY-UNPROVEN")


@pytest.mark.parametrize(
    "field",
    [
        "external_product_or_account_network_access",
        "oauth_link_generated",
        "owner_consent_requested",
        "token_received_or_stored",
        "gmail_api_called",
        "email_moved_or_deleted",
    ],
)
def test_p04_cannot_claim_external_effect(tmp_path: Path, field: str) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["s00_p04_execution_boundary"][field] = True
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-NO-EXTERNAL-EFFECT-IN-P04")


def test_security_incident_must_use_p02_pause_contract(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    _state(contract, "SECURITY_ISOLATED")["core_task_graph"] = "CONTINUE_SUBJECT_TO_INDEPENDENT_GATES"
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-ACTIVE-AND-SECURITY-EXCEPTION")


def test_receipt_alone_cannot_activate(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["activation_rule"]["receipt_alone_never_activates"] = False
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-ACTIVATION-RULE")


def test_receipt_contract_cannot_drop_token_field_prohibition(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["consent_receipt_contract"]["forbidden_fields"].remove("refresh_token")
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "DEGRADED-RECEIPT-CONTRACT")


def test_p02_gmail_authorization_drift_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/authorization_matrix.json"
    authorization = strict_json_load(path)
    _authorization_action(authorization, "GMAIL_OAUTH_CONSENT")["authorization"] = "PREAUTHORIZED"
    _write_json(path, authorization)
    _failed(evaluate_contract(project, False), "CONSENT-P02-AUTHORIZATION-ALIGNMENT")


def test_p02_missing_consent_default_drift_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/default_decisions.json"
    defaults = strict_json_load(path)
    _default(defaults, "OPTIONAL_GMAIL_CONSENT_MISSING")["blocks_task_graph"] = True
    _write_json(path, defaults)
    _failed(evaluate_contract(project, False), "CONSENT-P02-DEFAULT-ALIGNMENT")


def test_canonical_gmail_scope_drift_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/canonical_facts.json"
    canonical = strict_json_load(path)
    canonical["email"]["gmail_scope_required"] = "mail.google.com"
    _write_json(path, canonical)
    _failed(evaluate_contract(project, False), "CONSENT-CANONICAL-ALIGNMENT")


def test_p03_prerequisite_must_remain_pass(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/EVD-S00-P03.json"
    evidence = strict_json_load(path)
    evidence["status"] = "FAIL"
    _write_json(path, evidence)
    _failed(evaluate_contract(project, False), "PREREQ-P03-PASS")


def test_malformed_p03_evidence_index_fails_closed_without_crashing(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "machine/evidence/evidence_index.jsonl").write_text("{\n", encoding="utf-8")
    _failed(evaluate_contract(project, False), "PREREQ-P03-PASS")


def test_second_degraded_contract_source_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    shadow = project / "shadow/degraded_mode_contract.json"
    shadow.parent.mkdir(parents=True)
    shutil.copyfile(str(project / DEGRADED_PATH), str(shadow))
    _failed(evaluate_contract(project, False), "SOURCE-SINGLE-DEGRADED_MODE_CONTRACT")


def test_duplicate_json_key_fails_closed_without_crashing(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / PREREQUISITES_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{", '{\n  "schema_version": "duplicate",', 1), encoding="utf-8")
    _failed(evaluate_contract(project, False), "INPUT-PREREQUISITES-PARSE")


def test_runbook_requires_exactly_one_machine_contract_block(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / RUNBOOK_PATH
    with path.open("a", encoding="utf-8") as handle:
        handle.write('\n```json\n{"duplicate": true}\n```\n')
    _failed(evaluate_contract(project, False), "RUNBOOK-MACHINE-CONTRACT-PARSE")


def test_runbook_malformed_machine_contract_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / RUNBOOK_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"runbook_contract_id":', '"runbook_contract_id"'), encoding="utf-8")
    _failed(evaluate_contract(project, False), "RUNBOOK-MACHINE-CONTRACT-PARSE")


def test_runbook_contract_must_match_method_policy(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / RUNBOOK_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('"users.messages.trash"', '"users.messages.modifyLabels"', 1),
        encoding="utf-8",
    )
    _failed(evaluate_contract(project, False), "RUNBOOK-CROSS-SOURCE-CONTRACT")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"access_type": "offline"', '"access_type": "online"'),
        ('"pkce": "S256_REQUIRED"', '"pkce": "OPTIONAL"'),
        ('"redirect_uri": "EXACT_HTTPS_OWNER_CONTROLLED_URI"', '"redirect_uri": "WILDCARD_HTTP"'),
    ],
)
def test_runbook_unsafe_oauth_parameter_fails_closed(tmp_path: Path, old: str, new: str) -> None:
    project = _clone_project(tmp_path)
    path = project / RUNBOOK_PATH
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    _failed(evaluate_contract(project, False), "RUNBOOK-OAUTH-REQUEST-SAFETY")


@pytest.mark.parametrize(
    "phrase",
    ["7 天失效", "不得使用内嵌浏览器", "下一步是 Stage 0 整体复审", "传播延迟"],
)
def test_runbook_required_risk_or_stop_disclosure_cannot_be_removed(tmp_path: Path, phrase: str) -> None:
    project = _clone_project(tmp_path)
    path = project / RUNBOOK_PATH
    text = path.read_text(encoding="utf-8")
    assert phrase in text
    path.write_text(text.replace(phrase, "REMOVED", 1), encoding="utf-8")
    _failed(evaluate_contract(project, False), "RUNBOOK-RISK-AND-STOP-DISCLOSURE")


def test_non_first_party_oauth_source_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEGRADED_PATH
    contract = strict_json_load(path)
    contract["official_source_snapshot"][0]["url"] = "https://example.invalid/oauth"
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "CONSENT-OFFICIAL-SOURCE-SNAPSHOT")


def test_valid_nonsecret_disabled_receipt_passes() -> None:
    contract = strict_json_load(ROOT / DEGRADED_PATH)
    assert validate_consent_receipt(contract, FIXTURE["valid_nonsecret_receipt"]) == []


def test_valid_live_verified_active_receipt_passes_contract_shape() -> None:
    contract = strict_json_load(ROOT / DEGRADED_PATH)
    receipt = deepcopy(FIXTURE["valid_nonsecret_receipt"])
    receipt.update(
        {
            "authorization_status": "GRANTED",
            "granted_scopes": [GMAIL_SCOPE],
            "state_validated": True,
            "pkce_validated": True,
            "redirect_uri_validated": True,
            "token_storage_status": "VERIFIED_ENCRYPTED",
            "oauth_app_status": "VERIFIED_PRODUCTION",
            "external_capability_verified": True,
            "gmail_module_state": "ACTIVE",
        }
    )
    assert validate_consent_receipt(contract, receipt) == []


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("missing_required", "missing:observed_at"),
        ("access_token", "forbidden:access_token"),
        ("refresh_token", "forbidden:refresh_token"),
        ("secret_true", "secret_material_present"),
        ("broader_scope", "scope_not_exact"),
        ("scope_without_grant", "scope_without_grant"),
        ("capability_without_grant", "capability_without_grant"),
        ("active_without_gates", "active_without_all_receipt_gates"),
        ("local_path", "sensitive_value_pattern"),
        ("non_boolean", "state_validated_not_boolean"),
        ("unknown_status", "authorization_status_invalid"),
    ],
)
def test_invalid_or_secret_bearing_receipts_fail_closed(mutation: str, expected_error: str) -> None:
    contract = strict_json_load(ROOT / DEGRADED_PATH)
    receipt = deepcopy(FIXTURE["valid_nonsecret_receipt"])
    if mutation == "missing_required":
        del receipt["observed_at"]
    elif mutation == "access_token":
        receipt["access_token"] = "redacted-placeholder"
    elif mutation == "refresh_token":
        receipt["refresh_token"] = "redacted-placeholder"
    elif mutation == "secret_true":
        receipt["secret_material_present"] = True
    elif mutation == "broader_scope":
        receipt["authorization_status"] = "GRANTED"
        receipt["granted_scopes"] = [GMAIL_SCOPE, "https://mail.google.com/"]
    elif mutation == "scope_without_grant":
        receipt["granted_scopes"] = [GMAIL_SCOPE]
    elif mutation == "capability_without_grant":
        receipt["external_capability_verified"] = True
    elif mutation == "active_without_gates":
        receipt["gmail_module_state"] = "ACTIVE"
    elif mutation == "local_path":
        receipt["diagnostic_path"] = "/" + "Users/example/oauth.json"
    elif mutation == "non_boolean":
        receipt["state_validated"] = "yes"
    elif mutation == "unknown_status":
        receipt["authorization_status"] = "UNKNOWN"
    assert expected_error in validate_consent_receipt(contract, receipt)


def test_evidence_replay_is_deterministic_without_runtime_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["stage_phase_completion"]["stage_review_status"] == "NOT_STARTED"
    assert first["stage_phase_completion"]["stage_pass_claimed"] is False


def test_rollback_drill_restores_all_three_p04_artifacts() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert set(result["artifacts"]) == {
        PREREQUISITES_PATH.as_posix(),
        DEGRADED_PATH.as_posix(),
        RUNBOOK_PATH.as_posix(),
    }


def test_contract_evaluation_does_not_mutate_source_artifacts() -> None:
    paths = [PREREQUISITES_PATH, DEGRADED_PATH, RUNBOOK_PATH, FIXTURE_PATH]
    before = {path.as_posix(): sha256_file(ROOT / path) for path in paths}
    result = evaluate_contract(ROOT, require_external_reports=False)
    after = {path.as_posix(): sha256_file(ROOT / path) for path in paths}
    assert result["status"] == "PASS"
    assert before == after
