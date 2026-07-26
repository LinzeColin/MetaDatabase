#!/usr/bin/env python3
"""Fail-closed validation for P0.3 / CB-020."""

from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any


BASE_COMMIT = "2d99cc908b413d72e693563fd360686a867d6b92"
EXPECTED_PRIVATE_CLIENT_SHA256 = (
    "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa"
)
ALLOWED_EXACT = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/scripts/validate_cb020.py",
    "CyberBoss/docs/governance/RUN_CONTRACT_P0_3_CB_020.md",
    "CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md",
    "CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md",
    "CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cloudflare-access-policy.fixture.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/credential-slots.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/identity-scope.policy.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/provider-activation.example.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/cloudflare_adapter.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/oci_object_adapter.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/private_db_client_safe.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/scope_policy.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/secret_scan.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/object-store-simulator.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/private-db-simulator.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/provider-api-simulator.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/access-policy-contract.test.js",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/access-policy-fixture.html",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_external_adapters.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_identity_scope.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js",
}
ALLOWED_PREFIXES = ("CyberBoss/docs/evidence/CB-020/",)
FORBIDDEN_STATUS = re.compile(
    r"\bwaiting(?:_for_(?:credentials|user|soak))?\b|observe_for_(?:7|30)_days",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=180,
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
    evidence = project / "docs/evidence/CB-020"
    errors: list[str] = []
    command_reports: list[str] = []

    def expect(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    required = [
        project / "docs/governance/RUN_CONTRACT_P0_3_CB_020.md",
        project / "scripts/validate_cb020.py",
        evidence / "identity-scope.md",
        evidence / "provider-capability-observation.json",
        evidence / "access-fixture-evidence.md",
        evidence / "access-deny.fixture.png",
        evidence / "access-allow.fixture.png",
        evidence / "secret-scan.json",
        evidence / "security-report.md",
        evidence / "VALIDATION_REPORT.md",
        kit / "config/identity-scope.policy.json",
        kit / "config/credential-slots.json",
        kit / "config/cloudflare-access-policy.fixture.json",
        kit / "config/provider-activation.example.json",
        kit / "scripts/scope_policy.py",
        kit / "scripts/private_db_client_safe.py",
        kit / "scripts/cloudflare_adapter.py",
        kit / "scripts/oci_object_adapter.py",
        kit / "scripts/secret_scan.py",
        kit / "simulators/provider-api-simulator.py",
        kit / "tests/test_identity_scope.py",
        kit / "tests/test_external_adapters.py",
        kit / "tests/access-policy-contract.test.js",
    ]
    for path in required:
        expect(path.is_file(), f"required_file:{path.relative_to(project)}")
    if any(not path.is_file() for path in required):
        return errors, command_reports

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
    expect(statuses.get("CB-000") == "passed", "cb000_dependency")
    expect(statuses.get("CB-010") == "passed", "cb010_dependency")
    expect(statuses.get("CB-020") == "passed", "cb020_state")
    expect(state.get("current_run", {}).get("status") == "passed", "current_run_state")
    expect(
        all(
            item["status"] == "not_started"
            for item in state["tasks"]
            if item["id"] not in {"CB-000", "CB-010", "CB-020"}
        ),
        "later_tasks_started",
    )
    expect(all(value == "not_started" for value in state["pass_gates"].values()), "pass_gate_started")
    expect(FORBIDDEN_STATUS.search(json.dumps(state)) is None, "wait_status_present")

    observation = load_json(evidence / "provider-capability-observation.json")
    expect(observation.get("mode") == "read_only", "provider_mode")
    expect(observation.get("external_mutation_performed") is False, "provider_mutation")
    expect(observation.get("secret_values_emitted") is False, "provider_secret")
    cloudflare = observation.get("cloudflare") or {}
    expect(cloudflare.get("token_verify", {}).get("active_count") == 4, "cloudflare_tokens")
    expect(
        cloudflare.get("access_designated_token", {}).get("access_apps_read_http_status")
        == 200,
        "cloudflare_access_read",
    )
    expect(
        cloudflare.get("r2_d1_designated_token", {}).get("cross_service_read_observed")
        is True,
        "cloudflare_cross_service_read",
    )
    expect(
        cloudflare.get("r2_d1_designated_token", {}).get("real_write_status")
        == "hazard_blocked",
        "cloudflare_broad_write_not_blocked",
    )
    expect(cloudflare.get("target_dns_record_count") == 0, "cloudflare_target_dns")
    oci = observation.get("oci") or {}
    expect(oci.get("namespace_read_verified") is True, "oci_namespace")
    expect(oci.get("bucket_list_read_verified") is True, "oci_bucket_list")
    expect(oci.get("bucket_count") == 1, "oci_bucket_count")
    expect(oci.get("write_scope_attested") is False, "oci_write_attestation")
    private = observation.get("private_database") or {}
    expect(
        private.get("shared_client_sha256") == EXPECTED_PRIVATE_CLIENT_SHA256,
        "private_client_sha",
    )
    expect(
        private.get("private_database_clone_present_under_githubproject") is False,
        "private_database_clone",
    )
    expect(private.get("real_data_operation_performed") is False, "private_data_write")

    scanner = load_json(evidence / "secret-scan.json")
    expect(scanner.get("result") == "passed", "secret_scan_result")
    expect(scanner.get("known_secret_values_loaded", 0) >= 7, "secret_scan_known_values")
    expect(scanner.get("known_secret_hits") == 0, "known_secret_hit")
    expect(scanner.get("forbidden_pattern_hits") == 0, "secret_pattern_hit")
    expect(scanner.get("p0_findings") == 0, "security_p0")
    expect(scanner.get("p1_findings") == 0, "security_p1")
    expect(scanner.get("secret_values_emitted") is False, "scanner_secret_output")
    validation_report = (evidence / "VALIDATION_REPORT.md").read_text(
        encoding="utf-8"
    )
    security_report = (evidence / "security-report.md").read_text(encoding="utf-8")
    expect("- State: `PASS`" in validation_report, "validation_report_state")
    expect("| P0 | 0 |" in security_report, "security_report_p0")
    expect("| P1 | 0 |" in security_report, "security_report_p1")

    for name in ("access-deny.fixture.png", "access-allow.fixture.png"):
        try:
            width, height = png_dimensions(evidence / name)
        except (OSError, ValueError) as error:
            errors.append(str(error))
        else:
            expect(width >= 800 and height >= 500, f"screenshot_dimensions:{name}")

    access_fixture = load_json(kit / "config/cloudflare-access-policy.fixture.json")
    expect(access_fixture.get("fixture_only") is True, "access_fixture_marker")
    expect(access_fixture.get("contains_real_identity") is False, "access_real_identity")
    expect(access_fixture.get("contains_real_token") is False, "access_real_token")
    serialized_access = json.dumps(access_fixture).lower()
    expect('"decision": "bypass"' not in serialized_access, "access_bypass")
    expect('"everyone"' not in serialized_access, "access_everyone")
    expect("any_valid_service_token" not in serialized_access, "access_any_token")
    service_policies = [
        item
        for item in access_fixture.get("policies") or []
        if item.get("name") == "CyberBoss status collector"
    ]
    expect(len(service_policies) == 1, "access_service_policy_count")
    if len(service_policies) == 1:
        service = service_policies[0]
        expect(service.get("decision") == "non_identity", "access_service_decision")
        include = service.get("include") or []
        expect(
            len(include) == 1 and set(include[0]) == {"service_token"},
            "access_service_selector",
        )

    license_text = (project / "docs/evidence/CB-000/LICENSE_COMPLIANCE.md").read_text(
        encoding="utf-8"
    )
    notices = (project / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    expect("Corresponding Source" in license_text, "corresponding_source")
    expect("GPL-3.0-only AND AGPL-3.0-only" in license_text, "dual_license")
    expect("upstream clarification" in license_text.lower(), "clarification_record")
    expect("whereabouts-mcp" in notices, "notice_whereabouts")
    inventory = load_json(project / "docs/evidence/CB-000/dependency-license-inventory.json")
    expect(inventory.get("package_count_including_root") == 129, "dependency_count")
    expect(inventory.get("unresolved_licenses") == [], "unresolved_license")

    for path in sorted(changed_paths(repo)):
        if path not in ALLOWED_EXACT and not path.startswith(ALLOWED_PREFIXES):
            errors.append(f"run_scope_violation:{path}")
        if path.startswith(("CyberBoss/app/", "CyberBoss/vendor/")):
            errors.append(f"fixed_source_changed:{path}")

    commands = [
        [sys.executable, str(kit / "scripts/scope_policy.py"), "validate"],
        [
            "node",
            str(kit / "tests/validate_config.js"),
            str(kit / "config/cyberboss.env.example"),
            str(kit / "config/workspaces.json.example"),
        ],
        [sys.executable, str(kit / "tests/test_identity_scope.py")],
        [sys.executable, str(kit / "tests/test_external_adapters.py")],
        ["node", "--test", str(kit / "tests/access-policy-contract.test.js")],
        [sys.executable, str(kit / "scripts/cloudflare_adapter.py"), "plan"],
        [sys.executable, str(kit / "scripts/oci_object_adapter.py"), "plan"],
        [
            sys.executable,
            str(kit / "scripts/secret_scan.py"),
            "--repo",
            str(repo),
            "--scope",
            "CyberBoss",
        ],
        [sys.executable, str(project / "scripts/validate_cb000.py")],
        [
            sys.executable,
            str(kit / "tests/validate_task_dag.py"),
            str(pack / "04_TASK_DAG_EXECUTION_PACK.yaml"),
        ],
        [sys.executable, str(kit / "tests/validate_traceability.py"), str(pack)],
        [sys.executable, str(kit / "tests/validate_no_wait.py"), str(pack)],
        [sys.executable, str(kit / "tests/validate_taskpack.py"), str(pack)],
        [sys.executable, str(project / "scripts/validate_prestage0.py")],
    ]
    for command in commands:
        returncode, output = run(command, repo)
        label = Path(command[1] if len(command) > 1 else command[0]).name
        command_reports.append(
            f"{label}:exit={returncode}:tail={output.strip().splitlines()[-1] if output.strip() else '(empty)'}"
        )
        if returncode != 0:
            errors.append(f"command_failed:{label}")
            errors.extend(f"{label}:{line}" for line in output.splitlines()[-10:])

    return errors, command_reports


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    errors, reports = validate(project)
    for report in reports:
        print(f"COMMAND={report}")
    for error in sorted(set(errors)):
        print(f"ERROR={error}")
    if errors:
        print("CB020_REPO_VALIDATION=FAIL")
        return 1
    state = load_json(project / "machine/facts/task_state.json")
    task_status = next(
        item["status"] for item in state["tasks"] if item["id"] == "CB-020"
    )
    print(
        "CB020_REPO_VALIDATION=PASS "
        f"task_state={task_status} "
        "external_writes=0 provider_activation=activation_pending "
        "p0_findings=0 p1_findings=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
