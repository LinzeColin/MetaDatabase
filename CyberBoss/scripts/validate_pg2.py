#!/usr/bin/env python3
"""Fail-closed, credential-free Stage 2 exit-gate validator for CyberBoss PG-2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/PG-2"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = (
    "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
)
CB240_PUBLIC_IMPLEMENTATION = "839014fc4bcd52e11c8ff50331ff9dbd55fe0827"
CB240_IMPLEMENTATION = "fcfac053cab6944b2fc13a62491cce8ddb93e649"
CB240_IMPLEMENTATION_TREE = "781a8e32d2c3248c4cc4aebfe164a033efd45949"
CB240_CLOSURE = "91e9c267a775b138e27b196f0cc96de552ba958b"
CB240_CLOSURE_TREE = "53cac81bc4a63af9844e40dbea7d04ce14e35199"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
STAGE2_TASKS = ("CB-200", "CB-210", "CB-220", "CB-230", "CB-240")
STAGE2_SPECS = {
    "CB-200": {
        "phase": "P2.1",
        "implementation_commit": "6c8d7a1092a1f4d10a7f512ebe9abd2380aa2287",
        "repository_tree": "2bcca638945ce192c425755bba9b5a5769b5b491",
    },
    "CB-210": {
        "phase": "P2.2",
        "implementation_commit": "5c7b48d8f618bc83a70ebbd63eaf94b6ce6627ea",
        "repository_tree": "ebc1f9d6befc0c2f21086747d98b3c378950431a",
    },
    "CB-220": {
        "phase": "P2.3",
        "implementation_commit": "ac51cd2511a45def88068aef6d23fd10d7f507e4",
        "repository_tree": "77fa3a7c830921fcfd7cab449532e194af8ef74d",
    },
    "CB-230": {
        "phase": "P2.4",
        "implementation_commit": "1b3e338847d8819869a5e12091f25b5463a8d3be",
        "repository_tree": "ae9305f9e5c9746af4c1aab4f8fc4a44f54ddd7c",
    },
    "CB-240": {
        "phase": "P2.5",
        "implementation_commit": CB240_IMPLEMENTATION,
        "repository_tree": CB240_IMPLEMENTATION_TREE,
    },
}
PG2_ORACLES = ("FA-AC-007", "FA-AC-027", "FA-AC-029")
ROUTER_RESULT = {
    "task_id": "PG-2",
    "selected_skill": None,
    "mode": "DETERMINISTIC_TEST_ONLY",
    "max_lightweight_skill_loads": 0,
    "prohibited_skill_loads": 0,
}
IMPLEMENTATION_PATHS = {
    "CyberBoss/docs/governance/RUN_CONTRACT_PG_2.md",
    "CyberBoss/scripts/validate_pg2.py",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/PG-2/summary.json",
    "CyberBoss/docs/evidence/PG-2/subject.json",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
SENSITIVE_ENV_FRAGMENTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
    "SESSION",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "API_KEY",
    "OPENAI",
    "CODEX",
    "WECHAT",
    "CLOUDFLARE",
    "GITHUB",
)
SENSITIVE_ENV_PREFIXES = ("AWS_", "OCI_", "CF_", "GH_", "SSH_")
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bwxid_[A-Za-z0-9_-]+\b"
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


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def commit_paths(commit: str) -> set[str]:
    parent = git("rev-parse", f"{commit}^")[1]
    return set(filter(None, git("diff", "--name-only", parent, commit)[1].splitlines()))


def tree_at(commit: str, path: str) -> str | None:
    code, output = git("rev-parse", f"{commit}:{path}", check=False)
    return output if code == 0 else None


def report(errors: list[str], code: str, condition: bool) -> None:
    if not condition:
        errors.append(code)


def is_sensitive_environment_key(key: str) -> bool:
    upper = key.upper()
    return any(fragment in upper for fragment in SENSITIVE_ENV_FRAGMENTS) or upper.startswith(
        SENSITIVE_ENV_PREFIXES
    )


def credential_free_environment(root: Path) -> tuple[dict[str, str], int]:
    environment: dict[str, str] = {}
    removed = 0
    for key, value in os.environ.items():
        if is_sensitive_environment_key(key):
            removed += 1
            continue
        environment[key] = value
    if any(is_sensitive_environment_key(key) for key in environment):
        raise RuntimeError("credential_environment_scrub_failed")
    cache = root / "npm-cache"
    config = root / "config"
    tmp = root / "tmp"
    for directory in (cache, config, tmp):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "CI": "1",
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(tmp),
            "XDG_CONFIG_HOME": str(config),
            "NPM_CONFIG_USERCONFIG": "/dev/null",
            "NPM_CONFIG_CACHE": str(cache),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    return environment, removed


def run_command(
    name: str,
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    errors: list[str],
    *,
    markers: tuple[str, ...] = (),
    timeout: int = 900,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"command_exception:{name}:{type(error).__name__}")
        return {"name": name, "exit_code": None}
    output = result.stdout or ""
    if result.returncode != 0:
        tail = output.strip().splitlines()[-1:] or ["no_output"]
        errors.append(f"command_failed:{name}:{result.returncode}:{tail[0][:180]}")
    for marker in markers:
        if marker not in output:
            errors.append(f"command_marker:{name}:{marker}")
    return {"name": name, "exit_code": result.returncode}


def verify_manifest(path: Path, errors: list[str]) -> None:
    root = path.parent
    entries: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        errors.append(f"manifest_read:{path.relative_to(REPO)}:{type(error).__name__}")
        return
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            errors.append(f"manifest_line:{path.relative_to(REPO)}:{number}")
            continue
        digest, relative = match.groups()
        if relative in entries or relative.startswith("/") or ".." in Path(relative).parts:
            errors.append(f"manifest_path:{path.relative_to(REPO)}:{relative}")
            continue
        entries[relative] = digest
    actual = {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file()
        and candidate != path
        and "__pycache__" not in candidate.parts
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def stage2_index(errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_id in STAGE2_TASKS:
        spec = STAGE2_SPECS[task_id]
        path = f"CyberBoss/docs/evidence/{task_id}"
        evidence_tree = tree_at(CB240_CLOSURE, path)
        if evidence_tree is None:
            errors.append(f"anchor_evidence_tree:{task_id}")
            evidence_tree = ""
        rows.append(
            {
                "task_id": task_id,
                "phase": spec["phase"],
                "status": "passed",
                "implementation_commit": spec["implementation_commit"],
                "repository_tree": spec["repository_tree"],
                "evidence_tree": evidence_tree,
            }
        )
    return rows


def stage2_digest(rows: list[dict[str, Any]]) -> str:
    return canonical_sha256(
        {
            "anchor_commit": CB240_CLOSURE,
            "anchor_tree": CB240_CLOSURE_TREE,
            "tasks": rows,
        }
    )


def validate_frozen_history(rows: list[dict[str, Any]], errors: list[str]) -> None:
    report(errors, "cb240_anchor_tree", git("rev-parse", f"{CB240_CLOSURE}^{{tree}}", check=False)[1] == CB240_CLOSURE_TREE)
    report(
        errors,
        "cb240_anchor_ancestry",
        git("merge-base", "--is-ancestor", CB240_IMPLEMENTATION, CB240_CLOSURE, check=False)[0] == 0,
    )
    for row in rows:
        task_id = str(row["task_id"])
        path = f"CyberBoss/docs/evidence/{task_id}"
        report(
            errors,
            f"history_mutated:{task_id}",
            git("diff", "--quiet", CB240_CLOSURE, "--", path, check=False)[0] == 0,
        )
        implementation = str(row["implementation_commit"])
        report(
            errors,
            f"implementation_commit_missing:{task_id}",
            git("cat-file", "-e", f"{implementation}^{{commit}}", check=False)[0] == 0,
        )
        report(
            errors,
            f"implementation_ancestry:{task_id}",
            git("merge-base", "--is-ancestor", implementation, CB240_CLOSURE, check=False)[0] == 0,
        )
        if task_id != "CB-240":
            record = load_json(PROJECT / "docs/evidence" / task_id / "implementation-commit.json")
            report(
                errors,
                f"implementation_record:{task_id}",
                record.get("task_id") == task_id
                and record.get("phase") == row["phase"]
                and record.get("implementation_commit") == implementation
                and record.get("repository_tree") == row["repository_tree"]
                and git("rev-parse", f"{implementation}^{{tree}}", check=False)[1]
                == row["repository_tree"],
            )

    cb200_migration = load_json(PROJECT / "docs/evidence/CB-200/migration-acceptance.redacted.json")
    cb200_properties = load_json(PROJECT / "docs/evidence/CB-200/property-test-report.json")
    cb200_crash = load_json(PROJECT / "docs/evidence/CB-200/crash-matrix.redacted.json")
    cb200_security = load_json(PROJECT / "docs/evidence/CB-200/security-report.json")
    report(
        errors,
        "oracle_cb200",
        cb200_migration.get("result") == "passed"
        and cb200_migration.get("clean_migration") == "passed"
        and cb200_migration.get("existing_v1_migration") == "passed"
        and cb200_migration.get("integrity_check") == "ok"
        and cb200_migration.get("destructive_statements") == 0
        and cb200_properties.get("result") == "passed"
        and cb200_properties.get("stable_id_fixture_count") == 10000
        and cb200_properties.get("stable_id_collisions") == 0
        and cb200_properties.get("illegal_transition_successes") == 0
        and cb200_properties.get("raw_sql_illegal_transition_successes") == 0
        and cb200_properties.get("duplicate_inbox_rows") == 0
        and cb200_properties.get("duplicate_job_rows") == 0
        and cb200_crash.get("result") == "passed"
        and cb200_crash.get("accepted_but_lost") == 0
        and cb200_crash.get("duplicate_executable_jobs") == 0
        and cb200_crash.get("integrity_failures") == 0
        and cb200_security.get("result") == "passed"
        and cb200_security.get("p0_findings") == 0
        and cb200_security.get("p1_findings") == 0
        and cb200_security.get("secret_value_hits") == 0
        and cb200_security.get("private_database_operations") == 0,
    )

    cb210_crash = load_json(PROJECT / "docs/evidence/CB-210/crash-matrix.redacted.json")
    cb210_ordering = load_json(PROJECT / "docs/evidence/CB-210/ordering-property-report.json")
    cb210_replay = load_json(PROJECT / "docs/evidence/CB-210/replay-report.json")
    cb210_security = load_json(PROJECT / "docs/evidence/CB-210/security-report.json")
    cb210_cases = cb210_crash.get("cases") or []
    report(
        errors,
        "oracle_cb210",
        cb210_crash.get("result") == "passed"
        and len(cb210_cases) == 3
        and all(
            case.get("result") == "passed"
            and case.get("cursor_committed") is True
            and case.get("inbox_count") == 1
            and case.get("job_count") == 1
            and case.get("execution_count") == 1
            and case.get("message_lost") is False
            and case.get("integrity_check") == "ok"
            for case in cb210_cases
        )
        and cb210_crash.get("accepted_but_lost") == 0
        and cb210_crash.get("duplicate_executions") == 0
        and cb210_ordering.get("result") == "passed"
        and all(
            cb210_ordering.get(key) is True
            for key in (
                "numeric_contiguous_commit",
                "reversed_batch_sorted",
                "gap_rejected",
                "duplicate_sequence_rejected",
                "regression_rejected",
            )
        )
        and cb210_ordering.get("database_or_cursor_changes_on_rejection") == 0
        and cb210_replay.get("result") == "passed"
        and cb210_replay.get("replay_count") == 1000
        and cb210_replay.get("execution_count") == 1
        and cb210_replay.get("canonical_reconcile_set_diff") == 0
        and cb210_security.get("result") == "passed"
        and cb210_security.get("plaintext_scan_hits") == 0
        and cb210_security.get("secret_scan_hits") == 0
        and cb210_security.get("real_provider_used") is False,
    )

    cb220_scheduler = load_json(PROJECT / "docs/evidence/CB-220/scheduler-timeline.redacted.json")
    cb220_workspace = load_json(PROJECT / "docs/evidence/CB-220/workspace-matrix.redacted.json")
    cb220_resource = load_json(PROJECT / "docs/evidence/CB-220/resource-gate-report.json")
    cb220_stop = load_json(PROJECT / "docs/evidence/CB-220/stop-matrix.redacted.json")
    cb220_security = load_json(PROJECT / "docs/evidence/CB-220/security-report.json")
    report(
        errors,
        "oracle_cb220",
        cb220_scheduler.get("result") == "passed"
        and cb220_scheduler.get("max_active_runtime_leases") == 1
        and cb220_scheduler.get("fifo_dispatch_order") is True
        and cb220_scheduler.get("transactional_claim") is True
        and cb220_scheduler.get("stale_owner_fenced") is True
        and cb220_workspace.get("result") == "passed"
        and cb220_workspace.get("allowlisted_alias_dispatched") is True
        and cb220_workspace.get("absolute_path_dispatched") is False
        and cb220_workspace.get("unknown_alias_dispatched") is False
        and cb220_workspace.get("symlink_escape_dispatched") is False
        and cb220_workspace.get("filesystem_changed_on_rejection") is False
        and cb220_resource.get("result") == "passed"
        and cb220_resource.get("protect_blocks_mutation") is True
        and cb220_resource.get("measurement_unavailable_fails_closed") is True
        and cb220_resource.get("no_real_time_soak") is True
        and cb220_stop.get("result") == "passed"
        and cb220_stop.get("ack_claimed_terminal") is False
        and cb220_stop.get("false_success_count") == 0
        and cb220_security.get("result") == "passed"
        and cb220_security.get("workspace_escape_count") == 0
        and cb220_security.get("unsafe_mutation_replay_count") == 0,
    )

    cb230_matrix = load_json(PROJECT / "docs/evidence/CB-230/outbox-recovery-matrix.redacted.json")
    cb230_security = load_json(PROJECT / "docs/evidence/CB-230/security-report.json")
    cb230_retry = cb230_matrix.get("ac_021_retry") or {}
    cb230_dedupe = cb230_matrix.get("ac_022_dedupe") or {}
    cb230_chunks = cb230_matrix.get("ac_025_chunks") or {}
    cb230_recovery = cb230_matrix.get("ac_062_recovery") or {}
    report(
        errors,
        "oracle_cb230",
        cb230_matrix.get("result") == "passed"
        and (cb230_matrix.get("executable_suite") or {}).get("tests") == 37
        and (cb230_matrix.get("executable_suite") or {}).get("failures") == 0
        and (cb230_matrix.get("executable_suite") or {}).get("fixed_wait") is False
        and cb230_retry.get("result") == "passed"
        and cb230_retry.get("attempts") == 3
        and cb230_retry.get("real_wait_calls") == 0
        and cb230_retry.get("clock") == "virtual"
        and cb230_dedupe.get("result") == "passed"
        and cb230_dedupe.get("stage_count") == 1000
        and cb230_dedupe.get("confirmed_delivery_count") == 1
        and cb230_chunks.get("result") == "passed"
        and cb230_chunks.get("source_sha256") == cb230_chunks.get("reconstructed_sha256")
        and cb230_chunks.get("replied_before_all_final_chunks_confirmed") is False
        and cb230_recovery.get("result") == "passed"
        and cb230_recovery.get("unknown_dispatch_auto_replay_count") == 0
        and cb230_recovery.get("false_green_count") == 0
        and cb230_security.get("result") == "passed"
        and cb230_security.get("plaintext_scan_hits") == 0
        and cb230_security.get("secret_scan_hits") == 0
        and cb230_security.get("private_database_operations") == 0,
    )

    cb240_summary_path = PROJECT / "docs/evidence/CB-240/summary.json"
    cb240_subject_path = PROJECT / "docs/evidence/CB-240/subject.json"
    cb240_summary = load_json(cb240_summary_path)
    cb240_subject = load_json(cb240_subject_path)
    report(
        errors,
        "oracle_cb240",
        cb240_summary.get("schema_version") == "cyberboss.cb240.closure-summary.v1"
        and cb240_summary.get("product_version") == PRODUCT_VERSION
        and cb240_summary.get("taskpack_version") == TASKPACK_VERSION
        and cb240_summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and cb240_summary.get("implementation_commit") == CB240_IMPLEMENTATION
        and cb240_summary.get("implementation_tree") == CB240_IMPLEMENTATION_TREE
        and cb240_summary.get("acceptance")
        == {f"FA-AC-00{number}": "passed" for number in range(1, 7)}
        and cb240_summary.get("private_database_activation") == "activation_pending"
        and cb240_summary.get("real_private_database_operations") == 0
        and cb240_summary.get("real_r2_operations") == 0
        and cb240_summary.get("control_plane_llm_calls") == 0
        and cb240_summary.get("operations_llm_calls") == 0
        and cb240_summary.get("macos_launchd_dependency") is False
        and cb240_summary.get("pg_2_executed") is False
        and cb240_summary.get("result") == "passed"
        and cb240_subject.get("schema_version") == "cyberboss.cb240.subject.v1"
        and cb240_subject.get("public_implementation_commit") == CB240_PUBLIC_IMPLEMENTATION
        and cb240_subject.get("implementation_commit") == CB240_IMPLEMENTATION
        and cb240_subject.get("implementation_tree") == CB240_IMPLEMENTATION_TREE
        and cb240_subject.get("summary_sha256") == sha256(cb240_summary_path)
        and cb240_subject.get("deployment_release_pointer") == "activation_pending",
    )


def validate_state(final: bool, evidence_digest: str, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    for task_id in STAGE2_TASKS:
        report(errors, f"task_state_stage2:{task_id}", statuses.get(task_id) == "passed")
    for task_id, status in statuses.items():
        if task_id not in STAGE2_TASKS and task_id.startswith("CB-") and task_id >= "CB-300":
            report(errors, f"task_state_future:{task_id}", status == "not_started")
    gates = state.get("pass_gates") or {}
    report(errors, "task_state_prior_gates", gates.get("PG-0") == "passed" and gates.get("PG-1") == "passed")
    report(errors, "task_state_later_gates", all(gates.get(gate) == "not_started" for gate in ("PG-3", "PG-4", "PG-5")))
    expected_current = (
        {
            "run_id": "PG-2",
            "gate_id": "PG-2",
            "task_id": None,
            "scope": "stage_2_durable_messaging_canonical_gate",
            "status": "passed",
        }
        if final
        else {
            "run_id": "P2.5",
            "gate_id": None,
            "task_id": "CB-240",
            "scope": "canonical_sync_rebuild",
            "status": "passed",
        }
    )
    report(errors, "task_state_current_run", state.get("current_run") == expected_current)
    report(errors, "task_state_pg2", gates.get("PG-2") == ("passed" if final else "not_started"))
    overlay = state.get("taskpack_overlay") or {}
    common = (
        state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_pg2_overlay",
            overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("pg_2_executed") is True
            and overlay.get("stage_2_subject_digest") == evidence_digest
            and overlay.get("stage_2_anchor_commit") == CB240_CLOSURE
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_PG_2.md").read_text(encoding="utf-8")
    for marker in (
        "PG-2",
        PRODUCT_VERSION,
        TASKPACK_VERSION,
        TASKPACK_ZIP_SHA256,
        "FA-AC-007",
        "FA-AC-027",
        "FA-AC-029",
        "DETERMINISTIC_TEST_ONLY",
        "不加载任何 Skill",
        "CB-300",
        "Private-Database",
        "macOS `launchd`",
        "activation_pending",
        "03:20 UTC",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")


def validate_no_launchd(errors: list[str]) -> None:
    roots = (
        PROJECT / "app/src",
        PROJECT / "app/scripts",
        KIT / "systemd",
        KIT / "scripts",
    )
    forbidden = ("launchctl", "launchdaemon", "launchagents", "com.apple.launchd")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "node_modules" in path.parts:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(marker in content for marker in forbidden):
                errors.append(f"macos_launchd_dependency:{path.relative_to(REPO)}")


def run_clean_state_replay(errors: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-pg2-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        app_tests = [
            "test/job-state-machine.test.js",
            "test/runtime-spool.test.js",
            "test/durable-inbox-crash-cut.test.js",
            "test/weixin-cursor-commit.test.js",
            "test/job-scheduler.test.js",
            "test/resource-readiness-gate.test.js",
            "test/workspace-scope.test.js",
            "test/durable-outbox-crash-cut.test.js",
            "test/stream-delivery.test.js",
            "test/turn-gate-store.test.js",
            "test/weixin-outbox-transport.test.js",
            "test/canonical-sync.test.js",
        ]
        root_tests = [
            "tests/runtime-spool.test.js",
            "tests/durable-inbox.test.js",
            "tests/job-scheduler.test.js",
            "tests/durable-outbox.test.js",
            "tests/canonical-sync.test.js",
        ]
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("stage2_app_focused", ["node", "--test", *app_tests], PROJECT / "app", ("fail 0",), 600),
            ("stage2_root_contract", ["node", "--test", *root_tests], PROJECT, ("fail 0",), 600),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_full_regression", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
            ("identity_scope", [sys.executable, str(KIT / "tests/test_identity_scope.py")], REPO, ("OK",), 300),
            (
                "config",
                [
                    "node",
                    str(KIT / "tests/validate_config.js"),
                    "--allow-placeholders",
                    str(KIT / "config/cyberboss.env.example"),
                    str(KIT / "config/workspaces.json.example"),
                ],
                REPO,
                ("CONFIG_VALIDATION=PASS",),
                300,
            ),
            (
                "dag",
                [sys.executable, str(KIT / "tests/validate_task_dag.py"), str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml")],
                REPO,
                ("DAG_VALIDATION=PASS tasks=30 stages=6",),
                300,
            ),
            (
                "traceability",
                [sys.executable, str(KIT / "tests/validate_traceability.py"), str(PACK)],
                REPO,
                ("TRACEABILITY_VALIDATION=PASS requirements=53",),
                300,
            ),
            (
                "no_wait",
                [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)],
                REPO,
                ("NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0",),
                300,
            ),
            (
                "taskpack",
                [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
                REPO,
                ("TASKPACK_VALIDATION=PASS", "seven_is_minimum_not_limit=true"),
                300,
            ),
        ]
        commands = [
            run_command(name, command, cwd, environment, errors, markers=markers, timeout=timeout)
            for name, command, cwd, markers, timeout in specs
        ]
        return {
            "result": "passed" if not errors else "failed",
            "credential_named_environment_keys_removed": removed_count,
            "network_or_provider_operations": 0,
            "real_time_waits": 0,
            "commands": commands,
        }


def validate_subject_and_evidence(
    rows: list[dict[str, Any]], evidence_digest: str, errors: list[str]
) -> str | None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_missing")
        return None
    inventory = {candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()}
    if inventory != FINAL_EVIDENCE:
        errors.append(f"evidence_inventory:{sorted(inventory)}")
        return None
    summary_path = EVIDENCE / "summary.json"
    subject_path = EVIDENCE / "subject.json"
    try:
        summary = load_json(summary_path)
        subject = load_json(subject_path)
    except (OSError, ValueError, TypeError):
        errors.append("evidence_json")
        return None
    implementation_commit = str(subject.get("implementation_commit") or "")
    implementation_tree = str(subject.get("implementation_tree") or "")
    report(
        errors,
        "subject_contract",
        bool(re.fullmatch(r"[0-9a-f]{40}", implementation_commit))
        and subject.get("schema_version") == "cyberboss.pg2.subject.v1"
        and subject.get("task_id") == "PG-2"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("stage_2_anchor_commit") == CB240_CLOSURE
        and subject.get("stage_2_anchor_tree") == CB240_CLOSURE_TREE
        and subject.get("stage_2_evidence_digest") == evidence_digest
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1]
        == implementation_tree
        and git("merge-base", "--is-ancestor", CB240_CLOSURE, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("deployment_release_pointer") == "activation_pending"
        and subject.get("real_private_database_operations") == 0
        and subject.get("real_r2_operations") == 0
        and subject.get("real_cloudflare_operations") == 0
        and subject.get("real_oci_operations") == 0
        and subject.get("control_plane_llm_calls") == 0
        and subject.get("operations_llm_calls") == 0
        and subject.get("macos_launchd_dependency") is False,
    )
    expected_external = {
        "private_database": "activation_pending",
        "r2": "hazard_blocked",
        "cloudflare_access": "activation_pending",
        "oci": "activation_pending",
    }
    report(
        errors,
        "summary_contract",
        summary.get("schema_version") == "cyberboss.pg2.closure-summary.v1"
        and summary.get("task_id") == "PG-2"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("stage_2_anchor_commit") == CB240_CLOSURE
        and summary.get("stage_2_anchor_tree") == CB240_CLOSURE_TREE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("stage_2_evidence") == rows
        and summary.get("stage_2_evidence_digest") == evidence_digest
        and summary.get("acceptance") == {oracle: "passed" for oracle in PG2_ORACLES}
        and summary.get("local_validation")
        == {
            "stage2_focused_regression": "passed",
            "clean_state_replay": "passed",
            "dag": "passed",
            "traceability": "passed",
            "no_wait": "passed",
            "taskpack": "passed",
            "manifests": "passed",
        }
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("external_activation") == expected_external
        and summary.get("real_private_database_operations") == 0
        and summary.get("real_r2_operations") == 0
        and summary.get("real_cloudflare_operations") == 0
        and summary.get("real_oci_operations") == 0
        and summary.get("control_plane_llm_calls") == 0
        and summary.get("operations_llm_calls") == 0
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("next_native_node") == "CB-300",
    )
    for path in EVIDENCE.iterdir():
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_sensitive_or_absolute:{path.name}")
    return implementation_commit


def validate_commit_boundaries(
    implementation_commit: str | None, final: bool, errors: list[str]
) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", CB240_CLOSURE, implementation_commit, check=False)[0] == 0)
    report(errors, "implementation_inventory", commit_paths(implementation_commit) == IMPLEMENTATION_PATHS)
    if final:
        closure_paths = set(filter(None, git("diff", "--name-only", implementation_commit, "HEAD")[1].splitlines()))
        report(errors, "closure_atomic_inventory", closure_paths == CLOSURE_PATHS)


def validate(final: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    branch = git("branch", "--show-current")[1]
    report(errors, "branch_scope", branch.startswith("codex/cyberboss-"))
    report(errors, "worktree_dirty", not git("status", "--porcelain=v1", "--untracked-files=all")[1])
    report(errors, "nested_git_repository", not list(PROJECT.rglob(".git")))
    report(
        errors,
        "gitlink",
        not any(line.startswith("160000 ") for line in git("ls-files", "-s", "CyberBoss")[1].splitlines()),
    )
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_wait_calls = (
        "time" + ".sleep",
        "asyncio" + ".sleep",
        "child_process" + ".execSync(\"sleep",
    )
    report(
        errors,
        "validator_no_sleep",
        not any(marker in source for marker in forbidden_wait_calls),
    )
    report(errors, "anchor_commit", git("cat-file", "-e", f"{CB240_CLOSURE}^{{commit}}", check=False)[0] == 0)

    rows = stage2_index(errors)
    evidence_digest = stage2_digest(rows)
    validate_state(final, evidence_digest, errors)
    validate_contract(errors)
    validate_no_launchd(errors)
    validate_frozen_history(rows, errors)
    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)
    matrix = run_clean_state_replay(errors)
    implementation_commit = (
        validate_subject_and_evidence(rows, evidence_digest, errors)
        if final
        else git("rev-parse", "HEAD")[1]
    )
    validate_commit_boundaries(implementation_commit, final, errors)
    reports = {
        "mode": "final" if final else "prepare",
        "branch": branch,
        "stage2_evidence_digest": evidence_digest,
        "commands": len(matrix["commands"]),
        "errors": len(errors),
    }
    return errors, reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Validate the clean PG-2 implementation subject before closure evidence.",
    )
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("PG2_VALIDATION=FAIL")
        return 1
    print("PG2_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
