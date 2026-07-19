from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import (
    DuplicateKeyError,
    build_evidence,
    evaluate_contract,
    perform_rollback_drill,
    strict_json_load,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "machine/tests/fixtures/S00_P01.json").read_text(encoding="utf-8")
)


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__", "*.pyc"),
    )
    return destination


def _set_pointer(value, pointer: str, replacement) -> None:
    parts = [part for part in pointer.split("/") if part]
    current = value
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = replacement


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def test_baseline_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["next"] == "S00/P02_READY_NOT_STARTED"


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"product":{"version":"0.0.0.1","version":"0.0.0.2"}}', encoding="utf-8")
    with pytest.raises(DuplicateKeyError):
        strict_json_load(path)


def test_second_canonical_source_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    shadow = project / "shadow/canonical_facts.json"
    shadow.parent.mkdir(parents=True)
    shutil.copyfile(str(project / "machine/facts/canonical_facts.json"), str(shadow))
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "FACT-SINGLE-SOURCE" in result["summary"]["failed_check_ids"]


def test_wrong_version_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/canonical_facts.json"
    facts = strict_json_load(path)
    facts["product"]["version"] = "0.0.0.2"
    _write_json(path, facts)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "FACT-BASELINE-VALUES" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize("case", FIXTURE["boundary_mutations"], ids=lambda case: case["id"])
def test_sensitive_fact_boundary_mutations_fail_closed(tmp_path: Path, case) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/canonical_facts.json"
    facts = strict_json_load(path)
    _set_pointer(facts, case["json_pointer"], case["value"])
    _write_json(path, facts)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == case["expected_status"]
    assert "FACT-PINNED-HASH" in result["summary"]["failed_check_ids"]


def test_hash_lock_mismatch_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "machine/facts/canonical_facts.sha256").write_text(
        "0" * 64 + "  machine/facts/canonical_facts.json\n", encoding="utf-8"
    )
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "FACT-HASH-LOCK" in result["summary"]["failed_check_ids"]


def test_unresolved_conflict_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/canonical_conflicts.json"
    report = strict_json_load(path)
    report["status"] = "UNRESOLVED_CONFLICTS"
    report["unresolved_conflict_count"] = 1
    report["conflicts"] = [{"id": "CONFLICT-TEST", "status": "UNRESOLVED"}]
    _write_json(path, report)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "CONFLICT-NONE-UNRESOLVED" in result["summary"]["failed_check_ids"]


def test_malformed_canonical_json_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "machine/facts/canonical_facts.json").write_text("{", encoding="utf-8")
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "FACT-STRICT-JSON" in result["summary"]["failed_check_ids"]


def test_missing_required_fact_fails_closed_without_crashing(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/canonical_facts.json"
    facts = strict_json_load(path)
    del facts["product"]["version"]
    _write_json(path, facts)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "FACT-BASELINE-VALUES" in result["summary"]["failed_check_ids"]
    assert "FACT-CROSS-SOURCE" in result["summary"]["failed_check_ids"]


def test_invalid_conflict_collection_type_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/canonical_conflicts.json"
    report = strict_json_load(path)
    report["conflicts"] = "none"
    _write_json(path, report)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "CONFLICT-NONE-UNRESOLVED" in result["summary"]["failed_check_ids"]


def test_evidence_replay_is_deterministic() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback


def test_rollback_drill_restores_frozen_bytes() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["signed_sha256"] == result["restored_sha256"]
    assert result["corrupted_sha256"] != result["restored_sha256"]
    assert result["production_state_changed"] is False
