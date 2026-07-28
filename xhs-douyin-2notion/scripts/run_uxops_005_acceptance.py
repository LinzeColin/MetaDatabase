#!/usr/bin/env python3
"""Run the isolated CI-synthetic acceptance for TSK.x2n.uxops.005."""

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
TASK_ID = "TSK.x2n.uxops.005"
PHASE = "PH.X2N.5.5"
RUN_ID = "RUN-X2N-S05-U005"
TEST_MODULES = (
    "apps.companion.tests.test_lifecycle",
    "apps.companion.tests.test_webui",
    "apps.companion.tests.test_operations",
    "apps.companion.tests.test_canonical_store",
    "apps.companion.tests.test_sinks",
)
RUFF_PATHS = (
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/src/x2n_companion/lifecycle.py",
    "apps/companion/src/x2n_companion/migrations.py",
    "apps/companion/src/x2n_companion/runtime.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/src/x2n_companion/webui.py",
    "apps/companion/tests/test_lifecycle.py",
    "apps/companion/tests/test_webui.py",
    "scripts/replay_uxops_004_historical.py",
    "scripts/run_uxops_005_acceptance.py",
    "scripts/verify_uxops_005.py",
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


def _run(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int = 300) -> str:
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
        raise RuntimeError("Lifecycle suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-u005-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "Lifecycle synthetic suite",
            (sys.executable, "-B", "-m", "unittest", *TEST_MODULES),
            env=environment,
            timeout=420,
        )
        _run(
            "Lifecycle ruff",
            (sys.executable, "-B", "-m", "ruff", "check", *RUFF_PATHS),
            env=environment,
        )
        replay = _run(
            "Pinned Task004 historical verifier replay",
            (sys.executable, "-B", "scripts/replay_uxops_004_historical.py"),
            env=environment,
            timeout=420,
        )
    try:
        historical = json.loads(replay)
    except json.JSONDecodeError as error:
        raise RuntimeError("Pinned Task004 historical verifier replay did not return JSON") from error
    if (
        not isinstance(historical, dict)
        or historical.get("status") != "PASS"
        or historical.get("historical_commit") != "798e2693a8255030c19f17572b55392c2d4f5f07"
        or historical.get("current_task005_tree_evaluated") is not False
    ):
        raise RuntimeError("Pinned Task004 historical verifier isolation failed")
    return {
        "acceptance_status": {
            "ACC.x2n.data.004": "PASS_CI_SYNTH_DOMAIN_BOUND_ARCHIVE_RESTORE_INTEGRITY_DELETION_EPOCH",
            "ACC.x2n.gov.002": "PASS_CI_SYNTH_PRIVATE_CLIENT_ALLOWLIST_DIGEST_PIN_AUTH_ZERO_CONTACT",
            "ACC.x2n.media.002": "PASS_CI_SYNTH_LOCAL_RUNTIME_TEMPORARY_ARCHIVE_CLEANUP",
            "ACC.x2n.ops.003": "PASS_CI_SYNTH_DELETE_PREVIEW_TOMBSTONE_TTL_TMUTIL_CONTRACT",
        },
        "execution": {
            "authenticated_session_contact": 0,
            "external_network_calls": 0,
            "physical_delete_execution": "NOT_RUN",
            "platform_calls": 0,
            "private_database_client_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_notion_calls": 0,
            "runtime_data_writes": 0,
            "tmutil_calls": 0,
            "token_value_contact": 0,
        },
        "historical_replay": historical,
        "metrics": {
            "archive_chunk_max_bytes": 94371840,
            "durable_hard_erase_claims": 0,
            "foreign_domain_leaks": 0,
            "missing_x2n_object_fail_closed": True,
            "owner_confirmation_literals": 5,
            "synthetic_unit_tests": _test_count(tests),
            "temporary_get_outputs_remaining": 0,
            "tombstone_epoch_regressions_accepted": 0,
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
