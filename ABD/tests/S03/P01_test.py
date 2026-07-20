from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.stage2_delivery import (
    PINNED_RECEIPT_SHA256,
    RECEIPT_PATH,
    verify_stage2_delivery,
)
from abd_acceptance.terminology_governance import (
    ALLOWED_NUMERIC_DELTA_STRINGS,
    EVIDENCE_PATH,
    FIXTURE_PATH,
    FORBIDDEN_PATH,
    GLOSSARY_PATH,
    LEGACY_GLOSSARY_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    SUCCESSOR_EVOLVED_PHASE_HASHES,
    ROLLBACK_EVIDENCE_PATH,
    TEST_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_ui_gate,
    scan_ui_text,
    verify_existing_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
GLOSSARY = strict_json_load(ROOT / GLOSSARY_PATH)
POLICY = strict_json_load(ROOT / FORBIDDEN_PATH)


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


def _entry(term_id: str, glossary=GLOSSARY):
    return next(row for row in glossary["entries"] if row["term_id"] == term_id)


def _rule(term_id: str, policy=POLICY):
    return next(row for row in policy["rules"] if row["term_id"] == term_id)


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_terminology_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["decision"] == "ZH_TERMINOLOGY_AND_UI_EXPOSURE_POLICY_FROZEN"
    assert result["user_interface_status"] == "CONTRACT_ONLY_NOT_IMPLEMENTED_OR_DEPLOYED"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["release_status"] == "NOT_READY_S03_P02_TO_P04_AND_STAGE_REVIEW_REQUIRED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_stage2_github_delivery_is_exact_start_prerequisite() -> None:
    result = verify_stage2_delivery(ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S02_DELIVERED_S03_MAY_START"
    assert result["hashes"][RECEIPT_PATH.as_posix()] == PINNED_RECEIPT_SHA256
    assert result["next"] == "S03/P01_READY_NOT_STARTED"
    assert result["external_network_used_by_verifier"] is False


@pytest.mark.parametrize("relative", [GLOSSARY_PATH, FORBIDDEN_PATH, FIXTURE_PATH, TEST_PATH])
def test_frozen_phase_artifact_hashes_match_oracle_pins(relative: Path) -> None:
    accepted = {PINNED_PHASE_HASHES[relative.as_posix()]}
    if relative.as_posix() in SUCCESSOR_EVOLVED_PHASE_HASHES:
        accepted.add(SUCCESSOR_EVOLVED_PHASE_HASHES[relative.as_posix()])
    assert sha256_file(ROOT / relative) in accepted


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_frozen_baseline_and_delivery_hashes_match_oracle_pins(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


@pytest.mark.parametrize("term_id", FIXTURE["expected_term_ids"])
def test_every_necessary_term_has_chinese_definition_and_machine_mapping(term_id: str) -> None:
    entry = _entry(term_id)
    assert entry["zh_name"]
    assert entry["definition_zh"]
    assert entry["preferred_ui_label"]
    assert entry["first_use_display"]
    assert entry["machine_aliases"]
    assert entry["machine_mappings"]
    assert entry["ui_policy"] in GLOSSARY["ui_policy_values"]
    assert any("\u4e00" <= char <= "\u9fff" for char in entry["zh_name"])
    assert any("\u4e00" <= char <= "\u9fff" for char in entry["definition_zh"])


@pytest.mark.parametrize("token", FIXTURE["legacy_machine_tokens"])
def test_every_legacy_glossary_definition_is_preserved_exactly(token: str) -> None:
    legacy = strict_json_load(ROOT / LEGACY_GLOSSARY_PATH)
    entries = [row for row in GLOSSARY["entries"] if row["machine_token"] == token]
    assert len(entries) == 1
    entry = entries[0]
    assert f'{entry["zh_name"]}：{entry["definition_zh"]}' == legacy[token]
    assert entry["machine_mappings"] == [
        {"source": LEGACY_GLOSSARY_PATH.as_posix(), "identifier": token, "match_mode": "LEGACY_GLOSSARY_KEY"}
    ]


@pytest.mark.parametrize("term_id", FIXTURE["expected_term_ids"])
def test_every_glossary_term_has_one_closed_ui_rule(term_id: str) -> None:
    entry = _entry(term_id)
    rules = [row for row in POLICY["rules"] if row["term_id"] == term_id]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["raw_tokens"] == [entry["machine_token"]]
    assert rule["reason_code_on_failure"] in POLICY["reason_codes"]
    if entry["ui_policy"] in {"ZH_WITH_OPTIONAL_EXPLAINED_TOKEN", "BRAND_WITH_ZH_CONTEXT"}:
        assert rule["allowed_ui_forms"] == [entry["first_use_display"]]
    else:
        assert rule["allowed_ui_forms"] == []


@pytest.mark.parametrize("sample", FIXTURE["allowed_ui_samples"], ids=lambda row: row["id"])
def test_allowed_daily_ui_samples_have_no_unexplained_term(sample: dict) -> None:
    assert scan_ui_text(sample["text"], sample["surface_kind"], GLOSSARY, POLICY) == []


@pytest.mark.parametrize("sample", FIXTURE["blocked_ui_samples"], ids=lambda row: row["id"])
def test_unexplained_or_machine_ui_samples_fail_closed(sample: dict) -> None:
    violations = scan_ui_text(sample["text"], sample["surface_kind"], GLOSSARY, POLICY)
    assert violations
    assert sample["reason_code"] in [row["reason_code"] for row in violations]


@pytest.mark.parametrize("vector", FIXTURE["boundary_vectors"], ids=lambda row: row["id"])
def test_numeric_boundary_and_adverse_tick_never_relax_language_gate(vector: dict) -> None:
    assert resolve_ui_gate(
        text=vector["text"],
        surface_kind="ADVICE_CARD",
        glossary=GLOSSARY,
        policy=POLICY,
        numeric_delta=vector["numeric_delta"],
        adverse_odds_tick=vector["adverse_odds_tick"],
    ) == vector["expected"]


def test_unknown_rendered_surface_fails_closed_but_machine_record_does_not() -> None:
    unknown = scan_ui_text("全部中文", "UNREGISTERED_SURFACE", GLOSSARY, POLICY)
    assert unknown == [{"reason_code": "UI_SURFACE_UNKNOWN", "token": "UNREGISTERED_SURFACE", "term_id": None}]
    machine = scan_ui_text("REQ-S03-P01 API ttl_seconds", "NON_RENDERED_MACHINE_RECORD", GLOSSARY, POLICY)
    assert machine == []


@pytest.mark.parametrize("numeric_delta", ["0.0000", "0.00010", "1e-4", "0.1", "NaN"])
def test_non_frozen_numeric_boundary_representation_is_rejected(numeric_delta: str) -> None:
    with pytest.raises(ValueError):
        resolve_ui_gate(
            text="纯中文", surface_kind="DAILY_HOME", glossary=GLOSSARY, policy=POLICY,
            numeric_delta=numeric_delta, adverse_odds_tick=False,
        )


def test_boundary_inputs_reject_wrong_types() -> None:
    with pytest.raises(TypeError):
        resolve_ui_gate(
            text="纯中文", surface_kind="DAILY_HOME", glossary=GLOSSARY, policy=POLICY,
            numeric_delta=0, adverse_odds_tick=False,
        )
    with pytest.raises(TypeError):
        resolve_ui_gate(
            text="纯中文", surface_kind="DAILY_HOME", glossary=GLOSSARY, policy=POLICY,
            numeric_delta="0", adverse_odds_tick=1,
        )


def test_policy_counts_and_generic_patterns_are_exact() -> None:
    assert Counter(row["ui_policy"] for row in GLOSSARY["entries"]) == FIXTURE["expected_ui_policy_counts"]
    assert Counter(row["action"] for row in POLICY["rules"]) == FIXTURE["expected_action_counts"]
    assert [row["pattern_id"] for row in POLICY["generic_forbidden_patterns"]] == FIXTURE["expected_generic_pattern_ids"]
    assert POLICY["included_surface_kinds"] == FIXTURE["expected_surface_kinds"]


def test_contract_only_scope_and_external_effect_boundary_are_explicit() -> None:
    scope = GLOSSARY["contract_scope"]
    assert scope["status"] == "TERMINOLOGY_CONTRACT_FROZEN_UI_NOT_IMPLEMENTED"
    assert len(scope["non_claims"]) == 4
    assert POLICY["external_effect_boundary"] == FIXTURE["expected_external_effect_boundary"]
    assert POLICY["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"
    assert POLICY["external_effect_boundary"]["real_order_submitted"] is False
    assert POLICY["external_effect_boundary"]["return_or_roi_verified"] is False


def test_rollback_drill_restores_all_signed_terminology_inputs() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["production_state_changed"] is False
    assert rollback["external_state_changed"] is False
    assert len(rollback["artifacts"]) == 5
    assert all(row["status"] == "PASS" for row in rollback["artifacts"].values())


def test_evidence_build_is_deterministic_without_runtime_reports() -> None:
    first_evidence, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second_evidence, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first_evidence == second_evidence
    assert first_rollback == second_rollback
    assert first_evidence["status"] == "PASS"
    assert first_evidence["next"] == "S03/P02_READY_NOT_STARTED"
    assert first_evidence["stage2_delivery_prerequisite"]["receipt_sha256"] == PINNED_RECEIPT_SHA256
    assert first_evidence["external_effect_boundary"] == FIXTURE["expected_external_effect_boundary"]
    assert first_evidence["decision_sha256"]


def test_existing_evidence_verifier_is_fail_closed_when_evidence_absent_or_current() -> None:
    result = verify_existing_phase_evidence(ROOT, verify_git_history=True)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["next"] == "S03/P02_READY_NOT_STARTED"
    else:
        assert result["status"] == "FAIL"
        assert "S03P01-RECEIPT-EVIDENCE-STRICT-JSON" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("missing_term", "S03P01-GLOSSARY-TERM-SET-EXACT"),
        ("duplicate_term", "S03P01-GLOSSARY-TERM-SET-EXACT"),
        ("unsafe_mapping", "S03P01-GLOSSARY-MAPPING-TERM-TTL"),
        ("missing_mapping", "S03P01-GLOSSARY-MAPPING-TERM-TTL"),
        ("legacy_definition_drift", "S03P01-LEGACY-GLOSSARY-15-OF-15-PRESERVED"),
        ("bad_first_use", "S03P01-GLOSSARY-ENTRY-TERM-EV"),
        ("missing_rule", "S03P01-POLICY-TERM-SET-EXACT"),
        ("machine_term_allowed", "S03P01-POLICY-RULE-TERM-API"),
        ("missing_generic_pattern", "S03P01-POLICY-GENERIC-PATTERNS"),
        ("wide_machine_exemption", "S03P01-POLICY-MACHINE-EXEMPTION-NON-RENDERED-ONLY"),
        ("external_effect", "S03P01-POLICY-EXTERNAL-EFFECT-BOUNDARY"),
        ("absolute_local_path", "S03P01-GLOSSARY-PORTABLE-NO-LOCAL-PATH"),
        ("p02_started", "S03P01-SUCCESSOR-ARTIFACTS-NOT-STARTED"),
        ("p02_index_state_flip", "S03P01-SUCCESSOR-INDEX-PLANNED"),
        ("receipt_tamper", "S03P01-S02-DELIVERY-PREREQUISITE"),
        ("bankroll_drift", "S03P01-AUD300-AUD0-TARGET-BASELINE"),
        ("positive_cash", "S03P01-COSTS-ZERO-INCREMENTAL-CASH"),
    ],
)
def test_contract_mutations_fail_closed(tmp_path: Path, mutation: str, expected_check: str) -> None:
    project = _clone_project(tmp_path)
    glossary = strict_json_load(project / GLOSSARY_PATH)
    policy = strict_json_load(project / FORBIDDEN_PATH)
    if mutation == "missing_term":
        glossary["entries"].pop()
        _write_json(project / GLOSSARY_PATH, glossary)
    elif mutation == "duplicate_term":
        glossary["entries"].append(dict(glossary["entries"][0]))
        _write_json(project / GLOSSARY_PATH, glossary)
    elif mutation == "unsafe_mapping":
        glossary["entries"][1]["machine_mappings"][0]["source"] = "../../secret.json"
        _write_json(project / GLOSSARY_PATH, glossary)
    elif mutation == "missing_mapping":
        glossary["entries"][1]["machine_mappings"][0]["source"] = "missing.json"
        _write_json(project / GLOSSARY_PATH, glossary)
    elif mutation == "legacy_definition_drift":
        glossary["entries"][1]["definition_zh"] += "漂移"
        glossary["entries"][1]["first_use_display"] = f'{glossary["entries"][1]["zh_name"]}（TTL）'
        _write_json(project / GLOSSARY_PATH, glossary)
    elif mutation == "bad_first_use":
        _entry("TERM-EV", glossary)["first_use_display"] = "EV"
        _write_json(project / GLOSSARY_PATH, glossary)
    elif mutation == "missing_rule":
        policy["rules"].pop()
        _write_json(project / FORBIDDEN_PATH, policy)
    elif mutation == "machine_term_allowed":
        rule = _rule("TERM-API", policy)
        rule["action"] = "ALLOW_ONLY_WITH_EXACT_EXPLANATION"
        rule["allowed_ui_forms"] = ["程序接口（API）"]
        rule["reason_code_on_failure"] = "UI_TERM_UNEXPLAINED"
        _write_json(project / FORBIDDEN_PATH, policy)
    elif mutation == "missing_generic_pattern":
        policy["generic_forbidden_patterns"].pop()
        _write_json(project / FORBIDDEN_PATH, policy)
    elif mutation == "wide_machine_exemption":
        policy["non_rendered_machine_exemption"]["rendered_content_must_reenter_ui_gate"] = False
        _write_json(project / FORBIDDEN_PATH, policy)
    elif mutation == "external_effect":
        policy["external_effect_boundary"]["network_accessed"] = True
        _write_json(project / FORBIDDEN_PATH, policy)
    elif mutation == "absolute_local_path":
        glossary["contract_scope"]["non_claims"][0] += " /" + "Users/example/private"
        _write_json(project / GLOSSARY_PATH, glossary)
    elif mutation == "p02_started":
        _write_json(project / "advice_card_schema.json", {"status": "STARTED"})
    elif mutation == "p02_index_state_flip":
        index = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line]
        row = next(row for row in rows if row["id"] == "INDEX-AC-S03-P02")
        row["status"] = "PASS" if row.get("status") == "PLANNED" else "PLANNED"
        index.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    elif mutation == "receipt_tamper":
        receipt = strict_json_load(project / RECEIPT_PATH)
        receipt["delivery_status"] = "UNVERIFIED"
        _write_json(project / RECEIPT_PATH, receipt)
    elif mutation == "bankroll_drift":
        canonical = strict_json_load(project / "machine/facts/canonical_facts.json")
        canonical["product"]["initial_bankroll_aud"] = "301.00"
        _write_json(project / "machine/facts/canonical_facts.json", canonical)
    elif mutation == "positive_cash":
        costs = strict_json_load(project / "machine/facts/costs.json")
        costs["incremental_cash_budget"]["likely"] = "1.00"
        _write_json(project / "machine/facts/costs.json", costs)
    result = evaluate_contract(project)
    _failed(result, expected_check)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("receipt_status", "S02DELIVERY-RECEIPT-SHAPE"),
        ("receipt_checks", "S02DELIVERY-MAIN-CHECKS-EXACT"),
        ("receipt_cost", "S02DELIVERY-ZERO-CASH-DELIVERY-GATE"),
        ("receipt_effect", "S02DELIVERY-EXTERNAL-EFFECTS-EXACT"),
        ("stage_evidence", "S02DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY"),
        ("rollback", "S02DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY"),
        ("index", "S02DELIVERY-EVIDENCE-INDEX-BINDING"),
    ],
)
def test_stage2_delivery_mutations_block_s03(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    receipt = strict_json_load(project / RECEIPT_PATH)
    if mutation == "receipt_status":
        receipt["delivery_status"] = "UNVERIFIED"
        _write_json(project / RECEIPT_PATH, receipt)
    elif mutation == "receipt_checks":
        receipt["main_checks"][0]["conclusion"] = "failure"
        _write_json(project / RECEIPT_PATH, receipt)
    elif mutation == "receipt_cost":
        receipt["delivery_cost_gate"]["incremental_cash_spent_aud"] = "0.01"
        _write_json(project / RECEIPT_PATH, receipt)
    elif mutation == "receipt_effect":
        receipt["external_effects"]["production_deployment_claimed"] = True
        _write_json(project / RECEIPT_PATH, receipt)
    elif mutation == "stage_evidence":
        evidence = strict_json_load(project / "machine/evidence/EVD-S02-STAGE-REVIEW.json")
        evidence["status"] = "FAIL"
        _write_json(project / "machine/evidence/EVD-S02-STAGE-REVIEW.json", evidence)
    elif mutation == "rollback":
        rollback = strict_json_load(project / "machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json")
        rollback["external_state_changed"] = True
        _write_json(project / "machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json", rollback)
    elif mutation == "index":
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        next(row for row in rows if row["id"] == "INDEX-S02-STAGE-REVIEW")["status"] = "FAIL"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    result = verify_stage2_delivery(project, verify_git_history=False)
    _failed(result, expected)


def test_malformed_inputs_fail_closed_without_crashing(tmp_path: Path) -> None:
    for relative, check_id in [
        (GLOSSARY_PATH, "S03P01-GLOSSARY-STRICT-JSON"),
        (FORBIDDEN_PATH, "S03P01-POLICY-STRICT-JSON"),
        (FIXTURE_PATH, "S03P01-FIXTURE-STRICT-JSON"),
    ]:
        project = _clone_project(tmp_path / relative.stem)
        (project / relative).write_text('{"broken":', encoding="utf-8")
        result = evaluate_contract(project)
        _failed(result, check_id)


def test_s03_p02_is_absent_or_an_exact_controlled_successor() -> None:
    p02_paths = [
        "advice_card_schema.json",
        "advice_card_fixtures.json",
        "tests/S03/P02_test.py",
        "machine/tests/fixtures/S03_P02.json",
        "machine/evidence/EVD-S03-P02.json",
        "machine/evidence/EVD-S03-P02_rollback.json",
    ]
    later_paths = [
        "reason_codes_zh.json",
        "next_action_matrix.json",
        "machine/facts/stage3_review_contract.json",
        "tests/S03/stage_review_test.py",
    ]
    present = [relative for relative in p02_paths if (ROOT / relative).exists()]
    assert all(not (ROOT / relative).exists() for relative in later_paths)
    index_rows = [json.loads(line) for line in (ROOT / "machine/evidence/evidence_index.jsonl").read_text(encoding="utf-8").splitlines() if line]
    p02 = [row for row in index_rows if row["id"] == "INDEX-AC-S03-P02"]
    assert len(p02) == 1
    if not present:
        assert p02[0]["status"] == "PLANNED"
        return
    in_progress = set(p02_paths[:4])
    assert set(present) == in_progress or set(present) == set(p02_paths)
    if set(present) == in_progress:
        from abd_acceptance.advice_card import PINNED_PHASE_HASHES as P02_PINNED_PHASE_HASHES

        assert p02[0]["status"] == "PLANNED"
        assert all(sha256_file(ROOT / relative) == expected for relative, expected in P02_PINNED_PHASE_HASHES.items())
    else:
        from abd_acceptance.advice_card import verify_existing_phase_evidence as verify_p02_evidence

        successor = verify_p02_evidence(ROOT, verify_git_history=True)
        assert successor["status"] == "PASS", successor
        assert successor["next"] == "S03/P03_READY_NOT_STARTED"


def test_no_artifact_contains_secret_or_absolute_local_path() -> None:
    rendered = json.dumps({"glossary": GLOSSARY, "policy": POLICY, "fixture": FIXTURE}, ensure_ascii=False, sort_keys=True)
    for marker in [
        "/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\",
        "BEGIN " + "PRIVATE KEY", "s" + "k-", "gh" + "p_",
    ]:
        assert marker not in rendered


def test_fixture_boundary_set_is_exact_and_no_float_is_serialized() -> None:
    assert set(FIXTURE["allowed_numeric_delta_strings"]) == ALLOWED_NUMERIC_DELTA_STRINGS
    assert all(isinstance(row["numeric_delta"], str) for row in FIXTURE["boundary_vectors"])
    assert ".0001" in json.dumps(FIXTURE, ensure_ascii=False)
