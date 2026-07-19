from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.model_risk_research import verify_existing_phase_evidence as verify_p02_evidence
from abd_acceptance.open_source_reuse import (
    EVIDENCE_PATH,
    FIXTURE_PATH,
    LICENSE_INVENTORY_PATH,
    P02_EVIDENCE_SHA256,
    P02_ROLLBACK_SHA256,
    PINNED_PHASE_HASHES,
    REUSE_MATRIX_PATH,
    ROLLBACK_EVIDENCE_PATH,
    SUCCESSOR_EVOLVED_TEST_HASHES,
    TEST_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_reuse_admission,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


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
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _row(rows, item_id: str, key: str = "id"):
    return next(row for row in rows if row[key] == item_id)


def _project(value, source_id: str):
    return _row(value["projects"], source_id, "source_id")


def _license(value, source_id: str):
    return _row(value["entries"], source_id, "source_id")


def _admit(case, delta: str | None = None) -> str:
    return resolve_reuse_admission(
        license_class=case["license_class"],
        reuse_mode=case["reuse_mode"],
        source_contract=case["source_contract"],
        contains_order_capability=case["contains_order_capability"],
        requires_live_account=case["requires_live_account"],
        requires_incremental_cash=case["requires_incremental_cash"],
        numeric_delta=case.get("numeric_delta", "0") if delta is None else delta,
    )


def test_baseline_open_source_reuse_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["decision"] == "OPEN_SOURCE_REUSE_AND_LICENSE_DECISIONS_FROZEN"
    assert result["release_status"] == "NOT_READY_STAGE_REVIEW_REQUIRED"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["reuse_status"] == "RESEARCH_ONLY_NO_CODE_COPIED_OR_DEPENDENCY_ADDED"
    assert result["license_status"] == "ENGINEERING_AUDIT_NOT_LEGAL_CLEARANCE"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S02/P04_READY_NOT_STARTED"
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_p02_signed_receipt_is_exact_prerequisite_without_successor_recursion() -> None:
    result = verify_p02_evidence(
        ROOT,
        verify_git_history=True,
        verify_p01_prerequisite=True,
        verify_successor_state=False,
    )
    assert result["status"] == "PASS", result
    assert result["decision"] == "S02_P02_EVIDENCE_VERIFIED"
    assert result["evidence_sha256"] == P02_EVIDENCE_SHA256
    assert result["rollback_sha256"] == P02_ROLLBACK_SHA256
    assert result["next"] == "S02/P03_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", [REUSE_MATRIX_PATH, LICENSE_INVENTORY_PATH, FIXTURE_PATH, TEST_PATH])
def test_phase_artifact_hashes_match_oracle_pins(relative: Path) -> None:
    actual = sha256_file(ROOT / relative)
    if relative == TEST_PATH:
        assert actual == SUCCESSOR_EVOLVED_TEST_HASHES[relative.as_posix()]
        assert actual != PINNED_PHASE_HASHES[relative.as_posix()]
    else:
        assert actual == PINNED_PHASE_HASHES[relative.as_posix()]


@pytest.mark.parametrize("source_id", FIXTURE["expected_project_source_ids"])
def test_every_project_has_exact_identity_commit_readme_decision_and_three_way_ruling(source_id: str) -> None:
    matrix = strict_json_load(ROOT / REUSE_MATRIX_PATH)
    project = _project(matrix, source_id)
    assert project["repository"] == FIXTURE["expected_repositories"][source_id]
    assert project["pinned_commit"] == FIXTURE["expected_pinned_commits"][source_id]
    assert project["readme"]["sha256"] == FIXTURE["expected_readme_sha256"][source_id]
    assert project["pinned_commit"] in project["readme"]["url"]
    assert project["pinned_commit"] in project["commit_url"]
    assert project["decision"] == FIXTURE["expected_decisions"][source_id]
    assert project["adopt"]
    assert project["adapt"]
    assert project["reject"]
    assert not set(project["adopt"]) & set(project["reject"])
    assert project["license_evidence_id"] == f"LIC-{source_id}"
    assert project["unverified"]
    assert project["review_trigger"]


