#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.foundation.005."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
CI_SCRIPT_ROOT = PROJECT_ROOT / "scripts/ci"
if str(CI_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_SCRIPT_ROOT))

from ci_baseline import (  # noqa: E402
    ARTIFACT_POLICY,
    CI_POLICY,
    LICENSE_POLICY,
    MODEL_FIXTURE,
    SBOM,
    WORKFLOW,
    BaselineError,
    build_artifact,
    fixture_guard,
    run_sast,
    run_self_test,
    scan_source,
    validate_csp,
    validate_license,
    validate_model_dataset,
)


TASK_ID = "TSK.x2n.foundation.005"
RUN_ID = "RUN-X2N-S01-F005"
BRANCH = "codex/xhs-douyin-2notion-v0001-s01-foundation001"
TASK_BASE_COMMIT = "09d5cdf1993080401f99e023feb03be479baca27"
FINAL_COMMIT = "5f770b6daf63d57ec4698dc7fbc95a9dfeab2669"
STAGE_1_REVIEW_COMMIT = "2a81db2dd36638b00175ec6226462b37905d4705"
ORIGIN_CUTOFF = "7fd0768002081f27c070561fa855a08713d1bc00"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S01_FOUNDATION_005.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
G1_FACT = PROJECT_ROOT / "machine/facts/stage_1_gate_state.json"
MODEL_CARD = PROJECT_ROOT / "docs/model/MODEL_SYSTEM_CARD_S01_F005.md"
FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
EVIDENCE = PROJECT_ROOT / "evidence/ci/TSK.x2n.foundation.005.json"

ALLOWED_CHANGED_EXACT = {
    ".gitignore",
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_canonical_store.py",
    "docs/governance/RUN_CONTRACT_S01_FOUNDATION_005.md",
    "docs/governance/RUN_CONTRACT_S01_REVIEW.md",
    "docs/governance/STAGE_1_REVIEW.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "docs/product_design/v0.0.0.1/03_ARCHITECTURE_SECURITY_SYSTEM_CARD.md",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/facts/stage_1_gate_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/ci_gate_manifest.json",
    "machine/policy/dependency_license_policy.json",
    "machine/policy/release_artifact_allowlist.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/schemas/stage_1_gate_state.schema.json",
    "machine/sbom/stage_1_foundation_005.cdx.json",
    "pyproject.toml",
    "scripts/generate_foundation_002_sbom.py",
    "scripts/generate_foundation_004_sbom.py",
    "scripts/generate_foundation_005_sbom.py",
    "scripts/verify_foundation_001.py",
    "scripts/verify_foundation_002.py",
    "scripts/verify_foundation_003.py",
    "scripts/verify_foundation_004.py",
    "scripts/verify_foundation_005.py",
    "scripts/verify_stage_1_review.py",
    "scripts/verify_phase_0_2.py",
    "scripts/verify_phase_0_5.py",
    "scripts/verify_stage_0_review.py",
    "scripts/verify_stage_0_review_resume.py",
    "tests/test_foundation_005.py",
    "tests/test_stage_1_review.py",
    "uv.lock",
    "功能清单.md",
    "开发记录.md",
    "模型参数文件.md",
}
ALLOWED_CHANGED_PREFIXES = (
    "docs/model/",
    "evidence/ci/",
    "packages/test-fixtures/ci/",
    "scripts/ci/",
    "machine/evidence/stage_1/review/",
)

EXPECTED_BLOCKING_GATES = (
    "format",
    "lint",
    "python_compile",
    "typescript_contract",
    "root_unit",
    "companion_unit_integration",
    "contract_unit",
    "contract_acceptance",
    "sbom_drift",
    "scaffold_acceptance",
    "migration_integration",
    "extension_native_e2e",
)


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def _git(args: Sequence[str], cwd: Path = REPOSITORY_ROOT, *, binary: bool = False) -> str | bytes:
    git = shutil.which("git")
    _require(git is not None, "git unavailable")
    result = subprocess.run(
        [git, *args],
        cwd=cwd,
        env=_git_environment(),
        check=False,
        capture_output=True,
        text=not binary,
    )
    _require(result.returncode == 0, "local Git verification failed")
    return result.stdout if binary else str(result.stdout).rstrip()


