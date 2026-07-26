#!/usr/bin/env python3
"""Generate sanitized public evidence and validate the CB-010 repo-local work."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PAGE_URL = "https://status.linzezhang.com/"
SNAPSHOT_URL = "https://status.linzezhang.com/data/snapshot.json"
EXPECTED_PROJECT_FIELDS = {
    "name",
    "url",
    "parts",
    "host",
    "db",
    "store",
    "deploy",
    "backup",
    "agent",
    "notify",
    "status",
}
FORBIDDEN_EVIDENCE = re.compile(
    r"(?:"
    r"\b(?:authorization|bearer|context_token|raw_prompt|raw_result|thread_id)\b|"
    r"\bwxid_[A-Za-z0-9_-]*|"
    r"(?:^|[\s\"'])/(?:root|home)/|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:sk|gh[pousr])-[A-Za-z0-9_-]{20,}|"
    r"\b(?:sk|gh[pousr])_[A-Za-z0-9_-]{20,}|"
    r"\b(?!0\.0\.0\.4\b)(?:\d{1,3}\.){3}\d{1,3}\b"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fetch(url: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CyberBoss-CB010-ReadOnly-Observer/1.0",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        return response.status, headers, response.read()


def discover_ovh_access() -> dict[str, Any]:
    ssh_config = Path.home() / ".ssh/config"
    aliases: list[str] = []
    if ssh_config.is_file():
        for raw in ssh_config.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\s*Host\s+(.+?)\s*$", raw, re.IGNORECASE)
            if not match:
                continue
            aliases.extend(
                item
                for item in match.group(1).split()
                if "*" not in item and "?" not in item
            )
    matching_alias_count = sum(
        bool(re.search(r"ovh|cyberboss|singapore|vps", alias, re.IGNORECASE))
        for alias in aliases
    )
    env_names = {
        name
        for name in os.environ
        if re.fullmatch(
            r"(?:CB_)?OVH_(?:HOST|SSH_HOST|SSH_ALIAS)|CYBERBOSS_OVH_HOST", name
        )
    }
    return {
        "discovery_scope": [
            "ssh_config_host_alias_names",
            "ovh_host_environment_variable_names",
        ],
        "ssh_config_readable": ssh_config.is_file(),
        "configured_host_alias_count": len(aliases),
        "matching_ovh_or_cyberboss_alias_count": matching_alias_count,
        "matching_environment_variable_name_count": len(env_names),
        "authorized_target_found": bool(matching_alias_count or env_names),
        "credential_values_read": False,
        "private_key_contents_read": False,
        "target_guessing_performed": False,
    }


def build_public_observation() -> dict[str, Any]:
    page_status, page_headers, page_raw = fetch(PAGE_URL)
    snapshot_status, snapshot_headers, snapshot_raw = fetch(SNAPSHOT_URL)
    page = page_raw.decode("utf-8", errors="replace")
    snapshot = json.loads(snapshot_raw)
    projects = [
        item for item in snapshot.get("projects") or [] if isinstance(item, dict)
    ]
    project_keys = sorted({key for item in projects for key in item})
    field_types = {
        field: sorted(
            {
                "array" if isinstance(item.get(field), list) else type(item.get(field)).__name__
                for item in projects
                if field in item
            }
        )
        for field in project_keys
    }
    page_status_values = sorted(
        value
        for value in ("run", "access", "down")
        if re.search(rf"\b{value}\s*:", page)
        or re.search(rf"{value}\s*:\s*\[", page)
    )
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    cyberboss_rows = sum(
        "cyberboss" in json.dumps(item, ensure_ascii=False).lower()
        for item in projects
    )
    host = snapshot.get("host") or {}
    public_host_metrics: dict[str, int | float] = {}
    for key in (
        "mem_pct",
        "disk_pct",
        "disk_total_b",
        "disk_used_b",
        "load1",
        "uptime_days",
    ):
        value = host.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            public_host_metrics[key] = value
        elif isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?", value):
            public_host_metrics[key] = (
                float(value) if "." in value else int(value)
            )
    observation = {
        "schema_version": 1,
        "task_id": "CB-010",
        "observed_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "read_only_requests": [
            {"method": "GET", "url": PAGE_URL},
            {"method": "GET", "url": SNAPSHOT_URL},
        ],
        "page": {
            "http_status": page_status,
            "content_type": page_headers.get("content-type"),
            "cache_control": page_headers.get("cache-control"),
            "content_security_policy": page_headers.get("content-security-policy"),
            "server": page_headers.get("server"),
            "body_bytes": len(page_raw),
            "body_sha256": sha256_bytes(page_raw),
            "title": title_match.group(1).strip() if title_match else None,
            "snapshot_fetch_path_present": "data/snapshot.json" in page,
        },
        "snapshot": {
            "http_status": snapshot_status,
            "content_type": snapshot_headers.get("content-type"),
            "body_bytes": len(snapshot_raw),
            "body_sha256": sha256_bytes(snapshot_raw),
            "updated_at": snapshot.get("updated_at"),
            "top_level_keys": sorted(snapshot),
            "project_count": len(projects),
            "project_keys": project_keys,
            "project_field_types": field_types,
            "project_status_values_observed": sorted(
                {str(item.get("status")) for item in projects}
            ),
            "project_status_values_from_page_contract": page_status_values,
            "project_part_values_observed": sorted(
                {
                    str(value)
                    for item in projects
                    for value in (item.get("parts") or [])
                }
            ),
            "project_agent_values_observed": sorted(
                {str(item.get("agent")) for item in projects}
            ),
            "cyberboss_row_count": cyberboss_rows,
            "public_host_metrics": public_host_metrics,
        },
        "ovh_access_discovery": discover_ovh_access(),
        "evidence_boundaries": {
            "raw_page_persisted": False,
            "raw_snapshot_persisted": False,
            "project_rows_persisted": False,
            "host_ip_persisted": False,
            "credential_or_secret_persisted": False,
            "proves_public_status_contract": True,
            "proves_live_ovh_preflight": False,
            "may_replace_live_ovh_evidence": False,
        },
    }
    serialized = json.dumps(observation, ensure_ascii=False)
    if FORBIDDEN_EVIDENCE.search(serialized):
        raise ValueError("sanitized_observation_contains_forbidden_pattern")
    return observation


def run(command: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.returncode, result.stdout


def validate(project: Path) -> list[str]:
    errors: list[str] = []
    repo = project.parent
    pack = project / "docs/product_design/v0.0.0.4"
    kit = pack / "implementation-kit"
    evidence = project / "docs/evidence/CB-010"

    def expect(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    required = [
        project / "docs/governance/RUN_CONTRACT_P0_2_CB_010.md",
        project / "machine/facts/task_state.json",
        project / "scripts/validate_cb010.py",
        evidence / "resource-baseline.md",
        evidence / "status-contract.md",
        evidence / "VALIDATION_REPORT.md",
        evidence / "public-status-observation.json",
        evidence / "resource-pressure.local-container.json",
        kit / "scripts/preflight.sh",
        kit / "scripts/select-resource-profile.sh",
        kit / "scripts/resource_profile.py",
        kit / "scripts/resource-pressure-fixture.py",
        kit / "tests/test_resource_profile.py",
        kit / "tests/status-adapter-contract.test.js",
        kit / "status/global-status-contract.fixture.json",
        kit / "status/global-status-adapter.js",
    ]
    for path in required:
        expect(path.is_file(), f"required_file_missing:{path.relative_to(repo)}")
    if any(not path.is_file() for path in required):
        return errors

    observation = load_json(evidence / "public-status-observation.json")
    snapshot_observation = observation.get("snapshot") or {}
    boundaries = observation.get("evidence_boundaries") or {}
    expect((observation.get("page") or {}).get("http_status") == 200, "public_page_http")
    expect(snapshot_observation.get("http_status") == 200, "public_snapshot_http")
    expect(
        set(snapshot_observation.get("project_keys") or []) == EXPECTED_PROJECT_FIELDS,
        "public_project_contract_fields",
    )
    expect(
        snapshot_observation.get("project_status_values_from_page_contract")
        == ["access", "down", "run"],
        "public_project_status_contract",
    )
    expect(boundaries.get("raw_page_persisted") is False, "raw_page_persisted")
    expect(
        boundaries.get("raw_snapshot_persisted") is False,
        "raw_snapshot_persisted",
    )
    expect(
        boundaries.get("may_replace_live_ovh_evidence") is False,
        "public_evidence_replacement_claim",
    )
    expect(
        boundaries.get("proves_live_ovh_preflight") is False,
        "public_evidence_live_claim",
    )
    access = observation.get("ovh_access_discovery") or {}
    expect(access.get("credential_values_read") is False, "access_credential_read")
    expect(access.get("private_key_contents_read") is False, "access_key_read")
    expect(access.get("target_guessing_performed") is False, "access_target_guess")

    contract = load_json(kit / "status/global-status-contract.fixture.json")
    expect(
        set(contract.get("required_fields") or []) == EXPECTED_PROJECT_FIELDS,
        "status_fixture_required_fields",
    )
    expect(
        contract.get("allowed_status_values") == ["run", "access", "down"],
        "status_fixture_allowed_status",
    )
    expect(
        contract.get("cyberboss_row_present_at_observation")
        == bool(snapshot_observation.get("cyberboss_row_count")),
        "status_fixture_row_presence",
    )
    expect(
        contract.get("online_mutation_authorized_by_cb010") is False,
        "status_fixture_online_mutation",
    )

    pressure = load_json(evidence / "resource-pressure.local-container.json")
    expect(pressure.get("result") == "pass", "pressure_result")
    expect(pressure.get("no_sleep") is True, "pressure_no_sleep")
    expect(pressure.get("oom_observed") is False, "pressure_oom")
    cgroup = pressure.get("cgroup_evidence") or {}
    expect(
        cgroup.get("state") == "verified_bounded_local_container",
        "pressure_cgroup_local",
    )
    expect(cgroup.get("oom_kill_delta") == 0, "pressure_cgroup_oom")
    expect(
        cgroup.get("claimed_as_live_host_evidence") is False,
        "pressure_live_host_claim",
    )
    ladder = pressure.get("guard_ladder") or []
    expect(
        [(item.get("step"), item.get("actual")) for item in ladder]
        == [
            ("baseline", "recover"),
            ("queue_burst", "warn"),
            ("memory_protect", "protect"),
            ("disk_protect", "protect"),
            ("inode_protect", "protect"),
            ("queue_protect", "protect"),
            ("recovered", "recover"),
        ],
        "pressure_guard_ladder",
    )

    state = load_json(project / "machine/facts/task_state.json")
    state_tasks = {
        item.get("id"): item.get("status") for item in state.get("tasks") or []
    }
    cb010_status = state_tasks.get("CB-010")
    expect(state_tasks.get("CB-000") == "passed", "state_cb000")
    expect(cb010_status in {"activation_pending", "passed"}, "state_cb010")
    current_run = state.get("current_run") or {}
    expect(current_run.get("run_id") == "P0.2", "state_current_run_id")
    expect(current_run.get("task_id") == "CB-010", "state_current_task_id")
    expect(current_run.get("status") == cb010_status, "state_current_status")
    expect(
        all(
            status == "not_started"
            for task_id, status in state_tasks.items()
            if task_id not in {"CB-000", "CB-010"}
        ),
        "downstream_task_started",
    )
    expect(
        all(
            status == "not_started"
            for status in (state.get("pass_gates") or {}).values()
        ),
        "pass_gate_advanced",
    )

    live_preflight = evidence / "live-host-preflight.redacted.txt"
    live_pressure = evidence / "live-host-pressure.redacted.json"
    if cb010_status == "passed":
        expect(live_preflight.is_file(), "passed_without_live_preflight")
        expect(live_pressure.is_file(), "passed_without_live_pressure")
    else:
        expect(
            access.get("authorized_target_found") is False,
            "activation_pending_with_authorized_target",
        )
        expect(not live_preflight.exists(), "pending_with_live_preflight")
        expect(not live_pressure.exists(), "pending_with_live_pressure")

    commands = [
        [
            sys.executable,
            str(kit / "tests/test_resource_profile.py"),
        ],
        [
            str(kit / "scripts/preflight.sh"),
            "--check",
        ],
        [
            sys.executable,
            str(kit / "scripts/resource-pressure-fixture.py"),
        ],
        [
            "node",
            "--test",
            str(kit / "tests/status-adapter-contract.test.js"),
        ],
    ]
    for command in commands:
        returncode, output = run(command, repo)
        expect(returncode == 0, f"command_failed:{Path(command[0]).name}")
        if returncode != 0:
            errors.append(output[-1000:])

    for path in (
        kit / "scripts/preflight.sh",
        kit / "scripts/select-resource-profile.sh",
        kit / "scripts/resource-pressure-fixture.py",
        kit / "tests/test_resource_profile.py",
    ):
        text = path.read_text(encoding="utf-8")
        expect(
            re.search(r"\bsleep\b", text) is None,
            f"fixed_sleep_present:{path.relative_to(project)}",
        )

    for path in evidence.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            expect(
                FORBIDDEN_EVIDENCE.search(text) is None,
                f"forbidden_evidence:{path.relative_to(project)}",
            )

    allowed_exact = {
        "CyberBoss/CHANGELOG.md",
        "CyberBoss/HANDOFF.md",
        "CyberBoss/README.md",
        "CyberBoss/machine/facts/task_state.json",
        "CyberBoss/scripts/validate_cb000.py",
        "CyberBoss/scripts/validate_cb010.py",
        "CyberBoss/docs/governance/RUN_CONTRACT_P0_2_CB_010.md",
        "CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md",
        "CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md",
        "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/status-snapshot.example.json",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/preflight.sh",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/select-resource-profile.sh",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/resource_profile.py",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/resource-pressure-fixture.py",
    }
    allowed_prefixes = (
        "CyberBoss/docs/evidence/CB-010/",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/status/",
        "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/",
    )
    status_result = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    for raw in status_result.stdout.splitlines():
        path_text = raw[3:]
        candidates = path_text.split(" -> ")
        for candidate in candidates:
            if candidate not in allowed_exact and not candidate.startswith(
                allowed_prefixes
            ):
                errors.append(f"run_scope_violation:{candidate}")

    serialized_observation = json.dumps(observation, ensure_ascii=False)
    expect(
        FORBIDDEN_EVIDENCE.search(serialized_observation) is None,
        "public_observation_forbidden",
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-public-observation", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    evidence = project / "docs/evidence/CB-010"

    if args.write_public_observation:
        observation = build_public_observation()
        write_json(evidence / "public-status-observation.json", observation)
        print(
            "CB010_PUBLIC_OBSERVATION=PASS "
            f"projects={observation['snapshot']['project_count']} "
            f"cyberboss_rows={observation['snapshot']['cyberboss_row_count']} "
            "raw_snapshot_persisted=false live_ovh_claim=false"
        )
        return 0

    errors = validate(project)
    for error in sorted(set(errors)):
        print(f"ERROR={error}")
    if errors:
        print("CB010_REPO_VALIDATION=FAIL")
        return 1
    state = load_json(project / "machine/facts/task_state.json")
    task_status = next(
        item["status"] for item in state["tasks"] if item["id"] == "CB-010"
    )
    print(
        "CB010_REPO_VALIDATION=PASS "
        f"task_state={task_status} "
        f"live_ovh={str(task_status == 'passed').lower()} "
        "public_status_contract=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
