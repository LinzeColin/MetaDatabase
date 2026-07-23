#!/usr/bin/env python3
"""Read-only validator for the baseline-preserving v1.0.6 control package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from build_package_manifest import (
    BASELINE_PREDECESSOR_MANIFEST_PATH,
    BASELINE_PREDECESSOR_MANIFEST_SHA256,
    CONTROL_PREDECESSOR_MANIFEST_PATH,
    CONTROL_PREDECESSOR_MANIFEST_SHA256,
    FOUNDATION_PREDECESSOR_MANIFEST_PATH,
    FOUNDATION_PREDECESSOR_MANIFEST_SHA256,
    INHERITED_CONTRACT_HASHES,
    LEGACY_MANIFEST_PATH,
    LEGACY_MANIFEST_SHA256,
    MANIFEST_PATH,
    PACKAGE_ID,
    PACKAGE_VERSION,
    PREDECESSOR_MANIFEST_PATH,
    PREDECESSOR_MANIFEST_SHA256,
    build_manifest,
)
from validate_delivery_status import validate as validate_delivery_status

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_PATH = Path("taskpack/SOURCE_PROVENANCE.v1.0.6.json")
RMD06_CLEAN_MAINLINE_BASE_COMMIT = (
    "932dafae972ab00c3e2259ba3a06f6deaa8e108d"  # pragma: allowlist secret
)
CANDIDATE_SNAPSHOT = {
    "repository": "LinzeColin/MetaDatabase",
    "mainline_base_commit": RMD06_CLEAN_MAINLINE_BASE_COMMIT,
    "acceptance_remediation_base_commit": RMD06_CLEAN_MAINLINE_BASE_COMMIT,
    "shallow_checkout_fallback": "EXACT_PIN_ONLY",
}
PROTECTED_BETA_ATTEMPT_LEDGER_PATH = Path("machine/stages/S7/reviews/t0702/attempt-ledger.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_provenance(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Return the exact RMD-06 dependency and protected-Beta provenance authority."""

    root = root.resolve()
    attempt_ledger = _load(root / PROTECTED_BETA_ATTEMPT_LEDGER_PATH)
    attempt_summary = attempt_ledger.get("summary", {})
    if (
        len(attempt_ledger.get("attempts", [])) != 6
        or attempt_summary.get("controlled_main_deliveries") != 6
        or attempt_summary.get("protected_beta_dispatches") != 6
        or attempt_summary.get("protected_workflow_runs") != 6
        or attempt_summary.get("workflow_reruns") != 0
        or attempt_summary.get("latest_failure_phase") != "GITHUB_APP_TOKEN"
        or attempt_summary.get("latest_installation_token_failure_class") != "INSTALLATION_ZERO"
    ):
        raise ValueError("protected Beta attempt ledger is not the exact observed state")
    return {
        "schema_version": "moomooau.source-provenance.v7",
        "authorization": {
            "basis": (
                "Owner selected option 2 for private Governance and separately authorized "
                "one controlled main delivery plus one T0702 protected Beta dispatch; after "
                "that failed attempt and local diagnostic repair, Owner explicitly authorized "
                "controlled Stage 7 completion without artificial time or approval blockers"
            ),
            "authorized_on": "2026-07-23",
            "authorized_scope": (
                "RMD-06 dependency authentication, cloud preflight closure, one controlled "
                "historical main delivery and budget-one T0702 attempt, followed by controlled "
                "Stage 7 repair delivery and serial new first-attempt dispatches. Beta remains "
                "Raw-only with zero Gmail mutation; M3 and later Stage 7 phases require their "
                "real predecessor PASS; GitHub rerun, fixed calendar waits, manual routine "
                "approval and pre-acceptance final publication remain forbidden"
            ),
        },
        "predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-22-V1.0.5",
            "version": "1.0.5",
            "manifest": PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "control_predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-22-V1.0.4",
            "version": "1.0.4",
            "manifest": CONTROL_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": CONTROL_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "foundation_predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-22-V1.0.3",
            "version": "1.0.3",
            "manifest": FOUNDATION_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": FOUNDATION_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "baseline_predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-22-V1.0.2",
            "version": "1.0.2",
            "manifest": BASELINE_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": BASELINE_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "historical_baseline": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-20-V1.0.1",
            "version": "1.0.1",
            "manifest": LEGACY_MANIFEST_PATH.as_posix(),
            "manifest_sha256": LEGACY_MANIFEST_SHA256,
            "status": "IMMUTABLE_HISTORICAL_BASELINE",
        },
        "inherited_contract_hashes": INHERITED_CONTRACT_HASHES,
        "effective_package": {
            "package_id": PACKAGE_ID,
            "version": PACKAGE_VERSION,
            "manifest": MANIFEST_PATH.as_posix(),
            "roadmap": "taskpack/ROADMAP.v1.0.6.md",
            "status_authority": "machine/status/latest.json",
            "workflow_validator": "machine/tools/validate_workflow_matrix.py",
            "publication_status": "CONTROLLED_BETA_DELIVERY_NOT_FINAL",
        },
        "candidate_snapshot": CANDIDATE_SNAPSHOT,
        "semantic_delta": {
            "governance_visibility_changed": False,
            "dependency_credential_kind": "GITHUB_READ_ONLY_DEPLOY_KEY",
            "dependency_credential_repository_scope": "LinzeColin/Governance",
            "credential_material_in_package": False,
            "production_secret_reads_authorized": 0,
            "project_runtime_secret_reads_authorized": 0,
            "fork_pull_request_policy": ("FAIL_CLOSED_BEFORE_PROTECTED_DEPENDENCY_CHECKOUT"),
            "pull_request_target_allowed": False,
            "product_contract_changed": False,
            "task_graph_changed": False,
            "final_acceptance_thresholds_changed": False,
            "stage7_fixed_calendar_wait_removed": True,
            "protected_oracles_executed": 2,
            "protected_oracles_passed": 1,
            "protected_oracles_failed": 1,
            "production_workflow_runs": 0,
            "protected_workflow_runs": attempt_summary["protected_workflow_runs"],
            "remote_workflow_runs": attempt_summary["protected_workflow_runs"],
            "controlled_main_deliveries": attempt_summary["controlled_main_deliveries"],
            "protected_beta_dispatches": attempt_summary["protected_beta_dispatches"],
            "protected_beta_reruns": attempt_summary["workflow_reruns"],
            "private_raw_commits": 0,
            "gmail_mutations": 0,
            "protected_beta_outcome": "FAILED_GITHUB_APP_INSTALLATION_ZERO",
            "protected_beta_latest_failure_phase": "GITHUB_APP_TOKEN",
            "protected_beta_latest_installation_failure_class": "INSTALLATION_ZERO",
            "protected_beta_exact_root_cause_claimed": False,
            "protected_beta_attempt_ledger_sha256": _sha256(
                root / PROTECTED_BETA_ATTEMPT_LEDGER_PATH
            ),
            "remote_publications": 0,
        },
    }


