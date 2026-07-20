from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from abd_acceptance.advice_card import (
    ALLOWED_NUMERIC_DELTA_STRINGS,
    CONTRACT_ID,
    DISPLAY_ORDER,
    EVIDENCE_PATH,
    FIXTURES_PATH,
    INVALIDATION_CONDITIONS_ZH,
    MODEL_CARD_PATH,
    ORACLE_FIXTURE_PATH,
    PACK_REPORT_PATH,
    PARAMETERS_PATH,
    P01_EVIDENCE_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    PRIMARY_ANSWER_KEYS,
    REQUIRED_RECOMMENDATION_GATES,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    SCHEMA_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    CardContractError,
    _pack_report_passes,
    _paid_dependency_scan_passes,
    _structural_self_hash,
    build_advice_card,
    build_evidence,
    contrast_ratio,
    evaluate_contract as _evaluate_contract,
    extract_primary_answers,
    perform_rollback_drill,
    render_visible_text,
    safe_build_advice_card,
    validate_card,
    validate_daily_card_set,
    verify_existing_phase_evidence,
)
from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.terminology_governance import (
    scan_ui_text,
    verify_existing_phase_evidence as verify_p01_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = strict_json_load(ROOT / SCHEMA_PATH)
FIXTURES = strict_json_load(ROOT / FIXTURES_PATH)
ORACLE_FIXTURE = strict_json_load(ROOT / ORACLE_FIXTURE_PATH)
GLOSSARY = strict_json_load(ROOT / "glossary_zh.json")
POLICY = strict_json_load(ROOT / "forbidden_ui_terms.json")
PARAMETERS_SHA = sha256_file(ROOT / PARAMETERS_PATH)
MODEL_SHA = sha256_file(ROOT / MODEL_CARD_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def _build(decision=None, root: Path = ROOT):
    schema = strict_json_load(root / SCHEMA_PATH)
    glossary = strict_json_load(root / "glossary_zh.json")
    policy = strict_json_load(root / "forbidden_ui_terms.json")
    if decision is None:
        decision = strict_json_load(root / FIXTURES_PATH)["base_recommendation_input"]
    return build_advice_card(
        decision,
        schema=schema,
        glossary=glossary,
        policy=policy,
        parameters_sha256=sha256_file(root / PARAMETERS_PATH),
        model_sha256=sha256_file(root / MODEL_CARD_PATH),
    )


def _safe(decision):
    return safe_build_advice_card(
        decision,
        schema=SCHEMA,
        glossary=GLOSSARY,
        policy=POLICY,
        parameters_sha256=PARAMETERS_SHA,
        model_sha256=MODEL_SHA,
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
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _set_path(value: dict, dotted: str, replacement) -> None:
    current = value
    parts = dotted.split(".")
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = replacement


def _boundary_input(vector: dict) -> dict:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision.update(vector["overrides"])
    decision["vector_id"] = "BOUNDARY-" + vector["id"]
    return decision


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_advice_card_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURES["expected_oracle_check_minimum"]
    assert result["decision"] == ORACLE_FIXTURE["expected_decision"]
    assert result["phase_status"] == ORACLE_FIXTURE["expected_phase_status"]
    assert result["user_interface_status"] == ORACLE_FIXTURE["expected_ui_status"]
    assert result["human_ten_second_usability_status"] == ORACLE_FIXTURE["expected_human_timing_status"]
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["release_status"] == ORACLE_FIXTURE["expected_release_status"]
    assert result["next"] == ORACLE_FIXTURE["expected_next"]
    ids = [row["id"] for row in result["checks"]]
    assert len(ids) == len(set(ids))


def test_p01_delivery_is_exact_start_prerequisite() -> None:
    result = verify_p01_evidence(ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S03_P01_EVIDENCE_VERIFIED"
    assert result["next"] == "S03/P02_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_frozen_phase_artifact_hashes_match_oracle_pins(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_frozen_baseline_hashes_match_oracle_pins(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


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
def test_taskpack_report_gate_fails_closed_on_summary_mutation(path: str, replacement) -> None:
    report = strict_json_load(ROOT / PACK_REPORT_PATH)
    _set_path(report, path, replacement)
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
def test_paid_dependency_scan_gate_fails_closed_when_required_line_is_missing(required_line: str) -> None:
    lines = (ROOT / SCAN_REPORT_PATH).read_text(encoding="utf-8").splitlines()
    assert required_line in lines
    assert _paid_dependency_scan_passes("\n".join(line for line in lines if line != required_line) + "\n") is False


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("field", SCHEMA["required"])
def test_every_root_field_is_declared_and_required(field: str) -> None:
    assert field in SCHEMA["properties"]
    assert SCHEMA["additionalProperties"] is False


@pytest.mark.parametrize("field", SCHEMA["properties"]["action"]["required"])
def test_every_action_field_is_declared_and_required(field: str) -> None:
    assert field in SCHEMA["properties"]["action"]["properties"]
    assert SCHEMA["properties"]["action"]["additionalProperties"] is False


@pytest.mark.parametrize(("position", "section"), list(enumerate(DISPLAY_ORDER, start=1)))
def test_display_order_is_exact_and_action_is_second(position: int, section: str) -> None:
    assert SCHEMA["x-abd-display-contract"]["section_order"][position - 1] == section
    assert FIXTURES["expected_display_order"][position - 1] == section
    if section == "action":
        assert position == 2


@pytest.mark.parametrize(
    ("group", "name"),
    [
        ("status_palette", "RECOMMENDATION"),
        ("status_palette", "NO_RECOMMENDATION"),
        ("countdown_palette", "ACTIVE"),
        ("countdown_palette", "EXPIRING"),
        ("countdown_palette", "EXPIRED"),
    ],
)
def test_every_frozen_color_pair_has_text_contrast(group: str, name: str) -> None:
    colors = SCHEMA["x-abd-display-contract"][group][name]
    assert contrast_ratio(colors["background"], colors["foreground"]) >= 4.5
    assert SCHEMA["x-abd-display-contract"]["color_is_only_signal"] is False


@pytest.mark.parametrize(("position", "question_id"), list(enumerate(FIXTURES["expected_primary_question_ids"])))
def test_four_primary_questions_have_unique_direct_pointers(position: int, question_id: str) -> None:
    question = SCHEMA["x-abd-contract"]["primary_questions"][position]
    assert question["id"] == question_id
    assert question["answer_pointer"].startswith("/action/")
    assert "_zh" in question["answer_pointer"]


@pytest.mark.parametrize("field", SCHEMA["required"])
def test_base_recommendation_contains_every_frozen_root_field(field: str) -> None:
    card = _build()
    assert field in card
    assert validate_card(card, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY) == []


@pytest.mark.parametrize("field", SCHEMA["properties"]["action"]["required"])
def test_base_recommendation_contains_every_action_field(field: str) -> None:
    card = _build()
    assert field in card["action"]


@pytest.mark.parametrize(("answer_key", "expected"), list(ORACLE_FIXTURE["expected_primary_answers"].items()))
def test_primary_answers_are_directly_extractable(answer_key: str, expected: str) -> None:
    answers = extract_primary_answers(_build())
    assert list(answers) == PRIMARY_ANSWER_KEYS
    assert answers[answer_key] == expected


def test_recommendation_visible_text_passes_p01_chinese_gate() -> None:
    text = render_visible_text(_build(), SCHEMA)
    assert scan_ui_text(text, "ADVICE_CARD", GLOSSARY, POLICY) == []
    assert "演示平台" in text
    assert "最低可接受赔率2.050000" in text
    assert "由你自行决定" in text


@pytest.mark.parametrize("condition", INVALIDATION_CONDITIONS_ZH)
def test_every_invalidation_condition_is_visible_and_frozen(condition: str) -> None:
    card = _build()
    assert card["invalidation"]["conditions_zh"] == INVALIDATION_CONDITIONS_ZH
    assert condition in render_visible_text(card, SCHEMA)


@pytest.mark.parametrize("vector", FIXTURES["boundary_vectors"], ids=lambda row: row["id"])
def test_every_boundary_vector_is_deterministic_and_fail_closed(vector: dict) -> None:
    decision = _boundary_input(vector)
    first = _build(decision)
    second = _build(copy.deepcopy(decision))
    assert first == second
    assert first["status"] == vector["expected_status"]
    assert first["countdown"]["state"] == vector["expected_countdown_state"]
    assert first["safety"]["auto_order_enabled"] is False
    assert validate_card(first, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY) == []
    if first["status"] == "NO_RECOMMENDATION":
        assert first["action"]["stake_cents"] == 0
        assert first["action"]["action_type"] == "NO_ACTION"


@pytest.mark.parametrize("vector", FIXTURES["gate_failure_vectors"], ids=lambda row: row["id"])
def test_every_failed_upstream_gate_downgrades_to_no_recommendation(vector: dict) -> None:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision["vector_id"] = "GATE-" + vector["id"]
    decision["gates"][vector["gate"]] = False
    card = _build(decision)
    assert card["status"] == "NO_RECOMMENDATION"
    assert card["action"]["action_type"] == "NO_ACTION"
    assert card["action"]["stake_cents"] == 0
    assert card["reasons"][0]["code"] == "UPSTREAM_GATE_FAILED"
    assert validate_card(card, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY) == []


@pytest.mark.parametrize("vector", FIXTURES["malformed_input_vectors"], ids=lambda row: row["id"])
def test_every_malformed_input_is_strictly_rejected(vector: dict) -> None:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision["vector_id"] = "MALFORMED-" + vector["id"]
    decision[vector["path"]] = vector["replacement"]
    with pytest.raises((CardContractError, TypeError, ValueError)):
        _build(decision)


@pytest.mark.parametrize("vector", FIXTURES["malformed_input_vectors"], ids=lambda row: row["id"])
def test_every_malformed_input_has_a_valid_safe_no_recommendation(vector: dict) -> None:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision["vector_id"] = "MALFORMED-" + vector["id"]
    decision[vector["path"]] = vector["replacement"]
    card = _safe(decision)
    assert card["status"] == "NO_RECOMMENDATION"
    assert card["action"]["action_type"] == "NO_ACTION"
    assert card["action"]["stake_cents"] == 0
    assert card["reasons"][0]["code"] == "CARD_INPUT_INVALID"
    assert validate_card(card, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY) == []


@pytest.mark.parametrize("vector", FIXTURES["invalid_rendered_card_mutations"], ids=lambda row: row["id"])
def test_every_invalid_rendered_card_mutation_is_rejected(vector: dict) -> None:
    card = _build()
    _set_path(card, vector["path"], vector["replacement"])
    assert validate_card(card, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY)


@pytest.mark.parametrize("sequence", range(30))
def test_replay_is_stable_across_distinct_synthetic_input_ids(sequence: int) -> None:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision["vector_id"] = "REPLAY-%02d" % sequence
    first = _build(decision)
    second = _build(json.loads(json.dumps(decision, ensure_ascii=False)))
    assert first == second
    assert first["provenance"]["artifact_sha256"] == second["provenance"]["artifact_sha256"]
    assert first["card_id"] == second["card_id"]


@pytest.mark.parametrize("delta", sorted(ALLOWED_NUMERIC_DELTA_STRINGS))
def test_frozen_numeric_delta_representations_are_accepted(delta: str) -> None:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision["vector_id"] = "DELTA-" + delta
    decision["numeric_boundary_delta"] = delta
    assert _build(decision)["status"] == "RECOMMENDATION"


@pytest.mark.parametrize("delta", ["0.0000", "0.00010", "1e-4", "NaN", 0.0001, None])
def test_non_frozen_numeric_delta_representations_are_rejected(delta) -> None:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision["numeric_boundary_delta"] = delta
    with pytest.raises(CardContractError):
        _build(decision)


@pytest.mark.parametrize("field", REQUIRED_RECOMMENDATION_GATES)
def test_gate_values_reject_non_boolean_truthy_inputs(field: str) -> None:
    decision = copy.deepcopy(FIXTURES["base_recommendation_input"])
    decision["gates"][field] = 1
    with pytest.raises(CardContractError):
        _build(decision)


def test_no_recommendation_has_four_immediate_safe_answers() -> None:
    card = _build(copy.deepcopy(FIXTURES["base_no_recommendation_input"]))
    assert card["status"] == "NO_RECOMMENDATION"
    assert extract_primary_answers(card) == ORACLE_FIXTURE["expected_no_recommendation_answers"]
    assert validate_card(card, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY) == []


def test_daily_card_collection_rejects_duplicate_same_day_cards() -> None:
    first = _build()
    second = _build(copy.deepcopy(FIXTURES["base_no_recommendation_input"]))
    assert validate_daily_card_set([first]) == []
    assert validate_daily_card_set([first, second])
    assert validate_daily_card_set("not-a-list")


def test_card_schema_and_fixture_state_only_two_outcomes() -> None:
    assert SCHEMA["properties"]["status"]["enum"] == ["RECOMMENDATION", "NO_RECOMMENDATION"]
    assert SCHEMA["x-abd-contract"]["allowed_statuses"] == ["RECOMMENDATION", "NO_RECOMMENDATION"]


def test_contract_does_not_claim_human_timing_or_deployment() -> None:
    contract = SCHEMA["x-abd-contract"]
    gate = contract["ten_second_information_gate"]
    assert gate["type"] == "STRUCTURAL_SCAN_PATH_PROXY"
    assert gate["human_timing_validation"] == "DEFERRED_TO_S03_P04"
    assert "不声称真人" in gate["claim_boundary_zh"]
    assert contract["scope_status"].endswith("NOT_DEPLOYED")


def test_synthetic_fixture_cannot_be_mistaken_for_real_advice() -> None:
    assert FIXTURES["base_recommendation_input"]["synthetic_test_only"] is True
    assert "演示" in FIXTURES["base_recommendation_input"]["platform_zh"]
    assert "不代表真实市场建议" in FIXTURES["base_recommendation_input"]["reasons"][1]["detail_zh"]


def test_owner_final_action_and_no_guarantee_are_schema_constants() -> None:
    safety = SCHEMA["properties"]["safety"]["properties"]
    assert safety["auto_order_enabled"]["const"] is False
    assert safety["owner_final_action_required"]["const"] is True
    assert safety["guaranteed_return"]["const"] is False
    assert safety["target_shortfall_may_relax_gate"]["const"] is False


def test_rollback_drill_restores_all_signed_card_inputs() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == ORACLE_FIXTURE["expected_rollback_artifact_count"]
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_without_runtime_reports() -> None:
    first_evidence, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second_evidence, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first_evidence == second_evidence
    assert first_rollback == second_rollback
    assert first_evidence["status"] == "PASS"
    assert first_evidence["next"] == "S03/P03_READY_NOT_STARTED"
    assert first_evidence["external_effect_boundary"] == ORACLE_FIXTURE["expected_external_effect_boundary"]
    assert first_evidence["p01_delivery_prerequisite"]["evidence_sha256"] == PINNED_BASELINE_HASHES[P01_EVIDENCE_PATH.as_posix()]
    assert first_evidence["decision_sha256"]


def test_existing_evidence_verifier_is_fail_closed_when_absent_or_current() -> None:
    result = verify_existing_phase_evidence(ROOT, verify_git_history=True)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["next"] == "S03/P03_READY_NOT_STARTED"
    else:
        assert result["status"] == "FAIL"
        assert "S03P02-RECEIPT-EVIDENCE-STRICT-JSON" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize(
    ("relative", "check_id"),
    [
        (SCHEMA_PATH, "S03P02-HASH-ADVICE_CARD_SCHEMA-JSON"),
        (FIXTURES_PATH, "S03P02-HASH-ADVICE_CARD_FIXTURES-JSON"),
        (ORACLE_FIXTURE_PATH, "S03P02-HASH-MACHINE-TESTS-FIXTURES-S03_P02-JSON"),
        (Path("glossary_zh.json"), "S03P02-HASH-GLOSSARY_ZH-JSON"),
        (P01_EVIDENCE_PATH, "S03P02-HASH-MACHINE-EVIDENCE-EVD-S03-P01-JSON"),
    ],
)
def test_oracle_rejects_tampered_phase_or_prerequisite_artifacts(tmp_path: Path, relative: Path, check_id: str) -> None:
    clone = _clone_project(tmp_path)
    path = clone / relative
    path.write_bytes(path.read_bytes() + b"\n")
    _failed(evaluate_contract(clone), check_id)


def test_oracle_rejects_its_own_source_tampering(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "abd_acceptance/advice_card.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    _failed(evaluate_contract(clone), "S03P02-ORACLE-SELF-INTEGRITY")


def test_schema_rejects_unknown_root_and_action_fields() -> None:
    card = _build()
    card["unknown"] = "未知"
    assert validate_card(card, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY)
    card = _build()
    card["action"]["second_platform"] = "另一个平台"
    assert validate_card(card, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY)


def test_external_effect_boundary_is_all_false_and_zero_cash() -> None:
    boundary = ORACLE_FIXTURE["expected_external_effect_boundary"]
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    assert all(value is False for key, value in boundary.items() if key != "incremental_cash_spent_aud")


def test_p03_is_absent_or_an_exact_controlled_successor_and_later_work_is_not_started() -> None:
    result = evaluate_contract(ROOT)
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["S03P02-SUCCESSOR-ARTIFACTS-NOT-STARTED"]["passed"] is True
    assert checks["S03P02-SUCCESSOR-INDEX-PLANNED"]["passed"] is True
