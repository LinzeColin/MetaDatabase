#!/usr/bin/env python3
"""Fail-closed validation for the CyberBoss PS0.1 normalization baseline."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


EXPECTED_VERSION = "v0.0.0.4"
EXPECTED_LICENSE_SHA256 = (
    "526520455b0c01e09c1a23f6322a11d9e867de44dc833de8a94af6766dced64b"
)
TASK_REF = re.compile(r"\bCB-\d{3}\b")
GATE_REF = re.compile(r"\bPG-\d+\b")
ORACLE_ROW = re.compile(r"^\|\s*(AC-\d{3})\s*\|", re.MULTILINE)
REQUIREMENT_ROW = re.compile(
    r"^\|\s*((?:FR|NFR)-\d{3})\s*\|.*?\|\s*(AC-\d{3})\s*\|\s*$",
    re.MULTILINE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}:invalid_env_line")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def verify_manifest(manifest: Path, base: Path, errors: list[str]) -> None:
    entries: dict[str, str] = {}
    pattern = re.compile(r"^([0-9a-f]{64})  \./(.+)$")
    for number, raw in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(), 1
    ):
        match = pattern.fullmatch(raw)
        if not match:
            errors.append(f"manifest_invalid_line:{manifest}:{number}")
            continue
        expected, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"manifest_unsafe_path:{manifest}:{relative}")
            continue
        if relative in entries:
            errors.append(f"manifest_duplicate_path:{manifest}:{relative}")
            continue
        entries[relative] = expected

    actual_files = {
        path.relative_to(base).as_posix()
        for path in base.rglob("*")
        if path.is_file() and path != manifest
    }
    listed_files = set(entries)
    for relative in sorted(actual_files - listed_files):
        errors.append(f"manifest_unlisted_file:{manifest}:{relative}")
    for relative in sorted(listed_files - actual_files):
        errors.append(f"manifest_missing_file:{manifest}:{relative}")
    for relative in sorted(actual_files & listed_files):
        actual = sha256(base / relative)
        if actual != entries[relative]:
            errors.append(f"manifest_hash_mismatch:{manifest}:{relative}")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.rstrip()


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    repo = project.parent
    pack = project / "docs/product_design/v0.0.0.4"
    kit = pack / "implementation-kit"
    errors: list[str] = []

    def expect(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    required = [
        project / "AGENTS.md",
        project / "LICENSE",
        project / "README.md",
        project / "HANDOFF.md",
        project / "THIRD_PARTY_NOTICES.md",
        project / "UPSTREAM_PROVENANCE.md",
        project / "machine/facts/owner_decisions.json",
        project / "machine/facts/task_state.json",
        pack / "00_README_FIRST.md",
        pack / "02_PRD_ACCEPTANCE_CONTRACT.md",
        pack / "04_TASK_DAG_EXECUTION_PACK.yaml",
        pack / "10_TRACEABILITY_RELEASE_CHECKLIST.md",
        pack / "MANIFEST.sha256",
        kit / "MANIFEST.sha256",
    ]
    for path in required:
        expect(path.is_file(), f"required_file_missing:{path.relative_to(repo)}")
    if any(not path.is_file() for path in required):
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print("PRESTAGE0_VALIDATION=FAIL")
        return 1

    empty_files = [
        path.relative_to(repo).as_posix()
        for path in project.rglob("*")
        if path.is_file()
        and not any(
            part in {".git", "node_modules"}
            for part in path.relative_to(project).parts
        )
        and path.stat().st_size == 0
    ]
    for path in empty_files:
        errors.append(f"empty_file:{path}")

    dag = yaml.safe_load(
        (pack / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
    )
    tasks = dag.get("tasks") or []
    stage_plan = dag.get("stage_plan") or []
    gates = dag.get("pass_gates") or {}
    expect(nested(dag, "taskpack", "version") == EXPECTED_VERSION, "dag_version")
    expect(len(tasks) == 30, f"task_count_expected_30_actual_{len(tasks)}")
    expect(len(stage_plan) == 6, f"stage_count_expected_6_actual_{len(stage_plan)}")
    expect(set(gates) == {f"PG-{i}" for i in range(6)}, "pass_gate_set")

    expected_tasks: dict[str, tuple[str, str]] = {}
    expected_stage_tasks: dict[str, list[str]] = {}
    for stage_index in range(6):
        stage = f"S{stage_index}"
        stage_tasks: list[str] = []
        for phase_index in range(5):
            task_id = f"CB-{stage_index}{phase_index}0"
            phase = f"P{stage_index}.{phase_index + 1}"
            expected_tasks[task_id] = (stage, phase)
            stage_tasks.append(task_id)
        expected_stage_tasks[stage] = stage_tasks

    actual_tasks: dict[str, tuple[str, str]] = {}
    for task in tasks:
        task_id = task.get("id")
        if not isinstance(task_id, str):
            errors.append("task_missing_id")
            continue
        if task_id in actual_tasks:
            errors.append(f"duplicate_task_id:{task_id}")
        actual_tasks[task_id] = (task.get("stage"), task.get("phase"))
        for dependency in task.get("dependencies") or []:
            if dependency not in expected_tasks:
                errors.append(f"unknown_dependency:{task_id}:{dependency}")
        if not task.get("acceptance_criteria"):
            errors.append(f"task_without_acceptance:{task_id}")
    expect(actual_tasks == expected_tasks, "task_stage_phase_mapping")

    actual_stage_tasks: dict[str, list[str]] = {}
    for stage in stage_plan:
        stage_id = stage.get("id")
        if isinstance(stage_id, str):
            actual_stage_tasks[stage_id] = stage.get("tasks") or []
            expect(
                stage.get("exit_gate") == f"PG-{stage_id[1:]}",
                f"stage_exit_gate:{stage_id}",
            )
    expect(actual_stage_tasks == expected_stage_tasks, "stage_plan_task_mapping")
    expect(
        nested(dag, "canonical_facts", "max_phases_per_run") == 1,
        "dag_max_phases_per_run",
    )
    expect(
        nested(dag, "canonical_facts", "intermediate_push_allowed") is False,
        "dag_intermediate_push",
    )
    expect(
        nested(dag, "canonical_facts", "intermediate_pull_request_allowed") is False,
        "dag_intermediate_pr",
    )

    prd = (pack / "02_PRD_ACCEPTANCE_CONTRACT.md").read_text(encoding="utf-8")
    oracles = set(ORACLE_ROW.findall(prd))
    requirements = REQUIREMENT_ROW.findall(prd)
    expect(len(oracles) == 53, f"oracle_count_expected_53_actual_{len(oracles)}")
    expect(
        len(requirements) == 53,
        f"requirement_count_expected_53_actual_{len(requirements)}",
    )

    valid_tasks = set(expected_tasks)
    valid_gates = {f"PG-{i}" for i in range(6)}
    control_files = [
        path
        for path in sorted(pack.glob("[0-9][0-9]_*"))
        if path.is_file() and path.suffix in {".md", ".txt", ".yaml", ".yml"}
    ]
    for path in control_files:
        text = path.read_text(encoding="utf-8")
        for task_ref in TASK_REF.findall(text):
            if task_ref not in valid_tasks:
                errors.append(f"unknown_task_reference:{path.name}:{task_ref}")
        for gate_ref in GATE_REF.findall(text):
            if gate_ref not in valid_gates:
                errors.append(f"unknown_gate_reference:{path.name}:{gate_ref}")

    owner = load_json(project / "machine/facts/owner_decisions.json")
    owner_expectations = {
        ("project", "repository"): "LinzeColin/MetaDatabase",
        ("project", "subpath"): "CyberBoss/",
        ("project", "independent_repository_allowed"): False,
        ("license", "decision"): "A1",
        ("license", "subtree_license"): "AGPL-3.0-only",
        ("license", "root_license_overrides_subtree"): False,
        ("upstream_separation", "upstream_remote_allowed"): False,
        ("upstream_separation", "git_submodule_allowed"): False,
        ("upstream_separation", "git_url_runtime_dependency_allowed"): False,
        ("upstream_separation", "automatic_sync_allowed"): False,
        ("upstream_separation", "runtime_source_fetch_allowed"): False,
        ("upstream_separation", "periodic_rebase_allowed"): False,
        ("upstream_separation", "future_update_requires_owner_change_event"): True,
        ("workspace", "decision"): "B1",
        ("workspace", "default_alias"): "cyberboss",
        ("workspace", "repository"): "LinzeColin/MetaDatabase",
        ("data", "repository"): "LinzeColin/Private-Database",
        ("data", "area"): "Private-MetaDatabase",
        ("data", "domain"): "CyberBoss",
        ("data", "clone_allowed"): False,
        ("execution", "taskpack_version"): EXPECTED_VERSION,
        ("execution", "max_phases_per_run"): 1,
        ("execution", "intermediate_push_allowed"): False,
        ("execution", "intermediate_pull_request_allowed"): False,
        ("execution", "final_push_requires_all_pass_gates"): True,
    }
    for keys, expected in owner_expectations.items():
        expect(nested(owner, *keys) == expected, f"owner_fact:{'.'.join(keys)}")
    expect(
        nested(owner, "workspace", "default_write_globs") == ["CyberBoss/**"],
        "owner_workspace_write_scope",
    )

    state = load_json(project / "machine/facts/task_state.json")
    expect(state.get("taskpack_version") == EXPECTED_VERSION, "state_version")
    prestage = state.get("prestage") or []
    expect(
        prestage
        == [{"id": "PS0.1", "status": "passed", "acceptance": "passed"}],
        "state_prestage",
    )
    valid_statuses = {
        "not_started",
        "in_progress",
        "activation_pending",
        "hazard_blocked",
        "failed",
        "passed",
    }
    pass_gates = state.get("pass_gates") or {}
    expect(set(pass_gates) == {f"PG-{i}" for i in range(6)}, "state_pass_gate_set")
    for gate_id, status in pass_gates.items():
        expect(status in valid_statuses, f"state_pass_gate_status:{gate_id}:{status}")

    state_task_items = state.get("tasks") or []
    expect(len(state_task_items) == 30, "state_task_count")
    state_task_ids = [item.get("id") for item in state_task_items]
    expect(len(set(state_task_ids)) == len(state_task_ids), "state_task_duplicate_id")
    state_tasks = {
        item.get("id"): (item.get("stage"), item.get("phase"), item.get("status"))
        for item in state_task_items
    }
    expected_state_tasks = {
        task_id: (stage, phase)
        for task_id, (stage, phase) in expected_tasks.items()
    }
    actual_state_mapping = {
        task_id: (stage, phase)
        for task_id, (stage, phase, _status) in state_tasks.items()
    }
    expect(actual_state_mapping == expected_state_tasks, "state_task_mapping")
    state_statuses = {
        task_id: status
        for task_id, (_stage, _phase, status) in state_tasks.items()
    }
    for task_id, status in state_statuses.items():
        expect(status in valid_statuses, f"state_task_status:{task_id}:{status}")

    task_specs = {task.get("id"): task for task in tasks}
    for task_id, status in state_statuses.items():
        if status == "not_started":
            continue
        for dependency in (task_specs.get(task_id) or {}).get("dependencies") or []:
            expect(
                state_statuses.get(dependency) == "passed",
                f"state_dependency_not_passed:{task_id}:{dependency}",
            )

    for stage_index in range(6):
        gate_id = f"PG-{stage_index}"
        if pass_gates.get(gate_id) != "passed":
            continue
        for task_id in expected_stage_tasks[f"S{stage_index}"]:
            expect(
                state_statuses.get(task_id) == "passed",
                f"state_gate_task_not_passed:{gate_id}:{task_id}",
            )

    current_run = state.get("current_run") or {}
    if current_run.get("run_id") == "PS0.1":
        expect(current_run.get("status") == "passed", "state_current_prestage")
    else:
        current_task_id = current_run.get("task_id")
        current_spec = task_specs.get(current_task_id) or {}
        expect(
            current_run.get("run_id") == current_spec.get("phase"),
            "state_current_run_phase",
        )
        expect(
            current_run.get("status") == state_statuses.get(current_task_id),
            "state_current_run_status",
        )

    env = parse_env(kit / "config/cyberboss.env.example")
    env_expectations = {
        "CB_PRODUCT_VERSION": "0.0.0.4",
        "CB_PRIVATE_DB_CANONICAL_SYNC": "true",
        "CB_DATA_REPO_SLUG": "LinzeColin/Private-Database",
        "CB_DATA_AREA": "Private-MetaDatabase",
        "CB_DATA_DOMAIN": "CyberBoss",
        "CB_PRIVATE_DB_CLIENT": (
            "/opt/cyberboss-cloud/shared/private_db_client.py"
        ),
        "CB_PRIVATE_DB_AUTH_MODE": "gh-login",
        "CB_APP_REPO_SLUG": "LinzeColin/MetaDatabase",
        "CB_APP_SUBPATH": "CyberBoss",
        "CB_INCOMING_ROOT": "/var/lib/cyberboss/incoming",
    }
    for key, expected in env_expectations.items():
        expect(env.get(key) == expected, f"env_identity:{key}")
    for key in (
        "CB_DATA_REPO_PATH",
        "CB_DATA_REPO_URL",
        "CB_DATA_ROOT",
        "CB_APP_REPO_URL",
    ):
        expect(key not in env, f"forbidden_env:{key}")

    workspaces = load_json(kit / "config/workspaces.json.example")
    workspace = nested(workspaces, "workspaces", "cyberboss")
    expect(workspaces.get("default_alias") == "cyberboss", "workspace_default_alias")
    expect(
        list((workspaces.get("workspaces") or {}).keys()) == ["cyberboss"],
        "workspace_cardinality",
    )
    expect(isinstance(workspace, dict), "workspace_cyberboss_missing")
    if isinstance(workspace, dict):
        expect(workspace.get("repo") == "LinzeColin/MetaDatabase", "workspace_repo")
        expect(workspace.get("project_subpath") == "CyberBoss", "workspace_subpath")
        expect(workspace.get("write_globs") == ["CyberBoss/**"], "workspace_write")
        expect(
            workspace.get("sparse_paths") == ["CyberBoss", ".github"],
            "workspace_sparse_paths",
        )

    expect(sha256(project / "LICENSE") == EXPECTED_LICENSE_SHA256, "license_hash")
    root_license = (repo / "LICENSE").read_text(encoding="utf-8")
    root_readme = (repo / "README.md").read_text(encoding="utf-8")
    data_registry = (repo / "WHERE_IS_PROJECT_DATA.md").read_text(encoding="utf-8")
    expect(
        "CyberBoss/` subtree is licensed under\nGNU AGPL-3.0-only" in root_license,
        "root_license_carveout",
    )
    expect(
        "| CyberBoss | 🚧 Prestage 0 |" in root_readme,
        "root_readme_registration",
    )
    expect(
        "| `CyberBoss/` | `CyberBoss` | Prestage 0" in data_registry,
        "data_registry_registration",
    )
    expect(not (project / ".gitmodules").exists(), "project_gitmodules_forbidden")
    expect(
        not (kit / "simulators/canonical-git-simulator.sh").exists(),
        "canonical_git_simulator_present",
    )
    expect(
        (kit / "simulators/private-db-simulator.sh").is_file(),
        "private_db_simulator_missing",
    )

    scan_paths = [
        project / "README.md",
        project / "AGENTS.md",
        *control_files,
    ]
    scan_paths.extend(
        path
        for area in ("config", "scripts", "simulators", "sql", "status")
        for path in (kit / area).rglob("*")
        if path.is_file()
    )
    forbidden_patterns = {
        "independent_repo": re.compile(r"LinzeColin/cyberboss-cloud", re.I),
        "legacy_data_root": re.compile(r"Private-AgentDatabase", re.I),
        "legacy_workspace": re.compile(r"LinzeColin/CodexProject", re.I),
        "private_db_clone_url": re.compile(r"Private-Database\.git", re.I),
        "canonical_repo_path": re.compile(r"/var/lib/cyberboss/canonical-repo"),
        "canonical_commit_field": re.compile(r"\bcanonical_commit\b"),
        "canonical_git_simulator": re.compile(r"canonical-git-simulator"),
        "old_taskpack_version": re.compile(r"v0\.0\.0\.3"),
    }
    for path in sorted(set(scan_paths)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in forbidden_patterns.items():
            if pattern.search(text):
                errors.append(
                    f"forbidden_active_identity:{name}:{path.relative_to(repo)}"
                )

    verify_manifest(kit / "MANIFEST.sha256", kit, errors)
    verify_manifest(pack / "MANIFEST.sha256", pack, errors)

    try:
        branch = git(repo, "branch", "--show-current")
        expect(branch.startswith("codex/cyberboss"), f"branch_scope:{branch}")
        remotes = set(git(repo, "remote").splitlines())
        expect(remotes <= {"origin"}, f"unexpected_remote:{sorted(remotes)}")
        remote_branch = git(
            repo,
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/remotes/origin/codex/cyberboss*",
        )
        expect(not remote_branch, f"intermediate_remote_branch:{remote_branch}")
        for raw in git(repo, "status", "--porcelain=v1").splitlines():
            path_text = raw[3:]
            candidates = path_text.split(" -> ")
            for candidate in candidates:
                if candidate not in {
                    "README.md",
                    "LICENSE",
                    "WHERE_IS_PROJECT_DATA.md",
                } and not candidate.startswith("CyberBoss/"):
                    errors.append(f"run_scope_violation:{candidate}")
    except subprocess.CalledProcessError as exc:
        errors.append(f"git_check_failed:{exc.stderr.strip()}")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print("PRESTAGE0_VALIDATION=FAIL")
        return 1
    print(
        "PRESTAGE0_VALIDATION=PASS "
        "stages=6 tasks=30 oracles=53 requirements=53 "
        "owner_decisions=A1+B1 upstream=separated publication=local_only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
