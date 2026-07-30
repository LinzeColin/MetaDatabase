#!/usr/bin/env python3
"""Fail-closed verifier for Stage 6.2 model assurance."""

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.assurance.002"
PHASE = "PH.X2N.6.2"
RUN_ID = "RUN-X2N-S06-A002"
TASK_BASE_COMMIT = "bc9bd26d425bcee524981d74fa89d2315d966ec8"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
ASSURANCE_FACT = PROJECT_ROOT / "machine/facts/stage_6_assurance_002_state.json"
ASSURANCE_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_6_assurance_002_state.schema.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S06_ASSURANCE_002.md"
REPORT = PROJECT_ROOT / "docs/governance/STAGE_6_ASSURANCE_002.md"
SYSTEM_CARD = PROJECT_ROOT / "docs/model/MODEL_SYSTEM_CARD_S06_A002.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_assurance_002_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/models/TSK.x2n.assurance.002.json"
POLICY = PROJECT_ROOT / "machine/policy/ci_gate_manifest.json"

EXPECTED_ACCEPTANCES = {
    "ACC.x2n.ai.001": "PASS_CI_SYNTH_FEATURE_GATE_ASR_DISABLED_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.002": "PASS_CI_SYNTH_FEATURE_GATE_OCR_DISABLED_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.003": "PASS_CI_SYNTH_FEATURE_GATE_VISION_DISABLED_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.004": "PASS_CI_SYNTH_FUSION_RED_TEAM_SCHEMA_ISOLATION_MODEL_NOT_RUN",
    "ACC.x2n.ai.005": "PASS_CI_SYNTH_OWNER_TAXONOMY_GUARD_SUGGESTION_ONLY",
    "ACC.x2n.ai.006": "PASS_CI_SYNTH_FEATURE_GATE_CLASSIFICATION_SUGGESTION_ONLY_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.007": "PASS_CI_SYNTH_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO",
    "ACC.x2n.rel.002": "PASS_CI_SYNTH_MODEL_PIPELINE_FEATURES_DISABLED_PRIVATE_GOLD_NOT_RUN",
}
EXPECTED_EXECUTION = {
    "cloud_uploads": 0,
    "config_writes": 0,
    "model_calls": 0,
    "network_calls": 0,
    "platform_calls": 0,
    "private_gold_evaluation": "NOT_RUN",
    "real_account_execution": "NOT_RUN",
    "secret_reads": 0,
    "tool_calls": 0,
}
EXPECTED_FEATURE_GATES = {
    "asr": "DISABLED_PENDING_PRIVATE_GOLD",
    "automatic_classification": "DISABLED_PENDING_ACC.x2n.ai.006",
    "classification": "SUGGESTION_ONLY_PENDING_PRIVATE_GOLD",
    "fusion": "DISABLED_MODEL_NOT_RUN",
    "ocr": "DISABLED_PENDING_PRIVATE_GOLD",
    "vision": "DISABLED_PENDING_PRIVATE_GOLD",
}
EXPECTED_REPORTS = {
    "asr": "NOT_RUN_PRIVATE_GOLD",
    "classification": "SUGGESTION_ONLY_PENDING_PRIVATE_GOLD",
    "cross_model_disagreement": "NOT_RUN_FEATURES_DISABLED",
    "fusion": "PASS_CI_SYNTH_SCHEMA_AND_ISOLATION_MODEL_NOT_RUN",
    "ocr": "NOT_RUN_PRIVATE_GOLD",
    "system_card": "UPDATED_FEATURES_DISABLED",
    "vision": "NOT_RUN_PRIVATE_GOLD",
}
SOURCE_CHANGED_PATHS = (
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "docs/governance/RUN_CONTRACT_S06_ASSURANCE_002.md",
    "docs/governance/STAGE_6_ASSURANCE_002.md",
    "docs/model/MODEL_SYSTEM_CARD_S06_A002.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/stage_6_assurance_002_state.json",
    "machine/facts/task_state.json",
    "machine/policy/ci_gate_manifest.json",
    "machine/schemas/stage_6_assurance_002_state.schema.json",
    "scripts/run_assurance_002_acceptance.py",
    "scripts/verify_assurance_002.py",
    "tests/test_assurance_002.py",
    "功能清单.md",
    "开发记录.md",
)
SOURCE_CHANGED_EXACT = frozenset(SOURCE_CHANGED_PATHS)
CURRENT_ALLOWED_EXACT = SOURCE_CHANGED_EXACT | {EVIDENCE.relative_to(PROJECT_ROOT).as_posix()}
PLATFORM_CDN_PATTERN = re.compile(
    "|".join(re.escape("".join(parts)) for parts in (("xhs", "cdn"), ("douyin", "vod"), ("bili", "video"))),
    re.I,
)


