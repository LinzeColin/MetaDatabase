#!/usr/bin/env python3
"""Fail-closed verifier for Stage 6.4 performance, chaos, and recovery assurance."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
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

_BOOTSTRAP_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BOOTSTRAP_PROJECT_ROOT))

from scripts.run_assurance_004_acceptance import (
    EXPECTED_ACCEPTANCES,
    EXPECTED_EXECUTION,
    EXPECTED_REPORTS,
)  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.assurance.004"
PHASE = "PH.X2N.6.4"
RUN_ID = "RUN-X2N-S06-A004"
TASK_BASE_COMMIT = "f69dd7a4f2fbc0a0d50063e3d2f2a2e64ec58f7e"
STATUS = "PASS_CI_SYNTH_PERFORMANCE_CHAOS_RECOVERY_REAL_MVP_NOT_RUN"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
ASSURANCE_FACT = PROJECT_ROOT / "machine/facts/stage_6_assurance_004_state.json"
ASSURANCE_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_6_assurance_004_state.schema.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S06_ASSURANCE_004.md"
REPORT = PROJECT_ROOT / "docs/governance/STAGE_6_ASSURANCE_004.md"
CAMPAIGN_REPORT = PROJECT_ROOT / "docs/governance/ASSURANCE_004_CAMPAIGN_REPORT.md"
CAMPAIGN_POLICY = PROJECT_ROOT / "machine/policy/assurance_004_campaign_policy.json"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_assurance_004_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/chaos/TSK.x2n.assurance.004.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
RELEASE_ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/release_artifact_allowlist.json"
TASKPACK_DEPENDENCIES = (
    "TSK.x2n.uxops.004",
    "TSK.x2n.multimodal.001",
    "TSK.x2n.uxops.001",
)
RELEASE_POLICY = {
    "alpha_beta": "PROHIBITED",
    "direct_mvp_deploy_run_online_smoke": "TSK.x2n.assurance.005_ONLY",
    "fixed_health_observation": "PROHIBITED",
    "fixed_soak": "PROHIBITED",
}
SOURCE_CHANGED_PATHS = (
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "docs/governance/ASSURANCE_004_CAMPAIGN_REPORT.md",
    "docs/governance/RUN_CONTRACT_S06_ASSURANCE_004.md",
    "docs/governance/STAGE_6_ASSURANCE_004.md",
    "docs/product_design/v0.0.0.1/00_PRFAQ.md",
    "docs/product_design/v0.0.0.1/01_PRD.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/stage_6_assurance_004_state.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/assurance_004_campaign_policy.json",
    "machine/schemas/stage_6_assurance_004_state.schema.json",
    "scripts/run_assurance_004_acceptance.py",
    "scripts/verify_assurance_004.py",
    "tests/test_assurance_004.py",
    "功能清单.md",
    "开发记录.md",
)
SOURCE_CHANGED_EXACT = frozenset(SOURCE_CHANGED_PATHS)
CURRENT_ALLOWED_EXACT = SOURCE_CHANGED_EXACT | {EVIDENCE.relative_to(PROJECT_ROOT).as_posix()}
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


class Assurance004VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance004VerificationError(message)


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
    _require(result.returncode == 0, "local Git verification failed")
    return result.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Assurance004VerificationError(f"invalid JSON: {path.name}") from error
    _require(isinstance(payload, dict), f"JSON object required: {path.name}")
    return payload


def _taskpack() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise Assurance004VerificationError("Taskpack is unreadable") from error
    _require(isinstance(payload, dict), "Taskpack must be an object")
    return payload


def _safe_payload(payload: Any) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "/" + "home/" not in rendered, "local path entered public output")
    _require("github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "credential entered public output")
    _require(PLATFORM_CDN_PATTERN.search(rendered) is None, "platform CDN entered public output")


def _blob_at(commit: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:xhs-douyin-2notion/{relative_path}"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    _require(result.returncode == 0, "historical source blob is missing")
    return result.stdout


def _source_receipt(commit: str) -> str:
    digest = hashlib.sha256()
    for relative_path in SOURCE_CHANGED_PATHS:
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_blob_at(commit, relative_path))
        digest.update(b"\0")
    return digest.hexdigest()


def _changed_paths(start: str, end: str) -> list[str]:
    return [path for path in _git(("diff", "--name-only", "-z", f"{start}..{end}")).split("\0") if path]


def _validate_scope(start: str, end: str, *, allow_evidence: bool) -> int:
    changed = _changed_paths(start, end)
    _require(changed, "assurance004 source scope is empty")
    prefix = "xhs-douyin-2notion/"
    _require(all(path.startswith(prefix) for path in changed), "assurance004 scope escaped x2n")
    relative = [path.removeprefix(prefix) for path in changed]
    allowed = CURRENT_ALLOWED_EXACT if allow_evidence else SOURCE_CHANGED_EXACT
    _require(set(relative) <= allowed, "assurance004 scope contains an unapproved change")
    return len(relative)


def _json_line(output: str) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    _require(payloads, "assurance004 acceptance emitted no JSON receipt")
    return payloads[-1]


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(("rev-parse", "--show-toplevel"))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(("branch", "--show-current"))
    _require(branch not in {"", "main"}, "assurance004 must run in a non-main worktree")
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
    _require(sum("xhs-douyin-2notion" in path for path in main_paths) == 0, "main dirty state overlaps x2n")
    _require(allow_external_main_dirty or not main_paths, "MetaDatabase main worktree is dirty")
    _require(
        subprocess.run(
            ("git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, "HEAD"),
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "assurance004 does not descend from assurance003",
    )
    return Check("worktree_isolation", "PASS", {"branch": branch, "external_main_dirty_paths": len(main_paths)})


def validate_transition_and_facts() -> Check:
    tasks = {item.get("id"): item for item in _taskpack().get("tasks", []) if isinstance(item, dict)}
    task = tasks.get(TASK_ID)
    _require(
        isinstance(task, dict)
        and task.get("stage") == "STG.X2N.6"
        and task.get("phase") == PHASE
        and task.get("status") == "complete_ci_synth_performance_chaos_recovery"
        and tuple(task.get("acceptance_ids", [])) == tuple(EXPECTED_ACCEPTANCES)
        and tuple(task.get("depends_on", [])) == TASKPACK_DEPENDENCIES,
        "Taskpack assurance004 transition drifted",
    )
    next_task = tasks.get("TSK.x2n.assurance.005")
    _require(
        isinstance(next_task, dict) and next_task.get("phase") == "PH.X2N.6.5" and next_task.get("status") == "planned",
        "next Task authorization drifted",
    )
    state = _load_json(TASK_STATE)
    expected_state = (
        "stage_6_assurance004_ci_synth_performance_chaos_recovery_pass_assurance005_next_owner_input_required"
    )
    _require(
        state.get("schema_version") == "1.45"
        and state.get("stage") == "STG.X2N.6"
        and state.get("phase") == PHASE
        and state.get("last_completed_phase") == PHASE
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "single_dag_task_ci_synth_performance_chaos_recovery_assurance"
        and state.get("state") == expected_state
        and state.get("tasks", {}).get(TASK_ID) == "pass"
        and all(state.get("acceptance_status", {}).get(key) == value for key, value in EXPECTED_ACCEPTANCES.items())
        and state.get("next_phase") == "PH.X2N.6.5"
        and state.get("next_run") == "TSK.x2n.assurance.005"
        and state.get("next_task") == "TSK.x2n.assurance.005"
        and state.get("stage_6_task004_complete") is True
        and state.get("stage_6_task004_acceptance") == EXPECTED_ACCEPTANCES
        and state.get("stage_6_task005_authorized") is True
        and state.get("public_release_authorized") is False,
        "Task State assurance004 transition is invalid",
    )
    schema = _load_json(ASSURANCE_SCHEMA)
    fact = _load_json(ASSURANCE_FACT)
    _require(
        schema.get("$id") == "urn:x2n:stage-6-assurance-004-state:1.0"
        and fact.get("schema_version") == "1.0"
        and fact.get("project") == "x2n"
        and fact.get("stage") == "STG.X2N.6"
        and fact.get("task_id") == TASK_ID
        and fact.get("phase") == PHASE
        and fact.get("run_id") == RUN_ID
        and fact.get("task_base_commit") == TASK_BASE_COMMIT
        and fact.get("status") == STATUS
        and fact.get("acceptance_status") == EXPECTED_ACCEPTANCES
        and fact.get("execution") == EXPECTED_EXECUTION
        and fact.get("reports") == EXPECTED_REPORTS
        and fact.get("next_task")
        == {"id": "TSK.x2n.assurance.005", "phase": "PH.X2N.6.5", "status": "PLANNED_OWNER_INPUT_REQUIRED"}
        and fact.get("release_policy") == RELEASE_POLICY,
        "assurance004 fact drifted",
    )
    _safe_payload(fact)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    adr = next(
        (item for item in architecture.get("decisions", []) if isinstance(item, dict) and item.get("id") == "ADR-025"),
        None,
    )
    _require(
        project.get("schema_version") == "1.9"
        and project.get("status") == expected_state
        and project.get("stage_6_current_task")
        == "assurance004_ci_synth_performance_chaos_recovery_pass_assurance005_next_owner_input_required"
        and project.get("performance_chaos_recovery_assurance")
        == "isolated_extension_100_restart_xhs_100_50kill_media_cleanup_notion_mock_ten_stage_recovery_ten_seed_matrix_20_80_1000_10000_markdown_burst100_pass_real_mvp_not_run",
        "project fact overclaims assurance004 capability",
    )
    _require(
        architecture.get("schema_version") == "1.9"
        and architecture.get("phase") == PHASE
        and architecture.get("status") == expected_state
        and architecture.get("stage_gate")
        == "g5_pass_assurance001_pass_assurance002_features_disabled_assurance003_security_pass_assurance004_performance_chaos_recovery_pass_assurance005_owner_input_required"
        and isinstance(adr, dict)
        and adr.get("topic") == "stage_6_isolated_performance_chaos_and_recovery_campaign"
        and adr.get("state") == "accepted_implementation",
        "architecture fact overclaims assurance004 capability",
    )
    return Check("taskpack_state_and_fact_transition", "PASS", {"next_task": "TSK.x2n.assurance.005"})


def validate_campaign_boundary() -> Check:
    policy = _load_json(CAMPAIGN_POLICY)
    artifact_policy = _load_json(ARTIFACT_POLICY)
    release_policy = _load_json(RELEASE_ARTIFACT_POLICY)
    _require(
        policy.get("task_id") == TASK_ID
        and policy.get("phase") == PHASE
        and policy.get("execution_scope") == "CI_SYNTH_ISOLATED_TEMP_RUNTIME"
        and policy.get("critical_matrix", {}).get("seeds_per_critical_scenario") == 10
        and len(policy.get("critical_matrix", {}).get("scenarios", [])) == 6
        and policy.get("benchmark", {}).get("markdown_rebuild_scales") == [20, 80, 1_000, 10_000]
        and policy.get("benchmark", {}).get("burst_current_page_messages") == 100
        and policy.get("benchmark", {}).get("universal_timing_slo") == "PROHIBITED_RUNTIME_LOCAL_MEASUREMENT_ONLY"
        and policy.get("isolation", {}).get("owner_runtime") == "FORBIDDEN"
        and policy.get("isolation", {}).get("platform_calls") == 0
        and policy.get("release_boundary") == RELEASE_POLICY,
        "campaign policy drifted",
    )
    _require(
        "scripts/run_assurance_004_acceptance.py" in artifact_policy.get("enforcement", [])
        and "scripts/verify_assurance_004.py" in artifact_policy.get("enforcement", [])
        and release_policy.get("runtime_data_allowed") is False
        and release_policy.get("absolute_paths_allowed") is False
        and release_policy.get("credentials_allowed") is False
        and release_policy.get("platform_media_cdn_urls_allowed") is False,
        "public artifact policy drifted",
    )
    for path in (RUN_CONTRACT, REPORT, CAMPAIGN_REPORT, CAMPAIGN_POLICY, ASSURANCE_FACT, ASSURANCE_SCHEMA):
        _require(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, "assurance004 control missing or oversized")
        _safe_payload({"control": path.read_text(encoding="utf-8")})
    runner = ACCEPTANCE_RUNNER.read_text(encoding="utf-8")
    _require(
        "GIT_CONFIG_NOSYSTEM" in runner
        and "GIT_TERMINAL_PROMPT" in runner
        and "PLAYWRIGHT_BROWSERS_PATH" in runner
        and "TemporaryDirectory" in runner
        and "SEED_COUNT = 10" in runner
        and "BENCHMARK_SCALES = (20, 80, 1_000, 10_000)" in runner
        and "os.environ" + ".copy" not in runner,
        "campaign runner boundary drifted",
    )
    return Check(
        "isolated_campaign_public_boundary",
        "PASS",
        {"critical_seed_count": 10, "owner_runtime_access": 0, "sensitive_value_hits": 0},
    )


def validate_fresh_acceptance() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a004-verify-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = {
            "GCM_INTERACTIVE": "never",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "apps/companion/src:packages/contracts/src",
            "RUFF_CACHE_DIR": str(home / "ruff-cache"),
        }
        browser_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
        if browser_cache.is_dir():
            environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
        result = subprocess.run(
            [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
            cwd=PROJECT_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=2_400,
        )
    _require(result.returncode == 0, "fresh performance/chaos/recovery acceptance failed")
    receipt = _json_line(result.stdout)
    _require(
        receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("run_id") == RUN_ID
        and receipt.get("status") == STATUS
        and receipt.get("acceptance_status") == EXPECTED_ACCEPTANCES
        and receipt.get("execution") == EXPECTED_EXECUTION
        and receipt.get("reports") == EXPECTED_REPORTS,
        "fresh performance/chaos/recovery receipt drifted",
    )
    return Check(
        "fresh_ci_synth_performance_chaos_recovery",
        "PASS",
        {"benchmark_scales": 4, "critical_seed_runs": 10, "platform_calls": 0},
    )


def validate_evidence_and_scope() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_payload(evidence)
    task_commit = evidence.get("task_commit")
    _require(
        isinstance(task_commit, str) and re.fullmatch(r"[0-9a-f]{40}", task_commit) is not None,
        "assurance004 task commit is invalid",
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
        "assurance004 task commit ancestry is invalid",
    )
    _require(
        _validate_scope(TASK_BASE_COMMIT, task_commit, allow_evidence=False) >= len(SOURCE_CHANGED_EXACT),
        "assurance004 source scope incomplete",
    )
    current_paths = _validate_scope(TASK_BASE_COMMIT, "HEAD", allow_evidence=True)
    _require(
        evidence
        == {
            "acceptance_status": EXPECTED_ACCEPTANCES,
            "execution": EXPECTED_EXECUTION,
            "phase": PHASE,
            "reports": EXPECTED_REPORTS,
            "run_id": RUN_ID,
            "schema_version": "1.0",
            "source_receipt_sha256": _source_receipt(task_commit),
            "status": STATUS,
            "task_base_commit": TASK_BASE_COMMIT,
            "task_commit": task_commit,
            "task_id": TASK_ID,
        },
        "assurance004 evidence receipt drifted",
    )
    return Check("assurance_evidence_and_scope", "PASS", {"current_paths": current_paths, "task_source": "verified"})


def run_checks(
    *, verify_worktree: bool, allow_external_main_dirty: bool, run_acceptance: bool, require_evidence: bool
) -> list[Check]:
    checks = [validate_transition_and_facts(), validate_campaign_boundary()]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_fresh_acceptance())
    if require_evidence:
        checks.append(validate_evidence_and_scope())
    _require(all(check.status == "PASS" for check in checks), "assurance004 verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify x2n Stage 6 Assurance004")
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
    except (OSError, Assurance004VerificationError, subprocess.SubprocessError, yaml.YAMLError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
