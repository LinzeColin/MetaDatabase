#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P1.1 / CB-100."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-100"
BASE_COMMIT = "cc00d057ae096e0eccb88c52f7b5f85a10e18a3a"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_TASK_TITLE = "Apply supplied lightweight host layout and systemd walking skeleton"

ALLOWED_EXACT = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/tests/cloud-install-layout.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P1_1_CB_100.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss-journald.conf",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-layout.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/verify-installation.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-cloud.service",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/scripts/validate_cb100.py",
}

IMPLEMENTATION_PATHS = {
    "CyberBoss/tests/cloud-install-layout.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P1_1_CB_100.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss-journald.conf",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-layout.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/verify-installation.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-cloud.service",
    "CyberBoss/scripts/validate_cb100.py",
}

FINAL_EVIDENCE = {
    "VALIDATION_REPORT.md",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "publication-check.json",
    "rollback-plan.json",
    "systemd-acceptance.redacted.json",
    "target-preflight.redacted.json",
    "validation.txt",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.returncode, result.stdout.rstrip()


def changed_paths() -> set[str]:
    paths = set(
        filter(None, git("diff", "--name-only", BASE_COMMIT, "HEAD")[1].splitlines())
    )
    status = git("status", "--porcelain=v1", "--untracked-files=all")[1]
    for raw in status.splitlines():
        value = raw[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        if value:
            paths.add(value)
    return paths


def path_allowed(path: str) -> bool:
    return path in ALLOWED_EXACT or path.startswith("CyberBoss/docs/evidence/CB-100/")


def verify_manifest(path: Path, errors: list[str]) -> None:
    root = path.parent
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
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
        if candidate.is_file() and candidate != path
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def run_command(
    name: str,
    command: list[str],
    cwd: Path,
    required: tuple[str, ...],
    errors: list[str],
    timeout: int = 300,
) -> None:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"command_exception:{name}:{type(error).__name__}")
        return
    output = result.stdout or ""
    if result.returncode != 0:
        errors.append(f"command_failed:{name}:{result.returncode}")
        for line in output.splitlines()[-12:]:
            errors.append(f"command_tail:{name}:{line}")
    for marker in required:
        if marker not in output:
            errors.append(f"command_marker:{name}:{marker}")


def main() -> int:
    prepare_mode = "--prepare" in sys.argv[1:]
    unknown = [arg for arg in sys.argv[1:] if arg != "--prepare"]
    if unknown:
        print(f"ERROR=unknown_arguments:{','.join(unknown)}")
        return 2

    errors: list[str] = []

    def expect(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    expect(git("branch", "--show-current")[1] == EXPECTED_BRANCH, "git_branch")
    expect(git("remote")[1].splitlines() == ["origin"], "git_remote_set")
    expect(git("remote", "get-url", "origin")[1] == EXPECTED_ORIGIN, "git_origin")
    expect(git("cat-file", "-t", BASE_COMMIT, check=False)[1] == "commit", "base")
    expect(
        git("merge-base", "--is-ancestor", BASE_COMMIT, "HEAD", check=False)[0] == 0,
        "base_ancestor",
    )
    for path in sorted(changed_paths()):
        expect(path_allowed(path), f"scope:{path}")
        expect(not path.startswith("CyberBoss/app/src/"), f"app_source:{path}")
        expect(not path.startswith("CyberBoss/vendor/"), f"vendor:{path}")
        expect(
            not re.match(r"CyberBoss/docs/evidence/(?:CB-0\d\d|PG-0)/", path),
            f"historical_evidence:{path}",
        )
    expect(not list(PROJECT.rglob(".git")), "nested_git")
    for row in git("ls-files", "-s", "CyberBoss")[1].splitlines():
        expect(not row.startswith("160000 "), f"gitlink:{row}")

    immutable_paths = [
        "CyberBoss/docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md",
        "CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
        "CyberBoss/docs/product_design/v0.0.0.4/12_CURRENT_ROADMAP.md",
        "CyberBoss/machine/source-lock.json",
        "CyberBoss/vendor",
    ]
    for path in immutable_paths:
        expect(
            git("diff", "--quiet", BASE_COMMIT, "HEAD", "--", path, check=False)[0]
            == 0,
            f"immutable:{path}",
        )

    contract = (
        PROJECT / "docs/governance/RUN_CONTRACT_P1_1_CB_100.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "P1.1 / CB-100 Host Layout and systemd Walking Skeleton",
        BASE_COMMIT,
        "本 Run 不得顺带执行 `P1.2 / CB-110`",
        "target_id_sha256=7865f743d174",
        "100× crash/restart",
        "100× concurrent singleton",
        "不 push",
    ):
        expect(marker in contract, f"contract:{marker}")

    dag = yaml.safe_load((PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text())
    task = next((row for row in dag["tasks"] if row["id"] == "CB-100"), {})
    expect(task.get("title") == EXPECTED_TASK_TITLE, "task_title")
    expect(task.get("stage") == "S1", "task_stage")
    expect(task.get("phase") == "P1.1", "task_phase")
    expect(task.get("dependencies") == ["CB-040"], "task_dependencies")
    expect(task.get("acceptance_criteria") == ["AC-044", "AC-067"], "task_acceptance")
    expect(
        task.get("outputs")
        == [
            "cyberboss user",
            "approved directories and permissions",
            "systemd unit in disabled staging state",
            "release symlink layout",
        ],
        "task_outputs",
    )
    expect(
        "Do not expose any network route yet." in task.get("actions", []),
        "task_no_route",
    )
    expect(
        task.get("verification")
        == [
            "systemd-analyze verify",
            "permission negative tests",
            "second process cannot acquire singleton lock",
        ],
        "task_verification",
    )
    expect(task.get("pass_gate") == "PG-1", "task_gate")

    acceptance = (PACK / "02_PRD_ACCEPTANCE_CONTRACT.md").read_text(encoding="utf-8")
    for marker in (
        "AC-044 | FR-044 | 100× kill/restart + 100× concurrent start",
        "active owner=1；无固定 sleep/LLM call",
        "AC-067 | NFR-008 | clean shell 按 runbook + script --check",
    ):
        expect(marker in acceptance, f"acceptance:{marker}")

    state = load_json(PROJECT / "machine/facts/task_state.json")
    task_status = {row["id"]: row["status"] for row in state["tasks"]}
    expect(task_status.get("CB-040") == "passed", "state_cb040")
    expect(state["pass_gates"].get("PG-0") == "passed", "state_pg0")
    if prepare_mode:
        expect(state["current_run"].get("run_id") == "PG-0", "prepare_run")
        expect(task_status.get("CB-100") == "not_started", "prepare_cb100")
    else:
        expect(state["current_run"].get("run_id") == "P1.1", "final_run")
        expect(state["current_run"].get("task_id") == "CB-100", "final_task")
        expect(
            state["current_run"].get("scope") == "host_layout_and_systemd_walking_skeleton",
            "final_scope",
        )
        expect(state["current_run"].get("status") == "passed", "final_run_status")
        expect(task_status.get("CB-100") == "passed", "final_cb100")
    expect(
        all(
            status == "not_started"
            for task_id, status in task_status.items()
            if task_id not in {"CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100"}
        ),
        "later_task_started",
    )
    expect(
        all(state["pass_gates"][f"PG-{index}"] == "not_started" for index in range(1, 6)),
        "later_gate_started",
    )

    source = load_json(PROJECT / "machine/source-lock.json")
    expect(not any(source["upstream_relationship"].values()), "upstream_relationship")
    conflict = source["whereabouts_license_conflict"]
    expect(
        conflict["compliance_expression"] == "GPL-3.0-only AND AGPL-3.0-only",
        "license_expression",
    )
    expect(conflict["preserve_original_license_and_source"] is True, "license_preserve")
    expect(conflict["upstream_clarification_received"] is False, "license_clarification")

    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)

    install = (KIT / "scripts/install-layout.sh").read_text(encoding="utf-8")
    verify = (KIT / "scripts/verify-installation.sh").read_text(encoding="utf-8")
    unit = (KIT / "systemd/cyberboss-cloud.service").read_text(encoding="utf-8")
    journal = (KIT / "config/cyberboss-journald.conf").read_text(encoding="utf-8")
    for marker in (
        "User=cyberboss",
        "Group=cyberboss",
        "KillMode=control-group",
        "Restart=on-failure",
        "LogNamespace=cyberboss",
        "ProtectSystem=strict",
        "ReadWritePaths=/var/lib/cyberboss /srv/cyberboss-workspaces",
    ):
        expect(marker in unit, f"unit:{marker}")
    expect("User=root" not in unit, "unit_root")
    expect("ReadWritePaths=/opt" not in unit, "unit_opt_write")
    expect("ReadWritePaths=/etc" not in unit, "unit_etc_write")
    expect("systemctl enable" not in install, "install_enable")
    expect("systemctl start" not in install, "install_start")
    expect('systemd/*.{service,timer}' not in install, "install_future_units")
    expect("RELEASE_IDEMPOTENCY=PASS" in install, "install_idempotency")
    expect("resource_dropin_sha256" in install, "install_dropin_identity")
    expect("runtime_installed" in install and "network_routes_created" in install, "install_nonclaims")
    expect("for _iteration in $(seq 1 100)" in verify, "verify_count")
    expect("systemctl kill --kill-who=all --signal=KILL" in verify, "verify_crash")
    expect("ready_predicate=active_pid_and_lock" in verify, "verify_ready")
    expect("CB_SYSTEMD_MEMORY_HIGH" in verify, "verify_dynamic_limits")
    expect("root_required_for_identity_checks" in verify, "verify_root_identity")
    expect("sleep " not in verify, "verify_fixed_sleep")
    expect("fixed_sleep=0 llm_calls=0" in verify, "verify_nonwait")
    expect("SystemMaxUse=@CB_MAX_LOG_BYTES@" in journal, "journal_size")
    expect("RateLimitBurst=500" in journal, "journal_rate")

    dummy_release = "0" * 40
    commands = [
        (
            "shell_syntax",
            [
                "bash",
                "-n",
                str(KIT / "scripts/install-layout.sh"),
                str(KIT / "scripts/verify-installation.sh"),
            ],
            REPO,
            (),
            60,
        ),
        (
            "install_check",
            [
                "bash",
                str(KIT / "scripts/install-layout.sh"),
                "--check",
                "--release-id",
                dummy_release,
            ],
            REPO,
            (
                "INSTALL_CHECK=PASS",
                "live_commands=false",
                "persistent_writes=false",
            ),
            60,
        ),
        (
            "layout_test",
            ["node", "--test", str(PROJECT / "tests/cloud-install-layout.test.js")],
            REPO,
            ("ℹ tests 5", "ℹ pass 5", "ℹ fail 0"),
            120,
        ),
        ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
        (
            "app_test",
            ["npm", "test"],
            PROJECT / "app",
            ("ℹ tests 155", "ℹ pass 155", "ℹ fail 0"),
            300,
        ),
        (
            "cb000",
            [sys.executable, str(PROJECT / "scripts/validate_cb000.py")],
            REPO,
            ("CB000_VALIDATION=PASS",),
            300,
        ),
        (
            "prestage",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            REPO,
            ("PRESTAGE0_VALIDATION=PASS",),
            300,
        ),
        (
            "dag",
            [
                sys.executable,
                str(KIT / "tests/validate_task_dag.py"),
                str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml"),
            ],
            REPO,
            ("DAG_VALIDATION=PASS tasks=30 stages=6",),
            120,
        ),
        (
            "traceability",
            [sys.executable, str(KIT / "tests/validate_traceability.py"), str(PACK)],
            REPO,
            (
                "TRACEABILITY_VALIDATION=PASS requirements=53 "
                "oracles=53 mapped_oracles=53 tasks=30",
            ),
            120,
        ),
        (
            "no_wait",
            [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)],
            REPO,
            (
                "NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 "
                "credential_wait_nodes=0 fixed_sleep_scripts=0",
            ),
            120,
        ),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            REPO,
            (
                "TASKPACK_VALIDATION=PASS files=82 required_items=16 "
                "seven_is_minimum_not_limit=true",
            ),
            120,
        ),
    ]
    for name, command, cwd, required, timeout in commands:
        run_command(name, command, cwd, required, errors, timeout)

    with tempfile.TemporaryDirectory(prefix="cyberboss-cb100-secret-") as raw:
        output = Path(raw) / "scan.json"
        run_command(
            "secret_scan",
            [
                sys.executable,
                str(KIT / "scripts/secret_scan.py"),
                "--repo",
                str(REPO),
                "--scope",
                "CyberBoss",
                "--output",
                str(output),
            ],
            REPO,
            (),
            errors,
            180,
        )
        scan = load_json(output) if output.is_file() else {}
        for key in (
            "forbidden_pattern_hits",
            "known_secret_hits",
            "p0_findings",
            "p1_findings",
            "unreadable_files",
        ):
            expect(scan.get(key) == 0, f"secret:{key}:{scan.get(key)}")
        expect(scan.get("result") == "passed", "secret_result")
        expect(scan.get("secret_values_emitted") is False, "secret_value_emit")

    if not prepare_mode:
        for name in sorted(FINAL_EVIDENCE):
            expect((EVIDENCE / name).is_file(), f"evidence:{name}")
        if all((EVIDENCE / name).is_file() for name in FINAL_EVIDENCE):
            implementation = load_json(EVIDENCE / "implementation-commit.json")
            implementation_commit = implementation.get("commit", "")
            expect(implementation.get("base_commit") == BASE_COMMIT, "impl_base")
            expect(
                re.fullmatch(r"[0-9a-f]{40}", implementation_commit) is not None,
                "impl_commit_format",
            )
            expect(
                git("cat-file", "-t", implementation_commit, check=False)[1] == "commit",
                "impl_commit_object",
            )
            expect(
                git("rev-parse", f"{implementation_commit}^", check=False)[1]
                == BASE_COMMIT,
                "impl_parent",
            )
            expect(
                git(
                    "merge-base",
                    "--is-ancestor",
                    implementation_commit,
                    "HEAD",
                    check=False,
                )[0]
                == 0,
                "impl_ancestor",
            )
            implementation_diff = set(
                filter(
                    None,
                    git("diff", "--name-only", BASE_COMMIT, implementation_commit)[
                        1
                    ].splitlines(),
                )
            )
            expect(implementation_diff == IMPLEMENTATION_PATHS, "impl_path_set")
            expect(
                implementation.get("release_id") == implementation_commit,
                "impl_release_id",
            )
            expect(implementation.get("remote_publication") == "none", "impl_publication")

            preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
            expect(preflight["target_id_sha256"] == EXPECTED_TARGET_HASH, "preflight_target")
            expect(preflight["same_as_cb010"] is True, "preflight_same_host")
            expect(preflight["strict_host_key_checking"] is True, "preflight_known_host")
            expect(preflight["ssh_auth_mode"] == "key_only_batch", "preflight_auth")
            expect(preflight["resource"]["activation_safe"] is True, "preflight_safe")
            expect(preflight["resource"]["guard"] == "recover", "preflight_guard")
            expect(preflight["path_conflicts"] == 0, "preflight_paths")
            expect(preflight["listener_8765"] == 0, "preflight_8765")
            expect(preflight["listener_8780"] == 0, "preflight_8780")
            expect(preflight["persistent_write_performed"] is False, "preflight_write")
            expect(preflight["credential_values_emitted"] is False, "preflight_secret")

            install_result = load_json(EVIDENCE / "install-apply.redacted.json")
            expect(install_result["target_id_sha256"] == EXPECTED_TARGET_HASH, "install_target")
            expect(install_result["release_id"] == implementation_commit, "install_release")
            expect(install_result["apply_count"] == 2, "install_apply_count")
            expect(install_result["first_apply"] == "pass", "install_first")
            expect(install_result["second_apply"] == "idempotent_pass", "install_second")
            expect(install_result["installed_units"] == ["cyberboss-cloud.service"], "install_units")
            expect(install_result["unit_enabled"] is False, "install_enabled")
            expect(install_result["unit_active"] is False, "install_active")
            expect(install_result["runtime_installed"] is False, "install_runtime")
            expect(install_result["network_routes_created"] == 0, "install_routes")
            expect(install_result["credential_values_emitted"] is False, "install_secret")

            systemd = load_json(EVIDENCE / "systemd-acceptance.redacted.json")
            expect(systemd["target_id_sha256"] == EXPECTED_TARGET_HASH, "systemd_target")
            expect(systemd["release_id"] == implementation_commit, "systemd_release")
            expect(systemd["systemd_analyze_verify"] == "pass", "systemd_verify")
            expect(systemd["service_user"] == "cyberboss", "systemd_user")
            expect(systemd["runtime_uid_is_root"] is False, "systemd_root")
            expect(systemd["kill_mode"] == "control-group", "systemd_kill")
            expect(systemd["crash_restart"]["requested"] == 100, "restart_requested")
            expect(systemd["crash_restart"]["passed"] == 100, "restart_passed")
            expect(systemd["crash_restart"]["active_owner_units"] == 1, "restart_owner")
            expect(systemd["crash_restart"]["fixed_sleep_calls"] == 0, "restart_sleep")
            expect(systemd["crash_restart"]["llm_calls"] == 0, "restart_llm")
            expect(systemd["singleton"]["competitors"] == 100, "singleton_requested")
            expect(systemd["singleton"]["denied"] == 100, "singleton_denied")
            expect(systemd["singleton"]["post_release_acquire"] == 1, "singleton_release")
            expect(systemd["permissions"]["denied"] == 5, "permission_denied")
            expect(systemd["permissions"]["allowed"] == 2, "permission_allowed")
            expect(systemd["final_unit_state"] == "disabled/inactive", "systemd_final")
            expect(systemd["listener_8765"] == 0, "systemd_8765")
            expect(systemd["listener_8780"] == 0, "systemd_8780")
            expect(systemd["raw_journal_persisted"] is False, "systemd_journal")
            expect(systemd["credential_values_emitted"] is False, "systemd_secret")

            rollback = load_json(EVIDENCE / "rollback-plan.json")
            expect(rollback["target_id_sha256"] == EXPECTED_TARGET_HASH, "rollback_target")
            expect(rollback["release_id"] == implementation_commit, "rollback_release")
            expect(rollback["rollback_executed"] is False, "rollback_execution")
            expect(rollback["rollback_ready"] is True, "rollback_ready")
            expect(rollback["prestate"]["cyberboss_paths"] == "absent", "rollback_paths")
            expect(rollback["prestate"]["cyberboss_units"] == 0, "rollback_units")

            publication = load_json(EVIDENCE / "publication-check.json")
            expect(publication["state"] == "none", "publication_state")
            expect(publication["remote_branch_matches"] == [], "publication_branch")
            expect(publication["pull_request_matches"] == [], "publication_pr")
            expect(publication["remote_tag_matches"] == [], "publication_tag")
            expect(publication["push_performed"] is False, "publication_push")

            validation = (EVIDENCE / "validation.txt").read_text(encoding="utf-8")
            for marker in (
                "CB100_VALIDATION=PASS",
                "local_tests=5",
                "app_tests=155",
                "ovh_crash_restarts=100",
                "singleton_denials=100",
                "permission_denials=5",
                "unit_enabled=0",
                "unit_active=0",
                "listeners=0",
            ):
                expect(marker in validation, f"validation_marker:{marker}")
            report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
            for marker in (
                "CB-100 Validation Report",
                "Task state: `passed`",
                "CB-110: `not_started`",
                "AC-044: `passed`",
                "AC-067: `passed_for_CB-100_scope`",
                "GPL-3.0-only AND AGPL-3.0-only",
                "upstream_clarification_received=false",
            ):
                expect(marker in report, f"report:{marker}")
            handoff = (PROJECT / "HANDOFF.md").read_text(encoding="utf-8")
            expect("PostgreSQL schema/migration contract" not in handoff, "handoff_stale_scope")
            expect("P1.1 / CB-100" in handoff, "handoff_cb100")
            expect("P1.2 / CB-110" in handoff, "handoff_next")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print("CB100_VALIDATION=FAIL")
        return 1

    if prepare_mode:
        print(
            "CB100_VALIDATION=PASS mode=prepare local_tests=5 app_tests=155 "
            "remote_evidence=pending external_provider_writes=0"
        )
    else:
        print(
            "CB100_VALIDATION=PASS mode=final local_tests=5 app_tests=155 "
            "ovh_crash_restarts=100 singleton_denials=100 permission_denials=5 "
            "unit_enabled=0 unit_active=0 listeners=0 external_provider_writes=0"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