class Assurance002VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance002VerificationError(message)


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
        raise Assurance002VerificationError("local Git verification failed")
    return result.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Assurance002VerificationError(f"invalid JSON: {path.name}") from error
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _taskpack() -> dict[str, Any]:
    try:
        value = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise Assurance002VerificationError("Taskpack is unreadable") from error
    _require(isinstance(value, dict), "Taskpack must be an object")
    return value


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
    if result.returncode != 0:
        raise Assurance002VerificationError("historical source blob is missing")
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
    return [item for item in _git(("diff", "--name-only", "-z", f"{start}..{end}")).split("\0") if item]


def _validate_scope(start: str, end: str, *, allow_evidence: bool) -> int:
    changed = _changed_paths(start, end)
    _require(changed, "assurance002 source scope is empty")
    prefix = "xhs-douyin-2notion/"
    relative = [item.removeprefix(prefix) for item in changed]
    _require(all(item.startswith(prefix) for item in changed), "assurance002 scope escaped x2n")
    allowed = CURRENT_ALLOWED_EXACT if allow_evidence else SOURCE_CHANGED_EXACT
    _require(set(relative) <= allowed, "assurance002 scope contains an unapproved change")
    return len(relative)


def _json_line(output: str) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    _require(payloads, "assurance002 acceptance emitted no JSON receipt")
    return payloads[-1]


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(("rev-parse", "--show-toplevel"))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(("branch", "--show-current"))
    _require(branch not in {"", "main"}, "assurance002 must run in a non-main worktree")
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
        "assurance002 does not descend from assurance001",
    )
    return Check("worktree_isolation", "PASS", {"branch": branch, "external_main_dirty_paths": len(main_paths)})


