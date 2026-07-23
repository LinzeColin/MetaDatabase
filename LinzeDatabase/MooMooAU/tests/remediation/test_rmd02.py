from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from build_delivery_status import build_status
from validate_delivery_status import validate_value
from validate_evidence import (
    PROJECT_ROOT,
    _claim_summary,
    _validate_later_stage_record,
    validate_record,
)
from validate_publication import scan_tree

RMD02_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.2.json")
RMD02_MANIFEST_SHA256 = "6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3"
RMD02_LEGACY_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.1.json")
RMD02_LEGACY_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"

INHERITED_HASHES = {
    "machine/contracts/requirements.json": (
        "ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27"
    ),
    "machine/contracts/acceptance_contract.json": (
        "3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb"
    ),
    "machine/contracts/traceability_matrix.csv": (
        "263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2"
    ),
    "machine/contracts/kill_criteria.json": (
        "2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc"
    ),
}


def _load(relative: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8")),
    )


def _errors_for(record: dict[str, Any]) -> list[str]:
    task_id = str(record["task_id"])
    return cast(
        list[str],
        _validate_later_stage_record(
            record,
            Path("evidence/tasks") / f"{task_id}.json",
            PROJECT_ROOT,
        ),
    )


def test_rmd02_all_58_task_evidence_records_validate_without_promotion() -> None:
    graph = _load("machine/contracts/task_graph.json")
    tasks = graph["tasks"]
    assert isinstance(tasks, list)
    assert len(tasks) == 58
    for task in tasks:
        assert isinstance(task, dict)
        path = PROJECT_ROOT / "evidence/tasks" / f"{task['id']}.json"
        assert validate_record(path) == []
        claim = _claim_summary(path, PROJECT_ROOT)
        assert claim["formal_task_status"] == task["status"]
        assert claim["production_ready"] is False


def test_rmd02_stage7_blocked_record_is_valid_but_not_completed() -> None:
    path = PROJECT_ROOT / "evidence/tasks/T0704.json"
    assert validate_record(path) == []
    claim = _claim_summary(path, PROJECT_ROOT)
    assert claim["declared_record_status"] == "BLOCKED"
    assert claim["formal_task_status"] == "planned"
    assert set(claim["linked_final_acceptance_statuses"].values()) == {"NOT_RUN"}
    assert set(claim["protected_oracle_statuses"].values()) == {"NOT_RUN"}


def test_rmd02_rejects_stage_schema_and_cross_binding_drift() -> None:
    original = _load("evidence/tasks/T0101.json")

    wrong_schema = copy.deepcopy(original)
    wrong_schema["schema_version"] = "moomooau.stage7-evidence.v1"
    assert any("schema violation" in error for error in _errors_for(wrong_schema))

    wrong_local_acceptance = copy.deepcopy(original)
    wrong_local_acceptance["stage_acceptance_id"] = "S1AC-002"
    assert "task and stage acceptance mapping mismatch" in _errors_for(wrong_local_acceptance)

    wrong_final_acceptance = copy.deepcopy(original)
    linked = wrong_final_acceptance["linked_final_acceptance"]
    assert isinstance(linked, list)
    assert isinstance(linked[0], dict)
    linked[0]["id"] = "AC-034"
    assert "evidence final Acceptance bindings mismatch" in _errors_for(wrong_final_acceptance)


def test_rmd02_rejects_overstatement_prohibition_and_unsafe_reference() -> None:
    original = _load("evidence/tasks/T0301.json")

    overstated = copy.deepcopy(original)
    linked = overstated["linked_final_acceptance"]
    assert isinstance(linked, list)
    assert isinstance(linked[0], dict)
    linked[0]["status"] = "PASS"
    assert "final Acceptance claim is overstated" in _errors_for(overstated)

    prohibited = copy.deepcopy(original)
    counters = prohibited["prohibition_counters"]
    assert isinstance(counters, dict)
    counters["real_gmail_calls"] = 1
    assert "all prohibition counters must be integer zero" in _errors_for(prohibited)

    unsafe = copy.deepcopy(original)
    checks = unsafe["checks"]
    assert isinstance(checks, list)
    assert isinstance(checks[0], dict)
    checks[0]["evidence_ref"] = "../../outside.json"
    assert "evidence_ref is an unsafe path" in _errors_for(unsafe)


def test_rmd02_preserves_inherited_contracts_and_legacy_manifest() -> None:
    for relative, expected in INHERITED_HASHES.items():
        assert hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest() == expected
    legacy = PROJECT_ROOT / RMD02_LEGACY_MANIFEST_PATH
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == RMD02_LEGACY_MANIFEST_SHA256