def _validate_provenance(root: Path, failures: list[str]) -> None:
    try:
        provenance = _load(root / PROVENANCE_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        failures.append("v1.0.6 provenance is missing or invalid")
        return
    if not isinstance(provenance, dict):
        failures.append("v1.0.6 provenance must be an object")
        return
    if provenance != build_provenance(root):
        failures.append("v1.0.6 provenance differs from the exact deterministic authority")
    authorization = provenance.get("authorization", {})
    effective = provenance.get("effective_package", {})
    predecessor = provenance.get("predecessor", {})
    control_predecessor = provenance.get("control_predecessor", {})
    foundation_predecessor = provenance.get("foundation_predecessor", {})
    baseline_predecessor = provenance.get("baseline_predecessor", {})
    historical = provenance.get("historical_baseline", {})
    candidate_snapshot = provenance.get("candidate_snapshot", {})
    semantic_delta = provenance.get("semantic_delta", {})
    if not isinstance(authorization, dict):
        authorization = {}
    if not isinstance(effective, dict):
        effective = {}
    if not isinstance(predecessor, dict):
        predecessor = {}
    if not isinstance(control_predecessor, dict):
        control_predecessor = {}
    if not isinstance(foundation_predecessor, dict):
        foundation_predecessor = {}
    if not isinstance(baseline_predecessor, dict):
        baseline_predecessor = {}
    if not isinstance(historical, dict):
        historical = {}
    if not isinstance(candidate_snapshot, dict):
        candidate_snapshot = {}
    if not isinstance(semantic_delta, dict):
        semantic_delta = {}
    if (
        provenance.get("schema_version") != "moomooau.source-provenance.v7"
        or authorization.get("basis")
        != (
            "Owner selected option 2 for private Governance and separately authorized "
            "one controlled main delivery plus one T0702 protected Beta dispatch; after "
            "that failed attempt and local diagnostic repair, Owner explicitly authorized "
            "controlled Stage 7 completion without artificial time or approval blockers"
        )
        or effective.get("package_id") != PACKAGE_ID
        or effective.get("version") != PACKAGE_VERSION
        or effective.get("manifest") != MANIFEST_PATH.as_posix()
        or effective.get("roadmap") != "taskpack/ROADMAP.v1.0.6.md"
        or effective.get("status_authority") != "machine/status/latest.json"
        or effective.get("workflow_validator") != "machine/tools/validate_workflow_matrix.py"
        or effective.get("publication_status") != "CONTROLLED_BETA_DELIVERY_NOT_FINAL"
    ):
        failures.append("v1.0.6 provenance identity or authorization mismatch")
    if (
        predecessor.get("manifest") != PREDECESSOR_MANIFEST_PATH.as_posix()
        or predecessor.get("manifest_sha256") != PREDECESSOR_MANIFEST_SHA256
        or predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.5 predecessor provenance mismatch")
    if (
        control_predecessor.get("manifest") != CONTROL_PREDECESSOR_MANIFEST_PATH.as_posix()
        or control_predecessor.get("manifest_sha256") != CONTROL_PREDECESSOR_MANIFEST_SHA256
        or control_predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.4 control predecessor provenance mismatch")
    if (
        foundation_predecessor.get("manifest") != FOUNDATION_PREDECESSOR_MANIFEST_PATH.as_posix()
        or foundation_predecessor.get("manifest_sha256") != FOUNDATION_PREDECESSOR_MANIFEST_SHA256
        or foundation_predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.3 foundation predecessor provenance mismatch")
    if (
        baseline_predecessor.get("manifest") != BASELINE_PREDECESSOR_MANIFEST_PATH.as_posix()
        or baseline_predecessor.get("manifest_sha256") != BASELINE_PREDECESSOR_MANIFEST_SHA256
        or baseline_predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.2 baseline predecessor provenance mismatch")
    if (
        historical.get("manifest") != LEGACY_MANIFEST_PATH.as_posix()
        or historical.get("manifest_sha256") != LEGACY_MANIFEST_SHA256
        or historical.get("status") != "IMMUTABLE_HISTORICAL_BASELINE"
    ):
        failures.append("v1.0.1 historical provenance mismatch")
    if provenance.get("inherited_contract_hashes") != INHERITED_CONTRACT_HASHES:
        failures.append("inherited contract provenance mismatch")
    if candidate_snapshot != CANDIDATE_SNAPSHOT:
        failures.append("RMD-06 clean candidate snapshot provenance mismatch")
    if semantic_delta != {
        "governance_visibility_changed": False,
        "dependency_credential_kind": "GITHUB_READ_ONLY_DEPLOY_KEY",
        "dependency_credential_repository_scope": "LinzeColin/Governance",
        "credential_material_in_package": False,
        "production_secret_reads_authorized": 0,
        "project_runtime_secret_reads_authorized": 0,
        "fork_pull_request_policy": ("FAIL_CLOSED_BEFORE_PROTECTED_DEPENDENCY_CHECKOUT"),
        "pull_request_target_allowed": False,
        "product_contract_changed": False,
        "task_graph_changed": False,
        "final_acceptance_thresholds_changed": False,
        "stage7_fixed_calendar_wait_removed": True,
        "protected_oracles_executed": 2,
        "protected_oracles_passed": 1,
        "protected_oracles_failed": 1,
        "production_workflow_runs": 0,
        "protected_workflow_runs": 6,
        "remote_workflow_runs": 6,
        "controlled_main_deliveries": 6,
        "protected_beta_dispatches": 6,
        "protected_beta_reruns": 0,
        "private_raw_commits": 0,
        "gmail_mutations": 0,
        "protected_beta_outcome": "FAILED_GITHUB_APP_INSTALLATION_ZERO",
        "protected_beta_latest_failure_phase": "GITHUB_APP_TOKEN",
        "protected_beta_latest_installation_failure_class": "INSTALLATION_ZERO",
        "protected_beta_exact_root_cause_claimed": False,
        "protected_beta_attempt_ledger_sha256": _sha256(root / PROTECTED_BETA_ATTEMPT_LEDGER_PATH),
        "remote_publications": 0,
    }:
        failures.append("v1.0.6 semantic delta is incomplete or overstated")


def validate(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / MANIFEST_PATH
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return {"status": "FAIL", "verified_files": 0, "failures": ["manifest missing or unsafe"]}
    try:
        manifest = _load(manifest_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "verified_files": 0,
            "failures": [f"manifest is not valid readable JSON: {type(exc).__name__}"],
        }
    if not isinstance(manifest, dict):
        return {
            "status": "FAIL",
            "verified_files": 0,
            "failures": ["manifest root must be an object"],
        }

    failures: list[str] = []
    seen: set[str] = set()
    entries = manifest.get("files", [])
    if not isinstance(entries, list):
        entries = []
        failures.append("manifest files must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append("manifest entry must be an object")
            continue
        relative = entry.get("path", "")
        if not isinstance(relative, str) or not relative:
            failures.append("manifest path is invalid")
            continue
        if relative in seen:
            failures.append("duplicate manifest path")
            continue
        seen.add(relative)
        candidate = root / relative
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError:
            failures.append("manifest path escapes project root")
            continue
        if not path.is_file() or candidate.is_symlink():
            failures.append(f"missing or unsafe file: {relative}")
            continue
        if path.stat().st_size != entry.get("bytes") or _sha256(path) != entry.get("sha256"):
            failures.append(f"byte mismatch: {relative}")

    if manifest.get("package_id") != PACKAGE_ID or manifest.get("version") != PACKAGE_VERSION:
        failures.append("manifest package identity mismatch")
    if manifest.get("file_count_excluding_manifest") != len(entries):
        failures.append("manifest count mismatch")
    if MANIFEST_PATH.as_posix() in seen:
        failures.append("manifest must not hash itself")
    legacy_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("path") == LEGACY_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if legacy_entry is None or legacy_entry.get("sha256") != LEGACY_MANIFEST_SHA256:
        failures.append("legacy v1.0.1 manifest artifact is not preserved")
    predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("path") == PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if predecessor_entry is None or predecessor_entry.get("sha256") != PREDECESSOR_MANIFEST_SHA256:
        failures.append("predecessor v1.0.5 manifest artifact is not preserved")
    control_predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("path") == CONTROL_PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if (
        control_predecessor_entry is None
        or control_predecessor_entry.get("sha256") != CONTROL_PREDECESSOR_MANIFEST_SHA256
    ):
        failures.append("control predecessor v1.0.4 manifest artifact is not preserved")
    foundation_predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("path") == FOUNDATION_PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if (
        foundation_predecessor_entry is None
        or foundation_predecessor_entry.get("sha256") != FOUNDATION_PREDECESSOR_MANIFEST_SHA256
    ):
        failures.append("foundation predecessor v1.0.3 manifest artifact is not preserved")
    baseline_predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("path") == BASELINE_PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if (
        baseline_predecessor_entry is None
        or baseline_predecessor_entry.get("sha256") != BASELINE_PREDECESSOR_MANIFEST_SHA256
    ):
        failures.append("baseline predecessor v1.0.2 manifest artifact is not preserved")
    for relative, expected in INHERITED_CONTRACT_HASHES.items():
        entry = next(
            (item for item in entries if isinstance(item, dict) and item.get("path") == relative),
            None,
        )
        if entry is None or entry.get("sha256") != expected:
            failures.append(f"inherited contract is not preserved: {relative}")

    try:
        expected = build_manifest(root)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        failures.append(f"canonical manifest selection failed: {type(exc).__name__}")
    else:
        if manifest != expected:
            failures.append("manifest differs from the canonical v1.0.6 package selection")

    _validate_provenance(root, failures)
    status_result = validate_delivery_status(root)
    if status_result["status"] != "PASS":
        failures.append("sole delivery status authority failed validation")
    return {
        "status": "PASS" if not failures else "FAIL",
        "package_id": manifest.get("package_id"),
        "version": manifest.get("version"),
        "verified_files": len(seen),
        "legacy_manifest_sha256": LEGACY_MANIFEST_SHA256,
        "status_authority": manifest.get("status_authority"),
        "production_ready": status_result.get("production_readiness") == "PASS",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = validate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