def validate_transition_and_facts() -> Check:
    tasks = {item.get("id"): item for item in _taskpack().get("tasks", []) if isinstance(item, dict)}
    task = tasks.get(TASK_ID)
    _require(
        isinstance(task, dict)
        and task.get("stage") == "STG.X2N.6"
        and task.get("phase") == PHASE
        and task.get("status") == "complete_ci_synth_features_disabled"
        and tuple(task.get("acceptance_ids", [])) == tuple(EXPECTED_ACCEPTANCES),
        "Taskpack assurance002 transition drifted",
    )
    next_task = tasks.get("TSK.x2n.assurance.003")
    _require(
        isinstance(next_task, dict) and next_task.get("phase") == "PH.X2N.6.3" and next_task.get("status") == "planned",
        "next Task authorization drifted",
    )
    state = _load_json(TASK_STATE)
    expected_status = "stage_6_assurance002_ci_synth_features_disabled_assurance003_next_real_runtime_not_run"
    _require(
        state.get("schema_version") == "1.43"
        and state.get("phase") == PHASE
        and state.get("last_completed_phase") == PHASE
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "single_dag_task_ci_synth_model_assurance_features_disabled"
        and state.get("state") == expected_status
        and state.get("tasks", {}).get(TASK_ID) == "pass"
        and all(state.get("acceptance_status", {}).get(key) == value for key, value in EXPECTED_ACCEPTANCES.items())
        and state.get("next_task") == "TSK.x2n.assurance.003"
        and state.get("next_phase") == "PH.X2N.6.3"
        and state.get("stage_6_task002_complete") is True
        and state.get("stage_6_task003_authorized") is True
        and state.get("public_release_authorized") is False,
        "Task State assurance002 transition is invalid",
    )
    schema = _load_json(ASSURANCE_SCHEMA)
    fact = _load_json(ASSURANCE_FACT)
    _require(
        schema.get("$id") == "urn:x2n:stage-6-assurance-002-state:1.0"
        and fact.get("schema_version") == "1.0"
        and fact.get("project") == "x2n"
        and fact.get("stage") == "STG.X2N.6"
        and fact.get("task_id") == TASK_ID
        and fact.get("phase") == PHASE
        and fact.get("run_id") == RUN_ID
        and fact.get("task_base_commit") == TASK_BASE_COMMIT
        and fact.get("status") == "PASS_CI_SYNTH_MODEL_ASSURANCE_FEATURES_DISABLED_PRIVATE_GOLD_NOT_RUN"
        and fact.get("acceptance_status") == EXPECTED_ACCEPTANCES
        and fact.get("execution") == EXPECTED_EXECUTION
        and fact.get("feature_gates") == EXPECTED_FEATURE_GATES
        and fact.get("private_gold") == {"accessed": False, "quality_claim": "NONE", "status": "NOT_RUN_BY_CI_SYNTH"}
        and fact.get("next_task") == {"id": "TSK.x2n.assurance.003", "phase": "PH.X2N.6.3", "status": "PLANNED"},
        "assurance002 fact drifted",
    )
    _safe_payload(fact)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    _require(
        project.get("schema_version") == "1.7"
        and project.get("status") == expected_status
        and project.get("stage_6_current_task")
        == "assurance002_ci_synth_features_disabled_assurance003_next_real_runtime_not_run",
        "project fact overclaims model capability",
    )
    decisions = architecture.get("decisions")
    adr = next((item for item in decisions if isinstance(item, dict) and item.get("id") == "ADR-023"), None)
    _require(
        architecture.get("schema_version") == "1.7"
        and architecture.get("phase") == PHASE
        and architecture.get("status") == expected_status
        and architecture.get("stage_gate")
        == "g5_pass_assurance001_pass_assurance002_features_disabled_assurance003_authorized"
        and isinstance(adr, dict)
        and adr.get("topic") == "stage_6_model_assurance_explicit_feature_disabled_decision"
        and adr.get("state") == "accepted_implementation",
        "architecture fact overclaims model capability",
    )
    return Check("taskpack_state_and_fact_transition", "PASS", {"next_task": "TSK.x2n.assurance.003"})


def validate_model_boundary() -> Check:
    policy = _load_json(POLICY)
    flags = policy.get("model_features")
    _require(
        isinstance(flags, dict)
        and flags.get("asr") is False
        and flags.get("ocr") is False
        and flags.get("vision") is False
        and flags.get("fusion") is False
        and flags.get("classification") is False
        and flags.get("automatic_classification") is False
        and flags.get("automatic_classification_gate") == "ACC.x2n.ai.006",
        "model feature boundary drifted",
    )
    for control in (RUN_CONTRACT, REPORT, SYSTEM_CARD, ACCEPTANCE_RUNNER):
        _require(
            control.is_file() and control.stat().st_size <= 2 * 1024 * 1024, "assurance control missing or oversized"
        )
        _safe_payload({"control": control.read_text(encoding="utf-8")})
    card = SYSTEM_CARD.read_text(encoding="utf-8")
    _require(
        "NOT_RUN" in card
        and "auto_classify=false" in card
        and "TSK.x2n.assurance.005" in card
        and "Alpha" in card
        and "soak" in card,
        "System Card boundary drifted",
    )
    runner = ACCEPTANCE_RUNNER.read_text(encoding="utf-8")
    _require(
        "MISSING_PRIVATE_GOLD_ACTIONS" in runner
        and "model_contract_redteam" in runner
        and "private_gold_evaluation" in runner
        and "scan_source" in runner,
        "model assurance runner drifted",
    )
    return Check("model_boundary_and_system_card", "PASS", {"model_features_enabled": 0, "quality_claim": "NONE"})