@pytest.mark.parametrize("source_id", FIXTURE["expected_project_source_ids"])
def test_every_license_record_matches_exact_pinned_content_or_noassertion(source_id: str) -> None:
    inventory = strict_json_load(ROOT / LICENSE_INVENTORY_PATH)
    row = _license(inventory, source_id)
    expected = FIXTURE["expected_license_records"][source_id]
    assert row["id"] == expected["id"]
    assert row["detected_spdx"] == expected["spdx"]
    assert row["license_path"] == expected["path"]
    assert row["license_git_blob_sha1"] == expected["git_blob_sha1"]
    assert row["license_sha256"] == expected["sha256"]
    if expected["spdx"] == "NOASSERTION":
        assert row["license_api_result"] == "NOT_FOUND_AT_RETRIEVAL"
        assert row["p03_disposition"] == "REJECT_ALL_CODE_REUSE_PUBLIC_METADATA_RESEARCH_ONLY"
    else:
        assert row["pinned_commit"] in row["license_url"]
        assert row["copyright_notice"]


@pytest.mark.parametrize("source_id", FIXTURE["expected_project_source_ids"])
def test_project_and_license_graph_is_bijective(source_id: str) -> None:
    matrix = strict_json_load(ROOT / REUSE_MATRIX_PATH)
    inventory = strict_json_load(ROOT / LICENSE_INVENTORY_PATH)
    project = _project(matrix, source_id)
    license_row = _license(inventory, source_id)
    assert project["license_evidence_id"] == license_row["id"]
    assert project["repository"] == license_row["repository"]
    assert project["pinned_commit"] == license_row["pinned_commit"]


@pytest.mark.parametrize("case", FIXTURE["decision_vectors"])
def test_frozen_decision_vectors_are_fail_closed(case) -> None:
    assert _admit(case) == case["expected"]


@pytest.mark.parametrize(
    ("case", "delta"),
    [(case, delta) for case in FIXTURE["boundary_cases"] for delta in FIXTURE["numeric_boundary_deltas"]],
)
def test_plus_minus_point_0001_cannot_change_categorical_license_or_safety_decision(case, delta: str) -> None:
    assert _admit(case, delta) == case["expected"]


