#!/usr/bin/env python3
"""Fail-closed local seal for the CB-530 real backup and handover receipt."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-530"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB520_CLOSURE = "1e0ed85cb55b980b67a748b55968db8cac01eeec"
IMPLEMENTATION_COMMIT = "25670bf32c6d27e3668fcf59bc9ab754035e161d"
IMPLEMENTATION_TREE = "5e590295e804d2532351b3c4757019fa7df66e75"
RELEASE_SOURCE_TREE = "f7513a03e3760830fcd53dedda74fe2fbef45e2e"
PREVIOUS_RELEASE = "77aea54878408f6e7d7136e48b17aff1bf8049ee"
RELEASE_MANIFEST_SHA256 = "962b8d8cfe6b22c0f10a5cb4cc4eae794d2b12b456c85ceffdde4f5d29ed58c3"
SOURCE_ARCHIVE_SHA256 = "2673993b0ced81ae6fe7878dcb5cf220f622d7a4e713261d5421bbb69e711d0b"
LATEST_BACKUP_ID = "backup_5233145600b2b004151de2bb"
ROUTER_RESULT = {
    "task_id": "CB-530",
    "selected_skill": "output-skill",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 0,
    "fallback": "machine/skill_microplaybooks.json",
}
EVIDENCE_FILES = {
    "summary.json",
    "subject.json",
    "handover.md",
    "operator-command-transcript.md",
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
    completed = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040",
        "CB-100", "CB-110", "CB-120", "CB-130", "CB-140",
        "CB-200", "CB-210", "CB-220", "CB-230", "CB-240",
        "CB-300", "CB-310", "CB-320", "CB-330", "CB-340",
        "CB-400", "CB-410", "CB-420", "CB-430", "CB-440",
        "CB-500", "CB-510", "CB-520", "CB-530",
    )
    report(errors, "task_state_completed", all(statuses.get(task) == "passed" for task in completed))
    report(
        errors,
        "task_state_future",
        statuses.get("CB-540") == "not_started"
        and state.get("pass_gates", {}).get("PG-5") == "not_started",
    )
    report(
        errors,
        "task_state_current_run",
        state.get("current_run") == {
            "run_id": "P5.4",
            "gate_id": None,
            "task_id": "CB-530",
            "scope": "real_r2_oci_backup_isolated_restore_and_operator_handover",
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
        and overlay.get("acceptance_state") == "passed_with_explicit_channel_and_daily_oci_par_pending"
        and overlay.get("acceptance_scope") == "real_r2_oci_backup_and_isolated_restore_with_explicit_pending"
        and overlay.get("r2_backup_activation") == "verified"
        and overlay.get("oci_backup_activation") == "verified_exact_readback_with_daily_write_only_pending"
        and overlay.get("cb_530_implementation_commit") == IMPLEMENTATION_COMMIT
        and overlay.get("cb_530_implementation_tree") == IMPLEMENTATION_TREE
        and overlay.get("cb_530_release_current") == "verified"
        and overlay.get("cb_530_release_previous") == "verified"
        and overlay.get("cb_530_backup_id") == LATEST_BACKUP_ID
        and overlay.get("cb_530_r2_isolated_restore") == "verified"
        and overlay.get("cb_530_oci_daily_par") == "activation_pending_write_only_par"
        and overlay.get("cb_530_oci_exact_readback") == "verified_ephemeral_then_revoked"
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("formal_final_acceptance") == "activation_pending",
    )


def validate_evidence(errors: list[str]) -> None:
    inventory = {entry.name for entry in EVIDENCE.iterdir() if entry.is_file()} if EVIDENCE.is_dir() else set()
    report(errors, "evidence_inventory", inventory == EVIDENCE_FILES)
    if inventory != EVIDENCE_FILES:
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
        summary.get("schema_version") == "cyberboss.cb530.operations-summary.v1"
        and summary.get("task_id") == "CB-530"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("cb_520_closure_commit") == CB520_CLOSURE
        and summary.get("implementation_commit") == IMPLEMENTATION_COMMIT
        and summary.get("implementation_tree") == IMPLEMENTATION_TREE
        and summary.get("previous_release_commit") == PREVIOUS_RELEASE
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("release", {}).get("release_manifest_sha256") == RELEASE_MANIFEST_SHA256
        and summary.get("release", {}).get("source_tree") == RELEASE_SOURCE_TREE
        and summary.get("release", {}).get("source_archive_sha256") == SOURCE_ARCHIVE_SHA256
        and summary.get("release", {}).get("current_previous_pointer") == "verified"
        and summary.get("latest_backup", {}).get("backup_id") == LATEST_BACKUP_ID
        and summary.get("latest_backup", {}).get("sqlite_integrity") == "ok"
        and summary.get("latest_backup", {}).get("logical_digest_verified") is True
        and summary.get("latest_backup", {}).get("r2", {}).get("state") == "verified"
        and summary.get("latest_backup", {}).get("r2", {}).get("put_get_hash_verified") is True
        and summary.get("latest_backup", {}).get("r2", {}).get("isolated_restore") == "passed_network_disabled_not_promoted"
        and summary.get("latest_backup", {}).get("oci", {}).get("daily_service_state") == "write_verified_read_pending"
        and summary.get("latest_backup", {}).get("oci", {}).get("daily_par_readback") == "activation_pending_write_only_par"
        and summary.get("latest_backup", {}).get("oci", {}).get("temporary_exact_object_readback") == "verified_sha256_match_then_revoked"
        and summary.get("operations", {}).get("backup_timer") == "enabled_active"
        and summary.get("operations", {}).get("cloudflare_access_unauthenticated") == "302"
        and summary.get("operations", {}).get("private_database_daily_sync") == "passed_no_clone"
        and summary.get("operations", {}).get("private_database_material_sync") == "passed_no_clone"
        and summary.get("safety", {}).get("control_plane_llm_calls") == 0
        and summary.get("safety", {}).get("operations_llm_calls") == 0
        and summary.get("safety", {}).get("macos_launchd_dependency") is False
        and summary.get("known_limitations", {}).get("channel_wechat") == "pending_missing_real_wechat_credential"
        and summary.get("result") == "passed_with_explicit_channel_and_daily_oci_par_pending"
        and summary.get("next_native_node") == "CB-540",
    )
    report(
        errors,
        "subject_contract",
        subject.get("schema_version") == "cyberboss.cb530.subject.v1"
        and subject.get("task_id") == "CB-530"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("cb_520_closure_commit") == CB520_CLOSURE
        and subject.get("implementation_commit") == IMPLEMENTATION_COMMIT
        and subject.get("implementation_tree") == IMPLEMENTATION_TREE
        and subject.get("previous_release_commit") == PREVIOUS_RELEASE
        and subject.get("summary_sha256") == sha256(EVIDENCE / "summary.json")
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("release_manifest_sha256") == RELEASE_MANIFEST_SHA256
        and subject.get("release_source_tree") == RELEASE_SOURCE_TREE
        and subject.get("latest_backup_id") == LATEST_BACKUP_ID
        and subject.get("r2_backup") == "verified_put_get_hash_and_isolated_restore"
        and subject.get("oci_backup") == "verified_put_hash_metadata_with_daily_readback_pending"
        and subject.get("oci_exact_object_readback") == "verified_ephemeral_then_revoked"
        and subject.get("backup_timer") == "enabled_active_linux_systemd"
        and subject.get("cloudflare_access") == "verified_unauthenticated_302"
        and subject.get("private_database_sync") == "verified_daily_and_material_no_clone"
        and subject.get("channel_activation") == "pending_missing_real_wechat_credential"
        and all(subject.get(key) == 0 for key in ("control_plane_llm_calls", "operations_llm_calls", "real_time_waits"))
        and subject.get("macos_launchd_dependency") is False,
    )
    transcript = (EVIDENCE / "operator-command-transcript.md").read_text(encoding="utf-8")
    handover = (EVIDENCE / "handover.md").read_text(encoding="utf-8")
    report(
        errors,
        "evidence_markdown",
        "cyberboss-backup.service" in transcript
        and "cyberboss-restore@" in transcript
        and "activation_pending_write_only_par" in transcript
        and "CB-540" in handover
        and "v0.0.0.5" in handover,
    )
    for path in EVIDENCE.iterdir():
        content = path.read_text(encoding="utf-8")
        if SECRET_PATTERN.search(content) or "/Users/" in content or "/var/lib/" in content:
            errors.append(f"evidence_sensitive_or_absolute:{path.name}")


def validate_source(errors: list[str]) -> None:
    source = PROJECT / "app/src/services/backup/cb530-cloud-backup.js"
    cli = PROJECT / "app/scripts/cb530-cloud-backup.js"
    backup_unit = PROJECT / "ops/systemd/cyberboss-backup.service"
    restore_unit = PROJECT / "ops/systemd/cyberboss-restore@.service"
    timer = PROJECT / "ops/systemd/cyberboss-backup.timer"
    refresh = PROJECT / "ops/systemd/cb530-refresh-r2-oauth.js"
    handover = PROJECT / "docs/operations/CB530_OPERATOR_HANDOVER.md"
    for path in (source, cli, backup_unit, restore_unit, timer, refresh, handover):
        report(errors, f"source_exists:{path.name}", path.is_file())
    if not all(path.is_file() for path in (source, cli, backup_unit, restore_unit, timer, refresh, handover)):
        return
    source_text = source.read_text(encoding="utf-8")
    cli_text = cli.read_text(encoding="utf-8")
    unit_text = backup_unit.read_text(encoding="utf-8") + restore_unit.read_text(encoding="utf-8")
    timer_text = timer.read_text(encoding="utf-8")
    handover_text = handover.read_text(encoding="utf-8")
    for marker in ("runCloudBackup", "uploadR2Bundle", "uploadOciBundle", "restoreRemoteBackup", "control_plane_llm_calls"):
        if marker not in source_text:
            errors.append(f"backup_source_marker:{marker}")
    for marker in ("backupRequest", "CB530_RELEASE_ROOT_INVALID", "redactResult"):
        if marker not in cli_text:
            errors.append(f"backup_cli_marker:{marker}")
    for marker in ("LoadCredential=r2_oauth_refresh_token", "LoadCredential=oci_par_url", "cb530-refresh-r2-oauth.js"):
        if marker not in unit_text:
            errors.append(f"unit_marker:{marker}")
    report(errors, "backup_timer_contract", "OnCalendar=*-*-* 03:35:00 UTC" in timer_text and "Persistent=true" in timer_text)
    report(errors, "handover_contract", "write-only" in handover_text and "launchd" in handover_text)
    report(errors, "no_launchd_source", "launchctl" not in "\n".join((source_text, cli_text, unit_text, timer_text, refresh.read_text(encoding="utf-8"))).lower())


def validate_anchors(errors: list[str]) -> None:
    report(errors, "cb520_anchor", git("merge-base", "--is-ancestor", CB520_CLOSURE, IMPLEMENTATION_COMMIT, check=False)[0] == 0)
    report(errors, "implementation_commit", git("cat-file", "-e", f"{IMPLEMENTATION_COMMIT}^{{commit}}", check=False)[0] == 0)
    report(errors, "implementation_tree", git("rev-parse", f"{IMPLEMENTATION_COMMIT}^{{tree}}", check=False)[1] == IMPLEMENTATION_TREE)
    report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", IMPLEMENTATION_COMMIT, "HEAD", check=False)[0] == 0)
    report(errors, "frozen_design_unchanged", git("diff", "--quiet", IMPLEMENTATION_COMMIT, "--", "CyberBoss/docs/product_design/v0.0.0.4", check=False)[0] == 0)
    report(errors, "diff_check", git("diff", "--check", CB520_CLOSURE, "HEAD", check=False)[0] == 0)


def validate_focused_tests(errors: list[str]) -> None:
    result = subprocess.run(
        [
            "node", "--test", "--test-isolation=none",
            "test/cb530-cloud-backup.test.js",
            "../ops/systemd/test/cb530-refresh-r2-oauth.test.js",
            "../release/test/write-release-manifest.test.js",
            "test/cloud-supervisor.test.js",
        ],
        cwd=PROJECT / "app",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=300,
    )
    if result.returncode != 0 or "fail 0" not in result.stdout or "tests 16" not in result.stdout:
        errors.append("cb530_focused_tests")


def validate() -> list[str]:
    errors: list[str] = []
    report(errors, "branch_scope", git("branch", "--show-current")[1].startswith("codex/cyberboss-"))
    validate_state(errors)
    validate_evidence(errors)
    validate_source(errors)
    validate_anchors(errors)
    validate_focused_tests(errors)
    return errors


def main() -> int:
    errors = validate()
    print("mode=final")
    print(f"errors={len(errors)}")
    if errors:
        for issue in errors:
            print(f"ERROR={issue}")
        print("CB530_VALIDATION=FAIL")
        return 1
    print("CB530_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
