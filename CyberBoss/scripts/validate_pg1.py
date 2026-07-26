#!/usr/bin/env python3
"""Fail-closed independent Stage 1 exit-gate validator for CyberBoss PG-1."""

from __future__ import annotations

import argparse
import json
import os
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
EVIDENCE = PROJECT / "docs/evidence/PG-1"
BASE_COMMIT = "4020f07bc086ab9827ab97ddf295927075189a9f"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
EXPECTED_CANDIDATE = "571438751638a01c4648ff4fdf27403a97a971c3"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
PG1_DEFINITION = (
    "All-cloud Walking Skeleton passes with channel/runtime simulators and "
    "loopback transport; real adapters are additionally verified when activated."
)
STAGE1_TASKS = ["CB-100", "CB-110", "CB-120", "CB-130", "CB-140"]
EXPECTED_ACCEPTANCE = {
    "CB-100": ["AC-044", "AC-067"],
    "CB-110": ["AC-011", "AC-017", "AC-065"],
    "CB-120": ["AC-013", "AC-014", "AC-064"],
    "CB-130": ["AC-011", "AC-040", "AC-044", "AC-062"],
    "CB-140": ["AC-001", "AC-010", "AC-061", "AC-002", "AC-006"],
}
EXPECTED_HISTORY = {
    "CB-100": {
        "phase": "P1.1",
        "implementation": "b2a603e415a2045b441f31e07cf74ac451ba6240",
        "closure": "35a8d3716b41922298bc0cbe9aa4ff4b78af0266",
        "tree": "048f4472f7f354bd7acc12361aa18c3591d289fd",
    },
    "CB-110": {
        "phase": "P1.2",
        "implementation": "3cd8eee4f6b7c0a78f7b6fde90dae0f4ff1392fc",
        "closure": "bacb20147b1f9971b8d47c578599fd3494bed5c3",
        "tree": "6512e8b6b892d2e00b6560a2dafc9da2ee3cdd4f",
    },
    "CB-120": {
        "phase": "P1.3",
        "implementation": "10d988e908d72ea1a43bbed04a2130a338663363",
        "closure": "9e1c128aa3890f7c0ea0e69000fdb46e32a4bb00",
        "tree": "5ae1fc97b2899ccc30b3edea4df9fa5ead933c87",
    },
    "CB-130": {
        "phase": "P1.4",
        "implementation": "81dc1ee211e554dd8b84001bfca4b8aa73bb89dd",
        "closure": "20405812e4ebfc51d59093b5916dd624317309a7",
        "tree": "8a887d859a90940a9bc1071ae9daadbab081703b",
    },
    "CB-140": {
        "phase": "P1.5",
        "implementation": EXPECTED_CANDIDATE,
        "closure": BASE_COMMIT,
        "tree": "88140d620e63e2e1955a1f3686844ddf8f6a5901",
    },
}

ALLOWED_EXACT = {
    "CyberBoss/docs/governance/RUN_CONTRACT_PG_1.md",
    "CyberBoss/scripts/validate_pg1.py",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/README.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/CHANGELOG.md",
}
FINAL_EVIDENCE = {
    "VALIDATION_REPORT.md",
    "credential-free-probe.json",
    "gate-matrix.json",
    "gate-validation.txt",
    "publication-check.json",
    "stage1-evidence-index.json",
    "target-readonly.redacted.json",
}
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
SENSITIVE_ENV_PREFIXES = ("AWS_", "OCI_", "CF_", "GH_")
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bwxid_[A-Za-z0-9_-]+\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
            f"{result.stderr.strip()[:180]}"
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
    return path in ALLOWED_EXACT or path.startswith("CyberBoss/docs/evidence/PG-1/")


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
        raise RuntimeError("credential environment scrub failed")

    home = root / "home"
    codex_home = root / "empty-codex-home"
    wechat_state = root / "empty-wechat-state"
    tmp = root / "tmp"
    npm_cache = root / "npm-cache"
    dependency_site = Path(yaml.__file__).resolve().parents[1]
    for directory in (home, codex_home, wechat_state, tmp, npm_cache):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "CYBERBOSS_STATE_DIR": str(wechat_state),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "TMPDIR": str(tmp),
            "NPM_CONFIG_USERCONFIG": "/dev/null",
            "NPM_CONFIG_CACHE": str(npm_cache),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(dependency_site),
            "CI": "1",
            "NO_COLOR": "1",
        }
    )
    return environment, removed


