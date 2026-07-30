#!/usr/bin/env python3
"""Fail-closed verifier for Stage 6.3 security, privacy and supply-chain assurance."""

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
TASK_ID = "TSK.x2n.assurance.003"
PHASE = "PH.X2N.6.3"
RUN_ID = "RUN-X2N-S06-A003"
TASK_BASE_COMMIT = "28499818c2f99a2046a386d88c2ed0c85004bc56"
STATUS = "PASS_CI_SYNTH_SECURITY_PRIVACY_SUPPLY_CHAIN_REAL_MVP_NOT_RUN"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
ASSURANCE_FACT = PROJECT_ROOT / "machine/facts/stage_6_assurance_003_state.json"
ASSURANCE_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_6_assurance_003_state.schema.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S06_ASSURANCE_003.md"
REPORT = PROJECT_ROOT / "docs/governance/STAGE_6_ASSURANCE_003.md"
SECURITY_REPORT = PROJECT_ROOT / "docs/security/ASSURANCE_003_SECURITY_REPORT.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_assurance_003_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/security/TSK.x2n.assurance.003.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
RELEASE_ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/release_artifact_allowlist.json"
AUTH_POLICY = PROJECT_ROOT / "machine/policy/external_auth_material_isolation_policy.json"

EXPECTED_ACCEPTANCES = {
    "ACC.x2n.gov.002": "PASS_CI_SYNTH_PRIVATE_AUTH_ZERO_CONTACT_CURRENT_AND_HISTORY_SCAN_ZERO",
    "ACC.x2n.gov.003": "PASS_CI_SYNTH_PUBLIC_SOURCE_RELEASE_ALLOWLIST_LICENSE_ZERO_UNKNOWN",
    "ACC.x2n.media.001": "PASS_CI_SYNTH_FIVE_SCOPE_PERSISTENCE_CDN_PRIVATE_ZERO",
    "ACC.x2n.media.003": "PASS_CI_SYNTH_512_URL_FUZZ_32_SSRF_FORBIDDEN_ZERO_LOCAL_FILE_READS",
    "ACC.x2n.media.004": "PASS_CI_SYNTH_BOUNDED_FFMPEG_FFPROBE_TEMPORARY_ONLY",
    "ACC.x2n.rel.003": "PASS_CI_SYNTH_SAST_OSV_SBOM_LICENSE_ARTIFACT_HISTORY_ZERO",
}
EXPECTED_EXECUTION = {
    "anonymous_osv_batch_requests": 1,
    "external_release_uploads": 0,
    "model_calls": 0,
    "platform_calls": 0,
    "private_gold_reads": 0,
    "real_account_execution": "NOT_RUN",
    "runtime_deployment": "NOT_RUN",
    "secret_reads": 0,
}
EXPECTED_REPORTS = {
    "artifact": {"allowlist_findings": 0, "deterministic": True, "runtime_data_files": 0},
    "csp": {"host_permissions": 0, "remote_resources": 0},
    "history": {"credential_history_hits": 0},
    "license": {"unknown_licenses": 0},
    "media": {"cdn_persistence_findings": 0, "forbidden_target_successes": 0, "local_file_reads": 0},
    "osv": {"critical_high_unresolved": 0, "dependencies_queried": 33, "vulnerabilities_reported": 0},
    "sast": {"critical_high_findings": 0},
    "source": {"finding_count": 0},
    "terminology": {"active_legacy_aliases": 0},
}
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
    "docs/governance/RUN_CONTRACT_S06_ASSURANCE_003.md",
    "docs/governance/STAGE_6_ASSURANCE_003.md",
    "docs/product_design/v0.0.0.1/00_PRFAQ.md",
    "docs/product_design/v0.0.0.1/01_PRD.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    "docs/security/ASSURANCE_003_SECURITY_REPORT.md",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/stage_6_assurance_003_state.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/schemas/stage_6_assurance_003_state.schema.json",
    "scripts/run_assurance_003_acceptance.py",
    "scripts/verify_assurance_003.py",
    "scripts/verify_stage_3_review_resume_recheck.py",
    "tests/test_assurance_003.py",
    "tests/test_stage_3_review_resume_recheck.py",
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


class Assurance003VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance003VerificationError(message)


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
        raise Assurance003VerificationError(f"invalid JSON: {path.name}") from error
    _require(isinstance(payload, dict), f"JSON object required: {path.name}")
    return payload


