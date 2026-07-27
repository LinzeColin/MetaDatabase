#!/usr/bin/env python3
"""Fail-closed, credential-free Stage 3 exit-gate validator for CyberBoss PG-3."""

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
EVIDENCE = PROJECT / "docs/evidence/PG-3"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
STAGE3_ANCHOR = "c132ee648ab2ad0f5f66c0dc3ee923c11cabfa42"
STAGE3_ANCHOR_TREE = "7b82c30f2937dd8a17f69055f520ebc7b66dd806"
STAGE3_TASKS = ("CB-300", "CB-310", "CB-320", "CB-330", "CB-340")
STAGE3_SPECS = {
    "CB-300": {
        "phase": "P3.1", "implementation_commit": "02ac88119fc864c37b5346c2ad334e17c6bc7702",
        "repository_tree": "22415bfe64ebd8ea8c09120af6b8cc501ca56da8",
        "closure": "e8243ea81b5ecf239a8ec2df44189259c661adfa", "schema": "cyberboss.cb300",
    },
    "CB-310": {
        "phase": "P3.2", "implementation_commit": "5f977da0ed8c449aeaec3ae769982f6beccfd35e",
        "repository_tree": "ea1985fe90e1fdb8f31e893c2cece946455ba866",
        "closure": "183c2a7b624e5ae25c4ba27bb39651ebf207bfb4", "schema": "cyberboss.cb310",
    },
    "CB-320": {
        "phase": "P3.3", "implementation_commit": "beb92bfa1121f35ee008b10055962a24118a5ec7",
        "repository_tree": "d7fe8e698b5b5a3a7bb6b0ed0b50f9ee34621b84",
        "closure": "202e99cee168f0a2fb618e22819bc350e7f5261c", "schema": "cyberboss.cb320",
    },
    "CB-330": {
        "phase": "P3.4", "implementation_commit": "d994f6272d056812683a920a0baaaba65539f27b",
        "repository_tree": "56a230b3f70cbcb87ba4b20c118a4973b02539f8",
        "closure": "69012f32ae99ea35960c3dc08db059905a4f29ec", "schema": "cyberboss.cb330",
    },
    "CB-340": {
        "phase": "P3.5", "implementation_commit": "9bed78ee1824eebbc4134811993667cb3ca72a9b",
        "repository_tree": "83d61b1efd8656353d4c02a23b26aec67c6af14a",
        "closure": STAGE3_ANCHOR, "schema": "cyberboss.cb340",
    },
}
PG3_ORACLES = (
    "FA-AC-008", "FA-AC-009", "FA-AC-010", "FA-AC-011", "FA-AC-012",
    "FA-AC-013", "FA-AC-014", "FA-AC-029", "FA-AC-032",
)
ROUTER_RESULT = {
    "task_id": "PG-3",
    "selected_skill": None,
    "mode": "DETERMINISTIC_TEST_ONLY",
    "max_lightweight_skill_loads": 0,
    "prohibited_skill_loads": 0,
}
IMPLEMENTATION_PATHS = {
    "CyberBoss/docs/governance/RUN_CONTRACT_PG_3.md",
    "CyberBoss/scripts/validate_pg3.py",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/PG-3/subject.json",
    "CyberBoss/docs/evidence/PG-3/summary.json",
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


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def report(errors: list[str], code: str, condition: bool) -> None:
    if not condition:
        errors.append(code)


def commit_paths(commit: str) -> set[str]:
    parent = git("rev-parse", f"{commit}^")[1]
    return set(filter(None, git("diff", "--name-only", parent, commit)[1].splitlines()))


def tree_at(commit: str, path: str) -> str | None:
    code, output = git("rev-parse", f"{commit}:{path}", check=False)
    return output if code == 0 else None


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
        "CI": "1", "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(tmp),
        "XDG_CONFIG_HOME": str(config), "NPM_CONFIG_USERCONFIG": "/dev/null",
        "NPM_CONFIG_CACHE": str(cache), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
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


def stage3_index(errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_id in STAGE3_TASKS:
        spec = STAGE3_SPECS[task_id]
        evidence_tree = tree_at(STAGE3_ANCHOR, f"CyberBoss/docs/evidence/{task_id}")
        if evidence_tree is None:
            errors.append(f"anchor_evidence_tree:{task_id}")
            evidence_tree = ""
        rows.append({
            "task_id": task_id,
            "phase": spec["phase"],
            "status": "passed",
            "implementation_commit": spec["implementation_commit"],
            "repository_tree": spec["repository_tree"],
            "evidence_tree": evidence_tree,
        })
    return rows


def stage3_digest(rows: list[dict[str, Any]]) -> str:
    return canonical_sha256({"anchor_commit": STAGE3_ANCHOR, "anchor_tree": STAGE3_ANCHOR_TREE, "tasks": rows})


def validate_stage3_history(rows: list[dict[str, Any]], errors: list[str]) -> None:
    report(errors, "stage3_anchor_commit", git("cat-file", "-e", f"{STAGE3_ANCHOR}^{{commit}}", check=False)[0] == 0)
    report(errors, "stage3_anchor_tree", git("rev-parse", f"{STAGE3_ANCHOR}^{{tree}}", check=False)[1] == STAGE3_ANCHOR_TREE)
    for row in rows:
        task_id = str(row["task_id"])
        spec = STAGE3_SPECS[task_id]
        evidence_dir = PROJECT / "docs/evidence" / task_id
        summary_path = evidence_dir / "summary.json"
        subject_path = evidence_dir / "subject.json"
        report(errors, f"history_mutated:{task_id}", git("diff", "--quiet", STAGE3_ANCHOR, "--", f"CyberBoss/docs/evidence/{task_id}", check=False)[0] == 0)
        report(errors, f"closure_missing:{task_id}", git("cat-file", "-e", f"{spec['closure']}^{{commit}}", check=False)[0] == 0)
        report(errors, f"closure_in_anchor:{task_id}", git("merge-base", "--is-ancestor", spec["closure"], STAGE3_ANCHOR, check=False)[0] == 0)
        report(errors, f"implementation_missing:{task_id}", git("cat-file", "-e", f"{spec['implementation_commit']}^{{commit}}", check=False)[0] == 0)
        report(errors, f"implementation_tree:{task_id}", git("rev-parse", f"{spec['implementation_commit']}^{{tree}}", check=False)[1] == spec["repository_tree"])
        try:
            summary = load_json(summary_path)
            subject = load_json(subject_path)
        except (OSError, ValueError, TypeError):
            errors.append(f"evidence_read:{task_id}")
            continue
        report(
            errors,
            f"evidence_contract:{task_id}",
            summary.get("schema_version") == f"{spec['schema']}.closure-summary.v1"
            and summary.get("task_id") == task_id
            and summary.get("product_version") == PRODUCT_VERSION
            and summary.get("taskpack_version") == TASKPACK_VERSION
            and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
            and summary.get("implementation_commit") == spec["implementation_commit"]
            and summary.get("implementation_tree") == spec["repository_tree"]
            and summary.get("result") == "passed"
            and isinstance(summary.get("acceptance"), dict)
            and summary.get("acceptance")
            and all(value == "passed" for value in summary["acceptance"].values())
            and subject.get("schema_version") == f"{spec['schema']}.subject.v1"
            and subject.get("task_id") == task_id
            and subject.get("implementation_commit") == spec["implementation_commit"]
            and subject.get("implementation_tree") == spec["repository_tree"]
            and subject.get("summary_sha256") == sha256(summary_path),
        )
        external = summary.get("external_activation") or {}
        report(
            errors,
            f"truth_state:{task_id}",
            external.get("private_database") == "activation_pending"
            and external.get("r2") == "hazard_blocked"
            and external.get("cloudflare_access") == "activation_pending"
            and external.get("oci") == "activation_pending"
            and summary.get("real_private_database_operations") == 0
            and summary.get("real_r2_operations") == 0
            and summary.get("real_cloudflare_operations") == 0
            and summary.get("real_oci_operations") == 0
            and summary.get("control_plane_llm_calls") == 0
            and summary.get("operations_llm_calls") == 0
            and summary.get("macos_launchd_dependency") is False,
        )


def validate_state(final: bool, evidence_digest: str, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    for task_id in STAGE3_TASKS:
        report(errors, f"task_state_stage3:{task_id}", statuses.get(task_id) == "passed")
    for task_id in ("CB-400", "CB-410", "CB-420", "CB-430", "CB-440", "CB-500", "CB-510", "CB-520", "CB-530", "CB-540"):
        report(errors, f"task_state_future:{task_id}", statuses.get(task_id) == "not_started")
    gates = state.get("pass_gates") or {}
    report(errors, "task_state_prior_gates", all(gates.get(gate) == "passed" for gate in ("PG-0", "PG-1", "PG-2")))
    report(errors, "task_state_later_gates", all(gates.get(gate) == "not_started" for gate in ("PG-4", "PG-5")))
    report(errors, "task_state_pg3", gates.get("PG-3") == ("passed" if final else "not_started"))
    expected_current = (
        {
            "run_id": "PG-3", "gate_id": "PG-3", "task_id": None,
            "scope": "stage_3_adapter_timeline_status_backup_ops_gate", "status": "passed",
        }
        if final
        else {
            "run_id": "P3.5", "gate_id": None, "task_id": "CB-340",
            "scope": "resource_self_heal_retention", "status": "passed",
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
        and overlay.get("status_snapshot_status") == "passed"
        and overlay.get("access_domain_status") == "passed"
        and overlay.get("backup_runtime_status") == "passed"
        and overlay.get("backup_restore_status") == "passed"
        and overlay.get("operations_policy_status") == "passed"
        and overlay.get("retention_status") == "passed"
        and overlay.get("r2_backup_activation") == "hazard_blocked"
        and overlay.get("oci_backup_activation") == "activation_pending"
        and overlay.get("self_heal_activation") == "activation_pending"
        and overlay.get("timer_activation") == "activation_pending"
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_pg3_overlay",
            overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("pg_3_executed") is True
            and overlay.get("stage_3_anchor_commit") == STAGE3_ANCHOR
            and overlay.get("stage_3_subject_digest") == evidence_digest
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_PG_3.md").read_text(encoding="utf-8")
    for marker in (
        "PG-3", PRODUCT_VERSION, TASKPACK_VERSION, TASKPACK_ZIP_SHA256, STAGE3_ANCHOR,
        *PG3_ORACLES, "DETERMINISTIC_TEST_ONLY", "不加载任何 Skill", "CB-400",
        "Private-Database", "macOS `launchd`", "activation_pending", "hazard_blocked",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")


def validate_no_launchd(errors: list[str]) -> None:
    roots = (PROJECT / "app/src", PROJECT / "app/scripts", KIT / "systemd", KIT / "scripts")
    forbidden = ("launchctl", "launchdaemon", "launchagents", "com.apple.launchd")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "node_modules" in path.parts:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(marker in content for marker in forbidden):
                errors.append(f"macos_launchd_dependency:{path.relative_to(REPO)}")


def run_clean_state_replay(errors: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-pg3-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        app_tests = [
            "test/canonical-timeline-projection.test.js", "test/canonical-status-export.test.js",
            "test/canonical-access-domain.test.js", "test/canonical-backup-runtime.test.js",
            "test/canonical-operations-policy.test.js",
        ]
        root_tests = [
            "tests/canonical-timeline.test.js", "tests/canonical-status.test.js",
            "tests/canonical-access-plan.test.js", "tests/canonical-backup-runtime.test.js",
            "tests/canonical-operations-plan.test.js",
        ]
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("stage3_app_focused", ["node", "--test", *app_tests], PROJECT / "app", ("fail 0",), 600),
            ("stage3_root_contract", ["node", "--test", *root_tests], PROJECT, ("fail 0",), 600),
            ("access_policy", ["node", "--test", "tests/access-policy-contract.test.js"], KIT, ("fail 0",), 300),
            ("resource_profile", [sys.executable, str(KIT / "tests/test_resource_profile.py")], REPO, ("OK",), 300),
            ("external_adapter_fixture", [sys.executable, str(KIT / "tests/test_external_adapters.py")], REPO, ("OK",), 300),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_full_regression", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
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


def validate_subject_and_evidence(rows: list[dict[str, Any]], evidence_digest: str, errors: list[str]) -> str | None:
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
        and subject.get("schema_version") == "cyberboss.pg3.subject.v1"
        and subject.get("task_id") == "PG-3"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("stage_3_anchor_commit") == STAGE3_ANCHOR
        and subject.get("stage_3_anchor_tree") == STAGE3_ANCHOR_TREE
        and subject.get("stage_3_evidence_digest") == evidence_digest
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1] == implementation_tree
        and git("merge-base", "--is-ancestor", STAGE3_ANCHOR, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("deployment_release_pointer") == "activation_pending"
        and subject.get("real_private_database_operations") == 0
        and subject.get("real_r2_operations") == 0
        and subject.get("real_cloudflare_operations") == 0
        and subject.get("real_oci_operations") == 0
        and subject.get("real_global_status_operations") == 0
        and subject.get("real_service_operations") == 0
        and subject.get("control_plane_llm_calls") == 0
        and subject.get("operations_llm_calls") == 0
        and subject.get("macos_launchd_dependency") is False,
    )
    expected_external = {
        "private_database": "activation_pending", "r2": "hazard_blocked",
        "cloudflare_access": "activation_pending", "dns_route": "activation_pending",
        "analytics": "activation_pending", "oci": "activation_pending",
        "timeline": "activation_pending", "global_status": "activation_pending",
        "self_heal": "activation_pending", "timer": "activation_pending",
    }
    expected_local = {
        "stage3_focused_regression": "passed", "adapter_truth_state_review": "passed",
        "rollback_contract_review": "passed", "app_regression": "passed", "dag": "passed",
        "traceability": "passed", "no_wait": "passed", "taskpack": "passed", "manifests": "passed",
    }
    report(
        errors,
        "summary_contract",
        summary.get("schema_version") == "cyberboss.pg3.closure-summary.v1"
        and summary.get("task_id") == "PG-3"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("stage_3_anchor_commit") == STAGE3_ANCHOR
        and summary.get("stage_3_anchor_tree") == STAGE3_ANCHOR_TREE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("stage_3_evidence") == rows
        and summary.get("stage_3_evidence_digest") == evidence_digest
        and summary.get("acceptance") == {oracle: "passed" for oracle in PG3_ORACLES}
        and summary.get("local_validation") == expected_local
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("external_activation") == expected_external
        and summary.get("real_private_database_operations") == 0
        and summary.get("real_r2_operations") == 0
        and summary.get("real_cloudflare_operations") == 0
        and summary.get("real_oci_operations") == 0
        and summary.get("real_global_status_operations") == 0
        and summary.get("real_service_operations") == 0
        and summary.get("control_plane_llm_calls") == 0
        and summary.get("operations_llm_calls") == 0
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("next_native_node") == "CB-400",
    )
    for candidate in EVIDENCE.iterdir():
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")
    return implementation_commit


def validate_commit_boundaries(implementation_commit: str | None, final: bool, errors: list[str]) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", STAGE3_ANCHOR, implementation_commit, check=False)[0] == 0)
    report(errors, "implementation_inventory", commit_paths(implementation_commit) == IMPLEMENTATION_PATHS)
    if final:
        report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", implementation_commit, "HEAD", check=False)[0] == 0)
        closure_paths = set(filter(None, git("diff", "--name-only", implementation_commit, "HEAD")[1].splitlines()))
        report(errors, "closure_atomic_inventory", closure_paths == CLOSURE_PATHS)


def validate(final: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    rows = stage3_index(errors)
    evidence_digest = stage3_digest(rows)
    branch = git("branch", "--show-current")[1]
    report(errors, "branch_scope", branch.startswith("codex/cyberboss-"))
    report(errors, "worktree_dirty", not git("status", "--porcelain=v1", "--untracked-files=all")[1])
    report(errors, "nested_git_repository", not list(PROJECT.rglob(".git")))
    report(errors, "gitlink", not any(line.startswith("160000 ") for line in git("ls-files", "-s", "CyberBoss")[1].splitlines()))
    source = Path(__file__).read_text(encoding="utf-8")
    report(errors, "validator_no_sleep", all(marker not in source for marker in ("time" + ".sleep", "asyncio" + ".sleep")))
    report(errors, "diff_check", git("diff", "--check", STAGE3_ANCHOR, "HEAD", check=False)[0] == 0)
    validate_state(final, evidence_digest, errors)
    validate_stage3_history(rows, errors)
    validate_contract(errors)
    validate_no_launchd(errors)
    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)
    matrix = run_clean_state_replay(errors)
    implementation_commit = validate_subject_and_evidence(rows, evidence_digest, errors) if final else git("rev-parse", "HEAD")[1]
    validate_commit_boundaries(implementation_commit, final, errors)
    return errors, {"mode": "final" if final else "prepare", "branch": branch, "commands": len(matrix["commands"]), "errors": len(errors), "stage_3_evidence_digest": evidence_digest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Validate PG-3 implementation before closure evidence.")
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("PG3_VALIDATION=FAIL")
        return 1
    print("PG3_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
