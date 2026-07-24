from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast

from build_delivery_status import build_status
from build_package_manifest import INHERITED_CONTRACT_HASHES
from validate_evidence import PROJECT_ROOT
from validate_workflow_matrix import MATRIX_PATH, validate, validate_contract

RMD03_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.3.json")
RMD03_MANIFEST_SHA256 = "301fa1c6f5c46760c4aa3a7092bf0be77ca1a2e974e7b65e8b53dcf90db9925e"
RMD03_PREDECESSOR_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.2.json")
RMD03_PREDECESSOR_SHA256 = "6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3"
RMD03_LEGACY_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.1.json")
RMD03_LEGACY_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"


def _load(relative: str | Path) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8")),
    )


def test_rmd03_matrix_is_exact_and_binds_the_four_workflows() -> None:
    matrix = _load(MATRIX_PATH)
    assert validate_contract(PROJECT_ROOT, matrix) == []
    assert [entry["stage_id"] for entry in matrix["entries"]] == ["S3", "S4", "S5", "S6"]
    assert matrix["observation"] == {
        "observed_at_utc": "2026-07-22T08:25:00Z",
        "status": "PASS",
        "executed_entries": 4,
        "cumulative_passed": 4,
        "historical_fail_closed": 4,
        "tree_mutations": 0,
        "protected_oracles_executed": 0,
        "production_workflow_runs": 0,
        "remote_workflow_runs": 0,
        "external_writes": 0,
        "remote_publications": 0,
    }


def test_rmd03_matrix_rejects_mode_and_observation_greenwashing() -> None:
    matrix = _load(MATRIX_PATH)

    missing_mode = copy.deepcopy(matrix)
    missing_mode["entries"][0]["workflow_command"] = missing_mode["entries"][0][
        "workflow_command"
    ].replace(" --cumulative-final", "")
    assert "S3 command or expectation drift" in validate_contract(PROJECT_ROOT, missing_mode)

    remote_greenwashing = copy.deepcopy(matrix)
    remote_greenwashing["observation"]["remote_workflow_runs"] = 1
    assert any(
        "schema violation at observation.remote_workflow_runs" in error
        for error in validate_contract(PROJECT_ROOT, remote_greenwashing)
    )


def test_rmd03_offline_replay_passes_and_historical_defaults_remain_closed() -> None:
    governance_value = os.environ.get("MOOMOOAU_GOVERNANCE_ROOT")
    assert governance_value, "MOOMOOAU_GOVERNANCE_ROOT must name the pinned Governance checkout"
    result = validate(PROJECT_ROOT, Path(governance_value), execute=True)
    assert result["status"] == "PASS"
    assert result["tree_unchanged"] is True
    assert len(result["results"]) == 8
    cumulative = [item for item in result["results"] if item["mode"] == "CUMULATIVE_FINAL"]
    historical = [item for item in result["results"] if item["mode"] == "HISTORICAL_DEFAULT"]
    assert len(cumulative) == 4
    assert all(item["validator_status"] == "PASS" and item["exit_code"] == 0 for item in cumulative)
    assert len(historical) == 4
    assert all(
        item["validator_status"] == "BLOCKED" and item["exit_code"] == 1 for item in historical
    )
    assert all(item["zero_external_effect_signals"] is True for item in result["results"])
    assert result["protected_oracles_executed"] == 0
    assert result["production_workflow_runs"] == 0
    assert result["remote_workflow_runs"] == 0
    assert result["external_writes"] == 0
    assert result["remote_publications"] == 0


def test_rmd03_preserves_both_predecessors_and_all_frozen_contracts() -> None:
    assert (
        hashlib.sha256((PROJECT_ROOT / RMD03_PREDECESSOR_PATH).read_bytes()).hexdigest()
        == RMD03_PREDECESSOR_SHA256
    )
    assert (
        hashlib.sha256((PROJECT_ROOT / RMD03_LEGACY_PATH).read_bytes()).hexdigest()
        == RMD03_LEGACY_SHA256
    )
    for relative, expected in INHERITED_CONTRACT_HASHES.items():
        assert hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest() == expected


def test_rmd03_resolution_remains_preserved_in_the_current_successor_status() -> None:
    status = _load("machine/status/latest.json")
    assert status == build_status(PROJECT_ROOT)
    assert tuple(int(part) for part in status["package_version"].split(".")) >= (1, 0, 4)
    assert {
        "REV-P0-002",
        "REV-P0-003",
        "REV-P1-004",
        "REV-P2-007",
    }.issubset(status["resolved_review_findings"])
    assert "RMD-03_CUMULATIVE_CI_PENDING" not in status["blockers"]
    assert "RMD-04_PRODUCTION_COMPOSITION_PENDING" not in status["blockers"]
    assert status["dimensions"]["formal_task_completion"]["completed"] == 7
    assert status["dimensions"]["protected_oracles"]["executed"] == 0
    assert status["dimensions"]["final_acceptance"]["passed"] == 0
    assert status["dimensions"]["production_readiness"]["status"] == "BLOCKED"
    assert status["dimensions"]["publication"]["status"] == "LOCAL_ONLY_NOT_PUBLISHED"


def test_rmd03_v103_package_is_the_immutable_direct_predecessor() -> None:
    assert hashlib.sha256((PROJECT_ROOT / RMD03_MANIFEST_PATH).read_bytes()).hexdigest() == (
        RMD03_MANIFEST_SHA256
    )
    manifest = _load(RMD03_MANIFEST_PATH)
    assert manifest["package_id"] == "MMAU-ARCHIVE-TP-2026-07-22-V1.0.3"
    assert manifest["version"] == "1.0.3"
    assert manifest["predecessor"] == {
        "path": RMD03_PREDECESSOR_PATH.as_posix(),
        "sha256": RMD03_PREDECESSOR_SHA256,
        "status": "IMMUTABLE_CONTROL_PREDECESSOR",
    }
    assert manifest["legacy_baseline"] == {
        "path": RMD03_LEGACY_PATH.as_posix(),
        "sha256": RMD03_LEGACY_SHA256,
        "status": "IMMUTABLE_HISTORICAL_ARTIFACT",
    }
    provenance = _load("taskpack/SOURCE_PROVENANCE.v1.0.3.json")
    assert provenance["effective_package"]["manifest"] == RMD03_MANIFEST_PATH.as_posix()
    assert provenance["semantic_delta"]["resolved_review_findings"] == ["REV-P1-004"]
