#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P1.2 / CB-110."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-110"
BASE_COMMIT = "35a8d3716b41922298bc0cbe9aa4ff4b78af0266"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_MACHINE_HASH = (
    "ad8247c44f48e66acbd764d9a6aa1e79e2e81c9ca2bd766975607bd1d04f71ef"
)
EXPECTED_TASK_TITLE = "Install and pin Node/Codex plus disabled Claude adapter"
NODE_VERSION = "24.18.0"
NODE_SHA256 = "55aa7153f9d88f28d765fcdad5ae6945b5c0f98a36881703817e4c450fa76742"
CODEX_VERSION = "0.146.0-alpha.3.1"
CODEX_MAIN_SHA256 = (
    "3473d6d6416979b43118d203fa4e584c4e5af939206eee854d9db60c7555df17"
)
CODEX_PLATFORM_SHA256 = (
    "d495bfa843ed9198327cc087b69b99aff09a66d4f5e7139137bc72d02ccf3e53"
)

ALLOWED_EXACT = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/governance/RUN_CONTRACT_P1_2_CB_110.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/runtime-versions.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-toolchain.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/probe-codex-app-server.mjs",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/scripts/validate_cb110.py",
    "CyberBoss/tests/cloud-runtime-version.test.js",
}

IMPLEMENTATION_PATHS = {
    "CyberBoss/docs/governance/RUN_CONTRACT_P1_2_CB_110.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/runtime-versions.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-toolchain.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/probe-codex-app-server.mjs",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh",
    "CyberBoss/scripts/validate_cb110.py",
    "CyberBoss/tests/cloud-runtime-version.test.js",
}

