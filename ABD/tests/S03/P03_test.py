from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.advice_card import verify_existing_phase_evidence as verify_p02_evidence
from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.reason_next_action import (
    ALLOWED_NUMERIC_BOUNDARY_DELTAS,
    CONTRACT_ID,
    EVIDENCE_PATH,
    FIXED_CLOCK,
    FULL_JUNIT_PATH,
    GLOSSARY_PATH,
    JUNIT_PATH,
    NEXT_ACTION_MATRIX_PATH,
    ORACLE_FIXTURE_PATH,
    PACK_REPORT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    REASON_CODES_PATH,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    FailureGuidanceError,
    _action_by_id,
    _coverage_source_keys,
    _mapping_by_code,
    _pack_report_passes,
    _paid_dependency_scan_passes,
    _reason_by_code,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    render_failure_guidance,
    resolve_failure_states,
    safe_resolve_failure_states,
    validate_resolution,
    verify_existing_phase_evidence,
)
from abd_acceptance.terminology_governance import scan_ui_text


ROOT = Path(__file__).resolve().parents[2]
CATALOG = strict_json_load(ROOT / REASON_CODES_PATH)
MATRIX = strict_json_load(ROOT / NEXT_ACTION_MATRIX_PATH)
FIXTURE = strict_json_load(ROOT / ORACLE_FIXTURE_PATH)
GLOSSARY = strict_json_load(ROOT / GLOSSARY_PATH)
POLICY = strict_json_load(ROOT / "forbidden_ui_terms.json")
REASONS = _reason_by_code(CATALOG)
ACTIONS = _action_by_id(MATRIX)
MAPPINGS = _mapping_by_code(MATRIX)
COVERAGE_CASES = [
    (reference, code)
    for code, reason in REASONS.items()
    for reference in reason["coverage_refs"]
]


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(str(ROOT.parent / ".github"), str(destination.parent / ".github"))
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _resolve(states, delta: str = "0"):
    return resolve_failure_states(
        states,
        reason_catalog=CATALOG,
        next_action_matrix=MATRIX,
        numeric_boundary_delta=delta,
    )


def _safe(states, delta="0"):
    return safe_resolve_failure_states(
        states,
        reason_catalog=CATALOG,
        next_action_matrix=MATRIX,
        numeric_boundary_delta=delta,
    )


def _validate(value, catalog=CATALOG, matrix=MATRIX):
    return validate_resolution(
        value,
        reason_catalog=catalog,
        next_action_matrix=matrix,
        glossary=GLOSSARY,
        policy=POLICY,
    )


