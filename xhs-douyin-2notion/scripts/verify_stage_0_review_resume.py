#!/usr/bin/env python3
"""Fail-closed verifier for the x2n Stage 0 Review Resume.

The Owner-directed exception applies only to shared authentication material
outside x2n. It does not waive a sensitive value in the project, history,
private runtime, evidence, artifacts or repository remotes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Pattern
from urllib.parse import urlsplit

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
POLICY = PROJECT_ROOT / "machine/policy/external_auth_material_isolation_policy.json"
CHANGE_EVENT = PROJECT_ROOT / "docs/governance/CHANGE_EVENT_S00_REVIEW_RESUME.md"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
SNAPSHOT_TOOL = PROJECT_ROOT / "scripts/public_source_snapshot.py"
GATE_STATE = PROJECT_ROOT / "machine/facts/stage_gate_state.json"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_0/review_resume"

RESUME_ID = "STG.X2N.0.REVIEW.RESUME"
RESUME_RUN_ID = "RUN-X2N-S00-REVIEW-RESUME"
CHANGE_EVENT_ID = "CE-X2N-20260720-S00-REVIEW-RESUME"
POLICY_ID = "POLICY.X2N.AUTH-ISOLATION.001"
INCIDENT_ID = "INC-X2N-S00-P05-001"
OWNER_ACTION = "retained_shared_external_material_with_x2n_zero_contact"


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


def _load_module(module_name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, PROJECT_ROOT / "scripts" / filename)
    _require(spec is not None and spec.loader is not None, f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _git(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=REPOSITORY_ROOT, check=False, capture_output=True, text=True)
    return result.returncode, result.stdout


def _git_required(args: list[str]) -> str:
    returncode, stdout = _git(args)
    _require(returncode == 0, "isolated repository inspection failed")
    return stdout.rstrip()


def _text_files(root: Path) -> Iterable[Path]:
    ignored = {"__pycache__", ".pytest_cache", ".git"}
    suffixes = {"", ".md", ".json", ".yaml", ".yml", ".py", ".txt", ".toml"}
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or any(part in ignored for part in path.parts):
            continue
        if path.suffix.lower() in suffixes or path.name in {"VERSION", ".gitignore"}:
            yield path


def _sensitive_patterns() -> tuple[Pattern[str], ...]:
    fine_grained_prefix = "github" + "_pat_"
    short_prefix = "gh" + r"[pousr]_"
    cdn_fragments = (
        "byte" + "img",
        "psta" + "tp",
        "douyin" + "pic",
        "douyin" + "static",
        "xhscdn".replace("cdn", "" + "cdn"),
        "sns-web" + "pic",
    )
    return (
        re.compile(re.escape(fine_grained_prefix) + r"[A-Za-z0-9]"),
        re.compile(short_prefix + r"[A-Za-z0-9]{8,}"),
        re.compile(r"https://[^\s/:@]+(?::[^\s/@]+)?@github\.com/", re.IGNORECASE),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{12,}"),
        re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        re.compile("-----BEGIN " + r"[A-Z ]*" + "PRIVATE KEY-----"),
        re.compile(r"https?://[^\s\"']*(?:" + "|".join(cdn_fragments) + r")[^\s\"']*", re.IGNORECASE),
    )


def _sensitive_hit_count(texts: Iterable[str]) -> int:
    patterns = _sensitive_patterns()
    return sum(1 for value in texts if any(pattern.search(value) for pattern in patterns))


def _authenticated_remote_hit_count(values: Iterable[str]) -> int:
    hits = 0
    for value in values:
        if _sensitive_hit_count((value,)):
            hits += 1
            continue
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and (parsed.username is not None or parsed.password is not None):
            hits += 1
    return hits


def validate_owner_change_and_policy() -> Check:
    _require(POLICY.is_file() and CHANGE_EVENT.is_file() and ACCEPTANCE.is_file() and SNAPSHOT_TOOL.is_file(), "Resume control artifact missing")
    policy = _load_json(POLICY)
    _require(policy.get("schema_version") == "1.0" and policy.get("policy_id") == POLICY_ID, "isolation policy identity mismatch")
    _require(policy.get("incident_id") == INCIDENT_ID and policy.get("owner_change_event") == CHANGE_EVENT_ID, "policy routing mismatch")
    _require(policy.get("classification") == "external_owner_managed_shared_auth_material_outside_x2n", "external material classification drifted")
    _require(policy.get("owner_decision") == "retain_shared_external_material" and policy.get("residual_risk") == "owner_accepted_external_only", "Owner decision or residual-risk scope drifted")
    _require(policy.get("not_a_secret_presence_waiver") is True, "policy attempted to waive sensitive-value presence")

    controls = policy.get("x2n_controls", {})
    expected_controls = {
        "read_material", "request_material", "display_material", "persist_material", "use_material",
        "mutate_material", "delete_material", "rotate_material", "revoke_material",
        "modify_global_git_config", "modify_credential_helpers",
    }
    _require(set(controls) == expected_controls and all(value is False for value in controls.values()), "x2n zero-contact controls are incomplete or enabled")

    research = policy.get("future_public_source_research", {})
    _require(research.get("required_tool") == "scripts/public_source_snapshot.py", "anonymous snapshot tool is not mandatory")
    required_true = {
        "anonymous_https_only", "remote_userinfo_forbidden", "credential_helpers_disabled_per_command",
        "global_and_system_git_config_disabled_per_command", "interactive_auth_disabled",
        "environment_allowlist_only", "temporary_snapshot_required", "snapshot_deleted_after_audit",
    }
    _require(all(research.get(key) is True for key in required_true), "anonymous public-source controls are incomplete")

    requirements = policy.get("g0_resolution_requirements", {})
    zero_keys = {
        "project_current_tree_credential_hits", "project_history_credential_hits", "private_root_credential_hits",
        "product_or_runtime_references", "repository_authenticated_remote_hits",
    }
    _require(all(requirements.get(key) == 0 for key in zero_keys), "G0 zero-contact thresholds drifted")
    _require(requirements.get("owner_attestation_required") is True and requirements.get("full_stage_review_resume_required") is True, "G0 Resume requirements weakened")
    _require(policy.get("future_secret_hit_action") == "fail_closed_incident_no_waiver", "future sensitive-value action weakened")

    change_event = CHANGE_EVENT.read_text(encoding="utf-8")
    for token in (CHANGE_EVENT_ID, "x2n 零接触", "匿名公开源码研究补偿控制", "不执行新 DAG Task", "TSK.x2n.foundation.001"):
        _require(token in change_event, f"Owner Change Event missing: {token}")
    acceptance = ACCEPTANCE.read_text(encoding="utf-8")
    _require("`WAIVED_WITH_OWNER_DECISION` 不允许用于 Secret/CDN、未授权删除、数据丢失、许可证和不可回滚迁移。" in acceptance, "global non-waiver rule changed")

    tool = SNAPSHOT_TOOL.read_text(encoding="utf-8")
    for token in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "credential.helper=", "GIT_TERMINAL_PROMPT", "environment_allowlist"):
        if token == "environment_allowlist":
            _require("os.environ.copy" not in tool, "snapshot tool copies the ambient environment")
        else:
            _require(token in tool, f"snapshot tool missing isolation control: {token}")
    return Check("owner_change_and_isolation_policy", "PASS", {"policy_id": POLICY_ID, "zero_contact_controls": len(expected_controls), "secret_presence_waiver": False})


def validate_owner_attestation(root: Path) -> Check:
    verifier = _load_module("x2n_resume_owner_attestation", "verify_owner_recovery_attestation.py")
    try:
        check = verifier.validate_recovery_receipt(root)
    except Exception as exc:
        raise VerificationError(f"Owner attestation verification failed: {exc}") from exc
    _require(check.status == "PASS", "Owner attestation did not pass")
    _require(check.details.get("recovery_action") == OWNER_ACTION and check.details.get("old_material_state") == "retained_owner_directed", "Owner attestation does not match the directed external-retention action")
    _require(check.details.get("secret_values") == 0 and check.details.get("authorization_scope") == "STAGE_0_REVIEW_RESUME_ONLY", "Owner attestation scope is unsafe")
    return Check("owner_attestation", "PASS", {"incident_id": INCIDENT_ID, "recovery_action": OWNER_ACTION, "secret_values": 0, "private_receipt_metadata_exposed": False})


def _history_sensitive_hits() -> int:
    commits = _git_required(["rev-list", "--all", "--", "xhs-douyin-2notion"]).splitlines()
    if not commits:
        return 0
    expressions = (
        "github" + "_pat_[A-Za-z0-9]",
        "gh" + "[pousr]_[A-Za-z0-9]{8,}",
        "https://[^[:space:]/:@]+(:[^[:space:]/@]+)?@github\\.com/",
        "-----BEGIN [A-Z ]*" + "PRIVATE KEY-----",
    )
    hits = 0
    for commit in commits:
        for expression in expressions:
            returncode, stdout = _git(["grep", "-I", "-l", "-E", "-e", expression, commit, "--", "xhs-douyin-2notion"])
            _require(returncode in {0, 1}, "project-history sensitive-value scan failed")
            if returncode == 0:
                hits += len([line for line in stdout.splitlines() if line])
    return hits


def validate_repository_zero_contact() -> Check:
    current_hits = _sensitive_hit_count(path.read_text(encoding="utf-8", errors="replace") for path in _text_files(PROJECT_ROOT))
    history_hits = _history_sensitive_hits()

    returncode, stdout = _git(["config", "--local", "--get-regexp", r"^remote\..*\.url$"])
    _require(returncode in {0, 1}, "local repository remote inspection failed")
    remote_values = []
    for line in stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            remote_values.append(parts[1])
    remote_hits = _authenticated_remote_hit_count(remote_values)

    current_state = _load_json(TASK_STATE)
    foundation_complete = current_state.get("tasks", {}).get("TSK.x2n.foundation.001") == "pass"
    if foundation_complete:
        _require((PROJECT_ROOT / "apps").is_dir() and (PROJECT_ROOT / "packages").is_dir() and (PROJECT_ROOT / "SKILL.md").is_file(), "registered foundation scaffold missing")
        product_or_runtime_references = sum((PROJECT_ROOT / relative).exists() for relative in ("extension", "companion", "runtime", "downloads"))
    else:
        product_or_runtime_references = sum((PROJECT_ROOT / relative).exists() for relative in ("apps", "packages", "extension", "companion"))
    _require(current_hits == 0, "sensitive-shaped value found in current x2n tree")
    _require(history_hits == 0, "sensitive-shaped value found in x2n history")
    _require(remote_hits == 0, "authenticated repository remote found")
    _require(product_or_runtime_references == 0, "unregistered product or runtime implementation entered the repository")
    return Check("repository_zero_contact", "PASS", {
        "project_current_tree_credential_hits": current_hits,
        "project_history_credential_hits": history_hits,
        "repository_authenticated_remote_hits": remote_hits,
        "product_or_runtime_references": product_or_runtime_references,
    })


def validate_private_zero_contact(root: Path) -> Check:
    phase_0_1 = _load_module("x2n_resume_phase_0_1_private", "verify_phase_0_1.py")
    phase_0_5 = _load_module("x2n_resume_phase_0_5_private", "verify_phase_0_5.py")
    try:
        root_check = phase_0_1.validate_local_root(root)
        owner_input_check = phase_0_5.validate_owner_input(root)
    except Exception as exc:
        raise VerificationError(f"private-root validation failed: {exc}") from exc
    _require(root_check.status == "PASS" and owner_input_check.status == "PASS", "private-root contract did not pass")
    private_hits = _sensitive_hit_count(path.read_text(encoding="utf-8", errors="replace") for path in _text_files(root))
    _require(private_hits == 0, "sensitive-shaped value found in private root")
    return Check("private_zero_contact", "PASS", {"private_root_credential_hits": private_hits, "private_content_exposed": False, "absolute_path_exposed": False})


def validate_expected_gate(expect_g0: str) -> Check:
    base = _load_module("x2n_resume_base_review_state", "verify_stage_0_review.py")
    try:
        state_check = base.validate_current_state()
    except Exception as exc:
        raise VerificationError(f"current Stage state validation failed: {exc}") from exc
    gate = _load_json(GATE_STATE)
    expected_status = "pass" if expect_g0 == "pass" else "blocked_owner_action"
    _require(gate.get("gate_status") == expected_status, f"expected G0 {expect_g0}, observed a different state")
    if expect_g0 == "pass":
        _require(gate.get("review_id") == RESUME_ID and gate.get("run_id") == RESUME_RUN_ID, "G0 pass was not issued by the Resume Run")
    return Check("expected_stage_state", "PASS", {"expected_g0": expect_g0.upper(), "observed_g0": expected_status.upper(), "state_contract": state_check.status})


def run_core_checks(root: Path, expect_g0: str) -> list[Check]:
    base = _load_module("x2n_resume_base_review_core", "verify_stage_0_review.py")
    try:
        base_checks = base.run_core_checks()
    except Exception as exc:
        raise VerificationError(f"historical Stage Review validation failed: {exc}") from exc
    checks = [Check(f"base_{check.name}", check.status, check.details) for check in base_checks]
    checks.extend([
        validate_owner_change_and_policy(),
        validate_owner_attestation(root),
        validate_repository_zero_contact(),
        validate_private_zero_contact(root),
        validate_expected_gate(expect_g0),
    ])
    _require(all(check.status == "PASS" for check in checks), "a Resume core check did not pass")
    return checks


def _assert_public_evidence_safe(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "public Resume evidence contains a local absolute path")
    _require(_sensitive_hit_count((rendered,)) == 0, "public Resume evidence contains sensitive-shaped material")
    forbidden_keys = {"receipt_id", "attested_at", "receipt_hash", "resolved_root", "private_root_path", "account_identifier"}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            _require(not (set(value) & forbidden_keys), "public Resume evidence contains private receipt metadata")
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _assert_public_evidence_safe(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_evidence(checks: list[Check]) -> None:
    gate = _load_json(GATE_STATE)
    _require(gate.get("review_id") == RESUME_ID and gate.get("run_id") == RESUME_RUN_ID, "Resume evidence requires the Resume state")
    _require(gate.get("gate_status") == "pass" and gate.get("gate_decision") == "pass", "Resume evidence cannot be written before G0 pass")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    common = {
        "schema_version": "1.0",
        "project": "x2n",
        "stage": "STG.X2N.0",
        "review_id": RESUME_ID,
        "run_id": RESUME_RUN_ID,
        "generated_at": now,
        "review_base_head": _git_required(["rev-parse", "HEAD"]),
        "review_sync_target": gate["review_sync_target"],
        "origin_main_observed_at_evidence": _git_required(["rev-parse", "origin/main"]),
        "product_code": "NOT_STARTED",
        "real_account_execution": "NOT_RUN",
        "platform_calls": "NOT_RUN",
        "notion_calls": "NOT_RUN",
        "model_calls": "NOT_RUN",
        "media_downloads": "NOT_RUN",
        "redaction": {
            "private_content_included": False,
            "private_receipt_metadata_included": False,
            "secrets_included": False,
            "cdn_urls_included": False,
            "external_paths_included": False,
        },
    }
    verification = dict(common)
    verification.update({
        "status": "PASS",
        "review_status": "RESUME_COMPLETE",
        "g0_status": "PASS",
        "stage_1_authorized": True,
        "remote_upload": "AUTHORIZED_AFTER_G0_PASS",
        "checks": [check.__dict__ for check in checks],
        "historical_review_evidence": "PRESERVED_BLOCKED_AT_ORIGINAL_REVIEW",
        "downstream_product_acceptances": "NOT_RUN",
    })
    _write_json(EVIDENCE_DIR / "verification.json", verification)

    g0 = dict(common)
    g0.update({
        "gate_id": "G0",
        "status": "PASS",
        "decision": "PASS",
        "pass_conditions": {key: value.upper() for key, value in gate["pass_conditions"].items()},
        "stop_conditions": {key: value.upper() for key, value in gate["stop_conditions"].items()},
        "blocking_followups": gate["blocking_followups"],
        "stage_1_authorized": True,
        "remote_upload": "AUTHORIZED_AFTER_G0_PASS",
        "required_next_run": "TSK.x2n.foundation.001",
    })
    _write_json(EVIDENCE_DIR / "G0.json", g0)

    owner = dict(common)
    owner.update({
        "status": "PASS",
        "incident_id": INCIDENT_ID,
        "owner_change_event": CHANGE_EVENT_ID,
        "policy_id": POLICY_ID,
        "owner_decision": "retain_shared_external_material",
        "recovery_action": OWNER_ACTION,
        "external_residual_risk_owner_accepted": True,
        "x2n_zero_contact": True,
        "secret_presence_waiver": False,
        "private_receipt_validated": True,
    })
    _write_json(EVIDENCE_DIR / "owner_decision.json", owner)


def validate_evidence() -> Check:
    expected = {"verification.json", "G0.json", "owner_decision.json"}
    actual = {path.name for path in EVIDENCE_DIR.glob("*.json")}
    _require(actual == expected, f"Resume evidence set mismatch: {sorted(actual)}")
    for path in EVIDENCE_DIR.glob("*.json"):
        payload = _load_json(path)
        _assert_public_evidence_safe(payload)
        _require(payload.get("review_id") == RESUME_ID and payload.get("run_id") == RESUME_RUN_ID, f"Resume evidence identity mismatch: {path.name}")
        _require(payload.get("status") == "PASS", f"Resume evidence is not PASS: {path.name}")
        _require(all(value is False for value in payload.get("redaction", {}).values()), f"Resume evidence redaction flags are unsafe: {path.name}")
    verification = _load_json(EVIDENCE_DIR / "verification.json")
    _require(verification.get("g0_status") == "PASS" and verification.get("stage_1_authorized") is True, "Resume verification receipt did not authorize Stage 1")
    _require(verification.get("downstream_product_acceptances") == "NOT_RUN", "Resume evidence overstated downstream product acceptance")
    g0 = _load_json(EVIDENCE_DIR / "G0.json")
    _require(g0.get("decision") == "PASS" and g0.get("required_next_run") == "TSK.x2n.foundation.001", "G0 Resume receipt routing mismatch")
    owner = _load_json(EVIDENCE_DIR / "owner_decision.json")
    _require(owner.get("x2n_zero_contact") is True and owner.get("secret_presence_waiver") is False, "Owner decision evidence weakened the non-waiver boundary")
    return Check("resume_evidence", "PASS", {"files": len(actual), "g0": "PASS", "private_receipt_metadata_exposed": False})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-g0", choices=("blocked", "pass"), required=True)
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--source-roadmap", type=Path)
    parser.add_argument("--source-taskpack", type=Path)
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        _require(args.verify_worktree, "Resume requires --verify-worktree")
        _require(not args.allow_external_main_dirty or args.verify_worktree, "--allow-external-main-dirty requires --verify-worktree")
        _require(bool(args.source_roadmap and args.source_taskpack), "Resume requires both immutable original source files")
        _require(not args.write_evidence or args.expect_g0 == "pass", "Resume evidence cannot be written before G0 pass")
        _require(not args.require_evidence or args.expect_g0 == "pass", "Resume evidence is only valid for G0 pass")
        root_value = os.environ.get("X2N_DATA_ROOT")
        _require(bool(root_value), "X2N_DATA_ROOT is required")
        root = Path(str(root_value)).expanduser().resolve()

        checks = run_core_checks(root, args.expect_g0)
        base = _load_module("x2n_resume_base_review_full", "verify_stage_0_review.py")
        try:
            checks.append(Check("resume_worktree_scope", "PASS", base.validate_worktree_scope(args.allow_external_main_dirty).details))
            checks.append(Check("resume_original_sources", "PASS", base.validate_original_sources(args.source_roadmap, args.source_taskpack).details))
            checks.append(Check("resume_phase_reacceptance", "PASS", base.validate_phase_reacceptance(args.source_roadmap, args.source_taskpack, root, args.allow_external_main_dirty).details))
        except Exception as exc:
            raise VerificationError(f"full Resume reacceptance failed: {exc}") from exc
        if args.write_evidence:
            write_evidence(checks)
            checks.append(validate_evidence())
        elif args.require_evidence:
            checks.append(validate_evidence())

        g0_pass = args.expect_g0 == "pass"
        print(json.dumps({
            "status": "PASS",
            "review_status": "RESUME_COMPLETE" if g0_pass else "RESUME_PREFLIGHT_PASS",
            "review_id": RESUME_ID,
            "checks": [check.__dict__ for check in checks],
            "g0_status": "PASS" if g0_pass else "BLOCKED_PENDING_STATE_TRANSITION",
            "stage_1_authorized": g0_pass,
            "remote_upload": "AUTHORIZED_AFTER_G0_PASS" if g0_pass else "FORBIDDEN_UNTIL_G0_PASS",
            "shared_auth_accessed": False,
            "product_code": "NOT_STARTED",
            "real_account_execution": "NOT_RUN",
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, VerificationError, yaml.YAMLError) as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED",
            "error": "private filesystem or repository verification failed" if isinstance(exc, OSError) else str(exc),
            "g0_status": "BLOCKED",
            "stage_1_authorized": False,
            "remote_upload": "FORBIDDEN_UNTIL_G0_PASS",
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
