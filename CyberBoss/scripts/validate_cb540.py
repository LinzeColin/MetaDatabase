#!/usr/bin/env python3
"""Fail-closed local seal for the CB-540 real-cloud final decision."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-540"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB530_CLOSURE = "5e01bb9fc61fd932359e32667fc2cd5495aa724d"
IMPLEMENTATION_COMMIT = "fd3cd1e19d70caa148c3785288aaabfb909fed85"
IMPLEMENTATION_TREE = "9bc30622d34b11271c390420fa37e89d1ed1e5d8"
RELEASE_SOURCE_TREE = "bccd6aa8ade7b9fa19c6c54f5472df342844ebca"
SOURCE_ARCHIVE_SHA256 = "288147fde6622cb76c5e21a3600d16d71134510b9215554a8a8261bbe309c1c2"
RELEASE_MANIFEST_SHA256 = "4829f41e002e5c6fa242182d851317df376d6f407a8c593577612af738490ff7"
PREVIOUS_RELEASE = "25670bf32c6d27e3668fcf59bc9ab754035e161d"
LATEST_BACKUP_ID = "backup_5233145600b2b004151de2bb"
CRITICAL_ACCEPTANCE = {
    "FA-AC-001": "PASS", "FA-AC-020": "PASS", "FA-AC-021": "PASS",
    "FA-AC-022": "PASS", "FA-AC-023": "PASS", "FA-AC-024": "PASS",
    "FA-AC-025": "PASS", "FA-AC-027": "PASS", "FA-AC-028": "PASS",
    "FA-AC-029": "PASS", "FA-AC-030": "PASS",
}
ROUTER_RESULT = {
    "task_id": "CB-540", "selected_skill": "output-skill",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED", "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0, "actual_skill_body_loads": 0,
    "fallback": "machine/skill_microplaybooks.json",
}
DEPLOYMENT_SUBJECT = {
    "product_version": PRODUCT_VERSION,
    "taskpack_version": TASKPACK_VERSION,
    "deployed_commit": IMPLEMENTATION_COMMIT,
    "deployed_tree": IMPLEMENTATION_TREE,
    "release_source_tree": RELEASE_SOURCE_TREE,
    "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
    "release_manifest_sha256": RELEASE_MANIFEST_SHA256,
    "current_release": IMPLEMENTATION_COMMIT,
    "previous_release": PREVIOUS_RELEASE,
    "latest_backup_id": LATEST_BACKUP_ID,
    "r2_restore": "verified_put_get_hash_and_isolated_restore",
    "oci_daily_par": "activation_pending_write_only_par",
    "self_heal": "verified_channel_pending_no_restart",
    "live_rollback": "verified_current_previous_current",
}
DEPLOYMENT_DIGEST = "feb6ee99d3c13960a93d912f7878c48b51c587419618b79cef75eea2a890a5c9"
EVIDENCE_FILES = {"summary.json", "subject.json", "final-decision.md", "pass-gate-checklist.md"}
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def git(*args: str, check: bool = True) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "git_failed")
    return result.returncode, result.stdout.rstrip()


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("json_root")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def report(errors: list[str], code: str, condition: bool) -> None:
    if not condition:
        errors.append(code)


def validate_state(errors: list[str]) -> None:
    try:
        state = load_json(PROJECT / "machine/facts/task_state.json")
    except (OSError, ValueError, TypeError):
        errors.append("task_state_read")
        return
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    expected = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100", "CB-110", "CB-120", "CB-130", "CB-140",
        "CB-200", "CB-210", "CB-220", "CB-230", "CB-240", "CB-300", "CB-310", "CB-320", "CB-330", "CB-340",
        "CB-400", "CB-410", "CB-420", "CB-430", "CB-440", "CB-500", "CB-510", "CB-520", "CB-530", "CB-540",
    )
    report(errors, "task_state_passed", all(statuses.get(task) == "passed" for task in expected))
    report(errors, "task_state_pg5", state.get("pass_gates", {}).get("PG-5") == "not_started")
    report(errors, "task_state_current_run", state.get("current_run") == {
        "run_id": "P5.5", "gate_id": None, "task_id": "CB-540",
        "scope": "exact_mvp_degraded_decision_subject_seal_and_real_selfheal_rollback", "status": "passed",
    })
    overlay = state.get("taskpack_overlay", {})
    report(errors, "task_state_overlay", all((
        state.get("schema_version") == 1,
        state.get("taskpack_version") == TASKPACK_VERSION,
        overlay.get("product_version") == PRODUCT_VERSION,
        overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256,
        overlay.get("skill_router") == ROUTER_RESULT,
        overlay.get("formal_final_acceptance") == "blocked_external_independent_contexts_not_run",
        overlay.get("cb_540_implementation_commit") == IMPLEMENTATION_COMMIT,
        overlay.get("cb_540_implementation_tree") == IMPLEMENTATION_TREE,
        overlay.get("cb_540_release_source_tree") == RELEASE_SOURCE_TREE,
        overlay.get("cb_540_release_source_archive_sha256") == SOURCE_ARCHIVE_SHA256,
        overlay.get("cb_540_release_manifest_sha256") == RELEASE_MANIFEST_SHA256,
        overlay.get("cb_540_release_current") == "verified",
        overlay.get("cb_540_release_previous") == "verified",
        overlay.get("cb_540_self_heal") == "verified_channel_pending_no_restart",
        overlay.get("cb_540_self_heal_timer") == "enabled_active",
        overlay.get("cb_540_live_rollback") == "verified_current_previous_current",
        overlay.get("cb_540_controlled_release_transitions") == 3,
        overlay.get("cb_540_candidate_decision") == "MVP_DEGRADED",
        overlay.get("cb_540_deployment_digest") == DEPLOYMENT_DIGEST,
        overlay.get("control_plane_llm_calls") == 0,
        overlay.get("operations_llm_calls") == 0,
        overlay.get("macos_launchd_dependency") is False,
    )))


def validate_evidence(errors: list[str]) -> None:
    inventory = {item.name for item in EVIDENCE.iterdir() if item.is_file()} if EVIDENCE.is_dir() else set()
    report(errors, "evidence_inventory", inventory == EVIDENCE_FILES)
    if inventory != EVIDENCE_FILES:
        return
    try:
        summary = load_json(EVIDENCE / "summary.json")
        subject = load_json(EVIDENCE / "subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("evidence_json")
        return
    report(errors, "deployment_digest", canonical_sha256(DEPLOYMENT_SUBJECT) == DEPLOYMENT_DIGEST)
    report(errors, "summary_contract", all((
        summary.get("schema_version") == "cyberboss.cb540.final-decision-summary.v1",
        summary.get("task_id") == "CB-540", summary.get("product_version") == PRODUCT_VERSION,
        summary.get("taskpack_version") == TASKPACK_VERSION, summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256,
        summary.get("cb_530_closure_commit") == CB530_CLOSURE,
        summary.get("implementation_commit") == IMPLEMENTATION_COMMIT, summary.get("implementation_tree") == IMPLEMENTATION_TREE,
        summary.get("release") == {
            "current": IMPLEMENTATION_COMMIT, "previous": PREVIOUS_RELEASE, "source_tree": RELEASE_SOURCE_TREE,
            "source_archive_sha256": SOURCE_ARCHIVE_SHA256, "release_manifest_sha256": RELEASE_MANIFEST_SHA256,
            "immutable": True, "current_previous_pointer": "verified",
        },
        summary.get("skill_router") == ROUTER_RESULT,
        summary.get("critical_acceptance") == CRITICAL_ACCEPTANCE,
        summary.get("crossplane_receipts", {}).get("cloudflare_access_unauthenticated") == "302",
        summary.get("crossplane_receipts", {}).get("private_database_daily_sync") == "success_no_clone",
        summary.get("crossplane_receipts", {}).get("private_database_material_sync") == "success_no_clone",
        summary.get("crossplane_receipts", {}).get("self_heal") == "verified_exact_channel_pending_no_active_process_restart",
        summary.get("crossplane_receipts", {}).get("live_rollback") == "verified_current_previous_current",
        summary.get("crossplane_receipts", {}).get("live_rollback_transitions") == 3,
        summary.get("backup_restore_reuse", {}).get("latest_backup_id") == LATEST_BACKUP_ID,
        summary.get("backup_restore_reuse", {}).get("r2_restore") == DEPLOYMENT_SUBJECT["r2_restore"],
        summary.get("backup_restore_reuse", {}).get("oci_daily_par") == DEPLOYMENT_SUBJECT["oci_daily_par"],
        summary.get("development_candidate", {}).get("decision") == "MVP_DEGRADED",
        summary.get("development_candidate", {}).get("unaccepted_p0") == [],
        summary.get("development_candidate", {}).get("unaccepted_p1") == [],
        isinstance(summary.get("development_candidate", {}).get("degraded_components"), list),
        summary.get("safety", {}).get("control_plane_llm_calls") == 0,
        summary.get("safety", {}).get("operations_llm_calls") == 0,
        summary.get("safety", {}).get("real_time_waits") == 0,
        summary.get("safety", {}).get("macos_launchd_dependency") is False,
        summary.get("safety", {}).get("private_database_clone") is False,
        summary.get("formal_final_acceptance") == "BLOCKED_EXTERNAL_INDEPENDENT_CONTEXTS_NOT_RUN",
        summary.get("result") == "passed_mvp_degraded_subject_ready_for_pg5",
        summary.get("next_native_node") == "PG-5",
    )))
    report(errors, "subject_contract", all((
        subject.get("schema_version") == "cyberboss.cb540.subject.v1", subject.get("task_id") == "CB-540",
        subject.get("product_version") == PRODUCT_VERSION, subject.get("taskpack_version") == TASKPACK_VERSION,
        subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256, subject.get("cb_530_closure_commit") == CB530_CLOSURE,
        subject.get("implementation_commit") == IMPLEMENTATION_COMMIT, subject.get("implementation_tree") == IMPLEMENTATION_TREE,
        subject.get("release_source_tree") == RELEASE_SOURCE_TREE, subject.get("source_archive_sha256") == SOURCE_ARCHIVE_SHA256,
        subject.get("release_manifest_sha256") == RELEASE_MANIFEST_SHA256, subject.get("deployment_digest") == DEPLOYMENT_DIGEST,
        subject.get("summary_sha256") == sha256(EVIDENCE / "summary.json"),
        subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256"),
        subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256"),
        subject.get("run_contract_sha256") == sha256(PROJECT / "docs/governance/RUN_CONTRACT_P5_5_CB_540.md"),
        subject.get("final_decision_sha256") == sha256(EVIDENCE / "final-decision.md"),
        subject.get("pass_gate_checklist_sha256") == sha256(EVIDENCE / "pass-gate-checklist.md"),
        subject.get("deployment_current") == "verified_cb540_immutable_release",
        subject.get("deployment_previous") == "verified_cb530_immutable_release",
        subject.get("self_heal") == DEPLOYMENT_SUBJECT["self_heal"],
        subject.get("live_rollback") == DEPLOYMENT_SUBJECT["live_rollback"],
        subject.get("development_candidate") == "MVP_DEGRADED",
        subject.get("formal_final_acceptance") == "BLOCKED_EXTERNAL_INDEPENDENT_CONTEXTS_NOT_RUN",
        all(subject.get(key) == 0 for key in ("control_plane_llm_calls", "operations_llm_calls", "real_time_waits")),
        subject.get("macos_launchd_dependency") is False,
    )))
    decision = (EVIDENCE / "final-decision.md").read_text(encoding="utf-8")
    checklist = (EVIDENCE / "pass-gate-checklist.md").read_text(encoding="utf-8")
    report(errors, "evidence_markdown", all(marker in decision + checklist for marker in (
        "MVP_DEGRADED", "channel_pending", "current → previous → current", "BLOCKED", "launchd",
    )))
    for candidate in EVIDENCE.iterdir():
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8")
            if SECRET_PATTERN.search(content) or "/Users/" in content or "/var/lib/" in content:
                errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")


def validate_source(errors: list[str]) -> None:
    required = (
        PROJECT / "ops/systemd/cb540-selfheal-health.sh",
        PROJECT / "ops/systemd/cb540-selfheal-degraded-channel.conf",
        PROJECT / "ops/systemd/test/cb540-selfheal-health.test.js",
        PROJECT / "docs/governance/RUN_CONTRACT_P5_5_CB_540.md",
    )
    report(errors, "implementation_files", all(path.is_file() for path in required))
    report(errors, "implementation_executable", (PROJECT / "ops/systemd/cb540-selfheal-health.sh").stat().st_mode & 0o111 != 0)
    report(errors, "implementation_commit", git("cat-file", "-e", f"{IMPLEMENTATION_COMMIT}^{{commit}}", check=False)[0] == 0)
    report(errors, "implementation_tree", git("rev-parse", f"{IMPLEMENTATION_COMMIT}^{{tree}}", check=False)[1] == IMPLEMENTATION_TREE)
    report(errors, "implementation_ancestor", git("merge-base", "--is-ancestor", IMPLEMENTATION_COMMIT, "HEAD", check=False)[0] == 0)
    report(errors, "frozen_design_unchanged", git("diff", "--quiet", IMPLEMENTATION_COMMIT, "--", "CyberBoss/docs/product_design/v0.0.0.4", check=False)[0] == 0)
    report(errors, "diff_check", git("diff", "--check", IMPLEMENTATION_COMMIT, "HEAD", check=False)[0] == 0)
    for name, command in (
        ("shell_syntax", ["bash", "-n", str(PROJECT / "ops/systemd/cb540-selfheal-health.sh")]),
        ("focused_test", ["node", "--test", str(PROJECT / "ops/systemd/test/cb540-selfheal-health.test.js")]),
    ):
        result = subprocess.run(command, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if result.returncode != 0:
            errors.append(f"{name}_failed")


def main() -> int:
    errors: list[str] = []
    validate_state(errors)
    validate_evidence(errors)
    validate_source(errors)
    print(f"mode=final\nerrors={len(errors)}")
    for error in errors:
        print(error)
    print("CB540_VALIDATION=PASS" if not errors else "CB540_VALIDATION=FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
