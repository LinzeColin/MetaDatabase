#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P1.5 / CB-140."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-140"
BASE_COMMIT = "20405812e4ebfc51d59093b5916dd624317309a7"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"

IMPLEMENTATION_PATHS = {
    "CyberBoss/app/package.json",
    "CyberBoss/app/scripts/cloud-supervisor.js",
    "CyberBoss/app/src/adapters/channel/weixin/index.js",
    "CyberBoss/app/src/adapters/channel/weixin/message-utils.js",
    "CyberBoss/app/src/core/app.js",
    "CyberBoss/app/src/core/config.js",
    "CyberBoss/app/src/core/inbound-turn.js",
    "CyberBoss/app/src/core/stream-delivery.js",
    "CyberBoss/app/src/core/walking-skeleton-trace.js",
    "CyberBoss/app/test/cloud-walking-skeleton-live.test.js",
    "CyberBoss/app/test/cloud-walking-skeleton.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P1_5_CB_140.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-cloud-walking-skeleton.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-walking-skeleton-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-walking-skeleton.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-walking-skeleton-acceptance.mjs",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb140.py",
    "CyberBoss/tests/cloud-walking-skeleton.test.js",
}

CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/machine/facts/task_state.json",
}

FINAL_EVIDENCE = {
    "VALIDATION_REPORT.md",
    "artifact-checksums.txt",
    "artifact-manifest.json",
    "correlated-trace.redacted.ndjson",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "latency-baseline.md",
    "mac-offline.redacted.json",
    "network-scan.redacted.json",
    "publication-check.json",
    "rollback-plan.json",
    "security-report.json",
    "source-modification-record.json",
    "target-preflight.redacted.json",
    "validation.txt",
    "walking-skeleton.redacted.json",
    "wechat-roundtrip.fixture.png",
    "wechat-screenshot-evidence.md",
}

FROZEN_PATHS = [
    "CyberBoss/vendor",
    "CyberBoss/docs/evidence/CB-000",
    "CyberBoss/docs/evidence/CB-010",
    "CyberBoss/docs/evidence/CB-020",
    "CyberBoss/docs/evidence/CB-030",
    "CyberBoss/docs/evidence/CB-040",
    "CyberBoss/docs/evidence/CB-100",
    "CyberBoss/docs/evidence/CB-110",
    "CyberBoss/docs/evidence/CB-120",
    "CyberBoss/docs/evidence/CB-130",
    "CyberBoss/docs/evidence/PG-0",
    "CyberBoss/docs/product_design/v0.0.0.4/00_README_FIRST.md",
    "CyberBoss/docs/product_design/v0.0.0.4/01_PRFAQ_STRATEGY_OKR.md",
    "CyberBoss/docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md",
    "CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
    "CyberBoss/docs/product_design/v0.0.0.4/05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md",
    "CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md",
    "CyberBoss/docs/product_design/v0.0.0.4/07_RESEARCH_COMPETITOR_UPSTREAM_FINDINGS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/08_UPSTREAM_CODE_CHANGE_MAP.md",
    "CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/10_TRACEABILITY_RELEASE_CHECKLIST.md",
    "CyberBoss/docs/product_design/v0.0.0.4/11_AGENT_EXECUTION_PROMPTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/12_CURRENT_ROADMAP.md",
    "CyberBoss/docs/product_design/v0.0.0.4/13_STAGE2B_STAGE3_UPGRADES.md",
    "CyberBoss/docs/product_design/v0.0.0.4/14_PURSUING_GOAL.txt",
    "CyberBoss/machine/source-lock.json",
    "CyberBoss/LICENSE",
    "CyberBoss/THIRD_PARTY_NOTICES.md",
    "CyberBoss/UPSTREAM_PROVENANCE.md",
]

SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bwxid_[A-Za-z0-9_-]+\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            f"{result.stderr.strip()[:180]}"
        )
    return result.returncode, result.stdout.rstrip()


