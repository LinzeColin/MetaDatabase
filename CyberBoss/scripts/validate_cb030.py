#!/usr/bin/env python3
"""Fail-closed validation for P0.4 / CB-030."""

from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


BASE_COMMIT = "1c66c768866f1be485d03e232e9552951ac7e1f4"
EXPECTED_CODEX_VERSION = "0.146.0-alpha.3.1"
EXPECTED_OVH_TARGET_HASH = "7865f743d174"
ALLOWED_EXACT = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/scripts/validate_cb030.py",
    "CyberBoss/docs/governance/RUN_CONTRACT_P0_4_CB_030.md",
    "CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md",
    "CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md",
    "CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/auth_activation_check.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/secret_scan.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/codex-app-server-simulator.mjs",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/weixin-ilink-simulator.mjs",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/simulator-contract.test.mjs",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_external_adapters.py",
}
ALLOWED_PREFIXES = ("CyberBoss/docs/evidence/CB-030/",)
FORBIDDEN_STATUS = re.compile(
    r"\bwaiting(?:_for_(?:credentials|user|soak))?\b|observe_for_(?:7|30)_days",
    re.IGNORECASE,
)
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


def run(command: list[str], cwd: Path, timeout: int = 300) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )
    return result.returncode, result.stdout


def png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError(f"invalid_png:{path.name}")
    return struct.unpack(">II", raw[16:24])


def changed_paths(repo: Path) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", BASE_COMMIT, "--"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    paths = set(result.stdout.splitlines())
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    for raw in status.stdout.splitlines():
        value = raw[3:]
        paths.update(value.split(" -> "))
    return {path for path in paths if path}


