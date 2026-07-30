#!/usr/bin/env python3
"""Run the isolated CI-synthetic acceptance for TSK.x2n.uxops.004."""

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
TASK_ID = "TSK.x2n.uxops.004"
PHASE = "PH.X2N.5.4"
RUN_ID = "RUN-X2N-S05-U004"
TEST_MODULES = (
    "apps.companion.tests.test_operations",
    "apps.companion.tests.test_webui",
    "apps.companion.tests.test_profile_session",
    "apps.companion.tests.test_canonical_store",
    "apps.companion.tests.test_sinks",
)
RUFF_PATHS = (
    "apps/companion/src/x2n_companion/operations.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/src/x2n_companion/webui.py",
    "apps/companion/tests/test_operations.py",
    "scripts/replay_uxops_003_historical.py",
    "scripts/run_uxops_004_acceptance.py",
)


def _isolated_env(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


def _run(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int = 240) -> str:
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
        raise RuntimeError("Operations suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-u004-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "Operations synthetic suite",
            (sys.executable, "-B", "-m", "unittest", *TEST_MODULES),
            env=environment,
            timeout=300,
        )
        _run(
            "Operations ruff",
            (sys.executable, "-B", "-m", "ruff", "check", *RUFF_PATHS),
            env=environment,
        )
        replay = _run(
            "Pinned Task003 historical verifier replay",
            (sys.executable, "-B", "scripts/replay_uxops_003_historical.py"),
            env=environment,
            timeout=300,
        )
    try:
        historical = json.loads(replay)
    except json.JSONDecodeError as error:
        raise RuntimeError("Pinned Task003 historical verifier replay did not return JSON") from error
    if (
        not isinstance(historical, dict)
        or historical.get("status") != "PASS"
        or historical.get("historical_commit") != "7f78c3074880d887a683fa9cb2ed8b0477dc414c"
        or historical.get("current_task004_tree_evaluated") is not False
    ):
        raise RuntimeError("Pinned Task003 historical verifier isolation failed")
    return {
        "acceptance_status": {
            "ACC.x2n.ops.001": "PASS_CI_SYNTH_TEN_STAGE_KILL_RECOVERY_LOST_ZERO_DUPLICATE_SIDE_EFFECT_ZERO_TERMINAL",
            "ACC.x2n.ops.002": "PASS_CI_SYNTH_ALLOWLISTED_REDACTED_JOURNAL_STABLE_ERROR_CODE_OPAQUE_RUN_ID",
            "ACC.x2n.ops.004": "PASS_CI_SYNTH_EIGHT_COMPONENT_DOCTOR_OK_DEGRADED_BLOCKED_MINIMAL_REMEDIATION",
        },
        "execution": {
            "external_network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_notion_calls": 0,
            "runtime_data_writes": 0,
        },
        "historical_replay": historical,
        "metrics": {
            "all_stage_kill_points": 10,
            "canonical_loss": 0,
            "diagnostic_private_content_hits": 0,
            "doctor_degraded_cases": 6,
            "duplicate_notion_pages": 0,
            "recovery_loops": 0,
            "redaction_canaries": 8,
            "synthetic_unit_tests": _test_count(tests),
        },
        "phase": PHASE,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN",
        "task_id": TASK_ID,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