def _taskpack() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise Assurance003VerificationError("Taskpack is unreadable") from error
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
    _require(changed, "assurance003 source scope is empty")
    prefix = "xhs-douyin-2notion/"
    _require(all(path.startswith(prefix) for path in changed), "assurance003 scope escaped x2n")
    relative = [path.removeprefix(prefix) for path in changed]
    allowed = CURRENT_ALLOWED_EXACT if allow_evidence else SOURCE_CHANGED_EXACT
    _require(set(relative) <= allowed, "assurance003 scope contains an unapproved change")
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
    _require(payloads, "assurance003 acceptance emitted no JSON receipt")
    return payloads[-1]


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(("rev-parse", "--show-toplevel"))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(("branch", "--show-current"))
    _require(branch not in {"", "main"}, "assurance003 must run in a non-main worktree")
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
        "assurance003 does not descend from assurance002",
    )
    return Check("worktree_isolation", "PASS", {"branch": branch, "external_main_dirty_paths": len(main_paths)})


def validate_transition_and_facts() -> Check:
    tasks = {item.get("id"): item for item in _taskpack().get("tasks", []) if isinstance(item, dict)}
    task = tasks.get(TASK_ID)
    _require(
        isinstance(task, dict)
        and task.get("stage") == "STG.X2N.6"
        and task.get("phase") == PHASE
        and task.get("status") == "complete_ci_synth_security_privacy_supply_chain"
        and tuple(task.get("acceptance_ids", [])) == tuple(EXPECTED_ACCEPTANCES)
        and tuple(task.get("depends_on", []))
        == ("TSK.x2n.discovery.005", "TSK.x2n.foundation.005", "TSK.x2n.uxops.005"),
        "Taskpack assurance003 transition drifted",
    )
    next_task = tasks.get("TSK.x2n.assurance.004")
    _require(
        isinstance(next_task, dict) and next_task.get("phase") == "PH.X2N.6.4" and next_task.get("status") == "planned",
        "next Task authorization drifted",
    )
    state = _load_json(TASK_STATE)
    expected_state = (
        "stage_6_assurance003_ci_synth_security_privacy_supply_chain_pass_assurance004_next_real_runtime_not_run"
    )
    _require(
        state.get("schema_version") == "1.44"
        and state.get("stage") == "STG.X2N.6"
        and state.get("phase") == PHASE
        and state.get("last_completed_phase") == PHASE
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "single_dag_task_ci_synth_security_privacy_supply_chain_assurance"
        and state.get("state") == expected_state
        and state.get("tasks", {}).get(TASK_ID) == "pass"
        and all(state.get("acceptance_status", {}).get(key) == value for key, value in EXPECTED_ACCEPTANCES.items())
        and state.get("next_phase") == "PH.X2N.6.4"
        and state.get("next_run") == "TSK.x2n.assurance.004"
        and state.get("next_task") == "TSK.x2n.assurance.004"
        and state.get("stage_6_task003_complete") is True
        and state.get("stage_6_task003_acceptance") == EXPECTED_ACCEPTANCES
        and state.get("stage_6_task004_authorized") is True
        and state.get("public_release_authorized") is False,
        "Task State assurance003 transition is invalid",
    )
    schema = _load_json(ASSURANCE_SCHEMA)
    fact = _load_json(ASSURANCE_FACT)
    _require(
        schema.get("$id") == "urn:x2n:stage-6-assurance-003-state:1.0"
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
        and fact.get("next_task") == {"id": "TSK.x2n.assurance.004", "phase": "PH.X2N.6.4", "status": "PLANNED"}
        and fact.get("release_policy") == RELEASE_POLICY,
        "assurance003 fact drifted",
    )
    _safe_payload(fact)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    adr = next(
        (item for item in architecture.get("decisions", []) if isinstance(item, dict) and item.get("id") == "ADR-024"),
        None,
    )
    _require(
        project.get("schema_version") == "1.8"
        and project.get("status") == expected_state
        and project.get("stage_6_current_task")
        == "assurance003_ci_synth_security_privacy_supply_chain_pass_assurance004_next_real_runtime_not_run"
        and project.get("security_assurance")
        == "current_source_candidate_artifact_private_cdn_zero_history_credential_zero_sast_osv_sbom_license_csp_ssrf_media_pass",
        "project fact overclaims assurance003 capability",
    )
    _require(
        architecture.get("schema_version") == "1.8"
        and architecture.get("phase") == PHASE
        and architecture.get("status") == expected_state
        and architecture.get("stage_gate")
        == "g5_pass_assurance001_pass_assurance002_features_disabled_assurance003_security_pass_assurance004_authorized"
        and isinstance(adr, dict)
        and adr.get("topic") == "stage_6_security_privacy_license_supply_chain_assurance"
        and adr.get("state") == "accepted_implementation",
        "architecture fact overclaims assurance003 capability",
    )
    return Check("taskpack_state_and_fact_transition", "PASS", {"next_task": "TSK.x2n.assurance.004"})


