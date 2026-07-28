#!/usr/bin/env python3
"""Fail-closed verifier for taxonomy, constrained classification and review (Task005)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.multimodal.005"
PHASE = "PH.X2N.4.5"
RUN_ID = "RUN-X2N-S04-M005"
TASK_BASE_COMMIT = "0c2eb423c3dffea8a5305d3ce0640c7abb7935b4"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_005.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_multimodal_005_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/models/TSK.x2n.multimodal.005.json"
G4_REVIEW_ID = "STG.X2N.4.REVIEW"

SOURCE_RECEIPT_PATHS = (
    PROJECT_ROOT / "CHANGELOG.md",
    PROJECT_ROOT / "HANDOFF.md",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/taxonomy.py",
    PROJECT_ROOT / "apps/companion/tests/test_adapter_dispatch.py",
    PROJECT_ROOT / "apps/companion/tests/test_taxonomy.py",
    PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs",
    PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_005.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/00_PRFAQ.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/01_PRD.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md",
    TASKPACK,
    ARCHITECTURE,
    PROJECT_FACT,
    TASK_STATE,
    ACCEPTANCE_RUNNER,
    PROJECT_ROOT / "scripts/verify_adapters_010.py",
    PROJECT_ROOT / "scripts/verify_multimodal_001.py",
    PROJECT_ROOT / "scripts/verify_multimodal_002.py",
    PROJECT_ROOT / "scripts/verify_multimodal_003.py",
    PROJECT_ROOT / "scripts/verify_multimodal_004.py",
    PROJECT_ROOT / "scripts/verify_multimodal_005.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume_recheck.py",
    PROJECT_ROOT / "tests/test_adapters_010.py",
    PROJECT_ROOT / "功能清单.md",
    PROJECT_ROOT / "开发记录.md",
)

ALLOWED_CHANGED_EXACT = frozenset(
    {
        "CHANGELOG.md",
        "HANDOFF.md",
        "README.md",
        "apps/companion/src/x2n_companion/canonical_store.py",
        "apps/companion/src/x2n_companion/migrations.py",
        "apps/companion/src/x2n_companion/runtime_cli.py",
        "apps/companion/src/x2n_companion/taxonomy.py",
        "apps/companion/tests/test_adapter_dispatch.py",
        "apps/companion/tests/test_taxonomy.py",
        "apps/extension/scripts/extension-e2e.mjs",
        "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_005.md",
        "docs/product_design/v0.0.0.1/00_PRFAQ.md",
        "docs/product_design/v0.0.0.1/01_PRD.md",
        "docs/product_design/v0.0.0.1/02_ROADMAP.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "evidence/models/TSK.x2n.multimodal.005.json",
        "machine/facts/architecture_decisions.json",
        "machine/facts/project.json",
        "machine/facts/task_state.json",
        "scripts/run_multimodal_005_acceptance.py",
        "scripts/verify_adapters_010.py",
        "scripts/verify_multimodal_001.py",
        "scripts/verify_multimodal_002.py",
        "scripts/verify_multimodal_003.py",
        "scripts/verify_multimodal_004.py",
        "scripts/verify_multimodal_005.py",
        "scripts/verify_stage_3_review_resume.py",
        "scripts/verify_stage_3_review_resume_recheck.py",
        "tests/test_adapters_010.py",
        "功能清单.md",
        "开发记录.md",
    }
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
        raise VerificationError("local Git verification failed")
    return result.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError("required JSON fact is invalid") from error
    if not isinstance(payload, dict):
        raise VerificationError("required JSON fact must be an object")
    return payload


def _task_commit() -> str:
    evidence = _load_json(EVIDENCE)
    commit = evidence.get("task_commit")
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task005 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "Task005 audit pin does not descend from Task004 evidence pin",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task005 audit pin",
    )
    return commit


def _blob_at(commit: str, path: Path) -> bytes:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError("Task005 historical source blob is missing")
    return result.stdout


def _source_receipt(commit: str) -> str:
    digest = hashlib.sha256()
    for path in SOURCE_RECEIPT_PATHS:
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_blob_at(commit, path))
        digest.update(b"\0")
    return digest.hexdigest()


def _changed_paths(commit: str) -> list[str]:
    values = _git(["diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..{commit}"])
    return sorted(path for path in values.split("\0") if path)


def _task_relative(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    return path.removeprefix(prefix) if path.startswith(prefix) else None


def _safety_scan(paths: Iterable[Path], *, commit: str) -> None:
    forbidden_literals = ("Agent" + "Database", "OpenAI" + "Database", "github" + "_pat_", "Bearer" + " ")
    private_path = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
    cdn = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|(?:img|gw|video|vod|pic|media)\.alicdn)",
        flags=re.IGNORECASE,
    )
    for path in paths:
        text = _blob_at(commit, path).decode("utf-8", errors="replace")
        _require(not any(item in text for item in forbidden_literals), "Task005 public boundary violated")
        _require(private_path.search(text) is None, "Task005 local path entered public source")
        _require(cdn.search(text) is None, "Task005 media CDN URL entered public source")


def validate_scope_and_boundary() -> Check:
    commit = _task_commit()
    changed = _changed_paths(commit)
    relative = [_task_relative(path) for path in changed]
    _require(changed and all(path is not None for path in relative), "Task005 change escaped the child project")
    scoped = [path for path in relative if path is not None]
    _require(all(path in ALLOWED_CHANGED_EXACT for path in scoped), "Task005 contains an out-of-scope change")
    files = [PROJECT_ROOT / path for path in scoped if (PROJECT_ROOT / path).is_file()]
    _safety_scan(files, commit=commit)
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}
    _require(
        not any(Path(path).suffix.lower() in forbidden_suffixes for path in scoped),
        "Task005 Runtime media or database entered public source",
    )
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {"changed_files": len(scoped), "platform_cdn_urls": 0, "runtime_media_files": 0},
    )


def _load_task() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError("Taskpack is unreadable") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise VerificationError("Taskpack is invalid")
    matches = [item for item in payload["tasks"] if isinstance(item, dict) and item.get("id") == TASK_ID]
    _require(len(matches) == 1, "Task005 is missing or duplicated")
    return matches[0]


def _stage4_review_completed(state: dict[str, Any]) -> bool:
    """Accept a later G4 receipt without rewriting Task005's own receipt."""

    return (
        state.get("stage_4_review_complete") is True
        and state.get("stage_4_review_id") == G4_REVIEW_ID
        and state.get("stage_4_gate_status") == "pass_ci_synth"
        and state.get("stage_4_remote_upload_authorized") is False
        and state.get("stage_5_authorized") is True
        and state.get("public_release_authorized") is False
    )