def test_baseline_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["phase_status"] == FIXTURE["expected_phase_status"]
    assert result["coverage_status"] == "ALL_CURRENTLY_DECLARED_FAILURE_CLASSES_CLOSED_FUTURE_PHASES_MUST_EXTEND"
    assert result["release_status"] == FIXTURE["expected_release_status"]
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_p02_signed_delivery_is_exact_start_prerequisite() -> None:
    result = verify_p02_evidence(ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S03_P02_EVIDENCE_VERIFIED"
    assert result["next"] == "S03/P03_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_catalog_and_matrix_counts_are_exact() -> None:
    assert len(REASONS) == FIXTURE["expected_reason_count"] == 49
    assert len(ACTIONS) == FIXTURE["expected_action_count"] == 38
    assert len(MAPPINGS) == len(REASONS)
    assert len(COVERAGE_CASES) == FIXTURE["expected_coverage_reference_count"] == 72


def test_catalog_and_matrix_order_is_frozen() -> None:
    assert list(REASONS) == FIXTURE["expected_reason_codes"]
    assert list(ACTIONS) == FIXTURE["expected_action_ids"]
    assert list(MAPPINGS) == FIXTURE["expected_reason_codes"]


@pytest.mark.parametrize("code", FIXTURE["expected_reason_codes"])
def test_each_reason_has_one_frozen_action_and_unique_priority(code: str) -> None:
    reason = REASONS[code]
    mapping = MAPPINGS[code]
    assert reason["code"] == code
    assert reason["priority"] == mapping["priority"]
    assert reason["default_next_action_id"] == mapping["next_action_id"]
    assert mapping["action_count"] == 1
    assert mapping["next_action_id"] in ACTIONS
    assert mapping["retry_policy"] == "NO_ORDER_RETRY"
    assert reason["priority"] not in [
        REASONS[other]["priority"] for other in REASONS if other != code
    ]


@pytest.mark.parametrize("code", FIXTURE["expected_reason_codes"])
def test_each_reason_has_chinese_visible_content_and_traceable_source(code: str) -> None:
    reason = REASONS[code]
    visible = reason["title_zh"] + "\n" + reason["message_zh"]
    assert reason["coverage_refs"]
    assert scan_ui_text(visible, "USER_ERROR_NEXT_ACTION", GLOSSARY, POLICY) == []


@pytest.mark.parametrize("action_id", FIXTURE["expected_action_ids"])
def test_each_action_is_local_reversible_zero_cash_and_cannot_order(action_id: str) -> None:
    action = ACTIONS[action_id]
    assert action["automatic_selection"] is True
    assert action["external_effect_performed"] is False
    assert action["may_submit_order"] is False
    assert action["may_retry_order"] is False
    assert action["may_spend_cash"] is False
    assert action["may_relax_evidence_numeric_risk_or_safety_gate"] is False
    assert action["irreversible"] is False
    assert action["incremental_cash_cost_aud"] == "0.00"


@pytest.mark.parametrize("action_id", FIXTURE["expected_action_ids"])
def test_each_action_visible_text_passes_chinese_policy(action_id: str) -> None:
    action = ACTIONS[action_id]
    visible = "\n".join(
        action[key]
        for key in ["title_zh", "system_behavior_zh", "owner_guidance_zh"]
    )
    assert scan_ui_text(visible, "USER_ERROR_NEXT_ACTION", GLOSSARY, POLICY) == []


@pytest.mark.parametrize(("reference", "code"), COVERAGE_CASES)
def test_each_coverage_reference_maps_back_to_its_exact_reason(reference: str, code: str) -> None:
    group_id, source_key = reference.split(":", 1)
    group = next(row for row in FIXTURE["coverage_groups"] if row["id"] == group_id)
    assert group["mappings"][source_key] == code
    assert reference in REASONS[code]["coverage_refs"]


@pytest.mark.parametrize("group", FIXTURE["coverage_groups"], ids=lambda row: row["id"])
def test_each_authoritative_coverage_group_is_exact(group: dict) -> None:
    assert _coverage_source_keys(ROOT, group) == list(group["mappings"])


@pytest.mark.parametrize("code", FIXTURE["expected_reason_codes"])
def test_every_reason_resolves_deterministically_to_exactly_one_safe_action(code: str) -> None:
    first = _resolve([code])
    second = _resolve([code])
    assert first == second
    assert first["selected_reason"]["code"] == code
    assert first["next_action"]["action_id"] == MAPPINGS[code]["next_action_id"]
    assert first["considered_count"] == 1
    assert _validate(first) == []


@pytest.mark.parametrize("code", FIXTURE["expected_reason_codes"])
def test_every_reason_resolution_visible_text_hides_machine_codes(code: str) -> None:
    result = _resolve([code])
    visible = render_failure_guidance(result)
    assert code not in visible
    assert result["next_action"]["action_id"] not in visible
    assert scan_ui_text(visible, "USER_ERROR_NEXT_ACTION", GLOSSARY, POLICY) == []


@pytest.mark.parametrize("vector", FIXTURE["p02_reason_vectors"], ids=lambda row: row["id"])
def test_p02_failure_reason_is_normalized_to_exact_p03_reason(vector: dict) -> None:
    result = _resolve(vector["input"])
    assert result["selected_reason"]["code"] == vector["expected_reason_code"]
    assert result["considered_count"] == 1
    assert _validate(result) == []


@pytest.mark.parametrize("vector", FIXTURE["multi_failure_vectors"], ids=lambda row: row["id"])
def test_multiple_failures_have_one_order_invariant_priority_winner(vector: dict) -> None:
    forward = _resolve(vector["input"])
    reverse = _resolve(list(reversed(vector["input"])))
    assert forward["selected_reason"]["code"] == vector["expected_reason_code"]
    assert reverse["selected_reason"]["code"] == vector["expected_reason_code"]
    assert forward["next_action"] == reverse["next_action"]
    assert _validate(forward) == []
    assert _validate(reverse) == []


@pytest.mark.parametrize("vector", FIXTURE["malformed_inputs"], ids=lambda row: row["id"])
def test_every_malformed_or_unknown_input_fails_closed_to_unknown(vector: dict) -> None:
    result = _safe(vector["input"])
    assert result["selected_reason"]["code"] == "UNKNOWN_FAILURE_STATE"
    assert result["next_action"]["action_id"] == "STOP_AND_PRESERVE"
    assert _validate(result) == []


@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_boundary_deltas"])
def test_adverse_numeric_boundary_does_not_change_action(delta: str) -> None:
    result = _resolve(["CURRENT_ODDS_BELOW_MINIMUM"], delta)
    assert result["selected_reason"]["code"] == "CURRENT_ODDS_BELOW_MINIMUM"
    assert result["next_action"]["action_id"] == "WAIT_FOR_ACCEPTABLE_ODDS"
    assert result["numeric_boundary_delta"] == delta
    assert _validate(result) == []


@pytest.mark.parametrize("delta", ["0.0000", "0.00010", "1e-4", "NaN", 0.0001, None])
def test_non_frozen_numeric_boundary_is_rejected_and_safe_wrapper_stops(delta) -> None:
    with pytest.raises(FailureGuidanceError):
        _resolve(["CURRENT_ODDS_BELOW_MINIMUM"], delta)
    result = _safe(["CURRENT_ODDS_BELOW_MINIMUM"], delta)
    assert result["selected_reason"]["code"] == "UNKNOWN_FAILURE_STATE"
    assert result["numeric_boundary_delta"] == "0"


def test_empty_input_and_unknown_input_do_not_mean_no_qualified_opportunity() -> None:
    assert _safe([])["selected_reason"]["code"] == "UNKNOWN_FAILURE_STATE"
    assert _safe(["UNREGISTERED"])["selected_reason"]["code"] == "UNKNOWN_FAILURE_STATE"


def test_generic_upstream_gate_requires_exactly_one_registered_evidence_reference() -> None:
    good = _resolve([
        {
            "code": "UPSTREAM_GATE_FAILED",
            "evidence_refs": ["CARD:GATE:QUOTE-FRESH"],
        }
    ])
    assert good["selected_reason"]["code"] == "QUOTE_STALE"
    for refs in [[], ["UNKNOWN"], ["CARD:GATE:QUOTE-FRESH", "CARD:GATE:RISK-GATE-PASSED"]]:
        result = _safe([{"code": "UPSTREAM_GATE_FAILED", "evidence_refs": refs}])
        assert result["selected_reason"]["code"] == "UNKNOWN_FAILURE_STATE"


def test_machine_code_and_action_identifier_are_not_user_visible() -> None:
    result = _resolve(["SECURITY_INCIDENT"])
    visible = render_failure_guidance(result)
    assert "SECURITY_INCIDENT" not in visible
    assert "ISOLATE_AND_PRESERVE_EVIDENCE" not in visible


def test_resolution_provenance_detects_tampering() -> None:
    result = _resolve(["QUOTE_STALE"])
    result["next_action"]["owner_guidance_zh"] += "篡改"
    assert "resolution artifact hash differs" in _validate(result)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("remove_reason", "reason catalog and next-action matrix differ"),
        ("duplicate_reason", "duplicate reason code"),
        ("remove_mapping", "reason catalog and next-action matrix differ"),
        ("duplicate_mapping", "reason mappings are not uniquely ordered"),
        ("duplicate_priority", "reason mappings are not uniquely ordered"),
        ("unknown_action", "selected reason does not have exactly one action"),
        ("two_actions", "selected reason does not have exactly one action"),
    ],
)
def test_catalog_and_matrix_mutations_fail_closed(mutation: str, expected_error: str) -> None:
    catalog = copy.deepcopy(CATALOG)
    matrix = copy.deepcopy(MATRIX)
    if mutation == "remove_reason":
        catalog["reason_codes"].pop()
    elif mutation == "duplicate_reason":
        catalog["reason_codes"].append(copy.deepcopy(catalog["reason_codes"][0]))
    elif mutation == "remove_mapping":
        matrix["reason_code_mappings"].pop()
    elif mutation == "duplicate_mapping":
        matrix["reason_code_mappings"].append(copy.deepcopy(matrix["reason_code_mappings"][0]))
    elif mutation == "duplicate_priority":
        matrix["reason_code_mappings"][1]["priority"] = matrix["reason_code_mappings"][0]["priority"]
    elif mutation == "unknown_action":
        matrix["reason_code_mappings"][0]["next_action_id"] = "MISSING"
    elif mutation == "two_actions":
        matrix["reason_code_mappings"][0]["action_count"] = 2
    with pytest.raises(FailureGuidanceError, match=expected_error):
        resolve_failure_states(
            ["UNKNOWN_FAILURE_STATE"],
            reason_catalog=catalog,
            next_action_matrix=matrix,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("external_effect_performed", True),
        ("may_submit_order", True),
        ("may_retry_order", True),
        ("may_spend_cash", True),
        ("may_relax_evidence_numeric_risk_or_safety_gate", True),
        ("irreversible", True),
        ("incremental_cash_cost_aud", "0.01"),
    ],
)
def test_unsafe_action_mutation_is_rejected_by_oracle_clone(
    tmp_path: Path,
    field: str,
    replacement,
) -> None:
    project = _clone_project(tmp_path)
    matrix = strict_json_load(project / NEXT_ACTION_MATRIX_PATH)
    matrix["actions"][0][field] = replacement
    _write_json(project / NEXT_ACTION_MATRIX_PATH, matrix)
    _failed(evaluate_contract(project), "S03P03-HASH-NEXT_ACTION_MATRIX-JSON")


