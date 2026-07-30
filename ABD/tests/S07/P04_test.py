from __future__ import annotations

import ast
import json
import os
import shutil
from pathlib import Path

import pytest

from abd_acceptance import evidence_continuity
from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.evidence_continuity import (
    CONTRACT_ID,
    EVIDENCE_INDEX_PATH,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_FIXED_CLOCK,
    JUNIT_PATH,
    ORACLE_PATH,
    P03_EVIDENCE_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    EvidenceContinuityError,
    _check_manifest,
    _check_pins,
    _check_reports,
    _check_taskpack_continuity,
    _junit_is_normalized,
    _junit_summary,
    _strict_jsonl,
    _structural_self_hash,
    build_evidence as _build_evidence,
    evaluate_link_snapshot,
    perform_rollback_drill,
    validate_candidate_preflight as _validate_candidate_preflight,
    verify_existing_phase_evidence as _verify_existing_phase_evidence,
)
from abd_acceptance.ledger_trace import verify_existing_phase_evidence as verify_p03_evidence


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def validate_candidate_preflight(root: Path) -> dict:
    return _validate_candidate_preflight(root, verify_git_history=Path(root).resolve() == ROOT.resolve())


def build_evidence(root: Path, require_test_reports: bool = False):
    return _build_evidence(
        root,
        require_test_reports=require_test_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def verify_existing_phase_evidence(root: Path) -> dict:
    return _verify_existing_phase_evidence(root, verify_git_history=Path(root).resolve() == ROOT.resolve())


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"

    def link_or_copy(source: str, target: str) -> str:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        return target

    shutil.copytree(
        ROOT,
        destination,
        copy_function=link_or_copy,
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github", copy_function=link_or_copy)
    return destination


def _write_json(path: Path, value: object) -> None:
    path.unlink(missing_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.unlink(missing_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _case(case_id: str) -> dict:
    return next(case for case in FIXTURE["cases"] if case["case_id"] == case_id)


def test_candidate_preflight_and_contract_pass_without_generated_reports() -> None:
    preflight = validate_candidate_preflight(ROOT)
    assert preflight["status"] == "PASS", preflight
    assert preflight["next"] == FIXTURE["expected_next"]
    assert preflight["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert preflight["summary"]["failed"] == 0


def test_taskpack_scope_trace_and_continuity_contract_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    requirement = next(item for item in requirements if item["id"] == "REQ-S07-P04")
    contracts = strict_json_load(ROOT / "machine/facts/acceptance_contracts.json")
    contract = next(item for item in contracts if item["id"] == CONTRACT_ID)
    graph = strict_json_load(ROOT / "machine/facts/task_graph.json")["tasks"]
    traceability = strict_json_load(ROOT / "machine/facts/traceability_matrix.json")
    trace = next(item for item in traceability if item["requirement_id"] == "REQ-S07-P04")
    tasks = [item for item in graph if item.get("stage_id") == "S07" and item.get("phase_id") == "P04"]
    index = _strict_jsonl(ROOT / EVIDENCE_INDEX_PATH)
    index_row = next(item for item in index if item["id"] == "INDEX-AC-S07-P04")
    assert requirement["scope"] == ["evidence_index.jsonl", "traceability_matrix.json", "artifact_manifest.json"]
    assert requirement["target"] == "需求→任务→测试→证据→制品无孤儿。"
    assert contract["pass_gate"] == requirement["target"]
    assert contract["oracle"]["command"] == "python -m abd_acceptance --contract AC-S07-P04 --evidence machine/evidence"
    assert [row["id"] for row in contract["tests"]] == ["TEST-S07-P04", "TEST-S07-P04-BOUNDARY", "TEST-S07-P04-REPLAY"]
    assert [item["id"] for item in tasks] == ["T-S07-P04-01", "T-S07-P04-02", "T-S07-P04-03"]
    assert trace["evidence_id"] == "EVD-S07-P04"
    assert trace["artifact_ids"] == ["ART-S07-P04-01", "ART-S07-P04-02", "ART-S07-P04-03"]
    assert index_row["status"] in {"PLANNED", "PASS"}


def test_phase_artifact_paths_remain_inside_the_taskpack_scope() -> None:
    from abd_acceptance.evidence_continuity import PHASE_ARTIFACT_PATHS

    assert [path.as_posix() for path in PHASE_ARTIFACT_PATHS.values()] == [
        "machine/evidence/evidence_index.jsonl",
        "machine/facts/traceability_matrix.json",
        "machine/evidence/artifact_manifest.json",
    ]
    assert all(path.is_relative_to(Path("machine")) for path in PHASE_ARTIFACT_PATHS.values())


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_fixture_is_production_equivalent_and_predecessor_is_pinned() -> None:
    assert FIXTURE["schema_version"] == "1.0.0"
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["stage_id"] == "S07"
    assert FIXTURE["phase_id"] == "P04"
    assert FIXTURE["fixed_clock"] == "2026-07-30T00:00:00+10:00"
    assert FIXTURE["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert FIXTURE["expected_counts"] == {"requirements": 80, "contracts": 80, "tasks": 240, "traceability": 80, "index": 91}
    assert FIXTURE["predecessor"]["contract_id"] == "AC-S07-P03"
    assert FIXTURE["predecessor"]["evidence_sha256"] == sha256_file(ROOT / P03_EVIDENCE_PATH)


@pytest.mark.parametrize("case_id", [case["case_id"] for case in FIXTURE["cases"]])
def test_frozen_positive_boundary_negative_and_fault_cases_are_exact(case_id: str) -> None:
    case = _case(case_id)
    result = evaluate_link_snapshot(case["snapshot"], case["coverage"])
    assert result["status"] == case["expected"]["status"]
    assert result["reason_codes"] == case["expected"]["reason_codes"]
    assert result["external_network_used"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_time_soak_waited"] is False
    if case_id == "POSITIVE_EXACT_CHAIN":
        assert result["output_sha256"] == FIXTURE["expected_positive_output_sha256"]


@pytest.mark.parametrize(
    ("snapshot", "coverage"),
    [
        ({}, "1.0000"),
        ({"orphans": []}, "1.0000"),
        ({"orphans": {"tasks": "not-a-list"}}, "1.0000"),
        ({"orphans": {"tasks": [1]}}, "1.0000"),
        ({"orphans": {"tasks": []}}, "1"),
        ({"orphans": {"tasks": []}}, "1.00001"),
    ],
)
def test_malformed_snapshots_and_noncanonical_coverage_fail_closed(snapshot: dict, coverage: str) -> None:
    with pytest.raises(EvidenceContinuityError):
        evaluate_link_snapshot(snapshot, coverage)


def test_one_hundred_replays_are_hash_identical_without_waiting() -> None:
    positive = _case("POSITIVE_EXACT_CHAIN")
    hashes = {evaluate_link_snapshot(positive["snapshot"], positive["coverage"])["output_sha256"] for _ in range(FIXTURE["replay_count"])}
    assert hashes == {FIXTURE["expected_positive_output_sha256"]}


def test_ten_thousand_adverse_perturbations_never_enable_an_action() -> None:
    cases = [_case(case_id) for case_id in ("BOUNDARY_COVERAGE_MINUS_0001", "BOUNDARY_COVERAGE_PLUS_0001", "NEGATIVE_ORPHAN_TASK")]
    for index in range(FIXTURE["adverse_replay_count"]):
        case = cases[index % len(cases)]
        result = evaluate_link_snapshot(case["snapshot"], case["coverage"])
        assert result["status"] == "CONTINUITY_REJECTED_NO_ACTION"
        assert result["external_network_used"] is False
        assert result["recommendation_generated"] is False
        assert result["order_submission_enabled"] is False
        assert result["real_time_soak_waited"] is False


def test_oracle_source_has_no_network_process_or_sleep_capability() -> None:
    source = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports & {"requests", "urllib", "http", "socket", "subprocess", "asyncio", "time"}
    assert not any(token in source for token in ("sleep(", "requests.", "urllib.", "socket.", "subprocess.", "http://", "https://"))


def test_rollback_drill_is_hash_only_and_never_changes_external_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_time_soak_waited"] is False


def test_candidate_fails_closed_when_phase_fixture_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    fixture = strict_json_load(root / FIXTURE_PATH)
    fixture["expected_counts"]["tasks"] = 1
    _write_json(root / FIXTURE_PATH, fixture)
    checks: list[dict] = []
    _check_pins(root, checks, {})
    assert next(check for check in checks if check["id"] == "S07P04-PIN-S07_P04-JSON")["passed"] is False


def test_p04_fails_closed_when_the_p03_predecessor_verifier_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evidence_continuity, "verify_s07_p03_evidence", lambda *_args, **_kwargs: {"status": "FAIL", "summary": {"failed": 1}})
    checks: list[dict] = []
    evidence_continuity._check_predecessor(ROOT, FIXTURE, checks, verify_git_history=False)
    assert next(check for check in checks if check["id"] == "S07P04-P03-PREDECESSOR-PASS")["passed"] is False


def test_candidate_fails_closed_when_evidence_index_jsonl_is_malformed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / EVIDENCE_INDEX_PATH).unlink(missing_ok=True)
    (root / EVIDENCE_INDEX_PATH).write_text('{"id":"INDEX-AC-S07-P04"}\n{not-json}\n', encoding="utf-8")
    with pytest.raises(EvidenceContinuityError):
        _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    checks: list[dict] = []
    _check_taskpack_continuity(root, FIXTURE, checks)
    assert next(check for check in checks if check["id"] == "S07P04-EVIDENCE-INDEX-STRICT-JSONL")["passed"] is False


def test_candidate_fails_closed_when_traceability_orphans_a_task(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
    row = next(item for item in traceability if item["requirement_id"] == "REQ-S07-P04")
    row["task_ids"] = ["T-S07-P04-01", "T-S07-P04-03"]
    _write_json(root / "machine/facts/traceability_matrix.json", traceability)
    checks: list[dict] = []
    _check_taskpack_continuity(root, FIXTURE, checks)
    assert next(check for check in checks if check["id"] == "S07P04-ALL-LINK-COLLECTIONS-COVERED")["passed"] is False


def test_candidate_fails_closed_when_manifest_entry_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    manifest_path = root / "machine/evidence/artifact_manifest.json"
    manifest = strict_json_load(manifest_path)
    row = next(item for item in manifest["files"] if item["path"] == ORACLE_PATH.as_posix())
    row["sha256"] = "0" * 64
    _write_json(manifest_path, manifest)
    checks: list[dict] = []
    _check_manifest(root, checks, p04_index_status="PLANNED")
    assert next(check for check in checks if check["id"] == "S07P04-ARTIFACT-MANIFEST-COVERAGE")["passed"] is False


def test_generated_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    checks: list[dict] = []
    _check_reports(root, FIXTURE, checks, require_test_reports=True)
    assert next(check for check in checks if check["id"] == "S07P04-TARGETED-PYTEST-REPORT")["passed"] is False
    assert next(check for check in checks if check["id"] == "S07P04-FULL-PYTEST-REPORT")["passed"] is False


def test_junit_normalization_accepts_only_fixed_metadata(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" timestamp="%s" time="0.000"><testcase name="offline" time="0.000" /></testsuite></testsuites>'
        % JUNIT_FIXED_CLOCK,
        encoding="utf-8",
    )
    assert _junit_is_normalized(report) is True
    assert _junit_summary(report)["tests"] == 1
    report.write_text(report.read_text(encoding="utf-8").replace('time="0.000"', 'time="0.001"', 1), encoding="utf-8")
    assert _junit_is_normalized(report) is False


def test_oracle_cli_is_wired_to_exact_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S07-P04": write_evidence_continuity_phase_evidence' in source
    assert "from .evidence_continuity import write_phase_evidence as write_evidence_continuity_phase_evidence" in source


def test_candidate_evidence_carries_continuity_and_no_soak_summary() -> None:
    evidence, rollback = build_evidence(ROOT)
    assert evidence["status"] == "PASS", evidence["validation"]
    assert evidence["continuity_summary"]["orphan_counts"] == {
        "artifacts": 0,
        "contracts": 0,
        "evidence": 0,
        "release": 0,
        "requirements": 0,
        "tasks": 0,
        "traceability": 0,
    }
    assert evidence["continuity_summary"]["positive_output_sha256"] == FIXTURE["expected_positive_output_sha256"]
    assert evidence["structured_failure_log"]["case_reason_codes"]["NEGATIVE_ORPHAN_TASK"] == ["ORPHAN_TASKS"]
    assert evidence["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert evidence["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert evidence["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert evidence["deterministic_replay"]["real_time_wait_performed"] is False
    assert rollback["status"] == "PASS"


def test_p03_predecessor_receipt_remains_independently_verifiable() -> None:
    result = verify_p03_evidence(ROOT)
    assert result["status"] == "PASS", result


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        result = verify_existing_phase_evidence(ROOT)
        assert result["status"] == "PASS", result
    else:
        assert not (ROOT / EVIDENCE_PATH).is_file()
        assert not (ROOT / ROLLBACK_EVIDENCE_PATH).is_file()