def test_rmd02_rejects_evidence_outside_project_root(tmp_path: Path) -> None:
    outside = tmp_path / "T0101.json"
    outside.write_text("{}\n", encoding="utf-8")
    assert validate_record(outside) == ["evidence path escapes project root"]

    symlink = tmp_path / "T0101-link.json"
    symlink.symlink_to(PROJECT_ROOT / "evidence/tasks/T0101.json")
    assert validate_record(symlink) == ["evidence path is a symlink"]


def test_rmd02_delivery_status_is_deterministic_and_dimensionally_truthful() -> None:
    committed = _load("machine/status/latest.json")
    assert committed == build_status(PROJECT_ROOT)
    assert validate_value(committed, PROJECT_ROOT) == []
    dimensions = committed["dimensions"]
    assert isinstance(dimensions, dict)
    assert dimensions["evidence_integrity"]["status"] == "PASS"
    assert dimensions["mechanism_implementation"]["status"] == "LOCAL_MECHANISMS_EVIDENCED"
    assert dimensions["formal_task_completion"] == {
        "status": "INCOMPLETE",
        "completed": 7,
        "planned": 51,
        "total": 58,
        "contract_version": "1.0.1",
    }
    assert dimensions["protected_oracles"]["executed"] == 0
    assert dimensions["final_acceptance"] == {
        "status": "BLOCKED",
        "passed": 0,
        "blocked": 34,
        "total": 34,
    }
    assert dimensions["production_readiness"]["status"] == "BLOCKED"
    assert dimensions["publication"]["status"] == "LOCAL_ONLY_NOT_PUBLISHED"


def test_rmd02_delivery_status_rejects_greenwashing_and_source_drift() -> None:
    committed = _load("machine/status/latest.json")

    greenwashed = copy.deepcopy(committed)
    greenwashed["dimensions"]["production_readiness"]["status"] = "PASS"
    errors = validate_value(greenwashed, PROJECT_ROOT)
    assert any(
        "schema violation at dimensions.production_readiness.status" in item for item in errors
    )
    assert "status differs from deterministic source evidence" in errors

    undercounted = copy.deepcopy(committed)
    undercounted["dimensions"]["evidence_integrity"]["verified_records"] = 57
    errors = validate_value(undercounted, PROJECT_ROOT)
    assert any(
        "schema violation at dimensions.evidence_integrity.verified_records" in item
        for item in errors
    )
    assert "status differs from deterministic source evidence" in errors


def test_rmd02_v102_package_remains_immutable_control_predecessor() -> None:
    manifest = _load(RMD02_MANIFEST_PATH.as_posix())
    assert (
        hashlib.sha256((PROJECT_ROOT / RMD02_MANIFEST_PATH).read_bytes()).hexdigest()
        == RMD02_MANIFEST_SHA256
    )
    assert manifest["package_id"] == "MMAU-ARCHIVE-TP-2026-07-22-V1.0.2"
    assert manifest["version"] == "1.0.2"
    assert manifest["status_authority"] == "machine/status/latest.json"
    legacy_entry = next(
        item for item in manifest["files"] if item["path"] == RMD02_LEGACY_MANIFEST_PATH.as_posix()
    )
    assert legacy_entry["sha256"] == RMD02_LEGACY_MANIFEST_SHA256


def test_rmd02_v102_provenance_preserves_product_semantics() -> None:
    provenance = _load("taskpack/SOURCE_PROVENANCE.v1.0.2.json")
    assert provenance["authorization"]["owner_selection"] == (
        "1: create a baseline-preserving v1.0.2 successor"
    )
    assert provenance["effective_package"]["publication_status"] == ("LOCAL_ONLY_NOT_PUBLISHED")
    assert provenance["semantic_delta"] == {
        "resolved_review_findings": ["REV-P0-003", "REV-P2-007"],
        "product_contract_changed": False,
        "task_graph_changed": False,
        "final_acceptance_thresholds_changed": False,
        "protected_oracles_executed": 0,
        "production_workflow_runs": 0,
        "remote_publications": 0,
    }


def test_rmd02_publication_scan_ignores_only_nonpublishable_test_cache(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "machine/contracts/publication_safety.json"
    contract.parent.mkdir(parents=True)
    contract.write_text(
        json.dumps({"forbidden_locator_sha256_casefold": []}),
        encoding="utf-8",
    )
    cache = tmp_path / ".hypothesis/constants/generated"
    cache.parent.mkdir(parents=True)
    cache.write_text("/" + "Users/example/cache-only\n", encoding="utf-8")
    published = tmp_path / "README.md"
    published.write_text("/" + "Users/example/must-fail\n", encoding="utf-8")

    result = scan_tree(tmp_path)

    assert result["status"] == "FAIL"
    assert result["match_counts"]["local_absolute_path"] == 1
    assert result["matched_files"] == ["README.md"]
