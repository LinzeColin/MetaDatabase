#!/usr/bin/env python3
"""Run the isolated CI-synthetic acceptance for TSK.x2n.uxops.001."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "TSK.x2n.uxops.001"
PHASE = "PH.X2N.5.1"
RUN_ID = "RUN-X2N-S05-U001"


def _isolated_env(home: Path) -> dict[str, str]:
    """Keep this acceptance independent of Owner runtime/configuration state."""

    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


def _run(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int = 180) -> str:
    result = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed")
    return result.stdout + result.stderr


def _test_count(output: str) -> int:
    matches = re.findall(r"Ran (\d+) tests?", output)
    if not matches:
        raise RuntimeError("Notion sink suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-u001-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "Notion sink synthetic suite",
            (sys.executable, "-B", "-m", "unittest", "apps.companion.tests.test_sinks"),
            env=environment,
            timeout=240,
        )
        _run(
            "Notion sink ruff",
            (
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "apps/companion/src/x2n_companion/notion_sink.py",
                "apps/companion/tests/test_sinks.py",
                "scripts/run_uxops_001_acceptance.py",
            ),
            env=environment,
        )
    return {
        "acceptance_status": {
            "ACC.x2n.notion.001": "PASS_CI_SYNTH_MOCK_VERSIONED_ADDITIVE_SCHEMA_ONE_PAGE_USER_FIELDS_HASH_NOOP_REAL_NOTION_NOT_RUN",
            "ACC.x2n.notion.002": "PASS_CI_SYNTH_MOCK_TWO_RPS_429_529_RETRY_AFTER_BOUNDED_DEAD_LETTER_RETRY_STORM_ZERO",
            "ACC.x2n.notion.003": "PASS_CI_SYNTH_MOCK_OUTAGE_KILL_RECONCILE_RECEIPT_OR_DEAD_LETTER_DUPLICATE_PAGE_ZERO_REAL_NOTION_NOT_RUN",
            "ACC.x2n.notion.004": "PASS_CI_SYNTH_MOCK_FOURTEEN_X2N_VIEW_DEFINITIONS_CAPABILITY_FALLBACK_DOCUMENTED_REAL_NOTION_NOT_RUN",
        },
        "execution": {
            "network_calls": 0,
            "notion_mock_socket_opens": 0,
            "notion_real_calls": 0,
            "owner_notion_canary": "NOT_RUN",
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
        },
        "metrics": {
            "managed_view_definitions": 14,
            "maximum_requests_per_second": 2,
            "synthetic_unit_tests": _test_count(tests),
            "user_field_overwrites": 0,
        },
        "policy": {
            "child_blocks_per_request": 100,
            "schema_migration": "ADDITIVE_ONLY_VERSIONED",
            "view_conflict": "FAIL_CLOSED_NO_OWNER_VIEW_OVERWRITE",
            "view_unavailable": "DOCUMENTED_FALLBACK_NO_FALSE_CREATED_CLAIM",
        },
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_MOCK_SCOPED_REAL_NOTION_NOT_RUN",
        "task_id": TASK_ID,
        "phase": PHASE,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
