#!/usr/bin/env python3
"""Fail-closed, credential-free validator for CyberBoss P3.2 / CB-310."""

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


sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-310"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB300_CLOSURE = "e8243ea81b5ecf239a8ec2df44189259c661adfa"
CB300_IMPLEMENTATION = "02ac88119fc864c37b5346c2ad334e17c6bc7702"
CB300_IMPLEMENTATION_TREE = "22415bfe64ebd8ea8c09120af6b8cc501ca56da8"
ACCEPTANCE = ("FA-AC-009", "FA-AC-010", "FA-AC-028", "FA-AC-031")
ROUTER_RESULT = {
    "task_id": "CB-310",
    "selected_skill": "webapp-testing",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 0,
    "fallback": "machine/skill_microplaybooks.json",
}
IMPLEMENTATION_PATHS = {
    "CyberBoss/app/scripts/canonical-status-export.js",
    "CyberBoss/app/src/services/status/canonical-status-export.js",
    "CyberBoss/app/test/canonical-status-export.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P3_2_CB_310.md",
    "CyberBoss/scripts/validate_cb310.py",
    "CyberBoss/tests/canonical-status.test.js",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/CB-310/subject.json",
    "CyberBoss/docs/evidence/CB-310/summary.json",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
SENSITIVE_ENV_FRAGMENTS = (
    "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH", "COOKIE", "SESSION",
    "PRIVATE_KEY", "ACCESS_KEY", "API_KEY", "OPENAI", "CODEX", "WECHAT",
    "CLOUDFLARE", "GITHUB",
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
        ["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
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


def commit_paths(commit: str) -> set[str]:
    parent = git("rev-parse", f"{commit}^")[1]
    return set(filter(None, git("diff", "--name-only", parent, commit)[1].splitlines()))


def is_sensitive_environment_key(key: str) -> bool:
    upper = key.upper()
    return any(fragment in upper for fragment in SENSITIVE_ENV_FRAGMENTS) or upper.startswith(SENSITIVE_ENV_PREFIXES)


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
    environment.update({
        "CI": "1",
        "NO_COLOR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(tmp),
        "XDG_CONFIG_HOME": str(config),
        "NPM_CONFIG_USERCONFIG": "/dev/null",
        "NPM_CONFIG_CACHE": str(cache),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return environment, removed


def run_command(
    name: str, command: list[str], cwd: Path, environment: dict[str, str],
    errors: list[str], *, markers: tuple[str, ...] = (), timeout: int = 900,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False, timeout=timeout,
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
        if candidate.is_file() and candidate != path and "__pycache__" not in candidate.parts
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    prior = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100", "CB-110",
        "CB-120", "CB-130", "CB-140", "CB-200", "CB-210", "CB-220", "CB-230",
        "CB-240", "CB-300",
    )
    for task_id in prior:
        report(errors, f"task_state_prior:{task_id}", statuses.get(task_id) == "passed")
    report(errors, "task_state_cb310", statuses.get("CB-310") == ("passed" if final else "not_started"))
    for task_id in (
        "CB-320", "CB-330", "CB-340", "CB-400", "CB-410", "CB-420", "CB-430",
        "CB-440", "CB-500", "CB-510", "CB-520", "CB-530", "CB-540",
    ):
        report(errors, f"task_state_future:{task_id}", statuses.get(task_id) == "not_started")
    gates = state.get("pass_gates") or {}
    report(errors, "task_state_prior_gates", all(gates.get(gate) == "passed" for gate in ("PG-0", "PG-1", "PG-2")))
    report(errors, "task_state_later_gates", all(gates.get(gate) == "not_started" for gate in ("PG-3", "PG-4", "PG-5")))
    expected_current = (
        {
            "run_id": "P3.2",
            "gate_id": None,
            "task_id": "CB-310",
            "scope": "redacted_status_snapshot",
            "status": "passed",
        }
        if final
        else {
            "run_id": "P3.1",
            "gate_id": None,
            "task_id": "CB-300",
            "scope": "canonical_timeline_projection",
            "status": "passed",
        }
    )
    report(errors, "task_state_current_run", state.get("current_run") == expected_current)
    overlay = state.get("taskpack_overlay") or {}
    common = (
        state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("timeline_projection_status") == "passed"
        and overlay.get("timeline_activation") == "activation_pending"
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_cb310_overlay",
            overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("status_snapshot_status") == "passed"
            and overlay.get("status_activation") == "activation_pending"
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )


def validate_cb300_anchor(errors: list[str]) -> None:
    report(errors, "cb300_closure_commit", git("cat-file", "-e", f"{CB300_CLOSURE}^{{commit}}", check=False)[0] == 0)
    report(errors, "cb300_history", git("merge-base", "--is-ancestor", CB300_CLOSURE, "HEAD", check=False)[0] == 0)
    report(errors, "cb300_evidence_mutated", git("diff", "--quiet", CB300_CLOSURE, "--", "CyberBoss/docs/evidence/CB-300", check=False)[0] == 0)
    try:
        summary = load_json(PROJECT / "docs/evidence/CB-300/summary.json")
        subject = load_json(PROJECT / "docs/evidence/CB-300/subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("cb300_evidence_read")
        return
    report(
        errors,
        "cb300_subject",
        summary.get("schema_version") == "cyberboss.cb300.closure-summary.v1"
        and summary.get("result") == "passed"
        and summary.get("implementation_commit") == CB300_IMPLEMENTATION
        and summary.get("implementation_tree") == CB300_IMPLEMENTATION_TREE
        and subject.get("schema_version") == "cyberboss.cb300.subject.v1"
        and subject.get("summary_sha256") == sha256(PROJECT / "docs/evidence/CB-300/summary.json"),
    )


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P3_2_CB_310.md").read_text(encoding="utf-8")
    for marker in (
        "P3.2 / CB-310", PRODUCT_VERSION, TASKPACK_VERSION, TASKPACK_ZIP_SHA256,
        CB300_CLOSURE, "FA-AC-009", "FA-AC-010", "FA-AC-028", "FA-AC-031",
        "webapp-testing", "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
        "machine/skill_microplaybooks.json", "实际 Skill body load 为 `0`",
        "cyberboss.status.v2", "global-status-adapter.js", "atomic rename",
        "activation_pending", "macOS `launchd`", "CB-320",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")


def validate_code(errors: list[str]) -> None:
    module = (PROJECT / "app/src/services/status/canonical-status-export.js").read_text(encoding="utf-8")
    cli = (PROJECT / "app/scripts/canonical-status-export.js").read_text(encoding="utf-8")
    app_test = (PROJECT / "app/test/canonical-status-export.test.js").read_text(encoding="utf-8")
    root_test = (PROJECT / "tests/canonical-status.test.js").read_text(encoding="utf-8")
    for marker in (
        'STATUS_SCHEMA = "cyberboss.status.v2"', "writeStatusSnapshotAtomic",
        "writeGlobalStatusRowAtomic", "STATUS_ZERO_AGENT_COUNTER_VIOLATION",
        "STATUS_GENERATION_NON_MONOTONIC", "CRASH_BEFORE_RENAME",
        "CRASH_AFTER_RENAME", "buildGlobalStatusRow",
        "GLOBAL_STATUS_ADAPTER_PATH", "global-status-adapter.js", 'agent: "无"',
        "rejectSensitiveValue", "control_plane_llm_calls_total",
        "self_heal_agent_invocations_total",
    ):
        if marker not in module:
            errors.append(f"status_marker:{marker}")
    for marker in ("--input", "--snapshot", "--row", "--generated-at", "--observed-at", "control_plane_llm_calls_total"):
        if marker not in cli:
            errors.append(f"cli_marker:{marker}")
    for marker in ("every required component", "crash cuts", "zero-agent", "STATUS_GENERATION_NON_MONOTONIC"):
        if marker not in app_test:
            errors.append(f"app_test_marker:{marker}")
    if "canonical status CLI writes" not in root_test or "generation_id" not in root_test:
        errors.append("root_test_marker")
    forbidden = ("setTimeout(", "setInterval(", "sleep(", "launchctl", "launchdaemon", "com.apple.launchd")
    for label, text in (("module", module), ("cli", cli), ("app_test", app_test), ("root_test", root_test)):
        for marker in forbidden:
            if marker.lower() in text.lower():
                errors.append(f"forbidden_runtime:{label}:{marker}")
    for marker in ("fetch(", "loadSnapshot(", "NoClonePrivateDatabaseAdapter", "TimelineService"):
        if marker in module:
            errors.append(f"status_scope:{marker}")


def run_clean_validation(errors: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-cb310-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("status_snapshot", ["node", "--test", "test/canonical-status-export.test.js"], PROJECT / "app", ("fail 0",), 300),
            ("status_cli", ["node", "--test", "tests/canonical-status.test.js"], PROJECT, ("fail 0",), 300),
            ("status_syntax", ["node", "--check", "src/services/status/canonical-status-export.js"], PROJECT / "app", (), 120),
            ("status_cli_syntax", ["node", "--check", "scripts/canonical-status-export.js"], PROJECT / "app", (), 120),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_regression", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
            ("identity_scope", [sys.executable, str(KIT / "tests/test_identity_scope.py")], REPO, ("OK",), 300),
            (
                "config",
                ["node", str(KIT / "tests/validate_config.js"), "--allow-placeholders", str(KIT / "config/cyberboss.env.example"), str(KIT / "config/workspaces.json.example")],
                REPO, ("CONFIG_VALIDATION=PASS",), 300,
            ),
            ("dag", [sys.executable, str(KIT / "tests/validate_task_dag.py"), str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml")], REPO, ("DAG_VALIDATION=PASS tasks=30 stages=6",), 300),
            ("traceability", [sys.executable, str(KIT / "tests/validate_traceability.py"), str(PACK)], REPO, ("TRACEABILITY_VALIDATION=PASS requirements=53",), 300),
            ("no_wait", [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)], REPO, ("NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0",), 300),
            ("taskpack", [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)], REPO, ("TASKPACK_VALIDATION=PASS", "seven_is_minimum_not_limit=true"), 300),
        ]
        commands = [run_command(name, command, cwd, environment, errors, markers=markers, timeout=timeout) for name, command, cwd, markers, timeout in specs]
        return {"credential_named_environment_keys_removed": removed_count, "network_or_provider_operations": 0, "real_time_waits": 0, "commands": commands}


def validate_subject_and_evidence(errors: list[str]) -> str | None:
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
        and subject.get("schema_version") == "cyberboss.cb310.subject.v1"
        and subject.get("task_id") == "CB-310"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("cb300_closure_commit") == CB300_CLOSURE
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1] == implementation_tree
        and git("merge-base", "--is-ancestor", CB300_CLOSURE, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("deployment_release_pointer") == "activation_pending"
        and subject.get("real_private_database_operations") == 0
        and subject.get("real_r2_operations") == 0
        and subject.get("real_cloudflare_operations") == 0
        and subject.get("real_oci_operations") == 0
        and subject.get("real_global_status_operations") == 0
        and subject.get("control_plane_llm_calls") == 0
        and subject.get("operations_llm_calls") == 0
        and subject.get("macos_launchd_dependency") is False,
    )
    expected_external = {
        "private_database": "activation_pending",
        "r2": "hazard_blocked",
        "cloudflare_access": "activation_pending",
        "oci": "activation_pending",
        "timeline": "activation_pending",
        "global_status": "activation_pending",
    }
    expected_local = {
        "status_snapshot_contract": "passed",
        "global_collector_adapter": "passed",
        "atomic_crash_cuts": "passed",
        "component_fault_matrix": "passed",
        "dlp_schema": "passed",
        "zero_agent_counters": "passed",
        "app_regression": "passed",
        "manifests": "passed",
        "taskpack": "passed",
    }
    report(
        errors,
        "summary_contract",
        summary.get("schema_version") == "cyberboss.cb310.closure-summary.v1"
        and summary.get("task_id") == "CB-310"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("cb300_closure_commit") == CB300_CLOSURE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("acceptance") == {oracle: "passed" for oracle in ACCEPTANCE}
        and summary.get("local_validation") == expected_local
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("external_activation") == expected_external
        and summary.get("real_private_database_operations") == 0
        and summary.get("real_r2_operations") == 0
        and summary.get("real_cloudflare_operations") == 0
        and summary.get("real_oci_operations") == 0
        and summary.get("real_global_status_operations") == 0
        and summary.get("control_plane_llm_calls") == 0
        and summary.get("operations_llm_calls") == 0
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("next_native_node") == "CB-320",
    )
    for path in EVIDENCE.iterdir():
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "CB310-PRIVATE" in text or "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_sensitive_or_absolute:{path.name}")
    return implementation_commit


def validate_commit_boundaries(implementation_commit: str | None, final: bool, errors: list[str]) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", CB300_CLOSURE, implementation_commit, check=False)[0] == 0)
    report(errors, "implementation_inventory", commit_paths(implementation_commit) == IMPLEMENTATION_PATHS)
    if final:
        report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", implementation_commit, "HEAD", check=False)[0] == 0)
        closure_paths = set(filter(None, git("diff", "--name-only", implementation_commit, "HEAD")[1].splitlines()))
        report(errors, "closure_atomic_inventory", closure_paths == CLOSURE_PATHS)


def validate(final: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    branch = git("branch", "--show-current")[1]
    report(errors, "branch_scope", branch.startswith("codex/cyberboss-"))
    report(errors, "worktree_dirty", not git("status", "--porcelain=v1", "--untracked-files=all")[1])
    report(errors, "nested_git_repository", not list(PROJECT.rglob(".git")))
    report(errors, "gitlink", not any(line.startswith("160000 ") for line in git("ls-files", "-s", "CyberBoss")[1].splitlines()))
    source = Path(__file__).read_text(encoding="utf-8")
    report(errors, "validator_no_sleep", all(marker not in source for marker in ("time" + ".sleep", "asyncio" + ".sleep")))
    report(errors, "diff_check", git("diff", "--check", CB300_CLOSURE, "HEAD", check=False)[0] == 0)
    validate_state(final, errors)
    validate_cb300_anchor(errors)
    validate_contract(errors)
    validate_code(errors)
    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)
    matrix = run_clean_validation(errors)
    implementation_commit = validate_subject_and_evidence(errors) if final else git("rev-parse", "HEAD")[1]
    validate_commit_boundaries(implementation_commit, final, errors)
    return errors, {"mode": "final" if final else "prepare", "branch": branch, "commands": len(matrix["commands"]), "errors": len(errors)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Validate implemented CB-310 before closure evidence.")
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("CB310_VALIDATION=FAIL")
        return 1
    print("CB310_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