def _load_json_at(commit: str, path: Path) -> dict[str, Any]:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    value = json.loads(str(_git(["show", f"{commit}:{relative}"])))
    _require(isinstance(value, dict), f"historical JSON object required: {path.name}")
    return value


def _changed_paths() -> set[str]:
    changed = str(
        _git(
            [
                "-c",
                "core.quotePath=false",
                "diff",
                "--name-only",
                f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}",
            ]
        )
    ).splitlines()
    return {path for path in changed if path}


def _porcelain_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return paths


def _ast_equivalent_to_task_base(relative: str) -> bool:
    repository_path = f"xhs-douyin-2notion/{relative}"
    current = PROJECT_ROOT / relative
    if current.suffix != ".py" or not current.is_file():
        return False
    try:
        previous = str(_git(["show", f"{TASK_BASE_COMMIT}:{repository_path}"]))
        before = ast.dump(ast.parse(previous), include_attributes=False)
        after = ast.dump(ast.parse(current.read_text(encoding="utf-8")), include_attributes=False)
    except (SyntaxError, VerificationError):
        return False
    return before == after


def validate_scope_and_privacy() -> Check:
    changes = _changed_paths()
    formatting_only = 0
    for path in changes:
        if path == ".github/workflows/x2n-ci.yml":
            continue
        _require(path.startswith("xhs-douyin-2notion/"), "Foundation005 changed an unrelated repository path")
        relative = path.removeprefix("xhs-douyin-2notion/")
        allowed = relative in ALLOWED_CHANGED_EXACT or any(
            relative.startswith(prefix) for prefix in ALLOWED_CHANGED_PREFIXES
        )
        if allowed:
            continue
        if _ast_equivalent_to_task_base(relative):
            formatting_only += 1
            continue
        raise VerificationError(f"out-of-scope Foundation005 change: {relative}")
    privacy = scan_source()
    _require(privacy["status"] == "PASS" and privacy["finding_count"] == 0, "project privacy scan failed")
    return Check(
        "scope_and_privacy",
        "PASS",
        {
            "changed_files": len(changes),
            "format_only_python_files": formatting_only,
            "out_of_scope_writes": 0,
            "private_secret_cdn_findings": 0,
            "workflow_root_files": int(".github/workflows/x2n-ci.yml" in changes),
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(str(_git(["rev-parse", "--show-toplevel"]))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(str(_git(["branch", "--show-current"])) == BRANCH, "wrong Stage 1 worktree branch")
    persisted_remote = str(_git(["config", "--local", "--get", "remote.origin.url"]))
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote)
        is not None,
        "wrong or authenticated persisted origin",
    )
    for commit in (TASK_BASE_COMMIT, ORIGIN_CUTOFF):
        _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            [shutil.which("git") or "git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            env=_git_environment(),
            check=False,
        ).returncode
        == 0,
        "Foundation005 branch no longer descends from its Task base",
    )
    live_origin = str(_git(["rev-parse", "origin/main"]))
    _require(
        subprocess.run(
            [shutil.which("git") or "git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin],
            cwd=REPOSITORY_ROOT,
            env=_git_environment(),
            check=False,
        ).returncode
        == 0,
        "origin/main no longer descends from the Run cutoff",
    )
    origin_paths = str(
        _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{ORIGIN_CUTOFF}..{live_origin}"])
    ).splitlines()
    origin_overlap = sum(
        path == ".github/workflows/x2n-ci.yml" or path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/")
        for path in origin_paths
    )
    _require(origin_overlap == 0, "origin/main changed x2n or its workflow after the Run cutoff")

    main_path: Optional[Path] = None
    for block in str(_git(["worktree", "list", "--porcelain"])).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(
        main_path is not None and str(_git(["branch", "--show-current"], main_path)) == "main",
        "main worktree unavailable or off main",
    )
    main_paths = _porcelain_paths(
        str(_git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], main_path))
    )
    main_overlap = sum(
        path == ".github/workflows/x2n-ci.yml" or path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/")
        for path in main_paths
    )
    _require(main_overlap == 0, "main dirty state overlaps x2n or its workflow")
    _require(allow_external_main_dirty or not main_paths, "main worktree is dirty")
    return Check(
        "worktree_isolation",
        "PASS",
        {
            "branch": BRANCH,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(str(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"]))),
            "origin_overlap": origin_overlap,
            "project_overlap_paths": main_overlap,
        },
    )


def validate_task_contract() -> Check:
    taskpack = TASKPACK.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^- id: TSK\.x2n\.foundation\.005\n(.*?)(?=^- id: )", taskpack)
    _require(match is not None, "Foundation005 Task missing")
    block = match.group(0)
    for token in (
        "status: completed",
        "phase: PH.X2N.1.5",
        "Create fast changed-scope gates and full release pipelines using only synthetic data.",
        "ACC.x2n.rel.001",
        "ACC.x2n.rel.002",
        "ACC.x2n.rel.003",
        "CI self-test with seeded failures",
        "artifact allowlist test",
        "fixture leak test",
        "CI requires real secrets or accounts",
        "blocking checks can be silently skipped",
    ):
        _require(token in block, "Foundation005 Task contract drifted")
    acceptance = ACCEPTANCE.read_text(encoding="utf-8")
    for token in (
        "format/lint/type/unit/contract/migration/integration/E2E 全 Pass",
        "Flaky Blocking Test `0`",
        "ASR/OCR/Fusion/Classify/Red Team 均有明确状态",
        "自动分类仅在 ACC.x2n.ai.006 Pass 后开启",
        "Critical/High 未处置漏洞 `0`",
        "Secret/Private/CDN `0`",
        "Unknown License `0`",
        "Runtime Data `0`",
    ):
        _require(token in acceptance, "Foundation005 Acceptance contract drifted")
    run_contract = RUN_CONTRACT.read_text(encoding="utf-8")
    for token in (
        TASK_BASE_COMMIT,
        ORIGIN_CUTOFF,
        "G1=NOT_RUN",
        "不读取、显示、使用、修改、删除或轮换任何共享认证材料",
    ):
        _require(token in run_contract, "Foundation005 Run Contract incomplete")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {"acceptance_ids": 3, "phase": "PH.X2N.1.5", "single_task": True, "stop_conditions": 2},
    )


def validate_ci_policy() -> Check:
    policy = _load_json(CI_POLICY)
    _require(
        policy.get("task_id") == TASK_ID and policy.get("data_class") == "synthetic_only", "CI policy identity drifted"
    )
    _require(
        policy.get("credentials_required") is False and policy.get("blocking_checks_may_skip") is False,
        "CI fail-closed policy weakened",
    )
    optional_skips = policy.get("nonblocking_optional_skips", {})
    _require(optional_skips.get("per_repetition") == 3, "optional skip count drifted")
    _require(
        {row.get("reason"): row.get("count_per_repetition") for row in optional_skips.get("reasons", [])}
        == {
            "owner-private root is intentionally absent in public CI": 2,
            "private source snapshots are intentionally absent in public CI": 1,
        },
        "optional skip allowlist drifted",
    )
    toolchain = policy.get("toolchain", {})
    _require(
        toolchain
        == {
            "python": "3.12",
            "node": "24",
            "npm": "11.16.0",
            "uv": "0.11.28",
            "ruff": "0.15.22",
            "coverage": "7.15.2",
            "pyyaml": "6.0.3",
        },
        "CI toolchain drifted",
    )
    lanes = policy.get("lanes", {})
    fast = set(lanes.get("changed_scope", {}).get("blocking_gates", []))
    full = set(lanes.get("full_release", {}).get("blocking_gates", []))
    _require(
        {
            "format",
            "lint",
            "type",
            "unit",
            "contract",
            "ci_seeded_failure_self_test",
            "fixture_leak",
            "secret_private_cdn",
            "sast",
            "sbom",
            "license",
            "csp",
            "model_eval_contract",
        }
        <= fast,
        "changed-scope blocking gates incomplete",
    )
    _require(
        {
            "migration",
            "integration",
            "extension_e2e",
            "coverage",
            "live_osv",
            "release_artifact_allowlist",
            "determinism_replay",
        }
        <= full,
        "full-release blocking gates incomplete",
    )
    _require(lanes["full_release"].get("blocking_repetitions") == 2, "full-release repetition gate drifted")
    coverage = policy.get("coverage", {})
    _require(
        coverage.get("branch_mode_required") is True and coverage.get("overall_combined_percent_min") == 70.0,
        "coverage policy weakened",
    )
    _require(
        len(coverage.get("critical_module_combined_percent_min", {})) == 7, "critical coverage registry incomplete"
    )
    release = policy.get("release", {})
    _require(
        release
        == {
            "candidate_only": True,
            "g1_gate_source": "machine/facts/stage_1_gate_state.json",
            "remote_workflow_required_before_merge": True,
            "upload_before_g1": False,
        },
        "release policy drifted",
    )
    return Check(
        "ci_policy",
        "PASS",
        {
            "critical_coverage_modules": 7,
            "explicit_nonblocking_skips_per_repetition": 3,
            "fast_blockers": len(fast),
            "full_blockers": len(full),
            "silent_skips": 0,
        },
    )


def validate_workflow() -> Check:
    _require(
        WORKFLOW.is_file() and WORKFLOW.parent == REPOSITORY_ROOT / ".github/workflows",
        "x2n workflow is not root-level",
    )
    text = WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", text)
    allowed = {
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
        "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990",
        "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    }
    _require(
        uses and set(uses) == allowed and all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", item) for item in uses),
        "workflow action pin drifted",
    )
    _require("permissions:\n  contents: read" in text, "workflow permissions are not minimal")
    _require(
        text.count("persist-credentials: false") == text.count("actions/checkout@"),
        "checkout credential persistence not disabled",
    )
    _require(text.count("fetch-depth: 0") == text.count("actions/checkout@"), "full Git history unavailable to gates")
    _require(text.count("NPM_CONFIG_USERCONFIG: /dev/null") == 2, "dependency install user config is not isolated")
    for prohibited in ("continue-on-error", "pull_request_target", "secrets.", "persist-credentials: true"):
        _require(prohibited not in text, "workflow contains prohibited bypass or secret surface")
    for token in (
        "changed-scope:",
        "full-release:",
        "--lane fast --repetitions 1",
        "--lane full --repetitions 2",
        "npm ci --ignore-scripts",
        "uv sync --frozen --all-packages --group ci",
        "if-no-files-found: error",
        '"xhs-douyin-2notion/**"',
    ):
        _require(token in text, "workflow gate or trigger missing")
    _require(text.count("timeout-minutes:") == 3, "workflow job timeout incomplete")
    _require("runs-on: ubuntu-latest" in text and "runs-on: macos-15" in text, "workflow runner split drifted")
    return Check(
        "workflow_security_and_routing",
        "PASS",
        {
            "action_uses": len(uses),
            "full_sha_pins": len(uses),
            "jobs": 3,
            "permissions": "contents_read",
            "secret_references": 0,
        },
    )


def validate_fixtures_and_self_test() -> Check:
    fixture = fixture_guard()
    self_test = run_self_test()
    manifest = _load_json(FIXTURE_MANIFEST)
    rows = manifest.get("fixtures", [])
    frozen_rows = _load_json_at(FINAL_COMMIT, FIXTURE_MANIFEST).get("fixtures", [])
    _require(
        len(frozen_rows) == 8
        and [row.get("id") for row in frozen_rows[-3:]]
        == [
            "FIXTURE.X2N.S01.F005.001",
            "FIXTURE.X2N.S01.F005.002",
            "FIXTURE.X2N.S01.F005.003",
        ],
        "historical Foundation005 fixture registration drifted",
    )
    _require(
        len(rows) >= len(frozen_rows) and rows[: len(frozen_rows)] == frozen_rows,
        "Foundation005 fixture history was modified instead of append-only extended",
    )
    _require(
        self_test.get("silent_skips") == 0 and self_test.get("seeded_failure_categories", 0) >= 8,
        "seeded failure self-test incomplete",
    )
    return Check(
        "fixtures_and_seeded_failures",
        "PASS",
        {
            "change_scope_cases": self_test["change_scope_cases"],
            "registered_fixtures": fixture["registered_fixtures"],
            "seeded_failure_categories": self_test["seeded_failure_categories"],
            "sensitive_fixture_hits": 0,
        },
    )


def _generated_sbom() -> dict[str, Any]:
    path = PROJECT_ROOT / "scripts/generate_foundation_005_sbom.py"
    spec = importlib.util.spec_from_file_location("generate_foundation_005_sbom", path)
    _require(spec is not None and spec.loader is not None, "Foundation005 SBOM generator unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.build_sbom()
    _require(isinstance(value, dict), "Foundation005 SBOM generator returned invalid data")
    return value


def validate_security_supply_chain() -> Check:
    expected = _generated_sbom()
    current = _load_json(SBOM)
    _require(current == expected and len(current.get("components", [])) == 33, "Foundation005 SBOM drifted")
    license_report = validate_license()
    sast, sarif = run_sast()
    _require(sast.get("status") == "PASS" and sast.get("critical_high_findings") == 0, "SAST blocking finding")
    _require(
        sarif.get("version") == "2.1.0" and sarif.get("runs", [{}])[0].get("results") == [], "SARIF result drifted"
    )
    csp = validate_csp()
    for path in (ARTIFACT_POLICY, LICENSE_POLICY):
        _require(path.is_file(), "Foundation005 security policy missing")
    with tempfile.TemporaryDirectory(prefix="x2n-f005-artifact-") as value:
        first = Path(value) / "first.zip"
        second = Path(value) / "second.zip"
        first_report = build_artifact(first)
        second_report = build_artifact(second)
        _require(
            first_report["artifact_sha256"] == second_report["artifact_sha256"],
            "release candidate is not deterministic",
        )
    return Check(
        "security_supply_chain_and_artifact",
        "PASS",
        {
            "artifact_members": first_report["member_count"],
            "artifact_runtime_data": 0,
            "csp_remote_resources": csp["remote_resources"],
            "licenses_unknown": license_report["unknown_licenses"],
            "sast_critical_high": 0,
            "sbom_components": len(current["components"]),
        },
    )


def validate_model_baseline() -> Check:
    report = validate_model_dataset(MODEL_FIXTURE)
    _require(
        report.get("model_calls") == 0 and report.get("status") == "PASS_BASELINE_SKELETON", "model baseline overstated"
    )
    _require(
        report.get("automatic_classification") == "DISABLED_PENDING_ACC.x2n.ai.006",
        "automatic classification enabled early",
    )
    card = MODEL_CARD.read_text(encoding="utf-8")
    for token in (
        "NOT_RUN_FEATURE_DISABLED",
        "CONTRACT_PASS_MODEL_NOT_RUN",
        "ACC.x2n.ai.006",
        "AI 永远不得创建一级分类",
        "模型调用 0",
    ):
        _require(token in card, "Model System Card incomplete")
    return Check(
        "model_eval_baseline",
        "PASS",
        {
            "dataset_contract": "PASS",
            "disabled_capabilities": 4,
            "model_calls": 0,
            "red_team_model_execution": "NOT_RUN",
        },
    )


def validate_state_and_truthfulness() -> Check:
    state = _load_json_at(STAGE_1_REVIEW_COMMIT, TASK_STATE)
    _require(
        state.get("schema_version") == "1.8" and state.get("last_completed_phase") == "PH.X2N.1.5",
        "task state phase drifted",
    )
    _require(
        state.get("tasks", {}).get(TASK_ID) == "pass"
        and state.get("run_id") == "RUN-X2N-S01-REVIEW"
        and state.get("review_id") == "STG.X2N.1.REVIEW",
        "Foundation005 Task state missing",
    )
    expected_acceptance = {
        "ACC.x2n.rel.001": "pass_local_synthetic_pipeline_g1_pass_remote_ci_pending_post_upload",
        "ACC.x2n.rel.002": "pass_runner_dataset_contract_capabilities_disabled_model_not_run",
        "ACC.x2n.rel.003": "pass_local_current_locks_candidate_history_scans_g1_pass_remote_release_not_run",
    }
    _require(
        all(state.get("acceptance_status", {}).get(key) == value for key, value in expected_acceptance.items()),
        "Foundation005 Acceptance scope drifted",
    )
    _require(
        state.get("next_run") == "TSK.x2n.skeleton.001" and state.get("current_stage_gate") == "pass",
        "next route or G1 state drifted",
    )
    _require(state.get("current_stage_remote_upload") == "authorized_after_g1_pass", "Stage 1 upload gate drifted")
    _require(state.get("remote_ci_execution") == "pending_post_g1_upload", "remote CI status overstated")
    for field in (
        "real_account_execution",
        "platform_calls",
        "notion_calls",
        "model_calls",
        "media_processing",
        "real_sink_execution",
    ):
        _require(state.get(field) == "not_run", f"downstream execution overstated: {field}")
    project = _load_json_at(STAGE_1_REVIEW_COMMIT, PROJECT_FACT)
    architecture = _load_json_at(STAGE_1_REVIEW_COMMIT, ARCHITECTURE_FACT)
    gate = _load_json(G1_FACT)
    _require(project.get("status") == "stage_1_review_pass_g1_pass_stage_2_authorized", "project status drifted")
    _require(
        architecture.get("phase") == "PH.X2N.1.5"
        and architecture.get("stage_gate") == "g1_pass"
        and gate.get("gate_status") == "pass",
        "architecture status drifted",
    )
    return Check(
        "state_and_truthfulness",
        "PASS",
        {
            "current_g1": "PASS",
            "g1_at_task_completion": "NOT_RUN",
            "next_run": "TSK.x2n.skeleton.001",
            "platform_calls": 0,
            "remote_actions_at_task_completion": "NOT_RUN",
        },
    )


def validate_lane_report(path: Path) -> Check:
    report = _load_json(path)
    _require(report.get("status") == "PASS" and report.get("lane") == "full", "full lane report missing or failed")
    for field in (
        "blocking_failures",
        "flaky_blocking_tests",
        "silent_blocking_skips",
        "model_calls",
        "platform_calls",
        "real_accounts",
    ):
        _require(report.get(field) == 0, f"full lane blocker or prohibited execution: {field}")
    _require(
        report.get("blocking_repetitions") == 2 and report.get("blocking_executions", 0) >= 24,
        "full lane repetition evidence incomplete",
    )
    expected_results = [
        {
            "blocking": True,
            "gate": gate,
            "label": f"{gate}_r{repetition}",
            "repetition": repetition,
            "status": "PASS",
        }
        for repetition in (1, 2)
        for gate in EXPECTED_BLOCKING_GATES
    ]
    _require(report.get("blocking_results") == expected_results, "full lane execution identity drifted")
    _require(report.get("explicit_nonblocking_skips") == 6, "explicit optional skip evidence drifted")
    _require(report.get("artifact_deterministic") is True, "artifact determinism evidence missing")
    _require(report.get("coverage", {}).get("branch_mode") is True, "coverage branch evidence missing")
    _require(len(report.get("coverage", {}).get("critical_modules", {})) == 7, "critical coverage evidence incomplete")
    _require(report.get("osv", {}).get("critical_high_unresolved") == 0, "OSV evidence missing")
    _require(
        report.get("remote_github_actions") == "NOT_RUN_LOCAL_BASELINE"
        and report.get("stage_gate_evaluation") == "NOT_PERFORMED_BY_SOFTWARE_LANE"
        and "g1" not in report,
        "software lane overstated a remote or dynamic stage-gate decision",
    )
    toolchain = report.get("toolchain", {})
    expected_toolchain = _load_json(CI_POLICY).get("toolchain", {})
    actual_toolchain = toolchain.get("actual", {})
    _require(
        toolchain.get("status") == "PASS"
        and toolchain.get("policy_id") == "CI.X2N.001"
        and toolchain.get("policy_sha256") == hashlib.sha256(CI_POLICY.read_bytes()).hexdigest()
        and toolchain.get("expected") == expected_toolchain
        and ".".join(str(actual_toolchain.get("python", "")).split(".")[:2]) == expected_toolchain.get("python")
        and str(actual_toolchain.get("node", "")).split(".")[0] == expected_toolchain.get("node")
        and all(
            actual_toolchain.get(name) == expected_toolchain.get(name)
            for name in ("npm", "uv", "ruff", "coverage", "pyyaml")
        ),
        "software lane toolchain identity drifted",
    )
    artifact = path.parent / "x2n-source-candidate.zip"
    _require(
        artifact.is_file()
        and hashlib.sha256(artifact.read_bytes()).hexdigest() == report["artifact_report"]["artifact_sha256"],
        "lane artifact evidence drifted",
    )
    return Check(
        "local_full_lane",
        "PASS",
        {
            "blocking_executions": report["blocking_executions"],
            "blocking_failures": 0,
            "blocking_repetitions": 2,
            "explicit_nonblocking_skips": 6,
            "flaky_blocking_tests": 0,
            "remote_github_actions": "NOT_RUN",
            "silent_blocking_skips": 0,
        },
    )


def run_checks(
    *, verify_worktree: bool, allow_external_main_dirty: bool, lane_report: Path | None = None
) -> list[Check]:
    checks = [
        validate_task_contract(),
        validate_ci_policy(),
        validate_workflow(),
        validate_fixtures_and_self_test(),
        validate_security_supply_chain(),
        validate_model_baseline(),
        validate_state_and_truthfulness(),
        validate_scope_and_privacy(),
    ]
    if verify_worktree:
        checks.append(validate_worktree(allow_external_main_dirty))
    if lane_report is not None:
        checks.append(validate_lane_report(lane_report))
    return checks


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "/home/" not in rendered, "evidence contains a local absolute path")
    _require(re.search(r"https?://", rendered) is None, "evidence contains a URL")
    _require(
        "github" + "_pat_" not in rendered and "ghp" + "_" not in rendered,
        "evidence contains credential-shaped material",
    )
    _require(
        re.search(r"(?i)(?:xhs.?cdn|douyin.?vod|byteimg|pstatp|bilivideo|kscdn|alicdn)", rendered) is None,
        "evidence contains CDN material",
    )


def write_evidence(checks: list[Check], lane_report_path: Path) -> None:
    lane = _load_json(lane_report_path)
    _require(any(check.name == "local_full_lane" for check in checks), "evidence requires local full lane")
    model = validate_model_dataset()
    payload = {
        "acceptance_ids": ["ACC.x2n.rel.001", "ACC.x2n.rel.002", "ACC.x2n.rel.003"],
        "acceptance_status": {
            "ACC.x2n.rel.001": "PASS_LOCAL_SYNTHETIC_PIPELINE_REMOTE_CI_G1_NOT_RUN",
            "ACC.x2n.rel.002": "PASS_DATASET_RUNNER_SKELETON_CAPABILITIES_DISABLED_MODEL_NOT_RUN",
            "ACC.x2n.rel.003": "PASS_LOCAL_LOCK_AND_CANDIDATE_SCANS_REMOTE_RELEASE_NOT_RUN",
        },
        "artifact": {
            "deterministic": lane["artifact_deterministic"],
            "member_count": lane["artifact_report"]["member_count"],
            "runtime_data_files": lane["artifact_report"]["runtime_data_files"],
            "sha256": lane["artifact_report"]["artifact_sha256"],
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "coverage": lane["coverage"],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "g1": "NOT_RUN",
        "model_evaluation": model,
        "osv": lane["osv"],
        "phase": "PH.X2N.1.5",
        "private_content_included": False,
        "real_account_execution": "NOT_RUN",
        "remote_github_actions": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_G1_PASS",
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.1",
        "status": "PASS",
        "task_id": TASK_ID,
    }
    _safe_evidence(payload)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(evidence.get("status") == "PASS" and evidence.get("g1") == "NOT_RUN", "evidence status overstated")
    _require(
        evidence.get("remote_github_actions") == "NOT_RUN"
        and evidence.get("remote_upload") == "FORBIDDEN_UNTIL_G1_PASS",
        "remote state overstated",
    )
    _require(evidence.get("model_evaluation", {}).get("model_calls") == 0, "model execution overstated")
    _require(
        all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check"
    )
    return Check(
        "evidence", "PASS", {"receipt_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), "task": TASK_ID}
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.foundation.005")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--lane-report", type=Path)
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            lane_report=args.lane_report,
        )
        if args.write_evidence:
            _require(args.lane_report is not None, "--write-evidence requires --lane-report")
            write_evidence(checks, args.lane_report)
        if args.require_evidence:
            checks.append(verify_evidence())
        print(
            json.dumps(
                {
                    "checks": [{"name": item.name, "status": item.status} for item in checks],
                    "current_g1": "PASS",
                    "current_remote_github_actions": "PENDING_POST_G1_UPLOAD",
                    "g1": "NOT_RUN",
                    "remote_github_actions": "NOT_RUN",
                    "status": "PASS",
                    "task": TASK_ID,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (BaselineError, OSError, ValueError, VerificationError) as error:
        print(
            json.dumps(
                {"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID}, ensure_ascii=False, sort_keys=True
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