def validate_fresh_acceptance() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a002-verify-") as temporary:
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
            timeout=900,
        )
    _require(result.returncode == 0, "fresh model assurance acceptance failed")
    receipt = _json_line(result.stdout)
    pipeline = receipt.get("pipeline")
    _require(
        receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("run_id") == RUN_ID
        and receipt.get("status") == "PASS_CI_SYNTH_MODEL_ASSURANCE_FEATURES_DISABLED_PRIVATE_GOLD_NOT_RUN"
        and receipt.get("acceptance_status") == EXPECTED_ACCEPTANCES
        and receipt.get("execution") == EXPECTED_EXECUTION
        and receipt.get("feature_gates") == EXPECTED_FEATURE_GATES
        and isinstance(pipeline, dict)
        and pipeline.get("blocking_failures") == 0
        and pipeline.get("blocking_skips") == 0
        and pipeline.get("flaky_blocking_tests") == 0
        and pipeline.get("missing_private_gold", {}).get("safe_failures") == 4
        and pipeline.get("source_scan", {}).get("finding_count") == 0,
        "fresh model assurance acceptance receipt drifted",
    )
    return Check(
        "fresh_ci_synth_model_assurance",
        "PASS",
        {"model_contract_tests": pipeline["model_contract_redteam"]["tests"], "private_gold_reads": 0},
    )


def validate_evidence_and_scope() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_payload(evidence)
    task_commit = evidence.get("task_commit")
    _require(
        isinstance(task_commit, str) and re.fullmatch(r"[0-9a-f]{40}", task_commit) is not None,
        "assurance002 task commit is invalid",
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
        "assurance002 task commit ancestry is invalid",
    )
    _require(
        _validate_scope(TASK_BASE_COMMIT, task_commit, allow_evidence=False) >= len(SOURCE_CHANGED_EXACT),
        "source scope incomplete",
    )
    current_paths = _validate_scope(TASK_BASE_COMMIT, "HEAD", allow_evidence=True)
    _require(
        evidence
        == {
            "acceptance_status": EXPECTED_ACCEPTANCES,
            "execution": EXPECTED_EXECUTION,
            "feature_gates": EXPECTED_FEATURE_GATES,
            "model_reports": EXPECTED_REPORTS,
            "phase": PHASE,
            "private_gold": {"accessed": False, "quality_claim": "NONE", "status": "NOT_RUN_BY_CI_SYNTH"},
            "run_id": RUN_ID,
            "schema_version": "1.0",
            "source_receipt_sha256": _source_receipt(task_commit),
            "status": "PASS_CI_SYNTH_MODEL_ASSURANCE_FEATURES_DISABLED_PRIVATE_GOLD_NOT_RUN",
            "task_base_commit": TASK_BASE_COMMIT,
            "task_commit": task_commit,
            "task_id": TASK_ID,
        },
        "assurance002 evidence receipt drifted",
    )
    return Check("assurance_evidence_and_scope", "PASS", {"current_paths": current_paths, "task_source": "verified"})


def run_checks(
    *, verify_worktree: bool, allow_external_main_dirty: bool, run_acceptance: bool, require_evidence: bool
) -> list[Check]:
    checks = [validate_transition_and_facts(), validate_model_boundary()]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_fresh_acceptance())
    if require_evidence:
        checks.append(validate_evidence_and_scope())
    _require(all(check.status == "PASS" for check in checks), "assurance002 verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify x2n Stage 6 Assurance002")
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
    except (OSError, Assurance002VerificationError, subprocess.SubprocessError, yaml.YAMLError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