FINAL_EVIDENCE = {
    "VALIDATION_REPORT.md",
    "auth-probe.redacted.json",
    "codex-app-server-probe.redacted.json",
    "external-port-scan.redacted.json",
    "feature-flag-test.txt",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "publication-check.json",
    "readyz.redacted.json",
    "rollback-plan.json",
    "security-report.json",
    "target-preflight.redacted.json",
    "validation.txt",
    "version-manifest.json",
    "versions.md",
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
    return path in ALLOWED_EXACT or path.startswith("CyberBoss/docs/evidence/CB-110/")


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
        expect(not path.startswith("CyberBoss/app/"), f"fixed_app:{path}")
        expect(not path.startswith("CyberBoss/vendor/"), f"vendor:{path}")
        expect(
            not re.match(
                r"CyberBoss/docs/evidence/(?:CB-(?:000|010|020|030|040|100)|PG-0)/",
                path,
            ),
            f"historical_evidence:{path}",
        )
    expect(not list(PROJECT.rglob(".git")), "nested_git")
    for row in git("ls-files", "-s", "CyberBoss")[1].splitlines():
        expect(not row.startswith("160000 "), f"gitlink:{row}")

    immutable_paths = [
        "CyberBoss/LICENSE",
        "CyberBoss/app",
        "CyberBoss/vendor",
        "CyberBoss/machine/source-lock.json",
        "CyberBoss/docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md",
        "CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
        "CyberBoss/docs/product_design/v0.0.0.4/12_CURRENT_ROADMAP.md",
        "CyberBoss/docs/evidence/CB-000",
        "CyberBoss/docs/evidence/CB-010",
        "CyberBoss/docs/evidence/CB-020",
        "CyberBoss/docs/evidence/CB-030",
        "CyberBoss/docs/evidence/CB-040",
        "CyberBoss/docs/evidence/CB-100",
        "CyberBoss/docs/evidence/PG-0",
    ]
    for relative in immutable_paths:
        expect(
            git("diff", "--quiet", BASE_COMMIT, "HEAD", "--", relative, check=False)[
                0
            ]
            == 0,
            f"immutable:{relative}",
        )

    contract = (
        PROJECT / "docs/governance/RUN_CONTRACT_P1_2_CB_110.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "P1.2 / CB-110 Pinned Cloud Runtime Toolchain",
        BASE_COMMIT,
        "target_id_sha256=7865f743d174",
        NODE_VERSION,
        CODEX_VERSION,
        "本 Run 不执行设备认证，不安装 Claude Code",
        "不进入 `P1.3 / CB-120`",
        "不 push",
    ):
        expect(marker in contract, f"contract:{marker}")

    dag = yaml.safe_load((PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text())
    task = next((row for row in dag["tasks"] if row["id"] == "CB-110"), {})
    expect(task.get("title") == EXPECTED_TASK_TITLE, "task_title")
    expect(task.get("stage") == "S1", "task_stage")
    expect(task.get("phase") == "P1.2", "task_phase")
    expect(task.get("dependencies") == ["CB-100", "CB-030"], "task_dependencies")
    expect(
        task.get("acceptance_criteria") == ["AC-011", "AC-017", "AC-065"],
        "task_acceptance",
    )
    expect(
        task.get("outputs")
        == [
            "Node 22+",
            "Codex CLI/App Server ready",
            "Claude Code optional binary with no credentials/disabled flag",
            "version manifest",
        ],
        "task_outputs",
    )
    expect(
        "Codex App Server cannot become ready" in task.get("stop_conditions", []),
        "task_stop_ready",
    )
    expect(
        "Auth requires public callback/exposure" in task.get("stop_conditions", []),
        "task_stop_callback",
    )
    expect(task.get("pass_gate") == "PG-1", "task_gate")

    acceptance = (PACK / "02_PRD_ACCEPTANCE_CONTRACT.md").read_text(encoding="utf-8")
    for marker in (
        "AC-011 | FR-011 | `ss -lntp` + 外部 port scan",
        "8765 仅 127.0.0.1；公网不可达",
        "AC-017 | FR-017 | 默认配置尝试 Claude",
        "adapter 不启动；flag+eval gate 才能启用",
        "AC-065 | NFR-006 | port/secret/workspace/security suite",
        "P0/P1 findings=0",
    ):
        expect(marker in acceptance, f"acceptance:{marker}")

    state = load_json(PROJECT / "machine/facts/task_state.json")
    task_status = {row["id"]: row["status"] for row in state["tasks"]}
    for task_id in ("CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100"):
        expect(task_status.get(task_id) == "passed", f"state_dependency:{task_id}")
    expect(state["pass_gates"].get("PG-0") == "passed", "state_pg0")
    if prepare_mode:
        expect(state["current_run"].get("run_id") == "P1.1", "prepare_run")
        expect(task_status.get("CB-110") == "not_started", "prepare_cb110")
    else:
        expect(state["current_run"].get("run_id") == "P1.2", "final_run")
        expect(state["current_run"].get("task_id") == "CB-110", "final_task")
        expect(
            state["current_run"].get("scope") == "pinned_cloud_runtime_toolchain",
            "final_scope",
        )
        expect(state["current_run"].get("status") == "passed", "final_run_status")
        expect(task_status.get("CB-110") == "passed", "final_cb110")
    completed = {
        "CB-000",
        "CB-010",
        "CB-020",
        "CB-030",
        "CB-040",
        "CB-100",
        *(("CB-110",) if not prepare_mode else ()),
    }
    expect(
        all(
            status == ("passed" if task_id in completed else "not_started")
            for task_id, status in task_status.items()
        ),
        "task_state_boundary",
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
    expect(conflict["must_not_claim_upstream_clarification"] is True, "license_claim")

    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)

    runtime_spec = load_json(KIT / "config/runtime-versions.json")
    expect(runtime_spec.get("task_id") == "CB-110", "runtime_spec_task")
    expect(runtime_spec.get("platform") == "linux-x64", "runtime_spec_platform")
    expect(runtime_spec["node"]["version"] == NODE_VERSION, "node_version")
    expect(runtime_spec["node"]["archive_sha256"] == NODE_SHA256, "node_sha")
    expect(runtime_spec["codex"]["version"] == CODEX_VERSION, "codex_version")
    expect(
        runtime_spec["codex"]["main_archive_sha256"] == CODEX_MAIN_SHA256,
        "codex_main_sha",
    )
    expect(
        runtime_spec["codex"]["platform_archive_sha256"] == CODEX_PLATFORM_SHA256,
        "codex_platform_sha",
    )
    expect(
        runtime_spec["runtime"]["loopback_endpoint"] == "ws://127.0.0.1:8765",
        "runtime_endpoint",
    )
    expect(
        runtime_spec["claude_code"]
        == {
            "install_policy": "optional_not_installed",
            "credential_policy": "absent",
            "feature_flag_default": False,
            "evaluation_gate_default": False,
        },
        "claude_spec",
    )

    install = (KIT / "scripts/install-runtime-toolchain.sh").read_text(
        encoding="utf-8"
    )
    probe = (KIT / "scripts/probe-codex-app-server.mjs").read_text(encoding="utf-8")
    run = (KIT / "scripts/run-cyberboss.sh").read_text(encoding="utf-8")
    env_example = (KIT / "config/cyberboss.env.example").read_text(encoding="utf-8")
    for marker in (
        "download_and_verify",
        "archive_sha256_mismatch",
        "assert_no_escaping_symlink",
        "node:sqlite",
        "app-server --help",
        "version-manifest.json",
        "auth_content_read=false",
        "claude_binary=absent",
        "global_toolchain_modified=false",
    ):
        expect(marker in install, f"installer:{marker}")
    expect("npm install" not in install, "installer_npm_install")
    expect("apt-get" not in install, "installer_apt")
    expect("github.com" not in install, "installer_github")
    for marker in (
        'const EXPECTED_ENDPOINT = "ws://127.0.0.1:8765"',
        'method: "initialize"',
        'method: "initialized"',
        "authenticated_turn_started: false",
        "credential_content_read: false",
        "public_callback_used: false",
    ):
        expect(marker in probe, f"probe:{marker}")
    expect("0.0.0.0" not in probe, "probe_nonloopback")
    expect("turn/start" not in probe, "probe_turn")
    expect('CB_CLAUDE_RUNTIME:-false}" != "true"' in run, "claude_feature_gate")
    expect(
        'CB_CLAUDE_EVAL_PASSED:-false}" != "true"' in run,
        "claude_eval_gate",
    )
    expect("CB_CLAUDE_RUNTIME=false" in env_example, "claude_feature_default")
    expect("CB_CLAUDE_EVAL_PASSED=false" in env_example, "claude_eval_default")

    dummy_release = "0" * 40
    commands = [
        (
            "shell_syntax",
            [
                "bash",
                "-n",
                str(KIT / "scripts/install-runtime-toolchain.sh"),
                str(KIT / "scripts/run-cyberboss.sh"),
            ],
            REPO,
            (),
            60,
        ),
        (
            "probe_syntax",
            ["node", "--check", str(KIT / "scripts/probe-codex-app-server.mjs")],
            REPO,
            (),
            60,
        ),
        (
            "install_check",
            [
                "bash",
                str(KIT / "scripts/install-runtime-toolchain.sh"),
                "--check",
                "--release-id",
                dummy_release,
            ],
            REPO,
            (
                "RUNTIME_TOOLCHAIN_CHECK=PASS",
                "live_commands=false",
                "persistent_writes=false",
            ),
            60,
        ),
        (
            "runtime_test",
            ["node", "--test", str(PROJECT / "tests/cloud-runtime-version.test.js")],
            REPO,
            ("tests 6", "pass 6", "fail 0"),
            120,
        ),
        ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
        (
            "app_test",
            ["npm", "test"],
            PROJECT / "app",
            ("tests 155", "pass 155", "fail 0"),
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
            ("TASKPACK_VALIDATION=PASS files=", "seven_is_minimum_not_limit=true"),
            120,
        ),
        (
            "diff_check",
            ["git", "diff", "--check"],
            REPO,
            (),
            60,
        ),
    ]
    for name, command, cwd, required, timeout in commands:
        run_command(name, command, cwd, required, errors, timeout)

    with tempfile.TemporaryDirectory(prefix="cyberboss-cb110-secret-") as raw:
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
            implementation_commit = str(implementation.get("commit") or "")
            expect(implementation.get("base_commit") == BASE_COMMIT, "impl_base")
            expect(
                re.fullmatch(r"[0-9a-f]{40}", implementation_commit) is not None,
                "impl_commit_format",
            )
            expect(
                git("cat-file", "-t", implementation_commit, check=False)[1]
                == "commit",
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
            expect(implementation.get("release_id") == implementation_commit, "impl_release")
            expect(
                implementation.get("target_id_sha256") == EXPECTED_TARGET_HASH,
                "impl_target",
            )
            expect(implementation.get("remote_publication") == "none", "impl_publication")

            preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
            expect(preflight["target_id_sha256"] == EXPECTED_TARGET_HASH, "preflight_target")
            expect(preflight["machine_id_sha256"] == EXPECTED_MACHINE_HASH, "preflight_machine")
            expect(preflight["same_as_cb100"] is True, "preflight_same_host")
            expect(preflight["strict_host_key_checking"] is True, "preflight_known_host")
            expect(preflight["ssh_auth_mode"] == "key_only_batch", "preflight_auth")
            expect(preflight["listener_8765"] == 0, "preflight_8765")
            expect(preflight["listener_8780"] == 0, "preflight_8780")
            expect(preflight["unit_state"] == "disabled/inactive", "preflight_unit")
            expect(preflight["persistent_write_performed"] is False, "preflight_write")
            expect(preflight["credential_values_emitted"] is False, "preflight_secret")

            install_result = load_json(EVIDENCE / "install-apply.redacted.json")
            expect(install_result["target_id_sha256"] == EXPECTED_TARGET_HASH, "install_target")
            expect(install_result["release_id"] == implementation_commit, "install_release")
            expect(install_result["apply_count"] == 2, "install_apply_count")
            expect(install_result["first_apply"] == "pass", "install_first")
            expect(install_result["second_apply"] == "idempotent_pass", "install_second")
            expect(install_result["node"]["version"] == NODE_VERSION, "install_node")
            expect(install_result["node"]["archive_sha256"] == NODE_SHA256, "install_node_sha")
            expect(install_result["node"]["sqlite_self_test"] == "pass", "install_sqlite")
            expect(install_result["codex"]["version"] == CODEX_VERSION, "install_codex")
            expect(
                install_result["codex"]["main_archive_sha256"] == CODEX_MAIN_SHA256,
                "install_codex_main_sha",
            )
            expect(
                install_result["codex"]["platform_archive_sha256"]
                == CODEX_PLATFORM_SHA256,
                "install_codex_platform_sha",
            )
            expect(install_result["global_toolchain_modified"] is False, "install_global")
            expect(install_result["current_release_changed"] is False, "install_current")
            expect(install_result["business_runtime_started"] is False, "install_runtime")
            expect(install_result["credential_values_emitted"] is False, "install_secret")

            version_manifest = load_json(EVIDENCE / "version-manifest.json")
            expect(version_manifest["release_commit"] == implementation_commit, "manifest_release")
            expect(version_manifest["node"]["version"] == NODE_VERSION, "manifest_node")
            expect(version_manifest["codex"]["version"] == CODEX_VERSION, "manifest_codex")
            expect(version_manifest["codex"]["auth_activation"] == "activation_pending", "manifest_auth")
            expect(version_manifest["claude_code"]["binary"] == "absent", "manifest_claude")
            expect(version_manifest["public_callback_required"] is False, "manifest_callback")
            expect(version_manifest["business_runtime_started"] is False, "manifest_runtime")

            app_probe = load_json(EVIDENCE / "codex-app-server-probe.redacted.json")
            expect(app_probe["endpoint"] == "ws://127.0.0.1:8765", "probe_endpoint")
            expect(app_probe["readyz"]["passed"] is True, "probe_ready")
            expect(app_probe["readyz"]["status"] == 200, "probe_ready_status")
            expect(
                app_probe["protocol"]["initialize_result_present"] is True,
                "probe_initialize",
            )
            expect(app_probe["protocol"]["initialized_sent"] is True, "probe_initialized")
            expect(
                app_probe["protocol"]["authenticated_turn_started"] is False,
                "probe_turn",
            )
            expect(app_probe["credential_content_read"] is False, "probe_auth_read")
            expect(app_probe["public_callback_used"] is False, "probe_callback")
            expect(app_probe["business_runtime_started"] is False, "probe_runtime")
            expect(app_probe["child_cleanup"] == "complete", "probe_cleanup")

            readyz = load_json(EVIDENCE / "readyz.redacted.json")
            expect(readyz["target_id_sha256"] == EXPECTED_TARGET_HASH, "ready_target")
            expect(readyz["release_id"] == implementation_commit, "ready_release")
            expect(readyz["listener_addresses"] == ["127.0.0.1:8765"], "ready_listener")
            expect(readyz["non_loopback_listener_count"] == 0, "ready_nonloopback")
            expect(readyz["readyz_status"] == 200, "ready_status")
            expect(readyz["protocol_initialize"] == "pass", "ready_protocol")
            expect(readyz["final_listener_count"] == 0, "ready_final_listener")
            expect(readyz["final_process_count"] == 0, "ready_final_process")

            external_scan = load_json(EVIDENCE / "external-port-scan.redacted.json")
            expect(external_scan["target_id_sha256"] == EXPECTED_TARGET_HASH, "scan_target")
            expect(external_scan["port"] == 8765, "scan_port")
            expect(external_scan["performed_while_loopback_ready"] is True, "scan_live")
            expect(external_scan["public_tcp_reachable"] is False, "scan_reachable")
            expect(external_scan["target_address_persisted"] is False, "scan_address")

            auth = load_json(EVIDENCE / "auth-probe.redacted.json")
            expect(auth["probe_scope"] == "authorized_ovh_staging", "auth_scope")
            expect(auth["codex"]["cli_present"] is True, "auth_cli")
            expect(auth["codex"]["version"] == CODEX_VERSION, "auth_version")
            expect(auth["codex"]["target_adapter_state"] == "activation_pending", "auth_state")
            expect(auth["credential_content_read"] is False, "auth_read")
            expect(auth["credential_values_emitted"] is False, "auth_emit")
            expect(auth["external_mutation_performed"] is False, "auth_write")

            feature = (EVIDENCE / "feature-flag-test.txt").read_text(encoding="utf-8")
            for marker in (
                "FEATURE=false EVAL=false RESULT=denied",
                "FEATURE=true EVAL=false RESULT=denied",
                "FEATURE=false EVAL=true RESULT=denied",
                "FEATURE=true EVAL=true RESULT=gate_passed_adapter_not_started",
                "CLAUDE_BINARY=absent",
                "CLAUDE_CREDENTIAL=absent",
                "BUSINESS_RUNTIME_STARTED=0",
            ):
                expect(marker in feature, f"feature:{marker}")

            security = load_json(EVIDENCE / "security-report.json")
            for key in (
                "p0_findings",
                "p1_findings",
                "secret_pattern_hits",
                "known_secret_hits",
                "non_loopback_listener_count",
                "public_callback_count",
                "workspace_mutations",
                "provider_writes",
                "private_database_writes",
                "credential_content_reads",
            ):
                expect(security.get(key) == 0, f"security:{key}")
            expect(security["business_runtime_started"] is False, "security_runtime")
            expect(security["result"] == "passed", "security_result")

            rollback = load_json(EVIDENCE / "rollback-plan.json")
            expect(rollback["target_id_sha256"] == EXPECTED_TARGET_HASH, "rollback_target")
            expect(rollback["release_id"] == implementation_commit, "rollback_release")
            expect(rollback["rollback_executed"] is False, "rollback_execution")
            expect(rollback["rollback_ready"] is True, "rollback_ready")
            expect(rollback["preserve_codex_home"] is True, "rollback_auth")
            expect(rollback["current_release_unchanged"] is True, "rollback_current")

            publication = load_json(EVIDENCE / "publication-check.json")
            expect(publication["state"] == "none", "publication_state")
            expect(publication["remote_branch_matches"] == [], "publication_branch")
            expect(publication["pull_request_matches"] == [], "publication_pr")
            expect(publication["remote_tag_matches"] == [], "publication_tag")
            expect(publication["push_performed"] is False, "publication_push")

            validation = (EVIDENCE / "validation.txt").read_text(encoding="utf-8")
            for marker in (
                "CB110_VALIDATION=PASS",
                "local_tests=6",
                "app_tests=155",
                "node=24.18.0",
                "sqlite=PASS",
                "codex=0.146.0-alpha.3.1",
                "readyz=200",
                "initialize=PASS",
                "external_8765_reachable=0",
                "claude_negative=PASS",
                "p0_findings=0",
                "p1_findings=0",
            ):
                expect(marker in validation, f"validation_marker:{marker}")

            report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
            for marker in (
                "CB-110 Validation Report",
                "Task state: `passed`",
                "CB-120: `not_started`",
                "AC-011: `passed`",
                "AC-017: `passed`",
                "AC-065: `passed_for_CB-110_scope`",
                "Codex auth: `activation_pending`",
                "GPL-3.0-only AND AGPL-3.0-only",
                "upstream_clarification_received=false",
            ):
                expect(marker in report, f"report:{marker}")
            versions = (EVIDENCE / "versions.md").read_text(encoding="utf-8")
            for marker in (
                "Node.js `24.18.0`",
                "Codex CLI `0.146.0-alpha.3.1`",
                "SQLite adapter: `PASS`",
                "Claude Code binary: `absent`",
                "Codex auth: `activation_pending`",
                "ws://127.0.0.1:8765",
            ):
                expect(marker in versions, f"versions:{marker}")
            handoff = (PROJECT / "HANDOFF.md").read_text(encoding="utf-8")
            expect("P1.2 / CB-110" in handoff, "handoff_cb110")
            expect("P1.3 / CB-120" in handoff, "handoff_next")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print("CB110_VALIDATION=FAIL")
        return 1

    if prepare_mode:
        print(
            "CB110_VALIDATION=PASS mode=prepare local_tests=6 app_tests=155 "
            "remote_evidence=pending external_provider_writes=0"
        )
    else:
        print(
            "CB110_VALIDATION=PASS mode=final local_tests=6 app_tests=155 "
            f"node={NODE_VERSION} sqlite=PASS codex={CODEX_VERSION} readyz=200 "
            "initialize=PASS external_8765_reachable=0 claude_negative=PASS "
            "p0_findings=0 p1_findings=0 external_provider_writes=0"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
