#!/usr/bin/env python3
"""Fail-closed Stage 0 exit-gate validator for CyberBoss PG-0.

The validator executes repository-preparation checks in an isolated,
credential-scrubbed environment. It never performs a provider write, deploy,
push, PR, tag or Runtime activation.
"""

from __future__ import annotations

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
EVIDENCE = PROJECT / "docs/evidence/PG-0"
BASE_COMMIT = "7356393cf7fe8281b602c10352a827c15b48b748"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
PG0_DEFINITION = (
    "Pinned sources, current architecture, simulators, live-measurement script, "
    "activation sheet and no-wait policy validate; no credential is required "
    "to pass repository preparation."
)
STAGE0_TASKS = ["CB-000", "CB-010", "CB-020", "CB-030", "CB-040"]
EXPECTED_SOURCE_COMMITS = {
    "cyberboss": "373ab17d283f1e3b304a6a36e17e9e8d44f1acfc",
    "timeline-for-agent": "62e1fa8db26f7a9147ad96579fc4077a39b94c8b",
    "whereabouts-mcp": "e36cb307f082f747327fd3a5d406fd9718a1428d",
}
EXPECTED_FLAGS = {
    "CB_DURABLE_INBOX": "true",
    "CB_DURABLE_OUTBOX": "true",
    "CB_PRIVATE_DB_CANONICAL_SYNC": "true",
    "CB_TIMELINE_WEB": "true",
    "CB_STATUS_EXPORTER": "true",
    "CB_R2_SNAPSHOT": "true",
    "CB_OCI_BACKUP": "false",
    "CB_CLAUDE_RUNTIME": "false",
    "CB_FILE_ATTACHMENTS": "false",
    "CB_STORE_FULL_CONTENT": "false",
    "CB_AUTONOMOUS_MUTATION": "false",
}

ALLOWED_EXACT = {
    "CyberBoss/docs/governance/RUN_CONTRACT_PG_0.md",
    "CyberBoss/scripts/validate_pg0.py",
    "CyberBoss/scripts/validate_prestage0.py",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/README.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/CHANGELOG.md",
}