def validate(project: Path) -> tuple[list[str], list[str]]:
    repo = project.parent
    pack = project / "docs/product_design/v0.0.0.4"
    kit = pack / "implementation-kit"
    evidence = project / "docs/evidence/CB-030"
    errors: list[str] = []
    reports: list[str] = []

    def expect(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    required = [
        project / "docs/governance/RUN_CONTRACT_P0_4_CB_030.md",
        project / "scripts/validate_cb030.py",
        evidence / "auth-gates.md",
        evidence / "auth-probe.local.redacted.json",
        evidence / "auth-probe.ovh.redacted.json",
        evidence / "redacted-command-output.txt",
        evidence / "simulator-contract.md",
        evidence / "wechat-roundtrip.fixture.png",
        evidence / "wechat-screenshot-evidence.md",
        evidence / "secret-scan.json",
        evidence / "security-report.md",
        evidence / "VALIDATION_REPORT.md",
        kit / "scripts/auth_activation_check.py",
        kit / "simulators/weixin-ilink-simulator.mjs",
        kit / "simulators/codex-app-server-simulator.mjs",
        kit / "tests/simulator-contract.test.mjs",
    ]
    for path in required:
        expect(path.is_file(), f"required_file:{path.relative_to(project)}")
    if any(not path.is_file() for path in required):
        return errors, reports

    origin = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    expect(origin == "git@github.com:LinzeColin/MetaDatabase.git", "git_origin")
    expect(not any(project.rglob(".git")), "nested_git_repository")

    state = load_json(project / "machine/facts/task_state.json")
    statuses = {item["id"]: item["status"] for item in state["tasks"]}
    for task_id in ("CB-000", "CB-010", "CB-020", "CB-030"):
        expect(statuses.get(task_id) == "passed", f"{task_id.lower()}_dependency")
    expect(state.get("current_run", {}).get("run_id") == "P0.4", "current_run_id")
    expect(state.get("current_run", {}).get("task_id") == "CB-030", "current_task_id")
    expect(state.get("current_run", {}).get("status") == "passed", "current_run_state")
    expect(
        all(
            item["status"] == "not_started"
            for item in state["tasks"]
            if item["id"] not in {"CB-000", "CB-010", "CB-020", "CB-030"}
        ),
        "later_tasks_started",
    )
    expect(all(value == "not_started" for value in state["pass_gates"].values()), "pass_gate_started")
    expect(FORBIDDEN_STATUS.search(json.dumps(state)) is None, "wait_status_present")

    source_lock = load_json(project / "machine/source-lock.json")
    expect(
        source_lock.get("codex_cli", {}).get("exact_tested_version")
        == EXPECTED_CODEX_VERSION,
        "codex_version_pin",
    )
    upstream = source_lock.get("upstream_relationship") or {}
    expect(upstream and not any(upstream.values()), "upstream_relationship_not_severed")
    conflict = source_lock.get("whereabouts_license_conflict") or {}
    expect(
        conflict.get("compliance_expression")
        == "GPL-3.0-only AND AGPL-3.0-only",
        "license_conflict_expression",
    )
    expect(conflict.get("upstream_clarification_received") is False, "upstream_clarification_claim")

    local = load_json(evidence / "auth-probe.local.redacted.json")
    expect(local.get("claim_level") == "read_only_probe", "local_probe_claim")
    expect(local.get("probe_scope") == "local", "local_probe_scope")
    expect(local.get("external_mutation_performed") is False, "local_probe_mutation")
    expect(local.get("credential_content_read") is False, "local_probe_read")
    expect(local.get("credential_values_emitted") is False, "local_probe_emit")
    local_codex = local.get("codex") or {}
    expect(local_codex.get("version") == EXPECTED_CODEX_VERSION, "local_codex_version")
    expect(local_codex.get("login_classification") == "authenticated", "local_codex_login")
    expect(local_codex.get("target_adapter_state") == "activation_pending", "local_target_claim")
    expect(
        local_codex.get("auth_file", {}).get("group_or_other_bits_zero") is True,
        "local_codex_auth_mode",
    )
    expect(
        local.get("wechat", {}).get("target_adapter_state") == "activation_pending",
        "local_wechat_claim",
    )

    ovh = load_json(evidence / "auth-probe.ovh.redacted.json")
    expect(ovh.get("claim_level") == "read_only_probe", "ovh_probe_claim")
    expect(ovh.get("probe_scope") == "authorized_ovh_staging", "ovh_probe_scope")
    expect(ovh.get("external_mutation_performed") is False, "ovh_probe_mutation")
    expect(ovh.get("credential_content_read") is False, "ovh_probe_read")
    expect(ovh.get("credential_values_emitted") is False, "ovh_probe_emit")
    expect(
        ovh.get("target", {}).get("target_id_sha256") == EXPECTED_OVH_TARGET_HASH,
        "ovh_target_identity",
    )
    transport = ovh.get("transport") or {}
    expect(transport.get("ssh_auth_mode") == "key_only_batch", "ovh_ssh_auth")
    expect(transport.get("strict_host_key_checking") is True, "ovh_host_key")
    expect(transport.get("remote_persistent_write") is False, "ovh_remote_write")
    ovh_codex = ovh.get("codex") or {}
    ovh_wechat = ovh.get("wechat") or {}
    expect(ovh_codex.get("cli_present") is False, "ovh_codex_cli_state")
    expect(ovh_codex.get("auth_file", {}).get("present") is False, "ovh_codex_auth_state")
    expect(ovh_codex.get("target_adapter_state") == "activation_pending", "ovh_codex_claim")
    expect(
        ovh_wechat.get("state_directory", {}).get("present") is False,
        "ovh_wechat_state_dir",
    )
    expect(ovh_wechat.get("target_adapter_state") == "activation_pending", "ovh_wechat_claim")

    scanner = load_json(evidence / "secret-scan.json")
    expect(scanner.get("result") == "passed", "secret_scan_result")
    expect(scanner.get("known_secret_values_loaded") == 7, "secret_scan_known_values")
    expect(scanner.get("known_secret_hits") == 0, "known_secret_hit")
    expect(scanner.get("forbidden_pattern_hits") == 0, "secret_pattern_hit")
    expect(scanner.get("p0_findings") == 0, "security_p0")
    expect(scanner.get("p1_findings") == 0, "security_p1")
    expect(scanner.get("secret_values_emitted") is False, "scanner_secret_output")

    auth_sheet = (evidence / "auth-gates.md").read_text(encoding="utf-8")
    simulator_report = (evidence / "simulator-contract.md").read_text(encoding="utf-8")
    screenshot_report = (evidence / "wechat-screenshot-evidence.md").read_text(
        encoding="utf-8"
    )
    validation_report = (evidence / "VALIDATION_REPORT.md").read_text(
        encoding="utf-8"
    )
    security_report = (evidence / "security-report.md").read_text(encoding="utf-8")
    all_evidence_text = "\n".join(
        [auth_sheet, simulator_report, screenshot_report, validation_report, security_report]
    )
    expect(SECRET_PATTERN.search(all_evidence_text) is None, "evidence_secret_pattern")
    expect("codex login --device-auth" in auth_sheet, "device_auth_command")
    expect("npm run login" in auth_sheet, "wechat_qr_command")
    expect("activation_pending" in auth_sheet, "auth_pending_state")
    expect("SIMULATOR FIXTURE" in screenshot_report, "screenshot_fixture_claim")
    expect("ERR_MODULE_NOT_FOUND" in simulator_report, "baseline_failure_record")
    expect("tests=4 pass=4 fail=0" in simulator_report, "simulator_test_summary")
    expect("- State: `PASS`" in validation_report, "validation_report_state")
    expect("| P0 | 0 |" in security_report, "security_report_p0")
    expect("| P1 | 0 |" in security_report, "security_report_p1")

    try:
        width, height = png_dimensions(evidence / "wechat-roundtrip.fixture.png")
    except (OSError, ValueError) as error:
        errors.append(str(error))
    else:
        expect((width, height) == (1280, 720), "screenshot_dimensions")

    architecture_text = (
        project / "docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md"
    ).read_text(encoding="utf-8")
    activation_text = (
        project
        / "docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md"
    ).read_text(encoding="utf-8")
    expect("/var/lib/cyberboss/wechat" not in architecture_text, "stale_wechat_path_architecture")
    expect("/var/lib/cyberboss/wechat" not in activation_text, "stale_wechat_path_activation")
    expect("/var/lib/cyberboss/accounts" in architecture_text, "wechat_path_architecture")
    expect("/var/lib/cyberboss/accounts" in activation_text, "wechat_path_activation")

    for path in sorted(changed_paths(repo)):
        if path not in ALLOWED_EXACT and not path.startswith(ALLOWED_PREFIXES):
            errors.append(f"run_scope_violation:{path}")
        if path.startswith(("CyberBoss/app/", "CyberBoss/vendor/")):
            errors.append(f"fixed_source_changed:{path}")

    clean_fixture_report: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="cyberboss-cb030-auth-") as raw_temp:
        temp = Path(raw_temp)
        output = temp / "probe.json"
        returncode, command_output = run(
            [
                sys.executable,
                str(kit / "scripts/auth_activation_check.py"),
                "--mode",
                "local",
                "--codex-home",
                str(temp / "missing-codex-home"),
                "--wechat-state-dir",
                str(temp / "missing-wechat-state"),
                "--output",
                str(output),
                "--quiet",
            ],
            repo,
        )
        reports.append(
            f"auth_clean_fixture:exit={returncode}:tail="
            f"{command_output.strip().splitlines()[-1] if command_output.strip() else '(empty)'}"
        )
        if returncode != 0 or not output.is_file():
            errors.append("auth_clean_fixture_failed")
        else:
            clean_fixture_report = load_json(output)
    expect(
        clean_fixture_report.get("codex", {}).get("target_adapter_state")
        == "activation_pending",
        "clean_fixture_codex_state",
    )
    expect(
        clean_fixture_report.get("wechat", {}).get("target_adapter_state")
        == "activation_pending",
        "clean_fixture_wechat_state",
    )
    expect(
        clean_fixture_report.get("external_mutation_performed") is False,
        "clean_fixture_mutation",
    )

    commands = [
        (
            "simulator_contract",
            [
                "node",
                "--test",
                str(kit / "tests/simulator-contract.test.mjs"),
            ],
        ),
        (
            "app_check",
            ["npm", "--prefix", str(project / "app"), "run", "check"],
        ),
        (
            "app_test",
            ["npm", "--prefix", str(project / "app"), "test"],
        ),
        (
            "scope_policy",
            [sys.executable, str(kit / "scripts/scope_policy.py"), "validate"],
        ),
        (
            "identity_scope",
            [sys.executable, str(kit / "tests/test_identity_scope.py")],
        ),
        (
            "external_adapters",
            [sys.executable, str(kit / "tests/test_external_adapters.py")],
        ),
        (
            "access_policy",
            ["node", "--test", str(kit / "tests/access-policy-contract.test.js")],
        ),
        (
            "secret_scan_live",
            [
                sys.executable,
                str(kit / "scripts/secret_scan.py"),
                "--repo",
                str(repo),
                "--scope",
                "CyberBoss",
            ],
        ),
        (
            "cb000",
            [sys.executable, str(project / "scripts/validate_cb000.py")],
        ),
        (
            "task_dag",
            [
                sys.executable,
                str(kit / "tests/validate_task_dag.py"),
                str(pack / "04_TASK_DAG_EXECUTION_PACK.yaml"),
            ],
        ),
        (
            "traceability",
            [
                sys.executable,
                str(kit / "tests/validate_traceability.py"),
                str(pack),
            ],
        ),
        (
            "no_wait",
            [
                sys.executable,
                str(kit / "tests/validate_no_wait.py"),
                str(pack),
            ],
        ),
        (
            "taskpack",
            [
                sys.executable,
                str(kit / "tests/validate_taskpack.py"),
                str(pack),
            ],
        ),
        (
            "prestage",
            [sys.executable, str(project / "scripts/validate_prestage0.py")],
        ),
    ]
    for label, command in commands:
        returncode, output = run(command, repo)
        tail = output.strip().splitlines()[-1] if output.strip() else "(empty)"
        reports.append(f"{label}:exit={returncode}:tail={tail}")
        if returncode != 0:
            errors.append(f"command_failed:{label}")
            errors.extend(f"{label}:{line}" for line in output.splitlines()[-12:])
        if label == "simulator_contract" and "pass 4" not in output:
            errors.append("simulator_contract_count")
        if label == "app_test" and "pass 155" not in output:
            errors.append("app_test_count")

    process_result = subprocess.run(
        ["ps", "ax", "-o", "command="],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    simulator_processes = [
        line
        for line in process_result.stdout.splitlines()
        if re.search(
            r"node .*CyberBoss/.*/(?:weixin-ilink|codex-app-server)-simulator[.]mjs",
            line,
        )
    ]
    expect(not simulator_processes, "simulator_process_leak")

    return errors, reports


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    errors, reports = validate(project)
    for report in reports:
        print(f"COMMAND={report}")
    for error in sorted(set(errors)):
        print(f"ERROR={error}")
    if errors:
        print("CB030_REPO_VALIDATION=FAIL")
        return 1
    state = load_json(project / "machine/facts/task_state.json")
    task_status = next(
        item["status"] for item in state["tasks"] if item["id"] == "CB-030"
    )
    print(
        "CB030_REPO_VALIDATION=PASS "
        f"task_state={task_status} "
        "real_codex=activation_pending real_wechat=activation_pending "
        "simulator_tests=4 app_tests=155 external_writes=0 "
        "p0_findings=0 p1_findings=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