@pytest.mark.parametrize(
    ("relative", "check_id"),
    [
        (REASON_CODES_PATH, "S03P03-HASH-REASON_CODES_ZH-JSON"),
        (NEXT_ACTION_MATRIX_PATH, "S03P03-HASH-NEXT_ACTION_MATRIX-JSON"),
        (ORACLE_FIXTURE_PATH, "S03P03-HASH-MACHINE-TESTS-FIXTURES-S03_P03-JSON"),
        (Path("advice_card_schema.json"), "S03P03-HASH-ADVICE_CARD_SCHEMA-JSON"),
        (Path("machine/evidence/EVD-S03-P02.json"), "S03P03-HASH-MACHINE-EVIDENCE-EVD-S03-P02-JSON"),
    ],
)
def test_oracle_rejects_tampered_phase_or_prerequisite_artifact(
    tmp_path: Path,
    relative: Path,
    check_id: str,
) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_bytes(path.read_bytes() + b"\n")
    _failed(evaluate_contract(project), check_id)


def test_oracle_rejects_its_own_source_tampering(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "abd_acceptance/reason_next_action.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S03P03-ORACLE-SELF-INTEGRITY")


def test_evidence_build_is_deterministic_without_runtime_reports() -> None:
    first_evidence, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second_evidence, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first_evidence == second_evidence
    assert first_rollback == second_rollback
    assert first_evidence["status"] == "PASS"
    assert first_evidence["decision"] == FIXTURE["expected_decision"]
    assert first_evidence["next"] == "S03/P04_READY_NOT_STARTED"
    assert first_evidence["external_effect_boundary"] == FIXTURE["expected_external_effect_boundary"]
    assert first_evidence["p02_delivery_prerequisite"]["evidence_sha256"] == PINNED_BASELINE_HASHES["machine/evidence/EVD-S03-P02.json"]