def changed_paths() -> set[str]:
    paths = set(
        filter(None, git("diff", "--name-only", BASE_COMMIT, "HEAD")[1].splitlines())
    )
    status = git("status", "--porcelain=v1", "--untracked-files=all")[1]
    for raw in status.splitlines():
        value = raw[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        if value:
            paths.add(value)
    return paths


def verify_manifest(path: Path, errors: list[str]) -> None:
    root = path.parent
    entries: dict[str, str] = {}
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            errors.append(f"manifest_line:{path.relative_to(REPO)}:{number}")
            continue
        digest, relative = match.groups()
        if (
            relative in entries
            or relative.startswith("/")
            or ".." in Path(relative).parts
        ):
            errors.append(f"manifest_path:{path.relative_to(REPO)}:{relative}")
            continue
        entries[relative] = digest
    actual = {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file()
        and candidate != path
        and "__pycache__" not in candidate.parts
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def run_command(
    name: str,
    args: list[str],
    errors: list[str],
    *,
    cwd: Path = REPO,
) -> None:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        tail = result.stdout.strip().splitlines()[-1:] or ["no_output"]
        errors.append(f"command:{name}:{result.returncode}:{tail[0][:180]}")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {item["id"]: item["status"] for item in state["tasks"]}
    expected_passed = {
        "CB-000",
        "CB-010",
        "CB-020",
        "CB-030",
        "CB-040",
        "CB-100",
        "CB-110",
        "CB-120",
        "CB-130",
    }
    if final:
        expected_passed.add("CB-140")
    for task_id, status in statuses.items():
        expected = "passed" if task_id in expected_passed else "not_started"
        if status != expected:
            errors.append(f"task_state:{task_id}:{status}:{expected}")
    gates = state.get("pass_gates") or {}
    if gates.get("PG-0") != "passed":
        errors.append("gate_pg0")
    for gate in ("PG-1", "PG-2", "PG-3", "PG-4", "PG-5"):
        if gates.get(gate) != "not_started":
            errors.append(f"gate_not_started:{gate}")
    current = state.get("current_run") or {}
    if final:
        expected = {
            "run_id": "P1.5",
            "gate_id": None,
            "task_id": "CB-140",
            "scope": "all_cloud_walking_skeleton",
            "status": "passed",
        }
        if current != expected:
            errors.append("state_current_run_final")
    elif (
        current.get("run_id") != "P1.4"
        or current.get("task_id") != "CB-130"
        or current.get("status") != "passed"
    ):
        errors.append("state_prepare_baseline")


def validate_final_evidence(errors: list[str]) -> None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_directory")
        return
    actual = {
        candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()
    }
    if actual != FINAL_EVIDENCE:
        errors.append("evidence_inventory")
        return

    implementation = load_json(EVIDENCE / "implementation-commit.json")
    implementation_commit = implementation.get("implementation_commit")
    if (
        implementation.get("task_id") != "CB-140"
        or implementation.get("phase") != "P1.5"
        or implementation.get("base_commit") != BASE_COMMIT
        or implementation.get("parent_commit") != BASE_COMMIT
        or not re.fullmatch(r"[0-9a-f]{40}", str(implementation_commit or ""))
        or implementation.get("built_from_clean_worktree") is not True
        or implementation.get("remote_publication") != "none"
    ):
        errors.append("evidence_implementation")
        return
    if git("rev-parse", f"{implementation_commit}^")[1] != BASE_COMMIT:
        errors.append("implementation_parent")
    if git("rev-parse", "HEAD^")[1] != implementation_commit:
        errors.append("closure_parent")

    manifest = load_json(EVIDENCE / "artifact-manifest.json")
    if (
        manifest.get("task_id") != "CB-140"
        or manifest.get("phase") != "P1.5"
        or manifest.get("release_commit") != implementation_commit
        or manifest.get("source", {}).get("license_expression") != STRICT_LICENSE
        or manifest.get("source", {}).get("corresponding_source_complete") is not True
        or manifest.get("source", {}).get("original_licenses_preserved") is not True
        or manifest.get("source", {}).get("upstream_clarification_received") is not False
        or manifest.get("deployment", {}).get("remote_publication") != "none"
        or manifest.get("deployment", {}).get("switch_current") is not False
        or manifest.get("walking_skeleton", {}).get("pg_1_executed") is not False
        or manifest.get("walking_skeleton", {}).get("stage_2_spool_claimed") is not False
    ):
        errors.append("evidence_artifact_manifest")

    walking = load_json(EVIDENCE / "walking-skeleton.redacted.json")
    if (
        walking.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or walking.get("target_address_persisted") is not False
        or walking.get("release_commit") != implementation_commit
        or walking.get("simulator_e2e", {}).get("successful_traces") != 10
        or walking.get("simulator_e2e", {}).get("expected_traces") != 10
        or walking.get("inbound_policy", {}).get("allowlist_unauthorized_runtime_calls") != 0
        or walking.get("inbound_policy", {}).get("boundary_32768_runtime_calls") != 1
        or walking.get("inbound_policy", {}).get("boundary_32769_runtime_calls") != 0
        or walking.get("latency", {}).get("sample_count") != 20
        or walking.get("latency", {}).get("p50_ms", 5000) >= 5000
        or walking.get("latency", {}).get("p95_ms", 10000) >= 10000
        or walking.get("real_adapters", {}).get("wechat") != "activation_pending"
        or walking.get("real_adapters", {}).get("codex") != "activation_pending"
        or walking.get("pg_1_executed") is not False
        or walking.get("stage_2_spool_claimed") is not False
        or walking.get("result") != "passed"
    ):
        errors.append("evidence_walking_skeleton")

    mac = load_json(EVIDENCE / "mac-offline.redacted.json")
    if (
        mac.get("mac_runtime_source_config_hits") != 0
        or mac.get("mac_process_argument_hits") != 0
        or mac.get("mac_connector_hits") != 0
        or mac.get("non_loopback_runtime_connections") != 0
        or mac.get("result") != "passed"
    ):
        errors.append("evidence_mac")
    network = load_json(EVIDENCE / "network-scan.redacted.json")
    if (
        network.get("non_loopback_listener_count") != 0
        or network.get("operator_external_scan") != "passed"
        or network.get("target_address_persisted") is not False
        or network.get("result") != "passed"
    ):
        errors.append("evidence_network")
    preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
    if (
        preflight.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or preflight.get("current_release_commit") != EXPECTED_CURRENT
        or preflight.get("workspace_head") != EXPECTED_WORKSPACE
        or preflight.get("service_active") is not False
        or preflight.get("service_enabled") is not False
        or preflight.get("result") != "passed"
    ):
        errors.append("evidence_preflight")
    install = load_json(EVIDENCE / "install-apply.redacted.json")
    if (
        install.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or install.get("release_commit") != implementation_commit
        or install.get("check_passed") is not True
        or install.get("apply_pass_count") != 2
        or install.get("verify_pass_count") != 1
        or install.get("current_changed") is not False
        or install.get("service_started_during_install") is not False
        or install.get("result") != "passed"
    ):
        errors.append("evidence_install")
    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("remote_branch_count") != 0
        or publication.get("pull_request_count") != 0
        or publication.get("release_count") != 0
        or publication.get("result") != "passed"
    ):
        errors.append("evidence_publication")
    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("secret_value_hits") != 0
        or security.get("raw_private_content_hits") != 0
        or security.get("real_credential_reads") != 0
        or security.get("real_provider_writes") != 0
        or security.get("private_database_operations") != 0
        or security.get("target_address_persisted") is not False
        or security.get("result") != "passed"
    ):
        errors.append("evidence_security")

    trace_lines = (
        EVIDENCE / "correlated-trace.redacted.ndjson"
    ).read_text(encoding="utf-8").splitlines()
    if not trace_lines:
        errors.append("evidence_trace_empty")
    for line in trace_lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            errors.append("evidence_trace_json")
            break
        if not re.fullmatch(r"cb140-[0-9a-f]{24}", str(record.get("trace_id", ""))):
            errors.append("evidence_trace_id")
            break
        if any(
            key in record
            for key in (
                "text",
                "message",
                "result",
                "sender_id",
                "account_id",
                "context_token",
                "thread_id",
                "turn_id",
            )
        ):
            errors.append("evidence_trace_raw_field")
            break

    png = EVIDENCE / "wechat-roundtrip.fixture.png"
    raw = png.read_bytes()
    if (
        len(raw) < 24
        or raw[:8] != b"\x89PNG\r\n\x1a\n"
        or raw[12:16] != b"IHDR"
    ):
        errors.append("evidence_png")
    else:
        width, height = struct.unpack(">II", raw[16:24])
        if width < 640 or height < 480:
            errors.append("evidence_png_dimensions")

    for path in EVIDENCE.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() == ".png":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            errors.append(f"evidence_secret:{path.name}")
        ipv4_values = re.findall(
            r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])",
            text,
        )
        if any(value != "127.0.0.1" for value in ipv4_values):
            errors.append(f"evidence_ipv4:{path.name}")