@pytest.mark.parametrize(
    ("license_class", "reuse_mode", "delta"),
    [
        (license_class, reuse_mode, delta)
        for license_class in ["MIT", "Apache-2.0", "NOASSERTION"]
        for reuse_mode in [
            "DESIGN_PATTERN",
            "ALGORITHM_REFERENCE",
            "PARSER_TEST_PATTERN",
            "PUBLIC_METADATA_RESEARCH",
            "MOCK_SCHEMA_REFERENCE",
            "COPY_CODE",
            "ADD_RUNTIME_DEPENDENCY",
            "LIVE_SOURCE",
        ]
        for delta in ["-0.0001", "0", "0.0001"]
    ],
)
def test_reuse_admission_is_deterministic_across_all_license_mode_boundary_combinations(
    license_class: str,
    reuse_mode: str,
    delta: str,
) -> None:
    kwargs = {
        "license_class": license_class,
        "reuse_mode": reuse_mode,
        "source_contract": "UNVERIFIED",
        "contains_order_capability": False,
        "requires_live_account": False,
        "requires_incremental_cash": False,
        "numeric_delta": delta,
    }
    first = resolve_reuse_admission(**kwargs)
    second = resolve_reuse_admission(**kwargs)
    assert first == second
    if license_class == "NOASSERTION" and reuse_mode not in {"PUBLIC_METADATA_RESEARCH"}:
        assert first == "REJECT_NO_LICENSE"
    elif reuse_mode == "PUBLIC_METADATA_RESEARCH":
        assert first == "ALLOW_PUBLIC_METADATA_RESEARCH_ONLY"
    elif reuse_mode == "LIVE_SOURCE":
        assert first == "REJECT_UNVERIFIED_SOURCE_CONTRACT"
    elif reuse_mode in {"COPY_CODE", "ADD_RUNTIME_DEPENDENCY"}:
        assert first == "REJECT_P03_RUNTIME_SCOPE"
    else:
        assert first == "ALLOW_PINNED_RESEARCH_ADAPTATION"


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("contains_order_capability", "REJECT_ORDER_CAPABILITY"),
        ("requires_live_account", "REJECT_ACCOUNT_OR_API_ACCESS"),
        ("requires_incremental_cash", "REJECT_INCREMENTAL_CASH"),
    ],
)
@pytest.mark.parametrize("delta", FIXTURE["numeric_boundary_deltas"])
def test_order_account_and_cash_gates_dominate_all_numeric_deltas(flag: str, expected: str, delta: str) -> None:
    kwargs = {
        "license_class": "MIT",
        "reuse_mode": "DESIGN_PATTERN",
        "source_contract": "NOT_APPLICABLE",
        "contains_order_capability": False,
        "requires_live_account": False,
        "requires_incremental_cash": False,
        "numeric_delta": delta,
    }
    kwargs[flag] = True
    assert resolve_reuse_admission(**kwargs) == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"license_class": "GPL-3.0"},
        {"reuse_mode": "INSTALL_ANYWAY"},
        {"source_contract": "ASSUMED"},
        {"contains_order_capability": 1},
        {"requires_live_account": "false"},
        {"requires_incremental_cash": None},
        {"numeric_delta": 0.0001},
        {"numeric_delta": "NaN"},
        {"numeric_delta": "Infinity"},
        {"numeric_delta": "0.0002"},
        {"numeric_delta": "-0.0002"},
        {"numeric_delta": " 0.0001"},
        {"numeric_delta": "invalid"},
    ],
)
def test_reuse_admission_rejects_unknown_enums_non_boolean_flags_and_nonfrozen_numeric_input(kwargs) -> None:
    baseline = {
        "license_class": "MIT",
        "reuse_mode": "DESIGN_PATTERN",
        "source_contract": "NOT_APPLICABLE",
        "contains_order_capability": False,
        "requires_live_account": False,
        "requires_incremental_cash": False,
        "numeric_delta": "0",
    }
    baseline.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        resolve_reuse_admission(**baseline)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("roadmap_title", "S02P03-ROADMAP-EXACT"),
        ("roadmap_output", "S02P03-ROADMAP-EXACT"),
        ("requirement_target", "S02P03-REQUIREMENT-EXACT"),
        ("acceptance_command", "S02P03-ACCEPTANCE-CONTRACT-EXACT"),
        ("task_dependency", "S02P03-TASK-CHAIN-EXACT"),
        ("task_output", "S02P03-TASK-CHAIN-EXACT"),
        ("task_owner", "S02P03-TASK-CHAIN-EXACT"),
        ("trace_evidence", "S02P03-TRACEABILITY-EXACT"),
    ],
)
def test_taskpack_contract_drift_fails_closed(tmp_path: Path, mutation: str, expected_check: str) -> None:
    project = _clone_project(tmp_path)
    if mutation.startswith("roadmap"):
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        phase = next(row for row in next(row for row in value["stages"] if row["id"] == "S02")["phases"] if row["id"] == "P03")
        if mutation == "roadmap_title":
            phase["title"] = "drift"
        else:
            phase["outputs"][0] = "drift.json"
    elif mutation == "requirement_target":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P03")["target"] = "drift"
    elif mutation == "acceptance_command":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        _row(value, "AC-S02-P03")["oracle"]["command"] = "true"
    elif mutation.startswith("task"):
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        task = _row(value["tasks"], "T-S02-P03-02")
        if mutation == "task_dependency":
            task["depends_on"] = []
        elif mutation == "task_output":
            task["outputs"][0] = "wrong"
        else:
            task["owner_input_required"] = True
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P03", "requirement_id")["evidence_id"] = "wrong"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("status", "S02P03-MATRIX-SHAPE"),
        ("duplicate", "S02P03-MATRIX-PROJECT-COVERAGE"),
        ("repository", "S02P03-MATRIX-REPOSITORIES-EXACT"),
        ("commit", "S02P03-MATRIX-COMMITS-EXACT"),
        ("readme_hash", "S02P03-MATRIX-README-PINS-EXACT"),
        ("readme_url", "S02P03-MATRIX-README-PINS-EXACT"),
        ("decision", "S02P03-MATRIX-DECISIONS-EXACT"),
        ("adopt", "S02P03-MATRIX-ADOPT-ADAPT-REJECT-COMPLETE"),
        ("adapt", "S02P03-MATRIX-ADOPT-ADAPT-REJECT-COMPLETE"),
        ("reject_overlap", "S02P03-MATRIX-ADOPT-ADAPT-REJECT-COMPLETE"),
        ("api_url", "S02P03-MATRIX-OFFICIAL-PINNED-URLS"),
        ("global_copy", "S02P03-MATRIX-GLOBAL-CONTROLS"),
        ("silent_omission", "S02P03-MATRIX-COVERAGE-NO-SILENT-OMISSION"),
        ("cash", "S02P03-MATRIX-NO-EXTERNAL-EFFECT"),
        ("baseline_adopt", "S02P03-MATRIX-BASELINE-CONTINUITY"),
        ("flumine_order", "S02P03-FLUMINE-ORDER-CAPABILITY-REJECTED"),
        ("harvester_proxy", "S02P03-ODDSHARVESTER-NO-BYPASS-OR-LIVE-SOURCE"),
        ("unlicensed_copy", "S02P03-UNLICENSED-CODE-REUSE-REJECTED"),
        ("ml_return", "S02P03-ML-DEMO-NO-MODEL-OR-RETURN-EVIDENCE"),
        ("odds_service", "S02P03-ODDS-API-CODE-SERVICE-SEPARATION"),
    ],
)
def test_reuse_matrix_tampering_fails_closed(tmp_path: Path, mutation: str, expected_check: str) -> None:
    project = _clone_project(tmp_path)
    path = project / REUSE_MATRIX_PATH
    value = strict_json_load(path)
    first = _project(value, "SRC-013")
    if mutation == "status":
        value["status"] = "PASS"
    elif mutation == "duplicate":
        value["projects"][1]["source_id"] = "SRC-013"
    elif mutation == "repository":
        first["repository"] = "https://example.com/repo"
    elif mutation == "commit":
        first["pinned_commit"] = "main"
    elif mutation == "readme_hash":
        first["readme"]["sha256"] = "0" * 64
    elif mutation == "readme_url":
        first["readme"]["url"] = "https://github.com/betcode-org/flumine/blob/master/README.md"
    elif mutation == "decision":
        first["decision"] = "ADOPT_RUNTIME"
    elif mutation == "adopt":
        first["adopt"] = []
    elif mutation == "adapt":
        first["adapt"] = []
    elif mutation == "reject_overlap":
        first["reject"].append(first["adopt"][0])
    elif mutation == "api_url":
        first["repository_api"] = "http://api.github.com/repos/betcode-org/flumine"
    elif mutation == "global_copy":
        value["global_controls"]["code_copied"] = True
    elif mutation == "silent_omission":
        value["coverage"]["silent_project_omissions"] = 1
    elif mutation == "cash":
        value["external_effect_boundary"]["incremental_cash_spent_aud"] = "0.01"
    elif mutation == "baseline_adopt":
        first["adopt"].remove("事件循环")
    elif mutation == "flumine_order":
        first["reject"].remove("任何 place、cancel、update、replace 订单能力")
    elif mutation == "harvester_proxy":
        _project(value, "SRC-015")["reject"] = [
            item for item in _project(value, "SRC-015")["reject"] if "代理轮换" not in item
        ]
    elif mutation == "unlicensed_copy":
        _project(value, "SRC-016")["reject"] = [
            item for item in _project(value, "SRC-016")["reject"] if "复制、修改、打包或分发" not in item
        ]
    elif mutation == "ml_return":
        _project(value, "SRC-017")["reject"] = [
            item for item in _project(value, "SRC-017")["reject"] if "5.2%" not in item
        ]
    else:
        _project(value, "SRC-018")["reject"] = [
            item for item in _project(value, "SRC-018")["reject"] if "代码 Apache-2.0" not in item
        ]
    _write_json(path, value)
    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("legal_advice", "S02P03-LICENSE-POLICY-FAIL-CLOSED"),
        ("class_controls", "S02P03-LICENSE-CLASS-CONTROLS"),
        ("duplicate", "S02P03-LICENSE-ENTRY-COVERAGE"),
        ("spdx", "S02P03-LICENSE-PINS-EXACT"),
        ("license_hash", "S02P03-LICENSE-PINS-EXACT"),
        ("license_blob", "S02P03-LICENSE-PINS-EXACT"),
        ("noassertion_path", "S02P03-LICENSE-PINS-EXACT"),
        ("noassertion_disposition", "S02P03-LICENSE-NOASSERTION-REJECTS-COPY"),
        ("apache_scope", "S02P03-LICENSE-APACHE-CODE-SERVICE-BOUNDARY"),
        ("mit_disposition", "S02P03-LICENSE-MIT-NOTICE-AND-NO-P03-COPY"),
        ("summary", "S02P03-LICENSE-SUMMARY-EXACT"),
        ("effects", "S02P03-LICENSE-NO-EXTERNAL-EFFECT"),
    ],
)
def test_license_inventory_tampering_fails_closed(tmp_path: Path, mutation: str, expected_check: str) -> None:
    project = _clone_project(tmp_path)
    path = project / LICENSE_INVENTORY_PATH
    value = strict_json_load(path)
    if mutation == "legal_advice":
        value["policy"]["legal_advice"] = True
    elif mutation == "class_controls":
        value["license_classes"]["MIT"]["required_controls"] = []
    elif mutation == "duplicate":
        value["entries"][1]["id"] = value["entries"][0]["id"]
    elif mutation == "spdx":
        _license(value, "SRC-013")["detected_spdx"] = "GPL-3.0"
    elif mutation == "license_hash":
        _license(value, "SRC-013")["license_sha256"] = "0" * 64
    elif mutation == "license_blob":
        _license(value, "SRC-013")["license_git_blob_sha1"] = "0" * 40
    elif mutation == "noassertion_path":
        _license(value, "SRC-016")["license_path"] = "LICENSE"
    elif mutation == "noassertion_disposition":
        _license(value, "SRC-016")["p03_disposition"] = "COPY_ALLOWED"
    elif mutation == "apache_scope":
        _license(value, "SRC-018")["code_license_scope"] = "covers service data"
    elif mutation == "mit_disposition":
        _license(value, "SRC-013")["p03_disposition"] = "COPY_NOW"
    elif mutation == "summary":
        value["summary"]["NOASSERTION"] = 0
    else:
        value["external_effect_boundary"]["package_installed"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize("relative", [REUSE_MATRIX_PATH, LICENSE_INVENTORY_PATH, FIXTURE_PATH])
def test_strict_json_duplicate_keys_fail_closed(tmp_path: Path, relative: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_text('{"schema_version":"1.0.0","schema_version":"drift"}\n', encoding="utf-8")
    result = evaluate_contract(project)
    assert result["status"] == "FAIL"
    assert any("STRICT-JSON" in item for item in result["summary"]["failed_check_ids"])


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("relative", [REUSE_MATRIX_PATH, LICENSE_INVENTORY_PATH])
def test_nonfinite_json_numbers_fail_closed(tmp_path: Path, relative: Path, token: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_text('{"value":%s}\n' % token, encoding="utf-8")
    result = evaluate_contract(project)
    assert result["status"] == "FAIL"


@pytest.mark.parametrize(
    ("relative", "field"),
    [
        (REUSE_MATRIX_PATH, "project_count"),
        (LICENSE_INVENTORY_PATH, "projects"),
        (FIXTURE_PATH, "minimum_targeted_pytest_cases"),
    ],
)
def test_binary_float_in_authoritative_artifacts_fails_closed(tmp_path: Path, relative: Path, field: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    value = strict_json_load(path)
    if relative == REUSE_MATRIX_PATH:
        value["global_controls"][field] = 6.0
    elif relative == LICENSE_INVENTORY_PATH:
        value["summary"][field] = 6.0
    else:
        value[field] = 120.0
    _write_json(path, value)
    _failed(evaluate_contract(project), "S02P03-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS")


def test_p02_receipt_tamper_breaks_immutable_prerequisite(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/EVD-S02-P02.json"
    value = strict_json_load(path)
    value["status"] = "FAIL"
    _write_json(path, value)
    _failed(evaluate_contract(project), "S02P03-P02-IMMUTABLE-PREREQUISITE")


def test_p02_rollback_tamper_breaks_immutable_prerequisite(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/EVD-S02-P02_rollback.json"
    value = strict_json_load(path)
    value["status"] = "FAIL"
    _write_json(path, value)
    _failed(evaluate_contract(project), "S02P03-P02-IMMUTABLE-PREREQUISITE")


@pytest.mark.parametrize(
    "relative",
    [
        "research_gaps.json",
        "counterevidence.json",
        "review_schedule.json",
        "tests/S02/P04_test.py",
        "machine/tests/fixtures/S02_P04.json",
        "machine/evidence/EVD-S02-P04.json",
        "machine/evidence/EVD-S02-P04_rollback.json",
    ],
)
def test_any_p04_candidate_artifact_tamper_fails_predecessor_guard(tmp_path: Path, relative: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S02P03-P04-NOT-STARTED")


def test_evidence_index_p04_tamper_fails_predecessor_guard(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    _row(rows, "INDEX-AC-S02-P04")["status"] = "READY"
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    _failed(evaluate_contract(project), "S02P03-P04-NOT-STARTED")


def test_rollback_drill_restores_all_eight_signed_artifacts_without_external_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"] == 8
    for artifact in result["artifacts"].values():
        assert artifact["status"] == "PASS"
        assert artifact["corrupted_sha256"] != artifact["signed_sha256"]
        assert artifact["restored_sha256"] == artifact["signed_sha256"]


@pytest.mark.parametrize(
    "artifact",
    [
        REUSE_MATRIX_PATH.as_posix(),
        LICENSE_INVENTORY_PATH.as_posix(),
        FIXTURE_PATH.as_posix(),
        "machine/evidence/EVD-S02-P02.json",
        "machine/evidence/EVD-S02-P02_rollback.json",
        "machine/facts/research_reuse_matrix.json",
        "machine/facts/sources.json",
        ".github/workflows/abd-stage0-validation.yml",
    ],
)
def test_rollback_drill_covers_exact_required_artifact(artifact: str) -> None:
    result = perform_rollback_drill(ROOT)
    assert artifact in result["artifacts"]
    assert result["artifacts"][artifact]["status"] == "PASS"


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    evidence_a, rollback_a = build_evidence(ROOT, require_external_reports=False)
    evidence_b, rollback_b = build_evidence(ROOT, require_external_reports=False)
    assert evidence_a == evidence_b
    assert rollback_a == rollback_b
    assert evidence_a["status"] == "PASS", evidence_a["validation"]["summary"]
    assert evidence_a["decision"] == "OPEN_SOURCE_REUSE_AND_LICENSE_DECISIONS_FROZEN"
    assert evidence_a["next"] == "S02/P04_READY_NOT_STARTED"
    assert evidence_a["artifacts"] == {
        "ART-S02-P03-01": REUSE_MATRIX_PATH.as_posix(),
        "ART-S02-P03-02": LICENSE_INVENTORY_PATH.as_posix(),
    }
    unsigned = dict(evidence_a)
    decision_hash = unsigned.pop("decision_sha256")
    rendered = (json.dumps(unsigned, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    import hashlib

    assert decision_hash == hashlib.sha256(rendered).hexdigest()


def test_evidence_build_records_no_clone_install_account_api_order_model_cash_or_return_effect() -> None:
    evidence, _ = build_evidence(ROOT, require_external_reports=False)
    effects = evidence["external_effect_boundary"]
    assert effects == FIXTURE["expected_external_effect_boundary"]
    assert effects["github_upload_performed"] is False
    assert effects["repository_cloned"] is False
    assert effects["package_installed"] is False
    assert effects["provider_api_called"] is False
    assert effects["api_key_requested_or_used"] is False
    assert effects["incremental_cash_spent_aud"] == "0.00"
    assert effects["real_order_capability_present"] is False
    assert effects["model_or_strategy_executed"] is False
    assert effects["return_or_guarantee_claimed"] is False
    assert effects["s02_p04_started"] is False


def test_evidence_and_artifacts_contain_no_absolute_local_paths() -> None:
    evidence, rollback = build_evidence(ROOT, require_external_reports=False)
    rendered = json.dumps(
        [
            evidence,
            rollback,
            strict_json_load(ROOT / REUSE_MATRIX_PATH),
            strict_json_load(ROOT / LICENSE_INVENTORY_PATH),
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    assert str(ROOT) not in rendered
    assert ("/" + "Users/") not in rendered
    assert ("/private/" + "var/") not in rendered


def test_github_license_detection_is_not_legal_or_service_clearance() -> None:
    inventory = strict_json_load(ROOT / LICENSE_INVENTORY_PATH)
    policy = inventory["policy"]
    assert policy["legal_advice"] is False
    assert policy["code_license_separate_from_service_terms"] is True
    assert policy["p03_code_copy_or_dependency_addition"] is False
    assert inventory["summary"]["legal_clearance_claimed"] is False
    assert inventory["summary"]["service_terms_treated_as_code_license"] == 0


def test_unlicensed_repository_is_visible_but_not_reusable() -> None:
    matrix = strict_json_load(ROOT / REUSE_MATRIX_PATH)
    inventory = strict_json_load(ROOT / LICENSE_INVENTORY_PATH)
    project = _project(matrix, "SRC-016")
    license_row = _license(inventory, "SRC-016")
    assert project["decision"] == "REJECT_CODE_REUSE_RESEARCH_ONLY"
    assert "PUBLIC_METADATA_RESEARCH_ONLY" in project["adoption_status"]
    assert license_row["detected_spdx"] == "NOASSERTION"
    assert license_row["license_api_result"] == "NOT_FOUND_AT_RETRIEVAL"
    assert license_row["future_reuse"].startswith("BLOCKED_UNLESS_RIGHTSHOLDER")


def test_code_license_never_becomes_source_access_or_market_coverage_proof() -> None:
    matrix = strict_json_load(ROOT / REUSE_MATRIX_PATH)
    odds_api = _project(matrix, "SRC-018")
    harvester = _project(matrix, "SRC-015")
    assert "SERVICE_TERMS" in odds_api["source_contract_status"]
    assert any("覆盖证明" in item for item in odds_api["reject"])
    assert "BLOCKS_ALL_LIVE_ODDSPORTAL_ACCESS" in harvester["source_contract_status"]
    assert any("条款" in item for item in harvester["reject"])


def test_p03_evidence_paths_are_reserved_while_validated_p04_candidate_exists() -> None:
    assert EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-P03.json"
    assert ROLLBACK_EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-P03_rollback.json"
    assert (ROOT / "research_gaps.json").exists()
    assert (ROOT / "counterevidence.json").exists()
    assert (ROOT / "review_schedule.json").exists()
    assert (ROOT / "tests/S02/P04_test.py").exists()
    assert (ROOT / "machine/tests/fixtures/S02_P04.json").exists()
    assert (ROOT / "machine/facts/stage2_review_contract.json").is_file()
    assert (ROOT / "abd_acceptance/stage2_review.py").is_file()
    assert (ROOT / "tests/S02/stage_review_test.py").is_file()
    assert (ROOT / "machine/evidence/EVD-S02-STAGE-REVIEW.json").exists() is (
        ROOT / "machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json"
    ).exists()
