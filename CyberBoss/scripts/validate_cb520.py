#!/usr/bin/env python3
"""Fail-closed local seal for the CB-520 finite production canary receipt."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-520"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB510_CLOSURE = "2770380d3efa93b5632ef03581c0d76088b38cc2"
IMPLEMENTATION_COMMIT = "bb5a201a0aec38117a7e14f470662b6f45bd49c7"
IMPLEMENTATION_TREE = "99ae8068eee9ae8b5bd78207386eb65067fe7c30"
PREVIOUS_RELEASE = "82b47668c33cc403fee9194ad42b77e49c8b7da3"
SOURCE_ARCHIVE_SHA256 = "78b089303e0fc7a846d0c862fd45c70c5a597d898f2a8cb45d7bd317ffa1fa63"
CURRENT_MANIFEST_SHA256 = "d8d6bf36069f66ca6e013c119e5a84e3d03875955550fdeeca0b03ce99c710e6"
ROUTER_RESULT = {
    "task_id": "CB-520",
    "selected_skill": "webapp-testing",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 0,
    "fallback": "machine/skill_microplaybooks.json",
}
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def git(*args: str, check: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git_failed")
    return result.returncode, result.stdout.rstrip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    passed = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040",
        "CB-100", "CB-110", "CB-120", "CB-130", "CB-140",
        "CB-200", "CB-210", "CB-220", "CB-230", "CB-240",
        "CB-300", "CB-310", "CB-320", "CB-330", "CB-340",
        "CB-400", "CB-410", "CB-420", "CB-430", "CB-440",
        "CB-500", "CB-510", "CB-520",
    )
    report(errors, "task_state_passed", all(statuses.get(task) == "passed" for task in passed))
    report(
        errors,
        "task_state_future",
        all(statuses.get(task) == "not_started" for task in ("CB-530", "CB-540"))
        and state.get("pass_gates", {}).get("PG-5") == "not_started",
    )
    report(
        errors,
        "task_state_current_run",
        state.get("current_run") == {
            "run_id": "P5.3",
            "gate_id": None,
            "task_id": "CB-520",
            "scope": "finite_request_count_canary_live_rollback_and_restore",
            "status": "passed",
        },
    )
    overlay = state.get("taskpack_overlay", {})
    report(
        errors,
        "task_state_overlay",
        state.get("schema_version") == 1
        and state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("skill_router") == ROUTER_RESULT
        and overlay.get("acceptance_state") == "passed_with_explicit_pending"
        and overlay.get("acceptance_scope") == "real_request_count_canary_with_fail_closed_channel_pending"
        and overlay.get("channel_activation") == "pending_missing_real_wechat_credential"
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("live_request_count_canary") == "verified"
        and overlay.get("live_rollback") == "verified"
        and overlay.get("cb_520_implementation_commit") == IMPLEMENTATION_COMMIT
        and overlay.get("cb_520_implementation_tree") == IMPLEMENTATION_TREE
        and overlay.get("cb_520_release_current") == "verified"
        and overlay.get("cb_520_release_previous") == "verified"
        and overlay.get("cb_520_controlled_release_transitions") == 3
        and overlay.get("cb_520_global_status_refresh") == "verified"
        and overlay.get("cb_520_tunnel_recovery") == "verified"
        and overlay.get("formal_final_acceptance") == "activation_pending",
    )


def validate_evidence(errors: list[str]) -> None:
    expected_inventory = {
        "summary.json", "subject.json", "production-canary.md", "accelerated-reliability.md",
    }
    inventory = {candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()} if EVIDENCE.is_dir() else set()
    report(errors, "evidence_inventory", inventory == expected_inventory)
    if inventory != expected_inventory:
        return
    try:
        summary = load_json(EVIDENCE / "summary.json")
        subject = load_json(EVIDENCE / "subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("evidence_json")
        return
    report(
        errors,
        "summary_contract",
        summary.get("schema_version") == "cyberboss.cb520.canary-summary.v1"
        and summary.get("task_id") == "CB-520"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("cb_510_closure_commit") == CB510_CLOSURE
        and summary.get("implementation_commit") == IMPLEMENTATION_COMMIT
        and summary.get("implementation_tree") == IMPLEMENTATION_TREE
        and summary.get("previous_release_commit") == PREVIOUS_RELEASE
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("acceptance") == {
            "FA-AC-018": "passed_bounded_restart_and_rollback_recovery",
            "FA-AC-019": "passed_immutable_current_previous_release_transition",
            "FA-AC-023": "passed_finite_request_count_without_time_wait",
            "real_wechat": "pending_missing_real_wechat_credential",
        }
        and summary.get("release", {}).get("current_manifest_sha256") == CURRENT_MANIFEST_SHA256
        and summary.get("release", {}).get("source_archive_sha256") == SOURCE_ARCHIVE_SHA256
        and summary.get("release", {}).get("rollback_to_previous") == "verified"
        and summary.get("release", {}).get("restore_to_current") == "verified"
        and summary.get("canary", {}).get("loopback_healthz") == "200"
        and summary.get("canary", {}).get("timeline") == "200"
        and summary.get("canary", {}).get("protected_status_authorized") == "200"
        and summary.get("canary", {}).get("protected_status_anonymous") == "401"
        and summary.get("canary", {}).get("readyz") == "503_channel_pending"
        and summary.get("canary", {}).get("public_access_challenge") == "302"
        and summary.get("canary", {}).get("controlled_release_transitions") == 3
        and summary.get("canary", {}).get("channel_delivery") == "pending_missing_real_wechat_credential"
        and summary.get("runtime", {}).get("status_phase") == "P5.3"
        and summary.get("runtime", {}).get("status_task_id") == "CB-520"
        and summary.get("runtime", {}).get("healthy") is True
        and summary.get("runtime", {}).get("ready") is False
        and summary.get("runtime", {}).get("runtime_component") is True
        and summary.get("runtime", {}).get("channel_component") is False
        and summary.get("runtime", {}).get("bridge_component") is False
        and summary.get("runtime", {}).get("recovery_llm_call") is False
        and summary.get("runtime", {}).get("control_plane_llm_calls") == 0
        and summary.get("runtime", {}).get("operations_llm_calls") == 0
        and summary.get("platform", {}).get("cloud_service") == "active_enabled"
        and summary.get("platform", {}).get("dedicated_tunnel") == "active_enabled_recovered_after_controlled_switch"
        and summary.get("platform", {}).get("global_status") == "verified_post_canary_refresh"
        and summary.get("platform", {}).get("canonical_state") == "verified_no_clone_material_history_retained"
        and summary.get("safety") == {
            "real_time_waits": 0,
            "macos_launchd_dependency": False,
            "private_database_clone": False,
            "simulator_started": False,
            "simulator_claimed_as_real": False,
            "pending_claimed_as_ready": False,
        }
        and summary.get("result") == "passed_with_explicit_wechat_pending"
        and summary.get("next_native_node") == "CB-530",
    )
    report(
        errors,
        "subject_contract",
        subject.get("schema_version") == "cyberboss.cb520.subject.v1"
        and subject.get("task_id") == "CB-520"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("cb_510_closure_commit") == CB510_CLOSURE
        and subject.get("implementation_commit") == IMPLEMENTATION_COMMIT
        and subject.get("implementation_tree") == IMPLEMENTATION_TREE
        and subject.get("previous_release_commit") == PREVIOUS_RELEASE
        and subject.get("summary_sha256") == sha256(EVIDENCE / "summary.json")
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("deployment_current") == "verified_cb520_immutable_release"
        and subject.get("deployment_previous") == "verified_cb510_immutable_release"
        and subject.get("live_request_count_canary") == "verified_finite_no_wait"
        and subject.get("live_rollback") == "verified_previous_then_restore_current"
        and subject.get("global_status") == "verified_post_canary_refresh"
        and subject.get("channel_activation") == "pending_missing_real_wechat_credential"
        and all(subject.get(key) == 0 for key in ("control_plane_llm_calls", "operations_llm_calls", "real_time_waits"))
        and subject.get("macos_launchd_dependency") is False,
    )
    production = (EVIDENCE / "production-canary.md").read_text(encoding="utf-8")
    reliability = (EVIDENCE / "accelerated-reliability.md").read_text(encoding="utf-8")
    report(
        errors,
        "evidence_markdown",
        "current → previous → current" in production
        and "pending_missing_real_wechat_credential" in production
        and "真实时间" in reliability
        and "R2/OCI" in reliability,
    )
    for path in EVIDENCE.iterdir():
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if SECRET_PATTERN.search(content) or "/Users/" in content or "/var/lib/" in content:
            errors.append(f"evidence_sensitive_or_absolute:{path.name}")


def validate_anchors(errors: list[str]) -> None:
    report(errors, "cb510_anchor", git("merge-base", "--is-ancestor", CB510_CLOSURE, IMPLEMENTATION_COMMIT, check=False)[0] == 0)
    report(errors, "implementation_commit", git("cat-file", "-e", f"{IMPLEMENTATION_COMMIT}^{{commit}}", check=False)[0] == 0)
    report(errors, "implementation_tree", git("rev-parse", f"{IMPLEMENTATION_COMMIT}^{{tree}}", check=False)[1] == IMPLEMENTATION_TREE)
    report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", IMPLEMENTATION_COMMIT, "HEAD", check=False)[0] == 0)
    report(errors, "frozen_design_unchanged", git("diff", "--quiet", IMPLEMENTATION_COMMIT, "--", "CyberBoss/docs/product_design/v0.0.0.4", check=False)[0] == 0)
    report(errors, "diff_check", git("diff", "--check", CB510_CLOSURE, "HEAD", check=False)[0] == 0)


def validate_local_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P5_3_CB_520.md").read_text(encoding="utf-8")
    canary = (PROJECT / "app/scripts/cb520-canary.js").read_text(encoding="utf-8")
    for marker in (
        "P5.3 / CB-520", PRODUCT_VERSION, "current", "previous", "Cloudflare",
        "Private-Database", "真实时间", "WeChat",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract_marker:{marker}")
    for marker in (
        "evaluateInboundPolicy", "handleStopCommand", "runtime_turn_start_calls",
        "control_plane_llm_calls", "real_time_waits", "simulator_started",
    ):
        if marker not in canary:
            errors.append(f"canary_marker:{marker}")
    if "launchctl" in canary.lower() or "launchdaemon" in canary.lower():
        errors.append("canary_macos_launchd")


def validate_focused_tests(errors: list[str]) -> None:
    result = subprocess.run(
        ["node", "--test", "test/cb520-canary.test.js"],
        cwd=PROJECT / "app",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=300,
    )
    if result.returncode != 0 or "fail 0" not in result.stdout:
        errors.append("cb520_canary_tests")


def validate() -> list[str]:
    errors: list[str] = []
    report(errors, "branch_scope", git("branch", "--show-current")[1].startswith("codex/cyberboss-"))
    validate_state(errors)
    validate_evidence(errors)
    validate_anchors(errors)
    validate_local_contract(errors)
    validate_focused_tests(errors)
    return errors


def main() -> int:
    errors = validate()
    print("mode=final")
    print(f"errors={len(errors)}")
    if errors:
        for issue in errors:
            print(f"ERROR={issue}")
        print("CB520_VALIDATION=FAIL")
        return 1
    print("CB520_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