def validate(final: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    reports: list[str] = []

    if git("branch", "--show-current")[1] != EXPECTED_BRANCH:
        errors.append("branch")
    if git("remote")[1].splitlines() != ["origin"]:
        errors.append("remotes")
    if git("remote", "get-url", "origin")[1] != EXPECTED_ORIGIN:
        errors.append("origin")
    remote_code, remote = git(
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        f"refs/heads/{EXPECTED_BRANCH}",
        check=False,
    )
    if remote_code != 2 or remote:
        errors.append("remote_publication")

    allowed = IMPLEMENTATION_PATHS | CLOSURE_PATHS
    unexpected = sorted(
        path
        for path in changed_paths()
        if path not in allowed and not path.startswith("CyberBoss/docs/evidence/CB-140/")
    )
    if unexpected:
        errors.extend(f"unexpected_path:{path}" for path in unexpected)
    for frozen in FROZEN_PATHS:
        if git("diff", "--quiet", BASE_COMMIT, "HEAD", "--", frozen, check=False)[0] != 0:
            errors.append(f"frozen_path:{frozen}")

    contract = (
        PROJECT / "docs/governance/RUN_CONTRACT_P1_5_CB_140.md"
    ).read_text(encoding="utf-8")
    for required in (
        STRICT_LICENSE,
        "upstream_clarification_received=false",
        "不执行 `PG-1`",
        "activation_pending",
        "32768",
        "32769",
        "10",
        "20",
        "Mac-offline",
        "不创建新 repo",
    ):
        if required not in contract:
            errors.append(f"contract:{required}")

    ledger = load_json(PROJECT / "machine/facts/post-baseline-change-ledger.json")
    entries = [entry for entry in ledger.get("entries", []) if entry.get("task_id") == "CB-140"]
    if (
        len(entries) != 1
        or entries[0].get("base_commit") != BASE_COMMIT
        or ledger.get("strict_compliance_expression") != STRICT_LICENSE
        or ledger.get("upstream_clarification_received") is not False
    ):
        errors.append("modification_ledger")

    try:
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        verify_manifest(KIT / "MANIFEST.sha256", errors)
    except (OSError, ValueError) as error:
        errors.append(f"manifest_exception:{error}")

    validate_state(final, errors)
    if final:
        validate_final_evidence(errors)

    commands = [
        (
            "shell_syntax",
            [
                "bash",
                "-n",
                str(KIT / "scripts/install-cloud-process-family.sh"),
                str(KIT / "scripts/install-cloud-walking-skeleton.sh"),
                str(KIT / "scripts/accept-cloud-walking-skeleton.sh"),
                str(KIT / "scripts/run-cyberboss.sh"),
            ],
            REPO,
        ),
        (
            "builder_compile",
            [
                sys.executable,
                "-m",
                "py_compile",
                str(KIT / "scripts/build-cloud-process-artifacts.py"),
                str(KIT / "scripts/build-cloud-walking-skeleton-artifacts.py"),
            ],
            REPO,
        ),
        (
            "app_walking_tests",
            ["node", "--test", "test/cloud-walking-skeleton.test.js"],
            PROJECT / "app",
        ),
        (
            "root_walking_tests",
            ["node", "--test", "tests/cloud-walking-skeleton.test.js"],
            PROJECT,
        ),
        ("app_check", ["npm", "run", "check"], PROJECT / "app"),
        ("app_test", ["npm", "test"], PROJECT / "app"),
        (
            "prestage",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            REPO,
        ),
        (
            "dag",
            [
                sys.executable,
                str(KIT / "tests/validate_task_dag.py"),
                str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml"),
            ],
            REPO,
        ),
        (
            "traceability",
            [
                sys.executable,
                str(KIT / "tests/validate_traceability.py"),
                str(PACK),
            ],
            REPO,
        ),
        (
            "no_wait",
            [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)],
            REPO,
        ),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            REPO,
        ),
    ]
    for name, args, cwd in commands:
        run_command(name, args, errors, cwd=cwd)

    reports.extend(
        [
            f"mode={'final' if final else 'prepare'}",
            f"base_commit={BASE_COMMIT}",
            f"changed_paths={len(changed_paths())}",
            f"implementation_paths={len(IMPLEMENTATION_PATHS)}",
            f"evidence_required={len(FINAL_EVIDENCE)}",
            "license_expression=AGPL-3.0-only AND GPL-3.0-only",
            "upstream_clarification_received=false",
            "real_adapters=activation_pending",
            "pg_1_executed=false",
            "remote_publication=none",
        ]
    )
    return errors, reports


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--final", action="store_true")
    args = parser.parse_args()
    try:
        errors, reports = validate(final=args.final)
    except Exception as error:  # fail closed at the outermost boundary
        print(f"CB140_VALIDATION=FAIL exception={type(error).__name__}:{error}")
        return 2
    if errors:
        print("CB140_VALIDATION=FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("CB140_VALIDATION=PASS")
    for report in reports:
        print(f"- {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