def validate_security_boundary() -> Check:
    artifact_policy = _load_json(ARTIFACT_POLICY)
    release_policy = _load_json(RELEASE_ARTIFACT_POLICY)
    auth_policy = _load_json(AUTH_POLICY)
    controls = auth_policy.get("x2n_controls")
    _require(
        isinstance(controls, dict) and controls and all(value is False for value in controls.values()),
        "auth isolation policy drifted",
    )
    _require(
        "scripts/run_assurance_003_acceptance.py" in artifact_policy.get("enforcement", [])
        and "scripts/verify_assurance_003.py" in artifact_policy.get("enforcement", [])
        and release_policy.get("runtime_data_allowed") is False
        and release_policy.get("absolute_paths_allowed") is False
        and release_policy.get("credentials_allowed") is False
        and release_policy.get("platform_media_cdn_urls_allowed") is False,
        "public artifact policy drifted",
    )
    controls_to_scan = (RUN_CONTRACT, REPORT, SECURITY_REPORT, ASSURANCE_FACT, ASSURANCE_SCHEMA, ACCEPTANCE_RUNNER)
    for path in controls_to_scan:
        _require(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, "assurance003 control missing or oversized")
        _safe_payload({"control": path.read_text(encoding="utf-8")})
    runner = ACCEPTANCE_RUNNER.read_text(encoding="utf-8")
    _require(
        "GIT_CONFIG_NOSYSTEM" in runner
        and "GIT_TERMINAL_PROMPT" in runner
        and "_history_scan" in runner
        and "build-artifact" in runner
        and '"osv"' in runner
        and "os.environ" + ".copy" not in runner,
        "security acceptance runner boundary drifted",
    )
    return Check(
        "security_privacy_public_boundary",
        "PASS",
        {"artifact_runtime_data_allowed": False, "auth_controls": len(controls), "sensitive_value_hits": 0},
    )


def validate_fresh_acceptance() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a003-verify-") as temporary:
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
        result = subprocess.run(
            [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
            cwd=PROJECT_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=1_800,
        )
    _require(result.returncode == 0, "fresh security assurance acceptance failed")
    receipt = _json_line(result.stdout)
    pipeline = receipt.get("pipeline")
    _require(
        receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("run_id") == RUN_ID
        and receipt.get("status") == STATUS
        and receipt.get("acceptance_status") == EXPECTED_ACCEPTANCES
        and receipt.get("execution") == EXPECTED_EXECUTION
        and receipt.get("reports") == EXPECTED_REPORTS
        and isinstance(pipeline, dict)
        and pipeline.get("blocking_commands") == 7
        and pipeline.get("blocking_failures") == 0
        and pipeline.get("blocking_skips") == 0
        and pipeline.get("source", {}).get("finding_count") == 0
        and pipeline.get("sast", {}).get("critical_high_findings") == 0
        and pipeline.get("license", {}).get("unknown_licenses") == 0
        and pipeline.get("osv", {}).get("critical_high_unresolved") == 0
        and pipeline.get("artifact", {}).get("deterministic") is True
        and pipeline.get("history", {}).get("credential_history_hits") == 0
        and pipeline.get("media", {}).get("ssrf", {}).get("forbidden_target_successes") == 0
        and pipeline.get("nomenclature", {}).get("active_legacy_aliases") == 0,
        "fresh security assurance receipt drifted",
    )
    return Check(
        "fresh_ci_synth_security_assurance",
        "PASS",
        {"dependencies_queried": 33, "history_credential_hits": 0, "platform_calls": 0},
    )


def validate_evidence_and_scope() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_payload(evidence)
    task_commit = evidence.get("task_commit")
    _require(
        isinstance(task_commit, str) and re.fullmatch(r"[0-9a-f]{40}", task_commit) is not None,
        "assurance003 task commit is invalid",
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
        "assurance003 task commit ancestry is invalid",
    )
    _require(
        _validate_scope(TASK_BASE_COMMIT, task_commit, allow_evidence=False) >= len(SOURCE_CHANGED_EXACT),
        "assurance003 source scope incomplete",
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
        "assurance003 evidence receipt drifted",
    )
    return Check("assurance_evidence_and_scope", "PASS", {"current_paths": current_paths, "task_source": "verified"})


def run_checks(
    *, verify_worktree: bool, allow_external_main_dirty: bool, run_acceptance: bool, require_evidence: bool
) -> list[Check]:
    checks = [validate_transition_and_facts(), validate_security_boundary()]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_fresh_acceptance())
    if require_evidence:
        checks.append(validate_evidence_and_scope())
    _require(all(check.status == "PASS" for check in checks), "assurance003 verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify x2n Stage 6 Assurance003")
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
    except (OSError, Assurance003VerificationError, subprocess.SubprocessError, yaml.YAMLError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
