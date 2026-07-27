#!/usr/bin/env python3
"""Fail-closed, credential-free validator for CyberBoss P4.3 / CB-420."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-420"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB410_CLOSURE = "ea82f02b175e864d754ab5bdfaccd0e84a89e6d4"
CB410_TREE = "a8d110cc271dbce7fc8f0e8f36d2f16d815e8ddc"
ASSURANCE_SCHEMA = "cyberboss.security-assurance.v1"
SOURCE_PACKAGE_SCHEMA = "cyberboss.corresponding-source-package.v1"
REPORT_DIGEST = "49852bb4449942d0bc9df2623a2e340748144c2a3ae56b414280b696db90cab9"
SOURCE_MANIFEST_DIGEST = "e7ce7ce100ea55f6dcbc033c8179adb9eedf80097ce7dd7b1bf819179f07766f"
ASSURANCE_CARD_SHA256 = "95025624ea8e920f702529b9f6b5819474474be9d79f14e28ffaf6be30c258ed"
ACCEPTANCE = ("FA-AC-011", "FA-AC-017", "FA-AC-028", "FA-AC-032")
ROUTER_RESULT = {
    "task_id": "CB-420",
    "selected_skill": "output-skill",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 1,
    "fallback": "machine/skill_microplaybooks.json",
}
IMPLEMENTATION_PATHS = {
    "CyberBoss/app/scripts/security-assurance-suite.js",
    "CyberBoss/app/src/services/assurance/canonical-security-assurance.js",
    "CyberBoss/app/test/canonical-backup-runtime.test.js",
    "CyberBoss/app/test/canonical-security-assurance.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P4_3_CB_420.md",
    "CyberBoss/docs/governance/SUPPLY_CHAIN_ASSURANCE_CB_420.md",
    "CyberBoss/scripts/validate_cb420.py",
    "CyberBoss/tests/security-assurance-suite.test.js",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/CB-420/subject.json",
    "CyberBoss/docs/evidence/CB-420/summary.json",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
LOCAL_VALIDATION = {
    "assurance_unit": "passed",
    "assurance_cli": "passed",
    "assurance_root_cli": "passed",
    "secret_scan": "passed",
    "access_domain": "passed",
    "workspace_scope": "passed",
    "approval_policy": "passed",
    "cloud_runtime_boundary": "passed",
    "backup_privacy": "passed",
    "cb410_anchor": "passed",
    "cb400_anchor": "passed",
    "app_check": "passed",
    "app_regression": "passed",
    "identity_scope": "passed",
    "config": "passed",
    "dag": "passed",
    "traceability": "passed",
    "no_wait": "passed",
    "taskpack": "passed",
    "manifests": "passed",
}
EXTERNAL_ACTIVATION = {
    "cloudflare_web_analytics": "activation_pending",
    "release_distribution": "activation_pending",
    "private_database": "activation_pending",
    "r2": "hazard_blocked",
    "cloudflare_access": "activation_pending",
    "dns_route": "activation_pending",
    "oci": "activation_pending",
    "timeline": "activation_pending",
    "global_status": "activation_pending",
    "self_heal": "activation_pending",
    "timer": "activation_pending",
}
SENSITIVE_ENV_FRAGMENTS = (
    "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH", "COOKIE", "SESSION",
    "PRIVATE_KEY", "ACCESS_KEY", "API_KEY", "OPENAI", "CODEX", "WECHAT",
    "CLOUDFLARE", "GITHUB",
)
SENSITIVE_ENV_PREFIXES = ("AWS_", "OCI_", "CF_", "GH_", "SSH_")
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def git(*args: str, check: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git_failed")
    return result.returncode, result.stdout.rstrip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report(errors: list[str], code: str, condition: bool) -> None:
    if not condition:
        errors.append(code)


def commit_paths(commit: str) -> set[str]:
    parent = git("rev-parse", f"{commit}^")[1]
    return set(filter(None, git("diff", "--name-only", parent, commit)[1].splitlines()))


def is_sensitive_environment_key(key: str) -> bool:
    upper = key.upper()
    return any(fragment in upper for fragment in SENSITIVE_ENV_FRAGMENTS) or upper.startswith(SENSITIVE_ENV_PREFIXES)


def credential_free_environment(root: Path) -> tuple[dict[str, str], int]:
    environment: dict[str, str] = {}
    removed = 0
    for key, value in os.environ.items():
        if is_sensitive_environment_key(key):
            removed += 1
            continue
        environment[key] = value
    if any(is_sensitive_environment_key(key) for key in environment):
        raise RuntimeError("credential_environment_scrub_failed")
    cache = root / "npm-cache"
    config = root / "config"
    temporary = root / "tmp"
    for directory in (cache, config, temporary):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update({
        "CI": "1",
        "NO_COLOR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(temporary),
        "XDG_CONFIG_HOME": str(config),
        "NPM_CONFIG_USERCONFIG": "/dev/null",
        "NPM_CONFIG_CACHE": str(cache),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return environment, removed


def run_command(
    name: str, command: list[str], cwd: Path, environment: dict[str, str],
    errors: list[str], *, markers: tuple[str, ...] = (), timeout: int = 900,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as caught:
        errors.append(f"command_exception:{name}:{type(caught).__name__}")
        return {"name": name, "exit_code": None}
    output = result.stdout or ""
    if result.returncode != 0:
        tail = output.strip().splitlines()[-1:] or ["no_output"]
        errors.append(f"command_failed:{name}:{result.returncode}:{tail[0][:180]}")
    for marker in markers:
        if marker not in output:
            errors.append(f"command_marker:{name}:{marker}")
    return {"name": name, "exit_code": result.returncode}


def verify_manifest(path: Path, errors: list[str]) -> None:
    root = path.parent
    entries: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as caught:
        errors.append(f"manifest_read:{path.relative_to(REPO)}:{type(caught).__name__}")
        return
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            errors.append(f"manifest_line:{path.relative_to(REPO)}:{number}")
            continue
        digest, relative = match.groups()
        if relative in entries or relative.startswith("/") or ".." in Path(relative).parts:
            errors.append(f"manifest_path:{path.relative_to(REPO)}:{relative}")
            continue
        entries[relative] = digest
    actual = {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate != path and "__pycache__" not in candidate.parts
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    prior = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100", "CB-110",
        "CB-120", "CB-130", "CB-140", "CB-200", "CB-210", "CB-220", "CB-230",
        "CB-240", "CB-300", "CB-310", "CB-320", "CB-330", "CB-340", "CB-400",
        "CB-410",
    )
    for task_id in prior:
        report(errors, f"task_state_prior:{task_id}", statuses.get(task_id) == "passed")
    report(errors, "task_state_cb420", statuses.get("CB-420") == ("passed" if final else "not_started"))
    for task_id in ("CB-430", "CB-440", "CB-500", "CB-510", "CB-520", "CB-530", "CB-540"):
        report(errors, f"task_state_future:{task_id}", statuses.get(task_id) == "not_started")
    gates = state.get("pass_gates") or {}
    report(errors, "task_state_prior_gates", all(gates.get(gate) == "passed" for gate in ("PG-0", "PG-1", "PG-2", "PG-3")))
    report(errors, "task_state_later_gates", all(gates.get(gate) == "not_started" for gate in ("PG-4", "PG-5")))
    expected_current = (
        {
            "run_id": "P4.3", "gate_id": None, "task_id": "CB-420",
            "scope": "security_supply_chain_privacy_agpl_assurance", "status": "passed",
        }
        if final
        else {
            "run_id": "P4.2", "gate_id": None, "task_id": "CB-410",
            "scope": "codex_model_safety_fixture_evaluation", "status": "passed",
        }
    )
    report(errors, "task_state_current_run", state.get("current_run") == expected_current)
    overlay = state.get("taskpack_overlay") or {}
    common = (
        state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("software_correctness_status") == "passed"
        and overlay.get("model_safety_evaluation_status") == "passed"
        and overlay.get("model_safety_real_trial_state") == "activation_pending"
        and overlay.get("model_safety_release_recommendation") == "keep_release_disabled_pending_real_codex_trials"
        and overlay.get("system_card_status") == "passed"
        and overlay.get("r2_backup_activation") == "hazard_blocked"
        and overlay.get("oci_backup_activation") == "activation_pending"
        and overlay.get("self_heal_activation") == "activation_pending"
        and overlay.get("timer_activation") == "activation_pending"
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_cb420_overlay",
            overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("security_assurance_status") == "passed"
            and overlay.get("sbom_status") == "passed"
            and overlay.get("corresponding_source_status") == "passed"
            and overlay.get("analytics_privacy_assurance_status") == "passed"
            and overlay.get("security_assurance_real_activation") == "activation_pending"
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )


def validate_cb410_anchor(errors: list[str]) -> None:
    report(errors, "cb410_closure_commit", git("cat-file", "-e", f"{CB410_CLOSURE}^{{commit}}", check=False)[0] == 0)
    report(errors, "cb410_history", git("merge-base", "--is-ancestor", CB410_CLOSURE, "HEAD", check=False)[0] == 0)
    report(errors, "cb410_evidence_mutated", git("diff", "--quiet", CB410_CLOSURE, "--", "CyberBoss/docs/evidence/CB-410", check=False)[0] == 0)
    report(errors, "cb410_tree", git("rev-parse", f"{CB410_CLOSURE}^{{tree}}", check=False)[1] == CB410_TREE)
    try:
        summary = load_json(PROJECT / "docs/evidence/CB-410/summary.json")
        subject = load_json(PROJECT / "docs/evidence/CB-410/subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("cb410_evidence_read")
        return
    report(
        errors,
        "cb410_subject",
        summary.get("schema_version") == "cyberboss.cb410.closure-summary.v1"
        and summary.get("result") == "passed"
        and summary.get("fixture_scorecard_digest") == "8980c25ae5fcc9b19f786ed5648e181866805a25ecaaacb3f4779a03b5e84049"
        and subject.get("schema_version") == "cyberboss.cb410.subject.v1"
        and subject.get("summary_sha256") == sha256(PROJECT / "docs/evidence/CB-410/summary.json"),
    )


def validate_cb400_anchor(errors: list[str]) -> None:
    closure = "55192340a3bc80ac979e283a5308daee9158ad3e"
    report(errors, "cb400_history", git("merge-base", "--is-ancestor", closure, "HEAD", check=False)[0] == 0)
    report(errors, "cb400_evidence_mutated", git("diff", "--quiet", closure, "--", "CyberBoss/docs/evidence/CB-400", check=False)[0] == 0)


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P4_3_CB_420.md").read_text(encoding="utf-8")
    body_load = "实际 Skill body load 为 " + chr(96) + "1" + chr(96)
    launchd = "macOS " + chr(96) + "launchd" + chr(96)
    for marker in (
        "P4.3 / CB-420", PRODUCT_VERSION, TASKPACK_VERSION, TASKPACK_ZIP_SHA256,
        "FA-AC-011", "FA-AC-017", "FA-AC-028", "FA-AC-032", "output-skill",
        "NATIVE_IF_PRESENT_ELSE_EMBEDDED", body_load, "SBOM", "Corresponding Source",
        "activation_pending", "Private-Database", launchd, "CB-430",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")


def validate_assurance_card(errors: list[str]) -> None:
    path = PROJECT / "docs/governance/SUPPLY_CHAIN_ASSURANCE_CB_420.md"
    card = path.read_text(encoding="utf-8")
    external_8765 = "external " + chr(96) + "8765" + chr(96) + " is unreachable"
    for marker in (
        PRODUCT_VERSION, "129 components", "GPL-3.0-only AND AGPL-3.0-only",
        "Corresponding Source package", external_8765,
        "Cloudflare Web Analytics", "activation_pending", "launchd dependency",
    ):
        if marker.lower() not in card.lower():
            errors.append(f"assurance_card:{marker}")
    report(errors, "assurance_card_hash", sha256(path) == ASSURANCE_CARD_SHA256)
    if SECRET_PATTERN.search(card) or "/Users/" in card or "/var/lib/" in card:
        errors.append("assurance_card_sensitive_or_absolute")


def validate_code(errors: list[str]) -> None:
    evaluator = (PROJECT / "app/src/services/assurance/canonical-security-assurance.js").read_text(encoding="utf-8")
    cli = (PROJECT / "app/scripts/security-assurance-suite.js").read_text(encoding="utf-8")
    app_test = (PROJECT / "app/test/canonical-security-assurance.test.js").read_text(encoding="utf-8")
    root_test = (PROJECT / "tests/security-assurance-suite.test.js").read_text(encoding="utf-8")
    backup_test = (PROJECT / "app/test/canonical-backup-runtime.test.js").read_text(encoding="utf-8")
    for marker in (
        "ASSURANCE_SCHEMA", "SOURCE_PACKAGE_SCHEMA", "buildSecurityAssurance",
        "buildCorrespondingSourcePackage", "scanTextForHighConfidenceSecret",
        "assertSourceClosure", "activation_pending", "Cloudflare Web Analytics",
        "external_8765", "corresponding_source_complete", "unaccepted_p0_p1_findings",
        "SKIPPED_DIRECTORIES", "node_modules", "ASSURANCE_HIGH_CONFIDENCE_SECRET",
    ):
        if marker not in evaluator:
            errors.append(f"evaluator_marker:{marker}")
    for marker in ("--mode=", "SECURITY_ASSURANCE_EXTERNAL_RELEASE_DISABLED", "SECURITY_ASSURANCE=PASS"):
        if marker not in cli:
            errors.append(f"cli_marker:{marker}")
    for marker in (
        "secret-free", "source-complete", "activation-pending",
        "license closure mutation", "parallel archive",
    ):
        if marker.lower() not in app_test.lower():
            errors.append(f"app_test_marker:{marker}")
    for marker in ("local deterministic", "activation_pending", "EXTERNAL_RELEASE_DISABLED"):
        if marker.lower() not in root_test.lower():
            errors.append(f"root_test_marker:{marker}")
    private_marker = "-----BEGIN" + " PRIVATE KEY-----"
    report(errors, "backup_fixture_literal_private_marker", private_marker not in backup_test)
    forbidden = (
        "settimeout(", "setinterval(", "sleep(", "launchctl", "launchdaemon",
        "com.apple.launchd", "fetch(", "https.request", "http.request", "websocket",
        "systemctl", "codexrpcclient", "runtimeadapter", "child_process",
    )
    for label, content in (("evaluator", evaluator), ("cli", cli)):
        for marker in forbidden:
            if marker in content.lower():
                errors.append(f"forbidden_runtime:{label}:{marker}")


def expected_assurance() -> dict[str, Any]:
    sources = [
        {
            "id": "cyberboss",
            "bundle_path": "app",
            "bundle_manifest": "docs/evidence/CB-000/manifests/bundle-cyberboss.sha256",
            "bundle_manifest_sha256": "ddab31c724f4b8d97a6196d6d7f71a7347b7f715aa6a3db5fe54815c6fbbadd9",
            "compliance_expression": "AGPL-3.0-only",
            "license_sha256": "526520455b0c01e09c1a23f6322a11d9e867de44dc833de8a94af6766dced64b",
        },
        {
            "id": "timeline-for-agent",
            "bundle_path": "vendor/timeline-for-agent",
            "bundle_manifest": "docs/evidence/CB-000/manifests/bundle-timeline-for-agent.sha256",
            "bundle_manifest_sha256": "9ab9bb47b5b7a0222ebb9cda56d96839e37d780e77359dff6a3cfc081de40986",
            "compliance_expression": "AGPL-3.0-only",
            "license_sha256": "526520455b0c01e09c1a23f6322a11d9e867de44dc833de8a94af6766dced64b",
        },
        {
            "id": "whereabouts-mcp",
            "bundle_path": "vendor/whereabouts-mcp",
            "bundle_manifest": "docs/evidence/CB-000/manifests/bundle-whereabouts-mcp.sha256",
            "bundle_manifest_sha256": "13f55a13f1891cc859fde7f8b5177a85b9e01904a555265479c2d9c92d8ffe2c",
            "compliance_expression": "GPL-3.0-only AND AGPL-3.0-only",
            "license_sha256": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
        },
    ]
    report_data = {
        "schema_version": ASSURANCE_SCHEMA,
        "product_version": PRODUCT_VERSION,
        "taskpack_version": TASKPACK_VERSION,
        "evaluation_mode": "local_deterministic_read_only",
        "security": {
            "scanned_source_file_count": 107,
            "high_confidence_secret_hits": 0,
            "environment_file_hits": 0,
            "unaccepted_p0_p1_findings": 0,
            "control_plane_llm_calls": 0,
            "operations_llm_calls": 0,
            "macos_launchd_dependency": False,
        },
        "sbom": {
            "canonical_inventory": "docs/evidence/CB-000/dependency-license-inventory.json",
            "inventory_sha256": "ac17df609417c8bff6612cf9191ae64768a98d828b54cc89eb1a382c550cef3a",
            "lockfile_sha256": "0932f1d169965da5453e0a5803457988840200b2489e914e3ace5238f714f555",
            "component_count": 129,
            "unresolved_license_count": 0,
            "strict_dual_license_component_count": 1,
            "component_digest": "2f3a85d0a37436ffc8b14653bd86db776a25a8bb797cad4e5f5df62484923538",
        },
        "corresponding_source": {
            "schema_version": SOURCE_PACKAGE_SCHEMA,
            "source_count": 3,
            "source_ids": ["cyberboss", "timeline-for-agent", "whereabouts-mcp"],
            "source_lock_sha256": "796dd31d9d4e8b44f178b9243b28e852017437c8983e45a1f731788173086fbf",
            "release_source_file_count": 286,
            "release_source_manifest_digest": SOURCE_MANIFEST_DIGEST,
            "original_source_and_license_preserved": True,
            "strict_license_expression": "AGPL-3.0-only AND GPL-3.0-only",
            "upstream_clarification_received": False,
            "corresponding_source_complete": True,
            "distribution_state": "activation_pending",
            "sources": sources,
        },
        "access_and_analytics_privacy": {
            "access_boundary": "existing_contract_verified",
            "anonymous_or_origin_bypass": "denied_by_existing_contract",
            "external_8765": "unreachable",
            "analytics_provider": "Cloudflare Web Analytics",
            "analytics_state": "activation_pending",
            "safe_aggregate_payload_count": 3,
            "forbidden_analytics_payloads_rejected": 5,
            "second_analytics_database_allowed": False,
        },
        "external_activation": {
            "cloudflare_web_analytics": "activation_pending",
            "release_distribution": "activation_pending",
            "real_cloudflare_operations": 0,
            "network_or_provider_operations": 0,
        },
    }
    report_data["report_digest"] = REPORT_DIGEST
    report_data["status"] = "passed"
    return report_data


def run_clean_validation(errors: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-cb420-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("assurance_unit", ["node", "--test", "test/canonical-security-assurance.test.js"], PROJECT / "app", ("fail 0",), 300),
            ("assurance_cli", ["node", "app/scripts/security-assurance-suite.js", "evaluate", "--mode=local"], PROJECT, ("SECURITY_ASSURANCE=PASS", REPORT_DIGEST), 300),
            ("assurance_root_cli", ["node", "--test", "tests/security-assurance-suite.test.js"], PROJECT, ("fail 0",), 300),
            ("secret_scan", [sys.executable, str(KIT / "scripts/secret_scan.py"), "--repo", str(REPO), "--scope", "CyberBoss"], REPO, ('"result": "passed"', '"p0_findings": 0', '"p1_findings": 0'), 600),
            ("access_domain", ["node", "--test", "test/canonical-access-domain.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("workspace_scope", ["node", "--test", "test/workspace-scope.test.js"], PROJECT / "app", ("fail 0",), 300),
            ("approval_policy", ["node", "--test", "test/codex-approval.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("cloud_runtime_boundary", ["node", "--test", "tests/cloud-runtime-version.test.js"], PROJECT, ("fail 0",), 600),
            ("backup_privacy", ["node", "--test", "test/canonical-backup-runtime.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("cb410_anchor", ["git", "diff", "--quiet", CB410_CLOSURE, "--", "CyberBoss/docs/evidence/CB-410"], REPO, (), 300),
            ("cb400_anchor", ["git", "diff", "--quiet", "55192340a3bc80ac979e283a5308daee9158ad3e", "--", "CyberBoss/docs/evidence/CB-400"], REPO, (), 300),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_regression", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
            ("identity_scope", [sys.executable, str(KIT / "tests/test_identity_scope.py")], REPO, ("OK",), 300),
            (
                "config",
                ["node", str(KIT / "tests/validate_config.js"), "--allow-placeholders", str(KIT / "config/cyberboss.env.example"), str(KIT / "config/workspaces.json.example")],
                REPO,
                ("CONFIG_VALIDATION=PASS",),
                300,
            ),
            ("dag", [sys.executable, str(KIT / "tests/validate_task_dag.py"), str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml")], REPO, ("DAG_VALIDATION=PASS tasks=30 stages=6",), 300),
            ("traceability", [sys.executable, str(KIT / "tests/validate_traceability.py"), str(PACK)], REPO, ("TRACEABILITY_VALIDATION=PASS requirements=53",), 300),
            ("no_wait", [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)], REPO, ("NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0",), 300),
            ("taskpack", [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)], REPO, ("TASKPACK_VALIDATION=PASS", "seven_is_minimum_not_limit=true"), 300),
        ]
        commands = [run_command(name, command, cwd, environment, errors, markers=markers, timeout=timeout) for name, command, cwd, markers, timeout in specs]
        return {
            "credential_named_environment_keys_removed": removed_count,
            "network_or_provider_operations": 0,
            "real_time_waits": 0,
            "commands": commands,
        }


def validate_subject_and_evidence(errors: list[str]) -> str | None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_missing")
        return None
    inventory = {candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()}
    if inventory != FINAL_EVIDENCE:
        errors.append(f"evidence_inventory:{sorted(inventory)}")
        return None
    summary_path = EVIDENCE / "summary.json"
    subject_path = EVIDENCE / "subject.json"
    try:
        summary = load_json(summary_path)
        subject = load_json(subject_path)
    except (OSError, ValueError, TypeError):
        errors.append("evidence_json")
        return None
    implementation_commit = str(subject.get("implementation_commit") or "")
    implementation_tree = str(subject.get("implementation_tree") or "")
    report(
        errors,
        "subject_contract",
        bool(re.fullmatch(r"[0-9a-f]{40}", implementation_commit))
        and subject.get("schema_version") == "cyberboss.cb420.subject.v1"
        and subject.get("task_id") == "CB-420"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("cb_410_closure_commit") == CB410_CLOSURE
        and subject.get("cb_410_tree") == CB410_TREE
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1] == implementation_tree
        and git("merge-base", "--is-ancestor", CB410_CLOSURE, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("assurance_card_sha256") == ASSURANCE_CARD_SHA256
        and subject.get("deployment_release_pointer") == "activation_pending"
        and subject.get("real_private_database_operations") == 0
        and subject.get("real_r2_operations") == 0
        and subject.get("real_cloudflare_operations") == 0
        and subject.get("real_oci_operations") == 0
        and subject.get("real_service_operations") == 0
        and subject.get("control_plane_llm_calls") == 0
        and subject.get("operations_llm_calls") == 0
        and subject.get("macos_launchd_dependency") is False,
    )
    report(
        errors,
        "summary_contract",
        summary.get("schema_version") == "cyberboss.cb420.closure-summary.v1"
        and summary.get("task_id") == "CB-420"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("cb_410_closure_commit") == CB410_CLOSURE
        and summary.get("cb_410_tree") == CB410_TREE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("assurance_card_sha256") == ASSURANCE_CARD_SHA256
        and summary.get("security_assurance_report") == expected_assurance()
        and summary.get("acceptance") == {oracle: "passed" for oracle in ACCEPTANCE}
        and summary.get("local_validation") == LOCAL_VALIDATION
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("external_activation") == EXTERNAL_ACTIVATION
        and summary.get("real_private_database_operations") == 0
        and summary.get("real_r2_operations") == 0
        and summary.get("real_cloudflare_operations") == 0
        and summary.get("real_oci_operations") == 0
        and summary.get("real_service_operations") == 0
        and summary.get("control_plane_llm_calls") == 0
        and summary.get("operations_llm_calls") == 0
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("next_native_node") == "CB-430",
    )
    for candidate in EVIDENCE.iterdir():
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")
    return implementation_commit


def validate_commit_boundaries(implementation_commit: str | None, final: bool, errors: list[str]) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", CB410_CLOSURE, implementation_commit, check=False)[0] == 0)
    report(errors, "implementation_inventory", commit_paths(implementation_commit) == IMPLEMENTATION_PATHS)
    if final:
        report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", implementation_commit, "HEAD", check=False)[0] == 0)
        closure_paths = set(filter(None, git("diff", "--name-only", implementation_commit, "HEAD")[1].splitlines()))
        report(errors, "closure_atomic_inventory", closure_paths == CLOSURE_PATHS)


def validate(final: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    branch = git("branch", "--show-current")[1]
    report(errors, "branch_scope", branch.startswith("codex/cyberboss-"))
    report(errors, "worktree_dirty", not git("status", "--porcelain=v1", "--untracked-files=all")[1])
    report(errors, "nested_git_repository", not list(PROJECT.rglob(".git")))
    report(errors, "gitlink", not any(line.startswith("160000 ") for line in git("ls-files", "-s", "CyberBoss")[1].splitlines()))
    source = Path(__file__).read_text(encoding="utf-8")
    report(errors, "validator_no_sleep", all(marker not in source for marker in ("time" + ".sleep", "asyncio" + ".sleep")))
    report(errors, "diff_check", git("diff", "--check", CB410_CLOSURE, "HEAD", check=False)[0] == 0)
    validate_state(final, errors)
    validate_cb410_anchor(errors)
    validate_cb400_anchor(errors)
    validate_contract(errors)
    validate_assurance_card(errors)
    validate_code(errors)
    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)
    matrix = run_clean_validation(errors)
    implementation_commit = validate_subject_and_evidence(errors) if final else git("rev-parse", "HEAD")[1]
    validate_commit_boundaries(implementation_commit, final, errors)
    return errors, {
        "mode": "final" if final else "prepare",
        "branch": branch,
        "commands": len(matrix["commands"]),
        "errors": len(errors),
        "assurance_digest": REPORT_DIGEST,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Validate CB-420 implementation before closure evidence.")
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("CB420_VALIDATION=FAIL")
        return 1
    print("CB420_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