FINAL_EVIDENCE = {
    "gate-matrix.json",
    "credential-free-probe.json",
    "publication-check.json",
    "gate-validation.txt",
    "VALIDATION_REPORT.md",
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
            f"{result.stderr.strip()}"
        )
    return result.returncode, result.stdout.rstrip()


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def changed_paths() -> set[str]:
    _code, committed_text = git("diff", "--name-only", BASE_COMMIT, "HEAD")
    paths = set(filter(None, committed_text.splitlines()))
    _code, status_text = git("status", "--porcelain=v1", "--untracked-files=all")
    for raw in status_text.splitlines():
        if not raw:
            continue
        value = raw[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.add(value)
    return paths


def path_allowed(path: str) -> bool:
    return path in ALLOWED_EXACT or path.startswith("CyberBoss/docs/evidence/PG-0/")


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
    for path in (home, codex_home, wechat_state, tmp, npm_cache):
        path.mkdir(parents=True, exist_ok=True)

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
        for line in output.splitlines()[-20:]:
            errors.append(f"command_tail:{name}:{line}")
    for marker in required:
        if marker not in output:
            errors.append(f"command_marker:{name}:{marker}")
    return {
        "name": name,
        "exit_code": result.returncode,
        "required_markers": list(required),
    }


def run_credential_free_matrix(errors: list[str]) -> dict[str, Any]:
    command_results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cyberboss-pg0-") as raw_root:
        fixture_root = Path(raw_root)
        environment, removed_count = credential_free_environment(fixture_root)
        python = sys.executable

        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            (
                "cb000",
                [python, str(PROJECT / "scripts/validate_cb000.py")],
                REPO,
                ("CB000_VALIDATION=PASS",),
                300,
            ),
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
                (
                    "TRACEABILITY_VALIDATION=PASS requirements=53 "
                    "oracles=53 mapped_oracles=53 tasks=30",
                ),
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
                (
                    "TASKPACK_VALIDATION=PASS files=81 required_items=16 "
                    "seven_is_minimum_not_limit=true",
                ),
                120,
            ),
            (
                "config",
                [
                    "node",
                    str(KIT / "tests/validate_config.js"),
                    str(KIT / "config/cyberboss.env.example"),
                    str(KIT / "config/workspaces.json.example"),
                ],
                REPO,
                ("CONFIG_VALIDATION=PASS workspaces=1",),
                120,
            ),
            (
                "scope_policy",
                [python, str(KIT / "scripts/scope_policy.py"), "validate"],
                REPO,
                ("SCOPE_POLICY=PASS command=validate",),
                120,
            ),
            (
                "identity_scope",
                [python, str(KIT / "tests/test_identity_scope.py")],
                REPO,
                ("Ran 8 tests", "OK"),
                180,
            ),
            (
                "external_adapters",
                [python, str(KIT / "tests/test_external_adapters.py")],
                REPO,
                ("Ran 6 tests", "OK"),
                180,
            ),
            (
                "access_policy",
                ["node", "--test", str(KIT / "tests/access-policy-contract.test.js")],
                REPO,
                ("ℹ tests 8", "ℹ pass 8", "ℹ fail 0"),
                120,
            ),
            (
                "simulator_contract",
                ["node", "--test", str(KIT / "tests/simulator-contract.test.mjs")],
                REPO,
                ("ℹ tests 4", "ℹ pass 4", "ℹ fail 0"),
                180,
            ),
            (
                "status_contract",
                ["node", "--test", str(KIT / "tests/status-adapter-contract.test.js")],
                REPO,
                ("ℹ tests 7", "ℹ pass 7", "ℹ fail 0"),
                120,
            ),
            (
                "preflight_check",
                ["bash", str(KIT / "scripts/preflight.sh"), "--check"],
                REPO,
                (
                    "PREFLIGHT_CHECK=PASS live_commands=false "
                    "persistent_writes=false",
                ),
                120,
            ),
            (
                "resource_profile",
                [python, str(KIT / "tests/test_resource_profile.py")],
                REPO,
                ("Ran 7 tests", "OK"),
                180,
            ),
            (
                "resource_pressure",
                [python, str(KIT / "scripts/resource-pressure-fixture.py")],
                REPO,
                ("RESOURCE_PRESSURE=PASS", "no_sleep=true"),
                180,
            ),
            (
                "npm_clean_install_dry_run",
                ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--dry-run"],
                PROJECT / "app",
                (),
                300,
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
                ("ℹ tests 155", "ℹ pass 155", "ℹ fail 0"),
                300,
            ),
        ]

        for name, command, cwd, required, timeout in specs:
            command_results.append(
                run_command(
                    name,
                    command,
                    cwd,
                    environment,
                    errors,
                    required=required,
                    timeout=timeout,
                )
            )

        shell_files = sorted((KIT / "scripts").glob("*.sh")) + sorted(
            (KIT / "simulators").glob("*.sh")
        )
        shell_failures = 0
        for path in shell_files:
            result = subprocess.run(
                ["bash", "-n", str(path)],
                cwd=REPO,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                shell_failures += 1
                errors.append(f"shell_syntax:{path.relative_to(REPO)}")
        command_results.append(
            {
                "name": "shell_syntax",
                "exit_code": 0 if shell_failures == 0 else 1,
                "files_checked": len(shell_files),
            }
        )

        auth_output = fixture_root / "auth-probe.json"
        command_results.append(
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
                required=(
                    "AUTH_ACTIVATION_CHECK=PASS",
                    "external_mutation=0",
                    "credential_values_emitted=0",
                ),
                timeout=120,
            )
        )
        auth = load_json(auth_output) if auth_output.is_file() else {}
        if auth.get("probe_scope") != "authorized_ovh_staging":
            errors.append("auth_fixture_scope")
        if auth.get("external_mutation_performed") is not False:
            errors.append("auth_fixture_mutation")
        if auth.get("credential_content_read") is not False:
            errors.append("auth_fixture_content_read")
        if auth.get("credential_values_emitted") is not False:
            errors.append("auth_fixture_value_emit")
        if (auth.get("codex") or {}).get("target_adapter_state") != "activation_pending":
            errors.append("auth_fixture_codex_state")
        if (auth.get("wechat") or {}).get("target_adapter_state") != "activation_pending":
            errors.append("auth_fixture_wechat_state")
        if (auth.get("codex") or {}).get("auth_file", {}).get("present") is not False:
            errors.append("auth_fixture_codex_file")
        if (auth.get("wechat") or {}).get("account_state_file_count") != 0:
            errors.append("auth_fixture_wechat_files")

        secret_output = fixture_root / "secret-scan.json"
        command_results.append(
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
                timeout=180,
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
            "commands": command_results,
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

    # Current branch and a hard scope boundary preserve all completed Stage 0 inputs.
    expect(git("branch", "--show-current")[1] == EXPECTED_BRANCH, "git_branch")
    expect(git("remote", "get-url", "origin")[1] == EXPECTED_ORIGIN, "git_origin")
    expect(git("remote")[1].splitlines() == ["origin"], "git_remote_set")
    expect(git("cat-file", "-t", BASE_COMMIT, check=False)[1] == "commit", "base_commit")
    expect(
        git("merge-base", "--is-ancestor", BASE_COMMIT, "HEAD", check=False)[0] == 0,
        "base_not_ancestor",
    )
    for path in sorted(changed_paths()):
        expect(path_allowed(path), f"scope_violation:{path}")
        expect(not path.startswith("CyberBoss/app/"), f"app_changed:{path}")
        expect(not path.startswith("CyberBoss/vendor/"), f"vendor_changed:{path}")
        expect(
            not path.startswith("CyberBoss/docs/product_design/"),
            f"taskpack_changed:{path}",
        )
        expect(
            not re.match(r"CyberBoss/docs/evidence/CB-\d{3}/", path),
            f"stage0_evidence_changed:{path}",
        )
    expect(not list(PROJECT.rglob(".git")), "nested_git_repository")
    for row in git("ls-files", "-s", "CyberBoss")[1].splitlines():
        expect(not row.startswith("160000 "), f"gitlink:{row}")

    contract = PROJECT / "docs/governance/RUN_CONTRACT_PG_0.md"
    contract_text = contract.read_text(encoding="utf-8")
    for required in [
        "PG-0 Stage 0 Exit Gate",
        BASE_COMMIT,
        "不得顺带开始 `P1.1 / CB-100`",
        "scrubbed credential environment",
        "不 push",
    ]:
        expect(required in contract_text, f"run_contract:{required}")

    dag = yaml.safe_load((PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8"))
    expect(dag["pass_gates"]["PG-0"] == PG0_DEFINITION, "pg0_definition")
    stage0 = next((row for row in dag["stage_plan"] if row["id"] == "S0"), {})
    expect(stage0.get("tasks") == STAGE0_TASKS, "stage0_task_set")
    expect(stage0.get("exit_gate") == "PG-0", "stage0_exit_gate")
    canonical = dag["canonical_facts"]
    expect(canonical["code_repository"] == "LinzeColin/MetaDatabase", "dag_repo")
    expect(canonical["project_subpath"] == "CyberBoss/", "dag_subpath")
    expect(canonical["mac_dependency"] is False, "dag_mac_dependency")
    expect(canonical["runtime_transport"] == "ws://127.0.0.1:8765 only", "dag_transport")
    expect(canonical["real_time_soak_gate"] is False, "dag_wait")
    expect(canonical["credential_wait_blocks_development"] is False, "dag_credential_wait")
    expect(canonical["max_phases_per_run"] == 1, "dag_phase_limit")
    expect(canonical["intermediate_push_allowed"] is False, "dag_push")

    state = load_json(PROJECT / "machine/facts/task_state.json")
    task_status = {row["id"]: row["status"] for row in state["tasks"]}
    expect(all(task_status.get(task) == "passed" for task in STAGE0_TASKS), "stage0_status")
    expect(
        all(status == "not_started" for task, status in task_status.items() if task not in STAGE0_TASKS),
        "future_task_started",
    )
    if prepare_mode:
        expect(state["current_run"]["run_id"] == "P0.5", "prepare_current_run")
        expect(state["current_run"]["task_id"] == "CB-040", "prepare_current_task")
        expect(set(state["pass_gates"].values()) == {"not_started"}, "prepare_gate_state")
    else:
        expect(state["current_run"]["run_id"] == "PG-0", "final_current_run")
        expect(state["current_run"]["gate_id"] == "PG-0", "final_gate_id")
        expect(state["current_run"].get("task_id") is None, "final_gate_task_claim")
        expect(state["current_run"]["scope"] == "stage_0_exit_gate", "final_gate_scope")
        expect(state["current_run"]["status"] == "passed", "final_gate_status")
        expect(state["pass_gates"]["PG-0"] == "passed", "pg0_state")
        expect(
            all(state["pass_gates"][f"PG-{index}"] == "not_started" for index in range(1, 6)),
            "later_gate_started",
        )

    owner = load_json(PROJECT / "machine/facts/owner_decisions.json")
    source = load_json(PROJECT / "machine/source-lock.json")
    expect(owner["project"] == {
        "repository": "LinzeColin/MetaDatabase",
        "subpath": "CyberBoss/",
        "independent_repository_allowed": False,
    }, "owner_project")
    expect(owner["execution"]["max_phases_per_run"] == 1, "owner_phase_limit")
    expect(owner["execution"]["intermediate_push_allowed"] is False, "owner_push")
    expect(owner["execution"]["intermediate_pull_request_allowed"] is False, "owner_pr")
    expect(not any(source["upstream_relationship"].values()), "source_upstream_relationship")
    source_commits = {row["id"]: row["commit"] for row in source["sources"]}
    expect(source_commits == EXPECTED_SOURCE_COMMITS, "source_commit_set")
    conflict = source["whereabouts_license_conflict"]
    expect(
        conflict["compliance_expression"] == "GPL-3.0-only AND AGPL-3.0-only",
        "license_expression",
    )
    expect(conflict["preserve_original_license_and_source"] is True, "license_preserve")
    expect(conflict["upstream_clarification_received"] is False, "license_clarification")
    expect(conflict["must_not_claim_upstream_clarification"] is True, "license_claim_rule")

    inventory = load_json(PROJECT / "docs/evidence/CB-000/dependency-license-inventory.json")
    expect(inventory["package_count_including_root"] == 129, "dependency_count")
    expect(len(inventory["packages"]) == 129, "dependency_actual_count")
    expect(inventory["unresolved_licenses"] == [], "unresolved_dependency_license")
    expect(
        inventory["whereabouts_compliance_policy"]["upstream_clarification_received"] is False,
        "inventory_clarification",
    )
    expect(
        (PROJECT / "docs/evidence/CB-000/REUSE_CHANGE_MAP.md").is_file(),
        "module_map_missing",
    )

    architecture = load_json(PROJECT / "docs/evidence/CB-040/canonical-conflict-scan.json")
    expect(architecture["result"] == "pass", "architecture_result")
    expect(architecture["unresolved_conflicts"] == [], "architecture_conflicts")
    expect(
        architecture["stale_active_feature_flag_alias_hits"] == 0,
        "architecture_stale_flags",
    )
    substitutions = load_json(PROJECT / "docs/evidence/CB-040/environment-substitutions.json")
    expect(substitutions["code_identity"]["repository"] == "LinzeColin/MetaDatabase", "sub_repo")
    expect(substitutions["canonical_data"]["access_mode"] == "no_clone_client", "sub_data_mode")
    expect(substitutions["cloudflare"]["hostname"] == "cyberboss.linzezhang.com", "sub_domain")
    expect(substitutions["services_and_ports"]["http_bind"] == "127.0.0.1", "sub_bind")
    expect(substitutions["services_and_ports"]["http_port"] == 8780, "sub_port")
    expect(substitutions["activation_states"]["global_wait_nodes"] == 0, "sub_wait")
    expect(
        {row["name"]: str(row["value"]).lower() for row in substitutions["feature_flags"]}
        == EXPECTED_FLAGS,
        "sub_feature_flags",
    )
    env = parse_env(KIT / "config/cyberboss.env.example")
    expect({key: env.get(key) for key in EXPECTED_FLAGS} == EXPECTED_FLAGS, "env_flags")

    live = load_json(PROJECT / "docs/evidence/CB-010/live-host-pressure.redacted.json")
    expect(live["target"]["asset_class"] == "authorized_ovh_primary_host", "live_target")
    expect(live["target"]["address_persisted"] is False, "live_address")
    expect(live["safety_gate"]["result"] == "pass", "live_safety")
    expect(live["fixture"]["result"] == "pass", "live_fixture")
    expect(live["fixture"]["no_sleep"] is True, "live_fixture_wait")
    expect(live["evidence_boundaries"]["proves_runtime_deployment"] is False, "live_claim")

    auth_local = load_json(PROJECT / "docs/evidence/CB-030/auth-probe.local.redacted.json")
    auth_ovh = load_json(PROJECT / "docs/evidence/CB-030/auth-probe.ovh.redacted.json")
    expect(auth_local["external_mutation_performed"] is False, "auth_local_mutation")
    expect(auth_local["credential_values_emitted"] is False, "auth_local_value")
    expect(auth_ovh["external_mutation_performed"] is False, "auth_ovh_mutation")
    expect(auth_ovh["credential_values_emitted"] is False, "auth_ovh_value")
    expect(auth_ovh["codex"]["target_adapter_state"] == "activation_pending", "auth_ovh_codex")
    expect(auth_ovh["wechat"]["target_adapter_state"] == "activation_pending", "auth_ovh_wechat")
    auth_sheet = (PROJECT / "docs/evidence/CB-030/auth-gates.md").read_text(encoding="utf-8")
    for required in ["codex login --device-auth", "npm run login", "activation_pending"]:
        expect(required in auth_sheet, f"activation_sheet:{required}")

    cb040_report = (PROJECT / "docs/evidence/CB-040/VALIDATION_REPORT.md").read_text(
        encoding="utf-8"
    )
    expect("decision=GO_TO_PG-0" in cb040_report, "cb040_decision")
    expect("PG-0=not_started" in cb040_report, "cb040_gate_boundary")
    expect("155/155 passed" in cb040_report, "cb040_app_regression")

    matrix_result = run_credential_free_matrix(errors)
    command_names = [row["name"] for row in matrix_result["commands"]]
    expect(len(command_names) == len(set(command_names)), "duplicate_command_name")
    expect(len(command_names) == 22, f"command_count:{len(command_names)}")
    expect(
        all(row.get("exit_code") == 0 for row in matrix_result["commands"]),
        "credential_free_command_failure",
    )
    expect(matrix_result["auth"]["codex"] == "activation_pending", "fresh_auth_codex")
    expect(matrix_result["auth"]["wechat"] == "activation_pending", "fresh_auth_wechat")
    expect(matrix_result["auth"]["external_mutation_performed"] is False, "fresh_auth_mutation")
    expect(matrix_result["auth"]["credential_values_emitted"] is False, "fresh_auth_values")
    expect(matrix_result["secret_scan"]["result"] == "passed", "fresh_secret_scan")

    if not prepare_mode:
        for name in sorted(FINAL_EVIDENCE):
            expect((EVIDENCE / name).is_file(), f"final_evidence:{name}")
        if all((EVIDENCE / name).is_file() for name in FINAL_EVIDENCE):
            matrix = load_json(EVIDENCE / "gate-matrix.json")
            expect(matrix["gate_id"] == "PG-0", "matrix_gate")
            expect(matrix["base_commit"] == BASE_COMMIT, "matrix_base")
            expect(matrix["gate_definition"] == PG0_DEFINITION, "matrix_definition")
            expect(matrix["decision"] == "PASS", "matrix_decision")
            expect(
                {row["id"] for row in matrix["criteria"]}
                == {f"PG0-{index:02d}" for index in range(1, 9)},
                "matrix_criteria_set",
            )
            expect(
                all(row["result"] == "pass" for row in matrix["criteria"]),
                "matrix_criteria_result",
            )
            expect(matrix["next_boundary"] == "P1.1 / CB-100", "matrix_next")
            expect(matrix["p1_1_started"] is False, "matrix_p1_claim")

            recorded_probe = load_json(EVIDENCE / "credential-free-probe.json")
            expect(recorded_probe["gate_id"] == "PG-0", "probe_gate")
            expect(recorded_probe["result"] == "pass", "probe_result")
            expect(recorded_probe["isolated_home"] is True, "probe_home")
            expect(recorded_probe["empty_codex_home"] is True, "probe_codex_home")
            expect(recorded_probe["empty_wechat_state"] is True, "probe_wechat_home")
            expect(recorded_probe["auth"]["codex"] == "activation_pending", "probe_codex")
            expect(recorded_probe["auth"]["wechat"] == "activation_pending", "probe_wechat")
            expect(recorded_probe["auth"]["external_mutation_performed"] is False, "probe_mutation")
            expect(recorded_probe["auth"]["credential_values_emitted"] is False, "probe_values")
            expect(recorded_probe["secret_scan"]["result"] == "passed", "probe_secret")
            expect(
                set(recorded_probe["commands"]) == set(command_names),
                "probe_command_set",
            )

            publication = load_json(EVIDENCE / "publication-check.json")
            expect(publication["state"] == "none", "publication_state")
            expect(publication["remote_branch_matches"] == [], "publication_branch")
            expect(publication["open_pull_request_matches"] == [], "publication_pr")
            expect(publication["remote_tag_matches"] == [], "publication_tag")
            expect(publication["required_for_gate_pass"] is False, "publication_gate_dependency")

            output = (EVIDENCE / "gate-validation.txt").read_text(encoding="utf-8")
            for marker in (
                "PG0_VALIDATION=PASS",
                "stage0_tasks=5",
                "credential_free_commands=22",
                "simulator_tests=4",
                "app_tests=155",
                "unresolved_conflicts=0",
                "external_writes=0",
            ):
                expect(marker in output, f"recorded_output:{marker}")
            report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
            for marker in (
                "PG-0 Validation Report",
                "Gate state: `passed`",
                "P1.1 / CB-100: `not_started`",
                "GPL-3.0-only AND AGPL-3.0-only",
                "upstream_clarification_received=false",
            ):
                expect(marker in report, f"validation_report:{marker}")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print("PG0_VALIDATION=FAIL")
        return 1

    mode = "prepare" if prepare_mode else "final"
    print(
        "PG0_VALIDATION=PASS "
        f"mode={mode} stage0_tasks=5 credential_free_commands=22 "
        "simulator_tests=4 app_tests=155 unresolved_conflicts=0 "
        "credential_values=0 external_writes=0"
    )
    print(
        "CREDENTIAL_FREE=PASS "
        f"removed_environment_keys={matrix_result['removed_environment_key_count']} "
        f"secret_scan_files={matrix_result['secret_scan']['scanned_files']} "
        f"secret_scan_bytes={matrix_result['secret_scan']['scanned_bytes']} "
        "codex=activation_pending wechat=activation_pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