def test_rollback_restores_every_signed_input_without_external_effect() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"]
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())


def test_existing_evidence_verifier_is_fail_closed_when_absent_or_current() -> None:
    result = verify_existing_phase_evidence(ROOT, verify_git_history=True)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["next"] == "S03/P04_READY_NOT_STARTED"
    else:
        assert result["status"] == "FAIL"
        assert "S03P03-RECEIPT-EVIDENCE-STRICT-JSON" in result["summary"]["failed_check_ids"]


def test_external_effect_boundary_is_all_false_and_zero_cash() -> None:
    boundary = FIXTURE["expected_external_effect_boundary"]
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    assert all(
        value is False
        for key, value in boundary.items()
        if key != "incremental_cash_spent_aud"
    )


def test_catalog_and_matrix_do_not_claim_runtime_or_human_usability() -> None:
    assert "不代表网页" in CATALOG["non_claims"][0]
    assert "不执行模型" in CATALOG["non_claims"][1]
    assert "不执行任何外部" in MATRIX["non_claims"][0]
    assert FIXTURE["expected_release_status"] == "NOT_READY_S03_P04_AND_STAGE_REVIEW_REQUIRED"


def test_p04_controlled_build_is_exact_and_stage_review_is_not_started() -> None:
    result = evaluate_contract(ROOT)
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["S03P03-SUCCESSOR-ARTIFACTS-NOT-STARTED"]["passed"] is True
    assert checks["S03P03-SUCCESSOR-ARTIFACTS-NOT-STARTED"]["detail"]["mode"] in {
        "P04_CONTROLLED_BUILD",
        "P04_SIGNED_DELIVERY",
    }
    assert checks["S03P03-SUCCESSOR-ARTIFACTS-NOT-STARTED"]["detail"]["later"] == []
    assert checks["S03P03-SUCCESSOR-INDEX-PLANNED"]["passed"] is True


def test_current_taskpack_report_matches_exact_external_gate_shape() -> None:
    assert _pack_report_passes(strict_json_load(ROOT / PACK_REPORT_PATH))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        ("status", "FAIL"),
        ("summary.checks", 48),
        ("summary.passed", 48),
        ("summary.failed", 1),
    ],
)
def test_taskpack_report_gate_fails_closed_on_mutation(path: str, replacement) -> None:
    report = strict_json_load(ROOT / PACK_REPORT_PATH)
    current = report
    parts = path.split(".")
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = replacement
    assert _pack_report_passes(report) is False


def test_current_paid_dependency_scan_matches_exact_external_gate_shape() -> None:
    assert _paid_dependency_scan_passes((ROOT / SCAN_REPORT_PATH).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "required_line",
    [
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    ],
)
def test_paid_dependency_scan_gate_fails_when_required_line_is_missing(required_line: str) -> None:
    lines = (ROOT / SCAN_REPORT_PATH).read_text(encoding="utf-8").splitlines()
    assert required_line in lines
    changed = "\n".join(line for line in lines if line != required_line) + "\n"
    assert _paid_dependency_scan_passes(changed) is False
