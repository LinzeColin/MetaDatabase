#!/usr/bin/env python3
"""Fail-closed verifier for the Stage 6.1 software-assurance Task."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.assurance.001"
PHASE = "PH.X2N.6.1"
RUN_ID = "RUN-X2N-S06-A001"
TASK_BASE_COMMIT = "34fac27299e1b5599b78456ee825814f456f2df7"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
ASSURANCE_FACT = PROJECT_ROOT / "machine/facts/stage_6_assurance_001_state.json"
ASSURANCE_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_6_assurance_001_state.schema.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S06_ASSURANCE_001.md"
REPORT = PROJECT_ROOT / "docs/governance/STAGE_6_ASSURANCE_001.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_assurance_001_acceptance.py"
HISTORICAL_REPLAY = PROJECT_ROOT / "scripts/replay_stage_5_review_historical.py"
EVIDENCE = PROJECT_ROOT / "evidence/assurance/TSK.x2n.assurance.001.json"
PLATFORM_CDN_PATTERN = re.compile(
    "|".join(
        re.escape("".join(parts))
        for parts in (
            ("xhs", "cdn"),
            ("douyin", "vod"),
            ("byte", "img"),
            ("pstat", "p"),
            ("bili", "video"),
            ("hd", "slb"),
            ("ks", "cdn"),
            ("yx", "imgs"),
            ("sina", "img"),
            ("tb", "cdn"),
            ("ali", "cdn"),
        )
    ),
    re.I,
)

EXPECTED_ACCEPTANCES = {
    "ACC.x2n.data.002": "PASS_CI_SYNTH_80X2_100_CONCURRENT_FULL_SERVICE_GRAPH_DUPLICATES_ZERO_OWNER_MVP_NOT_RUN",
    "ACC.x2n.data.004": "PASS_CI_SYNTH_10K_MIGRATION_BACKUP_ROLLBACK_DATA_LOSS_ZERO_REAL_RUNTIME_NOT_RUN",
    "ACC.x2n.rel.001": "PASS_CI_SYNTH_CURRENT_FORMAT_LINT_TYPE_UNIT_CONTRACT_MIGRATION_INTEGRATION_BROWSER_E2E_RISK_COVERAGE",
    "ACC.x2n.rel.008": "PASS_CI_SYNTH_FRESH_COPY_SKILL_LIFECYCLE_REAL_INSTALL_NOT_RUN",
}
EXPECTED_ACCEPTANCE_IDS = (
    "ACC.x2n.rel.001",
    "ACC.x2n.data.002",
    "ACC.x2n.data.004",
    "ACC.x2n.rel.008",
)
EXPECTED_EXECUTION = {
    "external_network_calls": 0,
    "model_calls": 0,
    "notion_real_calls": 0,
    "physical_delete_execution": "NOT_RUN",
    "platform_calls": 0,
    "private_database_client_calls": 0,
    "real_account_execution": "NOT_RUN",
    "real_runtime_deployment": "NOT_RUN",
    "tmutil_calls": 0,
}

SOURCE_CHANGED_PATHS = (
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "SKILL.md",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/src/x2n_companion/skill_lifecycle.py",
    "apps/companion/tests/test_canonical_store.py",
    "apps/companion/tests/test_media_preprocessing.py",
    "apps/companion/tests/test_skill_lifecycle.py",
    "apps/extension/scripts/extension-e2e.mjs",
    "docs/governance/RUN_CONTRACT_S06_ASSURANCE_001.md",
    "docs/governance/STAGE_6_ASSURANCE_001.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/stage_6_assurance_001_state.json",
    "machine/facts/task_state.json",
    "machine/policy/ci_gate_manifest.json",
    "machine/schemas/stage_6_assurance_001_state.schema.json",
    "scripts/ci/ci_baseline.py",
    "scripts/ci/run_lane.py",
    "scripts/run_adapters_005_acceptance.py",
    "scripts/replay_stage_5_review_historical.py",
    "scripts/run_assurance_001_acceptance.py",
    "scripts/verify_assurance_001.py",
    "tests/test_assurance_001.py",
    "tests/test_stage_3_review_resume_recheck.py",
    "功能清单.md",
    "开发记录.md",
)
SOURCE_CHANGED_EXACT = frozenset(SOURCE_CHANGED_PATHS)
CURRENT_ALLOWED_EXACT = SOURCE_CHANGED_EXACT | {EVIDENCE.relative_to(PROJECT_ROOT).as_posix()}


class AssuranceVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssuranceVerificationError(message)


def _git(arguments: Sequence[str], *, cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssuranceVerificationError("local Git verification failed")
    return result.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssuranceVerificationError(f"invalid JSON: {path.name}") from error
    _require(isinstance(payload, dict), f"JSON object required: {path.name}")
    return payload


def _taskpack() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise AssuranceVerificationError("Taskpack is unreadable") from error
    _require(isinstance(payload, dict), "Taskpack must be an object")
    return payload


def _blob_at(commit: str, relative_path: str) -> bytes:
    repository_path = f"xhs-douyin-2notion/{relative_path}"
    result = subprocess.run(
        ["git", "show", f"{commit}:{repository_path}"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssuranceVerificationError("historical source blob is missing")
    return result.stdout


def _source_receipt(commit: str) -> str:
    digest = hashlib.sha256()
    for relative_path in SOURCE_CHANGED_PATHS:
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_blob_at(commit, relative_path))
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_payload(payload: Any) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "/" + "home/" not in rendered, "local path entered a public artifact")
    _require(
        "github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "credential entered a public artifact"
    )
    _require(PLATFORM_CDN_PATTERN.search(rendered) is None, "platform media CDN value entered a public artifact")


def _scope_name(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    return path.removeprefix(prefix) if path.startswith(prefix) else None


def _python_ast(blob: bytes) -> str:
    try:
        return ast.dump(ast.parse(blob.decode("utf-8")), annotate_fields=True, include_attributes=False)
    except (SyntaxError, UnicodeDecodeError) as error:
        raise AssuranceVerificationError("format-only Python source is invalid") from error


def _format_only_python_change(*, relative_path: str, commit: str) -> bool:
    if not relative_path.endswith(".py"):
        return False
    return _python_ast(_blob_at(TASK_BASE_COMMIT, relative_path)) == _python_ast(_blob_at(commit, relative_path))


def _changed_paths(start: str, end: str) -> list[str]:
    return [item for item in _git(("diff", "--name-only", "-z", f"{start}..{end}")).split("\0") if item]


def _validate_scope(start: str, end: str, *, allow_evidence: bool) -> int:
    changed = _changed_paths(start, end)
    _require(changed, "assurance source scope is empty")
    relative = [_scope_name(item) for item in changed]
    _require(all(item is not None for item in relative), "assurance scope escaped x2n")
    allowed = CURRENT_ALLOWED_EXACT if allow_evidence else SOURCE_CHANGED_EXACT
    for item in relative:
        assert item is not None
        if item in allowed:
            continue
        _require(
            _format_only_python_change(relative_path=item, commit=end),
            "assurance scope contains an unapproved semantic change",
        )
    return len(relative)


def _json_line(output: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            values.append(payload)
    _require(values, "assurance acceptance emitted no JSON receipt")
    return values[-1]


def validate_taskpack_and_transition() -> Check:
    tasks = {item.get("id"): item for item in _taskpack().get("tasks", []) if isinstance(item, dict)}
    task = tasks.get(TASK_ID)
    _require(
        isinstance(task, dict)
        and task.get("stage") == "STG.X2N.6"
        and task.get("phase") == PHASE
        and task.get("status") == "complete_ci_synth"
        and tuple(task.get("acceptance_ids", [])) == EXPECTED_ACCEPTANCE_IDS
        and tuple(task.get("depends_on", []))
        == (
            "TSK.x2n.foundation.005",
            "TSK.x2n.uxops.004",
            "TSK.x2n.uxops.005",
        ),
        "Taskpack assurance001 contract drifted",
    )
    next_task = tasks.get("TSK.x2n.assurance.002")
    _require(
        isinstance(next_task, dict) and next_task.get("phase") == "PH.X2N.6.2" and next_task.get("status") == "planned",
        "next Task authorization drifted",
    )
    state = _load_json(TASK_STATE)
    _require(
        state.get("schema_version") == "1.42"
        and state.get("stage") == "STG.X2N.6"
        and state.get("phase") == PHASE
        and state.get("last_completed_phase") == PHASE
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "single_dag_task_ci_synth_software_assurance"
        and state.get("state") == "stage_6_assurance001_ci_synth_pass_assurance002_next_real_runtime_not_run"
        and state.get("tasks", {}).get(TASK_ID) == "pass"
        and state.get("acceptance_status", {}).get("ACC.x2n.rel.001") == EXPECTED_ACCEPTANCES["ACC.x2n.rel.001"]
        and state.get("acceptance_status", {}).get("ACC.x2n.data.002") == EXPECTED_ACCEPTANCES["ACC.x2n.data.002"]
        and state.get("acceptance_status", {}).get("ACC.x2n.data.004") == EXPECTED_ACCEPTANCES["ACC.x2n.data.004"]
        and state.get("acceptance_status", {}).get("ACC.x2n.rel.008") == EXPECTED_ACCEPTANCES["ACC.x2n.rel.008"]
        and state.get("next_phase") == "PH.X2N.6.2"
        and state.get("next_run") == "TSK.x2n.assurance.002"
        and state.get("next_task") == "TSK.x2n.assurance.002"
        and state.get("next_phase_authorized") is True
        and state.get("stage_6_task001_complete") is True
        and state.get("stage_6_task002_authorized") is True
        and state.get("public_release_authorized") is False,
        "Task State assurance001 transition is invalid",
    )
    return Check("taskpack_and_state_transition", "PASS", {"next_task": "TSK.x2n.assurance.002"})


def validate_assurance_fact_and_public_boundary() -> Check:
    schema = _load_json(ASSURANCE_SCHEMA)
    fact = _load_json(ASSURANCE_FACT)
    _require(
        schema.get("$id") == "urn:x2n:stage-6-assurance-001-state:1.0"
        and fact.get("schema_version") == "1.0"
        and fact.get("project") == "x2n"
        and fact.get("stage") == "STG.X2N.6"
        and fact.get("task_id") == TASK_ID
        and fact.get("phase") == PHASE
        and fact.get("run_id") == RUN_ID
        and fact.get("task_base_commit") == TASK_BASE_COMMIT
        and fact.get("status") == "PASS_CI_SYNTH_CURRENT_SOFTWARE_ASSURANCE_REAL_MVP_NOT_RUN"
        and fact.get("acceptance_status") == EXPECTED_ACCEPTANCES
        and fact.get("execution") == EXPECTED_EXECUTION
        and fact.get("next_task") == {"id": "TSK.x2n.assurance.002", "phase": "PH.X2N.6.2", "status": "PLANNED"}
        and fact.get("release_policy")
        == {
            "alpha_beta": "PROHIBITED",
            "direct_mvp_deploy_run_online_smoke": "TSK.x2n.assurance.005_ONLY",
            "fixed_health_observation": "PROHIBITED",
            "fixed_soak": "PROHIBITED",
        },
        "assurance001 fact contract drifted",
    )
    _safe_payload(fact)
    for path in (RUN_CONTRACT, REPORT, ASSURANCE_FACT, ASSURANCE_SCHEMA, ACCEPTANCE_RUNNER, HISTORICAL_REPLAY):
        _require(path.is_file(), "assurance control artifact is missing")
        _require(path.stat().st_size <= 2 * 1024 * 1024, "assurance control artifact exceeds size budget")
        _safe_payload({"control": path.read_text(encoding="utf-8")})
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    expected_status = "stage_6_assurance001_ci_synth_pass_assurance002_next_real_runtime_not_run"
    _require(
        project.get("schema_version") == "1.6"
        and project.get("status") == expected_status
        and project.get("stage_6_current_task") == "assurance001_ci_synth_pass_assurance002_next_real_runtime_not_run",
        "project fact overclaims assurance001 capability",
    )
    decisions = architecture.get("decisions")
    adr = (
        next(
            (item for item in decisions if isinstance(item, dict) and item.get("id") == "ADR-022"),
            None,
        )
        if isinstance(decisions, list)
        else None
    )
    _require(
        architecture.get("schema_version") == "1.6"
        and architecture.get("phase") == PHASE
        and architecture.get("status") == expected_status
        and architecture.get("stage_gate")
        == "g5_pass_ci_synth_stage6_assurance001_pass_assurance002_authorized_private_gold_disabled"
        and isinstance(adr, dict)
        and adr.get("topic") == "stage_6_software_assurance_current_pipeline_and_historical_replay"
        and adr.get("state") == "accepted_implementation",
        "architecture fact overclaims assurance001 capability",
    )
    skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    _require(
        "x2n_companion.skill_lifecycle" in skill
        and "x2n_companion.scaffold" not in skill
        and "TSK.x2n.assurance.005" in skill
        and "Alpha, Beta, fixed 30-day observation, or soak gate" in skill,
        "Skill lifecycle or release boundary drifted",
    )
    return Check("assurance_fact_and_public_boundary", "PASS", {"controls_scanned": 6, "sensitive_value_hits": 0})


def validate_current_pipeline_definition() -> Check:
    lane = (PROJECT_ROOT / "scripts/ci/run_lane.py").read_text(encoding="utf-8")
    runner = ACCEPTANCE_RUNNER.read_text(encoding="utf-8")
    lifecycle = (PROJECT_ROOT / "apps/companion/src/x2n_companion/skill_lifecycle.py").read_text(encoding="utf-8")
    _require(
        '"format", "--check", "."' in lane
        and "test_assurance_001.py" in lane
        and "historical_stage5_review" in lane
        and '"test:extension"' in lane,
        "current CI lane does not cover assurance001",
    )
    _require(
        "MUTATION_CASES" in runner
        and "run_adapters_005_acceptance.py" in runner
        and "run_uxops_005_acceptance.py" in runner
        and "replay_stage_5_review_historical.py" in runner,
        "assurance acceptance runner lost critical coverage",
    )
    _require(
        "REAL_INSTALL_AND_MVP_DEPLOYMENT_NOT_RUN" in lifecycle
        and "X2N_SKILL_REAL_CANARY_UNAUTHORIZED" in lifecycle
        and "X2N_SKILL_UNINSTALL_DESTRUCTIVE_UNAUTHORIZED" in lifecycle,
        "fresh-copy lifecycle is not fail closed",
    )
    return Check("current_pipeline_definition", "PASS", {"critical_mutants": 2, "fresh_copy_commands": 7})


def validate_fresh_acceptance() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a001-verify-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = {
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "apps/companion/src:packages/contracts/src",
        }
        result = subprocess.run(
            [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
            cwd=PROJECT_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=7_200,
        )
    _require(result.returncode == 0, "fresh assurance acceptance failed")
    receipt = _json_line(result.stdout)
    pipeline = receipt.get("pipeline")
    _require(
        receipt.get("schema_version") == "1.0"
        and receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("run_id") == RUN_ID
        and receipt.get("status") == "PASS_CI_SYNTH_CURRENT_SOFTWARE_ASSURANCE_REAL_MVP_NOT_RUN"
        and receipt.get("acceptance_status") == EXPECTED_ACCEPTANCES
        and receipt.get("execution") == EXPECTED_EXECUTION
        and isinstance(pipeline, dict)
        and pipeline.get("blocking_failures") == 0
        and pipeline.get("blocking_skips") == 0
        and pipeline.get("flaky_blocking_tests") == 0
        and pipeline.get("source_scan", {}).get("finding_count") == 0
        and pipeline.get("coverage", {}).get("status") == "PASS"
        and pipeline.get("extension_e2e", {}).get("status") == "PASS"
        and pipeline.get("extension_e2e", {}).get("platform_calls") == 0,
        "fresh assurance pipeline receipt drifted",
    )
    _require(
        receipt.get("idempotency")
        == {
            "artifact_duplicates": 0,
            "concurrent_duplicate_messages": 100,
            "content_duplicates": 0,
            "input_items": 80,
            "markdown_duplicates": 0,
            "notion_mock_pages": 80,
            "notion_page_duplicates": 0,
            "outbox_receipts": 160,
            "relation_duplicates": 0,
            "sequential_runs": 2,
        }
        and receipt.get("migration", {}).get("data_loss") == 0
        and receipt.get("migration", {}).get("unreadable_records") == 0
        and receipt.get("migration", {}).get("destructive_migration_without_verified_backup") == 0
        and receipt.get("fresh_copy", {}).get("commands") == 7
        and receipt.get("fresh_copy", {}).get("runtime_writes") == 0
        and receipt.get("mutation") == {"killed_mutants": 2, "mutants": 2, "surviving_mutants": 0}
        and receipt.get("historical_replay", {}).get("status") == "PASS"
        and receipt.get("historical_replay", {}).get("historical_commit") == TASK_BASE_COMMIT
        and receipt.get("historical_replay", {}).get("current_stage_6_tree_evaluated") is False,
        "fresh assurance acceptance metrics drifted",
    )
    return Check(
        "fresh_ci_synth_assurance_acceptance",
        "PASS",
        {
            "companion_tests": pipeline["companion_unit_integration"]["tests"],
            "fresh_copy_commands": receipt["fresh_copy"]["commands"],
            "killed_mutants": receipt["mutation"]["killed_mutants"],
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(("rev-parse", "--show-toplevel"))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(("branch", "--show-current"))
    _require(branch not in {"", "main"}, "assurance001 must run in a non-main worktree")
    _require(
        re.fullmatch(
            r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?",
            _git(("config", "--local", "--get", "remote.origin.url")),
        )
        is not None,
        "wrong or authenticated persisted origin",
    )
    main_path: Path | None = None
    for block in _git(("worktree", "list", "--porcelain")).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        if worktree and "branch refs/heads/main" in lines:
            main_path = Path(worktree)
            break
    _require(main_path is not None and _git(("branch", "--show-current"), cwd=main_path) == "main", "main unavailable")
    main_paths = _git(
        ("-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"), cwd=main_path
    ).splitlines()
    _require(sum("xhs-douyin-2notion" in item for item in main_paths) == 0, "main dirty state overlaps x2n")
    _require(allow_external_main_dirty or not main_paths, "MetaDatabase main worktree is dirty")
    _require(
        subprocess.run(
            ("git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, "HEAD"),
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "assurance001 does not descend from G5",
    )
    return Check(
        "worktree_isolation",
        "PASS",
        {"branch": branch, "external_main_dirty_paths": len(main_paths), "main_mutated": False},
    )


def validate_evidence_and_scope() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_payload(evidence)
    task_commit = evidence.get("task_commit")
    _require(
        isinstance(task_commit, str) and re.fullmatch(r"[0-9a-f]{40}", task_commit) is not None,
        "assurance task commit is invalid",
    )
    _git(("cat-file", "-e", f"{task_commit}^{{commit}}"))
    _require(
        subprocess.run(
            ("git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, task_commit),
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
        and subprocess.run(
            ("git", "merge-base", "--is-ancestor", task_commit, "HEAD"),
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "assurance task commit ancestry is invalid",
    )
    _require(
        _validate_scope(TASK_BASE_COMMIT, task_commit, allow_evidence=False) >= len(SOURCE_CHANGED_EXACT),
        "assurance task source scope is incomplete",
    )
    current_paths = _validate_scope(TASK_BASE_COMMIT, "HEAD", allow_evidence=True)
    _require(
        evidence
        == {
            "acceptance_status": EXPECTED_ACCEPTANCES,
            "execution": EXPECTED_EXECUTION,
            "fresh_copy": {
                "commands": 7,
                "private_path_output": 0,
                "real_canary": "NOT_RUN",
                "runtime_writes": 0,
            },
            "historical_replay": {
                "current_stage_6_tree_evaluated": False,
                "historical_commit": TASK_BASE_COMMIT,
                "historical_review": "STG.X2N.5.REVIEW",
                "status": "PASS",
            },
            "idempotency": {
                "artifact_duplicates": 0,
                "concurrent_duplicate_messages": 100,
                "content_duplicates": 0,
                "input_items": 80,
                "markdown_duplicates": 0,
                "notion_mock_pages": 80,
                "notion_page_duplicates": 0,
                "outbox_receipts": 160,
                "relation_duplicates": 0,
                "sequential_runs": 2,
            },
            "migration": {
                "data_loss": 0,
                "destructive_migration_without_verified_backup": 0,
                "tombstone_epoch_regressions_accepted": 0,
                "unreadable_records": 0,
            },
            "mutation": {"killed_mutants": 2, "mutants": 2, "surviving_mutants": 0},
            "phase": PHASE,
            "run_id": RUN_ID,
            "schema_version": "1.0",
            "source_receipt_sha256": _source_receipt(task_commit),
            "status": "PASS_CI_SYNTH_CURRENT_SOFTWARE_ASSURANCE_REAL_MVP_NOT_RUN",
            "task_base_commit": TASK_BASE_COMMIT,
            "task_commit": task_commit,
            "task_id": TASK_ID,
        },
        "assurance evidence receipt drifted",
    )
    return Check("assurance_evidence_and_scope", "PASS", {"current_paths": current_paths, "task_source": "verified"})


def run_checks(
    *, verify_worktree: bool, allow_external_main_dirty: bool, run_acceptance: bool, require_evidence: bool
) -> list[Check]:
    checks = [
        validate_taskpack_and_transition(),
        validate_assurance_fact_and_public_boundary(),
        validate_current_pipeline_definition(),
    ]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_fresh_acceptance())
    if require_evidence:
        checks.append(validate_evidence_and_scope())
    _require(all(check.status == "PASS" for check in checks), "assurance001 verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify x2n Stage 6 Assurance001")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--run-acceptance", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            run_acceptance=args.run_acceptance,
            require_evidence=args.require_evidence,
        )
        print(
            json.dumps(
                {
                    "checks": [{"details": item.details, "name": item.name, "status": item.status} for item in checks],
                    "status": "PASS",
                    "task_id": TASK_ID,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, AssuranceVerificationError, subprocess.SubprocessError, yaml.YAMLError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