def run_command(
    name: str,
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    errors: list[str],
    required: tuple[str, ...] = (),
    timeout: int = 300,
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
        return {"name": name, "exit_code": None, "required_markers": list(required)}
    output = result.stdout or ""
    if result.returncode != 0:
        errors.append(f"command_failed:{name}:{result.returncode}")
        for line in output.splitlines()[-12:]:
            errors.append(f"command_tail:{name}:{line[:180]}")
    for marker in required:
        if marker not in output:
            errors.append(f"command_marker:{name}:{marker}")
    return {
        "name": name,
        "exit_code": result.returncode,
        "required_markers": list(required),
    }


def run_credential_free_matrix(errors: list[str]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cyberboss-pg1-") as raw_root:
        fixture_root = Path(raw_root)
        environment, removed_count = credential_free_environment(fixture_root)
        python = sys.executable
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            (
                "prestage",
                [python, str(PROJECT / "scripts/validate_prestage0.py")],
                REPO,
                ("PRESTAGE0_VALIDATION=PASS",),
                300,
            ),
            (
                "dag",
                [
                    python,
                    str(KIT / "tests/validate_task_dag.py"),
                    str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml"),
                ],
                REPO,
                ("DAG_VALIDATION=PASS tasks=30 stages=6",),
                120,
            ),
            (
                "traceability",
                [python, str(KIT / "tests/validate_traceability.py"), str(PACK)],
                REPO,
                ("TRACEABILITY_VALIDATION=PASS requirements=53",),
                120,
            ),
            (
                "no_wait",
                [python, str(KIT / "tests/validate_no_wait.py"), str(PACK)],
                REPO,
                (
                    "NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 "
                    "credential_wait_nodes=0 fixed_sleep_scripts=0",
                ),
                120,
            ),
            (
                "taskpack",
                [python, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
                REPO,
                ("TASKPACK_VALIDATION=PASS", "seven_is_minimum_not_limit=true"),
                120,
            ),
            (
                "simulator_contract",
                ["node", "--test", str(KIT / "tests/simulator-contract.test.mjs")],
                REPO,
                ("tests 5", "pass 5", "fail 0"),
                180,
            ),
            (
                "app_walking_static",
                ["node", "--test", "test/cloud-walking-skeleton.test.js"],
                PROJECT / "app",
                ("tests 4", "pass 4", "fail 0"),
                120,
            ),
            (
                "app_walking_live",
                ["node", "--test", "test/cloud-walking-skeleton-live.test.js"],
                PROJECT / "app",
                ("tests 1", "pass 1", "fail 0"),
                180,
            ),
            (
                "root_walking_contract",
                ["node", "--test", "tests/cloud-walking-skeleton.test.js"],
                PROJECT,
                ("tests 5", "pass 5", "fail 0"),
                120,
            ),
            (
                "root_process_contract",
                ["node", "--test", "tests/cloud-process-family.test.js"],
                PROJECT,
                ("tests 5", "pass 5", "fail 0"),
                120,
            ),
            (
                "app_check",
                ["npm", "run", "check"],
                PROJECT / "app",
                (),
                300,
            ),
            (
                "app_test",
                ["npm", "test"],
                PROJECT / "app",
                ("tests 175", "pass 175", "fail 0"),
                360,
            ),
        ]
        for name, command, cwd, required, timeout in specs:
            results.append(
                run_command(
                    name,
                    command,
                    cwd,
                    environment,
                    errors,
                    required,
                    timeout,
                )
            )

        shell_files = sorted((KIT / "scripts").glob("*.sh")) + sorted(
            (KIT / "simulators").glob("*.sh")
        )
        syntax_failures = 0
        for script in shell_files:
            result = subprocess.run(
                ["bash", "-n", str(script)],
                cwd=REPO,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                syntax_failures += 1
                errors.append(f"shell_syntax:{script.relative_to(REPO)}")
        results.append(
            {
                "name": "shell_syntax",
                "exit_code": 0 if syntax_failures == 0 else 1,
                "files_checked": len(shell_files),
            }
        )

        auth_output = fixture_root / "auth-probe.json"
        results.append(
            run_command(
                "auth_clean_fixture",
                [
                    python,
                    str(KIT / "scripts/auth_activation_check.py"),
                    "--mode",
                    "authorized_ovh_staging",
                    "--codex-home",
                    environment["CODEX_HOME"],
                    "--wechat-state-dir",
                    environment["CYBERBOSS_STATE_DIR"],
                    "--output",
                    str(auth_output),
                ],
                REPO,
                environment,
                errors,
                (
                    "AUTH_ACTIVATION_CHECK=PASS",
                    "external_mutation=0",
                    "credential_values_emitted=0",
                ),
                120,
            )
        )
        auth = load_json(auth_output) if auth_output.is_file() else {}
        if auth.get("external_mutation_performed") is not False:
            errors.append("auth_fixture_mutation")
        if auth.get("credential_content_read") is not False:
            errors.append("auth_fixture_content_read")
        if auth.get("credential_values_emitted") is not False:
            errors.append("auth_fixture_value_emit")
        if (auth.get("codex") or {}).get("target_adapter_state") != "activation_pending":
            errors.append("auth_fixture_codex")
        if (auth.get("wechat") or {}).get("target_adapter_state") != "activation_pending":
            errors.append("auth_fixture_wechat")

        secret_output = fixture_root / "secret-scan.json"
        results.append(
            run_command(
                "secret_scan",
                [
                    python,
                    str(KIT / "scripts/secret_scan.py"),
                    "--repo",
                    str(REPO),
                    "--scope",
                    "CyberBoss",
                    "--output",
                    str(secret_output),
                ],
                REPO,
                environment,
                errors,
                (),
                180,
            )
        )
        secret = load_json(secret_output) if secret_output.is_file() else {}
        for key in (
            "forbidden_pattern_hits",
            "known_secret_hits",
            "p0_findings",
            "p1_findings",
            "unreadable_files",
        ):
            if secret.get(key) != 0:
                errors.append(f"secret_scan:{key}:{secret.get(key)}")
        if secret.get("result") != "passed":
            errors.append("secret_scan_result")
        if secret.get("secret_values_emitted") is not False:
            errors.append("secret_scan_value_emit")

        return {
            "removed_environment_key_count": removed_count,
            "isolated_home": True,
            "empty_codex_home": True,
            "empty_wechat_state": True,
            "commands": results,
            "auth": {
                "codex": (auth.get("codex") or {}).get("target_adapter_state"),
                "wechat": (auth.get("wechat") or {}).get("target_adapter_state"),
                "external_mutation_performed": auth.get("external_mutation_performed"),
                "credential_values_emitted": auth.get("credential_values_emitted"),
            },
            "secret_scan": {
                "result": secret.get("result"),
                "scanned_files": secret.get("scanned_files"),
                "scanned_bytes": secret.get("scanned_bytes"),
                "forbidden_pattern_hits": secret.get("forbidden_pattern_hits"),
                "known_secret_hits": secret.get("known_secret_hits"),
                "p0_findings": secret.get("p0_findings"),
                "p1_findings": secret.get("p1_findings"),
                "unreadable_files": secret.get("unreadable_files"),
                "secret_values_emitted": secret.get("secret_values_emitted"),
            },
        }


def evidence_json(task_id: str, name: str) -> dict[str, Any]:
    return load_json(PROJECT / "docs/evidence" / task_id / name)


def validate_historical_evidence(errors: list[str]) -> None:
    for task_id, expected in EXPECTED_HISTORY.items():
        evidence_path = f"CyberBoss/docs/evidence/{task_id}"
        if git("diff", "--quiet", BASE_COMMIT, "--", evidence_path, check=False)[0] != 0:
            errors.append(f"history_dirty:{task_id}")
        tree = git("rev-parse", f"{BASE_COMMIT}:{evidence_path}")[1]
        if tree != expected["tree"]:
            errors.append(f"history_tree:{task_id}")
        if git("cat-file", "-t", expected["implementation"], check=False)[1] != "commit":
            errors.append(f"implementation_commit:{task_id}")
        if git("cat-file", "-t", expected["closure"], check=False)[1] != "commit":
            errors.append(f"closure_commit:{task_id}")
        if git(
            "merge-base",
            "--is-ancestor",
            expected["closure"],
            BASE_COMMIT,
            check=False,
        )[0] != 0:
            errors.append(f"closure_ancestry:{task_id}")
        report = (
            PROJECT / "docs/evidence" / task_id / "VALIDATION_REPORT.md"
        ).read_text(encoding="utf-8")
        if "passed" not in report:
            errors.append(f"history_report:{task_id}")

    cb100 = evidence_json("CB-100", "systemd-acceptance.redacted.json")
    if (
        cb100.get("systemd_analyze_verify") != "pass"
        or cb100.get("runtime_uid_is_root") is not False
        or cb100.get("kill_mode") != "control-group"
        or (cb100.get("crash_restart") or {}).get("passed") != 100
        or (cb100.get("singleton") or {}).get("denied") != 100
        or cb100.get("final_unit_state") != "disabled/inactive"
        or cb100.get("listener_8765") != 0
        or cb100.get("listener_8780") != 0
    ):
        errors.append("history_cb100")

    cb110_version = evidence_json("CB-110", "version-manifest.json")
    cb110_ready = evidence_json("CB-110", "readyz.redacted.json")
    cb110_auth = evidence_json("CB-110", "auth-probe.redacted.json")
    cb110_security = evidence_json("CB-110", "security-report.json")
    if (
        (cb110_version.get("node") or {}).get("version") != "24.18.0"
        or (cb110_version.get("node") or {}).get("sqlite_adapter") != "node:sqlite"
        or (cb110_version.get("codex") or {}).get("version") != "0.146.0-alpha.3.1"
        or (cb110_version.get("claude_code") or {}).get("adapter_state") != "disabled"
        or cb110_ready.get("readyz_status") != 200
        or cb110_ready.get("non_loopback_listener_count") != 0
        or cb110_ready.get("final_listener_count") != 0
        or (cb110_auth.get("codex") or {}).get("target_adapter_state")
        != "activation_pending"
        or (cb110_auth.get("wechat") or {}).get("target_adapter_state")
        != "activation_pending"
        or cb110_security.get("p0_findings") != 0
        or cb110_security.get("p1_findings") != 0
        or cb110_security.get("result") != "passed"
    ):
        errors.append("history_cb110")

    cb120_install = evidence_json("CB-120", "install-acceptance.redacted.json")
    cb120_identity = evidence_json("CB-120", "identity-negative.redacted.json")
    cb120_pressure = evidence_json("CB-120", "resource-pressure.redacted.json")
    cb120_security = evidence_json("CB-120", "security-report.json")
    if (
        cb120_install.get("candidate_test_count") != 166
        or cb120_install.get("workspace_filter") != "blob:none"
        or cb120_install.get("workspace_clean") is not True
        or cb120_install.get("private_database_cloned") is not False
        or cb120_identity.get("data_identity_plan_only_passed") is not True
        or cb120_identity.get("private_database_clone_present") is not False
        or cb120_pressure.get("oom_events") != 0
        or cb120_pressure.get("fixed_sleep_seconds") != 0
        or cb120_pressure.get("result") != "pass"
        or cb120_security.get("strict_compliance_expression") != STRICT_LICENSE
        or cb120_security.get("upstream_clarification_received") is not False
        or cb120_security.get("result") != "passed"
    ):
        errors.append("history_cb120")

    cb130 = evidence_json("CB-130", "cloud-process-acceptance.redacted.json")
    cb130_security = evidence_json("CB-130", "security-report.json")
    if (
        set((cb130.get("acceptance") or {}).values()) != {"passed"}
        or (cb130.get("network") or {}).get("public_listeners") != 0
        or (cb130.get("process_family") or {}).get("one_systemd_cgroup") is not True
        or (cb130.get("singleton") or {}).get("concurrent_start_passes") != 100
        or (cb130.get("restart") or {}).get("kill_restart_passes") != 100
        or (cb130.get("fault_matrix") or {}).get("false_green_observed") is not False
        or (cb130.get("adapters") or {}).get("real_codex") != "activation_pending"
        or (cb130.get("adapters") or {}).get("real_wechat") != "activation_pending"
        or (cb130.get("final") or {}).get("processes") != 0
        or (cb130.get("final") or {}).get("listeners_8765_8780_19080") != 0
        or cb130_security.get("license_expression") != STRICT_LICENSE
        or cb130_security.get("upstream_clarification_received") is not False
    ):
        errors.append("history_cb130")

    cb140 = evidence_json("CB-140", "walking-skeleton.redacted.json")
    cb140_mac = evidence_json("CB-140", "mac-offline.redacted.json")
    cb140_network = evidence_json("CB-140", "network-scan.redacted.json")
    cb140_security = evidence_json("CB-140", "security-report.json")
    if (
        (cb140.get("simulator_e2e") or {}).get("successful_traces") != 10
        or (cb140.get("simulator_e2e") or {}).get("expected_traces") != 10
        or (cb140.get("simulator_e2e") or {}).get("complete_stage_chain") is not True
        or (cb140.get("inbound_policy") or {}).get(
            "allowlist_unauthorized_runtime_calls"
        )
        != 0
        or (cb140.get("inbound_policy") or {}).get("boundary_32768_runtime_calls")
        != 1
        or (cb140.get("inbound_policy") or {}).get("boundary_32769_runtime_calls")
        != 0
        or (cb140.get("latency") or {}).get("sample_count") != 20
        or (cb140.get("correlation") or {}).get("raw_message_content_persisted")
        is not False
        or (cb140.get("correlation") or {}).get("raw_result_content_persisted")
        is not False
        or (cb140.get("correlation") or {}).get("raw_identity_persisted") is not False
        or (cb140.get("real_adapters") or {}).get("wechat") != "activation_pending"
        or (cb140.get("real_adapters") or {}).get("codex") != "activation_pending"
        or cb140.get("pg_1_executed") is not False
        or cb140.get("stage_2_spool_claimed") is not False
        or cb140_mac.get("mac_runtime_source_config_hits") != 0
        or cb140_mac.get("mac_process_argument_hits") != 0
        or cb140_mac.get("mac_connector_hits") != 0
        or cb140_mac.get("non_loopback_runtime_connections") != 0
        or cb140_network.get("non_loopback_listener_count") != 0
        or cb140_network.get("operator_external_scan") != "passed"
        or cb140_security.get("license_expression") != STRICT_LICENSE
        or cb140_security.get("upstream_clarification_received") is not False
    ):
        errors.append("history_cb140")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row["id"]: row["status"] for row in state["tasks"]}
    expected_passed = {
        "CB-000",
        "CB-010",
        "CB-020",
        "CB-030",
        "CB-040",
        *STAGE1_TASKS,
    }
    for task_id, status in statuses.items():
        expected = "passed" if task_id in expected_passed else "not_started"
        if status != expected:
            errors.append(f"task_state:{task_id}:{status}:{expected}")
    gates = state.get("pass_gates") or {}
    if gates.get("PG-0") != "passed":
        errors.append("gate_pg0")
    if final:
        if gates.get("PG-1") != "passed":
            errors.append("gate_pg1")
        expected_current = {
            "run_id": "PG-1",
            "gate_id": "PG-1",
            "task_id": None,
            "scope": "stage_1_exit_gate",
            "status": "passed",
        }
    else:
        if gates.get("PG-1") != "not_started":
            errors.append("prepare_gate_pg1")
        expected_current = {
            "run_id": "P1.5",
            "gate_id": None,
            "task_id": "CB-140",
            "scope": "all_cloud_walking_skeleton",
            "status": "passed",
        }
    if state.get("current_run") != expected_current:
        errors.append("current_run")
    for gate in ("PG-2", "PG-3", "PG-4", "PG-5"):
        if gates.get(gate) != "not_started":
            errors.append(f"later_gate:{gate}")


def validate_final_evidence(
    matrix_result: dict[str, Any], errors: list[str]
) -> None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_directory")
        return
    actual = {
        candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()
    }
    if actual != FINAL_EVIDENCE:
        errors.append("evidence_inventory")
        return

    matrix = load_json(EVIDENCE / "gate-matrix.json")
    if (
        matrix.get("gate_id") != "PG-1"
        or matrix.get("base_commit") != BASE_COMMIT
        or matrix.get("gate_definition") != PG1_DEFINITION
        or matrix.get("decision") != "PASS"
        or {row.get("id") for row in matrix.get("criteria", [])}
        != {f"PG1-{index:02d}" for index in range(1, 10)}
        or not all(row.get("result") == "pass" for row in matrix.get("criteria", []))
        or matrix.get("strict_compliance_expression") != STRICT_LICENSE
        or matrix.get("upstream_clarification_received") is not False
        or matrix.get("real_adapters") != {
            "codex": "activation_pending",
            "wechat": "activation_pending",
        }
        or matrix.get("stage_2_spool_claimed") is not False
        or matrix.get("next_boundary") != "P2.1 / CB-200"
        or matrix.get("p2_1_started") is not False
        or matrix.get("external_mutations") != 0
        or matrix.get("publication") != "none"
    ):
        errors.append("evidence_gate_matrix")

    index = load_json(EVIDENCE / "stage1-evidence-index.json")
    indexed = {row.get("task_id"): row for row in index.get("tasks", [])}
    if (
        index.get("gate_id") != "PG-1"
        or index.get("base_commit") != BASE_COMMIT
        or index.get("result") != "passed"
        or set(indexed) != set(STAGE1_TASKS)
    ):
        errors.append("evidence_index_header")
    else:
        for task_id, expected in EXPECTED_HISTORY.items():
            row = indexed[task_id]
            if (
                row.get("phase") != expected["phase"]
                or row.get("status") != "passed"
                or row.get("implementation_commit") != expected["implementation"]
                or row.get("closure_commit") != expected["closure"]
                or row.get("evidence_tree") != expected["tree"]
                or row.get("acceptance_criteria") != EXPECTED_ACCEPTANCE[task_id]
                or row.get("evidence_immutable") is not True
            ):
                errors.append(f"evidence_index:{task_id}")

    probe = load_json(EVIDENCE / "credential-free-probe.json")
    fresh_commands = {row["name"] for row in matrix_result["commands"]}
    if (
        probe.get("gate_id") != "PG-1"
        or probe.get("result") != "pass"
        or probe.get("isolated_home") is not True
        or probe.get("empty_codex_home") is not True
        or probe.get("empty_wechat_state") is not True
        or set(probe.get("commands", [])) != fresh_commands
        or (probe.get("auth") or {}).get("codex") != "activation_pending"
        or (probe.get("auth") or {}).get("wechat") != "activation_pending"
        or (probe.get("auth") or {}).get("external_mutation_performed") is not False
        or (probe.get("secret_scan") or {}).get("result") != "passed"
        or probe.get("external_writes") != 0
        or probe.get("requires_real_credential") is not False
    ):
        errors.append("evidence_credential_probe")

    target = load_json(EVIDENCE / "target-readonly.redacted.json")
    final = target.get("final_probe") or {}
    if (
        target.get("gate_id") != "PG-1"
        or target.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or target.get("target_address_persisted") is not False
        or target.get("credential_content_reads") != 0
        or target.get("target_mutations") != 0
        or (target.get("preserved_attempts") or [{}])[0].get("counted_as_pass")
        is not False
        or final.get("service_active") is not False
        or final.get("service_enabled") is not False
        or final.get("current_release") != EXPECTED_CURRENT
        or final.get("workspace_head") != EXPECTED_WORKSPACE
        or final.get("workspace_dirty_count") != 0
        or final.get("candidate_release") != EXPECTED_CANDIDATE
        or final.get("candidate_present") is not True
        or final.get("cyberboss_process_count") != 0
        or final.get("walking_listener_count") != 0
        or final.get("incoming_entry_count") != 0
        or final.get("staging_state_present") is not False
        or final.get("staging_env_present") is not False
        or final.get("runtime_token_present") is not False
        or target.get("result") != "passed"
    ):
        errors.append("evidence_target")

    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("repository") != "LinzeColin/MetaDatabase"
        or publication.get("branch") != EXPECTED_BRANCH
        or publication.get("remote_branch_count") != 0
        or publication.get("pull_request_count") != 0
        or publication.get("tag_count") != 0
        or publication.get("release_count") != 0
        or publication.get("external_object_mutations") != 0
        or publication.get("push_performed") is not False
        or publication.get("result") != "passed"
    ):
        errors.append("evidence_publication")

    output = (EVIDENCE / "gate-validation.txt").read_text(encoding="utf-8")
    for marker in (
        "PG1_VALIDATION=PASS mode=prepare",
        "stage1_tasks=5",
        "credential_free_commands=15",
        "app_tests=175",
        "real_adapters=activation_pending",
        "external_mutations=0",
    ):
        if marker not in output:
            errors.append(f"evidence_output:{marker}")
    report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    for marker in (
        "PG-1 Validation Report",
        "Gate state: `passed`",
        "P2.1 / CB-200: `not_started`",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
        "activation_pending",
        "Stage 2 SQLite WAL spool",
    ):
        if marker not in report:
            errors.append(f"evidence_report:{marker}")

    for candidate in EVIDENCE.iterdir():
        if not candidate.is_file():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            errors.append(f"evidence_secret:{candidate.name}")
        ipv4_values = re.findall(
            r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])",
            text,
        )
        if any(value != "127.0.0.1" for value in ipv4_values):
            errors.append(f"evidence_ipv4:{candidate.name}")