def _stage5_task001_completed(state: dict[str, Any]) -> bool:
    return (
        _stage4_review_completed(state)
        and state.get("tasks", {}).get("TSK.x2n.uxops.001") == "pass"
        and state.get("last_completed_phase") == "PH.X2N.5.1"
        and state.get("run_id") == "RUN-X2N-S05-U001"
        and state.get("state") == "stage_5_task001_notion_projection_ci_synth_pass_task002_next_real_notion_not_run"
        and state.get("next_run") == "TSK.x2n.uxops.002"
        and state.get("stage_5_task001_complete") is True
        and state.get("stage_5_remote_upload_authorized") is False
    )


def validate_task_and_transition() -> Check:
    task = _load_task()
    state = _load_json(TASK_STATE)
    _require(
        task.get("status") == "completed"
        and task.get("stage") == "STG.X2N.4"
        and task.get("phase") == PHASE
        and task.get("depends_on") == ["TSK.x2n.multimodal.004", "TSK.x2n.foundation.002"]
        and task.get("acceptance_ids") == ["ACC.x2n.ai.005", "ACC.x2n.ai.006", "ACC.x2n.ai.007"],
        "Task005 contract drifted",
    )
    g4_completed = _stage4_review_completed(state)
    _require(
        g4_completed
        or (
            state.get("stage") == "STG.X2N.4"
            and state.get("last_completed_phase") == PHASE
            and state.get("run_id") == RUN_ID
            and state.get("run_kind") == "single_dag_task_ci_synth_owner_taxonomy_classifier_private_gold_pending"
            and all(
                state.get("tasks", {}).get(task_id) == "pass"
                for task_id in (
                    "TSK.x2n.multimodal.001",
                    "TSK.x2n.multimodal.002",
                    "TSK.x2n.multimodal.003",
                    "TSK.x2n.multimodal.004",
                    TASK_ID,
                )
            )
            and state.get("next_phase") == "G4"
            and state.get("next_run") == "G4"
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "review_pending"
            and state.get("current_stage_gate") == "review_pending"
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("remote_upload") == "not_required_for_local_stage_transition"
        ),
        "Task005 state transition is invalid",
    )
    statuses = state.get("acceptance_status", {})
    _require(
        statuses.get("ACC.x2n.ai.001") == "pending_private_gold_asr_disabled_ci_synth_contract_pass"
        and statuses.get("ACC.x2n.ai.002") == "pending_private_gold_ocr_disabled_ci_synth_contract_pass"
        and statuses.get("ACC.x2n.ai.003") == "pending_private_gold_vision_disabled_ci_synth_contract_pass"
        and statuses.get("ACC.x2n.ai.004") == "pass_ci_synth_fusion_schema_injection_isolation_model_not_run"
        and statuses.get("ACC.x2n.ai.005") == "pass_ci_synth_owner_taxonomy_registry_revision_review_suggestion_only"
        and statuses.get("ACC.x2n.ai.006") == "pending_private_gold_classification_suggestion_only_ci_contract_pass"
        and statuses.get("ACC.x2n.ai.007") == "pass_ci_synth_task005_provenance_cache_budget_cloud_zero",
        "Task005 acceptance state is invalid",
    )
    return Check(
        "taskpack_and_stage4_transition",
        "PASS",
        {
            "completed_task": TASK_ID,
            "next_task": "TSK.x2n.uxops.002" if _stage5_task001_completed(state) else "TSK.x2n.uxops.001" if g4_completed else "G4",
            "automatic_classification": "DISABLED_PENDING_PRIVATE_GOLD",
        },
    )


