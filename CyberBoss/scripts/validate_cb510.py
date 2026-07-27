#!/usr/bin/env python3
"""Fail-closed local seal validator for the real CB-510 activation receipt.

The validator never contacts providers. Provider facts are represented only by the
redacted, commit-bound CB-510 Subject and summary; any unavailable capability must
remain an explicit pending value instead of becoming a false green claim.
"""

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
EVIDENCE = PROJECT / "docs/evidence/CB-510"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB500_CLOSURE = "b219606f5f395624775ce761f2b2be6a55aab75e"
IMPLEMENTATION_COMMIT = "82b47668c33cc403fee9194ad42b77e49c8b7da3"
IMPLEMENTATION_TREE = "0a472d2846d6478e01f3d392624ab2c825ad7b40"
ROUTER_RESULT = {
    "task_id": "CB-510",
    "selected_skill": "webapp-testing",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 0,
    "fallback": "machine/skill_microplaybooks.json",
}
ACCEPTANCE = {
    "FA-AC-020": "pending_missing_real_wechat_credential",
    "FA-AC-021": "passed_real_codex_login_and_loopback_runtime",
    "FA-AC-022": "passed_owner_only_access_dns_and_protected_status",
    "FA-AC-028": "passed_redacted_timeline_and_evidence",
    "FA-AC-031": "passed_chinese_timeline_and_global_status",
}
EXTERNAL_ACTIVATION = {
    "candidate_installation": "verified",
    "current_switch": "verified",
    "private_database": "verified",
    "cloudflare_access": "verified",
    "dns_route": "verified",
    "timeline": "verified",
    "global_status": "verified",
    "self_heal": "verified_systemd",
    "timer": "verified_daily_and_material",
    "service": "verified",
    "channel_wechat": "pending_missing_real_credential",
    "access_service_token": "pending_minimal_scope_unavailable",
    "live_request_count_canary": "activation_pending_next_cb520",
    "live_rollback": "activation_pending_next_cb520",
    "r2": "activation_pending_next_cb530",
    "oci": "activation_pending_next_cb530",
    "analytics": "activation_pending_next_cb540",
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
    prior = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040",
        "CB-100", "CB-110", "CB-120", "CB-130", "CB-140",
        "CB-200", "CB-210", "CB-220", "CB-230", "CB-240",
        "CB-300", "CB-310", "CB-320", "CB-330", "CB-340",
        "CB-400", "CB-410", "CB-420", "CB-430", "CB-440", "CB-500",
    )
    report(errors, "task_state_prior", all(statuses.get(task) == "passed" for task in prior))
    report(errors, "task_state_cb510", statuses.get("CB-510") == "passed")
    report(
        errors,
        "task_state_future",
        all(statuses.get(task) == "not_started" for task in ("CB-520", "CB-530", "CB-540"))
        and state.get("pass_gates", {}).get("PG-5") == "not_started",
    )
    overlay = state.get("taskpack_overlay", {})
    report(
        errors,
        "task_state_current_run",
        state.get("current_run") == {
            "run_id": "P5.2",
            "gate_id": None,
            "task_id": "CB-510",
            "scope": "real_cloud_activation_access_timeline_status_canonical_sync",
            "status": "passed",
        },
    )
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
        and overlay.get("acceptance_scope") == "real_cloud_activation_with_fail_closed_channel_pending"
        and overlay.get("release_candidate_real_activation") == "verified"
        and overlay.get("clean_staging_real_activation") == "verified"
        and overlay.get("private_database_activation") == "verified"
        and overlay.get("timeline_activation") == "verified"
        and overlay.get("status_activation") == "verified"
        and overlay.get("access_activation") == "verified"
        and overlay.get("self_heal_activation") == "verified"
        and overlay.get("timer_activation") == "verified"
        and overlay.get("channel_activation") == "pending_missing_real_wechat_credential"
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("r2_backup_activation") == "hazard_blocked"
        and overlay.get("formal_final_acceptance") == "activation_pending",
    )