def validate(final: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []

    if git("branch", "--show-current")[1] != EXPECTED_BRANCH:
        errors.append("git_branch")
    if git("remote")[1].splitlines() != ["origin"]:
        errors.append("git_remote_set")
    if git("remote", "get-url", "origin")[1] != EXPECTED_ORIGIN:
        errors.append("git_origin")
    if git("cat-file", "-t", BASE_COMMIT, check=False)[1] != "commit":
        errors.append("base_commit")
    if git(
        "merge-base", "--is-ancestor", BASE_COMMIT, "HEAD", check=False
    )[0] != 0:
        errors.append("base_not_ancestor")
    remote_code, remote = git(
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        f"refs/heads/{EXPECTED_BRANCH}",
        check=False,
    )
    if remote_code != 2 or remote:
        errors.append("remote_branch_published")

    for path in sorted(changed_paths()):
        if not path_allowed(path):
            errors.append(f"scope_violation:{path}")
    if list(PROJECT.rglob(".git")):
        errors.append("nested_git_repository")
    for row in git("ls-files", "-s", "CyberBoss")[1].splitlines():
        if row.startswith("160000 "):
            errors.append(f"gitlink:{row}")

    contract = (
        PROJECT / "docs/governance/RUN_CONTRACT_PG_1.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "PG-1 Stage 1 Exit Gate",
        BASE_COMMIT,
        "不得顺带开始 `P2.1 / CB-200`",
        "scrubbed credential environment",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
        "activation_pending",
        "SQLite WAL durable",
        "不创建新 repo",
        "不 push",
    ):
        if marker not in contract:
            errors.append(f"run_contract:{marker}")

    dag = yaml.safe_load(
        (PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
    )
    if dag["pass_gates"].get("PG-1") != PG1_DEFINITION:
        errors.append("pg1_definition")
    stage1 = next((row for row in dag["stage_plan"] if row["id"] == "S1"), {})
    if stage1.get("tasks") != STAGE1_TASKS or stage1.get("exit_gate") != "PG-1":
        errors.append("stage1_definition")
    task_rows = {row["id"]: row for row in dag["tasks"]}
    for task_id in STAGE1_TASKS:
        if (
            task_rows[task_id].get("acceptance_criteria")
            != EXPECTED_ACCEPTANCE[task_id]
            or task_rows[task_id].get("pass_gate") != "PG-1"
        ):
            errors.append(f"acceptance_map:{task_id}")
    if dag["canonical_facts"].get("mac_dependency") is not False:
        errors.append("dag_mac_dependency")
    if dag["canonical_facts"].get("runtime_transport") != "ws://127.0.0.1:8765 only":
        errors.append("dag_transport")
    if dag["canonical_facts"].get("max_phases_per_run") != 1:
        errors.append("dag_phase_limit")
    if dag["canonical_facts"].get("intermediate_push_allowed") is not False:
        errors.append("dag_publication")

    source = load_json(PROJECT / "machine/source-lock.json")
    conflict = source["whereabouts_license_conflict"]
    obligations = {
        item.strip() for item in conflict["compliance_expression"].split("AND")
    }
    if obligations != {"AGPL-3.0-only", "GPL-3.0-only"}:
        errors.append("license_obligations")
    if conflict.get("preserve_original_license_and_source") is not True:
        errors.append("license_preservation")
    if conflict.get("upstream_clarification_received") is not False:
        errors.append("license_clarification")
    if any(source["upstream_relationship"].values()):
        errors.append("upstream_relationship")

    validate_state(final, errors)
    validate_historical_evidence(errors)
    matrix_result = run_credential_free_matrix(errors)
    command_names = [row["name"] for row in matrix_result["commands"]]
    if len(command_names) != 15 or len(set(command_names)) != 15:
        errors.append(f"credential_command_count:{len(command_names)}")
    if not all(row.get("exit_code") == 0 for row in matrix_result["commands"]):
        errors.append("credential_command_failure")
    if matrix_result["auth"] != {
        "codex": "activation_pending",
        "wechat": "activation_pending",
        "external_mutation_performed": False,
        "credential_values_emitted": False,
    }:
        errors.append("credential_auth_result")
    if matrix_result["secret_scan"].get("result") != "passed":
        errors.append("credential_secret_result")

    if final:
        validate_final_evidence(matrix_result, errors)
        if git("rev-parse", "HEAD^")[1] != BASE_COMMIT:
            errors.append("closure_parent")
        if git("status", "--porcelain=v1", "--untracked-files=all")[1]:
            errors.append("worktree_dirty")

    return errors, matrix_result


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--final", action="store_true")
    args = parser.parse_args()
    try:
        errors, matrix = validate(final=args.final)
    except Exception as error:  # fail closed at the outermost boundary
        print(f"PG1_VALIDATION=FAIL exception={type(error).__name__}:{error}")
        return 2
    if errors:
        print("PG1_VALIDATION=FAIL")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    mode_name = "final" if args.final else "prepare"
    print(
        f"PG1_VALIDATION=PASS mode={mode_name} stage1_tasks=5 "
        "credential_free_commands=15 simulator_contract_tests=5 "
        "walking_static_tests=4 walking_live_tests=1 app_tests=175 "
        "real_adapters=activation_pending external_mutations=0"
    )
    print(
        "CREDENTIAL_FREE=PASS "
        f"removed_environment_keys={matrix['removed_environment_key_count']} "
        f"secret_scan_files={matrix['secret_scan']['scanned_files']} "
        f"secret_scan_bytes={matrix['secret_scan']['scanned_bytes']} "
        "codex=activation_pending wechat=activation_pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