def validate_implementation_shape() -> Check:
    taxonomy = (PROJECT_ROOT / "apps/companion/src/x2n_companion/taxonomy.py").read_text(encoding="utf-8")
    store = (PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py").read_text(encoding="utf-8")
    migrations = (PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py").read_text(encoding="utf-8")
    cli = (PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py").read_text(encoding="utf-8")
    tests = (PROJECT_ROOT / "apps/companion/tests/test_taxonomy.py").read_text(encoding="utf-8")
    required = (
        "class TaxonomyRegistry",
        "class TaxonomySnapshot",
        "class ConstrainedClassifier",
        "class ClassificationEvaluator",
        "class AutoClassificationGate",
        "class OwnerReviewService",
        "def load_private_classification_gold_dataset",
        "__getstate__",
    )
    _require(all(token in taxonomy for token in required), "Task005 taxonomy implementation is incomplete")
    _require(
        all(token not in taxonomy for token in ("requests.", "httpx", "sqlite3", "subprocess")),
        "Task005 taxonomy implementation crossed its no-network/no-Store boundary",
    )
    classifier = taxonomy[taxonomy.index("class ConstrainedClassifier") : taxonomy.index("class ClassificationGoldCase")]
    _require(
        "TaxonomyRegistry" not in classifier and "CanonicalStore" not in classifier and "open(" not in classifier,
        "classifier retains a taxonomy mutation or file route",
    )
    _require(
        "taxonomy_revision" in migrations
        and "taxonomy_category_no_delete" in migrations
        and "taxonomy_revision_no_update" in migrations
        and "taxonomy_revision_no_delete" in migrations
        and "def append_classification" in store
        and "cannot supersede another content item" in store,
        "Task005 append-only taxonomy/review persistence is incomplete",
    )
    _require(
        'evaluation_actions.add_parser("classify")' in cli
        and 'if args.action == "eval" and args.eval_action == "classify"' in cli
        and all(token in tests for token in ("disabled_or_unknown", "private_gold", "owner_review_confirmation")),
        "Task005 private evaluation, CLI or review coverage is incomplete",
    )
    return Check(
        "owner_taxonomy_classifier_and_review_shape",
        "PASS",
        {"classifier_store_mutators": 0, "cloud_routes": 0, "taxonomy_physical_deletes": 0},
    )


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "Task005 evidence contains a local user path")
    _require("github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "Task005 evidence contains a secret")
    _require("https://" not in rendered and "http://" not in rendered, "Task005 evidence contains a URL")


def validate_facts_and_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_evidence(evidence)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    commit = _task_commit()
    _require(
        evidence.get("task_id") == TASK_ID
        and evidence.get("phase") == PHASE
        and evidence.get("run_id") == RUN_ID
        and evidence.get("status") == "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING"
        and evidence.get("task_commit") == commit
        and evidence.get("source_receipt_sha256") == _source_receipt(commit),
        "Task005 evidence receipt drifted",
    )
    execution = evidence.get("execution", {})
    policy = evidence.get("policy", {})
    _require(
        all(execution.get(field) == 0 for field in ("ai_top_level_category_mutations", "cloud_uploads", "model_calls", "network_calls", "notion_calls", "platform_calls"))
        and execution.get("owner_private_gold_evaluation") == "NOT_RUN"
        and execution.get("real_account_execution") == "NOT_RUN"
        and policy.get("auto_classify") == "DISABLED_PENDING_PRIVATE_GOLD"
        and policy.get("taxonomy_actor") == "OWNER_ONLY"
        and policy.get("raw_media_url_persisted") is False,
        "Task005 evidence overclaims automation or external execution",
    )
    _require(
        project.get("status")
        in {
            "stage_4_task005_taxonomy_classifier_ci_synth_private_gold_pending_g4_review_pending",
            "stage_4_g4_pass_ci_synth_private_gold_disabled_stage_5_task001_next",
            "stage_5_task001_notion_projection_ci_synth_pass_task002_next_real_notion_not_run",
        }
        and project.get("taxonomy_classification")
        == "owner_registry_append_only_revisions_constrained_deterministic_local_suggestion_only_review_private_gold_oracle_auto_classify_disabled_pending_private_gold"
        and project.get("canonical_store") == "active_local_sqlite_logical_truth",
        "Task005 project fact drifted",
    )
    decisions = architecture.get("decisions")
    _require(isinstance(decisions, list), "architecture decisions are invalid")
    taxonomy_decision = next((item for item in decisions if isinstance(item, dict) and item.get("id") == "ADR-009"), None)
    classifier_decision = next((item for item in decisions if isinstance(item, dict) and item.get("id") == "ADR-016"), None)
    _require(
        isinstance(taxonomy_decision, dict)
        and taxonomy_decision.get("state") == "accepted_implementation"
        and isinstance(classifier_decision, dict)
        and classifier_decision.get("state") == "accepted_implementation",
        "Task005 architecture decisions drifted",
    )
    return Check(
        "evidence_and_current_facts",
        "PASS",
        {"auto_classify": "DISABLED_PENDING_PRIVATE_GOLD", "platform_calls": 0, "source_receipt": "verified"},
    )


def _run_acceptance() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        raise VerificationError("Task005 acceptance runner failed")
    payloads: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    _require(payloads, "Task005 acceptance runner did not emit a receipt")
    return payloads[-1]


def validate_acceptance_execution() -> Check:
    receipt = _run_acceptance()
    execution = receipt.get("execution", {})
    policy = receipt.get("policy", {})
    _require(
        receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("run_id") == RUN_ID
        and receipt.get("status") == "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING"
        and receipt.get("metrics", {}).get("synthetic_unit_tests", 0) >= 22
        and receipt.get("metrics", {}).get("automatic_classification_writes") == 0
        and all(execution.get(field) == 0 for field in ("ai_top_level_category_mutations", "cloud_uploads", "model_calls", "network_calls", "notion_calls", "platform_calls"))
        and execution.get("owner_private_gold_evaluation") == "NOT_RUN"
        and policy.get("auto_classify") == "DISABLED_PENDING_PRIVATE_GOLD"
        and policy.get("taxonomy_actor") == "OWNER_ONLY",
        "Task005 acceptance receipt is invalid",
    )
    return Check(
        "fresh_synthetic_acceptance",
        "PASS",
        {"auto_classify": "DISABLED_PENDING_PRIVATE_GOLD", "synthetic_unit_tests": receipt["metrics"]["synthetic_unit_tests"]},
    )


def validate_historical_compatibility() -> Check:
    commands = (
        ("scripts/verify_multimodal_001.py", "--verify-worktree"),
        ("scripts/verify_multimodal_002.py", "--verify-worktree"),
        ("scripts/verify_multimodal_003.py", "--verify-worktree"),
        ("scripts/verify_multimodal_004.py", "--verify-worktree"),
        ("scripts/verify_adapters_010.py", "--verify-worktree", "--require-evidence"),
        ("scripts/verify_stage_3_review_resume_recheck.py", "--verify-worktree", "--skip-acceptance", "--require-evidence"),
        ("scripts/verify_stage_3_review_resume.py", "--require-evidence"),
    )
    for command in commands:
        result = subprocess.run(
            [sys.executable, "-B", *command],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=300,
        )
        if result.returncode != 0:
            raise VerificationError("a historical compatibility verifier failed")
    return Check(
        "historical_task_and_g3_compatibility",
        "PASS",
        {"historical_verifiers": len(commands), "stage_3_uploads": 0, "platform_calls": 0},
    )


def validate_worktree() -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) not in {"", "main"}, "Task005 must remain in a non-main worktree")
    return Check("worktree_isolation", "PASS", {"main_mutated": False, "task_worktree": True})


def run_checks(*, verify_worktree: bool, run_acceptance: bool) -> list[Check]:
    checks = [
        validate_scope_and_boundary(),
        validate_task_and_transition(),
        validate_implementation_shape(),
        validate_facts_and_evidence(),
        validate_historical_compatibility(),
    ]
    if verify_worktree:
        checks.append(validate_worktree())
    if run_acceptance:
        checks.append(validate_acceptance_execution())
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--run-acceptance", action="store_true")
    arguments = parser.parse_args()
    try:
        checks = run_checks(verify_worktree=arguments.verify_worktree, run_acceptance=arguments.run_acceptance)
    except (OSError, VerificationError, subprocess.TimeoutExpired):
        return 1
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


if __name__ == "__main__":
    raise SystemExit(main())