def validate_evidence(errors: list[str]) -> None:
    inventory = {candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()} if EVIDENCE.is_dir() else set()
    report(errors, "evidence_inventory", inventory == {"summary.json", "subject.json"})
    if inventory != {"summary.json", "subject.json"}:
        return
    try:
        summary = load_json(EVIDENCE / "summary.json")
        subject = load_json(EVIDENCE / "subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("evidence_json")
        return
    common = (
        summary.get("schema_version") == "cyberboss.cb510.activation-summary.v1"
        and summary.get("task_id") == "CB-510"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("cb_500_closure_commit") == CB500_CLOSURE
        and summary.get("implementation_commit") == IMPLEMENTATION_COMMIT
        and summary.get("implementation_tree") == IMPLEMENTATION_TREE
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("acceptance") == ACCEPTANCE
        and summary.get("release", {}).get("manifest_binding") == "verified"
        and summary.get("release", {}).get("manifest_product_version") == PRODUCT_VERSION
        and summary.get("runtime", {}).get("codex_login") == "verified"
        and summary.get("runtime", {}).get("codex_app_server") == "verified_loopback"
        and summary.get("runtime", {}).get("codex_authenticated_turn") == "not_executed_zero_model_invariant"
        and summary.get("runtime", {}).get("readyz") == "503_channel_pending"
        and summary.get("runtime", {}).get("channel") == "pending_missing_real_wechat_credential"
        and summary.get("runtime", {}).get("channel_simulator_started") is False
        and summary.get("runtime", {}).get("bridge_started") is False
        and summary.get("runtime", {}).get("control_plane_llm_calls") == 0
        and summary.get("runtime", {}).get("operations_llm_calls") == 0
        and summary.get("canonical", {}).get("private_database") == "verified_no_clone_material_roundtrip"
        and summary.get("canonical", {}).get("verified_batch_count_minimum") >= 1
        and summary.get("timeline", {}).get("direct_canonical_writes") == 0
        and summary.get("timeline", {}).get("fallback_used") is False
        and summary.get("cloudflare", {}).get("access") == "verified_owner_allow_only_default_deny"
        and summary.get("global_status", {}).get("collector") == "verified_live_snapshot"
        and summary.get("external_activation") == EXTERNAL_ACTIVATION
        and summary.get("safety") == {
            "real_time_waits": 0,
            "macos_launchd_dependency": False,
            "private_database_clone": False,
            "simulator_claimed_as_real": False,
            "pending_claimed_as_ready": False,
        }
        and summary.get("result") == "passed_with_explicit_pending"
        and summary.get("evidence_scope") == "real_cloud_activation_with_fail_closed_channel_pending"
        and summary.get("next_native_node") == "CB-520"
    )
    report(errors, "summary_contract", common)
    subject_ok = (
        subject.get("schema_version") == "cyberboss.cb510.subject.v1"
        and subject.get("task_id") == "CB-510"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("cb_500_closure_commit") == CB500_CLOSURE
        and subject.get("implementation_commit") == IMPLEMENTATION_COMMIT
        and subject.get("implementation_tree") == IMPLEMENTATION_TREE
        and subject.get("summary_sha256") == sha256(EVIDENCE / "summary.json")
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("deployment_release_commit") == IMPLEMENTATION_COMMIT
        and subject.get("deployment_release_pointer") == "current_verified_previous_retained"
        and subject.get("private_database_activation") == "verified_no_clone_material_roundtrip"
        and subject.get("cloudflare_activation") == "verified_access_dns_tunnel"
        and subject.get("timeline_activation") == "verified_canonical_public_pointer"
        and subject.get("global_status_activation") == "verified_live_snapshot"
        and subject.get("channel_activation") == "pending_missing_real_wechat_credential"
        and all(subject.get(key) == 0 for key in ("control_plane_llm_calls", "operations_llm_calls", "real_time_waits"))
        and subject.get("macos_launchd_dependency") is False
    )
    report(errors, "subject_contract", subject_ok)
    for path in (EVIDENCE / "summary.json", EVIDENCE / "subject.json"):
        content = path.read_text(encoding="utf-8")
        if SECRET_PATTERN.search(content) or "/Users/" in content or "/var/lib/" in content:
            errors.append(f"evidence_sensitive_or_absolute:{path.name}")


def validate_anchors(errors: list[str]) -> None:
    report(errors, "cb500_anchor", git("merge-base", "--is-ancestor", CB500_CLOSURE, IMPLEMENTATION_COMMIT, check=False)[0] == 0)
    report(errors, "implementation_commit", git("cat-file", "-e", f"{IMPLEMENTATION_COMMIT}^{{commit}}", check=False)[0] == 0)
    report(errors, "implementation_tree", git("rev-parse", f"{IMPLEMENTATION_COMMIT}^{{tree}}", check=False)[1] == IMPLEMENTATION_TREE)
    report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", IMPLEMENTATION_COMMIT, "HEAD", check=False)[0] == 0)
    report(errors, "frozen_design_unchanged", git("diff", "--quiet", IMPLEMENTATION_COMMIT, "--", "CyberBoss/docs/product_design/v0.0.0.4", check=False)[0] == 0)
    report(errors, "diff_check", git("diff", "--check", CB500_CLOSURE, "HEAD", check=False)[0] == 0)


def validate_local_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P5_2_CB_510.md").read_text(encoding="utf-8")
    supervisor = (PROJECT / "app/scripts/cloud-supervisor.js").read_text(encoding="utf-8")
    for marker in (
        "P5.2 / CB-510", PRODUCT_VERSION, "pending", "Private-Database", "Cloudflare",
        "real-time", "previous", "Status",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract_marker:{marker}")
    for marker in ("CB_CHANNEL_ACTIVATION_MODE", "holdPendingChannel", "notifySystemdReady", "timelinePublicRoot"):
        if marker not in supervisor:
            errors.append(f"supervisor_marker:{marker}")
    if "launchctl" in supervisor.lower() or "launchdaemon" in supervisor.lower():
        errors.append("supervisor_macos_launchd")


def validate_focused_tests(errors: list[str]) -> None:
    result = subprocess.run(
        ["node", "--test", "test/cloud-supervisor.test.js"],
        cwd=PROJECT / "app",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=300,
    )
    if result.returncode != 0 or "fail 0" not in result.stdout:
        errors.append("cloud_supervisor_tests")


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
        print("CB510_VALIDATION=FAIL")
        return 1
    print("CB510_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
